from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.content import DEFINITIONS
from app.main import create_app
from completion_helpers import finish_required_stages


HEADERS = {"X-Requested-With": "interview-app"}
BASE_NOW = datetime(2026, 10, 11, 1, 0, tzinfo=timezone.utc)
SURVEY_FIXTURE = Path(__file__).parent / "fixtures" / "frontend_client_payloads.json"


def mutate(client, run, endpoint, *, key=None, **values):
    payload = {
        "expected_revision": run["revision"],
        "idempotency_key": key or str(uuid4()),
        **values,
    }
    response = client.post(
        f"/api/runs/{run['run_id']}/{endpoint}", headers=HEADERS, json=payload
    )
    assert response.status_code == 200, response.text
    return response.json(), payload


def finish_rule_games(client, run, clock):
    for game_type in ("rsp", "card"):
        for expected_index in range(1, 4):
            run, _ = mutate(client, run, "rule-games", game_type=game_type, action="start")
            round_state = run["rule_games"]["games"][game_type]["rounds"][-1]
            assert round_state["index"] == expected_index
            clock[0] = datetime.fromisoformat(round_state["reveal_due_at"])
            run, _ = mutate(
                client,
                run,
                "rule-games",
                game_type=game_type,
                action="reveal",
                round_id=round_state["round_id"],
            )
            round_state = run["rule_games"]["games"][game_type]["rounds"][-1]
            clock[0] = datetime.fromisoformat(round_state["deadline_at"])
            run, _ = mutate(
                client,
                run,
                "rule-games",
                game_type=game_type,
                action="finish",
                round_id=round_state["round_id"],
            )
    return run


def typed_records(run):
    return [record for record in run["records"] if record["source_type"] == "typed_answer"]


def test_owned_rule_game_run_restores_exact_versioned_baseline_interview(tmp_path, monkeypatch):
    clock = [BASE_NOW]
    monkeypatch.setattr("app.rule_games._now", lambda: clock[0])
    database_url = f"sqlite:///{tmp_path / 'interview-connection.db'}"
    application = create_app(database_url)
    try:
        with TestClient(application) as client:
            registered = client.post(
                "/api/register",
                headers=HEADERS,
                json={"username": "interview-owner", "password": "synthetic-password"},
            )
            assert registered.status_code == 201
            owner = registered.json()
            run = client.post("/api/runs", headers=HEADERS, json={}).json()

            fixture = json.loads(SURVEY_FIXTURE.read_text(encoding="utf-8"))
            for survey in fixture["surveys"]:
                run, _ = mutate(client, run, "surveys", **survey)
            assert [record["item_id"] for record in run["records"]] == [
                item["item_id"] for item in DEFINITIONS["surveys"]
            ]

            run = finish_rule_games(client, run, clock)
            assert run["game"]["phase"] == "awaiting_start"
            assert {
                game_type: [round_state["status"] for round_state in game["rounds"]]
                for game_type, game in run["rule_games"]["games"].items()
            } == {"rsp": ["completed"] * 3, "card": ["completed"] * 3}

            questions = [
                question for question in run["questions"]
                if question["question_mode"] == "baseline"
            ]
            assert [question["question_id"] for question in questions] == [
                question["question_id"] for question in DEFINITIONS["questions"]
            ]
            assert questions == DEFINITIONS["questions"]
            original_game = deepcopy(run["game"])
            original_rule_games = deepcopy(run["rule_games"])

            original_text = "\r\n  팀원에게 조건을 물었습니다 🙂\r\n두 번째 줄 <합성>  \r\n"
            run, first_payload = mutate(
                client,
                run,
                "answers",
                key="interview-first-answer",
                question_id=questions[0]["question_id"],
                status="asked_answered",
                text=original_text,
            )
            first_snapshot = deepcopy(run)
            first_record = deepcopy(typed_records(run)[0])
            assert first_record["data"]["text"] == original_text
            assert first_record["data"]["question_text_snapshot"] == questions[0]["question_text"]
            assert first_record["data"]["answer_version"] == "1.0.0"
            assert first_record["data"]["previous_answer_version_ref"] is None
            assert first_record["context"]["submitted_elapsed_ms"] is None
            assert run["game"] == original_game and run["rule_games"] == original_rule_games

            retry = client.post(
                f"/api/runs/{run['run_id']}/answers", headers=HEADERS, json=first_payload
            )
            assert retry.status_code == 200 and retry.json() == first_snapshot
            assert len(typed_records(retry.json())) == 1

            run, _ = mutate(
                client,
                run,
                "answers",
                question_id=questions[1]["question_id"],
                status="asked_no_text",
                text="",
            )
            run, _ = mutate(
                client,
                run,
                "answers",
                question_id=questions[2]["question_id"],
                status="skipped",
                text="",
            )
            initial_records = typed_records(run)
            assert [record["data"]["question_id"] for record in initial_records] == [
                question["question_id"] for question in questions
            ]
            assert [record["presentation_order"] for record in initial_records] == [1, 2, 3]
            assert [record["data"]["status"] for record in initial_records] == [
                "asked_answered", "asked_no_text", "skipped"
            ]
            assert initial_records[1]["data"]["text"] == ""
            assert initial_records[2]["data"]["text"] == ""

            corrected_text = "  정정본 첫 줄\r\n새 정보 뒤에도 유지했습니다 🐱\r\n  "
            run, _ = mutate(
                client,
                run,
                "answers",
                question_id=questions[0]["question_id"],
                status="asked_answered",
                text=corrected_text,
                replaces_answer_id=first_record["data"]["answer_id"],
                expected_answer_version=first_record["data"]["answer_version"],
            )
            answer_records = typed_records(run)
            corrected = answer_records[-1]
            assert answer_records[0] == first_record
            assert corrected["data"]["text"] == corrected_text
            assert corrected["source_version"] == corrected["data"]["answer_version"] == "2.0.0"
            assert corrected["data"]["answer_id"] != first_record["data"]["answer_id"]
            assert corrected["data"]["previous_answer_version_ref"] == {
                "answer_id": first_record["data"]["answer_id"],
                "answer_version": "1.0.0",
            }
            assert corrected["presentation_order"] == 4
            assert run["game"] == original_game and run["rule_games"] == original_rule_games

            restored = client.get(f"/api/runs/{run['run_id']}")
            assert restored.status_code == 200 and restored.json() == run
            restarted = create_app(database_url)
            try:
                with TestClient(restarted) as reloaded:
                    reloaded.cookies.update(client.cookies)
                    assert reloaded.get(f"/api/runs/{run['run_id']}").json() == run
            finally:
                restarted.state.store.engine.dispose()

            client.post("/api/logout", headers=HEADERS)
            assert client.post(
                "/api/register",
                headers=HEADERS,
                json={"username": "interview-other", "password": "synthetic-password"},
            ).status_code == 201
            assert client.get(f"/api/runs/{run['run_id']}").status_code == 404
            foreign, _ = mutate_request(
                client,
                run,
                "answers",
                question_id=questions[1]["question_id"],
                status="asked_answered",
                text="타 소유자 합성 답변",
            )
            assert foreign.status_code == 404 and foreign.json() == {"error": "not_found"}

            client.post("/api/logout", headers=HEADERS)
            assert client.post(
                "/api/login",
                headers=HEADERS,
                json={"username": "interview-owner", "password": "synthetic-password"},
            ).status_code == 200
            run = finish_required_stages(client, run)
            run, _ = mutate(client, run, "analyze")
            run, _ = mutate(client, run, "finalize")
            assert run["status"] == "completed"
            latest_q1 = next(
                record for record in reversed(typed_records(run))
                if record["data"]["question_id"] == questions[1]["question_id"]
            )
            finalized, _ = mutate_request(
                client,
                run,
                "answers",
                question_id=questions[1]["question_id"],
                status="asked_answered",
                text="완료 뒤 정정 시도",
                replaces_answer_id=latest_q1["data"]["answer_id"],
                expected_answer_version=latest_q1["data"]["answer_version"],
            )
            assert finalized.status_code == 409
            assert finalized.json() == {"error": "stale_after_finalize"}

            assert client.delete(f"/api/runs/{run['run_id']}", headers=HEADERS).status_code == 204
            assert client.get(f"/api/runs/{run['run_id']}").status_code == 404
            deleted, _ = mutate_request(
                client,
                run,
                "answers",
                question_id=questions[0]["question_id"],
                status="asked_answered",
                text="삭제 뒤 합성 답변",
            )
            assert deleted.status_code == 404 and deleted.json() == {"error": "not_found"}
    finally:
        application.state.store.engine.dispose()


def mutate_request(client, run, endpoint, **values):
    payload = {
        "expected_revision": run["revision"],
        "idempotency_key": str(uuid4()),
        **values,
    }
    return client.post(
        f"/api/runs/{run['run_id']}/{endpoint}", headers=HEADERS, json=payload
    ), payload
