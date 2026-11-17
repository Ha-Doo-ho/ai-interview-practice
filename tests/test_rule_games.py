from __future__ import annotations

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.content import DEFINITIONS
from app.main import create_app
from app import rule_games


HEADERS = {"X-Requested-With": "interview-app"}
BASE_NOW = datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc)


@pytest.fixture
def api(tmp_path, monkeypatch):
    clock = [BASE_NOW]
    monkeypatch.setattr("app.rule_games._now", lambda: clock[0])
    application = create_app(f"sqlite:///{tmp_path / 'rule-games.db'}")
    with TestClient(application, raise_server_exceptions=False) as client:
        owner = client.post(
            "/api/register",
            headers=HEADERS,
            json={"username": "rule-owner", "password": "synthetic-password"},
        )
        assert owner.status_code == 201
        run = client.post("/api/runs", headers=HEADERS, json={}).json()
        yield client, application, owner.json(), run, clock
    application.state.store.engine.dispose()


def post(client, run, *, key=None, **extra):
    payload = {
        "expected_revision": run["revision"],
        "idempotency_key": key or str(uuid4()),
        **extra,
    }
    response = client.post(
        f"/api/runs/{run['run_id']}/rule-games", headers=HEADERS, json=payload
    )
    return response, payload


def visit_surveys(client, run):
    for item in DEFINITIONS["surveys"]:
        kind = item["type"]
        response = (
            {"selected_position": 3}
            if kind == "ordinal_6"
            else {
                "self": {"status": "skipped"},
                "imagined_others": {"status": "skipped"},
            }
            if kind == "paired_perspective"
            else {
                "final_value": None,
                "interaction_occurred": False,
                "explicit_confirmation": False,
                "change_count": 0,
            }
            if kind == "bipolar_slider"
            else {"selected_ids": [], "selection_events": []}
        )
        request = {
            "expected_revision": run["revision"],
            "idempotency_key": str(uuid4()),
            "item_id": item["item_id"],
            "item_version": item["item_version"],
            "status": "skipped",
            "response": response,
        }
        result = client.post(
            f"/api/runs/{run['run_id']}/surveys", headers=HEADERS, json=request
        )
        assert result.status_code == 200, result.text
        run = result.json()
    return run


def assert_error(response, code, status=409):
    assert response.status_code == status, response.text
    assert response.json() == {"error": code}


def winning_hand(opponent):
    return {"rock": "paper", "paper": "scissors", "scissors": "rock"}[opponent]


def losing_hand(opponent):
    return {"rock": "scissors", "paper": "rock", "scissors": "paper"}[opponent]


def choice_for_rsp(rule_id, opponent):
    if rule_id == "rsp-win":
        return winning_hand(opponent)
    if rule_id == "rsp-lose":
        return losing_hand(opponent)
    return opponent


def test_definitions_and_get_are_public_read_only(api):
    client, application, _owner, run, _clock = api
    definitions = client.get("/api/rule-game-definitions")
    assert definitions.status_code == 200
    assert definitions.json() == {
        "version": "1.0.0",
        "rounds_per_game": 3,
        "duration_ms": 20000,
        "reveal_after_ms": 10000,
        "correct_points": 10,
        "incorrect_points": -5,
        "score_floor": 0,
        "games": {
            "rsp": {
                "game_type": "rsp",
                "game_id": "rule-rsp",
                "game_version": "1.0.0",
                "title": "가위바위보 규칙 전환",
                "rules": [
                    {"rule_id": "rsp-win", "label": "상대에게 이기는 손을 선택"},
                    {"rule_id": "rsp-lose", "label": "상대에게 지는 손을 선택"},
                    {"rule_id": "rsp-draw", "label": "상대와 같은 손을 선택"},
                ],
            },
            "card": {
                "game_type": "card",
                "game_id": "rule-card",
                "game_version": "1.0.0",
                "title": "카드 규칙 전환",
                "rules": [
                    {"rule_id": "card-even", "label": "짝수 카드를 선택"},
                    {"rule_id": "card-multiple-3", "label": "3의 배수 카드를 선택"},
                    {"rule_id": "card-at-least-7", "label": "7 이상 카드를 선택"},
                ],
            },
        },
    }
    before = application.state.store.get_run(run["user_id"], run["run_id"])
    result = client.get(f"/api/runs/{run['run_id']}/rule-games")
    assert result.status_code == 200
    assert result.json()["run"] == run
    assert result.json()["server_time"] == BASE_NOW.isoformat()
    assert "rule_games" not in result.json()["run"]
    assert application.state.store.get_run(run["user_id"], run["run_id"]) == before


def test_rsp_full_round_persists_lineage_events_scoring_and_exact_replay(api):
    client, application, owner, run, clock = api
    run = visit_surveys(client, run)
    response, request = post(client, run, key="rsp-start", game_type="rsp", action="start")
    assert response.status_code == 200, response.text
    run = response.json()
    round_state = run["rule_games"]["games"]["rsp"]["rounds"][0]
    assert round_state["index"] == 1 and round_state["phase"] == "initial"
    assert round_state["lineage"] == {
        "user_id": owner["user_id"],
        "run_id": run["run_id"],
        "attempt_id": run["attempt_id"],
    }
    assert round_state["definition_snapshot"]["game_id"] == "rule-rsp"
    assert round_state["scoring_snapshot"] == {
        "correct_points": 10,
        "incorrect_points": -5,
        "score_floor": 0,
    }
    assert round_state["events"][0]["type"] == "round_started"
    opponent = round_state["stimulus"]["opponent_hand"]
    good = choice_for_rsp(round_state["rule"]["rule_id"], opponent)
    response, _ = post(
        client,
        run,
        game_type="rsp",
        action="answer",
        round_id=round_state["round_id"],
        stimulus_id=round_state["stimulus"]["stimulus_id"],
        choice=good,
    )
    assert response.status_code == 200, response.text
    run = response.json()
    answered = run["rule_games"]["games"]["rsp"]["rounds"][0]
    event = answered["events"][-2]
    assert event["type"] == "response_selected"
    assert event["rule"] == answered["rule"]
    assert event["stimulus"] == {
        "stimulus_id": round_state["stimulus"]["stimulus_id"],
        "opponent_hand": opponent,
    }
    assert (event["choice"], event["correct"], event["score_before"], event["score_after"]) == (good, True, 0, 10)
    assert answered["stimulus"]["stimulus_id"] != round_state["stimulus"]["stimulus_id"]
    assert answered["events"][-1]["type"] == "stimulus_issued"
    clock[0] += timedelta(seconds=10)
    response, _ = post(client, run, game_type="rsp", action="reveal", round_id=answered["round_id"])
    assert response.status_code == 200, response.text
    run = response.json()
    changed = run["rule_games"]["games"]["rsp"]["rounds"][0]
    assert changed["phase"] == "changed" and changed["rule"]["rule_id"] == "rsp-lose"
    assert changed["stimulus"]["stimulus_id"] != answered["stimulus"]["stimulus_id"]
    bad = winning_hand(changed["stimulus"]["opponent_hand"])
    response, answer_request = post(
        client,
        run,
        key="rsp-answer-two",
        game_type="rsp",
        action="answer",
        round_id=changed["round_id"],
        stimulus_id=changed["stimulus"]["stimulus_id"],
        choice=bad,
    )
    assert response.status_code == 200, response.text
    run = response.json()
    after_bad = deepcopy(run)
    final_round = run["rule_games"]["games"]["rsp"]["rounds"][0]
    assert (final_round["score"], final_round["correct_count"], final_round["incorrect_count"]) == (5, 1, 1)
    retry = client.post(
        f"/api/runs/{run['run_id']}/rule-games", headers=HEADERS, json=answer_request
    )
    assert retry.status_code == 200 and retry.json() == after_bad
    clock[0] += timedelta(seconds=10)
    response, _ = post(client, run, game_type="rsp", action="finish", round_id=final_round["round_id"])
    assert response.status_code == 200, response.text
    run = response.json()
    completed = run["rule_games"]["games"]["rsp"]["rounds"][0]
    assert completed["status"] == completed["phase"] == "completed"
    assert completed["events"][-1]["type"] == "round_ended"
    assert [event["sequence_no"] for event in completed["events"]] == list(range(1, len(completed["events"]) + 1))
    stored = application.state.store.get_run(owner["user_id"], run["run_id"])
    assert stored["rule_games"] == run["rule_games"]
    public = client.get(f"/api/runs/{run['run_id']}").json()
    assert public["game"] == after_bad["game"] and public["records"] == after_bad["records"]


def test_card_board_duplicate_stale_and_visibility_late(api):
    client, _application, _owner, run, clock = api
    run = visit_surveys(client, run)
    response, _ = post(client, run, game_type="card", action="start")
    run = response.json()
    card_round = run["rule_games"]["games"]["card"]["rounds"][0]
    cards = card_round["stimulus"]["cards"]
    assert len(cards) == 8 and len({c["card_id"] for c in cards}) == 8
    assert all(1 <= c["value"] <= 12 for c in cards)
    choice = cards[0]["card_id"]
    response, _ = post(client, run, game_type="card", action="answer", round_id=card_round["round_id"], stimulus_id=card_round["stimulus"]["stimulus_id"], choice=choice)
    run = response.json()
    duplicate, _ = post(client, run, game_type="card", action="answer", round_id=card_round["round_id"], stimulus_id=card_round["stimulus"]["stimulus_id"], choice=choice)
    assert_error(duplicate, "rule_game_duplicate_choice")
    stale, _ = post(client, run, game_type="card", action="answer", round_id=card_round["round_id"], stimulus_id="stale", choice=cards[1]["card_id"])
    assert_error(stale, "rule_game_stale_stimulus")
    clock[0] += timedelta(seconds=10)
    response, _ = post(client, run, game_type="card", action="reveal", round_id=card_round["round_id"])
    run = response.json()
    changed = run["rule_games"]["games"]["card"]["rounds"][0]
    assert changed["rule"]["rule_id"] == "card-multiple-3"
    assert changed["stimulus"]["stimulus_id"] != card_round["stimulus"]["stimulus_id"]
    assert changed["stimulus"]["selected_card_ids"] == []
    clock[0] += timedelta(seconds=11)
    late, _ = post(client, run, game_type="card", action="answer", round_id=changed["round_id"], stimulus_id=changed["stimulus"]["stimulus_id"], choice=changed["stimulus"]["cards"][0]["card_id"])
    assert_error(late, "rule_game_round_expired")
    visible, _ = post(client, run, game_type="card", action="visibility", round_id=changed["round_id"], hidden=True)
    assert visible.status_code == 200
    run = visible.json()
    visibility = run["rule_games"]["games"]["card"]["rounds"][0]["events"][-1]
    assert visibility["type"] == "visibility_reported" and visibility["hidden"] is True
    assert visibility["interpretation"] == "client_reported"


def test_start_gate_timing_active_round_and_payload_validation(api):
    client, _application, _owner, run, clock = api
    denied, _ = post(client, run, game_type="rsp", action="start")
    assert_error(denied, "survey_responses_required")
    run = visit_surveys(client, run)
    response, _ = post(client, run, game_type="rsp", action="start")
    assert response.status_code == 200
    run = response.json()
    current = run["rule_games"]["games"]["rsp"]["rounds"][0]
    active, _ = post(client, run, game_type="card", action="start")
    assert_error(active, "rule_game_active_round")
    early_reveal, _ = post(client, run, game_type="rsp", action="reveal", round_id=current["round_id"])
    assert_error(early_reveal, "rule_game_reveal_too_early")
    early_finish, _ = post(client, run, game_type="rsp", action="finish", round_id=current["round_id"])
    assert_error(early_finish, "rule_game_finish_too_early")
    injected, _ = post(client, run, game_type="rsp", action="answer", round_id=current["round_id"], stimulus_id=current["stimulus"]["stimulus_id"], choice="rock", score=999)
    assert_error(injected, "validation_error", 422)
    stale_round, _ = post(client, run, game_type="rsp", action="answer", round_id="old-round", stimulus_id=current["stimulus"]["stimulus_id"], choice="rock")
    assert_error(stale_round, "rule_game_stale_round")
    clock[0] += timedelta(seconds=20)
    response, _ = post(client, run, game_type="rsp", action="finish", round_id=current["round_id"])
    assert response.status_code == 200


def test_owner_deleted_finalized_revision_and_original_state_are_protected(api):
    client, application, owner, run, _clock = api
    run = visit_surveys(client, run)
    original_game, original_records = deepcopy(run["game"]), deepcopy(run["records"])
    stale = deepcopy(run)
    started, _ = post(client, run, game_type="rsp", action="start")
    assert started.status_code == 200
    run = started.json()
    assert run["game"] == original_game and run["records"] == original_records
    conflict, _ = post(client, stale, game_type="card", action="start")
    assert_error(conflict, "revision_conflict")
    client.post("/api/logout", headers=HEADERS)
    client.post("/api/register", headers=HEADERS, json={"username": "rule-other", "password": "synthetic-password"})
    foreign_get = client.get(f"/api/runs/{run['run_id']}/rule-games")
    assert_error(foreign_get, "not_found", 404)
    foreign_post, _ = post(client, run, game_type="card", action="start")
    assert_error(foreign_post, "not_found", 404)
    client.post("/api/logout", headers=HEADERS)
    login = client.post("/api/login", headers=HEADERS, json={"username": "rule-owner", "password": "synthetic-password"})
    assert login.status_code == 200
    assert client.delete(f"/api/runs/{run['run_id']}", headers=HEADERS).status_code == 204
    deleted = client.get(f"/api/runs/{run['run_id']}/rule-games")
    assert_error(deleted, "not_found", 404)
    deleted_post, _ = post(client, run, game_type="card", action="start")
    assert_error(deleted_post, "not_found", 404)


def test_both_games_run_three_round_rule_cycles_and_reject_a_fourth(api):
    client, _application, _owner, run, clock = api
    run = visit_surveys(client, run)
    expected = {
        "rsp": [("rsp-win", "rsp-lose"), ("rsp-lose", "rsp-draw"), ("rsp-draw", "rsp-win")],
        "card": [
            ("card-even", "card-multiple-3"),
            ("card-multiple-3", "card-at-least-7"),
            ("card-at-least-7", "card-even"),
        ],
    }
    for game_type in ("rsp", "card"):
        for index, (initial_rule, changed_rule) in enumerate(expected[game_type], 1):
            response, _ = post(client, run, game_type=game_type, action="start")
            assert response.status_code == 200, response.text
            run = response.json()
            round_state = run["rule_games"]["games"][game_type]["rounds"][-1]
            assert (round_state["index"], round_state["rule"]["rule_id"]) == (index, initial_rule)
            clock[0] += timedelta(seconds=10)
            response, _ = post(client, run, game_type=game_type, action="reveal", round_id=round_state["round_id"])
            assert response.status_code == 200, response.text
            run = response.json()
            round_state = run["rule_games"]["games"][game_type]["rounds"][-1]
            assert round_state["rule"]["rule_id"] == changed_rule
            clock[0] += timedelta(seconds=10)
            response, _ = post(client, run, game_type=game_type, action="finish", round_id=round_state["round_id"])
            assert response.status_code == 200, response.text
            run = response.json()
        fourth, _ = post(client, run, game_type=game_type, action="start")
        assert_error(fourth, "rule_game_round_limit")
    assert all(
        round_state["status"] == "completed"
        for game in run["rule_games"]["games"].values()
        for round_state in game["rounds"]
    )


def test_concurrent_starts_allow_one_commit_and_one_revision_conflict(api):
    client, _application, _owner, run, _clock = api
    run = visit_surveys(client, run)
    path = f"/api/runs/{run['run_id']}/rule-games"
    requests = [
        {"expected_revision": run["revision"], "idempotency_key": "race-rsp", "game_type": "rsp", "action": "start"},
        {"expected_revision": run["revision"], "idempotency_key": "race-card", "game_type": "card", "action": "start"},
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda body: client.post(path, headers=HEADERS, json=body), requests))
    assert sorted(response.status_code for response in responses) == [200, 409]
    rejected = next(response for response in responses if response.status_code == 409)
    assert rejected.json() == {"error": "revision_conflict"}
    latest = client.get(path).json()["run"]
    active = [
        round_state
        for game in latest["rule_games"]["games"].values()
        for round_state in game["rounds"]
        if round_state["status"] == "in_progress"
    ]
    assert len(active) == 1 and latest["revision"] == run["revision"] + 1


def test_finalized_run_rejects_rule_game_mutation(api):
    client, application, owner, run, _clock = api
    run = visit_surveys(client, run)

    def complete(snapshot):
        snapshot["status"] = "completed"
        snapshot["completed_at"] = BASE_NOW.isoformat()

    finalized = application.state.store.mutate(
        owner["user_id"], run["run_id"], run["revision"], "test_finalize", "test-finalize", {}, complete
    )
    response, _ = post(client, finalized, game_type="rsp", action="start")
    assert_error(response, "stale_after_finalize")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("game_type", []),
        ("game_type", {}),
        ("game_type", True),
        ("game_type", None),
        ("action", []),
        ("action", {}),
        ("action", False),
        ("action", None),
    ],
)
def test_non_string_game_and_action_values_are_422_without_mutation(api, field, value):
    client, application, owner, run, _clock = api
    before = application.state.store.get_run(owner["user_id"], run["run_id"])
    body = {
        "expected_revision": run["revision"],
        "idempotency_key": str(uuid4()),
        "game_type": "rsp",
        "action": "start",
        field: value,
    }
    response = client.post(f"/api/runs/{run['run_id']}/rule-games", headers=HEADERS, json=body)
    assert_error(response, "validation_error", 422)
    assert application.state.store.get_run(owner["user_id"], run["run_id"]) == before


@pytest.mark.parametrize(
    "changes",
    [
        {"round_id": [], "stimulus_id": "stimulus", "choice": "rock"},
        {"round_id": "round", "stimulus_id": {}, "choice": "rock"},
        {"round_id": "round", "stimulus_id": "stimulus", "choice": []},
        {"round_id": "r" * 129, "stimulus_id": "stimulus", "choice": "rock"},
        {"round_id": "round", "stimulus_id": "s" * 129, "choice": "rock"},
        {"round_id": "round", "stimulus_id": "stimulus", "choice": "c" * 129},
        {"game_type": "card", "round_id": "round", "stimulus_id": "stimulus", "choice": "c" * 129},
        {"round_id": "round", "stimulus_id": "stimulus", "choice": "rock", "correct": True},
    ],
)
def test_answer_identifiers_and_unknown_fields_are_strict_422(api, changes):
    client, application, owner, run, _clock = api
    before = application.state.store.get_run(owner["user_id"], run["run_id"])
    body = {
        "expected_revision": run["revision"],
        "idempotency_key": str(uuid4()),
        "game_type": "rsp",
        "action": "answer",
        **changes,
    }
    response = client.post(f"/api/runs/{run['run_id']}/rule-games", headers=HEADERS, json=body)
    assert_error(response, "validation_error", 422)
    assert application.state.store.get_run(owner["user_id"], run["run_id"]) == before


@pytest.mark.parametrize("game_type", ["rsp", "card"])
def test_initial_answer_at_reveal_boundary_is_rejected_without_mutation(api, game_type):
    client, application, owner, run, clock = api
    run = visit_surveys(client, run)
    started, _ = post(client, run, game_type=game_type, action="start")
    assert started.status_code == 200, started.text
    run = started.json()
    round_state = run["rule_games"]["games"][game_type]["rounds"][0]
    choice = (
        choice_for_rsp(round_state["rule"]["rule_id"], round_state["stimulus"]["opponent_hand"])
        if game_type == "rsp"
        else round_state["stimulus"]["cards"][0]["card_id"]
    )
    before = application.state.store.get_run(owner["user_id"], run["run_id"])
    clock[0] = datetime.fromisoformat(round_state["reveal_due_at"])
    response, _ = post(
        client,
        run,
        game_type=game_type,
        action="answer",
        round_id=round_state["round_id"],
        stimulus_id=round_state["stimulus"]["stimulus_id"],
        choice=choice,
    )
    assert_error(response, "rule_game_reveal_required")
    assert application.state.store.get_run(owner["user_id"], run["run_id"]) == before
    reveal, _ = post(client, run, game_type=game_type, action="reveal", round_id=round_state["round_id"])
    assert reveal.status_code == 200, reveal.text


def test_finish_without_reveal_records_missing_observation_without_inventing_event(api):
    client, _application, _owner, run, clock = api
    run = visit_surveys(client, run)
    started, _ = post(client, run, game_type="rsp", action="start")
    assert started.status_code == 200, started.text
    run = started.json()
    round_state = run["rule_games"]["games"]["rsp"]["rounds"][0]
    initial_rule = deepcopy(round_state["rule"])
    clock[0] = datetime.fromisoformat(round_state["deadline_at"])
    finished, _ = post(client, run, game_type="rsp", action="finish", round_id=round_state["round_id"])
    assert finished.status_code == 200, finished.text
    completed = finished.json()["rule_games"]["games"]["rsp"]["rounds"][0]
    assert completed["status"] == "completed"
    assert completed["revealed_at"] is None and completed["rule"] == initial_rule
    assert completed["quality_flags"] == ["rule_reveal_not_recorded"]
    assert "rule_revealed" not in [event["type"] for event in completed["events"]]


def test_round_scoring_snapshot_survives_global_definition_changes(api, monkeypatch):
    client, _application, _owner, run, _clock = api
    run = visit_surveys(client, run)
    started, _ = post(client, run, game_type="rsp", action="start")
    assert started.status_code == 200, started.text
    run = started.json()
    round_state = run["rule_games"]["games"]["rsp"]["rounds"][0]
    monkeypatch.setitem(rule_games.RULE_GAME_DEFINITIONS, "correct_points", 99)
    monkeypatch.setitem(rule_games.RULE_GAME_DEFINITIONS, "incorrect_points", -99)
    monkeypatch.setitem(rule_games.RULE_GAME_DEFINITIONS, "score_floor", 50)

    correct_choice = choice_for_rsp(round_state["rule"]["rule_id"], round_state["stimulus"]["opponent_hand"])
    scored, _ = post(
        client,
        run,
        game_type="rsp",
        action="answer",
        round_id=round_state["round_id"],
        stimulus_id=round_state["stimulus"]["stimulus_id"],
        choice=correct_choice,
    )
    assert scored.status_code == 200, scored.text
    run = scored.json()
    assert run["rule_games"]["games"]["rsp"]["rounds"][0]["score"] == 10

    for expected_score in (5, 0, 0):
        current = run["rule_games"]["games"]["rsp"]["rounds"][0]
        actual_correct = choice_for_rsp(current["rule"]["rule_id"], current["stimulus"]["opponent_hand"])
        wrong_choice = next(hand for hand in ("rock", "paper", "scissors") if hand != actual_correct)
        scored, _ = post(
            client,
            run,
            game_type="rsp",
            action="answer",
            round_id=current["round_id"],
            stimulus_id=current["stimulus"]["stimulus_id"],
            choice=wrong_choice,
        )
        assert scored.status_code == 200, scored.text
        run = scored.json()
        assert run["rule_games"]["games"]["rsp"]["rounds"][0]["score"] == expected_score
    final_round = run["rule_games"]["games"]["rsp"]["rounds"][0]
    assert (final_round["correct_count"], final_round["incorrect_count"]) == (1, 3)

