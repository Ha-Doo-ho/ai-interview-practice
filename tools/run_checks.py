"""Offline test/sample launcher: select fresh DB before app import.

Usage: python -m tools.run_checks [--output-root PATH] [pytest paths/options]
       python -m tools.run_checks --sample
Every run creates a new directory. Existing DBs and reports are not reused.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def launch():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', type=Path, default=ROOT / 'artifacts/offline-checks')
    parser.add_argument('--sample', action='store_true')
    args, pytest_args = parser.parse_known_args()
    output = args.output_root.resolve()
    if not output.is_relative_to(ROOT):
        parser.error('output-root must be inside this workspace')
    output.mkdir(parents=True, exist_ok=True)
    attempt = Path(tempfile.mkdtemp(prefix='run-', dir=output))
    scratch = attempt / 'temporary'
    scratch.mkdir()
    env = {k: v for k, v in os.environ.items() if k.upper() in
           {'SYSTEMROOT','WINDIR','COMSPEC','SYSTEMDRIVE','PROCESSOR_ARCHITECTURE'}}
    env.update(DATABASE_URL='sqlite:///' + (scratch / 'import.db').as_posix(), AI_LIVE_ENABLED='false',
               PAID_AI_ENABLED='false', COOKIE_SECURE='false', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
               INTERVIEW_OFFLINE_RUN='1', TEMP=str(scratch), TMP=str(scratch))
    config = {'sample': args.sample, 'pytest_args': pytest_args, 'root': str(ROOT), 'attempt': str(attempt)}
    dump(attempt / 'CONFIG.json', config)
    sources = [p for directory in ['app','tests','tools','migrations'] for p in (ROOT / directory).rglob('*')
               if p.is_file() and '__pycache__' not in p.parts]
    dump(attempt / 'SOURCE_HASHES.json', [{'path': p.relative_to(ROOT).as_posix(),
        'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(sources)])
    command = [sys.executable, '-I', '-B', '-X', 'utf8', str(Path(__file__).resolve()), '--child', str(attempt)]
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8')
    (attempt / 'stdout.txt').write_text(result.stdout, encoding='utf-8')
    (attempt / 'stderr.txt').write_text(result.stderr, encoding='utf-8')
    dump(attempt / 'EXECUTION.json', {'command': command, 'exit_code': result.returncode,
         'database_url': env['DATABASE_URL'], 'credentials_inherited': False,
         'source_hashes_sha256': hashlib.sha256((attempt / 'SOURCE_HASHES.json').read_bytes()).hexdigest()})
    print(result.stdout, end='')
    if result.stderr:
        print(result.stderr, file=sys.stderr, end='')
    print('Evidence: ' + str(attempt))
    return result.returncode


def child(attempt):
    config = json.loads((attempt / 'CONFIG.json').read_text(encoding='utf-8'))
    scratch = (attempt / 'temporary').resolve()
    assert scratch.is_relative_to(ROOT) and scratch.is_dir()
    assert os.environ['DATABASE_URL'] == 'sqlite:///' + (scratch / 'import.db').as_posix()
    assert 'app.main' not in sys.modules
    sys.path.insert(0, str(ROOT))
    sys.dont_write_bytecode = True
    platform.uname()  # Cache Windows OS metadata before the subprocess guard.
    import socket
    socket_source = str(Path(socket.__file__).resolve())
    events = []
    violations = []
    provider_transport_attempts = []
    canary = False

    def internal_socketpair(address):
        if not isinstance(address, tuple) or address[0] not in {'127.0.0.1','::1'}:
            return False
        frame = sys._getframe(1)
        while frame:
            if frame.f_code.co_filename == socket_source and frame.f_code.co_name == '_fallback_socketpair':
                return True
            frame = frame.f_back
        return False

    def deny(kind):
        events.append({'event': kind, 'canary': canary, 'blocked': True})
        if not canary:
            violations.append(kind)
        raise PermissionError('offline_check_guard:' + kind)

    def audit(event, values):
        if event == 'sqlite3.connect':
            value = str(values[0])
            if value == ':memory:':
                return
            target = Path(value).resolve()
            if not target.is_relative_to(scratch):
                deny('outside_temporary_db')
            events.append({'event': event, 'path': str(target)})
        elif event in {'socket.connect','socket.connect_ex','socket.bind'}:
            if internal_socketpair(values[1]):
                return  # Only stdlib local wakeup sockets, not HTTP/network clients.
            deny('network')
        elif event in {'socket.getaddrinfo','socket.sendto','urllib.Request','subprocess.Popen','os.system'}:
            deny(event)
        elif event == 'open' and isinstance(values[0], (str, bytes, os.PathLike)):
            target = Path(os.fsdecode(values[0])).resolve()
            if target == Path(os.devnull).resolve():
                return
            mode, flags = values[1] or '', values[2] or 0
            writing = any(c in mode for c in 'wax+') or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if writing and not target.is_relative_to(attempt):
                deny('write_outside_attempt')
    sys.addaudithook(audit)
    canary = True
    rejected = []
    import sqlite3
    for name, fn in [('db', lambda: sqlite3.connect(str(attempt / 'forbidden.db'))),
                     ('network', lambda: sys.audit('socket.connect', None, ('example.invalid', 443)))]:
        try:
            fn()
        except PermissionError:
            rejected.append(name)
    canary = False
    assert rejected == ['db','network'] and not (attempt / 'forbidden.db').exists()
    from app.ai_provider import LiveProvider
    def blocked_transport(*args, **kwargs):
        provider_transport_attempts.append('blocked')
        deny('external_model_transport')
    LiveProvider._http_transport = staticmethod(blocked_transport)
    code = 1
    outcome = []
    http_count = {'requests': 0}
    try:
        from app import main
        assert main.DEFINITIONS['runtime_mode'] == 'mock'
        with main.app.state.store.engine.connect() as conn:
            binding = [list(r) for r in conn.exec_driver_sql('PRAGMA database_list')]
        assert any(r[1] == 'main' and Path(r[2]).resolve() == scratch / 'import.db' for r in binding)
        # Observe the real ASGI transport, not a network server or mocked route.
        from fastapi import FastAPI
        original_call = FastAPI.__call__
        async def counted_call(self, scope, receive, send):
            if scope['type'] == 'http':
                http_count['requests'] += 1
            return await original_call(self, scope, receive, send)
        FastAPI.__call__ = counted_call
        if config['sample']:
            from tools.generate_sample import main as generate
            generate(output_dir=attempt / 'sample')
            code = 0
        else:
            import pytest
            class Observer:
                def pytest_runtest_logreport(self, report):
                    if report.when == 'call' or report.failed or report.skipped:
                        outcome.append({'nodeid': report.nodeid, 'when': report.when, 'outcome': report.outcome,
                                        'duration': report.duration,
                                        'details': str(report.longrepr) if report.failed else None})
            # Fixed output options follow user arguments so protected files stay protected.
            args = config['pytest_args'] or ['tests']
            args = [*args, '-q', '-p', 'no:cacheprovider', '--basetemp', str(scratch / 'pytest'),
                    '--harness-report', str(attempt / 'harness-results.json')]
            code = int(pytest.main(args, plugins=[Observer()]))
        main.app.state.store.engine.dispose()
    finally:
        dump(attempt / 'RESULTS.json', {'pytest_or_sample_exit_code': code, 'test_reports': outcome,
             'http_requests_observed': http_count['requests'], 'provider_transport_attempts': provider_transport_attempts,
             'db_and_guard_events': events, 'guard_violations': violations,
             'scope': 'In-process real FastAPI + isolated SQLite, synthetic/mock only; no browser/MySQL/live AI'})
    return code if not violations else 1


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--child':
        raise SystemExit(child(Path(sys.argv[2]).resolve()))
    raise SystemExit(launch())
