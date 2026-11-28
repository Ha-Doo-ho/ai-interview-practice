"""Grounded live extraction and deterministic unified interview reports.

Only immutable baseline question/answer text and server definitions enter the
provider. Survey and game evidence is joined after extraction for display and
deterministic comparison, never as a model profile.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from typing import Any, Callable, Mapping
from uuid import uuid4

from .ai_provider import BudgetLimits, LiveProvider, GeminiProvider, ProviderError
from .analysis import (
    CRITERIA,
    CRITERION_STATUSES,
    REQUIRED_MAPPING_FIELDS,
    compare_evidence,
    validate_quote,
)


InterviewAnalysisError = ProviderError

PROMPT_VERSION = "grounded-interview-extraction-v1"
SCHEMA_VERSION = "grounded-interview-extraction-schema-v1"
REPORT_VERSION = "grounded-unified-report-v1"
PRACTICE_TEMPLATE_VERSION = "rubric-practice-v1"
OFFSET_UNIT = "unicode_code_point"

LIVE_CONFIG_KEYS = frozenset(
    {
        "AI_PROVIDER_KEY",
        "AI_MODEL_ID",
        "AI_ALLOWED_MODEL_IDS",
        "AI_LIVE_ENABLED",
        "PAID_AI_ENABLED",
        "AI_MAX_COST_MICROUSD",
        "AI_INPUT_RATE_MICROUSD_PER_MILLION_TOKENS",
        "AI_OUTPUT_RATE_MICROUSD_PER_MILLION_TOKENS",
    }
)

# Tests may monkeypatch this callable. Production leaves it None and therefore
# uses LiveProvider's HTTPS transport. It is intentionally never put in a
# prepared object or persisted result.
_PROVIDER_TRANSPORT: Callable[..., Any] | None = None

_DEFAULT_LIMITS = {
    "max_input_tokens": 12_000,
    "max_output_tokens": 2_000,
    "timeout_ms": 30_000,
    "max_retries": 0,
    "max_calls_per_run": 9,
}

_STATUS_LIMITATIONS = {
    "explicit": ["이 표시는 답변 원문에 해당 요소가 명시되었다는 뜻이며 실제 경험의 진실성을 검증하지 않습니다."],
    "partial": ["이 표시는 답변 원문에 일부 관련 내용이 있다는 뜻이며 실제 경험의 진실성을 검증하지 않습니다."],
    "not_mentioned": ["요청한 요소가 이 답변 원문에서 명시적으로 확인되지 않았습니다. 행동이 없었다는 뜻이 아닙니다."],
    "not_asked": ["이 질문에서 해당 요소를 요청하지 않았습니다."],
    "unassessable": ["제출된 답변 원문이 없거나 의미 분석을 실행하지 않아 판정할 수 없습니다."],
}

_PRACTICE_TEXT = {
    "situation": "다음 연습에서는 당시 상황과 제약을 한 문장으로 먼저 설명해 보세요.",
    "role": "다음 연습에서는 본인이 맡은 역할과 책임 범위를 구체적으로 설명해 보세요.",
    "other_information": "다음 연습에서는 누구에게 어떤 정보를 확인했는지 설명해 보세요.",
    "action": "다음 연습에서는 본인이 실제로 한 행동을 순서대로 설명해 보세요.",
    "reasoning": "다음 연습에서는 선택 기준과 다른 대안을 함께 설명해 보세요.",
    "result": "다음 연습에서는 확인 가능한 결과와 그 범위를 설명해 보세요.",
    "learning": "다음 연습에서는 이후 유지하거나 바꾼 점을 설명해 보세요.",
}


def _error(code: str, detail: str | None = None) -> ProviderError:
    return ProviderError(code if detail is None else f"{code}: {detail}")


def _positive_int(name: str, default: int | None = None, *, allow_zero: bool = False) -> int:
    raw = os.getenv(name)
    if raw in (None, ""):
        if default is None:
            raise _error("live_not_configured", name)
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise _error("config_invalid", name) from exc
    if value < 0 or (value == 0 and not allow_zero):
        raise _error("config_invalid", name)
    return value


def _live_config() -> dict[str, Any]:
    model_id = os.getenv('AI_MODEL_ID', '')
    model_provider = 'gemini' if model_id.startswith('gemini-') else 'openai'
    provider_name = (os.getenv('AI_PROVIDER', '').strip().lower() or model_provider)
    if provider_name not in ('openai', 'gemini'):
        raise _error('provider_invalid')
    missing = sorted(key for key in LIVE_CONFIG_KEYS if not os.getenv(key))
    if missing:
        raise _error("live_not_configured", ",".join(missing))
    if os.getenv("AI_LIVE_ENABLED", "").lower() != "true":
        raise _error("live_disabled")
    if os.getenv("PAID_AI_ENABLED", "").lower() != "true":
        raise _error("paid_ai_not_approved")
    if provider_name != model_provider:
        raise _error('provider_model_mismatch')
    allowed = {item.strip() for item in os.environ["AI_ALLOWED_MODEL_IDS"].split(",") if item.strip()}
    if model_id not in allowed:
        raise _error("model_not_allowed")
    config = {
        "provider": provider_name,
        "model_id": model_id,
        "max_input_tokens": _positive_int("AI_MAX_INPUT_TOKENS", _DEFAULT_LIMITS["max_input_tokens"]),
        "max_output_tokens": _positive_int("AI_MAX_OUTPUT_TOKENS", _DEFAULT_LIMITS["max_output_tokens"]),
        "timeout_ms": _positive_int("AI_TIMEOUT_MS", _DEFAULT_LIMITS["timeout_ms"]),
        "max_retries": _positive_int("AI_MAX_RETRIES", _DEFAULT_LIMITS["max_retries"], allow_zero=True),
        "max_calls_per_run": _positive_int("AI_MAX_CALLS_PER_RUN", _DEFAULT_LIMITS["max_calls_per_run"]),
        "max_cost_microusd": _positive_int("AI_MAX_COST_MICROUSD"),
        "input_rate": _positive_int("AI_INPUT_RATE_MICROUSD_PER_MILLION_TOKENS"),
        "output_rate": _positive_int("AI_OUTPUT_RATE_MICROUSD_PER_MILLION_TOKENS"),
    }
    if config["max_retries"] != 0:
        raise _error("config_invalid", "AI_MAX_RETRIES")
    return config


def analysis_capabilities() -> dict[str, Any]:
    """Return public availability without leaking a key or request content."""

    try:
        config = _live_config()
    except ProviderError as exc:
        code = str(exc).split(":", 1)[0]
        capability = {
            "live_available": False,
            "reason": code,
            "model_id": os.getenv("AI_MODEL_ID") or None,
            "max_calls_per_run": _safe_public_int("AI_MAX_CALLS_PER_RUN"),
            "max_cost_microusd": _safe_public_int("AI_MAX_COST_MICROUSD"),
        }
        if code == "live_not_configured":
            capability["missing_settings"] = sorted(name for name in LIVE_CONFIG_KEYS if not os.getenv(name))
        return capability
    return {
        "live_available": True,
        "reason": "available",
        "model_id": config["model_id"],
        "max_calls_per_run": config["max_calls_per_run"],
        "max_cost_microusd": config["max_cost_microusd"],
    }


def _safe_public_int(name: str) -> int | None:
    try:
        value = int(os.getenv(name, ""))
    except ValueError:
        return None
    return value if value >= 0 else None


def _question_list(run: Mapping[str, Any], definitions: Mapping[str, Any]) -> list[dict[str, Any]]:
    run_questions = {str(item.get("question_id")): item for item in run.get("questions", []) if isinstance(item, dict)}
    result = []
    for defined in definitions.get("questions", []):
        if not isinstance(defined, dict) or defined.get("question_mode") != "baseline":
            continue
        candidate = run_questions.get(str(defined.get("question_id")))
        immutable_fields = (
            "question_version", "question_text", "behavior_id", "target_behavior_ids",
            "asked_criteria", "question_mode", "rubric_id",
            "conditioned_on_prior_evidence", "disclosed_prior_information",
            "generated_from_evidence_refs",
        )
        if candidate is None or any(candidate.get(key) != defined.get(key) for key in immutable_fields):
            raise _error("question_definition_mismatch", str(defined.get("question_id")))
        if candidate.get("rubric_version") != defined.get("rubric_version"):
            raise _error("rubric_version_incompatible", str(defined.get("question_id")))
        result.append(deepcopy(candidate))
    return result


def _latest_leaf_answers(run: Mapping[str, Any], questions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    neutral_ids = {str(item["question_id"]) for item in questions}
    records = [item for item in run.get("records", []) if isinstance(item, dict) and item.get("source_type") == "typed_answer"]
    superseded = {
        str(previous.get("answer_id"))
        for record in records
        if isinstance((previous := (record.get("data") or {}).get("previous_answer_version_ref")), dict)
        and previous.get("answer_id")
    }
    leaves: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for record in records:
        data = record.get("data") or {}
        answer_id = data.get("answer_id") or record.get("record_id")
        if not answer_id or str(answer_id) in superseded:
            continue
        question_id = str(data.get("question_id") or record.get("item_id") or "")
        if question_id in neutral_ids:
            # Older neutral records did not persist these empty fields. Explicit
            # conditioning is never erased while constructing the model input.
            if (data.get("question_mode", "baseline") != "baseline"
                    or data.get("conditioned_on_prior_evidence", False) is not False
                    or data.get("disclosed_prior_information", []) != []
                    or data.get("generated_from_evidence_refs", []) != []):
                raise _error("baseline_conditioning_mismatch", question_id)
        answer = {
            "answer_id": str(answer_id),
            "answer_version": str(data.get("answer_version") or record.get("source_version")),
            "question_id": question_id,
            "question_version": str(data.get("question_version") or record.get("item_version")),
            "status": data.get("status") or record.get("status"),
            "text": data.get("text") if isinstance(data.get("text"), str) else "",
        }
        leaves.setdefault(question_id, []).append((int(record.get("presentation_order") or 0), answer))
    result: dict[str, dict[str, Any]] = {}
    for question in questions:
        question_id = str(question["question_id"])
        candidates = leaves.get(question_id, [])
        if len(candidates) > 1:
            raise _error("answer_leaf_ambiguous", question_id)
        if candidates:
            answer = candidates[0][1]
            if answer["question_version"] != str(question["question_version"]):
                raise _error("answer_question_version_mismatch", question_id)
            result[question_id] = answer
    return result


def input_snapshot(run: Mapping[str, Any], definitions: Mapping[str, Any]) -> dict[str, Any]:
    questions = _question_list(run, definitions)
    answers = _latest_leaf_answers(run, questions)
    snapshot = {
        "generation": run.get("generation"),
        "definitions_version": definitions.get("version"),
        "question_refs": [
            {"question_id": item.get("question_id"), "question_version": item.get("question_version")}
            for item in questions
        ],
        "answer_refs": [
            {
                "answer_id": answers[item["question_id"]]["answer_id"],
                "answer_version": answers[item["question_id"]]["answer_version"],
                "question_id": item["question_id"],
                "question_version": item["question_version"],
                "status": answers[item["question_id"]]["status"],
            }
            for item in questions if item["question_id"] in answers
        ],
        "survey_record_refs": [
            {
                "record_id": item.get("record_id"),
                "record_version": item.get("record_version"),
                "source_version": item.get("source_version"),
                "status": item.get("status"),
            }
            for item in run.get("records", [])
            if isinstance(item, dict) and item.get("source_type") == "survey"
        ],
        "resource_game": _resource_game_ref(run.get("game")),
        "rule_games": _rule_game_refs(run.get("rule_games")),
    }
    if run.get("flow_version") == "five-game-v2":
        snapshot["appointment_games_digest"] = hashlib.sha256(json.dumps(
            run.get("appointment_games"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
    return snapshot


def _resource_game_ref(game: Any) -> dict[str, Any] | None:
    if not isinstance(game, dict):
        return None
    return {key: game.get(key) for key in ("game_id", "game_version", "state_version")}


def _rule_game_refs(rule_games: Any) -> list[dict[str, Any]]:
    if not isinstance(rule_games, dict):
        return []
    refs = []
    for game in (rule_games.get("games") or {}).values():
        if not isinstance(game, dict):
            continue
        refs.append({
            "game_id": game.get("game_id"),
            "game_version": game.get("game_version"),
            "state_version": game.get("state_version", rule_games.get("version")),
            "content_digest": hashlib.sha256(json.dumps(game, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
        })
    return refs


def _behavior(definitions: Mapping[str, Any], behavior_id: str) -> dict[str, Any]:
    for item in definitions.get("behaviors", []):
        if isinstance(item, dict) and item.get("behavior_id") == behavior_id:
            allowed = ("behavior_id", "behavior_version", "name", "operational_definition", "inclusions", "exclusions", "context_requirements")
            return {key: deepcopy(item.get(key)) for key in allowed}
    raise _error("behavior_definition_missing", behavior_id)


def _mapping_base_eligible(mapping: Mapping[str, Any], *, use: str) -> bool:
    aliases = {
        "baseline_extraction": {"baseline_extraction"},
        "comparison": {"comparison", "evidence_comparison"},
    }
    return (
        REQUIRED_MAPPING_FIELDS.issubset(mapping)
        and all(mapping.get(key) not in (None, "") for key in REQUIRED_MAPPING_FIELDS)
        and mapping.get("practice_review_status") == "approved_for_practice"
        and mapping.get("validity_status") == "provisional_unvalidated"
        and bool(set(mapping.get("permitted_uses") or []).intersection(aliases[use]))
    )


def _interview_mapping(
    definitions: Mapping[str, Any], question: Mapping[str, Any], *, use: str
) -> tuple[dict[str, Any] | None, str | None]:
    behavior_id = str(question.get("behavior_id"))
    candidates = [
        item for item in definitions.get("mappings", [])
        if isinstance(item, dict)
        and item.get("source_kind") == "interview_rubric"
        and item.get("behavior_id") == behavior_id
        and item.get("source_definition_id") == question.get("rubric_id")
    ]
    if len(candidates) != 1:
        return None, "interview_mapping_missing_or_ambiguous"
    mapping = candidates[0]
    behavior = _behavior(definitions, behavior_id)
    if str(mapping.get("source_definition_version")) != str(question.get("rubric_version")):
        return mapping, "rubric_version_incompatible"
    if str(mapping.get("behavior_version")) != str(behavior.get("behavior_version")):
        return mapping, "behavior_version_incompatible"
    if not _mapping_base_eligible(mapping, use=use):
        return mapping, "interview_mapping_ineligible"
    return mapping, None


def _rubric() -> dict[str, Any]:
    return {
        "rubric_id": "evidence-rubric",
        "rubric_version": "1.0.0",
        "criteria": list(CRITERIA),
        "statuses": ["explicit", "partial", "not_mentioned", "not_asked", "unassessable"],
        "meaning": "Status only records whether the answer text explicitly contains the requested element.",
    }


def _model_input(
    question: Mapping[str, Any], answer: Mapping[str, Any], definitions: Mapping[str, Any],
    mapping: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "question": {
            "question_id": question["question_id"],
            "question_version": question["question_version"],
            "question_text": question["question_text"],
            "asked_criteria": list(question.get("asked_criteria") or []),
            "rubric_id": question.get("rubric_id"),
            "rubric_version": question.get("rubric_version"),
        },
        "answer": {key: answer[key] for key in ("answer_id", "answer_version", "status", "text")},
        "behavior": _behavior(definitions, str(question["behavior_id"])),
        "rubric": {
            **_rubric(),
            "rubric_id": question.get("rubric_id"),
            "rubric_version": question.get("rubric_version"),
            "mapping_id": mapping.get("mapping_id"),
            "mapping_version": mapping.get("version"),
        },
    }


def _output_schema() -> dict[str, Any]:
    span = {
        "type": "object",
        "properties": {
            "start": {"type": "integer", "minimum": 0},
            "end": {"type": "integer", "minimum": 0},
            "quote": {"type": "string", "maxLength": 400},
        },
        "required": ["start", "end", "quote"],
        "additionalProperties": False,
    }
    item = {
        "type": "object",
        "properties": {
            "criterion": {"type": "string", "enum": list(CRITERIA)},
            "status": {"type": "string", "enum": ["explicit", "partial", "not_mentioned", "not_asked", "unassessable"]},
            "evidence_spans": {"type": "array", "items": span, "maxItems": 2},
        },
        "required": ["criterion", "status", "evidence_spans"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"criteria": {"type": "array", "items": item, "minItems": 7, "maxItems": 7}},
        "required": ["criteria"],
        "additionalProperties": False,
    }


def _conservative_tokens(value: Any) -> int:
    # One token per UTF-8 byte is deliberately conservative for every script.
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _cost_microusd(input_tokens: int, output_tokens: int, input_rate: int, output_rate: int) -> int:
    return math.ceil((input_tokens * input_rate + output_tokens * output_rate) / 1_000_000)


def prepare_analysis(run: Mapping[str, Any], definitions: Mapping[str, Any], mode: str) -> dict[str, Any]:
    if mode not in {"live", "mock"}:
        raise _error("mode_invalid")
    questions = _question_list(run, definitions)
    answers = _latest_leaf_answers(run, questions)
    missing = [item["question_id"] for item in questions if item["question_id"] not in answers]
    if missing:
        raise _error("baseline_answers_incomplete", ",".join(missing))
    snapshot = input_snapshot(run, definitions)
    if mode == "mock":
        return {
            "requested_mode": "mock", "runtime_mode": "mock", "provider_execution": "not_called",
            "model_id": None, "input_snapshot": snapshot, "calls_required": 0, "cost_microusd": 0,
            "max_calls_per_run": 0, "max_cost_microusd": 0, "max_input_tokens": 0,
            "max_output_tokens": 0, "timeout_ms": 0, "max_retries": 0,
            "_run": deepcopy(dict(run)), "_definitions": deepcopy(dict(definitions)), "_calls": [],
        }
    config = _live_config()
    calls = []
    for question in questions:
        answer = answers[question["question_id"]]
        if answer["status"] == "asked_answered" and answer["text"].strip():
            mapping, mapping_error = _interview_mapping(definitions, question, use="baseline_extraction")
            if mapping_error:
                raise _error(mapping_error, str(question["question_id"]))
            structured = _model_input(question, answer, definitions, mapping)
            bound = {
                "model": config["model_id"],
                "store": False,
                "tools": [],
                "instructions_version": PROMPT_VERSION,
                "instructions": LiveProvider.instructions,
                "input": [{"role": "user", "content": [{"type": "input_text", "text": json.dumps(structured, ensure_ascii=False)}]}],
                "text": {"format": {"type": "json_schema", "name": "interview_analysis", "strict": True, "schema": _output_schema()}},
            }
            input_tokens = _conservative_tokens(bound)
            if config['provider'] == 'gemini':
                input_tokens = max(input_tokens, _conservative_tokens(GeminiProvider.payload(structured, config['max_output_tokens'], _output_schema(), model_id=config['model_id'])))
            if input_tokens > config["max_input_tokens"]:
                raise _error("budget_exceeded", "input_tokens")
            calls.append({
                "question": question, "answer": answer, "mapping": deepcopy(mapping),
                "structured_input": structured, "input_tokens": input_tokens,
            })
    if not calls:
        raise _error("live_answer_required")
    if len(calls) > config["max_calls_per_run"]:
        raise _error("budget_exceeded", "calls")
    cost = sum(_cost_microusd(item["input_tokens"], config["max_output_tokens"], config["input_rate"], config["output_rate"]) for item in calls)
    if cost > config["max_cost_microusd"]:
        raise _error("budget_exceeded", "cost")
    test_double = _PROVIDER_TRANSPORT is not None
    return {
        "requested_mode": "live",
        "runtime_mode": "mock" if test_double else "live",
        "provider_execution": "test_double" if test_double else "provider_completed",
        "model_id": config["model_id"], "input_snapshot": snapshot,
        "calls_required": len(calls), "cost_microusd": cost,
        "max_calls_per_run": config["max_calls_per_run"], "max_cost_microusd": config["max_cost_microusd"],
        "max_input_tokens": config["max_input_tokens"], "max_output_tokens": config["max_output_tokens"],
        "timeout_ms": config["timeout_ms"], "max_retries": 0,
        "_input_rate": config["input_rate"], "_output_rate": config["output_rate"], "_provider": config['provider'],
        "_run": deepcopy(dict(run)), "_definitions": deepcopy(dict(definitions)), "_calls": calls,
    }


def _resolve_gemini_quote_offsets(output: Mapping[str, Any], source: str) -> dict[str, Any]:
    """Recompute a unique exact quote's Unicode offsets; strict validation still follows."""
    result = deepcopy(output)
    if not isinstance(result, dict) or not isinstance(source, str) or not isinstance(result.get('criteria'), list):
        return result
    for item in result['criteria']:
        if not isinstance(item, dict) or not isinstance(item.get('evidence_spans'), list):
            continue
        for span in item['evidence_spans']:
            if not isinstance(span, dict) or not isinstance(span.get('quote'), str) or not span['quote']:
                continue
            quote=span['quote']; start=span.get('start'); end=span.get('end')
            if type(start) is int and type(end) is int and 0 <= start < end <= len(source) and source[start:end] == quote:
                continue
            index=source.find(quote)
            if index >= 0 and source.find(quote,index+1) == -1:
                span['start']=index; span['end']=index+len(quote)
    return result


def _server_criteria(question: Mapping[str, Any], answer: Mapping[str, Any], output: Mapping[str, Any] | None) -> dict[str, Any]:
    asked = set(question.get("asked_criteria") or [])
    if output is None:
        return {
            criterion: {
                "criterion": criterion,
                "status": "not_asked" if criterion not in asked else "unassessable",
                "evidence_spans": [],
                "limitations": deepcopy(_STATUS_LIMITATIONS["not_asked" if criterion not in asked else "unassessable"]),
                "missing_reason": "criterion_not_asked" if criterion not in asked else (
                    "asked_no_text" if not answer.get("text") else "ai_not_used"
                ),
            }
            for criterion in CRITERIA
        }
    if set(output) != {"criteria"} or not isinstance(output.get("criteria"), list) or len(output["criteria"]) != 7:
        raise _error("provider_schema_invalid")
    seen: dict[str, dict[str, Any]] = {}
    for item in output["criteria"]:
        if not isinstance(item, dict) or set(item) != {"criterion", "status", "evidence_spans"}:
            raise _error("provider_schema_invalid")
        criterion, status, spans = item["criterion"], item["status"], item["evidence_spans"]
        if criterion not in CRITERIA or criterion in seen or status not in CRITERION_STATUSES or not isinstance(spans, list):
            raise _error("provider_schema_invalid")
        if criterion not in asked and (status != "not_asked" or spans):
            raise _error("provider_schema_invalid")
        if criterion in asked and status == "not_asked":
            raise _error("provider_schema_invalid")
        if status in {"explicit", "partial"} and not spans:
            raise _error("provider_schema_invalid")
        if status not in {"explicit", "partial"} and spans:
            raise _error("provider_schema_invalid")
        if len(spans) > 2:
            raise _error("provider_schema_invalid")
        validated = []
        for raw in spans:
            if not isinstance(raw, dict) or set(raw) != {"start", "end", "quote"}:
                raise _error("provider_schema_invalid")
            if (
                isinstance(raw.get("start"), bool) or not isinstance(raw.get("start"), int)
                or isinstance(raw.get("end"), bool) or not isinstance(raw.get("end"), int)
                or raw["end"] <= raw["start"]
                or not isinstance(raw.get("quote"), str)
                or not raw["quote"].strip()
                or len(raw["quote"]) > 400
            ):
                raise _error("provider_schema_invalid")
            bound = {
                **raw, "source_id": answer["answer_id"], "source_version": answer["answer_version"],
                "offset_unit": OFFSET_UNIT,
            }
            try:
                validated.append(validate_quote(answer["text"], bound, answer["answer_id"], answer["answer_version"]))
            except ProviderError as exc:
                raise _error("citation_invalid") from exc
        seen[criterion] = {
            "criterion": criterion, "status": status, "evidence_spans": validated,
            "limitations": deepcopy(_STATUS_LIMITATIONS[status]),
            "missing_reason": None if status in {"explicit", "partial"} else (
                "criterion_not_asked" if status == "not_asked" else status
            ),
        }
    if set(seen) != set(CRITERIA):
        raise _error("provider_schema_invalid")
    return {criterion: seen[criterion] for criterion in CRITERIA}


def _metric_for(run: Mapping[str, Any], behavior_id: str) -> Mapping[str, Any] | None:
    sources = []
    game = run.get("game") or {}
    if isinstance(game, dict):
        sources.append(game.get("metrics", []))
    # Retain compatibility with snapshots that separately persisted the old
    # deterministic analysis result while preferring the original game facts.
    analysis = run.get("analysis") or {}
    if isinstance(analysis, dict):
        sources.append(analysis.get("metrics", []))
    for metrics in sources:
        for item in metrics if isinstance(metrics, list) else []:
            if isinstance(item, dict) and item.get("behavior_id") == behavior_id:
                return item
    return None


def _resource_mapping_compatible(
    run: Mapping[str, Any], definitions: Mapping[str, Any], behavior_id: str,
    metric: Mapping[str, Any] | None,
) -> tuple[bool, list[str]]:
    question = next((item for item in _question_list(run, definitions) if item.get("behavior_id") == behavior_id), None)
    if question is None:
        return False, []
    interview_mapping, interview_error = _interview_mapping(definitions, question, use="comparison")
    refs = [f"{interview_mapping.get('mapping_id')}@{interview_mapping.get('version')}"] if interview_mapping else []
    if interview_error:
        return False, refs
    if metric is None:
        return True, refs
    candidates = [
        item for item in definitions.get("mappings", [])
        if isinstance(item, dict)
        and item.get("source_kind") == "game_event_rule"
        and item.get("behavior_id") == behavior_id
        and item.get("mapping_id") == metric.get("mapping_id")
    ]
    if len(candidates) != 1:
        return False, refs
    mapping = candidates[0]
    refs.append(f"{mapping.get('mapping_id')}@{mapping.get('version')}")
    behavior = _behavior(definitions, behavior_id)
    game = run.get("game") or {}
    compatible = (
        _mapping_base_eligible(mapping, use="comparison")
        and str(mapping.get("version")) == str(metric.get("mapping_version"))
        and str(mapping.get("behavior_version")) == str(behavior.get("behavior_version"))
        and metric.get("behavior_version", mapping.get("behavior_version")) == mapping.get("behavior_version")
        and mapping.get("source_definition_id") == game.get("game_id")
        and str(mapping.get("source_definition_version")) == str(game.get("game_version"))
        and metric.get("source_definition_id", mapping.get("source_definition_id")) == mapping.get("source_definition_id")
        and str(metric.get("source_definition_version", mapping.get("source_definition_version"))) == str(mapping.get("source_definition_version"))
        and metric.get("unit") == "eligible_opportunity_ratio"
    )
    return compatible, refs


def _comparison(
    run: Mapping[str, Any], definitions: Mapping[str, Any], behavior_id: str, criteria: Mapping[str, Any]
) -> dict[str, Any]:
    metric = _metric_for(run, behavior_id)
    compatible, mapping_refs = _resource_mapping_compatible(run, definitions, behavior_id, metric)
    decision = compare_evidence(
        compatible=compatible,
        denominator=metric.get("denominator") if metric else None,
        numerator=metric.get("numerator") if metric else None,
        # Exact textual mention is not a direction-specific rule connecting a
        # self-report statement to a game observation.
        explicit_support=False,
        observation_difference=False,
        documented_context_difference=False,
        unresolved=any(item["status"] in {"partial", "not_mentioned", "unassessable"} for item in criteria.values()),
    )
    return {
        "mapping_status": (
            "incompatible" if not compatible else
            "mapped" if metric else
            "no_eligible_resource_game_evidence"
        ),
        "status": decision["status"], "reason": decision["reason"],
        "comparison_rule_version": decision["comparison_rule_version"],
        "mapping_refs": mapping_refs,
        "metric_refs": [metric.get("metric_id")] if metric and metric.get("metric_id") else [],
        "limitations": [
            "규칙 전환 게임 점수는 이 행동 비교에 사용하지 않습니다.",
            "자기보고 진술의 진실이나 안정된 성향을 인증하지 않습니다.",
        ],
    }


def _suggestions(criteria: Mapping[str, Any], answer: Mapping[str, Any]) -> list[dict[str, Any]]:
    suggestions = []
    for criterion in CRITERIA:
        item = criteria[criterion]
        if item["status"] in {"explicit", "not_asked"}:
            continue
        refs = [f"{answer['answer_id']}@{answer['answer_version']}"] if answer.get("answer_id") else []
        suggestions.append({
            "criterion": criterion, "text": _PRACTICE_TEXT[criterion],
            "template_version": PRACTICE_TEMPLATE_VERSION, "basis_refs": refs,
        })
    return suggestions


def _survey_report(run: Mapping[str, Any]) -> list[dict[str, Any]]:
    surveys = []
    for record in run.get("records", []):
        if isinstance(record, dict) and record.get("source_type") == "survey":
            item = deepcopy(record)
            # S-B02 has a context-only preference mapping; R has no behavior
            # mapping. Neither is eligible for direct behavior comparison.
            item["comparison_exclusion"] = {
                "S-B02": "context_only_preference",
                "R-UNMAPPED": "R-UNMAPPED",
            }.get(item.get("item_id"))
            surveys.append(item)
    return surveys


def _rule_games_report(run: Mapping[str, Any]) -> list[dict[str, Any]]:
    state = run.get("rule_games") or {}
    result = []
    for game in (state.get("games") or {}).values():
        if not isinstance(game, dict):
            continue
        rounds = []
        for item in game.get("rounds", []):
            if not isinstance(item, dict):
                continue
            rounds.append({
                "round_id": item.get("round_id"), "round_index": item.get("index"),
                "status": item.get("status"), "score": item.get("score"),
                "correct_count": item.get("correct_count"), "incorrect_count": item.get("incorrect_count"),
                "quality_flags": deepcopy(item.get("quality_flags") or []),
                "event_refs": [event.get("event_id") for event in item.get("events", []) if isinstance(event, dict) and event.get("event_id")],
            })
        result.append({
            "game_id": game.get("game_id"), "game_version": game.get("game_version"),
            "state_version": game.get("state_version", state.get("version")),
            "mapping_status": "unmapped", "comparison_status": "not_comparable", "rounds": rounds,
            "limitations": ["라운드 점수는 규칙 게임 결과이며 합격·성향·행동 점수가 아닙니다."],
        })
    return result


def _build_report(prepared: Mapping[str, Any], outputs: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    run, definitions = prepared["_run"], prepared["_definitions"]
    questions = _question_list(run, definitions)
    answers = _latest_leaf_answers(run, questions)
    behaviors = {item.get("behavior_id"): item for item in definitions.get("behaviors", []) if isinstance(item, dict)}
    cards = []
    for question in questions:
        answer = answers[question["question_id"]]
        criteria = _server_criteria(question, answer, outputs.get(answer["answer_id"]))
        behavior = behaviors.get(question.get("behavior_id"), {})
        interview_mapping, _ = _interview_mapping(definitions, question, use="baseline_extraction")
        cards.append({
            "behavior_id": question.get("behavior_id"), "behavior_version": behavior.get("behavior_version"),
            "behavior_name": behavior.get("name"),
            "question_id": question["question_id"], "question_version": question["question_version"],
            "question_text": question["question_text"],
            "rubric_id": question.get("rubric_id"), "rubric_version": question.get("rubric_version"),
            "answer_id": answer["answer_id"], "answer_version": answer["answer_version"],
            "answer_status": answer["status"], "criteria": criteria,
            "comparison": _comparison(run, definitions, str(question.get("behavior_id")), criteria),
            "practice_suggestions": _suggestions(criteria, answer),
            "extraction_provenance": {
                "prompt_version": PROMPT_VERSION, "schema_version": SCHEMA_VERSION,
                "rubric_id": question.get("rubric_id"), "rubric_version": question.get("rubric_version"),
                "mapping_id": (interview_mapping or {}).get("mapping_id"),
                "mapping_version": (interview_mapping or {}).get("version"),
                "runtime_mode": prepared["runtime_mode"], "model_id": prepared["model_id"],
            },
        })
    report = {
        "report_id": str(uuid4()), "report_version": REPORT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "runtime_mode": prepared["runtime_mode"], "requested_mode": prepared["requested_mode"],
        "provider_execution": prepared["provider_execution"], "model_id": prepared["model_id"],
        "input_snapshot": deepcopy(prepared["input_snapshot"]),
        "limitations": [
            "면접 답변은 사용자의 자기보고이며 실제 사건을 외부 검증하지 않습니다.",
            "설문 강도와 규칙 게임 점수는 면접 의미 분석 입력에 사용하지 않았습니다.",
            "이 보고서는 합격, 성격, 거짓말 또는 채용 판단을 제공하지 않습니다.",
        ],
        "cards": cards, "surveys": _survey_report(run), "rule_games": _rule_games_report(run),
    }
    if run.get("flow_version") == "five-game-v2":
        from .five_game_reporting import build_five_game_report
        report["five_games"] = build_five_game_report(run)
    return report


def execute_analysis(prepared: Mapping[str, Any], *, before_call: Callable[[], Any] | None = None) -> dict[str, Any]:
    required = {
        "requested_mode", "runtime_mode", "provider_execution", "model_id", "input_snapshot",
        "calls_required", "cost_microusd", "max_calls_per_run", "max_cost_microusd",
        "max_input_tokens", "max_output_tokens", "timeout_ms", "max_retries", "_run", "_definitions", "_calls",
    }
    if not isinstance(prepared, Mapping) or not required.issubset(prepared):
        raise _error("prepared_invalid")
    outputs: dict[str, Mapping[str, Any]] = {}
    if prepared["requested_mode"] == "live":
        current = _live_config()
        guarded = (
            "model_id", "max_input_tokens", "max_output_tokens", "timeout_ms",
            "max_retries", "max_calls_per_run", "max_cost_microusd",
        )
        if (any(current[key] != prepared[key] for key in guarded)
                or current['provider'] != prepared.get('_provider', 'openai')
                or current['input_rate'] != prepared.get('_input_rate')
                or current['output_rate'] != prepared.get('_output_rate')
                or (_PROVIDER_TRANSPORT is not None) != (prepared.get('provider_execution') == 'test_double')):
            raise _error("configuration_changed")
        limits = BudgetLimits(
            max_input_tokens=prepared["max_input_tokens"],
            max_output_tokens=prepared["max_output_tokens"],
            max_timeout_ms=prepared["timeout_ms"],
            max_retries=0,
            max_calls_per_run=prepared["max_calls_per_run"],
        )
        provider_class = GeminiProvider if current['provider'] == 'gemini' else LiveProvider
        provider = provider_class(transport=_PROVIDER_TRANSPORT, limits=limits, model_id=prepared["model_id"])
        for call in prepared["_calls"]:
            if before_call is not None:
                before_call()
            output = provider.generate(
                call["structured_input"], input_tokens=call["input_tokens"],
                output_tokens=prepared["max_output_tokens"], timeout_ms=prepared["timeout_ms"],
                retries=0, calls_per_run=prepared["calls_required"],
                estimated_cost=prepared["cost_microusd"] / 1_000_000,
                output_schema=_output_schema(),
            )
            if current['provider'] == 'gemini':
                output = _resolve_gemini_quote_offsets(output, call['answer']['text'])
            # Validate immediately; no partial report may escape.
            _server_criteria(call["question"], call["answer"], output)
            outputs[call["answer"]["answer_id"]] = output
    report = _build_report(prepared, outputs)
    return {
        "runtime_mode": prepared["runtime_mode"], "requested_mode": prepared["requested_mode"],
        "provider_execution": prepared["provider_execution"], "model_id": prepared["model_id"],
        "input_snapshot": deepcopy(prepared["input_snapshot"]), "report": report,
    }
