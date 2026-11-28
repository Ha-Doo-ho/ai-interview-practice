from __future__ import annotations

import copy
import sys
import threading
import types
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.content import DEFINITIONS
from app.main import create_app


HEADERS = {"X-Requested-With": "interview-app"}


def _register(client: TestClient, username: str = "analysis-owner") -> dict:
    response = client.post(
        "/api/register",
        headers=HEADERS,
        json={"username": username, "password": "synthetic-password"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _new_run(client: TestClient) -> dict:
    response = client.post("/api/runs", headers=HEADERS, json={})
    assert response.status_code == 201, response.text
    return response.json()


def _answer_all(client: TestClient, run: dict, *, prefix: str = "합성 답변") -> dict:
    for question in [q for q in run["questions"] if q["question_mode"] == "baseline"]:
        response = client.post(
            f"/api/runs/{run['run_id']}/answers",
            headers=HEADERS,
            json={
                "expected_revision": run["revision"],
                "idempotency_key": str(uuid4()),
                "question_id": question["question_id"],
                "status": "asked_answered",
                "text": f"{prefix}: {question['question_id']}",
            },
        )
        assert response.status_code == 200, response.text
        run = response.json()
    return run


def _input_snapshot(run: dict, _definitions: dict) -> dict:
    return {
        "generation": run["generation"],
        "definitions_version": DEFINITIONS["version"],
        "answer_refs": [
            [record["data"]["answer_id"], record["data"]["answer_version"]]
            for record in run["records"]
            if record.get("source_type") == "typed_answer"
        ],
        "survey_refs": [record["record_id"] for record in run["records"] if record.get("source_type") == "survey"],
        "game_state_version": run.get("game", {}).get("state_version"),
        "rule_games_state_version": run.get("rule_games", {}).get("state_version"),
    }


def _fake_module(*, calls_required: int = 1, cost_microusd: int = 7, execute=None):
    module = types.ModuleType("app.interview_analysis")
    module.analysis_capabilities = lambda: {
        "live_available": True,
        "reason": None,
        "model_id": "synthetic-model",
        "max_calls_per_run": 2,
        "max_cost_microusd": 14,
    }
    module.input_snapshot = _input_snapshot

    def prepare(run, definitions, mode):
        return {
            "run": copy.deepcopy(run),
            "definitions": copy.deepcopy(definitions),
            "requested_mode": mode,
            "input_snapshot": _input_snapshot(run, definitions),
            "calls_required": calls_required,
            "cost_microusd": cost_microusd,
            "max_calls_per_run": 2,
            "max_cost_microusd": 14,
        }

    module.prepare_analysis = prepare

    def default_execute(prepared, *, before_call=None):
        if before_call:
            before_call()
        snapshot = _input_snapshot(prepared["run"], prepared["definitions"])
        return {
            "runtime_mode": "mock",
            "requested_mode": prepared["requested_mode"],
            "provider_execution": "test_double" if prepared["requested_mode"] == "live" else "not_called",
            "model_id": "synthetic-model",
            "input_snapshot": snapshot,
            "report": {"report_id": "synthetic-report", "cards": [], "surveys": [], "rule_games": []},
        }

    module.execute_analysis = execute or default_execute
    return module


def _request(client: TestClient, run: dict, key: str, mode: str = "live"):
    return client.post(
        f"/api/runs/{run['run_id']}/interview-analysis",
        headers=HEADERS,
        json={"expected_revision": run["revision"], "idempotency_key": key, "mode": mode},
    )


def test_failed_provider_persists_safe_status_without_private_error_data(tmp_path, monkeypatch):
    from app.ai_provider import ProviderError
    from app.store import InterviewAnalysisRequestRow
    def fail(prepared, *, before_call=None):
        if before_call: before_call()
        raise ProviderError('gemini_http_503')
    monkeypatch.setitem(sys.modules, 'app.interview_analysis', _fake_module(execute=fail))
    app=create_app(f"sqlite:///{tmp_path / 'analysis.db'}")
    with TestClient(app) as client:
        _register(client);run=_answer_all(client,_new_run(client))
        response=_request(client,run,'synthetic-failure')
        assert response.status_code==422 and response.json()=={'error':'gemini_http_503'}
        from sqlalchemy.orm import Session
        with Session(app.state.store.engine) as session:
            row=session.scalar(select(InterviewAnalysisRequestRow))
            assert row.status=='failed' and row.response=={'error_code':'gemini_http_503'}


def test_failed_reservation_does_not_store_untrusted_error_text(tmp_path, monkeypatch):
    from app.store import InterviewAnalysisRequestRow
    def fail(prepared, *, before_call=None):
        if before_call: before_call()
        raise RuntimeError('private key and private answer')
    monkeypatch.setitem(sys.modules, 'app.interview_analysis', _fake_module(execute=fail))
    app=create_app(f"sqlite:///{tmp_path / 'analysis.db'}")
    with TestClient(app) as client:
        _register(client);run=_answer_all(client,_new_run(client))
        response=_request(client,run,'synthetic-private-error')
        assert 'private' not in response.text
        from sqlalchemy.orm import Session
        with Session(app.state.store.engine) as session:
            row=session.scalar(select(InterviewAnalysisRequestRow))
            assert row.status=='failed' and row.response is None


def test_capabilities_lists_missing_server_settings_without_values(tmp_path, monkeypatch):
    from test_live_interview_analysis import _configure_live

    _configure_live(monkeypatch)
    monkeypatch.delenv('AI_PROVIDER_KEY', raising=False)
    application=create_app(f"sqlite:///{tmp_path / 'missing-settings.db'}")
    with TestClient(application) as client:
        _register(client)
        response=client.get('/api/interview-analysis-capabilities')
        assert response.status_code==200
        assert response.json()['reason']=='live_not_configured'
        assert response.json()['missing_settings']==['AI_PROVIDER_KEY']


def test_capabilities_and_analysis_save_new_namespace_without_changing_evidence(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "app.interview_analysis", _fake_module())
    app = create_app(f"sqlite:///{tmp_path / 'analysis.db'}")
    with TestClient(app) as client:
        assert client.get("/api/interview-analysis-capabilities").status_code == 401
        _register(client)
        capability = client.get("/api/interview-analysis-capabilities")
        assert capability.status_code == 200
        assert capability.json() == {
            "live_available": True,
            "reason": None,
            "model_id": "synthetic-model",
            "max_calls_per_run": 2,
            "max_cost_microusd": 14,
        }
        run = _answer_all(client, _new_run(client))
        evidence = copy.deepcopy({key: run[key] for key in ("records", "game", "questions")})

        response = _request(client, run, "analysis-1")
        assert response.status_code == 200, response.text
        saved = response.json()
        assert saved["revision"] == run["revision"] + 1
        assert saved["interview_analysis"]["provider_execution"] == "test_double"
        assert saved["interview_report"] == saved["interview_analysis"]["report"]
        assert saved["interview_report_stale"] is False
        assert {key: saved[key] for key in evidence} == evidence
        assert saved["analysis"] is None and saved["report"] is None

        replay = _request(client, run, "analysis-1")
        assert replay.status_code == 200
        assert replay.json() == saved


def test_strict_body_prerequisites_and_mode_do_not_call_provider(tmp_path, monkeypatch):
    called = []

    def execute(_prepared, *, before_call=None):
        called.append(True)
        raise AssertionError("provider must not run")

    monkeypatch.setitem(sys.modules, "app.interview_analysis", _fake_module(execute=execute))
    app = create_app(f"sqlite:///{tmp_path / 'validation.db'}")
    with TestClient(app) as client:
        _register(client)
        run = _new_run(client)
        invalid = client.post(
            f"/api/runs/{run['run_id']}/interview-analysis",
            headers=HEADERS,
            json={"expected_revision": 0, "idempotency_key": "x", "mode": "live", "extra": True},
        )
        assert invalid.status_code == 422 and invalid.json() == {"error": "validation_error"}
        no_answers = _request(client, run, "no-answers")
        assert no_answers.status_code == 409
        assert no_answers.json() == {"error": "baseline_answers_incomplete"}
        run = _answer_all(client, run)
        bad_mode = _request(client, run, "bad-mode", "automatic")
        assert bad_mode.status_code == 422 and bad_mode.json() == {"error": "mode_invalid"}
        assert called == []


def test_failed_reservation_is_not_retried_and_budget_counts_failures_after_restart(tmp_path, monkeypatch):
    calls = []

    def fail(_prepared, *, before_call=None):
        if before_call:
            before_call()
        calls.append("called")
        raise RuntimeError("synthetic provider failure with secret payload")

    module = _fake_module(execute=fail)
    monkeypatch.setitem(sys.modules, "app.interview_analysis", module)
    url = f"sqlite:///{tmp_path / 'budget.db'}"
    app = create_app(url)
    with TestClient(app) as client:
        _register(client)
        run = _answer_all(client, _new_run(client))
        first = _request(client, run, "failed-key")
        assert first.status_code == 422
        assert first.json() == {"error": "analysis_provider_error"}
        again = _request(client, run, "failed-key")
        assert again.status_code == 409
        assert again.json() == {"error": "analysis_request_failed"}
        assert calls == ["called"]

    restarted = create_app(url)
    monkeypatch.setitem(sys.modules, "app.interview_analysis", _fake_module(calls_required=2, cost_microusd=14))
    with TestClient(restarted) as client:
        login = client.post("/api/login", headers=HEADERS, json={"username": "analysis-owner", "password": "synthetic-password"})
        assert login.status_code == 200
        current = client.get(f"/api/runs/{run['run_id']}").json()
        over_budget = _request(client, current, "new-key")
        assert over_budget.status_code == 422
        assert over_budget.json() == {"error": "budget_exceeded"}
        assert calls == ["called"]


def test_concurrent_same_key_reserves_once_and_running_key_never_calls_twice(tmp_path, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def blocked(prepared, *, before_call=None):
        if before_call:
            before_call()
        calls.append("called")
        entered.set()
        assert release.wait(5)
        return _fake_module().execute_analysis(prepared, before_call=before_call)

    monkeypatch.setitem(
        sys.modules,
        "app.interview_analysis",
        _fake_module(calls_required=2, cost_microusd=14, execute=blocked),
    )
    app = create_app(f"sqlite:///{tmp_path / 'concurrent.db'}")
    with TestClient(app) as setup:
        _register(setup)
        run = _answer_all(setup, _new_run(setup))
        cookies = dict(setup.cookies)

    results = []

    def invoke():
        with TestClient(app) as client:
            client.cookies.update(cookies)
            results.append(_request(client, run, "same-key"))

    first = threading.Thread(target=invoke)
    first.start()
    assert entered.wait(5)
    invoke()
    with TestClient(app) as other:
        other.cookies.update(cookies)
        over_budget = _request(other, run, "different-key")
        assert over_budget.status_code == 422
        assert over_budget.json() == {"error": "budget_exceeded"}
    release.set()
    first.join(5)
    assert len(results) == 2
    assert sorted(response.status_code for response in results) == [200, 409]
    conflict = next(response for response in results if response.status_code == 409)
    assert conflict.json() == {"error": "analysis_request_running"}
    assert calls == ["called"]


def test_late_provider_result_after_revision_change_is_discarded_and_report_becomes_stale(tmp_path, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    provider_calls = []

    def blocked(prepared, *, before_call=None):
        if before_call:
            before_call()
        provider_calls.append("first")
        entered.set()
        assert release.wait(5)
        if before_call:
            before_call()
        provider_calls.append("second")
        return _fake_module().execute_analysis(prepared, before_call=None)

    monkeypatch.setitem(sys.modules, "app.interview_analysis", _fake_module(execute=blocked))
    app = create_app(f"sqlite:///{tmp_path / 'late.db'}")
    with TestClient(app) as setup:
        _register(setup)
        run = _answer_all(setup, _new_run(setup))
        cookies = dict(setup.cookies)

        result = []

        def invoke():
            with TestClient(app) as client:
                client.cookies.update(cookies)
                result.append(_request(client, run, "late-key"))

        thread = threading.Thread(target=invoke)
        thread.start()
        assert entered.wait(5)
        question = next(q for q in run["questions"] if q["question_mode"] == "baseline")
        prior = next(r for r in run["records"] if r.get("data", {}).get("question_id") == question["question_id"])
        changed = setup.post(
            f"/api/runs/{run['run_id']}/answers",
            headers=HEADERS,
            json={
                "expected_revision": run["revision"],
                "idempotency_key": "answer-change",
                "question_id": question["question_id"],
                "status": "asked_answered",
                "text": "합성 정정 답변",
                "replaces_answer_id": prior["data"]["answer_id"],
                "expected_answer_version": prior["data"]["answer_version"],
            },
        )
        assert changed.status_code == 200
        release.set()
        thread.join(5)
        assert result[0].status_code == 409
        assert result[0].json() == {"error": "revision_conflict"}
        assert provider_calls == ["first"]
        current = setup.get(f"/api/runs/{run['run_id']}").json()
        assert current.get("interview_analysis") is None

    # A stored report becomes stale after a later answer revision, but the
    # analysis mutation itself did not mark its own report stale.
    monkeypatch.setitem(sys.modules, "app.interview_analysis", _fake_module())
    app2 = create_app(f"sqlite:///{tmp_path / 'stale.db'}")
    with TestClient(app2) as client:
        _register(client, "stale-owner")
        run = _answer_all(client, _new_run(client))
        saved = _request(client, run, "stored-report").json()
        assert saved["interview_report_stale"] is False
        question = next(q for q in saved["questions"] if q["question_mode"] == "baseline")
        prior = next(r for r in saved["records"] if r.get("data", {}).get("question_id") == question["question_id"])
        changed = client.post(
            f"/api/runs/{saved['run_id']}/answers",
            headers=HEADERS,
            json={
                "expected_revision": saved["revision"], "idempotency_key": "stale-change",
                "question_id": question["question_id"], "status": "asked_answered", "text": "변경된 합성 답변",
                "replaces_answer_id": prior["data"]["answer_id"],
                "expected_answer_version": prior["data"]["answer_version"],
            },
        )
        assert changed.status_code == 200
        assert changed.json()["interview_report_stale"] is True


def test_delete_during_provider_call_purges_reservation_and_discards_result(tmp_path, monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    def blocked(prepared, *, before_call=None):
        if before_call:
            before_call()
        entered.set()
        assert release.wait(5)
        return _fake_module().execute_analysis(prepared, before_call=None)

    monkeypatch.setitem(sys.modules, "app.interview_analysis", _fake_module(execute=blocked))
    app = create_app(f"sqlite:///{tmp_path / 'delete.db'}")
    with TestClient(app) as setup:
        _register(setup)
        run = _answer_all(setup, _new_run(setup))
        cookies = dict(setup.cookies)
        result = []

        def invoke():
            with TestClient(app) as client:
                client.cookies.update(cookies)
                result.append(_request(client, run, "delete-key"))

        thread = threading.Thread(target=invoke)
        thread.start()
        assert entered.wait(5)
        deleted = setup.delete(f"/api/runs/{run['run_id']}", headers=HEADERS)
        assert deleted.status_code == 204
        release.set()
        thread.join(5)
        assert result[0].status_code == 410
        assert result[0].json() == {"error": "cancelled_after_deletion"}

    from app.store import InterviewAnalysisRequestRow, Session

    with Session(app.state.store.engine) as session:
        assert session.scalars(select(InterviewAnalysisRequestRow)).all() == []


def test_explicit_mock_uses_real_analysis_pipeline_without_provider_or_prerequisite_games(tmp_path, monkeypatch):
    import app.interview_analysis as interview_analysis

    provider_calls = []

    def forbidden_provider(*_args, **_kwargs):
        provider_calls.append("called")
        raise AssertionError("mock mode must not call a provider")

    monkeypatch.setattr(interview_analysis, "_PROVIDER_TRANSPORT", forbidden_provider)
    app = create_app(f"sqlite:///{tmp_path / 'real-mock.db'}")
    with TestClient(app) as client:
        _register(client, "real-mock-owner")
        run = _answer_all(client, _new_run(client))
        original = copy.deepcopy({key: run[key] for key in ("records", "game", "questions")})
        response = _request(client, run, "explicit-mock", mode="mock")
        assert response.status_code == 200, response.text
        saved = response.json()
        assert saved["interview_analysis"]["requested_mode"] == "mock"
        assert saved["interview_analysis"]["runtime_mode"] == "mock"
        assert saved["interview_analysis"]["provider_execution"] == "not_called"
        assert saved["interview_report"]["cards"]
        assert saved["interview_report_stale"] is False
        assert {key: saved[key] for key in original} == original
        assert provider_calls == []
