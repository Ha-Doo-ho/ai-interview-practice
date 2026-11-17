"""Evidence-preserving analysis for the text interview MVP.

The default implementation is deliberately conservative.  It does not claim
semantic understanding in mock mode: it preserves an asked answer as partial
self-report evidence, with an exact quote and an explicit limitation.  This is
useful for deterministic end-to-end verification without fabricating model
accuracy.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping, Sequence

from .ai_provider import Provider, ProviderError


AnalysisError = ProviderError

RUNTIME_MODES = frozenset({"mock", "live"})
COMPARISON_STATUSES = frozenset(
    {
        "supports_statement",
        "contextual_difference",
        "needs_clarification",
        "insufficient_evidence",
        "not_comparable",
    }
)
CRITERIA = ("situation", "role", "other_information", "action", "reasoning", "result", "learning")
CRITERION_STATUSES = frozenset({"explicit", "partial", "not_mentioned", "not_asked", "unassessable"})
BASELINE_INPUT_KEYS = frozenset({"question", "answer", "behavior_id", "rubric_version"})
CONDITIONED_INPUT_KEYS = BASELINE_INPUT_KEYS
LINEAGE_ALLOWLISTS = {
    "baseline_game": frozenset(
        {"game_events", "game_rules", "game_conditions", "game_state", "mapping_version"}
    ),
    "baseline_interview": frozenset(
        {"neutral_question", "typed_answer", "behavior_id", "rubric_version", "mapping_version"}
    ),
}
REQUIRED_MAPPING_FIELDS = frozenset(
    {
        "mapping_id",
        "version",
        "behavior_id",
        "reason",
        "observable_proxy",
        "preconditions",
        "limitations",
        "permitted_uses",
        "practice_review_status",
        "validity_status",
        "reviewer_type",
        "reviewer_id",
        "reviewed_at",
    }
)
FORBIDDEN_REPORT_KEYS = frozenset(
    {
        "score",
        "consistency_score",
        "confidence",
        "accuracy",
        "lie_probability",
        "truth_probability",
        "pass_probability",
        "personality_score",
        "hiring_recommendation",
    }
)

PROMPT_VERSION = "interview-extraction-v1"
QUESTION_PROMPT_VERSION = "adaptive-question-v1"
RUBRIC_VERSION = "evidence-rubric-v1"
SCHEMA_VERSION = "analysis-schema-v1"
COMPARISON_RULE_VERSION = "comparison-precedence-v1"
REPORT_VERSION = "evidence-report-v1"
ALGORITHM_VERSION = "deterministic-conservative-mock-v1"


def _error(code: str, detail: str | None = None) -> AnalysisError:
    return AnalysisError(f"{code}{': ' + detail if detail else ''}")


def validate_quote(
    source_text: str,
    span: Mapping[str, Any],
    source_id: str,
    source_version: str | int,
) -> dict[str, Any]:
    """Validate an immutable Unicode code point half-open citation."""

    if not isinstance(source_text, str):
        raise _error("source_text_invalid")
    if span.get("source_id") != source_id:
        raise _error("source_id_mismatch")
    if str(span.get("source_version")) != str(source_version):
        raise _error("source_version_mismatch")
    start, end = span.get("start"), span.get("end")
    if not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool):
        raise _error("quote_range_invalid")
    if start < 0 or end < start or end > len(source_text):
        raise _error("quote_range_out_of_bounds")
    if span.get("quote") != source_text[start:end]:
        raise _error("quote_mismatch")
    result = dict(span)
    if result.get("offset_unit", "unicode_code_point") != "unicode_code_point":
        raise _error("quote_offset_unit_invalid")
    return result


def validate_lineage_inputs(kind: str, inputs: Mapping[str, Any]) -> dict[str, Any]:
    allowed = LINEAGE_ALLOWLISTS.get(kind)
    if allowed is None:
        raise _error("lineage_kind_invalid", kind)
    leaked = sorted(set(inputs) - allowed)
    if leaked:
        raise _error("lineage_allowlist_violation", ",".join(leaked))
    return dict(inputs)


def build_cache_key(
    *,
    mode: str,
    user_id: str,
    run_id: str,
    attempt_id: str,
    source_id: str,
    source_version: str,
    question_version: str,
    rubric_version: str,
    mapping_version: str,
    prompt_version: str,
) -> list[str]:
    if mode not in {"baseline", "conditioned_followup"}:
        raise _error("cache_mode_invalid")
    values = (
        mode,
        user_id,
        run_id,
        attempt_id,
        source_id,
        source_version,
        question_version,
        rubric_version,
        mapping_version,
        prompt_version,
    )
    if any(value is None or str(value) == "" for value in values):
        raise _error("cache_key_incomplete")
    return [str(value) for value in values]


def _validate_extraction_input(payload: Mapping[str, Any], *, conditioned: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    allowed = CONDITIONED_INPUT_KEYS if conditioned else BASELINE_INPUT_KEYS
    leaked = sorted(set(payload) - allowed)
    if leaked:
        raise _error("input_allowlist_violation", ",".join(leaked))
    missing = sorted(allowed - set(payload))
    if missing:
        raise _error("input_missing", ",".join(missing))
    question = payload.get("question")
    answer = payload.get("answer")
    if not isinstance(question, dict) or not isinstance(answer, dict):
        raise _error("input_schema_invalid")
    question_mode = question.get("question_mode", "baseline")
    disclosed = question.get("conditioned_on_prior_evidence") is True
    if conditioned:
        if question_mode != "adaptive_followup" or not disclosed:
            raise _error("conditioned_question_required")
    elif question_mode != "baseline" or disclosed or question.get("generated_from_evidence_refs") or question.get("disclosed_prior_information"):
        raise _error("conditioned_question_in_baseline")
    if question.get("behavior_id") not in (None, payload.get("behavior_id")):
        raise _error("behavior_mismatch")
    if not question.get("question_id") or question.get("question_version") is None:
        raise _error("question_version_missing")
    if not answer.get("answer_id") or answer.get("answer_version") is None:
        raise _error("answer_version_missing")
    return question, answer


def _criterion_result(
    *,
    criterion: str,
    asked: set[str],
    answer: Mapping[str, Any],
) -> dict[str, Any]:
    text = answer.get("text")
    status = answer.get("status")
    if criterion not in asked:
        return {
            "criterion": criterion,
            "status": "not_asked",
            "evidence_spans": [],
            "limitations": ["이 질문에서 해당 요소를 요청하지 않았습니다."],
            "missing_reason": "criterion_not_asked",
        }
    if status in {"unasked", "asked_no_text"} or not isinstance(text, str) or not text:
        return {
            "criterion": criterion,
            "status": "unassessable",
            "evidence_spans": [],
            "limitations": ["제출된 답변 원문이 없어 내용을 평가할 수 없습니다."],
            "missing_reason": "asked_no_text",
        }
    return {
        "criterion": criterion,
        "status": "unassessable",
        "evidence_spans": [],
        "limitations": [
            "deterministic mock은 답변이 이 기준을 언급했는지 의미 판정하지 않습니다.",
            "진술의 실제 발생 여부는 검증되지 않았습니다.",
        ],
        "missing_reason": "mock_semantic_assessment_not_performed",
    }


def _extract(payload: Mapping[str, Any], *, conditioned: bool) -> dict[str, Any]:
    question, answer = _validate_extraction_input(payload, conditioned=conditioned)
    mode = "conditioned_followup" if conditioned else "baseline"
    asked = set(question.get("asked_criteria") or [])
    invalid_criteria = asked - set(CRITERIA)
    if invalid_criteria:
        raise _error("criterion_invalid", ",".join(sorted(invalid_criteria)))
    criteria = {
        criterion: _criterion_result(criterion=criterion, asked=asked, answer=answer)
        for criterion in CRITERIA
    }
    answer_spans: list[dict[str, Any]] = []
    text = answer.get("text")
    if isinstance(text, str) and text:
        span = {
            "source_id": answer["answer_id"],
            "source_version": answer["answer_version"],
            "start": 0,
            "end": len(text),
            "quote": text,
            "offset_unit": "unicode_code_point",
        }
        answer_spans.append(validate_quote(text, span, answer["answer_id"], answer["answer_version"]))
    result = {
        "extraction_id": f"extraction:{answer['answer_id']}:{answer['answer_version']}:{mode}",
        "version": "1",
        "answer_id": answer["answer_id"],
        "answer_version": answer["answer_version"],
        "question_id": question["question_id"],
        "question_version": question["question_version"],
        "mode": mode,
        "behavior_id": payload["behavior_id"],
        "rubric_id": question.get("rubric_id") or "evidence-rubric",
        "rubric_version": payload["rubric_version"],
        "criteria": criteria,
        "answer_evidence_spans": answer_spans,
        "model_id": None,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "runtime_mode": "mock",
        "provider_execution": "deterministic_local",
        "algorithm_version": ALGORITHM_VERSION,
        "created_at": None,
        "conditioned_on_prior_evidence": conditioned,
        "independent_confirmation": False if conditioned else None,
        "lineage": {
            "cache_namespace": mode,
            "input_fields": ["question", "answer", "behavior_id", "rubric_version"],
            "question_ref": f"{question['question_id']}@{question['question_version']}",
            "answer_ref": f"{answer['answer_id']}@{answer['answer_version']}",
            "rubric_ref": f"{question.get('rubric_id') or 'evidence-rubric'}@{payload['rubric_version']}",
        },
    }
    if conditioned:
        result["generated_from_evidence_refs"] = list(question.get("generated_from_evidence_refs") or [])
        result["disclosed_prior_information"] = deepcopy(question.get("disclosed_prior_information") or [])
    return result


def extract_answer(payload: Mapping[str, Any]) -> dict[str, Any]:
    return _extract(payload, conditioned=False)


def extract_conditioned_answer(payload: Mapping[str, Any]) -> dict[str, Any]:
    return _extract(payload, conditioned=True)


def validate_runtime_modes(items: Iterable[Mapping[str, Any]]) -> str:
    modes = {item.get("runtime_mode") for item in items if item.get("runtime_mode") is not None}
    invalid = modes - RUNTIME_MODES
    if invalid:
        raise _error("runtime_mode_invalid")
    if len(modes) > 1:
        raise _error("mixed_provenance")
    return next(iter(modes), "mock")


def validate_snapshot(run: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> None:
    if run.get("status") in {"deleting", "deleted"}:
        raise _error("run_deleted")
    for record in records:
        record_id = str(record.get("record_id", "unknown"))
        if record.get("user_id") != run.get("user_id"):
            raise _error("ownership_mismatch", record_id)
        if record.get("run_id") != run.get("run_id"):
            raise _error("cross_run_evidence", record_id)
        if run.get("attempt_id") is not None and record.get("attempt_id") != run.get("attempt_id"):
            raise _error("attempt_mismatch", record_id)
        if record.get("status") in {"withdrawn", "deleted", "deleting"} or record.get("consent_status") == "withdrawn":
            raise _error("withdrawn_evidence", record_id)
        if record.get("generation") is not None and run.get("generation") is not None and record.get("generation") != run.get("generation"):
            raise _error("stale_generation", record_id)
        if not record.get("record_id") or record.get("source_version") is None:
            raise _error("source_version_missing", record_id)


def compare_evidence(
    *,
    compatible: bool,
    denominator: int | None,
    numerator: int | None,
    explicit_support: bool,
    observation_difference: bool,
    documented_context_difference: bool,
    unresolved: bool,
) -> dict[str, Any]:
    if not compatible:
        status, reason = "not_comparable", "incompatible_behavior_mapping_unit_or_version"
    elif denominator is None or denominator <= 0:
        status, reason = "insufficient_evidence", "no_eligible_opportunity_or_relevant_evidence"
    elif observation_difference and documented_context_difference:
        status, reason = "contextual_difference", "recorded_observation_and_context_difference"
    elif unresolved:
        status, reason = "needs_clarification", "relevant_evidence_requires_context"
    elif explicit_support:
        status, reason = "supports_statement", "compatible_observation_supports_statement_direction"
    else:
        status, reason = "needs_clarification", "evidence_direction_not_resolved"
    return {
        "status": status,
        "reason": reason,
        "comparison_rule_version": COMPARISON_RULE_VERSION,
    }


def _iter_definitions(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [dict(item, **({} if "behavior_id" in item else {"behavior_id": key})) if isinstance(item, dict) else {"id": key, "value": item} for key, item in value.items()]
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    return []


def _mapping_for(definitions: Mapping[str, Any], behavior_id: str) -> tuple[dict[str, Any] | None, str | None]:
    candidates = [item for item in _iter_definitions(definitions.get("mappings")) if item.get("behavior_id") == behavior_id]
    if not candidates:
        return None, "mapping_missing"
    mapping = candidates[0]
    missing = sorted(REQUIRED_MAPPING_FIELDS - set(mapping))
    if missing:
        return mapping, "mapping_contract_incomplete"
    if mapping.get("practice_review_status") != "approved_for_practice":
        return mapping, "mapping_not_approved_for_practice"
    if mapping.get("validity_status") != "provisional_unvalidated":
        return mapping, "mapping_validity_status_invalid"
    uses = set(mapping.get("permitted_uses") or [])
    if not uses.intersection({"comparison", "evidence_comparison"}):
        return mapping, "mapping_use_not_permitted"
    return mapping, None


def _mapping_candidates(definitions: Mapping[str, Any], behavior_id: str) -> list[dict[str, Any]]:
    return [item for item in _iter_definitions(definitions.get("mappings")) if item.get("behavior_id") == behavior_id]


def _source_mapping(
    candidates: Sequence[Mapping[str, Any]],
    *,
    source_kind: str | None = None,
    source_definition_id: str | None = None,
    mapping_id: str | None = None,
) -> dict[str, Any] | None:
    for candidate in candidates:
        if source_kind is not None and candidate.get("source_kind") != source_kind:
            continue
        if source_definition_id is not None and str(candidate.get("source_definition_id")) != str(source_definition_id):
            continue
        if mapping_id is not None and candidate.get("mapping_id") != mapping_id:
            continue
        return dict(candidate)
    return None


def _mapping_eligibility_error(mapping: Mapping[str, Any] | None, *, use: str) -> str | None:
    if mapping is None:
        return "mapping_missing"
    missing = sorted(REQUIRED_MAPPING_FIELDS - set(mapping))
    if missing:
        return "mapping_contract_incomplete"
    if mapping.get("practice_review_status") != "approved_for_practice":
        return "mapping_not_approved_for_practice"
    if mapping.get("validity_status") != "provisional_unvalidated":
        return "mapping_validity_status_invalid"
    aliases = {
        "comparison": {"comparison", "evidence_comparison"},
        "question_generation": {"question_generation", "practice_question_generation"},
        "baseline_extraction": {"baseline_extraction"},
    }
    if not set(mapping.get("permitted_uses") or []).intersection(aliases[use]):
        return "mapping_use_not_permitted"
    return None


def _questions_by_id(run: Mapping[str, Any], definitions: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for source in (definitions.get("questions"), run.get("questions")):
        for question in _iter_definitions(source):
            question_id = question.get("question_id") or question.get("id")
            if question_id:
                result[str(question_id)] = question
    return result


def _answer_from_record(record: Mapping[str, Any]) -> dict[str, Any]:
    data = deepcopy(record.get("data") or {})
    if not data.get("answer_id"):
        data["answer_id"] = record.get("record_id")
    if data.get("answer_version") is None:
        data["answer_version"] = record.get("source_version")
    return data


def _current_answer_records(records: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    answers = [record for record in records if record.get("source_type") == "typed_answer"]
    by_ref: dict[tuple[str, str], Mapping[str, Any]] = {}
    predecessor_by_ref: dict[tuple[str, str], tuple[str, str]] = {}
    referenced: set[tuple[str, str]] = set()
    for record in answers:
        data = _answer_from_record(record)
        key = (str(data.get("answer_id")), str(data.get("answer_version")))
        if key in by_ref:
            raise _error("answer_version_duplicate", f"{key[0]}@{key[1]}")
        by_ref[key] = record
    for record in answers:
        data = _answer_from_record(record)
        previous = data.get("previous_answer_version_ref")
        if previous is None:
            continue
        if not isinstance(previous, dict):
            raise _error("correction_ref_invalid", str(data.get("answer_id")))
        prior_key = (str(previous.get("answer_id")), str(previous.get("answer_version")))
        prior_record = by_ref.get(prior_key)
        if prior_record is None:
            raise _error("correction_predecessor_missing", f"{prior_key[0]}@{prior_key[1]}")
        prior_data = _answer_from_record(prior_record)
        if prior_data.get("question_id") != data.get("question_id"):
            raise _error("correction_question_mismatch", str(data.get("answer_id")))
        if prior_key in referenced:
            raise _error("correction_fork", f"{prior_key[0]}@{prior_key[1]}")
        referenced.add(prior_key)
        current_key = (str(data.get("answer_id")), str(data.get("answer_version")))
        predecessor_by_ref[current_key] = prior_key
    for start in by_ref:
        seen: set[tuple[str, str]] = set()
        current = start
        while current in predecessor_by_ref:
            if current in seen:
                raise _error("correction_cycle", f"{current[0]}@{current[1]}")
            seen.add(current)
            current = predecessor_by_ref[current]
    leaves = [record for key, record in by_ref.items() if key not in referenced]
    by_question: dict[str, list[Mapping[str, Any]]] = {}
    for record in leaves:
        question_id = str(_answer_from_record(record).get("question_id"))
        by_question.setdefault(question_id, []).append(record)
    if any(len(values) > 1 for values in by_question.values()):
        raise _error("correction_chain_ambiguous")
    return leaves


def _question_for_answer(answer: Mapping[str, Any], questions: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    question = deepcopy(questions.get(str(answer.get("question_id"))) or {})
    snapshots = {
        "question_id": answer.get("question_id"),
        "question_version": answer.get("question_version"),
        "question_text": answer.get("question_text_snapshot"),
        "behavior_id": answer.get("behavior_id"),
        "question_mode": answer.get("question_mode"),
        "conditioned_on_prior_evidence": answer.get("conditioned_on_prior_evidence"),
        "disclosed_prior_information": answer.get("disclosed_prior_information"),
        "generated_from_evidence_refs": answer.get("generated_from_evidence_refs"),
        "rubric_id": answer.get("rubric_id"),
        "rubric_version": answer.get("rubric_version"),
    }
    for key, value in snapshots.items():
        if value is not None:
            if key in question and str(question[key]) != str(value):
                raise _error("question_snapshot_mismatch", str(answer.get("question_id")))
            question[key] = value
    question.setdefault("asked_criteria", ["action", "reasoning"])
    question.setdefault("question_mode", "baseline")
    question.setdefault("conditioned_on_prior_evidence", question["question_mode"] != "baseline")
    if not question.get("question_id") or question.get("question_version") is None:
        raise _error("question_missing", str(answer.get("question_id")))
    return question


def _metric_list(run: Mapping[str, Any]) -> list[dict[str, Any]]:
    metrics = run.get("game", {}).get("metrics", []) if isinstance(run.get("game"), dict) else []
    values = _iter_definitions(metrics)
    for metric in values:
        numerator, denominator = metric.get("numerator"), metric.get("denominator")
        if denominator is None:
            continue
        if not isinstance(denominator, int) or denominator < 0:
            raise _error("metric_invalid", str(metric.get("metric_id")))
        if numerator is not None and (not isinstance(numerator, int) or numerator < 0 or numerator > denominator):
            raise _error("metric_invalid", str(metric.get("metric_id")))
        if denominator == 0 and numerator not in (None, 0):
            raise _error("metric_invalid", str(metric.get("metric_id")))
    return deepcopy(values)


def validate_paired_response(
    data: Mapping[str, Any],
    *,
    owner_user_id: str,
    expected_pair_id: str | None,
) -> list[str]:
    """Return actionable paired-self-report errors without inventing a peer."""

    errors: list[str] = []
    if expected_pair_id is not None and data.get("pair_id") != expected_pair_id:
        errors.append("pair_id_mismatch")
    if data.get("respondent_user_id") != owner_user_id:
        errors.append("respondent_user_mismatch")
    for perspective in ("self", "imagined_others"):
        branch = data.get(perspective)
        if not isinstance(branch, dict):
            errors.append(f"missing_{perspective}")
            continue
        if branch.get("perspective") != perspective:
            errors.append(f"{perspective}_perspective_mismatch")
        status = branch.get("status")
        if status not in {"submitted", "timed_out", "skipped"}:
            errors.append(f"{perspective}_status_invalid")
        if status == "submitted" and branch.get("selected_position") is None:
            errors.append(f"{perspective}_submitted_without_selection")
    source_roles = [data.get("source_role")]
    source_roles.extend(
        branch.get("source_role")
        for branch in (data.get("self"), data.get("imagined_others"))
        if isinstance(branch, dict)
    )
    if any(role not in (None, "self_report") for role in source_roles):
        errors.append("source_role_mismatch")
    order = {
        "pair_id_mismatch": 0,
        "respondent_user_mismatch": 1,
        "missing_self": 2,
        "missing_imagined_others": 3,
        "source_role_mismatch": 99,
    }
    return sorted(set(errors), key=lambda value: (order.get(value, 50), value))


def _survey_by_behavior(
    records: Sequence[Mapping[str, Any]], definitions: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    definition_by_item = {
        str(item.get("item_id")): item
        for item in _iter_definitions(definitions.get("surveys"))
        if item.get("item_id")
    }
    for record in records:
        source_type = str(record.get("source_type", ""))
        if "survey" not in source_type and source_type not in {"ordinal_6", "paired_perspective", "bipolar_slider", "top_k_rank"}:
            continue
        data = deepcopy(record.get("data") or {})
        item_definition = definition_by_item.get(str(record.get("item_id")), {})
        if item_definition and str(item_definition.get("item_version")) != str(record.get("item_version")):
            raise _error("survey_definition_version_mismatch", str(record.get("record_id")))
        behavior_id = (
            data.get("behavior_id")
            or record.get("context", {}).get("behavior_id")
            or item_definition.get("behavior_id")
        )
        if behavior_id:
            record_status = str(record.get("status", ""))
            data["record_id"] = record.get("record_id")
            data["source_version"] = record.get("source_version")
            data["item_id"] = record.get("item_id")
            data["item_version"] = record.get("item_version")
            data["response_type"] = record.get("context", {}).get("response_type")
            data["record_status"] = record_status
            data["evidence_eligibility"] = "eligible" if record_status == "submitted" else "partial_not_eligible"
            if item_definition.get("type") == "paired_perspective" or "pair_id" in data:
                paired_errors = validate_paired_response(
                    data,
                    owner_user_id=str(record.get("user_id")),
                    expected_pair_id=item_definition.get("pair_id"),
                )
                if paired_errors:
                    data["_eligibility_errors"] = paired_errors
                    data["source_interpretation"] = "invalid_paired_self_report_record"
                    data["evidence_eligibility"] = "invalid"
            key = str(behavior_id)
            if key not in result:
                result[key] = deepcopy(data)
                result[key]["responses"] = [deepcopy(data)]
            else:
                result[key]["responses"].append(deepcopy(data))
    return result


def _survey_precondition_errors(
    response: Mapping[str, Any], mapping: Mapping[str, Any] | None
) -> list[str]:
    """Check the approved source mapping against the preserved response state."""

    if mapping is None:
        return []
    preconditions = set(mapping.get("preconditions") or [])
    errors: list[str] = []
    if "submitted" in preconditions and response.get("record_status") != "submitted":
        errors.append("submitted")
    if "ordinal_label_preserved" in preconditions and (
        response.get("selected_position") is None or not response.get("selected_label_snapshot")
    ):
        errors.append("ordinal_label_preserved")
    if "both_perspectives_submitted" in preconditions:
        if any(
            not isinstance(response.get(perspective), dict)
            or response[perspective].get("status") != "submitted"
            for perspective in ("self", "imagined_others")
        ):
            errors.append("both_perspectives_submitted")
    if "paired_version_matched" in preconditions:
        if str(response.get("paired_item_version")) != str(response.get("item_version")):
            errors.append("paired_version_matched")
    if "explicit_confirmation" in preconditions and response.get("explicit_confirmation") is not True:
        errors.append("explicit_confirmation")
    if "valid_step" in preconditions:
        snapshot = response.get("definition_snapshot") or {}
        value = response.get("final_value")
        minimum, maximum, step = snapshot.get("min"), snapshot.get("max"), snapshot.get("step")
        if (
            value is None
            or not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not isinstance(minimum, (int, float))
            or not isinstance(maximum, (int, float))
            or not isinstance(step, (int, float))
            or step <= 0
            or value < minimum
            or value > maximum
            or abs((value - minimum) / step - round((value - minimum) / step)) > 1e-9
        ):
            errors.append("valid_step")
    return errors


def _metric_by_behavior(metrics: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for metric in metrics:
        if metric.get("behavior_id"):
            result.setdefault(str(metric["behavior_id"]), dict(metric))
    return result


def _criterion_spans(extraction: Mapping[str, Any]) -> list[dict[str, Any]]:
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for span in extraction.get("answer_evidence_spans", []):
        key = (span.get("source_id"), str(span.get("source_version")), span.get("start"), span.get("end"), span.get("quote"))
        unique[key] = dict(span)
    for item in extraction.get("criteria", {}).values():
        for span in item.get("evidence_spans", []):
            key = (span.get("source_id"), str(span.get("source_version")), span.get("start"), span.get("end"), span.get("quote"))
            unique[key] = dict(span)
    return list(unique.values())


def _adaptive_question(
    behavior_id: str,
    survey: Mapping[str, Any] | None,
    metric: Mapping[str, Any] | None,
    extraction: Mapping[str, Any] | None,
    rubric_mapping: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build a grounded follow-up that names the narrow observed action."""

    refs: list[str] = []
    disclosed: list[str] = []
    clauses: list[str] = []
    if survey:
        label = survey.get("selected_label_snapshot") or survey.get("selected_label")
        if label:
            clauses.append(f"자기보고 문항에서 '{label}'을 선택했습니다")
            disclosed.append(f"survey label: {label}")
            refs.append(f"survey:{survey['record_id']}@{survey['source_version']}")
    if metric and metric.get("denominator") is not None:
        numerator, denominator = metric.get("numerator"), metric.get("denominator")
        if denominator == 0:
            clauses.append("이번 과제에는 이 행동을 기록할 적격 기회가 없었습니다")
            disclosed.append("game observation: no eligible opportunity")
        else:
            observed_action = {
                "B01": "결정 전에 정보 창을 연 횟수",
                "B02": "개인·팀 배분을 확정한 횟수",
                "B03": "새 정보 뒤 선택을 바꾼 횟수(유지도 허용)",
            }.get(behavior_id, "해당 행동이 기록된 횟수")
            clauses.append(f"이번 과제의 적격 기회 {denominator}회 중 {observed_action}는 {numerator}회였습니다")
            disclosed.append(f"game observation: {numerator}/{denominator} eligible opportunities")
        refs.append(f"game_metric:{metric.get('metric_id')}@{metric.get('algorithm_version')}")
    if extraction:
        refs.append(f"extraction:{extraction['extraction_id']}@{extraction['version']}")
    if not clauses:
        return None
    focus = {
        "B01": "다른 사람의 정보를 확인할지 정한 판단 기준이나 조건",
        "B02": "개인 과제와 팀 과제 사이에서 배분을 확정한 판단 기준이나 조건",
        "B03": "새 정보를 받은 뒤 기존 선택을 유지하거나 바꾼 판단 기준이나 조건",
    }.get(behavior_id, "그 행동을 선택한 판단 기준이나 조건")
    rubric_id = (extraction or {}).get("rubric_id") or (rubric_mapping or {}).get("source_definition_id") or f"rubric-{behavior_id.lower()}"
    rubric_version = (extraction or {}).get("rubric_version") or (rubric_mapping or {}).get("source_definition_version") or RUBRIC_VERSION
    return {
        "question_id": f"followup:{behavior_id}:v1",
        "question_version": "1",
        "question_text": f"{', '.join(clauses)}. 실제 경험에서 {focus}을 설명해 주세요.",
        "behavior_id": behavior_id,
        "target_behavior_ids": [behavior_id],
        "question_mode": "adaptive_followup",
        "asked_criteria": ["reasoning"],
        "conditioned_on_prior_evidence": True,
        "generated_from_evidence_refs": refs,
        "disclosure_refs": refs,
        "disclosed_prior_information": disclosed,
        "selection_reason": "관찰된 좁은 행동과 자기보고의 조건 차이를 설명하는 연습 질문",
        "trigger_rule_id": "adaptive-context-check",
        "trigger_rule_version": "1",
        "question_prompt_version": QUESTION_PROMPT_VERSION,
        "rubric_id": rubric_id,
        "rubric_version": rubric_version,
        "runtime_mode": "mock",
    }


def _practice_suggestion(behavior_id: str) -> str:
    return {
        "B01": "다음 연습에서는 누구에게 무엇을 확인했고 그 정보가 결정에 어떻게 반영됐는지 설명해 보세요.",
        "B02": "다음 연습에서는 개인·팀 자원의 배분 기준, 고려한 다른 선택지, 결과를 구분해 설명해 보세요.",
        "B03": "다음 연습에서는 새 정보가 무엇이었고 무엇을 유지하거나 수정했는지, 그 이유를 설명해 보세요.",
    }.get(behavior_id, "다음 연습에서는 관찰 가능한 행동과 당시 조건을 구분해 설명해 보세요.")


def _report(
    *,
    run: Mapping[str, Any],
    definitions: Mapping[str, Any],
    surveys: Mapping[str, Mapping[str, Any]],
    metrics: Sequence[Mapping[str, Any]],
    extractions: Sequence[Mapping[str, Any]],
    comparisons: Sequence[Mapping[str, Any]],
    questions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    metric_map = _metric_by_behavior(metrics)
    baseline_map = {item["behavior_id"]: item for item in extractions if item["mode"] == "baseline"}
    comparison_map = {item["behavior_id"]: item for item in comparisons}
    question_map = {item["behavior_id"]: item for item in questions}
    behaviors = _iter_definitions(definitions.get("behaviors"))
    behavior_map = {str(item.get("behavior_id")): item for item in behaviors if item.get("behavior_id")}
    ordered_ids = [behavior_id for behavior_id in ("B01", "B02", "B03") if behavior_id in behavior_map or behavior_id in comparison_map]
    cards: list[dict[str, Any]] = []
    answer_texts = {
        (data.get("answer_id"), str(data.get("answer_version"))): data.get("text", "")
        for record in run.get("records", [])
        if record.get("source_type") == "typed_answer"
        for data in [record.get("data") or {}]
    }
    for behavior_id in ordered_ids:
        definition = behavior_map.get(behavior_id, {})
        comparison = comparison_map[behavior_id]
        extraction = baseline_map.get(behavior_id)
        interview_evidence: list[dict[str, Any]] = []
        if extraction:
            for span in _criterion_spans(extraction):
                interview_evidence.append(
                    {
                        **span,
                        "answer_text": answer_texts.get((span["source_id"], str(span["source_version"])), ""),
                        "source_kind": "typed_self_report",
                        "extraction_ref": f"{extraction['extraction_id']}@{extraction['version']}",
                        "limitations": ["자기보고 진술이며 실제 발생 사실을 인증하지 않습니다."],
                    }
                )
        survey = surveys.get(behavior_id)
        metric = metric_map.get(behavior_id)
        source_refs = list(comparison.get("evidence_refs", []))
        card = {
            "claim_id": f"claim:{run['run_id']}:{behavior_id}:1",
            "claim_type": "evidence_connection",
            "behavior_id": behavior_id,
            "behavior_name": definition.get("name", behavior_id),
            "operational_definition": definition.get("operational_definition"),
            "comparison_status": comparison["status"],
            "survey_evidence": deepcopy(survey) if survey else None,
            "game_evidence": deepcopy(metric) if metric else None,
            "interview_evidence": interview_evidence,
            "comparison": {
                "status": comparison["status"],
                "reason": comparison["reason"],
                "causal_claim": False,
                "independent_confirmation_from_followup": False,
            },
            "limitations": list(comparison.get("limitations", [])),
            "open_question": question_map.get(behavior_id, {}).get("question_text"),
            "practice_suggestion": _practice_suggestion(behavior_id),
            "practice_suggestion_basis_refs": source_refs,
            "source_refs": source_refs,
            "rubric_id": (extraction or {}).get("rubric_id") or "evidence-rubric",
            "rubric_version": (extraction or {}).get("rubric_version") or RUBRIC_VERSION,
            "runtime_mode": "mock",
        }
        cards.append(card)
    return {
        "report_id": f"report:{run['run_id']}:{run.get('attempt_id')}:g{run.get('generation')}",
        "report_version": REPORT_VERSION,
        "title": "나의 근거 연결 보고서",
        "summary": "자기보고, 과제에서 관찰된 선택, 면접 자기보고를 출처별로 연결했습니다. 결과는 연습용이며 성격·진실성·채용 결과를 판정하지 않습니다.",
        "cards": cards,
        "runtime_mode": "mock",
        "model_id": None,
        "prompt_version": QUESTION_PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "lineage": {
            "user_id": run.get("user_id"),
            "run_id": run.get("run_id"),
            "attempt_id": run.get("attempt_id"),
            "generation": run.get("generation"),
            "baseline_extraction_refs": [f"{x['extraction_id']}@{x['version']}" for x in extractions if x["mode"] == "baseline"],
            "conditioned_followup_refs": [f"{x['extraction_id']}@{x['version']}" for x in extractions if x["mode"] == "conditioned_followup"],
            "mapping_version_policy": "approved_for_practice_only",
        },
        "limitations": [
            "순서형 응답의 라벨과 위치 사이 간격은 측정되지 않았으므로 평균, 백분율, 간격 크기로 해석할 수 없습니다.",
            "라운드마다 정보와 보상 조건이 함께 달라질 수 있어 보상 결과 차이를 정보 확인의 인과 효과로 해석할 수 없습니다.",
            "deterministic mock은 답변의 의미 완전성을 판정하지 않습니다.",
            "과제 관찰은 해당 조건의 대리 지표이며 과제 밖 행동으로 일반화할 수 없습니다.",
            "후속 답변은 앞선 근거를 공개한 뒤 작성된 조건부 자기보고이며 독립 확인으로 계산하지 않습니다.",
        ],
    }


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def validate_report(
    report: Mapping[str, Any],
    run: Mapping[str, Any],
    metrics: Sequence[Mapping[str, Any]],
    extractions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    forbidden = sorted(set(_walk_keys(report)) & FORBIDDEN_REPORT_KEYS)
    if forbidden:
        raise _error("forbidden_report_field", ",".join(forbidden))
    if report.get("runtime_mode") not in RUNTIME_MODES:
        raise _error("runtime_mode_invalid")
    validate_snapshot(run, run.get("records", []))
    records_by_answer: dict[tuple[str, str], Mapping[str, Any]] = {}
    survey_records: dict[tuple[str, str], Mapping[str, Any]] = {}
    for record in run.get("records", []):
        if "survey" in str(record.get("source_type", "")):
            survey_records[(str(record.get("record_id")), str(record.get("source_version")))] = record
        if record.get("source_type") != "typed_answer":
            continue
        data = record.get("data") or {}
        records_by_answer[(str(data.get("answer_id")), str(data.get("answer_version")))] = data
    metrics_by_id = {str(metric.get("metric_id")): metric for metric in metrics}
    extraction_ids = {str(item.get("extraction_id")) for item in extractions}
    valid_evidence_refs = {
        *(f"survey:{record_id}@{version}" for record_id, version in survey_records),
        *(f"game_metric:{metric.get('metric_id')}@{metric.get('algorithm_version')}" for metric in metrics),
        *(f"extraction:{item.get('extraction_id')}@{item.get('version')}" for item in extractions),
    }
    for card in report.get("cards", []):
        if card.get("comparison_status") not in COMPARISON_STATUSES:
            raise _error("comparison_status_invalid")
        game = card.get("game_evidence")
        if game:
            stored = metrics_by_id.get(str(game.get("metric_id")))
            if stored is None or any(game.get(key) != stored.get(key) for key in ("numerator", "denominator", "behavior_id", "mapping_version")):
                raise _error("metric_mismatch", str(game.get("metric_id")))
        survey = card.get("survey_evidence")
        if survey:
            responses = survey.get("responses", [survey])
            if responses:
                primary = responses[0]
                for key, value in survey.items():
                    if key != "responses" and key in primary and value != primary[key]:
                        raise _error("survey_mismatch", str(primary.get("record_id")))
            for response in responses:
                record_key = (str(response.get("record_id")), str(response.get("source_version")))
                record = survey_records.get(record_key)
                if record is None:
                    raise _error("survey_source_missing", record_key[0])
                original = record.get("data") or {}
                metadata = {
                    "item_id": record.get("item_id"),
                    "item_version": record.get("item_version"),
                    "response_type": record.get("context", {}).get("response_type"),
                    "record_status": record.get("status"),
                    "evidence_eligibility": "eligible" if record.get("status") == "submitted" else "partial_not_eligible",
                }
                for key, value in response.items():
                    if key in {"record_id", "source_version", "_eligibility_errors", "source_interpretation", "evidence_eligibility"}:
                        continue
                    expected = original.get(key, metadata.get(key))
                    if value != expected:
                        raise _error("survey_mismatch", f"{record_key[0]}:{key}")
        for ref in card.get("source_refs") or []:
            if ref not in valid_evidence_refs:
                raise _error("evidence_ref_missing", str(ref))
        for citation in card.get("interview_evidence") or []:
            key = (str(citation.get("source_id")), str(citation.get("source_version")))
            answer = records_by_answer.get(key)
            if answer is None:
                raise _error("citation_source_missing", key[0])
            validate_quote(answer.get("text", ""), citation, key[0], key[1])
            extraction_ref = str(citation.get("extraction_ref", "")).split("@", 1)[0]
            if extraction_ref not in extraction_ids:
                raise _error("extraction_ref_missing", extraction_ref)
    return dict(report)


def validate_model_extraction_output(output: Mapping[str, Any], source_text: str, source_id: str, source_version: str) -> dict[str, Any]:
    """Validate a future live structured extraction before it can be stored."""

    if set(output) != {"criteria"} or not isinstance(output.get("criteria"), list):
        raise _error("provider_schema_invalid")
    seen: set[str] = set()
    for item in output["criteria"]:
        if not isinstance(item, dict) or set(item) - {"criterion", "status", "evidence_spans", "limitations", "missing_reason"}:
            raise _error("provider_schema_invalid")
        criterion, status = item.get("criterion"), item.get("status")
        if criterion not in CRITERIA or criterion in seen or status not in CRITERION_STATUSES:
            raise _error("provider_schema_invalid")
        seen.add(criterion)
        spans = item.get("evidence_spans") or []
        if status in {"explicit", "partial"} and not spans:
            raise _error("provider_schema_invalid")
        if status in {"not_mentioned", "not_asked", "unassessable"} and spans:
            raise _error("provider_schema_invalid")
        for span in spans:
            validate_quote(source_text, span, source_id, source_version)
    if seen != set(CRITERIA):
        raise _error("provider_schema_invalid")
    return deepcopy(dict(output))


def analyze_run(run: dict[str, Any], definitions: dict[str, Any]) -> dict[str, Any]:
    """Analyze one owned, version-fixed run snapshot.

    The caller must still re-check generation/deletion immediately before
    persisting the returned derivation.  This function records the generation
    it analyzed so the store can perform that completion guard.
    """

    required = {"run_id", "user_id", "attempt_id", "generation", "records", "runtime_mode"}
    missing = sorted(required - set(run))
    if missing:
        raise _error("run_snapshot_incomplete", ",".join(missing))
    if run.get("runtime_mode") != "mock":
        if run.get("runtime_mode") == "live":
            raise _error("live_analysis_blocked: no approved provider execution")
        raise _error("runtime_mode_invalid")
    records = run.get("records")
    if not isinstance(records, list):
        raise _error("records_invalid")
    validate_snapshot(run, records)
    validate_runtime_modes([run, definitions])
    questions_by_id = _questions_by_id(run, definitions)

    extractions: list[dict[str, Any]] = []
    for record in _current_answer_records(records):
        answer = _answer_from_record(record)
        question = _question_for_answer(answer, questions_by_id)
        behavior_id = answer.get("behavior_id") or question.get("behavior_id")
        source_candidates = _mapping_candidates(definitions, str(behavior_id))
        default_interview_mapping = _source_mapping(source_candidates, source_kind="interview_rubric")
        if default_interview_mapping is not None:
            question.setdefault("rubric_id", default_interview_mapping.get("source_definition_id"))
            question.setdefault("rubric_version", default_interview_mapping.get("source_definition_version"))
        extraction_input = {
            "question": question,
            "answer": answer,
            "behavior_id": behavior_id,
            "rubric_version": question.get("rubric_version") or RUBRIC_VERSION,
        }
        if question.get("question_mode") == "adaptive_followup":
            extraction = extract_conditioned_answer(extraction_input)
        else:
            extraction = extract_answer(extraction_input)
        interview_mapping = _source_mapping(
            source_candidates,
            source_kind="interview_rubric",
            source_definition_id=extraction.get("rubric_id"),
        )
        if interview_mapping is None and source_candidates and not any(item.get("source_kind") for item in source_candidates):
            interview_mapping = source_candidates[0]
        extraction["mapping_id"] = (interview_mapping or {}).get("mapping_id")
        extraction["mapping_version"] = (interview_mapping or {}).get("version")
        mapping_eligibility_error = (
            _mapping_eligibility_error(interview_mapping, use="baseline_extraction")
            if interview_mapping and interview_mapping.get("source_kind")
            else (None if interview_mapping else "mapping_missing")
        )
        if (
            mapping_eligibility_error is None
            and interview_mapping
            and interview_mapping.get("source_kind")
            and str(extraction.get("rubric_version")) != str(interview_mapping.get("source_definition_version"))
        ):
            mapping_eligibility_error = "rubric_version_incompatible"
        extraction["mapping_eligible"] = mapping_eligibility_error is None
        extraction["mapping_eligibility_error"] = mapping_eligibility_error
        extraction["lineage"].update(
            {
                "user_id": run["user_id"],
                "run_id": run["run_id"],
                "attempt_id": run["attempt_id"],
                "generation": run["generation"],
                "cache_key": build_cache_key(
                    mode=extraction["mode"],
                    user_id=str(run["user_id"]),
                    run_id=str(run["run_id"]),
                    attempt_id=str(run["attempt_id"]),
                    source_id=str(answer["answer_id"]),
                    source_version=str(answer["answer_version"]),
                    question_version=str(question["question_version"]),
                    rubric_version=str(extraction["rubric_version"]),
                    mapping_version=str((interview_mapping or {}).get("version") or "unmapped"),
                    prompt_version=PROMPT_VERSION,
                ),
            }
        )
        extractions.append(extraction)

    metrics = _metric_list(run)
    surveys = _survey_by_behavior(records, definitions)
    metric_map = _metric_by_behavior(metrics)
    baseline_by_behavior = {item["behavior_id"]: item for item in extractions if item["mode"] == "baseline"}
    conditioned_by_behavior: dict[str, list[dict[str, Any]]] = {}
    for item in extractions:
        if item["mode"] == "conditioned_followup":
            conditioned_by_behavior.setdefault(item["behavior_id"], []).append(item)

    behavior_definitions = _iter_definitions(definitions.get("behaviors"))
    behavior_ids = [str(item.get("behavior_id")) for item in behavior_definitions if item.get("behavior_id")]
    for behavior_id in ("B01", "B02", "B03"):
        if behavior_id not in behavior_ids:
            behavior_ids.append(behavior_id)

    comparisons: list[dict[str, Any]] = []
    generated_questions: list[dict[str, Any]] = []
    for behavior_id in behavior_ids:
        candidates = _mapping_candidates(definitions, behavior_id)
        source_aware = any(item.get("source_kind") for item in candidates)
        mapping: dict[str, Any] | None = None
        mapping_error: str | None = None
        eligible_mappings: list[dict[str, Any]] = []
        excluded_evidence: list[dict[str, str]] = []
        survey = surveys.get(behavior_id)
        metric = metric_map.get(behavior_id)
        baseline = baseline_by_behavior.get(behavior_id)
        conditioned = conditioned_by_behavior.get(behavior_id, [])
        question_survey: Mapping[str, Any] | None = None
        question_rubric_mapping: Mapping[str, Any] | None = None
        denominator = metric.get("denominator") if metric else None
        numerator = metric.get("numerator") if metric else None
        evidence_refs: list[str] = []
        if source_aware:
            if metric:
                game_mapping = _source_mapping(
                    candidates,
                    source_kind="game_event_rule",
                    mapping_id=metric.get("mapping_id"),
                )
                error = _mapping_eligibility_error(game_mapping, use="comparison")
                if error:
                    mapping_error = f"game_{error}"
                elif metric.get("mapping_version") is not None and str(metric.get("mapping_version")) != str(game_mapping.get("version")):
                    mapping_error = "game_mapping_version_incompatible"
                else:
                    eligible_mappings.append(game_mapping)
                    evidence_refs.append(f"game_metric:{metric.get('metric_id')}@{metric.get('algorithm_version')}")
            if survey:
                for response in survey.get("responses", [survey]):
                    paired_errors = response.get("_eligibility_errors") or []
                    ref = f"survey:{response['record_id']}@{response['source_version']}"
                    if paired_errors:
                        reason = "paired_perspective_invalid:" + ",".join(paired_errors)
                        mapping_error = mapping_error or reason
                        excluded_evidence.append({"evidence_ref": ref, "reason": reason})
                        continue
                    survey_mapping = _source_mapping(
                        candidates,
                        source_definition_id=str(response.get("item_id")),
                    )
                    precondition_errors = _survey_precondition_errors(response, survey_mapping)
                    if precondition_errors:
                        reason = "survey_precondition_not_met:" + ",".join(precondition_errors)
                        excluded_evidence.append({"evidence_ref": ref, "reason": reason})
                        continue
                    error = _mapping_eligibility_error(survey_mapping, use="comparison")
                    if error == "mapping_use_not_permitted":
                        excluded_evidence.append({"evidence_ref": ref, "reason": "survey_mapping_use_not_permitted"})
                        continue
                    if error:
                        mapping_error = mapping_error or f"survey_{error}"
                        excluded_evidence.append({"evidence_ref": ref, "reason": f"survey_{error}"})
                        continue
                    if response.get("item_version") is not None and str(response.get("item_version")) != str(survey_mapping.get("source_definition_version")):
                        mapping_error = mapping_error or "survey_mapping_version_incompatible"
                        excluded_evidence.append({"evidence_ref": ref, "reason": "survey_mapping_version_incompatible"})
                        continue
                    eligible_mappings.append(survey_mapping)
                    evidence_refs.append(ref)
            if baseline:
                interview_mapping = _source_mapping(
                    candidates,
                    source_kind="interview_rubric",
                    source_definition_id=baseline.get("rubric_id"),
                )
                error = _mapping_eligibility_error(interview_mapping, use="comparison")
                if error is None and baseline.get("mapping_eligibility_error") == "rubric_version_incompatible":
                    error = "rubric_version_incompatible"
                ref = f"extraction:{baseline['extraction_id']}@{baseline['version']}"
                if error:
                    mapping_error = mapping_error or f"interview_{error}"
                    excluded_evidence.append({"evidence_ref": ref, "reason": f"interview_{error}"})
                else:
                    eligible_mappings.append(interview_mapping)
                    evidence_refs.append(ref)
            mapping = eligible_mappings[0] if eligible_mappings else (candidates[0] if candidates else None)
        else:
            mapping, mapping_error = _mapping_for(definitions, behavior_id)
            if mapping_error is None and metric:
                if metric.get("mapping_id") is not None and metric.get("mapping_id") != mapping.get("mapping_id"):
                    mapping_error = "mapping_id_incompatible"
                elif metric.get("mapping_version") is not None and str(metric.get("mapping_version")) != str(mapping.get("version")):
                    mapping_error = "mapping_version_incompatible"
            if survey:
                for response in survey.get("responses", [survey]):
                    evidence_refs.append(f"survey:{response['record_id']}@{response['source_version']}")
            if metric:
                evidence_refs.append(f"game_metric:{metric.get('metric_id')}@{metric.get('algorithm_version')}")
            if baseline:
                evidence_refs.append(f"extraction:{baseline['extraction_id']}@{baseline['version']}")
        compatible = mapping_error is None
        if mapping_error:
            decision = {"status": "not_comparable", "reason": mapping_error, "comparison_rule_version": COMPARISON_RULE_VERSION}
        else:
            decision = compare_evidence(
                compatible=compatible,
                denominator=denominator,
                numerator=numerator,
                explicit_support=False,
                observation_difference=False,
                documented_context_difference=bool(metric and metric.get("documented_context_difference")),
                unresolved=bool(evidence_refs),
            )
        comparison = {
            "comparison_id": f"comparison:{run['run_id']}:{behavior_id}:g{run['generation']}",
            "version": "1",
            "behavior_id": behavior_id,
            "behavior_version": (mapping or {}).get("behavior_version", "1"),
            "mapping_id": (mapping or {}).get("mapping_id"),
            "mapping_version": (mapping or {}).get("version"),
            "mapping_refs": [f"{item.get('mapping_id')}@{item.get('version')}" for item in eligible_mappings] if source_aware else ([f"{mapping.get('mapping_id')}@{mapping.get('version')}"] if mapping else []),
            "evidence_refs": evidence_refs,
            "excluded_evidence_with_reasons": excluded_evidence,
            "baseline_extraction_refs": [baseline["extraction_id"]] if baseline else [],
            "conditioned_followup_refs": [item["extraction_id"] for item in conditioned],
            "conditioned_followups_counted_as_independent": False,
            "status": decision["status"],
            "reason": decision["reason"],
            "limitations": [
                "이 비교는 같은 연습 회차의 기록된 조건에만 적용됩니다.",
                "자기보고 진술의 진실이나 안정된 성향을 인증하지 않습니다.",
            ],
            "comparison_rule_version": COMPARISON_RULE_VERSION,
            "runtime_mode": "mock",
            "model_id": None,
            "prompt_version": QUESTION_PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
        comparisons.append(comparison)
        if source_aware:
            question_allowed = any(
                _mapping_eligibility_error(item, use="question_generation") is None
                for item in candidates
            )
            if survey:
                for response in survey.get("responses", [survey]):
                    candidate_mapping = _source_mapping(
                        candidates,
                        source_definition_id=str(response.get("item_id")),
                    )
                    if (
                        not response.get("_eligibility_errors")
                        and not _survey_precondition_errors(response, candidate_mapping)
                        and _mapping_eligibility_error(candidate_mapping, use="question_generation") is None
                    ):
                        question_survey = response
                        break
            question_rubric_mapping = _source_mapping(
                candidates,
                source_kind="interview_rubric",
                source_definition_id=(baseline or {}).get("rubric_id") or f"rubric-{behavior_id.lower()}",
            )
        else:
            question_allowed = mapping_error is None
            question_survey = survey
        if mapping_error is None and question_allowed:
            followup = _adaptive_question(
                behavior_id,
                question_survey,
                metric,
                baseline,
                question_rubric_mapping,
            )
            if followup:
                generated_questions.append(followup)

    report = _report(
        run=run,
        definitions=definitions,
        surveys=surveys,
        metrics=metrics,
        extractions=extractions,
        comparisons=comparisons,
        questions=generated_questions,
    )
    validate_report(report, run, metrics, extractions)
    return {
        "extractions": extractions,
        "metrics": metrics,
        "comparisons": comparisons,
        "questions": generated_questions,
        "report": report,
        "runtime_mode": "mock",
    }
