from __future__ import annotations

from copy import deepcopy
import json

import pytest

from app.ai_provider import ProviderError
from app.content import DEFINITIONS


CRITERIA = ("situation", "role", "other_information", "action", "reasoning", "result", "learning")


def _record(question, *, answer_id, version, status, text, previous=None, order=1):
    return {
        "record_id": f"record-{answer_id}",
        "record_version": 1,
        "source_type": "typed_answer",
        "source_version": version,
        "status": "submitted",
        "item_id": question["question_id"],
        "item_version": question["question_version"],
        "presentation_order": order,
        "data": {
            "answer_id": answer_id,
            "answer_version": version,
            "previous_answer_version_ref": previous,
            "question_id": question["question_id"],
            "question_version": question["question_version"],
            "question_text_snapshot": question["question_text"],
            "behavior_id": question["behavior_id"],
            "status": status,
            "text": text,
        },
    }


def sample_run():
    questions = DEFINITIONS["questions"]
    old = _record(
        questions[0], answer_id="answer-old", version="1.0.0",
        status="asked_answered", text="오래된 답변", order=1,
    )
    current_text = "🙂 팀원에게 일정과 제약을 물었습니다. 그 답을 계획에 반영했습니다."
    current = _record(
        questions[0], answer_id="answer-current", version="2.0.0",
        status="asked_answered", text=current_text,
        previous={"answer_id": "answer-old", "answer_version": "1.0.0"}, order=4,
    )
    empty = _record(
        questions[1], answer_id="answer-empty", version="1.0.0",
        status="asked_no_text", text="", order=2,
    )
    skipped = _record(
        questions[2], answer_id="answer-skipped", version="1.0.0",
        status="skipped", text="", order=3,
    )
    survey = {
        "record_id": "survey-1", "record_version": 1, "source_type": "survey",
        "source_version": "1.0.0", "status": "submitted", "item_id": "S-B01",
        "item_version": "1.0.0", "presentation_order": 1,
        "data": {"response_type": "ordinal_6", "selected_option_id": "agree-6",
                 "selected_label_snapshot": "매우 그렇다", "selected_position": 6},
    }
    return {
        "run_id": "run-1", "user_id": "user-1", "attempt_id": "attempt-1",
        "generation": 7, "revision": 19, "status": "in_progress",
        "questions": deepcopy(questions),
        "records": [survey, old, empty, skipped, current],
        "game": {"game_id": "resource-bridge", "game_version": "1.0.0", "state_version": 3, "rounds": []},
        "rule_games": {
            "version": "1.0.0", "mapping_status": "unmapped",
            "games": {
                "rsp": {"game_id": "rule-rsp", "game_version": "1.0.0", "rounds": [{
                    "round_id": "rsp-round-1", "index": 1, "status": "completed", "score": 10,
                    "correct_count": 1, "incorrect_count": 0, "quality_flags": [],
                    "stimulus": {"opponent_hand": "rock"},
                    "events": [{"event_id": "event-1", "type": "round_started"}],
                }]},
                "card": {"game_id": "rule-card", "game_version": "1.0.0", "rounds": []},
            },
        },
    }


def _configure_live(monkeypatch):
    values = {
        "AI_PROVIDER_KEY": "synthetic-key-not-live",
        "AI_MODEL_ID": "synthetic-model",
        "AI_ALLOWED_MODEL_IDS": "synthetic-model",
        "AI_LIVE_ENABLED": "true",
        "PAID_AI_ENABLED": "true",
        "AI_MAX_INPUT_TOKENS": "20000",
        "AI_MAX_OUTPUT_TOKENS": "1200",
        "AI_TIMEOUT_MS": "5000",
        "AI_MAX_RETRIES": "0",
        "AI_MAX_CALLS_PER_RUN": "3",
        "AI_MAX_COST_MICROUSD": "100000",
        "AI_INPUT_RATE_MICROUSD_PER_MILLION_TOKENS": "2000000",
        "AI_OUTPUT_RATE_MICROUSD_PER_MILLION_TOKENS": "8000000",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def _model_result(text, question):
    start = text.index("팀원")
    end = text.index(".", start)
    asked = set(question["asked_criteria"])
    return {
        "criteria": [
            {
                "criterion": criterion,
                "status": "explicit" if criterion == "action" else "not_mentioned" if criterion in asked else "not_asked",
                "evidence_spans": [{"start": start, "end": end, "quote": text[start:end]}] if criterion == "action" else [],
            }
            for criterion in CRITERIA
        ]
    }


def test_mock_builds_grounded_unified_report_without_provider_call(monkeypatch):
    import app.interview_analysis as subject

    monkeypatch.setattr(subject, "_PROVIDER_TRANSPORT", lambda *args, **kwargs: pytest.fail("provider called"))
    prepared = subject.prepare_analysis(sample_run(), DEFINITIONS, "mock")
    result = subject.execute_analysis(prepared)

    assert prepared["calls_required"] == prepared["cost_microusd"] == 0
    assert result["runtime_mode"] == "mock"
    assert result["provider_execution"] == "not_called"
    assert set(result) == {"runtime_mode", "requested_mode", "provider_execution", "model_id", "input_snapshot", "report"}
    report = result["report"]
    assert [card["behavior_id"] for card in report["cards"]] == ["B01", "B02", "B03"]
    assert report["cards"][0]["answer_id"] == "answer-current"
    assert report["cards"][1]["answer_status"] == "asked_no_text"
    assert report["cards"][1]["criteria"]["other_information"]["status"] == "not_asked"
    assert report["surveys"][0]["data"]["selected_label_snapshot"] == "매우 그렇다"
    assert report["rule_games"][0]["mapping_status"] == "unmapped"
    assert report["rule_games"][0]["comparison_status"] == "not_comparable"
    assert "stimulus" not in report["rule_games"][0]["rounds"][0]
    assert report["rule_games"][0]["rounds"][0]["event_refs"] == ["event-1"]


def test_input_snapshot_uses_latest_leaf_and_version_lineage_only():
    from app.interview_analysis import input_snapshot

    snapshot = input_snapshot(sample_run(), DEFINITIONS)
    assert snapshot["generation"] == 7
    assert snapshot["definitions_version"] == "1.0.0"
    assert snapshot["answer_refs"][0] == {
        "answer_id": "answer-current", "answer_version": "2.0.0",
        "question_id": "baseline-b01", "question_version": "1.0.0", "status": "asked_answered",
    }
    assert all(ref["answer_id"] != "answer-old" for ref in snapshot["answer_refs"])
    assert snapshot["survey_record_refs"] == [{
        "record_id": "survey-1", "record_version": 1, "source_version": "1.0.0", "status": "submitted",
    }]
    assert snapshot["resource_game"] == {"game_id": "resource-bridge", "game_version": "1.0.0", "state_version": 3}


@pytest.mark.parametrize("item_id,response,exclusion", [
    ("S-B02", {"final_value": -3, "interaction_occurred": True,
               "explicit_confirmation": True, "change_count": 1}, "context_only_preference"),
    ("R-UNMAPPED", {"selected_ids": ["growth", "helping", "autonomy"],
                    "selection_events": []}, "R-UNMAPPED"),
    ("O-B02", {"selected_position": 5}, None),
])
def test_survey_exclusion_distinguishes_context_preference_from_unmapped(item_id, response, exclusion, monkeypatch):
    import app.interview_analysis as subject
    from app.survey import build_survey_record

    run = sample_run()
    definition = next(item for item in DEFINITIONS["surveys"] if item["item_id"] == item_id)
    record = build_survey_record(
        definition=definition, user_id=run["user_id"], run_id=run["run_id"],
        attempt_id=run["attempt_id"], presentation_order=1, response=response,
        status="submitted", elapsed_ms=1000,
    )
    run["records"][0] = record
    before = deepcopy(run)
    monkeypatch.setattr(subject, "_PROVIDER_TRANSPORT", lambda *a, **kw: pytest.fail("provider called"))
    result = subject.execute_analysis(subject.prepare_analysis(run, DEFINITIONS, "mock"))
    displayed = result["report"]["surveys"][0]

    assert displayed["comparison_exclusion"] == exclusion
    assert {key: value for key, value in displayed.items() if key != "comparison_exclusion"} == record
    assert run == before
    assert result["provider_execution"] == "not_called"
    assert all(game["mapping_status"] == "unmapped" for game in result["report"]["rule_games"])


def test_live_sends_only_allowlisted_current_nonblank_interview_input(monkeypatch):
    import app.interview_analysis as subject

    _configure_live(monkeypatch)
    seen = []

    def transport(endpoint, payload, **kwargs):
        structured = json.loads(payload["input"][0]["content"][0]["text"])
        seen.append(structured)
        text = structured["answer"]["text"]
        question = structured["question"]
        return {"status": "completed", "output_text": json.dumps(_model_result(text, question), ensure_ascii=False)}

    monkeypatch.setattr(subject, "_PROVIDER_TRANSPORT", transport)
    prepared = subject.prepare_analysis(sample_run(), DEFINITIONS, "live")
    callbacks = []
    result = subject.execute_analysis(prepared, before_call=lambda: callbacks.append("reserved"))

    assert prepared["calls_required"] == 1
    assert 0 < prepared["cost_microusd"] <= prepared["max_cost_microusd"]
    assert callbacks == ["reserved"]
    assert result["requested_mode"] == "live"
    assert result["runtime_mode"] == "mock"
    assert result["provider_execution"] == "test_double"
    assert len(seen) == 1
    assert set(seen[0]) == {"question", "answer", "behavior", "rubric"}
    assert set(seen[0]["question"]) == {"question_id", "question_version", "question_text", "asked_criteria", "rubric_id", "rubric_version"}
    assert set(seen[0]["answer"]) == {"answer_id", "answer_version", "status", "text"}
    serialized = json.dumps(seen, ensure_ascii=False)
    assert "매우 그렇다" not in serialized and "rule-rsp" not in serialized and "오래된 답변" not in serialized
    criterion = result["report"]["cards"][0]["criteria"]["action"]
    span = criterion["evidence_spans"][0]
    assert span["quote"] == sample_run()["records"][-1]["data"]["text"][span["start"]:span["end"]]
    assert span["source_id"] == "answer-current"
    assert span["offset_unit"] == "unicode_code_point"


def test_live_fails_closed_before_callback_when_config_is_incomplete(monkeypatch):
    import app.interview_analysis as subject

    for key in list(subject.LIVE_CONFIG_KEYS):
        monkeypatch.delenv(key, raising=False)
    called = []
    with pytest.raises(ProviderError, match="live_not_configured"):
        subject.prepare_analysis(sample_run(), DEFINITIONS, "live")
    assert called == []


def test_live_requires_nonblank_answer_and_all_baseline_leaf_states(monkeypatch):
    import app.interview_analysis as subject

    _configure_live(monkeypatch)
    run = sample_run()
    run["records"] = [record for record in run["records"] if record.get("item_id") != "baseline-b03"]
    with pytest.raises(ProviderError, match="baseline_answers_incomplete"):
        subject.prepare_analysis(run, DEFINITIONS, "live")
    run = sample_run()
    for record in run["records"]:
        if record.get("source_type") == "typed_answer":
            record["data"]["status"] = "asked_no_text"
            record["data"]["text"] = ""
    with pytest.raises(ProviderError, match="live_answer_required"):
        subject.prepare_analysis(run, DEFINITIONS, "live")


@pytest.mark.parametrize("mutation", ["wrong_quote", "wrong_offset", "model_provenance", "personality_field"])
def test_live_rejects_unbound_or_forbidden_model_output(monkeypatch, mutation):
    import app.interview_analysis as subject

    _configure_live(monkeypatch)

    def transport(endpoint, payload, **kwargs):
        structured = json.loads(payload["input"][0]["content"][0]["text"])
        output = _model_result(structured["answer"]["text"], structured["question"])
        span = output["criteria"][3]["evidence_spans"][0]
        if mutation == "wrong_quote":
            span["quote"] = "다른 문구"
        elif mutation == "wrong_offset":
            span["end"] += 1
        elif mutation == "model_provenance":
            span["source_id"] = "foreign-answer"
        else:
            output["personality_score"] = 99
        return {"status": "completed", "output_text": json.dumps(output, ensure_ascii=False)}

    monkeypatch.setattr(subject, "_PROVIDER_TRANSPORT", transport)
    prepared = subject.prepare_analysis(sample_run(), DEFINITIONS, "live")
    with pytest.raises(ProviderError, match="provider_schema_invalid|citation_invalid"):
        subject.execute_analysis(prepared)


def test_capabilities_never_returns_key_and_reports_finite_limits(monkeypatch):
    from app.interview_analysis import analysis_capabilities

    _configure_live(monkeypatch)
    result = analysis_capabilities()
    assert result == {
        "live_available": True,
        "reason": "available",
        "model_id": "synthetic-model",
        "max_calls_per_run": 3,
        "max_cost_microusd": 100000,
    }
    assert "synthetic-key-not-live" not in repr(result)


def test_budget_counts_full_instructions_schema_and_callback_precedes_transport(monkeypatch):
    import app.interview_analysis as subject

    _configure_live(monkeypatch)
    transported = []
    monkeypatch.setattr(subject, "_PROVIDER_TRANSPORT", lambda *args, **kwargs: transported.append(1))
    prepared = subject.prepare_analysis(sample_run(), DEFINITIONS, "live")
    raw_answer_bytes = len(sample_run()["records"][-1]["data"]["text"].encode("utf-8"))
    assert prepared["_calls"][0]["input_tokens"] > raw_answer_bytes

    with pytest.raises(RuntimeError, match="reservation failed"):
        subject.execute_analysis(
            prepared,
            before_call=lambda: (_ for _ in ()).throw(RuntimeError("reservation failed")),
        )
    assert transported == []


def test_existing_resource_game_metric_is_used_for_comparison():
    from app.interview_analysis import execute_analysis, prepare_analysis

    run = sample_run()
    run["game"]["metrics"] = [{
        "metric_id": "metric-b01", "behavior_id": "B01", "behavior_version": "1.0.0",
        "mapping_id": "map-game-b01", "mapping_version": "1.0.0",
        "source_definition_id": "resource-bridge", "source_definition_version": "1.0.0",
        "numerator": 2, "denominator": 3, "unit": "eligible_opportunity_ratio",
        "included_opportunity_ids": ["opp-1", "opp-2", "opp-3"],
        "excluded_opportunities_with_reasons": [], "algorithm_version": "game-aggregation-1.0.0",
    }]
    comparison = execute_analysis(prepare_analysis(run, DEFINITIONS, "mock"))["report"]["cards"][0]["comparison"]
    assert comparison["mapping_status"] == "mapped"
    assert comparison["metric_refs"] == ["metric-b01"]
    assert comparison["status"] != "insufficient_evidence"


def test_explicit_interview_text_does_not_claim_support_without_direction_rule(monkeypatch):
    import app.interview_analysis as subject

    _configure_live(monkeypatch)
    run = sample_run()
    run["game"]["metrics"] = [{
        "metric_id": "metric-b01-zero", "behavior_id": "B01", "behavior_version": "1.0.0",
        "mapping_id": "map-game-b01", "mapping_version": "1.0.0",
        "source_definition_id": "resource-bridge", "source_definition_version": "1.0.0",
        "numerator": 0, "denominator": 3, "unit": "eligible_opportunity_ratio",
        "included_opportunity_ids": ["opp-1", "opp-2", "opp-3"],
        "excluded_opportunities_with_reasons": [], "algorithm_version": "game-aggregation-1.0.0",
    }]

    def transport(endpoint, payload, **kwargs):
        structured = json.loads(payload["input"][0]["content"][0]["text"])
        text = structured["answer"]["text"]
        quote = text[:1]
        output = {
            "criteria": [
                {"criterion": criterion, "status": "explicit", "evidence_spans": [{"start": 0, "end": 1, "quote": quote}]}
                for criterion in CRITERIA
            ]
        }
        return {"status": "completed", "output_text": json.dumps(output, ensure_ascii=False)}

    monkeypatch.setattr(subject, "_PROVIDER_TRANSPORT", transport)
    comparison = subject.execute_analysis(subject.prepare_analysis(run, DEFINITIONS, "live"))["report"]["cards"][0]["comparison"]
    assert comparison["status"] == "needs_clarification"
    assert comparison["reason"] == "evidence_direction_not_resolved"


@pytest.mark.parametrize(
    ("legacy_budget", "estimated_cost"),
    [("NaN", 0.0), ("Infinity", 0.0), ("1.0", float("nan")), ("1.0", float("inf"))],
)
def test_provider_rejects_nonfinite_costs_before_transport(monkeypatch, legacy_budget, estimated_cost):
    from app.ai_provider import BudgetLimits, LiveProvider

    monkeypatch.setenv("AI_PROVIDER_KEY", "synthetic-key-not-live")
    monkeypatch.setenv("AI_MODEL_ID", "synthetic-model")
    monkeypatch.setenv("AI_ALLOWED_MODEL_IDS", "synthetic-model")
    monkeypatch.setenv("AI_LIVE_ENABLED", "true")
    monkeypatch.setenv("PAID_AI_ENABLED", "true")
    monkeypatch.delenv("AI_MAX_COST_MICROUSD", raising=False)
    monkeypatch.setenv("AI_MAX_COST_PER_RUN", legacy_budget)
    calls = []
    provider = LiveProvider(
        transport=lambda *args, **kwargs: calls.append(1),
        limits=BudgetLimits(), model_id="synthetic-model",
    )
    with pytest.raises(ProviderError, match="cost_budget_unknown"):
        provider.generate(
            {}, input_tokens=0, output_tokens=0, timeout_ms=0, retries=0,
            calls_per_run=1, estimated_cost=estimated_cost,
        )
    assert calls == []


def test_live_rejects_unapproved_interview_mapping_or_rubric_drift(monkeypatch):
    import app.interview_analysis as subject

    _configure_live(monkeypatch)
    for mutation, expected in (
        ("retired", "interview_mapping_ineligible"),
        ("incomplete", "interview_mapping_ineligible"),
        ("rubric", "rubric_version_incompatible"),
    ):
        definitions = deepcopy(DEFINITIONS)
        run = sample_run()
        if mutation == "retired":
            mapping = next(item for item in definitions["mappings"] if item["mapping_id"] == "map-interview-b01")
            mapping["practice_review_status"] = "retired"
        elif mutation == "incomplete":
            mapping = next(item for item in definitions["mappings"] if item["mapping_id"] == "map-interview-b01")
            mapping.pop("reason")
        else:
            run["questions"][0]["rubric_version"] = "999"
        with pytest.raises(ProviderError, match=expected):
            subject.prepare_analysis(run, definitions, "live")


@pytest.mark.parametrize("field", ["mapping_id", "mapping_version", "behavior_version", "source_definition_version", "unit"])
def test_game_metric_identity_mismatch_is_not_comparable(field):
    from app.interview_analysis import execute_analysis, prepare_analysis

    run = sample_run()
    metric = {
        "metric_id": "metric-b01", "behavior_id": "B01", "behavior_version": "1.0.0",
        "mapping_id": "map-game-b01", "mapping_version": "1.0.0",
        "source_definition_id": "resource-bridge", "source_definition_version": "1.0.0",
        "numerator": 1, "denominator": 3, "unit": "eligible_opportunity_ratio",
        "included_opportunity_ids": ["opp-1", "opp-2", "opp-3"],
        "excluded_opportunities_with_reasons": [], "algorithm_version": "game-aggregation-1.0.0",
    }
    metric[field] = "wrong"
    run["game"]["metrics"] = [metric]
    comparison = execute_analysis(prepare_analysis(run, DEFINITIONS, "mock"))["report"]["cards"][0]["comparison"]
    assert comparison["mapping_status"] == "incompatible"
    assert comparison["status"] == "not_comparable"


def test_invalid_interview_mapping_is_not_comparable_without_game_metric():
    from app.interview_analysis import execute_analysis, prepare_analysis

    definitions = deepcopy(DEFINITIONS)
    mapping = next(item for item in definitions["mappings"] if item["mapping_id"] == "map-interview-b01")
    mapping["permitted_uses"] = ["original_response_report"]
    comparison = execute_analysis(prepare_analysis(sample_run(), definitions, "mock"))["report"]["cards"][0]["comparison"]
    assert comparison["mapping_status"] == "incompatible"
    assert comparison["status"] == "not_comparable"


def test_card_records_exact_extraction_provenance():
    import app.interview_analysis as subject

    card = subject.execute_analysis(subject.prepare_analysis(sample_run(), DEFINITIONS, "mock"))["report"]["cards"][0]
    assert card["behavior_version"] == "1.0.0"
    assert card["rubric_id"] == "rubric-b01"
    assert card["rubric_version"] == "1.0.0"
    assert card["extraction_provenance"] == {
        "prompt_version": subject.PROMPT_VERSION,
        "schema_version": subject.SCHEMA_VERSION,
        "rubric_id": "rubric-b01",
        "rubric_version": "1.0.0",
        "mapping_id": "map-interview-b01",
        "mapping_version": "1.0.0",
        "runtime_mode": "mock",
        "model_id": None,
    }


@pytest.mark.parametrize("span_kind", ["empty", "whitespace", "too_many", "too_long"])
def test_live_rejects_semantically_empty_or_oversized_explicit_spans(monkeypatch, span_kind):
    import app.interview_analysis as subject

    _configure_live(monkeypatch)

    def transport(endpoint, payload, **kwargs):
        structured = json.loads(payload["input"][0]["content"][0]["text"])
        output = _model_result(structured["answer"]["text"], structured["question"])
        item = output["criteria"][3]
        if span_kind == "empty":
            item["evidence_spans"] = [{"start": 0, "end": 0, "quote": ""}]
        elif span_kind == "whitespace":
            item["evidence_spans"] = [{"start": 1, "end": 2, "quote": " "}]
        elif span_kind == "too_many":
            item["evidence_spans"] = item["evidence_spans"] * 3
        else:
            text = "가" * 401
            structured["answer"]["text"] = text
            item["evidence_spans"] = [{"start": 0, "end": 401, "quote": text}]
        return {"status": "completed", "output_text": json.dumps(output, ensure_ascii=False)}

    monkeypatch.setattr(subject, "_PROVIDER_TRANSPORT", transport)
    with pytest.raises(ProviderError, match="provider_schema_invalid|citation_invalid"):
        subject.execute_analysis(subject.prepare_analysis(sample_run(), DEFINITIONS, "live"))
