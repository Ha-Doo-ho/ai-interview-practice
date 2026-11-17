"""Same-run journey through real API/SQLite; synthetic inputs and offline AI only."""
from copy import deepcopy
import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from test_interview_connection import BASE_NOW, HEADERS, SURVEY_FIXTURE, finish_rule_games, mutate
from test_live_interview_analysis import _configure_live, _model_result


@pytest.mark.parametrize("mode", ["mock", "live"])
def test_saved_surveys_games_answers_and_report_share_one_owned_run(tmp_path, monkeypatch, mode):
    import app.interview_analysis as analysis

    clock = [BASE_NOW]
    monkeypatch.setattr("app.rule_games._now", lambda: clock[0])
    _configure_live(monkeypatch)
    provider_inputs = []

    def offline_transport(_endpoint, payload, **_kwargs):
        data = json.loads(payload["input"][0]["content"][0]["text"])
        provider_inputs.append(data)
        return {"status": "completed", "output_text": json.dumps(_model_result(data["answer"]["text"], data["question"]), ensure_ascii=False)}

    monkeypatch.setattr(analysis, "_PROVIDER_TRANSPORT", offline_transport)
    database_url = f"sqlite:///{tmp_path / 'report-journey.db'}"
    app = create_app(database_url)
    try:
        with TestClient(app) as client:
            assert client.post("/api/register", headers=HEADERS, json={"username": "report-journey", "password": "synthetic-password"}).status_code == 201
            run = client.post("/api/runs", headers=HEADERS, json={}).json()
            for survey in json.loads(SURVEY_FIXTURE.read_text(encoding="utf-8"))["surveys"]:
                run, _ = mutate(client, run, "surveys", **survey)
            run = finish_rule_games(client, run, clock)
            questions = run["questions"]
            for question, status, text in zip(questions, ["asked_answered", "asked_no_text", "skipped"], ["🙂 팀원에게 일정을 물었습니다. 함께 계획을 정했습니다.", "", ""]):
                run, _ = mutate(client, run, "answers", question_id=question["question_id"], status=status, text=text)
            originals = deepcopy({key: run[key] for key in ("records", "game", "rule_games", "questions")})
            run_id, revision = run["run_id"], run["revision"]
            run, payload = mutate(client, run, "interview-analysis", key="same-report-request", mode=mode)
            assert run["run_id"] == run_id and run["revision"] == revision + 1
            assert all(run[key] == value for key, value in originals.items())
            assert run["status"] == "in_progress" and run["interview_report_stale"] is False
            report = run["interview_report"]
            assert report["runtime_mode"] == "mock"
            assert report["provider_execution"] == ("not_called" if mode == "mock" else "test_double")
            assert len(report["surveys"]) == 6 and len(report["cards"]) == 3
            assert len(report["rule_games"]) == 2
            for game in report["rule_games"]:
                assert game["mapping_status"] == "unmapped" and game["comparison_status"] == "not_comparable"
                assert len(game["rounds"]) == 3
                assert all(item["status"] == "completed" for item in game["rounds"])
            assert all(card["comparison"]["status"] == "insufficient_evidence" for card in report["cards"])
            assert len(provider_inputs) == (0 if mode == "mock" else 1)
            if mode == "live":
                assert set(provider_inputs[0]) == {"question", "answer", "behavior", "rubric"}
                span = report["cards"][0]["criteria"]["action"]["evidence_spans"][0]
                answer = next(record["data"] for record in run["records"] if record.get("data", {}).get("answer_id") == span["source_id"])
                assert answer["answer_version"] == span["source_version"]
                assert answer["text"][span["start"]:span["end"]] == span["quote"]
            replay = client.post(f"/api/runs/{run_id}/interview-analysis", headers=HEADERS, json=payload)
            assert replay.status_code == 200 and replay.json() == run
            assert len(provider_inputs) == (0 if mode == "mock" else 1)
            restarted = create_app(database_url)
            try:
                with TestClient(restarted) as restored:
                    restored.cookies.update(client.cookies)
                    assert restored.get(f"/api/runs/{run_id}").json() == run
                    answer = next(record["data"] for record in run["records"] if record["source_type"] == "typed_answer")
                    changed, _ = mutate(restored, run, "answers", question_id=answer["question_id"], status="asked_answered", text="🙂 팀원에게 새 일정을 물었습니다.", replaces_answer_id=answer["answer_id"], expected_answer_version=answer["answer_version"])
                    assert changed["interview_report_stale"] is True
                    assert changed["interview_report"] == report
            finally:
                restarted.state.store.engine.dispose()
    finally:
        app.state.store.engine.dispose()
