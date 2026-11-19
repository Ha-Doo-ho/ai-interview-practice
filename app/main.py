from __future__ import annotations

import copy
import importlib
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .content import DEFINITIONS
from .game import GameValidation, apply_game_action
from .rule_games import RULE_GAME_DEFINITIONS, apply_rule_game_action, server_time, surveys_visited, validate_action_body
from .store import Conflict, Deleted, Finalized, InvalidCredentials, NotFound, Store, StoreError, Validation
from .survey import SurveyValidation, build_survey_record


COOKIE_NAME = "interview_session"
CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "interview-app"


def _require_no_aptitude_active(snapshot: dict) -> None:
    if any(a.get('status') == 'active' for a in snapshot.get('aptitude_games', {}).get('attempts', [])):
        raise Conflict('aptitude_active')


def _require_five_games(snapshot: dict) -> None:
    if snapshot.get("flow_version") != "five-game-v2":
        return
    rules = snapshot.get("rule_games", {}).get("games", {})
    if any(len(rules.get(kind, {}).get("rounds", [])) != 3 or
           any(r.get("status") != "completed" for r in rules[kind]["rounds"])
           for kind in ("rsp", "card")):
        raise Conflict("game_order_required")
    games = snapshot.get("appointment_games", {}).get("games", [])
    if ([g.get("type") for g in games] != ["day", "place", "bus"] or
            any(g.get("status") != "complete" or len(g.get("questions", [])) != 10 for g in games)):
        raise Conflict("game_order_required")


def _error_status(code: str) -> int:
    if code.startswith('aptitude_'):
        return 409
    if code in {
        "idempotency_conflict",
        "current_user_changed",
        "revision_conflict",
        "stale_after_finalize",
        "invalid_state",
        "record_already_submitted",
        "answer_version_conflict",
        "analysis_required",
        "baseline_answers_required",
        "survey_responses_required",
        "game_completion_required",
        "main_round_completion_required",
        "baseline_derivation_changed",
        "rule_game_active_round",
        "rule_game_round_limit",
        "rule_game_invalid_state",
        "rule_game_stale_round",
        "rule_game_stale_stimulus",
        "rule_game_duplicate_choice",
        "rule_game_reveal_too_early",
        "rule_game_reveal_required",
        "rule_game_finish_too_early",
        "rule_game_round_expired",
        "analysis_request_running",
        "analysis_request_failed",
        "baseline_answers_incomplete",
        "live_answer_required",
        "interview_analysis_required",
        "interview_report_stale",
        "evidence_linkage_required",
        "evidence_linkage_stale",
        "game_order_required",
        "appointment_invalid_sequence",
        "appointment_already_configured",
        "appointment_difficulty_required",
        "appointment_stale_question",
        "appointment_invalid_state",
        "appointment_already_settled",
        "appointment_invalid_phase",
    }:
        return 409
    if code in {"unauthorized", "invalid_credentials"}:
        return 401
    if code == "not_found":
        return 404
    if code == "cancelled_after_deletion":
        return 410
    if code == "username_taken":
        return 409
    return 422


def _public_snapshot(snapshot: dict, *, definition: bool = False) -> dict:
    """Filter response copies only; retain full immutable server evidence.

    Replay responses use their own recorded reveal state, not the latest run.
    Definitions are public and cannot authorize disclosure for any round.
    """
    public = copy.deepcopy(snapshot)
    if isinstance(public.get('aptitude_games'), dict):
        from .aptitude_games import public_state
        public['aptitude_games'] = public_state(public['aptitude_games'])
    if isinstance(public.get("appointment_games"), dict):
        from .appointment_game import public_appointment_state
        public["appointment_games"] = public_appointment_state(public["appointment_games"])
    for game in public.get("rule_games", {}).get("games", {}).values():
        for round_state in game.get("rounds", []):
            if not round_state.get("revealed_at"):
                round_state.get("rule_snapshot", {}).pop("changed", None)
    interview_analysis = snapshot.get("interview_analysis")
    if isinstance(interview_analysis, dict) and isinstance(interview_analysis.get("input_snapshot"), dict):
        try:
            module = importlib.import_module("app.interview_analysis")
            current_input = module.input_snapshot(copy.deepcopy(snapshot), copy.deepcopy(DEFINITIONS))
            public["interview_report_stale"] = interview_analysis["input_snapshot"] != current_input
        except (ImportError, AttributeError, TypeError, ValueError):
            # A stored report whose lineage cannot be recomputed is unsafe to
            # present as current. This field contains no source content.
            public["interview_report_stale"] = True
    if isinstance(snapshot.get("game_analysis"), dict):
        try:
            module = importlib.import_module("app.five_game_ai")
            expected = module.prepare(copy.deepcopy(snapshot), "mock")["input_snapshot"]
            public["game_analysis_stale"] = snapshot["game_analysis"].get("input_snapshot") != expected
        except Exception:
            public["game_analysis_stale"] = True
    if isinstance(snapshot.get("synthesis_analysis"), dict):
        try:
            from .synthesis import build_prompt
            public['synthesis_analysis_stale'] = snapshot['synthesis_analysis']['input_snapshot']['source_digest'] != build_prompt(snapshot)['source_digest']
        except Exception:
            public['synthesis_analysis_stale'] = True
    if snapshot.get("evidence_linkage") is not None:
        try:
            module = importlib.import_module("app.evidence_linkage")
            public["evidence_linkage_stale"] = not module.linkage_is_current(
                copy.deepcopy(snapshot), copy.deepcopy(DEFINITIONS)
            )
        except (ImportError, AttributeError, TypeError, ValueError, StoreError):
            public["evidence_linkage_stale"] = True
    for round_state in public.get("game", {}).get("rounds", []):
        new_information = round_state.get("new_information", {})
        if definition or not new_information.get("revealed_at"):
            new_information.pop("text", None)
            new_information.pop("updated_requirements", None)
            round_state.pop("final_requirements", None)
            round_state.pop("reward_table_final", None)
    return public


def _analysis_input_snapshot(run_snapshot: dict) -> dict:
    """Content-free version lineage used to detect stale derivations."""
    return {
        "generation": run_snapshot["generation"],
        "record_refs": [
            {
                "record_id": record.get("record_id"),
                "record_version": record.get("record_version"),
                "source_type": record.get("source_type"),
                "source_version": record.get("source_version"),
                "status": record.get("status"),
            }
            for record in run_snapshot.get("records", [])
            if not (record.get("source_type") == "typed_answer"
                    and record.get("data", {}).get("question_mode") == "supplemental")
        ],
        "game_state_version": run_snapshot.get("game", {}).get("state_version"),
        "definitions_version": DEFINITIONS["version"],
    }


def _reuse_immutable_baseline(previous: dict, current: dict) -> None:
    immutable_keys = (
        "extraction_id",
        "version",
        "answer_id",
        "answer_version",
        "question_id",
        "question_version",
        "mode",
        "behavior_id",
        "criteria",
        "answer_evidence_spans",
    )
    prior_by_id = {
        item.get("extraction_id"): item
        for item in previous.get("extractions", [])
        if item.get("mode") == "baseline"
    }
    merged_baseline = []
    for item in current["extractions"]:
        if item.get("mode") != "baseline":
            continue
        prior = prior_by_id.get(item.get("extraction_id"))
        if prior is not None:
            if {key: prior.get(key) for key in immutable_keys} != {key: item.get(key) for key in immutable_keys}:
                raise Conflict("baseline_derivation_changed")
            merged_baseline.append(copy.deepcopy(prior))
        else:
            merged_baseline.append(item)
    conditioned = [item for item in current["extractions"] if item.get("mode") == "conditioned_followup"]
    current["extractions"] = merged_baseline + conditioned


def _preserve_presented_questions(run_snapshot: dict, result: dict) -> None:
    existing = {
        question["question_id"]: question
        for question in run_snapshot.get("questions", [])
        if question.get("question_mode") == "adaptive_followup"
    }
    result["questions"] = [copy.deepcopy(existing.get(question.get("question_id"), question)) for question in result["questions"]]
    existing_by_behavior = {question.get("behavior_id"): question for question in existing.values()}
    for card in result.get("report", {}).get("cards", []):
        question = existing_by_behavior.get(card.get("behavior_id"))
        if question is not None:
            card["open_question"] = question.get("question_text")


def _require_csrf(request: Request) -> None:
    if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise PermissionError("csrf_required")


def _body_common(body: dict) -> tuple[int, str]:
    expected = body.get("expected_revision")
    key = body.get("idempotency_key")
    if isinstance(expected, bool) or not isinstance(expected, int) or not isinstance(key, str):
        raise Validation("validation_error")
    if not key or len(key) > 128:
        raise Validation("validation_error")
    return expected, key


def _safe_analysis(result: object) -> dict:
    if not isinstance(result, dict):
        raise Validation("analysis_validation_error")
    required = {"extractions", "metrics", "comparisons", "questions", "report", "runtime_mode"}
    if not required.issubset(result):
        raise Validation("analysis_validation_error")
    if result["runtime_mode"] not in {"mock", "live"}:
        raise Validation("analysis_validation_error")
    if result["runtime_mode"] == "live" and os.getenv("PAID_AI_ENABLED", "false").lower() != "true":
        raise Validation("live_ai_disabled")
    if not all(isinstance(result[field], list) for field in ("extractions", "metrics", "comparisons", "questions")):
        raise Validation("analysis_validation_error")
    if not isinstance(result["report"], dict):
        raise Validation("analysis_validation_error")
    allowed_comparison = {"supports_statement", "contextual_difference", "needs_clarification", "insufficient_evidence", "not_comparable"}
    if any(item.get("status") not in allowed_comparison for item in result["comparisons"] if isinstance(item, dict)):
        raise Validation("analysis_validation_error")
    for question in result["questions"]:
        if not isinstance(question, dict) or question.get("question_mode") != "adaptive_followup" or question.get("conditioned_on_prior_evidence") is not True:
            raise Validation("analysis_validation_error")
    return copy.deepcopy(result)


_INTERVIEW_INPUT_ERRORS = {
    "mode_invalid",
    "live_not_configured",
    "live_disabled",
    "paid_ai_not_approved",
    "model_not_allowed",
    "config_invalid",
    "budget_exceeded",
    "provider_schema_invalid",
    "citation_invalid",
}


def _raise_interview_error(exc: Exception) -> None:
    if isinstance(exc, StoreError):
        raise exc
    code = str(exc).split(":", 1)[0]
    if code in {"baseline_answers_incomplete", "live_answer_required"}:
        raise Conflict(code) from None
    from .ai_provider import ProviderError

    if code in _INTERVIEW_INPUT_ERRORS or isinstance(exc, ProviderError):
        raise Validation(code) from None
    raise Validation("analysis_provider_error") from None


def _safe_interview_analysis(result: object, prepared: dict) -> dict:
    required = {
        "runtime_mode",
        "requested_mode",
        "provider_execution",
        "model_id",
        "input_snapshot",
        "report",
    }
    if not isinstance(result, dict) or set(result) != required:
        raise Validation("provider_schema_invalid")
    if result["requested_mode"] != prepared.get("requested_mode"):
        raise Validation("provider_schema_invalid")
    if result["runtime_mode"] not in {"mock", "live"}:
        raise Validation("provider_schema_invalid")
    if result["provider_execution"] not in {"provider_completed", "not_called", "test_double"}:
        raise Validation("provider_schema_invalid")
    if result["input_snapshot"] != prepared.get("input_snapshot") or not isinstance(result["report"], dict):
        raise Validation("provider_schema_invalid")
    if result["requested_mode"] == "mock" and (
        result["runtime_mode"] != "mock" or result["provider_execution"] != "not_called"
    ):
        raise Validation("provider_schema_invalid")
    if result["provider_execution"] == "provider_completed" and result["runtime_mode"] != "live":
        raise Validation("provider_schema_invalid")
    if result["provider_execution"] == "test_double" and result["runtime_mode"] != "mock":
        raise Validation("provider_schema_invalid")
    return copy.deepcopy(result)


def _current_baseline_answers(snapshot: dict) -> list[dict]:
    records = [
        record
        for record in snapshot.get("records", [])
        if record.get("source_type") == "typed_answer"
        and record.get("data", {}).get("question_mode") == "baseline"
    ]
    replaced_ids = {
        reference.get("answer_id")
        for record in records
        if isinstance((reference := record.get("data", {}).get("previous_answer_version_ref")), dict)
    }
    return [
        record
        for record in records
        if record.get("data", {}).get("answer_id") not in replaced_ids
    ]


def create_app(database_url: str | None = None) -> FastAPI:
    db_url = database_url or os.getenv("DATABASE_URL", "sqlite:///./interview.db")
    store = Store(db_url)
    application = FastAPI(title="AI interview practice", docs_url=None, redoc_url=None)
    application.state.store = store

    @application.exception_handler(PermissionError)
    async def permission_error(_request: Request, exc: PermissionError):
        return JSONResponse({"error": str(exc)}, status_code=403)

    @application.exception_handler(StoreError)
    async def store_error(_request: Request, exc: StoreError):
        code = str(exc) or "validation_error"
        return JSONResponse({"error": code}, status_code=_error_status(code))

    @application.exception_handler(SurveyValidation)
    @application.exception_handler(GameValidation)
    async def domain_error(_request: Request, exc: ValueError):
        # Early timeout remains public validation_error/422, like other game
        # input rejections. A domain reason is not a separate public contract.
        code = str(exc) if str(exc) in {"invalid_state", "validation_error"} else "validation_error"
        return JSONResponse({"error": code}, status_code=_error_status(code))

    def current_user(request: Request) -> dict:
        return store.resolve_session(request.cookies.get(COOKIE_NAME))

    async def json_body(request: Request) -> dict:
        try:
            body = await request.json()
        except Exception as exc:
            raise Validation("validation_error") from exc
        if not isinstance(body, dict):
            raise Validation("validation_error")
        return body

    def set_cookie(response: JSONResponse, token: str) -> None:
        response.set_cookie(
            COOKIE_NAME,
            token,
            httponly=True,
            secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
            samesite="strict",
            max_age=12 * 60 * 60,
            path="/",
        )

    def cache_derivations(user_id: str, run_snapshot: dict, result: dict) -> None:
        for extraction in result["extractions"]:
            namespace = "baseline_extraction" if extraction.get("mode") == "baseline" else "conditioned_extraction"
            cache_key = extraction.get("lineage", {}).get("cache_key") or f"{extraction.get('extraction_id')}@{extraction.get('version')}"
            store.put_cache(user_id, run_snapshot["run_id"], run_snapshot["attempt_id"], namespace, str(cache_key), {"extraction": extraction})
        if result.get("metrics"):
            store.put_cache(
                user_id,
                run_snapshot["run_id"],
                run_snapshot["attempt_id"],
                "baseline_game",
                f"{run_snapshot['game']['game_version']}:{run_snapshot['game']['algorithm_version']}",
                {"metrics": result["metrics"]},
            )

    @application.get("/api/definitions")
    async def definitions():
        return _public_snapshot(DEFINITIONS, definition=True)

    @application.post("/api/register", status_code=201)
    async def register(request: Request):
        _require_csrf(request)
        body = await json_body(request)
        if not isinstance(body.get("username"), str) or not isinstance(body.get("password"), str):
            raise Validation("validation_error")
        user = store.create_user(body["username"], body["password"])
        token = store.create_session(user["user_id"])
        response = JSONResponse(user, status_code=201)
        set_cookie(response, token)
        return response

    @application.post("/api/login")
    async def login(request: Request):
        _require_csrf(request)
        body = await json_body(request)
        if not isinstance(body.get("username"), str) or not isinstance(body.get("password"), str):
            raise InvalidCredentials("invalid_credentials")
        user = store.authenticate(body["username"], body["password"])
        token = store.create_session(user["user_id"])
        response = JSONResponse(user)
        set_cookie(response, token)
        return response

    @application.get("/api/me")
    async def me(request: Request):
        return current_user(request)

    @application.get("/api/interview-analysis-capabilities")
    async def interview_analysis_capabilities(request: Request):
        current_user(request)
        module = importlib.import_module("app.interview_analysis")
        try:
            capabilities = module.analysis_capabilities()
        except Exception as exc:
            _raise_interview_error(exc)
        public_keys = {
            "live_available",
            "reason",
            "model_id",
            "max_calls_per_run",
            "max_cost_microusd",
        }
        if not isinstance(capabilities, dict) or not public_keys.issubset(capabilities):
            raise Validation("config_invalid")
        return {key: copy.deepcopy(capabilities[key]) for key in public_keys}

    @application.post("/api/logout", status_code=204)
    async def logout(request: Request):
        _require_csrf(request)
        current_user(request)
        store.delete_session(request.cookies.get(COOKIE_NAME))
        response = Response(status_code=204)
        response.delete_cookie(COOKIE_NAME, path="/")
        return response

    @application.delete("/api/account", status_code=204)
    async def delete_account(request: Request):
        _require_csrf(request)
        user = current_user(request)
        store.delete_account(user["user_id"])
        response = Response(status_code=204)
        response.delete_cookie(COOKIE_NAME, path="/")
        return response

    @application.post("/api/runs", status_code=201)
    async def create_run(request: Request):
        _require_csrf(request)
        user = current_user(request)
        body = await json_body(request)
        if set(body) - {"idempotency_key", "expected_user_id", "flow_version"}:
            raise Validation("validation_error")
        if body.get("flow_version") not in (None, "five-game-v2"):
            raise Validation("validation_error")
        if "expected_user_id" in body and body["expected_user_id"] != user["user_id"]:
            raise Conflict("current_user_changed")
        if "idempotency_key" in body and body["idempotency_key"] is None:
            raise Validation("validation_error")
        return JSONResponse(_public_snapshot(store.create_run(user["user_id"], body.get("idempotency_key"), body.get("flow_version"))), status_code=201)

    @application.get("/api/runs")
    async def list_runs(request: Request):
        user = current_user(request)
        return {"runs": [_public_snapshot(run) for run in store.list_runs(user["user_id"])]}

    @application.get("/api/runs/{run_id}")
    async def get_run(run_id: str, request: Request):
        user = current_user(request)
        return _public_snapshot(store.get_run(user["user_id"], run_id))

    @application.get("/api/rule-game-definitions")
    async def rule_game_definitions():
        return copy.deepcopy(RULE_GAME_DEFINITIONS)

    @application.get("/api/runs/{run_id}/rule-games")
    async def get_rule_games(run_id: str, request: Request):
        user = current_user(request)
        return {
            "run": _public_snapshot(store.get_run(user["user_id"], run_id)),
            "server_time": server_time(),
        }

    @application.get('/api/aptitude-games/definitions')
    async def aptitude_definitions():
        from .aptitude_games import definitions
        return definitions()

    @application.get('/api/runs/{run_id}/aptitude-games')
    async def get_aptitude_games(run_id: str, request: Request):
        from .aptitude_games import _now
        user = current_user(request)
        return {'run': _public_snapshot(store.get_run(user['user_id'], run_id)), 'server_time_ms': _now()}

    @application.post('/api/runs/{run_id}/aptitude-games')
    async def aptitude_action(run_id: str, request: Request):
        from .aptitude_games import apply_action
        _require_csrf(request)
        user = current_user(request)
        body = await json_body(request)
        expected, key = _body_common(body)
        values = {k: v for k, v in body.items() if k not in {'expected_revision', 'idempotency_key'}}
        return _public_snapshot(store.mutate(user['user_id'], run_id, expected, 'aptitude_game', key, body,
                                             lambda snapshot: apply_action(snapshot, values)))

    @application.post("/api/runs/{run_id}/rule-games")
    async def rule_game_action(run_id: str, request: Request):
        _require_csrf(request)
        user = current_user(request)
        body = await json_body(request)
        expected, key = _body_common(body)
        validate_action_body(body)
        if body["action"] == "start":
            current = store.get_run(user["user_id"], run_id)
            survey_ids = {item["item_id"] for item in DEFINITIONS["surveys"]}
            if not surveys_visited(current, survey_ids):
                raise Conflict("survey_responses_required")

        def apply(snapshot: dict) -> None:
            if snapshot.get("flow_version") == "five-game-v2" and body["action"] == "start" and body["game_type"] == "card":
                rounds = snapshot.get("rule_games", {}).get("games", {}).get("rsp", {}).get("rounds", [])
                if len(rounds) != 3 or any(r.get("status") != "completed" for r in rounds):
                    raise Conflict("game_order_required")
            _require_no_aptitude_active(snapshot)
            apply_rule_game_action(snapshot, body)

        return _public_snapshot(store.mutate(user["user_id"], run_id, expected, "rule_game", key, body, apply))

    @application.get("/api/runs/{run_id}/appointment-games")
    async def get_appointment_games(run_id: str, request: Request):
        user = current_user(request)
        return {"run": _public_snapshot(store.get_run(user["user_id"], run_id)), "server_time": server_time()}

    @application.post("/api/runs/{run_id}/appointment-games")
    async def appointment_game_action(run_id: str, request: Request):
        from .appointment_game import apply_appointment_action
        _require_csrf(request)
        user = current_user(request)
        body = await json_body(request)
        expected, key = _body_common(body)
        def apply(snapshot: dict) -> None:
            if snapshot.get("flow_version") != "five-game-v2":
                raise Conflict("game_order_required")
            games = snapshot.get("rule_games", {}).get("games", {})
            for kind in ("rsp", "card"):
                rounds = games.get(kind, {}).get("rounds", [])
                if len(rounds) != 3 or any(r.get("status") != "completed" for r in rounds):
                    raise Conflict("game_order_required")
            _require_no_aptitude_active(snapshot)
            apply_appointment_action(snapshot, {k: v for k, v in body.items() if k not in {"expected_revision", "idempotency_key"}})
        return _public_snapshot(store.mutate(user["user_id"], run_id, expected, "appointment_game", key, body, apply))

    @application.delete("/api/runs/{run_id}", status_code=204)
    async def delete_run(run_id: str, request: Request):
        _require_csrf(request)
        user = current_user(request)
        store.delete_run(user["user_id"], run_id)
        return Response(status_code=204)

    @application.post("/api/runs/{run_id}/surveys")
    async def submit_survey(run_id: str, request: Request):
        _require_csrf(request)
        user = current_user(request)
        body = await json_body(request)
        expected, key = _body_common(body)
        definition = next((item for item in DEFINITIONS["surveys"] if item["item_id"] == body.get("item_id")), None)
        if definition is None or definition["item_version"] != body.get("item_version"):
            raise Validation("validation_error")

        def apply(snapshot: dict) -> None:
            if any(record.get("source_type") == "survey" and record.get("item_id") == definition["item_id"] for record in snapshot["records"]):
                raise Conflict("record_already_submitted")
            record = build_survey_record(
                definition=definition,
                user_id=user["user_id"],
                run_id=run_id,
                attempt_id=snapshot["attempt_id"],
                presentation_order=sum(1 for r in snapshot["records"] if r.get("source_type") == "survey") + 1,
                response=body.get("response"),
                status=body.get("status"),
                elapsed_ms=body.get("elapsed_ms"),
            )
            snapshot["records"].append(record)

        return _public_snapshot(store.mutate(user["user_id"], run_id, expected, "survey", key, body, apply))

    @application.post("/api/runs/{run_id}/game")
    async def game_action(run_id: str, request: Request):
        _require_csrf(request)
        user = current_user(request)
        body = await json_body(request)
        expected, key = _body_common(body)

        def apply(snapshot: dict) -> None:
            if snapshot.get("flow_version") == "five-game-v2":
                raise Conflict("game_order_required")
            apply_game_action(snapshot["game"], body.get("action"), personal=body.get("personal"), reason=body.get("reason"))

        return _public_snapshot(store.mutate(user["user_id"], run_id, expected, "game", key, body, apply))

    @application.post("/api/runs/{run_id}/supplemental-interview")
    async def add_supplemental_interview(run_id: str, request: Request):
        _require_csrf(request)
        user = current_user(request)
        body = await json_body(request)
        if set(body) != {"expected_revision", "idempotency_key"}:
            raise Validation("validation_error")
        expected, key = _body_common(body)
        from .supplemental_interview import add_questions
        return _public_snapshot(store.mutate(user["user_id"], run_id, expected,
            "supplemental_interview", key, body, add_questions))

    @application.post("/api/runs/{run_id}/answers")
    async def submit_answer(run_id: str, request: Request):
        _require_csrf(request)
        user = current_user(request)
        body = await json_body(request)
        expected, key = _body_common(body)
        answer_status = body.get("status", "asked_answered")
        if not isinstance(answer_status, str) or answer_status not in {"asked_answered", "asked_no_text", "skipped"}:
            raise Validation("validation_error")
        if answer_status == "asked_answered" and (not isinstance(body.get("text"), str) or not body["text"].strip()):
            raise Validation("validation_error")
        if answer_status != "asked_answered" and body.get("text") is not None and body.get("text") != "":
            raise Validation("validation_error")

        def apply(snapshot: dict) -> None:
            _require_five_games(snapshot)
            question = next((item for item in snapshot["questions"] if item["question_id"] == body.get("question_id")), None)
            if question is None:
                raise Validation("validation_error")
            existing_answers = [
                record for record in snapshot["records"]
                if record.get("source_type") == "typed_answer" and record.get("data", {}).get("question_id") == question["question_id"]
            ]
            replaces_id = body.get("replaces_answer_id")
            expected_answer_version = body.get("expected_answer_version")
            previous_ref = None
            answer_version = "1.0.0"
            if replaces_id is None:
                if existing_answers:
                    raise Conflict("record_already_submitted")
            else:
                previous = next((record for record in existing_answers if record.get("data", {}).get("answer_id") == replaces_id), None)
                if previous is None or expected_answer_version != previous.get("data", {}).get("answer_version"):
                    raise Conflict("answer_version_conflict")
                if any((record.get("data", {}).get("previous_answer_version_ref") or {}).get("answer_id") == replaces_id for record in existing_answers):
                    raise Conflict("answer_version_conflict")
                previous_ref = {"answer_id": replaces_id, "answer_version": expected_answer_version}
                try:
                    answer_version = f"{int(str(expected_answer_version).split('.', 1)[0]) + 1}.0.0"
                except (TypeError, ValueError) as exc:
                    raise Conflict("answer_version_conflict") from exc
            now = datetime.now(timezone.utc).isoformat()
            answer_id = str(uuid4())
            snapshot["records"].append(
                {
                    "record_id": str(uuid4()),
                    "record_version": "1.0.0",
                    "source_type": "typed_answer",
                    "source_version": answer_version,
                    "user_id": user["user_id"],
                    "run_id": run_id,
                    "attempt_id": snapshot["attempt_id"],
                    "item_id": None,
                    "item_version": None,
                    "instructions_version": question.get("question_prompt_version"),
                    "presentation_id": question["question_id"],
                    "presentation_order": sum(1 for r in snapshot["records"] if r.get("source_type") == "typed_answer") + 1,
                    "status": answer_status,
                    "started_at": None,
                    "completed_at": now,
                    "context": {"language": "ko-KR", "submitted_elapsed_ms": body.get("elapsed_ms")},
                    "quality_flags": [],
                    "data": {
                        "answer_id": answer_id,
                        "answer_version": answer_version,
                        "previous_answer_version_ref": previous_ref,
                        "question_id": question["question_id"],
                        "question_version": question["question_version"],
                        "question_text_snapshot": question["question_text"],
                        "parent_question_id": question.get("parent_question_id"),
                        "question_group": question.get("question_group"),
                        "behavior_id": question.get("behavior_id"),
                        "question_mode": question["question_mode"],
                        "conditioned_on_prior_evidence": question["conditioned_on_prior_evidence"],
                        "disclosed_prior_information": copy.deepcopy(question.get("disclosed_prior_information", [])),
                        "generated_from_evidence_refs": copy.deepcopy(question.get("generated_from_evidence_refs", [])),
                        "generation_provenance": copy.deepcopy(question.get("generation_provenance")),
                        "linkage_id": question.get("linkage_id"),
                        "source_report_id": question.get("source_report_id"),
                        "text": body.get("text") or "",
                        "status": answer_status,
                        "source_kind": "typed_self_report",
                        "media_id": None,
                        "asr_raw_transcript_id": None,
                        "corrected_transcript_id": None,
                    },
                }
            )

        return _public_snapshot(store.mutate(user["user_id"], run_id, expected, "answer", key, body, apply))

    @application.post("/api/runs/{run_id}/interview-analysis")
    async def create_interview_analysis(run_id: str, request: Request):
        _require_csrf(request)
        user = current_user(request)
        body = await json_body(request)
        if set(body) != {"expected_revision", "idempotency_key", "mode"}:
            raise Validation("validation_error")
        expected, key = _body_common(body)
        if body.get("mode") not in {"live", "mock"}:
            raise Validation("mode_invalid")

        replay = store.get_interview_analysis_replay(
            user["user_id"], run_id, key, body
        )
        if replay is not None:
            return _public_snapshot(replay)

        snapshot = store.get_run(user["user_id"], run_id)
        if snapshot["revision"] != expected:
            raise Conflict("revision_conflict")
        if snapshot["status"] == "completed":
            raise Finalized("stale_after_finalize")
        _require_five_games(snapshot)
        baseline_ids = {
            question["question_id"]
            for question in snapshot.get("questions", [])
            if question.get("question_mode") == "baseline"
        }
        current_answers = _current_baseline_answers(snapshot)
        visited_ids = {
            record.get("data", {}).get("question_id") for record in current_answers
        }
        if not baseline_ids.issubset(visited_ids):
            raise Conflict("baseline_answers_incomplete")
        if body["mode"] == "live" and not any(
            record.get("data", {}).get("status") == "asked_answered"
            and isinstance(record.get("data", {}).get("text"), str)
            and record["data"]["text"].strip()
            for record in current_answers
        ):
            raise Conflict("live_answer_required")
        module = importlib.import_module("app.interview_analysis")
        try:
            prepared = module.prepare_analysis(
                copy.deepcopy(snapshot), copy.deepcopy(DEFINITIONS), body["mode"]
            )
        except Exception as exc:
            _raise_interview_error(exc)
        budget_fields = (
            "calls_required",
            "cost_microusd",
            "max_calls_per_run",
            "max_cost_microusd",
        )
        if not isinstance(prepared, dict) or any(field not in prepared for field in budget_fields):
            raise Validation("config_invalid")
        reservation = store.reserve_interview_analysis(
            user["user_id"],
            run_id,
            snapshot["attempt_id"],
            expected,
            key,
            body,
            body["mode"],
            prepared["calls_required"],
            prepared["cost_microusd"],
            prepared["max_calls_per_run"],
            prepared["max_cost_microusd"],
        )
        if reservation["state"] == "replay":
            return _public_snapshot(reservation["response"])
        request_id = reservation["request_id"]

        def before_call() -> None:
            store.assert_interview_analysis_current(user["user_id"], request_id)

        try:
            result = await run_in_threadpool(
                module.execute_analysis, prepared, before_call=before_call
            )
            result = _safe_interview_analysis(result, prepared)
            updated = store.complete_interview_analysis(
                user["user_id"], request_id, result
            )
        except Exception as exc:
            store.fail_interview_analysis(user["user_id"], request_id, error_code=str(exc).split(':',1)[0])
            _raise_interview_error(exc)
        return _public_snapshot(updated)

    @application.get('/api/runs/{run_id}/synthesis-prompt')
    async def synthesis_prompt(run_id: str, request: Request):
        from .synthesis import build_prompt
        snapshot = store.get_run(current_user(request)['user_id'], run_id)
        frozen = (snapshot.get('report') or {}).get('synthesis_prompt')
        return frozen if snapshot['status'] == 'completed' and frozen else build_prompt(snapshot)

    @application.post('/api/runs/{run_id}/synthesis-analysis')
    async def create_synthesis_analysis(run_id: str, request: Request):
        from . import synthesis, five_game_ai
        _require_csrf(request)
        user = current_user(request)
        body = await json_body(request)
        if set(body) != {'expected_revision','idempotency_key','mode'} or body.get('mode') not in ('mock','live'):
            raise Validation('validation_error')
        expected, key = _body_common(body)
        tagged = {'operation':'synthesis-analysis','body':body}
        replay = store.get_interview_analysis_replay(user['user_id'],run_id,key,tagged)
        if replay is not None:
            return _public_snapshot(replay)
        snapshot = store.get_run(user['user_id'],run_id)
        if snapshot['revision'] != expected: raise Conflict('revision_conflict')
        if snapshot['status'] == 'completed': raise Finalized('stale_after_finalize')
        _require_no_aptitude_active(snapshot)
        _require_five_games(snapshot)
        try:
            # Existing baseline analysis and five required games must be current.
            five_game_ai.prepare(snapshot,'mock')
            prepared = synthesis.prepare(snapshot,body['mode'])
        except Exception as exc:
            _raise_interview_error(exc)
        reservation = store.reserve_interview_analysis(user['user_id'],run_id,snapshot['attempt_id'],expected,key,
            tagged,body['mode'],prepared['calls_required'],prepared['cost_microusd'],
            prepared['max_calls_per_run'],prepared['max_cost_microusd'])
        if reservation['state']=='replay':return _public_snapshot(reservation['response'])
        request_id=reservation['request_id']
        try:
            result=await run_in_threadpool(synthesis.execute,prepared,
                before_call=lambda:store.assert_interview_analysis_current(user['user_id'],request_id))
            result=_safe_interview_analysis(result,prepared)
            updated=store.complete_interview_analysis(user['user_id'],request_id,result,kind='synthesis')
        except Exception as exc:
            store.fail_interview_analysis(user['user_id'],request_id,error_code=str(exc).split(':',1)[0])
            _raise_interview_error(exc)
        return _public_snapshot(updated)

    @application.post("/api/runs/{run_id}/game-analysis")
    async def create_game_analysis(run_id: str, request: Request):
        from . import five_game_ai
        _require_csrf(request)
        user = current_user(request)
        body = await json_body(request)
        if set(body) != {"expected_revision", "idempotency_key", "mode"}:
            raise Validation("validation_error")
        expected, key = _body_common(body)
        if body.get("mode") not in {"mock", "live"}:
            raise Validation("mode_invalid")
        tagged = {"operation": "five-game-analysis", "body": body}
        replay = store.get_interview_analysis_replay(user["user_id"], run_id, key, tagged)
        if replay is not None:
            return _public_snapshot(replay)
        snapshot = store.get_run(user["user_id"], run_id)
        if snapshot["revision"] != expected:
            raise Conflict("revision_conflict")
        if snapshot["status"] == "completed":
            raise Finalized("stale_after_finalize")
        if snapshot.get("flow_version") != "five-game-v2":
            raise Conflict("game_order_required")
        _require_five_games(snapshot)
        try:
            prepared = five_game_ai.prepare(copy.deepcopy(snapshot), body["mode"])
        except Exception as exc:
            _raise_interview_error(exc)
        reservation = store.reserve_interview_analysis(
            user["user_id"], run_id, snapshot["attempt_id"], expected, key, tagged, body["mode"],
            prepared["calls_required"], prepared["cost_microusd"],
            prepared["max_calls_per_run"], prepared["max_cost_microusd"])
        if reservation["state"] == "replay":
            return _public_snapshot(reservation["response"])
        request_id = reservation["request_id"]
        try:
            result = await run_in_threadpool(
                five_game_ai.execute, prepared,
                before_call=lambda: store.assert_interview_analysis_current(user["user_id"], request_id))
            result = _safe_interview_analysis(result, prepared)
            updated = store.complete_interview_analysis(user["user_id"], request_id, result, kind="game")
        except Exception as exc:
            store.fail_interview_analysis(user["user_id"], request_id, error_code=str(exc).split(':',1)[0])
            _raise_interview_error(exc)
        return _public_snapshot(updated)

    @application.post("/api/runs/{run_id}/evidence-linkage")
    async def create_evidence_linkage(run_id: str, request: Request):
        _require_csrf(request)
        user = current_user(request)
        body = await json_body(request)
        if set(body) != {"expected_revision", "idempotency_key"}:
            raise Validation("validation_error")
        expected, key = _body_common(body)

        def apply(snapshot: dict) -> None:
            module = importlib.import_module("app.evidence_linkage")
            linkage = module.build_linkage(copy.deepcopy(snapshot), copy.deepcopy(DEFINITIONS))
            if not isinstance(linkage, dict) or not isinstance(linkage.get("questions"), list):
                raise Validation("evidence_linkage_invalid")
            previous = snapshot.get("evidence_linkage")
            if previous is not None and previous != linkage:
                history = snapshot.setdefault("evidence_linkage_history", [])
                if previous not in history:
                    history.append(copy.deepcopy(previous))
            snapshot["evidence_linkage"] = copy.deepcopy(linkage)
            existing = {question["question_id"]: question for question in snapshot["questions"]}
            for question in linkage["questions"]:
                if question["question_id"] in existing:
                    # Already presented wording and disclosures stay immutable.
                    continue
                snapshot["questions"].append(copy.deepcopy(question))
                existing[question["question_id"]] = question

        return _public_snapshot(store.mutate(user["user_id"], run_id, expected,
                                             "evidence_linkage", key, body, apply))

    @application.post("/api/runs/{run_id}/interview-finalize")
    async def finalize_interview(run_id: str, request: Request):
        _require_csrf(request)
        user = current_user(request)
        body = await json_body(request)
        if set(body) != {"expected_revision", "idempotency_key"}:
            raise Validation("validation_error")
        expected, key = _body_common(body)

        def apply(snapshot: dict) -> None:
            survey_ids = {item["item_id"] for item in DEFINITIONS["surveys"]}
            if not surveys_visited(snapshot, survey_ids):
                raise Conflict("survey_responses_required")
            games = snapshot.get("rule_games", {}).get("games", {})
            for game_type in ("rsp", "card"):
                rounds = games.get(game_type, {}).get("rounds", [])
                if len(rounds) != 3 or any(item.get("status") != "completed" for item in rounds):
                    raise Conflict("game_completion_required")
            if snapshot.get("flow_version") == "five-game-v2":
                games = snapshot.get("appointment_games", {}).get("games", [])
                if len(games) != 3 or any(g.get("status") != "complete" or len(g.get("questions", [])) != 10 for g in games):
                    raise Conflict("game_completion_required")
            baseline_ids = {q["question_id"] for q in snapshot["questions"]
                            if q.get("question_mode") == "baseline"}
            visited_ids = {r.get("data", {}).get("question_id") for r in _current_baseline_answers(snapshot)
                           if r.get("data", {}).get("status") in {"asked_answered", "asked_no_text", "skipped"}}
            if len(baseline_ids) != 3 or not baseline_ids.issubset(visited_ids):
                raise Conflict("baseline_answers_required")
            module = importlib.import_module("app.evidence_linkage")
            _require_no_aptitude_active(snapshot)
            report = module.finalize_report(copy.deepcopy(snapshot), copy.deepcopy(DEFINITIONS))
            from .synthesis import build_prompt
            report['synthesis_prompt'] = build_prompt(snapshot)
            synthesis_result = snapshot.get('synthesis_analysis')
            if synthesis_result and synthesis_result['input_snapshot']['source_digest'] == report['synthesis_prompt']['source_digest']:
                report['synthesis_analysis'] = copy.deepcopy(synthesis_result)
            if snapshot.get('aptitude_games'):
                from .aptitude_games import public_state
                report['aptitude_games'] = public_state(snapshot['aptitude_games'])
            if not isinstance(report, dict) or report.get("status") != "finalized":
                raise Validation("evidence_linkage_invalid")
            if snapshot.get("flow_version") != "five-game-v2":
                snapshot["interview_report"] = copy.deepcopy(report)
            snapshot["report"] = copy.deepcopy(report)
            snapshot["status"] = "completed"
            snapshot["completed_at"] = datetime.now(timezone.utc).isoformat()

        return _public_snapshot(store.mutate(user["user_id"], run_id, expected,
                                             "interview_finalize", key, body, apply))

    @application.post("/api/runs/{run_id}/analyze")
    async def analyze(run_id: str, request: Request):
        _require_csrf(request)
        user = current_user(request)
        body = await json_body(request)
        expected, key = _body_common(body)
        prior = store.get_idempotent_result(user["user_id"], run_id, "analyze", key, body)
        if prior is not None:
            return _public_snapshot(prior)
        snapshot = store.get_run(user["user_id"], run_id)
        if snapshot.get("flow_version") == "five-game-v2":
            raise Conflict("game_order_required")
        _require_no_aptitude_active(snapshot)
        if snapshot["revision"] != expected:
            raise Conflict("revision_conflict")
        if snapshot["status"] == "completed":
            raise Finalized("stale_after_finalize")
        if not any(
            round_state.get("practice_or_main") == "main" and round_state.get("status") == "completed"
            for round_state in snapshot["game"]["rounds"]
        ):
            raise Conflict("main_round_completion_required")
        job = store.begin_job(user["user_id"], run_id, snapshot["attempt_id"], expected, "analysis")
        try:
            analysis_module = importlib.import_module("app.analysis")
            result = _safe_analysis(analysis_module.analyze_run(copy.deepcopy(snapshot), copy.deepcopy(DEFINITIONS)))
            result["input_snapshot"] = _analysis_input_snapshot(snapshot)
            _preserve_presented_questions(snapshot, result)
            store.complete_job(user["user_id"], job["job_id"], result)
        except Exception:
            store.fail_job(user["user_id"], job["job_id"])
            raise

        def apply(run_snapshot: dict) -> None:
            run_snapshot["analysis"] = copy.deepcopy(result)
            run_snapshot["report_draft"] = copy.deepcopy(result["report"])
            existing = {question["question_id"] for question in run_snapshot["questions"]}
            for question in result["questions"]:
                if question["question_id"] not in existing:
                    run_snapshot["questions"].append(copy.deepcopy(question))
                    existing.add(question["question_id"])

        updated = store.mutate(user["user_id"], run_id, expected, "analyze", key, body, apply)
        cache_derivations(user["user_id"], snapshot, result)
        return _public_snapshot(updated)

    @application.post("/api/runs/{run_id}/finalize")
    async def finalize(run_id: str, request: Request):
        _require_csrf(request)
        user = current_user(request)
        body = await json_body(request)
        expected, key = _body_common(body)
        prior = store.get_idempotent_result(user["user_id"], run_id, "finalize", key, body)
        if prior is not None:
            return _public_snapshot(prior)
        snapshot = store.get_run(user["user_id"], run_id)
        _require_no_aptitude_active(snapshot)
        if snapshot.get("flow_version") == "five-game-v2":
            raise Conflict("game_order_required")
        if snapshot["revision"] != expected:
            raise Conflict("revision_conflict")
        if snapshot["status"] == "completed":
            raise Finalized("stale_after_finalize")
        if not snapshot.get("analysis") or not snapshot.get("report_draft"):
            raise Conflict("analysis_required")
        answered = {
            r.get("data", {}).get("question_id")
            for r in snapshot["records"]
            if r.get("source_type") == "typed_answer"
            and r.get("data", {}).get("status") in {"asked_answered", "asked_no_text", "skipped"}
        }
        baseline_ids = {q["question_id"] for q in snapshot["questions"] if q.get("question_mode") == "baseline"}
        if not baseline_ids.issubset(answered):
            raise Conflict("baseline_answers_required")
        # Completion means every required stage was visited, not that every
        # prompt was answered. Preserve explicit missingness as valid progress.
        survey_ids = {item["item_id"] for item in DEFINITIONS["surveys"]}
        recorded_surveys = {
            record.get("item_id")
            for record in snapshot["records"]
            if record.get("source_type") == "survey"
            and record.get("status") in {"submitted", "timed_out", "skipped"}
        }
        if not survey_ids.issubset(recorded_surveys):
            raise Conflict("survey_responses_required")
        game = snapshot["game"]
        if game["phase"] != "complete" or not game["rounds"] or any(
            round_state.get("status") != "completed" for round_state in game["rounds"]
        ):
            raise Conflict("game_completion_required")
        result = snapshot["analysis"]
        analysis_stale = result.get("input_snapshot") != _analysis_input_snapshot(snapshot)
        if analysis_stale:
            job = store.begin_job(user["user_id"], run_id, snapshot["attempt_id"], expected, "conditioned_analysis")
            try:
                analysis_module = importlib.import_module("app.analysis")
                result = _safe_analysis(analysis_module.analyze_run(copy.deepcopy(snapshot), copy.deepcopy(DEFINITIONS)))
                result["input_snapshot"] = _analysis_input_snapshot(snapshot)
                _reuse_immutable_baseline(snapshot["analysis"], result)
                _preserve_presented_questions(snapshot, result)
                store.complete_job(user["user_id"], job["job_id"], result)
            except Exception:
                store.fail_job(user["user_id"], job["job_id"])
                raise

        def apply(run_snapshot: dict) -> None:
            run_snapshot["analysis"] = copy.deepcopy(result)
            run_snapshot["report_draft"] = copy.deepcopy(result["report"])
            run_snapshot["report"] = copy.deepcopy(result["report"])
            run_snapshot["report"]["runtime_mode"] = result["runtime_mode"]
            from .supplemental_interview import export_answers
            if supplementary := export_answers(run_snapshot):
                run_snapshot["report"]["supplemental_answers"] = supplementary
            run_snapshot["status"] = "completed"
            run_snapshot["completed_at"] = datetime.now(timezone.utc).isoformat()

        updated = store.mutate(user["user_id"], run_id, expected, "finalize", key, body, apply)
        if analysis_stale:
            cache_derivations(user["user_id"], snapshot, result)
        return _public_snapshot(updated)

    static_dir = Path(__file__).with_name("static")
    application.mount("/static", StaticFiles(directory=static_dir), name="static")
    frontend_dir = Path(__file__).resolve().parents[1] / "html"
    application.mount("/frontend", StaticFiles(directory=frontend_dir), name="frontend")

    @application.get("/")
    async def index():
        return FileResponse(frontend_dir / "index.html")

    return application


app = create_app()
