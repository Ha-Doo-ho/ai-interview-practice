from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4


class SurveyValidation(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _position(definition: dict, value: object, *, required: bool) -> dict | None:
    if value is None:
        if required:
            raise SurveyValidation("validation_error")
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise SurveyValidation("validation_error")
    option = next((entry for entry in definition["ordered_options"] if entry["position"] == value), None)
    if option is None:
        raise SurveyValidation("validation_error")
    return {
        "selected_option_id": option["option_id"],
        "selected_label_snapshot": option["label"],
        "selected_position": value,
    }


def _ordinal(definition: dict, response: object, status: str) -> dict:
    if response is None:
        if status == "submitted":
            raise SurveyValidation("validation_error")
        selected = None
    elif isinstance(response, dict):
        selected = _position(definition, response.get("selected_position"), required=status == "submitted")
    else:
        raise SurveyValidation("validation_error")
    return {
        **(selected or {}),
        "scale_id": definition["scale_id"],
        "scale_version": definition["scale_version"],
        "ordered_options_snapshot": deepcopy(definition["ordered_options"]),
        "missing_reason": None if selected else status,
    }


def _paired(definition: dict, response: object, status: str) -> dict:
    if not isinstance(response, dict):
        raise SurveyValidation("validation_error")
    result: dict = {
        "pair_id": definition["pair_id"],
        "respondent_user_id": None,
        "paired_item_version": definition["paired_item_version"],
        "perspective_presentation_order": deepcopy(definition["perspective_presentation_order"]),
        "prior_response_visible": bool(definition["prior_response_visible"]),
        "ordered_options_snapshot": deepcopy(definition["ordered_options"]),
    }
    for perspective in ("self", "imagined_others"):
        raw = response.get(perspective)
        if not isinstance(raw, dict):
            raise SurveyValidation("validation_error")
        branch_status = raw.get("status")
        if not isinstance(branch_status, str) or branch_status not in {"submitted", "timed_out", "skipped"}:
            raise SurveyValidation("validation_error")
        selected = _position(definition, raw.get("selected_position"), required=branch_status == "submitted")
        result[perspective] = {
            "perspective": perspective,
            "status": branch_status,
            **(selected or {}),
            "missing_reason": None if selected else branch_status,
        }
    if status == "submitted" and any(result[key]["status"] != "submitted" for key in ("self", "imagined_others")):
        raise SurveyValidation("validation_error")
    return result


def _slider(definition: dict, response: object, status: str) -> dict:
    if not isinstance(response, dict):
        raise SurveyValidation("validation_error")
    final = response.get("final_value")
    interacted = response.get("interaction_occurred")
    confirmed = response.get("explicit_confirmation")
    changes = response.get("change_count")
    if not isinstance(interacted, bool) or not isinstance(confirmed, bool):
        raise SurveyValidation("validation_error")
    if isinstance(changes, bool) or not isinstance(changes, int) or changes < 0:
        raise SurveyValidation("validation_error")
    if final is not None:
        if isinstance(final, bool) or not isinstance(final, (int, float)):
            raise SurveyValidation("validation_error")
        minimum, maximum, step = definition["min"], definition["max"], definition["step"]
        if final < minimum or final > maximum or abs((final - minimum) / step - round((final - minimum) / step)) > 1e-9:
            raise SurveyValidation("validation_error")
    if status == "submitted" and (final is None or not confirmed):
        raise SurveyValidation("validation_error")
    missing_reason = None
    if final is None:
        missing_reason = "timed_out_without_interaction" if status == "timed_out" and not interacted else status
    return {
        "left_anchor_id": definition["left_anchor"]["anchor_id"],
        "left_anchor_label": definition["left_anchor"]["label"],
        "right_anchor_id": definition["right_anchor"]["anchor_id"],
        "right_anchor_label": definition["right_anchor"]["label"],
        "min": definition["min"],
        "max": definition["max"],
        "step": definition["step"],
        "initial_value": definition["initial_value"],
        "final_value": final,
        "interaction_occurred": interacted,
        "explicit_confirmation": confirmed,
        "submit_status": status,
        "change_count": changes,
        "missing_reason": missing_reason,
    }


def _rank(definition: dict, response: object, status: str) -> dict:
    if not isinstance(response, dict):
        raise SurveyValidation("validation_error")
    selected = response.get("selected_ids")
    events = response.get("selection_events")
    if not isinstance(selected, list) or not isinstance(events, list):
        raise SurveyValidation("validation_error")
    all_ids = [entry["option_id"] for entry in definition["candidates"]]
    if any(not isinstance(value, str) for value in selected):
        raise SurveyValidation("validation_error")
    if len(selected) != len(set(selected)) or any(value not in all_ids for value in selected):
        raise SurveyValidation("validation_error")
    requested = definition["requested_k"]
    if len(selected) > requested or (status == "submitted" and len(selected) != requested):
        raise SurveyValidation("validation_error")
    ranked = response.get("ranked_selection", [{"option_id": value, "rank": rank} for rank, value in enumerate(selected, 1)])
    if not isinstance(ranked, list) or any(not isinstance(entry, dict) for entry in ranked):
        raise SurveyValidation("validation_error")
    ranks = [entry.get("rank") for entry in ranked]
    if any(isinstance(rank, bool) or not isinstance(rank, int) or not 1 <= rank <= requested for rank in ranks):
        raise SurveyValidation("validation_error")
    if len(ranks) != len(set(ranks)) or ranks != sorted(ranks) or [entry.get("option_id") for entry in ranked] != selected:
        raise SurveyValidation("validation_error")
    if status == "submitted" and ranks != list(range(1, requested + 1)):
        raise SurveyValidation("validation_error")
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get("action"), str) or event["action"] not in {"select", "move", "remove"}:
            raise SurveyValidation("validation_error")
        if event.get("option_id") not in all_ids:
            raise SurveyValidation("validation_error")
    return {
        "candidate_set_id": definition["candidate_set_id"],
        "candidate_set_version": definition["candidate_set_version"],
        "all_candidate_ids": all_ids,
        "candidate_snapshots": deepcopy(definition["candidates"]),
        "display_order": deepcopy(definition["display_order"]),
        "requested_k": requested,
        "ranked_selection": [{"option_id": entry["option_id"], "rank": entry["rank"]} for entry in ranked],
        "submitted_count": len(selected),
        "selection_events": deepcopy(events),
        "unselected_ids": [value for value in all_ids if value not in selected],
        "missing_reason": None if len(selected) == requested else status,
    }


def build_survey_record(
    *,
    definition: dict,
    user_id: str,
    run_id: str,
    attempt_id: str,
    presentation_order: int,
    response: object,
    status: str,
    elapsed_ms: int | None,
) -> dict:
    if not isinstance(status, str) or status not in {"submitted", "timed_out", "skipped"}:
        raise SurveyValidation("validation_error")
    if elapsed_ms is not None and (isinstance(elapsed_ms, bool) or not isinstance(elapsed_ms, int) or elapsed_ms < 0):
        raise SurveyValidation("validation_error")
    builders = {
        "ordinal_6": _ordinal,
        "paired_perspective": _paired,
        "bipolar_slider": _slider,
        "top_k_rank": _rank,
    }
    try:
        data = builders[definition["type"]](definition, response, status)
    except KeyError as exc:
        raise SurveyValidation("validation_error") from exc
    if definition["type"] == "paired_perspective":
        data["respondent_user_id"] = user_id
    data.update(
        {
            "item_id": definition["item_id"],
            "item_version": definition["item_version"],
            "behavior_id": definition.get("behavior_id"),
            "prompt_snapshot": definition["prompt"],
            "measurement_level": "ordinal" if definition["type"] in {"ordinal_6", "paired_perspective", "top_k_rank"} else "ordered_bipolar_position",
            "definition_snapshot": deepcopy(definition),
        }
    )
    completed = _now()
    return {
        "record_id": str(uuid4()),
        "record_version": "1.0.0",
        "source_type": "survey",
        "source_version": definition["item_version"],
        "user_id": user_id,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "item_id": definition["item_id"],
        "item_version": definition["item_version"],
        "instructions_version": definition["instructions_version"],
        "presentation_id": str(uuid4()),
        "presentation_order": presentation_order,
        "status": status,
        "started_at": None,
        "started_at_missing_reason": "client_start_time_not_collected",
        "presented_at": None,
        "presented_at_missing_reason": "definition_loaded_before_submission_without_server_presentation_event",
        "completed_at": completed,
        "context": {
            "response_type": definition["type"],
            "behavior_id": definition.get("behavior_id"),
            "language": "ko-KR",
            "time_limit_ms": definition.get("time_limit_ms"),
            "submitted_elapsed_ms": elapsed_ms,
        },
        "data": data,
        "quality_flags": [],
    }
