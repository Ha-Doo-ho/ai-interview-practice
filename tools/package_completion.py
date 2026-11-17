"""Build a deterministic source-only delivery ZIP without importing the app.

The default is a read-only dry run. Use --build after the delivery documents
are frozen. Existing bundles require the explicit --replace switch.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
POLICY_VERSION = 'completion-source-20261013-1'
ROOT_FILES = ('requirements.txt', 'pytest.ini', 'conftest.py', 'AGENTS.md',
              '.env.example', 'README.md')
SOURCE_SUFFIXES = {
    'app': {'.py', '.html', '.css', '.js', '.json', '.svg', '.png', '.ico'},
    'html': {'.html', '.css', '.js', '.json', '.svg', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.ico'},
    'migrations': {'.sql', '.py', '.md'},
    'tools': {'.py', '.js', '.cjs', '.mjs', '.ps1', '.md'},
    'ai_interview_codex': {'.md', '.json', '.toml', '.csv'},
}
REPORT_NAMES = ('BACKEND_REPORT.md', 'FRONTEND_REPORT.md', 'REVIEW.md',
                'PACKAGE_REPORT.md', 'VERIFICATION.md', 'FINAL_VERIFICATION.md')
EXPLICIT_FIXTURES = ('docs/ai-interview/backend-readiness/20260920-003025-KST/API_SCENARIOS.json',
                     'docs/ai-interview/completion-example-20261013.json')
FORBIDDEN_PARTS = {'__pycache__', '.git', '.venv', 'node_modules', 'runtime',
                   'private', 'secrets', 'attempts', 'temporary', 'runs', 'artifacts'}
FORBIDDEN_SUFFIXES = {'.db', '.sqlite', '.sqlite3', '.pyc', '.pyo', '.pem', '.key',
                      '.pfx', '.p12', '.zip', '.7z', '.tar', '.gz'}
PRIVATE_MATERIAL = re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}\b')


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def _safe_source(root, path):
    relative = path.relative_to(root)
    lower_parts = [part.lower() for part in relative.parts]
    return (not path.is_symlink() and path.resolve().is_relative_to(root)
            and not any(part in FORBIDDEN_PARTS for part in lower_parts)
            and path.suffix.lower() not in FORBIDDEN_SUFFIXES
            and not any(part.startswith('.env') or part.startswith('id_rsa')
                        or part.startswith('id_ed25519') for part in lower_parts))


def collect_sources(root):
    root = Path(root).resolve()
    selected = {}

    def add(path, *, explicit=False):
        if not path.is_file():
            return
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('unsafe_source_path:' + str(path.relative_to(root)))
        if not explicit and not _safe_source(root, path):
            return
        name = path.relative_to(root).as_posix()
        data = path.read_bytes()
        if data.startswith(b'SQLite format 3\x00') or PRIVATE_MATERIAL.search(data):
            raise ValueError('private_material:' + name)
        selected[name] = data

    for name in ROOT_FILES:
        add(root / name, explicit=True)
    for directory, suffixes in SOURCE_SUFFIXES.items():
        source = root / directory
        if source.is_dir():
            for path in source.rglob('*'):
                if path.suffix.lower() in suffixes:
                    add(path)
    tests = root / 'tests'
    if tests.is_dir():
        for path in tests.iterdir():
            if path.suffix.lower() in {'.py', '.js', '.cjs', '.mjs'}:
                add(path)
        fixtures = tests / 'fixtures'
        if fixtures.is_dir():
            for path in fixtures.rglob('*.json'):
                add(path)
    docs = root / 'docs/ai-interview'
    if docs.is_dir():
        for path in docs.glob('*.md'):
            add(path)
    for name in EXPLICIT_FIXTURES:
        add(root / name, explicit=True)
    for name in REPORT_NAMES:
        add(root / 'artifacts/completion-20261013' / name, explicit=True)
    return dict(sorted(selected.items()))


def build_package(root, output, *, dry_run=True, replace=False):
    root = Path(root).resolve()
    output = Path(output).resolve()
    delivery = root / 'artifacts/delivery-20261013'
    if not output.is_relative_to(delivery) or output.suffix.lower() != '.zip':
        raise ValueError('output_must_be_delivery_zip')
    files = collect_sources(root)
    manifest = {
        'policy_version': POLICY_VERSION,
        'source_only': True,
        'included_roots': list(SOURCE_SUFFIXES) + ['tests', 'docs/ai-interview/*.md'],
        'explicit_fixture_exceptions': [name for name in EXPLICIT_FIXTURES if name in files],
        'explicit_completion_reports': [name for name in files if name.startswith('artifacts/')],
        'files': [{'path': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                  for name, data in files.items()],
    }
    payloads = {**files, 'PACKAGE_MANIFEST.json': _json_bytes(manifest)}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(payloads.items()):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    bundle = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(payloads):
            raise ValueError('package_integrity_failed')
        for name, expected in payloads.items():
            if archive.read(name) != expected:
                raise ValueError('package_entry_mismatch:' + name)
    digest = hashlib.sha256(bundle).hexdigest()
    if not dry_run:
        if output.exists() and not replace:
            raise FileExistsError('existing_bundle_requires_explicit_replace')
        output.parent.mkdir(parents=True, exist_ok=True)
        mode = 'wb' if replace else 'xb'
        with output.open(mode) as stream:
            stream.write(bundle)
        output.with_suffix('.manifest.json').write_bytes(_json_bytes(manifest))
        output.with_suffix('.zip.sha256').write_text(f'{digest}  {output.name}\n', encoding='utf-8')
    return {'dry_run': dry_run, 'output': str(output), 'archive_sha256': digest,
            'archive_size': len(bundle), 'source_count': len(files), 'manifest': manifest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true', help='Write ZIP after documents are frozen')
    parser.add_argument('--replace', action='store_true', help='Explicitly replace an existing ZIP')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/delivery-20261013/AI-interview-source-20261013.zip')
    parser.add_argument('--manifest-output', type=Path, help='Optional dry-run manifest inside workspace artifacts')
    args = parser.parse_args()
    result = build_package(ROOT, args.output, dry_run=not args.build, replace=args.replace)
    if args.manifest_output:
        target = args.manifest_output.resolve()
        if not target.is_relative_to(ROOT / 'artifacts'):
            parser.error('manifest-output must be inside workspace artifacts')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_json_bytes(result['manifest']))
    print(json.dumps({key: value for key, value in result.items() if key != 'manifest'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
