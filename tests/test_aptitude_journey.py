"""Real HTTP journeys with isolated SQLite, synthetic solutions and a fixed clock.

Only test helpers read the private snapshot to make deterministic player choices;
every game mutation, refresh, replay and deletion goes through authenticated HTTP.
"""
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.store import IdempotencyRow, RunRow
from test_aptitude_api import request
from test_completion_pipeline import api, HEADERS, journey, ok


@pytest.fixture
def game_api(api, monkeypatch):
    now = [1_000_000]
    monkeypatch.setattr("app.aptitude_games._now", lambda: now[0])
    return (*api, now)


def _attempt(run):
    return run["aptitude_games"]["attempts"][-1]


def _ok(client, run, **values):
    response, body = request(client, run, **values)
    assert response.status_code == 200, response.text
    return response.json(), body


def _act(client, run, action, **values):
    attempt = _attempt(run)
    question = attempt["current_question"] or attempt["questions"][-1]
    return _ok(client, run, action=action, attempt_id=attempt["id"],
               question_id=question["id"], **values)


def _private_question(app, owner, run):
    # Read-only test fixture access, never an endpoint or browser capability.
    private = app.state.store.get_run(owner["user_id"], run["run_id"])
    return private["aptitude_games"]["attempts"][-1]["current_question"]


def _assert_private_fields_absent(attempt):
    if attempt["status"] != "active":
        return
    forbidden = {"solution", "seed", "red_probability", "favorable_color", "favorable_choice",
                 "favorable_choice_rate", "favorable_choice_change"}

    def check(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    check(attempt)
    question = attempt["current_question"]
    if question is not None:
        assert "outcome" not in question and "actual_outcome" not in question
        assert "min_operations" not in question and "minimum_fences" not in question
        if attempt["mode"] != "practice":
            assert "transformed_points" not in question


def _refresh(client, run):
    restored = client.get(f"/api/runs/{run['run_id']}/aptitude-games")
    assert restored.status_code == 200, restored.text
    restored = restored.json()["run"]
    assert restored["revision"] == run["revision"]
    assert restored["aptitude_games"] == run["aptitude_games"]
    normal = client.get(f"/api/runs/{run['run_id']}")
    assert normal.status_code == 200
    assert normal.json()["aptitude_games"] == restored["aptitude_games"]
    _assert_private_fields_absent(_attempt(restored))
    return restored


def _submit(client, app, owner, run, now, *, correct=True):
    question = _private_question(app, owner, run)
    kind = _attempt(run)["type"]
    if correct and kind == "rotation":
        for command in question["solution"]:
            now[0] += 25
            run, _ = _act(client, run, "rotate", command=command)
    elif correct and kind == "path":
        for position, orientation in question["solution"].items():
            row, col = map(int, position.split(","))
            for _ in range(1 if orientation == "/" else 2):
                now[0] += 25
                run, _ = _act(client, run, "cell", row=row, col=col)
    run = _refresh(client, run)
    now[0] += 100
    choice = {}
    if kind == "potion":
        choice["choice"] = question["outcome"] if correct else {"red": "blue", "blue": "red"}[question["outcome"]]
    run, body = _act(client, run, "submit", **choice)
    _assert_private_fields_absent(_attempt(run))
    return run, body


def _assert_replay_and_fresh_rejection(client, run, body):
    path = f"/api/runs/{run['run_id']}/aptitude-games"
    replay = client.post(path, headers=HEADERS, json=body)
    assert replay.status_code == 200, replay.text
    assert replay.json() == run
    rejected = client.post(path, headers=HEADERS, json={
        **body, "expected_revision": run["revision"], "idempotency_key": str(uuid4()),
    })
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["error"] == "aptitude_invalid_state"
    assert client.get(f"/api/runs/{run['run_id']}").json()["revision"] == run["revision"]


@pytest.mark.parametrize("kind,mode,count", [
    ("rotation", "main", 10), ("path", "main", 10),
    ("potion", "quick", 20), ("potion", "main", 48),
])
def test_complete_http_games_practice_refresh_replay_results_and_delete(game_api, kind, mode, count):
    client, app, owner, run, _legacy_clock, now = game_api
    baseline = {key: deepcopy(run.get(key)) for key in ("rule_games", "appointment_games", "records")}
    run, _ = _ok(client, run, action="start", game_type=kind, mode="practice", difficulty="hard")
    assert _attempt(run)["question_limit"] == 1
    _assert_private_fields_absent(_attempt(run))
    run, practice_body = _submit(client, app, owner, run, now)
    practice = deepcopy(_attempt(run))
    assert practice["status"] == "complete" and practice["score"] == 0
    assert practice["summary"]["correct_count"] == 1
    assert practice["summary"]["excluded_from_summary"] is True
    assert practice["summary"]["normalized_score"] is None
    assert practice["max_score"] == 0
    _assert_replay_and_fresh_rejection(client, run, practice_body)

    run, _ = _ok(client, run, action="start", game_type=kind, mode=mode, difficulty="hard")
    assert _attempt(run)["question_limit"] == count
    definitions = client.get('/api/aptitude-games/definitions').json()['games']
    definition = next(item for item in definitions if item['type'] == kind)
    count_field = 'quick_question_count' if mode == 'quick' else 'question_count'
    assert definition[count_field] == count
    score, correct_count = 0, 0
    for number in range(1, count + 1):
        active = _attempt(run)
        assert active["current_question"]["number"] == number
        _assert_private_fields_absent(active)
        expected_correct = number % 7 != 1
        before = score
        score = max(0, score + (10 if expected_correct else -5))
        correct_count += expected_correct
        run, body = _submit(client, app, owner, run, now, correct=expected_correct)
        record = _attempt(run)["questions"][-1]
        assert record["outcome"] == ("correct" if expected_correct else "wrong")
        assert record["score_before"] == before and record["score_after"] == score
        assert record["score_delta"] == score - before
        assert record["response_time_ms"] >= 100
        assert len(_attempt(run)["questions"]) == number
        _assert_replay_and_fresh_rejection(client, run, body)
        run = _refresh(client, run)
        if number < count:
            run, _ = _act(client, run, "next")

    attempt = _attempt(run)
    summary = attempt["summary"]
    assert attempt["status"] == "complete" and attempt["current_question"] is None
    assert summary["total_questions"] == summary["answered_count"] == count
    assert summary["correct_count"] == correct_count
    assert summary["wrong_count"] == count - correct_count
    assert summary["timeout_count"] == summary["unasked_count"] == 0
    assert summary["score"] == attempt["score"] == score
    assert summary["max_score"] == count * 10
    assert summary["normalized_score"] == pytest.approx(round(score / (count * 10) * 100, 3))
    assert sum(q["score_delta"] for q in attempt["questions"]) == score
    assert run["aptitude_games"]["attempts"][0] == practice
    if kind == "potion":
        metrics = summary["metrics"]
        assert metrics["prediction_hit_rate"] == pytest.approx(round(correct_count / count, 6))
        assert len(metrics["by_combination"]) == 6
        assert sum(v["choice_count"] for v in metrics["by_combination"].values()) == count
    for key, value in baseline.items():
        assert run.get(key) == value

    assert client.delete(f"/api/runs/{run['run_id']}", headers=HEADERS).status_code == 204
    assert client.get(f"/api/runs/{run['run_id']}/aptitude-games").status_code == 404
    assert client.get(f"/api/runs/{run['run_id']}").status_code == 404
    assert client.get("/api/runs").json() == {"runs": []}
    assert client.post(f"/api/runs/{run['run_id']}/aptitude-games", headers=HEADERS, json=body).status_code == 404
    with Session(app.state.store.engine) as session:
        tombstone = session.scalar(select(RunRow).where(RunRow.run_id == run["run_id"]))
        assert tombstone.status == "deleted" and tombstone.snapshot is None
        assert session.scalar(select(IdempotencyRow).where(IdempotencyRow.run_id == run["run_id"])) is None


@pytest.mark.parametrize("kind", ["rotation", "path", "potion"])
def test_http_interruption_restart_retains_attempt_and_server_deadline_settles_once(game_api, kind):
    client, app, owner, run, _legacy_clock, now = game_api
    mode = "quick" if kind == "potion" else "main"
    run, _ = _ok(client, run, action="start", game_type=kind, mode=mode, difficulty="hard")
    if kind == "rotation":
        run, _ = _act(client, run, "rotate", command="right")
    elif kind == "path":
        run, _ = _act(client, run, "cell", row=0, col=0)
    run = _refresh(client, run)
    run, stopped_body = _act(client, run, "stop")
    stopped = deepcopy(_attempt(run))
    assert stopped["status"] == "interrupted" and stopped["score"] == 0
    assert stopped["summary"]["interrupted_count"] == 1
    assert stopped["summary"]["unasked_count"] == stopped["question_limit"] - 1
    if kind != "potion":
        assert stopped["questions"][0]["metrics"]["operations"] == 1
    run, _ = _ok(client, run, action="start", game_type=kind, mode=mode, difficulty="hard")
    assert _attempt(run)["id"] != stopped["id"]
    assert run["aptitude_games"]["attempts"][0] == stopped
    stale = client.post(f"/api/runs/{run['run_id']}/aptitude-games", headers=HEADERS, json={
        **stopped_body, "expected_revision": run["revision"], "idempotency_key": str(uuid4()),
    })
    assert stale.status_code == 409
    attempt = _attempt(run)
    remaining = attempt["current_question"]["remaining_ms"]
    now[0] += remaining
    refreshed = client.get(f"/api/runs/{run['run_id']}/aptitude-games").json()["run"]
    assert refreshed["revision"] == run["revision"]
    assert _attempt(refreshed)["current_question"]["remaining_ms"] == 0
    assert _attempt(refreshed)["current_question"]["id"] == attempt["current_question"]["id"]
    run, timeout_body = _act(client, refreshed, "timeout")
    result = _attempt(run)
    assert result["summary"]["timeout_count"] == 1 and result["score"] == 0
    assert result["questions"][0]["outcome"] == "timeout"
    assert result["questions"][0]["scoring_delta"] == -5
    assert result["questions"][0]["score_delta"] == 0
    _assert_replay_and_fresh_rejection(client, run, timeout_body)
    if kind == "potion":
        assert result["status"] == "active" and result["current_question"] is None
        assert "actual_outcome" not in result["questions"][0]["metrics"]
        run, _ = _act(client, run, "next")
        assert _attempt(run)["current_question"]["number"] == 2
        run, _ = _act(client, run, "stop")
    else:
        assert result["status"] == "complete"
        assert result["summary"]["unasked_count"] == result["question_limit"] - 1
    assert run["aptitude_games"]["attempts"][0] == stopped
    _refresh(client, run)


def test_http_completed_interview_keeps_optional_results_and_rejects_new_game_mutation(game_api):
    client, app, owner, run, legacy_clock, now = game_api
    run, _ = _ok(client, run, action="start", game_type="rotation", mode="practice", difficulty="easy")
    run, _ = _submit(client, app, owner, run, now)
    result = deepcopy(run["aptitude_games"])
    run = journey((client, app, owner, run, legacy_clock))
    run = ok(client, run, "evidence-linkage")
    run = ok(client, run, "interview-finalize")
    assert run["status"] == "completed"
    assert run["aptitude_games"] == result
    assert run["report"]["aptitude_games"] == result
    denied, _ = request(client, run, action="start", game_type="path", mode="main", difficulty="hard")
    assert denied.status_code == 409
    assert denied.json() == {"error": "stale_after_finalize"}
    assert client.get(f"/api/runs/{run['run_id']}").json() == run
