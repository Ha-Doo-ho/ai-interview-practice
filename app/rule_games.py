from __future__ import annotations

import copy
import random
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .store import Conflict, Validation


RULE_GAME_DEFINITIONS = {
    "version": "1.0.0",
    "rounds_per_game": 3,
    "duration_ms": 20_000,
    "reveal_after_ms": 10_000,
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

_COMMON_FIELDS = {"expected_revision", "idempotency_key", "game_type", "action"}
_ACTION_FIELDS = {
    "start": set(),
    "answer": {"round_id", "stimulus_id", "choice"},
    "reveal": {"round_id"},
    "finish": {"round_id"},
    "visibility": {"round_id", "hidden"},
}
_HANDS = ("rock", "paper", "scissors")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def server_time() -> str:
    return _now().isoformat()


def initial_rule_games() -> dict:
    return {
        "version": RULE_GAME_DEFINITIONS["version"],
        "mapping_status": "unmapped",
        "games": {
            game_type: {
                "game_type": game_type,
                "game_id": definition["game_id"],
                "game_version": definition["game_version"],
                "rounds": [],
            }
            for game_type, definition in RULE_GAME_DEFINITIONS["games"].items()
        },
    }


def validate_action_body(body: dict) -> None:
    game_type, action = body.get("game_type"), body.get("action")
    if not isinstance(game_type, str) or not isinstance(action, str):
        raise Validation("validation_error")
    if game_type not in RULE_GAME_DEFINITIONS["games"] or action not in _ACTION_FIELDS:
        raise Validation("validation_error")
    expected = _COMMON_FIELDS | _ACTION_FIELDS[action]
    if set(body) != expected:
        raise Validation("validation_error")
    for field in _ACTION_FIELDS[action] - {"hidden"}:
        if not isinstance(body.get(field), str) or not body[field] or len(body[field]) > 128:
            raise Validation("validation_error")
    if action == "visibility" and not isinstance(body.get("hidden"), bool):
        raise Validation("validation_error")
    if action == "answer":
        choice = body["choice"]
        if game_type == "rsp" and choice not in _HANDS:
            raise Validation("validation_error")


def surveys_visited(snapshot: dict, survey_ids: set[str]) -> bool:
    visited = {
        record.get("item_id")
        for record in snapshot.get("records", [])
        if record.get("source_type") == "survey"
        and record.get("status") in {"submitted", "timed_out", "skipped"}
    }
    return survey_ids.issubset(visited)


def _elapsed_ms(round_state: dict, now: datetime) -> int:
    return max(0, int((now - datetime.fromisoformat(round_state["started_at"])).total_seconds() * 1000))


def _event(round_state: dict, event_type: str, now: datetime, **facts) -> dict:
    return {
        "event_id": str(uuid4()),
        "sequence_no": len(round_state["events"]) + 1,
        "type": event_type,
        "server_at": now.isoformat(),
        "elapsed_ms": _elapsed_ms(round_state, now),
        **facts,
    }


def _rule(game_type: str, index: int, *, changed: bool) -> dict:
    rules = RULE_GAME_DEFINITIONS["games"][game_type]["rules"]
    return copy.deepcopy(rules[(index - 1 + int(changed)) % len(rules)])


def _stimulus(game_type: str) -> dict:
    stimulus_id = str(uuid4())
    if game_type == "rsp":
        return {"stimulus_id": stimulus_id, "opponent_hand": random.choice(_HANDS)}
    values = random.sample(range(1, 13), 8)
    return {
        "stimulus_id": stimulus_id,
        "cards": [
            {"card_id": str(uuid4()), "value": value}
            for value in values
        ],
        "selected_card_ids": [],
    }


def _active_round(rule_games: dict) -> tuple[str, dict] | None:
    for game_type, game in rule_games["games"].items():
        for round_state in game["rounds"]:
            if round_state["status"] == "in_progress":
                return game_type, round_state
    return None


def _correct(game_type: str, rule_id: str, stimulus: dict, choice: str) -> bool:
    if game_type == "rsp":
        opponent = stimulus["opponent_hand"]
        wins = {"rock": "paper", "paper": "scissors", "scissors": "rock"}
        loses = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
        expected = wins[opponent] if rule_id == "rsp-win" else loses[opponent] if rule_id == "rsp-lose" else opponent
        return choice == expected
    card = next((item for item in stimulus["cards"] if item["card_id"] == choice), None)
    if card is None:
        raise Validation("validation_error")
    value = card["value"]
    return value % 2 == 0 if rule_id == "card-even" else value % 3 == 0 if rule_id == "card-multiple-3" else value >= 7


def _start(snapshot: dict, game_type: str, now: datetime) -> None:
    rule_games = snapshot["rule_games"]
    if _active_round(rule_games) is not None:
        raise Conflict("rule_game_active_round")
    game = rule_games["games"][game_type]
    if len(game["rounds"]) >= RULE_GAME_DEFINITIONS["rounds_per_game"]:
        raise Conflict("rule_game_round_limit")
    index = len(game["rounds"]) + 1
    deadline = now + timedelta(milliseconds=RULE_GAME_DEFINITIONS["duration_ms"])
    reveal_due = now + timedelta(milliseconds=RULE_GAME_DEFINITIONS["reveal_after_ms"])
    definition = RULE_GAME_DEFINITIONS["games"][game_type]
    round_state = {
        "round_id": str(uuid4()),
        "index": index,
        "practice_or_main": "main",
        "status": "in_progress",
        "phase": "initial",
        "started_at": now.isoformat(),
        "deadline_at": deadline.isoformat(),
        "reveal_due_at": reveal_due.isoformat(),
        "revealed_at": None,
        "completed_at": None,
        "duration_ms": RULE_GAME_DEFINITIONS["duration_ms"],
        "score": 0,
        "correct_count": 0,
        "incorrect_count": 0,
        "rule": _rule(game_type, index, changed=False),
        "stimulus": _stimulus(game_type),
        "events": [],
        "quality_flags": [],
        "lineage": {
            "user_id": snapshot["user_id"],
            "run_id": snapshot["run_id"],
            "attempt_id": snapshot["attempt_id"],
        },
        "definition_snapshot": {
            "definitions_version": RULE_GAME_DEFINITIONS["version"],
            "game_type": game_type,
            "game_id": definition["game_id"],
            "game_version": definition["game_version"],
            "rounds_per_game": RULE_GAME_DEFINITIONS["rounds_per_game"],
            "duration_ms": RULE_GAME_DEFINITIONS["duration_ms"],
            "reveal_after_ms": RULE_GAME_DEFINITIONS["reveal_after_ms"],
        },
        "rule_snapshot": {
            "initial": _rule(game_type, index, changed=False),
            "changed": _rule(game_type, index, changed=True),
        },
        "scoring_snapshot": {
            "correct_points": RULE_GAME_DEFINITIONS["correct_points"],
            "incorrect_points": RULE_GAME_DEFINITIONS["incorrect_points"],
            "score_floor": RULE_GAME_DEFINITIONS["score_floor"],
        },
    }
    round_state["events"].append(_event(round_state, "round_started", now))
    round_state["events"].append(
        _event(round_state, "stimulus_issued", now, rule=copy.deepcopy(round_state["rule"]), stimulus=copy.deepcopy(round_state["stimulus"]))
    )
    game["rounds"].append(round_state)


def _requested_round(rule_games: dict, game_type: str, round_id: str) -> dict:
    active = _active_round(rule_games)
    if active is None or active[0] != game_type or active[1]["round_id"] != round_id:
        raise Conflict("rule_game_stale_round")
    return active[1]


def _answer(round_state: dict, game_type: str, body: dict, now: datetime) -> None:
    if now >= datetime.fromisoformat(round_state["deadline_at"]):
        raise Conflict("rule_game_round_expired")
    if round_state["phase"] == "initial" and now >= datetime.fromisoformat(round_state["reveal_due_at"]):
        raise Conflict("rule_game_reveal_required")
    stimulus = round_state["stimulus"]
    if body["stimulus_id"] != stimulus["stimulus_id"]:
        raise Conflict("rule_game_stale_stimulus")
    if game_type == "rsp":
        event_stimulus = copy.deepcopy(stimulus)
    else:
        if body["choice"] in stimulus["selected_card_ids"]:
            raise Conflict("rule_game_duplicate_choice")
        if not any(card["card_id"] == body["choice"] for card in stimulus["cards"]):
            raise Validation("validation_error")
        event_stimulus = copy.deepcopy(stimulus)
        stimulus["selected_card_ids"].append(body["choice"])
    correct = _correct(game_type, round_state["rule"]["rule_id"], event_stimulus, body["choice"])
    before = round_state["score"]
    scoring = round_state["scoring_snapshot"]
    delta = scoring["correct_points"] if correct else scoring["incorrect_points"]
    after = max(scoring["score_floor"], before + delta)
    round_state["score"] = after
    round_state["correct_count" if correct else "incorrect_count"] += 1
    round_state["events"].append(
        _event(
            round_state,
            "response_selected",
            now,
            rule=copy.deepcopy(round_state["rule"]),
            stimulus=event_stimulus,
            choice=body["choice"],
            correct=correct,
            score_before=before,
            score_after=after,
        )
    )
    if game_type == "rsp":
        round_state["stimulus"] = _stimulus(game_type)
        round_state["events"].append(
            _event(round_state, "stimulus_issued", now, rule=copy.deepcopy(round_state["rule"]), stimulus=copy.deepcopy(round_state["stimulus"]))
        )


def _reveal(round_state: dict, game_type: str, now: datetime) -> None:
    if now >= datetime.fromisoformat(round_state["deadline_at"]):
        raise Conflict("rule_game_round_expired")
    if round_state["phase"] != "initial":
        raise Conflict("rule_game_invalid_state")
    if now < datetime.fromisoformat(round_state["reveal_due_at"]):
        raise Conflict("rule_game_reveal_too_early")
    round_state["phase"] = "changed"
    round_state["revealed_at"] = now.isoformat()
    round_state["rule"] = copy.deepcopy(round_state["rule_snapshot"]["changed"])
    round_state["stimulus"] = _stimulus(game_type)
    round_state["events"].append(
        _event(
            round_state,
            "rule_revealed",
            now,
            rule=copy.deepcopy(round_state["rule"]),
            stimulus=copy.deepcopy(round_state["stimulus"]),
        )
    )
    round_state["events"].append(
        _event(round_state, "stimulus_issued", now, rule=copy.deepcopy(round_state["rule"]), stimulus=copy.deepcopy(round_state["stimulus"]))
    )


def _finish(round_state: dict, now: datetime) -> None:
    if now < datetime.fromisoformat(round_state["deadline_at"]):
        raise Conflict("rule_game_finish_too_early")
    round_state["status"] = "completed"
    round_state["phase"] = "completed"
    round_state["completed_at"] = now.isoformat()
    if round_state["revealed_at"] is None:
        round_state["quality_flags"].append("rule_reveal_not_recorded")
    round_state["events"].append(
        _event(
            round_state,
            "round_ended",
            now,
            score=round_state["score"],
            correct_count=round_state["correct_count"],
            incorrect_count=round_state["incorrect_count"],
        )
    )


def apply_rule_game_action(snapshot: dict, body: dict) -> None:
    if "rule_games" not in snapshot:
        snapshot["rule_games"] = initial_rule_games()
    now = _now()
    game_type, action = body["game_type"], body["action"]
    if action == "start":
        _start(snapshot, game_type, now)
        return
    round_state = _requested_round(snapshot["rule_games"], game_type, body["round_id"])
    if action == "answer":
        _answer(round_state, game_type, body, now)
    elif action == "reveal":
        _reveal(round_state, game_type, now)
    elif action == "finish":
        _finish(round_state, now)
    else:
        round_state["events"].append(
            _event(
                round_state,
                "visibility_reported",
                now,
                hidden=body["hidden"],
                interpretation="client_reported",
            )
        )
