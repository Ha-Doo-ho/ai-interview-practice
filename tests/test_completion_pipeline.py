"""Synthetic SQLite/API integration for the new interview completion path."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content import DEFINITIONS
from app.main import create_app
from app.store import IdempotencyRow, InterviewAnalysisRequestRow, RunRow

HEADERS = {"X-Requested-With": "interview-app"}


@pytest.fixture
def api(tmp_path, monkeypatch):
    clock = [datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)]
    monkeypatch.setattr("app.rule_games._now", lambda: clock[0])
    app = create_app(f"sqlite:///{tmp_path / 'completion.db'}")
    with TestClient(app) as client:
        owner = client.post("/api/register", headers=HEADERS,
                            json={"username": "completion-owner", "password": "synthetic-password"})
        assert owner.status_code == 201
        run = client.post("/api/runs", headers=HEADERS, json={}).json()
        yield client, app, owner.json(), run, clock
    app.state.store.engine.dispose()


def post(client, run, operation, **extra):
    body = {"expected_revision": run["revision"], "idempotency_key": str(uuid4()), **extra}
    response = client.post(f"/api/runs/{run['run_id']}/{operation}", headers=HEADERS, json=body)
    return response, body


def ok(client, run, operation, **extra):
    result, _ = post(client, run, operation, **extra)
    assert result.status_code == 200, result.text
    return result.json()


def journey(api, *, games=True, mode="mock"):
    client, _app, _owner, run, clock = api
    for item in DEFINITIONS["surveys"]:
        kind = item["type"]
        response = ({"selected_position": 3} if kind == "ordinal_6" else
                    {"self": {"status": "skipped"}, "imagined_others": {"status": "skipped"}}
                    if kind == "paired_perspective" else
                    {"final_value": None, "interaction_occurred": False,
                     "explicit_confirmation": False, "change_count": 0}
                    if kind == "bipolar_slider" else {"selected_ids": [], "selection_events": []})
        if item["item_id"] == "O-B01":
            response = {"selected_position": 6}
        run = ok(client, run, "surveys", item_id=item["item_id"],
                 item_version=item["item_version"], response=response,
                 status="submitted" if item["item_id"] == "O-B01" else "skipped")
    if games:
        for game_type in ("rsp", "card"):
            for _ in range(3):
                run = ok(client, run, "rule-games", game_type=game_type, action="start")
                round_id = run["rule_games"]["games"][game_type]["rounds"][-1]["round_id"]
                run = accepted_game_answer(client, run, game_type)
                clock[0] += timedelta(seconds=10)
                run = ok(client, run, "rule-games", game_type=game_type, action="reveal", round_id=round_id)
                run = accepted_game_answer(client, run, game_type)
                clock[0] += timedelta(seconds=10)
                run = ok(client, run, "rule-games", game_type=game_type, action="finish", round_id=round_id)
    for index, question in enumerate(DEFINITIONS["questions"]):
        run = ok(client, run, "answers", question_id=question["question_id"],
                 status="asked_answered" if index == 0 else "skipped",
                 text="팀원에게 제약을 물었고 계획에 반영했습니다." if index == 0 else "")
    return ok(client, run, "interview-analysis", mode=mode)


def accepted_game_answer(client, run, game_type):
    round_state = run["rule_games"]["games"][game_type]["rounds"][-1]
    stimulus = round_state["stimulus"]
    if game_type == "rsp":
        opponent = stimulus["opponent_hand"]
        rule = round_state["rule"]["rule_id"]
        choice = ({"rock": "paper", "paper": "scissors", "scissors": "rock"}[opponent]
                  if rule == "rsp-win" else
                  {"rock": "scissors", "paper": "rock", "scissors": "paper"}[opponent]
                  if rule == "rsp-lose" else opponent)
    else:
        choice = stimulus["cards"][0]["card_id"]
    return ok(client, run, "rule-games", game_type=game_type, action="answer",
              round_id=round_state["round_id"], stimulus_id=stimulus["stimulus_id"], choice=choice)


def test_whole_journey_exact_replay_restore_optional_followups_and_delete(api):
    client, app, owner, _run, _clock = api
    run = journey(api)
    baseline = deepcopy(run["interview_analysis"])
    linked, link_body = post(client, run, "evidence-linkage")
    assert linked.status_code == 200, linked.text
    run = linked.json()
    assert run["evidence_linkage_stale"] is False
    questions = run["evidence_linkage"]["questions"]
    observations = run["evidence_linkage"]["observations"]
    assert len(observations) == 6
    assert all(item["before"]["accepted_count"] == item["after"]["accepted_count"] == 1 for item in observations)
    assert all(item["response_details"] and item["event_refs"] for item in observations)
    assert questions and all(q["conditioned_on_prior_evidence"] for q in questions)
    replay = client.post(f"/api/runs/{run['run_id']}/evidence-linkage", headers=HEADERS, json=link_body)
    assert replay.json() == run
    changed_retry = client.post(f"/api/runs/{run['run_id']}/evidence-linkage", headers=HEADERS,
                                json={**link_body, "expected_revision": run["revision"]})
    assert changed_retry.status_code == 409
    assert changed_retry.json() == {"error": "idempotency_conflict"}
    assert client.get(f"/api/runs/{run['run_id']}").json() == run
    assert run["interview_analysis"] == baseline
    finalized, finalize_body = post(client, run, "interview-finalize")
    assert finalized.status_code == 200, finalized.text
    final = finalized.json()
    assert final["status"] == "completed" and final["completed_at"]
    assert final["interview_analysis"] == baseline
    assert final["interview_report"]["cards"] == baseline["report"]["cards"]
    assert final["interview_report"]["status"] == "finalized"
    assert final["report"] == final["interview_report"]
    assert len(final["interview_report"]["followup_answers"]) == len(questions)
    assert all(item["status"] == "not_answered" for item in final["interview_report"]["followup_answers"])
    assert client.post(f"/api/runs/{run['run_id']}/interview-finalize", headers=HEADERS,
                       json=finalize_body).json() == final
    changed_retry = client.post(f"/api/runs/{run['run_id']}/interview-finalize", headers=HEADERS,
                                json={**finalize_body, "expected_revision": final["revision"]})
    assert changed_retry.status_code == 409
    assert changed_retry.json() == {"error": "idempotency_conflict"}
    rejected, _ = post(client, final, "interview-finalize")
    assert rejected.status_code == 409
    rejected, _ = post(client, final, "evidence-linkage")
    assert rejected.status_code == 409
    assert client.get("/api/runs").json()["runs"][0] == final
    rejected, _ = post(client, final, "answers", question_id=questions[0]["question_id"], text="후속 답변")
    assert rejected.status_code == 409
    assert client.delete(f"/api/runs/{run['run_id']}", headers=HEADERS).status_code == 204
    assert client.get(f"/api/runs/{run['run_id']}").status_code == 404
    assert client.post(f"/api/runs/{run['run_id']}/interview-finalize", headers=HEADERS,
                       json=finalize_body).status_code == 404
    assert client.post(f"/api/runs/{run['run_id']}/evidence-linkage", headers=HEADERS,
                       json=link_body).status_code == 404
    assert client.get("/api/runs").json() == {"runs": []}
    with pytest.raises(Exception, match="not_found"):
        app.state.store.get_run(owner["user_id"], run["run_id"])
    with Session(app.state.store.engine) as session:
        tombstone = session.scalar(select(RunRow).where(RunRow.run_id == run["run_id"]))
        assert tombstone.snapshot is None and tombstone.status == "deleted"
        assert tombstone.generation == final["generation"] + 1
        assert session.scalar(select(IdempotencyRow).where(IdempotencyRow.run_id == run["run_id"])) is None
        assert session.scalar(select(InterviewAnalysisRequestRow).where(InterviewAnalysisRequestRow.run_id == run["run_id"])) is None


def test_followup_provenance_is_server_owned_and_neutral_report_stays_current(api):
    client, _app, _owner, _run, _clock = api
    initial = journey(api)
    linked, linkage_body = post(client, initial, "evidence-linkage")
    assert linked.status_code == 200
    run = linked.json()
    linked_response = deepcopy(run)
    baseline = deepcopy(run["interview_analysis"])
    question = run["evidence_linkage"]["questions"][0]
    run = ok(client, run, "answers", question_id=question["question_id"], text="후속 자기보고",
             generated_from_evidence_refs=["foreign-source"], disclosed_prior_information=["spoofed"],
             question_mode="baseline", conditioned_on_prior_evidence=False)
    answer = run["records"][-1]["data"]
    assert answer["generated_from_evidence_refs"] == question["generated_from_evidence_refs"]
    assert answer["disclosed_prior_information"] == question["disclosed_prior_information"]
    assert answer["question_mode"] == "adaptive_followup"
    assert answer["conditioned_on_prior_evidence"] is True
    assert answer["linkage_id"] == question["linkage_id"]
    assert answer["source_report_id"] == question["source_report_id"]
    assert run["interview_report_stale"] is False and run["evidence_linkage_stale"] is False
    assert run["interview_analysis"] == baseline
    assert client.post(f"/api/runs/{run['run_id']}/evidence-linkage", headers=HEADERS,
                       json=linkage_body).json() == linked_response
    final = ok(client, run, "interview-finalize")
    saved = final["interview_report"]["followup_answers"][0]
    assert saved["text"] == "후속 자기보고" and saved["status"] == "asked_answered"
    assert saved["generated_from_evidence_refs"] == question["generated_from_evidence_refs"]


@pytest.mark.parametrize("status", ["skipped", "asked_no_text"])
def test_optional_followup_missingness_is_explicit_and_neutral_cards_immutable(api, status):
    client, _app, _owner, _run, _clock = api
    run = ok(client, journey(api), "evidence-linkage")
    baseline = deepcopy(run["interview_analysis"])
    question = run["evidence_linkage"]["questions"][0]
    run = ok(client, run, "answers", question_id=question["question_id"], text="", status=status)
    assert run["interview_report_stale"] is False and run["evidence_linkage_stale"] is False
    final = ok(client, run, "interview-finalize")
    assert final["interview_analysis"] == baseline
    assert final["interview_report"]["cards"] == baseline["report"]["cards"]
    followup = final["interview_report"]["followup_answers"][0]
    assert followup["status"] == status and followup["text"] == ""


def test_public_linkage_currentness_fails_closed_on_unreadable_lineage(api, monkeypatch):
    client, _app, _owner, _run, _clock = api
    run = ok(client, journey(api), "evidence-linkage")

    def cannot_read(*args):
        raise ValueError("synthetic invalid lineage")

    monkeypatch.setattr("app.evidence_linkage.linkage_is_current", cannot_read)
    restored = client.get(f"/api/runs/{run['run_id']}")
    assert restored.status_code == 200
    assert restored.json()["evidence_linkage_stale"] is True


def test_requested_live_offline_transport_quotes_link_finalize_and_restart(api, monkeypatch):
    import app.interview_analysis as analysis
    from test_live_interview_analysis import _configure_live, _model_result

    client, app, _owner, _run, _clock = api
    _configure_live(monkeypatch)
    provider_inputs = []

    def offline_transport(_endpoint, payload, **_kwargs):
        item = json.loads(payload["input"][0]["content"][0]["text"])
        provider_inputs.append(item)
        return {"status": "completed", "output_text": json.dumps(
            _model_result(item["answer"]["text"], item["question"]), ensure_ascii=False)}

    monkeypatch.setattr(analysis, "_PROVIDER_TRANSPORT", offline_transport)
    run = journey(api, mode="live")
    baseline = deepcopy(run["interview_analysis"])
    assert baseline["requested_mode"] == "live"
    assert baseline["runtime_mode"] == "mock" and baseline["provider_execution"] == "test_double"
    assert len(provider_inputs) == 1
    assert set(provider_inputs[0]) == {"question", "answer", "behavior", "rubric"}
    assert "매우 그렇다" not in json.dumps(provider_inputs, ensure_ascii=False)
    assert "rule-rsp" not in json.dumps(provider_inputs, ensure_ascii=False)
    run = ok(client, run, "evidence-linkage")
    link = next(item for item in run["evidence_linkage"]["links"] if item["behavior_id"] == "B01")
    spans = [span for item in link["interview_refs"] for span in item["evidence_spans"]]
    assert spans
    for span in spans:
        original = next(r["data"] for r in run["records"]
                        if r.get("data", {}).get("answer_id") == span["source_id"])
        assert span["source_version"] == original["answer_version"]
        assert span["quote"] == original["text"][span["start"]:span["end"]]
    question = run["evidence_linkage"]["questions"][0]
    assert any(span["quote"] in question["question_text"] for span in spans)
    assert link["survey_refs"][0]["response_text"] == "매우 그렇다"
    run = ok(client, run, "answers", question_id=question["question_id"], text="공개된 근거를 참고한 후속 답변")
    final = ok(client, run, "interview-finalize")
    assert final["interview_analysis"] == baseline and len(provider_inputs) == 1
    restarted = create_app(str(app.state.store.engine.url))
    try:
        with TestClient(restarted) as restored:
            restored.cookies.update(client.cookies)
            assert restored.get(f"/api/runs/{run['run_id']}").json() == final
    finally:
        restarted.state.store.engine.dispose()


def test_baseline_edit_stales_linkage_and_rebuild_preserves_question_history(api):
    client, _app, _owner, _run, _clock = api
    run = ok(client, journey(api), "evidence-linkage")
    old_linkage = deepcopy(run["evidence_linkage"])
    old_questions = deepcopy(run["questions"])
    answer = next(r["data"] for r in run["records"] if r.get("source_type") == "typed_answer")
    run = ok(client, run, "answers", question_id=answer["question_id"], text="수정한 자기보고",
             replaces_answer_id=answer["answer_id"], expected_answer_version=answer["answer_version"])
    assert run["interview_report_stale"] is True and run["evidence_linkage_stale"] is True
    for operation in ("evidence-linkage", "interview-finalize"):
        rejected, _ = post(client, run, operation)
        assert rejected.status_code == 409, rejected.text
    run = ok(client, run, "interview-analysis", mode="mock")
    rejected, _ = post(client, run, "interview-finalize")
    assert rejected.status_code == 409
    run = ok(client, run, "evidence-linkage")
    assert run["evidence_linkage"]["linkage_id"] != old_linkage["linkage_id"]
    assert run["questions"][:len(old_questions)] == old_questions
    assert old_linkage in run["evidence_linkage_history"]
    assert run["evidence_linkage_stale"] is False


def test_completion_requires_current_analysis_linkage_and_both_games(api):
    client, _app, _owner, run, _clock = api
    rejected, _ = post(client, run, "evidence-linkage")
    assert rejected.status_code == 409
    run = journey(api, games=False)
    rejected, _ = post(client, run, "interview-finalize")
    assert rejected.status_code == 409
    run = ok(client, run, "evidence-linkage")
    rejected, _ = post(client, run, "interview-finalize")
    assert rejected.status_code == 409
    assert client.get(f"/api/runs/{run['run_id']}").json()["status"] == "in_progress"


@pytest.mark.parametrize("operation", ["evidence-linkage", "interview-finalize"])
def test_new_endpoints_reject_client_content_owner_csrf_and_revision(api, operation):
    client, app, _owner, run, _clock = api
    rejected, _ = post(client, run, operation, report={"fake": True})
    assert rejected.status_code == 422
    no_csrf = client.post(f"/api/runs/{run['run_id']}/{operation}",
                          json={"expected_revision": 0, "idempotency_key": "no-csrf"})
    assert no_csrf.status_code == 403
    with TestClient(app) as other:
        other.post("/api/register", headers=HEADERS,
                   json={"username": "other-owner", "password": "synthetic-password"})
        denied, _ = post(other, run, operation)
        assert denied.status_code == 404
    assert client.get(f"/api/runs/{run['run_id']}").json() == run
    rejected, _ = post(client, run, operation, expected_revision=999)
    assert rejected.status_code == 409


@pytest.mark.parametrize("mutation,error", [
    ("survey_missing", "survey_responses_required"),
    ("baseline_missing", "baseline_answers_required"),
    ("round_missing", "game_completion_required"),
    ("round_unfinished", "game_completion_required"),
    ("fourth_round", "game_completion_required"),
])
def test_finalize_checks_each_required_stage_without_persisting_failure(api, mutation, error):
    client, app, owner, _run, _clock = api
    run = ok(client, journey(api), "evidence-linkage")

    def break_stage(snapshot):
        if mutation == "survey_missing":
            snapshot["records"] = [r for r in snapshot["records"] if r.get("item_id") != DEFINITIONS["surveys"][0]["item_id"]]
        elif mutation == "baseline_missing":
            snapshot["records"] = [r for r in snapshot["records"] if r.get("data", {}).get("question_id") != DEFINITIONS["questions"][0]["question_id"]]
        elif mutation == "round_missing":
            snapshot["rule_games"]["games"]["rsp"]["rounds"].pop()
        elif mutation == "round_unfinished":
            snapshot["rule_games"]["games"]["card"]["rounds"][0]["status"] = "active"
        else:
            rounds = snapshot["rule_games"]["games"]["card"]["rounds"]
            rounds.append(deepcopy(rounds[-1]))

    run = app.state.store.mutate(owner["user_id"], run["run_id"], run["revision"],
                                 "synthetic_stage_fault", mutation, {}, break_stage)
    before = client.get(f"/api/runs/{run['run_id']}").json()
    failed, _ = post(client, run, "interview-finalize")
    assert failed.status_code == 409 and failed.json() == {"error": error}
    assert client.get(f"/api/runs/{run['run_id']}").json() == before
