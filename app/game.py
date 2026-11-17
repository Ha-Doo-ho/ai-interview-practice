from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4


class GameValidation(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp() -> str:
    return _now().isoformat()


def initial_game_state(definition: dict) -> dict:
    presentation_id = str(uuid4())
    rounds = []
    for source in definition["rounds"]:
        snapshot = deepcopy(source)
        snapshot["reward_table"] = deepcopy(source["reward_table_initial"])
        snapshot.update(
            {
                "status": "not_started",
                "started_at": None,
                "deadline_at": None,
                "completed_at": None,
                "initial_decision": None,
                "final_decision": None,
                "revision_outcome": None,
                "game_result": None,
                "missing_reason": None,
            }
        )
        rounds.append(snapshot)
    return {
        "game_id": definition["game_id"],
        "game_version": definition["game_version"],
        "rules_version": definition["rules_version"],
        "algorithm_version": definition["algorithm_version"],
        "seed": definition["seed"],
        "presentation": {
            "presentation_id": presentation_id,
            "instructions_version": definition["rules_version"],
            "presentation_order": 1,
            "definition_ref": f"{definition['game_id']}:{definition['game_version']}",
            "immutable": True,
        },
        "state_version": 0,
        "round_index": 0,
        "phase": "awaiting_start",
        "rounds": rounds,
        "events": [],
        "metrics": [],
    }


def _event(game: dict, round_state: dict, event_type: str, *, value: dict | None = None, before: str, after: str) -> dict:
    before_version = game["state_version"]
    game["state_version"] += 1
    event = {
        "event_id": str(uuid4()),
        "sequence_no": len(game["events"]) + 1,
        "event_type": event_type,
        "server_received_at": _stamp(),
        "round_id": round_state["round_id"],
        "practice_or_main": round_state["practice_or_main"],
        "state_before_ref": before,
        "state_after_ref": after,
        "state_version_before": before_version,
        "state_version_after": game["state_version"],
        "immutable_parent_ref": f"game_presentation:{game['presentation']['presentation_id']}",
        "value": deepcopy(value),
    }
    game["events"].append(event)
    return event


def _allocation(round_state: dict, personal: object, reason: object, decision_type: str) -> dict:
    if isinstance(personal, bool) or not isinstance(personal, int):
        raise GameValidation("validation_error")
    total = round_state["total_resources"]
    if personal < 0 or personal > total:
        raise GameValidation("validation_error")
    if reason is not None and not isinstance(reason, str):
        raise GameValidation("validation_error")
    return {
        "decision_id": str(uuid4()),
        "decision_version": "1.0.0",
        "decision_type": decision_type,
        "personal": personal,
        "team": total - personal,
        "total_resources": total,
        "reason_self_report": reason or "",
        "reason_source_kind": "typed_self_report",
        "decided_at": _stamp(),
        "available_actions": list(range(0, total + 1)),
    }


def _result(round_state: dict, decision: dict) -> dict:
    requirements = round_state["final_requirements"]
    personal_ok = decision["personal"] >= requirements["personal_min"]
    team_ok = decision["team"] >= requirements["team_min"]
    prerequisite_met = personal_ok if requirements.get("prerequisite") else True
    return {
        "result_version": "1.0.0",
        "personal_condition_met": personal_ok,
        "team_condition_met": team_ok and prerequisite_met,
        "prerequisite_met": prerequisite_met,
        "requirements_snapshot": deepcopy(requirements),
        "calculation_rule": round_state["result_calculation"],
        "rules_version": "1.0.0",
        "interpretation_limit": "게임 규칙 안의 결과이며 협업 또는 성격 점수가 아니다.",
    }


def _complete_round(game: dict, round_state: dict) -> None:
    round_state["status"] = "completed"
    round_state["completed_at"] = _stamp()
    if game["round_index"] == len(game["rounds"]) - 1:
        game["phase"] = "complete"
    else:
        game["phase"] = "round_complete"
    game["metrics"] = aggregate_game(game)


def _deadline(round_state: dict) -> datetime:
    value = round_state.get("deadline_at")
    if not isinstance(value, str):
        raise GameValidation("invalid_state")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise GameValidation("invalid_state") from exc
    if parsed.tzinfo is None:
        raise GameValidation("invalid_state")
    return parsed


def _timeout_round(game: dict, round_state: dict, phase: str) -> None:
    round_state["missing_reason"] = {
        "decision": "timed_out_before_initial_decision",
        "allocated": "timed_out_before_new_information",
        "revision": "timed_out_without_final_decision",
    }[phase]
    after = "complete" if game["round_index"] == len(game["rounds"]) - 1 else "round_complete"
    _event(game, round_state, "round_timed_out", value={"missing_reason": round_state["missing_reason"]}, before=phase, after=after)
    _complete_round(game, round_state)


def apply_game_action(game: dict, action: str, *, personal: object = None, reason: object = None) -> None:
    if not isinstance(action, str) or action not in {"start", "open_info", "allocate", "reveal", "revise", "next", "timeout"}:
        raise GameValidation("validation_error")
    if game["phase"] == "complete":
        raise GameValidation("invalid_state")
    round_state = game["rounds"][game["round_index"]]
    phase = game["phase"]
    if phase in {"decision", "allocated", "revision"}:
        expired = _now() >= _deadline(round_state)
        if action == "timeout":
            if not expired:
                raise GameValidation("deadline_not_reached")
            _timeout_round(game, round_state, phase)
            return
        if expired:
            _timeout_round(game, round_state, phase)
            return
    if action == "start":
        if phase != "awaiting_start":
            raise GameValidation("invalid_state")
        started = _now()
        round_state["started_at"] = started.isoformat()
        round_state["deadline_at"] = (started + timedelta(milliseconds=round_state["time_limit_ms"])).isoformat()
        round_state["status"] = "in_progress"
        game["phase"] = "decision"
        _event(game, round_state, "round_started", before=phase, after="decision")
    elif action == "open_info":
        if phase != "decision" or round_state["information"]["opened"]:
            raise GameValidation("invalid_state")
        round_state["information"]["opened"] = True
        _event(
            game,
            round_state,
            "information_opened",
            value={"information_id": round_state["information"]["information_id"], "information_version": round_state["information"]["version"]},
            before=phase,
            after=phase,
        )
    elif action == "allocate":
        if phase != "decision":
            raise GameValidation("invalid_state")
        decision = _allocation(round_state, personal, reason, "initial")
        round_state["initial_decision"] = decision
        game["phase"] = "allocated"
        _event(game, round_state, "initial_allocation", value={k: decision[k] for k in ("decision_id", "personal", "team")}, before=phase, after="allocated")
    elif action == "reveal":
        if phase != "allocated":
            raise GameValidation("invalid_state")
        game["phase"] = "revision"
        round_state["new_information"]["revealed_at"] = _stamp()
        round_state["reward_table"] = deepcopy(round_state["reward_table_final"])
        _event(
            game,
            round_state,
            "new_information_revealed",
            value={"information_id": round_state["new_information"]["information_id"], "information_version": round_state["new_information"]["version"], "initial_decision_id": round_state["initial_decision"]["decision_id"]},
            before=phase,
            after="revision",
        )
    elif action == "revise":
        if phase != "revision":
            raise GameValidation("invalid_state")
        decision = _allocation(round_state, personal, reason, "revision")
        round_state["final_decision"] = decision
        initial = round_state["initial_decision"]
        round_state["revision_outcome"] = (
            "changed_after_evidence" if decision["personal"] != initial["personal"] else "unchanged_after_evidence"
        )
        round_state["game_result"] = _result(round_state, decision)
        after = "complete" if game["round_index"] == len(game["rounds"]) - 1 else "round_complete"
        _event(
            game,
            round_state,
            "final_allocation",
            value={
                "decision_id": decision["decision_id"],
                "personal": decision["personal"],
                "team": decision["team"],
                "revision_outcome": round_state["revision_outcome"],
                "new_information_id": round_state["new_information"]["information_id"],
            },
            before=phase,
            after=after,
        )
        _complete_round(game, round_state)
    elif action == "next":
        if phase != "round_complete":
            raise GameValidation("invalid_state")
        previous = round_state
        game["round_index"] += 1
        game["phase"] = "awaiting_start"
        _event(game, previous, "round_advanced", value={"next_round_id": game["rounds"][game["round_index"]]["round_id"]}, before=phase, after="awaiting_start")
    elif action == "timeout":
        raise GameValidation("invalid_state")


def aggregate_game(game: dict) -> list[dict]:
    main_rounds = [round_state for round_state in game["rounds"] if round_state["practice_or_main"] == "main"]
    events_by_round = {
        round_state["round_id"]: [event for event in game["events"] if event["round_id"] == round_state["round_id"]]
        for round_state in main_rounds
    }

    def sequence(round_state: dict, event_type: str) -> int | None:
        event = next((item for item in events_by_round[round_state["round_id"]] if item["event_type"] == event_type), None)
        return event["sequence_no"] if event else None

    def b01(round_state: dict) -> bool:
        opened, decided = sequence(round_state, "information_opened"), sequence(round_state, "initial_allocation")
        return opened is not None and decided is not None and opened < decided

    def b02(round_state: dict) -> bool:
        return sequence(round_state, "initial_allocation") is not None

    def b03(round_state: dict) -> bool:
        initial = sequence(round_state, "initial_allocation")
        revealed = sequence(round_state, "new_information_revealed")
        final = sequence(round_state, "final_allocation")
        return (
            initial is not None
            and revealed is not None
            and final is not None
            and initial < revealed < final
            and round_state.get("revision_outcome") == "changed_after_evidence"
        )

    def opportunity(round_state: dict, behavior_id: str) -> dict:
        return next(item for item in round_state["opportunities"] if item["behavior_id"] == behavior_id)

    def eligibility(round_state: dict, behavior_id: str) -> tuple[bool, str]:
        declared = opportunity(round_state, behavior_id)
        if not declared.get("eligible"):
            return False, str(declared.get("eligible_reason") or "definition_ineligible")
        if sequence(round_state, "round_started") is None:
            return False, "round_not_started"
        if behavior_id == "B03" and sequence(round_state, "new_information_revealed") is None:
            return False, "evidence_not_revealed"
        return True, "eligible_opportunity_presented"

    definitions = {
        "B01": ("map-game-b01", "info", b01),
        "B02": ("map-game-b02", "allocation", b02),
        "B03": ("map-game-b03", "revision", b03),
    }
    metrics = []
    for behavior_id, (mapping_id, suffix, observed) in definitions.items():
        eligible = [r for r in main_rounds if eligibility(r, behavior_id)[0]]
        included = [
            opportunity(r, behavior_id)["opportunity_id"]
            for r in eligible
        ]
        numerator = sum(1 for r in eligible if observed(r))
        denominator = len(eligible)
        observations = []
        for round_state in eligible:
            observation = {
                "round_id": round_state["round_id"],
                "opportunity_id": opportunity(round_state, behavior_id)["opportunity_id"],
                "observed": observed(round_state),
            }
            if behavior_id == "B01":
                opened, decided = sequence(round_state, "information_opened"), sequence(round_state, "initial_allocation")
                observation.update(information_open_sequence=opened, decision_sequence=decided)
                if decided is None:
                    observation["observed"] = None
                    observation["reason"] = round_state.get("missing_reason") or "no_finalized_initial_decision"
                elif opened is None:
                    observation["reason"] = "not_opened"
                elif opened >= decided:
                    observation["reason"] = "after_decision"
            elif behavior_id == "B02":
                observation.update(
                    initial_allocation=deepcopy(round_state.get("initial_decision")),
                    final_allocation=deepcopy(round_state.get("final_decision")),
                    total_resources=round_state["total_resources"],
                )
                if round_state.get("initial_decision") is None:
                    observation["observed"] = None
                    observation["reason"] = round_state.get("missing_reason") or "no_initial_decision"
            else:
                observation.update(
                    initial_decision_sequence=sequence(round_state, "initial_allocation"),
                    evidence_sequence=sequence(round_state, "new_information_revealed"),
                    final_decision_sequence=sequence(round_state, "final_allocation"),
                    revision_outcome=round_state.get("revision_outcome"),
                )
                if observation["initial_decision_sequence"] is None:
                    observation["reason"] = "no_initial_decision"
                elif observation["evidence_sequence"] is None:
                    observation["reason"] = "evidence_not_revealed"
                elif observation["final_decision_sequence"] is None:
                    observation["reason"] = "no_final_decision"
                elif not (
                    observation["initial_decision_sequence"]
                    < observation["evidence_sequence"]
                    < observation["final_decision_sequence"]
                ):
                    observation["reason"] = "invalid_event_order"
                elif round_state.get("revision_outcome") == "unchanged_after_evidence":
                    observation["reason"] = "unchanged_after_evidence"
            observations.append(observation)
        metrics.append(
            {
                "metric_id": f"metric-{behavior_id.lower()}",
                "behavior_id": behavior_id,
                "mapping_id": mapping_id,
                "mapping_version": "1.0.0",
                "numerator": numerator,
                "denominator": denominator,
                "value": numerator / denominator if denominator else None,
                "unit": "eligible_opportunity_ratio",
                "included_opportunity_ids": included,
                "excluded_opportunities_with_reasons": [
                    {"opportunity_id": opportunity(r, behavior_id)["opportunity_id"], "reason": "practice_excluded"}
                    for r in game["rounds"]
                    if r["practice_or_main"] == "practice"
                ]
                + [
                    {"opportunity_id": opportunity(r, behavior_id)["opportunity_id"], "reason": eligibility(r, behavior_id)[1]}
                    for r in main_rounds
                    if not eligibility(r, behavior_id)[0]
                ],
                "algorithm_version": game["algorithm_version"],
                "interpretation_limit": {
                    "B01": "정보 열기는 이해·동의의 증거가 아니다.",
                    "B02": "특정 배분이 더 좋은 성향 또는 능력 점수가 아니다.",
                    "B03": "유지도 적격 관찰이며 변경 횟수에 가점을 주지 않는다.",
                }[behavior_id],
                "opportunity_kind": suffix,
                "observations": observations,
            }
        )
    return metrics
