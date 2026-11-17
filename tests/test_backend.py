from __future__ import annotations

import copy
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.content import DEFINITIONS
from app.game import GameValidation, aggregate_game, apply_game_action, initial_game_state
from app.main import create_app
from app.store import CacheRow, Conflict, Deleted, Finalized, NotFound, Store
from app.survey import build_survey_record
from completion_helpers import finish_one_main_round


HEADER = {"X-Requested-With": "interview-app"}


def make_store(tmp_path) -> Store:
    return Store(f"sqlite:///{tmp_path / 'test.db'}")


def register(client: TestClient, username: str = "student") -> dict:
    response = client.post(
        "/api/register",
        json={"username": username, "password": "correct horse battery staple"},
        headers=HEADER,
    )
    assert response.status_code == 201
    return response.json()


def new_run(client: TestClient) -> dict:
    response = client.post("/api/runs", json={}, headers=HEADER)
    assert response.status_code == 201
    return response.json()


def mutation(run: dict, key: str, **extra) -> dict:
    return {"expected_revision": run["revision"], "idempotency_key": key, **extra}


@pytest.mark.scenario("SCN-001")
def test_definitions_preserve_required_survey_meaning_and_game_rounds():
    surveys = {item["item_id"]: item for item in DEFINITIONS["surveys"]}
    assert set(surveys) == {"O-B01", "O-B02", "O-B03", "P-B01", "S-B02", "R-UNMAPPED"}
    assert [o["label"] for o in surveys["O-B01"]["ordered_options"]] == [
        "전혀 그렇지 않다",
        "그렇지 않다",
        "그렇지 않은 편이다",
        "그런 편이다",
        "그렇다",
        "매우 그렇다",
    ]
    assert surveys["P-B01"]["prompt"] == surveys["O-B01"]["prompt"]
    assert surveys["S-B02"]["behavior_id"] == "B02"
    assert surveys["R-UNMAPPED"]["behavior_id"] is None
    rounds = DEFINITIONS["game"]["rounds"]
    assert [r["practice_or_main"] for r in rounds] == ["practice", "main", "main", "main"]


@pytest.mark.scenario("SCN-016", "SCN-017", "SCN-018")
def test_source_specific_mappings_are_independently_approved_for_practice_only():
    mappings = DEFINITIONS["mappings"]
    required = {
        "mapping_id", "version", "source_definition_id", "source_definition_version", "source_kind",
        "behavior_id", "behavior_version", "reason", "observable_proxy", "preconditions",
        "eligible_opportunity_rule", "limitations", "permitted_uses", "practice_review_status",
        "validity_status", "reviewer_type", "reviewer_id", "review_mode", "reviewed_at",
    }
    assert len(mappings) == 11
    assert all(required.issubset(mapping) for mapping in mappings)
    assert all(mapping["practice_review_status"] == "approved_for_practice" for mapping in mappings)
    assert all(mapping["validity_status"] == "provisional_unvalidated" for mapping in mappings)
    assert all(mapping["reviewer_id"] == "/root/domain_review_resume" for mapping in mappings)
    assert not any(mapping["source_definition_id"] == "collaboration" for mapping in mappings)
    slider = next(mapping for mapping in mappings if mapping["mapping_id"] == "map-survey-s-b02")
    assert "evidence_comparison" not in slider["permitted_uses"]


@pytest.mark.scenario("SCN-059", "SCN-060", "SCN-061")
def test_store_idempotency_revision_and_finalization_are_atomic(tmp_path):
    store = make_store(tmp_path)
    user = store.create_user("alice", "a sufficiently long password")
    run = store.create_run(user["user_id"])

    def append_marker(data):
        data["records"].append({"record_id": "one"})

    first = store.mutate(
        user["user_id"], run["run_id"], 0, "survey", "same", {"choice": 4}, append_marker
    )
    retry = store.mutate(
        user["user_id"], run["run_id"], 0, "survey", "same", {"choice": 4}, append_marker
    )
    assert retry == first
    assert len(store.get_run(user["user_id"], run["run_id"])["records"]) == 1

    with pytest.raises(Conflict, match="idempotency_conflict"):
        store.mutate(
            user["user_id"], run["run_id"], 0, "survey", "same", {"choice": 5}, append_marker
        )
    with pytest.raises(Conflict, match="revision_conflict"):
        store.mutate(user["user_id"], run["run_id"], 0, "survey", "new", {}, append_marker)

    finalized = store.mutate(
        user["user_id"], run["run_id"], 1, "finalize", "finish", {}, lambda data: data.update(status="completed")
    )
    assert finalized["status"] == "completed"
    with pytest.raises(Finalized, match="stale_after_finalize"):
        store.mutate(user["user_id"], run["run_id"], 2, "survey", "late", {}, append_marker)


@pytest.mark.scenario("SCN-063")
def test_job_completion_checks_deletion_generation_and_scrubs_content(tmp_path):
    store = make_store(tmp_path)
    user = store.create_user("alice", "a sufficiently long password")
    run = store.create_run(user["user_id"])
    job = store.begin_job(user["user_id"], run["run_id"], run["attempt_id"], 0, "analysis")
    store.delete_run(user["user_id"], run["run_id"])

    with pytest.raises(Deleted, match="cancelled_after_deletion"):
        store.complete_job(user["user_id"], job["job_id"], {"secret": "must disappear"})
    metadata = store.get_job_metadata(user["user_id"], job["job_id"])
    assert metadata["status"] == "cancelled_after_deletion"
    assert metadata["content_present"] is False
    with pytest.raises(NotFound):
        store.get_run(user["user_id"], run["run_id"])


@pytest.mark.scenario("SCN-062")
def test_jobs_and_cache_reject_cross_owner_access(tmp_path):
    store = make_store(tmp_path)
    alice = store.create_user("alice", "a sufficiently long password")
    bob = store.create_user("bob", "a sufficiently long password")
    run = store.create_run(alice["user_id"])
    job = store.begin_job(alice["user_id"], run["run_id"], run["attempt_id"], 0, "analysis")

    with pytest.raises(NotFound):
        store.complete_job(bob["user_id"], job["job_id"], {"must": "stay private"})
    with pytest.raises(NotFound):
        store.get_job_metadata(bob["user_id"], job["job_id"])
    store.put_cache(alice["user_id"], run["run_id"], run["attempt_id"], "baseline", "k1", {"value": 1})
    assert store.get_cache(alice["user_id"], run["run_id"], run["attempt_id"], "baseline", "k1") == {"value": 1}
    with pytest.raises(NotFound):
        store.get_cache(bob["user_id"], run["run_id"], run["attempt_id"], "baseline", "k1")
    assert store.get_cache(alice["user_id"], run["run_id"], run["attempt_id"], "conditioned", "k1") is None
    with pytest.raises(NotFound):
        store.begin_job(alice["user_id"], run["run_id"], "wrong-attempt", 0, "analysis")
    with pytest.raises(NotFound):
        store.put_cache(alice["user_id"], run["run_id"], "wrong-attempt", "baseline", "k2", {"value": 2})


def test_cache_insert_cannot_resurrect_after_delete_between_check_and_write(tmp_path):
    store = make_store(tmp_path)
    user = store.create_user("alice", "a sufficiently long password")
    run = store.create_run(user["user_id"])
    armed = [True]

    def delete_before_insert(_conn, _cursor, statement, _parameters, _context, _executemany):
        if armed[0] and statement.startswith("UPDATE derived_cache"):
            armed[0] = False
            store.delete_run(user["user_id"], run["run_id"])

    event.listen(store.engine, "before_cursor_execute", delete_before_insert)
    try:
        with pytest.raises(Deleted, match="cancelled_after_deletion"):
            store.put_cache(user["user_id"], run["run_id"], run["attempt_id"], "baseline", "race", {"secret": "discard"})
    finally:
        event.remove(store.engine, "before_cursor_execute", delete_before_insert)
    with Session(store.engine) as session:
        assert session.scalar(select(CacheRow).where(CacheRow.run_id == run["run_id"])) is None


def test_job_success_cannot_overwrite_cancellation_after_delete_between_check_and_write(tmp_path):
    store = make_store(tmp_path)
    user = store.create_user("alice", "a sufficiently long password")
    run = store.create_run(user["user_id"])
    job = store.begin_job(user["user_id"], run["run_id"], run["attempt_id"], 0, "analysis")
    armed = [True]

    def delete_before_update(_conn, _cursor, statement, _parameters, _context, _executemany):
        if armed[0] and statement.startswith("UPDATE analysis_jobs"):
            armed[0] = False
            store.delete_run(user["user_id"], run["run_id"])

    event.listen(store.engine, "before_cursor_execute", delete_before_update)
    try:
        with pytest.raises(Deleted, match="cancelled_after_deletion"):
            store.complete_job(user["user_id"], job["job_id"], {"secret": "discard"})
    finally:
        event.remove(store.engine, "before_cursor_execute", delete_before_update)
    metadata = store.get_job_metadata(user["user_id"], job["job_id"])
    assert metadata["status"] == "cancelled_after_deletion"
    assert metadata["content_present"] is False


@pytest.mark.scenario("SCN-012")
def test_auth_csrf_ownership_and_redacted_errors(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}")
    with TestClient(app) as alice:
        assert alice.post("/api/register", json={"username": "x", "password": "long enough password"}).status_code == 403
        register(alice, "alice")
        run = new_run(alice)
        assert "password" not in str(alice.get("/api/me").json()).lower()

        with TestClient(app) as bob:
            register(bob, "bob")
            hidden = bob.get(f"/api/runs/{run['run_id']}")
            assert hidden.status_code == 404
            assert hidden.json() == {"error": "not_found"}


@pytest.mark.scenario("SCN-003")
def test_survey_submission_preserves_strength_and_retry_is_idempotent(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}")
    with TestClient(app) as client:
        register(client)
        run = new_run(client)
        body = mutation(
            run,
            "ordinal-1",
            item_id="O-B01",
            item_version="1.0.0",
            status="submitted",
            response={"selected_position": 5},
            elapsed_ms=412,
        )
        response = client.post(f"/api/runs/{run['run_id']}/surveys", json=body, headers=HEADER)
        assert response.status_code == 200
        updated = response.json()
        record = updated["records"][0]
        assert record["data"]["selected_position"] == 5
        assert record["data"]["selected_label_snapshot"] == "그렇다"
        assert len(record["data"]["ordered_options_snapshot"]) == 6
        retry = client.post(f"/api/runs/{run['run_id']}/surveys", json=body, headers=HEADER)
        assert retry.json() == updated
        changed = copy.deepcopy(body)
        changed["response"]["selected_position"] = 6
        conflict = client.post(f"/api/runs/{run['run_id']}/surveys", json=changed, headers=HEADER)
        assert conflict.status_code == 409
        assert conflict.json() == {"error": "idempotency_conflict"}


@pytest.mark.scenario("SCN-004", "SCN-007", "SCN-009", "SCN-010")
def test_all_survey_modes_preserve_original_semantics(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}")
    with TestClient(app) as client:
        register(client)
        run = new_run(client)
        cases = [
            (
                "P-B01",
                {"self": {"selected_position": 6, "status": "submitted"}, "imagined_others": {"selected_position": 3, "status": "submitted"}},
            ),
            (
                "S-B02",
                {"final_value": 0, "interaction_occurred": False, "explicit_confirmation": True, "change_count": 0},
            ),
            (
                "R-UNMAPPED",
                {
                    "selected_ids": ["growth", "stability", "autonomy"],
                    "selection_events": [
                        {"action": "select", "option_id": "stability", "order": 1},
                        {"action": "select", "option_id": "growth", "order": 2},
                        {"action": "move", "option_id": "growth", "rank": 1},
                        {"action": "select", "option_id": "autonomy", "order": 4},
                    ],
                },
            ),
        ]
        for index, (item_id, survey_response) in enumerate(cases, 1):
            response = client.post(
                f"/api/runs/{run['run_id']}/surveys",
                json=mutation(
                    run,
                    f"survey-{index}",
                    item_id=item_id,
                    item_version="1.0.0",
                    status="submitted",
                    response=survey_response,
                    elapsed_ms=100 + index,
                ),
                headers=HEADER,
            )
            assert response.status_code == 200, response.text
            run = response.json()

        paired, slider, ranked = run["records"]
        assert paired["data"]["self"]["selected_label_snapshot"] == "매우 그렇다"
        assert paired["data"]["imagined_others"]["perspective"] == "imagined_others"
        assert paired["data"]["perspective_presentation_order"] == ["self", "imagined_others"]
        assert paired["data"]["prior_response_visible"] is True
        assert slider["data"]["final_value"] == 0
        assert slider["data"]["submit_status"] == "submitted"
        assert slider["data"]["explicit_confirmation"] is True
        assert ranked["data"]["ranked_selection"] == [
            {"option_id": "growth", "rank": 1},
            {"option_id": "stability", "rank": 2},
            {"option_id": "autonomy", "rank": 3},
        ]
        assert set(ranked["data"]["unselected_ids"]) == {"helping", "recognition"}
        assert "distance" not in ranked["data"]


@pytest.mark.scenario("SCN-006")
def test_slider_preserves_custom_half_step_range_without_interpreting_it():
    definition = copy.deepcopy(next(item for item in DEFINITIONS["surveys"] if item["item_id"] == "S-B02"))
    definition.update(min=-3, max=3, step=0.5, initial_value=0)
    record = build_survey_record(
        definition=definition,
        user_id="u-006",
        run_id="run-006",
        attempt_id="attempt-006",
        presentation_order=1,
        response={"final_value": 1.5, "interaction_occurred": True, "explicit_confirmation": True, "change_count": 2},
        status="submitted",
        elapsed_ms=1234,
    )
    data = record["data"]
    assert (data["min"], data["max"], data["step"], data["initial_value"], data["final_value"]) == (-3, 3, 0.5, 0, 1.5)
    assert data["interaction_occurred"] is True
    assert not any(key in data for key in ("percent", "trait_score", "ability_score"))


@pytest.mark.scenario("SCN-008")
def test_timed_out_slider_does_not_turn_untouched_center_into_an_answer(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}")
    with TestClient(app) as client:
        register(client)
        run = new_run(client)
        response = client.post(
            f"/api/runs/{run['run_id']}/surveys",
            json=mutation(
                run,
                "slider-timeout",
                item_id="S-B02",
                item_version="1.0.0",
                status="timed_out",
                response={"final_value": None, "interaction_occurred": False, "explicit_confirmation": False, "change_count": 0},
                elapsed_ms=30000,
            ),
            headers=HEADER,
        )
        assert response.status_code == 200, response.text
        data = response.json()["records"][0]["data"]
        assert data["final_value"] is None
        assert data["missing_reason"] == "timed_out_without_interaction"


def test_answer_correction_creates_linked_version_without_overwriting_original(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}")
    with TestClient(app) as client:
        register(client)
        run = new_run(client)
        question = DEFINITIONS["questions"][0]
        first = client.post(
            f"/api/runs/{run['run_id']}/answers",
            headers=HEADER,
            json=mutation(run, "answer-v1", question_id=question["question_id"], text="첫 원문"),
        )
        assert first.status_code == 200, first.text
        run = first.json()
        original = run["records"][0]["data"]
        corrected = client.post(
            f"/api/runs/{run['run_id']}/answers",
            headers=HEADER,
            json=mutation(
                run,
                "answer-v2",
                question_id=question["question_id"],
                text="정정 원문",
                replaces_answer_id=original["answer_id"],
                expected_answer_version=original["answer_version"],
            ),
        )
        assert corrected.status_code == 200, corrected.text
        records = corrected.json()["records"]
        assert records[0]["data"]["text"] == "첫 원문"
        assert records[0]["data"]["answer_version"] == "1.0.0"
        assert records[1]["data"]["text"] == "정정 원문"
        assert records[1]["data"]["answer_version"] == "2.0.0"
        assert records[1]["data"]["previous_answer_version_ref"] == {
            "answer_id": original["answer_id"], "answer_version": "1.0.0"
        }


def test_asked_without_text_is_preserved_as_missing_not_behavior_absence(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}")
    with TestClient(app) as client:
        register(client)
        run = new_run(client)
        response = client.post(
            f"/api/runs/{run['run_id']}/answers",
            headers=HEADER,
            json=mutation(run, "no-text", question_id=DEFINITIONS["questions"][0]["question_id"], text="", status="asked_no_text"),
        )
        assert response.status_code == 200, response.text
        record = response.json()["records"][0]
        assert record["status"] == "asked_no_text"
        assert record["data"]["status"] == "asked_no_text"
        assert record["data"]["text"] == ""


@pytest.mark.scenario("SCN-067")
def test_game_enforces_sequence_and_records_unchanged_after_evidence(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}")
    with TestClient(app) as client:
        register(client)
        run = new_run(client)
        for key, payload in [
            ("start", {"action": "start"}),
            ("open", {"action": "open_info"}),
            ("alloc", {"action": "allocate", "personal": 4, "reason": "연습 배분"}),
            ("reveal", {"action": "reveal"}),
            ("revise", {"action": "revise", "personal": 4, "reason": "유지"}),
        ]:
            response = client.post(
                f"/api/runs/{run['run_id']}/game",
                json=mutation(run, key, **payload),
                headers=HEADER,
            )
            assert response.status_code == 200, response.text
            run = response.json()
        current = run["game"]["rounds"][0]
        assert current["revision_outcome"] == "unchanged_after_evidence"
        assert [e["sequence_no"] for e in run["game"]["events"]] == list(range(1, 6))
        assert run["game"]["phase"] == "round_complete"


def test_game_deadline_rejects_early_timeout_and_turns_late_choice_into_timeout(monkeypatch):
    current = [datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)]
    monkeypatch.setattr("app.game._now", lambda: current[0])
    game = initial_game_state(DEFINITIONS["game"])
    apply_game_action(game, "start")
    with pytest.raises(GameValidation, match="deadline_not_reached"):
        apply_game_action(game, "timeout")
    current[0] += timedelta(seconds=200)
    apply_game_action(game, "allocate", personal=4, reason="late selection must not be saved")
    round_state = game["rounds"][0]
    assert game["phase"] == "round_complete"
    assert round_state["initial_decision"] is None
    assert round_state["missing_reason"] == "timed_out_before_initial_decision"
    assert game["events"][-1]["event_type"] == "round_timed_out"


@pytest.mark.scenario("SCN-011", "SCN-013", "SCN-014", "SCN-015", "SCN-019", "SCN-021", "SCN-023")
def test_game_aggregates_only_three_main_rounds_with_explicit_opportunities(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}")
    with TestClient(app) as client:
        register(client)
        run = new_run(client)
        opened_main = 0
        for round_index in range(4):
            actions = [("start", {})]
            if round_index in {0, 2}:
                actions.append(("open_info", {}))
                if round_index > 0:
                    opened_main += 1
            actions += [
                ("allocate", {"personal": 4 + (round_index % 2), "reason": f"round {round_index}"}),
                ("reveal", {}),
                ("revise", {"personal": 5, "reason": "new information considered"}),
            ]
            for action_index, (action, extra) in enumerate(actions):
                response = client.post(
                    f"/api/runs/{run['run_id']}/game",
                    json=mutation(run, f"r{round_index}-{action_index}-{action}", action=action, **extra),
                    headers=HEADER,
                )
                assert response.status_code == 200, response.text
                run = response.json()
            if round_index < 3:
                response = client.post(
                    f"/api/runs/{run['run_id']}/game",
                    json=mutation(run, f"r{round_index}-next", action="next"),
                    headers=HEADER,
                )
                assert response.status_code == 200, response.text
                run = response.json()

        assert run["game"]["phase"] == "complete"
        metrics = {metric["behavior_id"]: metric for metric in run["game"]["metrics"]}
        assert metrics["B01"]["denominator"] == 3
        assert metrics["B01"]["numerator"] == opened_main
        assert metrics["B01"]["included_opportunity_ids"] == ["opp-main-1-info", "opp-main-2-info", "opp-main-3-info"]
        assert metrics["B03"]["denominator"] == 3
        assert all(r["practice_or_main"] == "main" for r in run["game"]["rounds"][1:])
        assert all(event["immutable_parent_ref"].startswith("game_presentation:") for event in run["game"]["events"])
        assert [event["state_version_after"] for event in run["game"]["events"]] == list(range(1, len(run["game"]["events"]) + 1))
        first_main = run["game"]["rounds"][1]
        assert first_main["initial_decision"]["personal"] + first_main["initial_decision"]["team"] == first_main["total_resources"]
        assert first_main["initial_decision"]["reason_source_kind"] == "typed_self_report"
        assert metrics["B02"]["observations"][0]["initial_allocation"]["personal"] == first_main["initial_decision"]["personal"]
        assert "understand" not in str(metrics["B01"]).lower()


@pytest.mark.scenario("SCN-020")
def test_game_uses_server_sequence_and_state_versions_not_client_values():
    game = initial_game_state(DEFINITIONS["game"])
    apply_game_action(game, "start")
    apply_game_action(game, "open_info")
    assert [event["sequence_no"] for event in game["events"]] == [1, 2]
    assert [(event["state_version_before"], event["state_version_after"]) for event in game["events"]] == [(0, 1), (1, 2)]
    assert game["state_version"] == 2


@pytest.mark.scenario("SCN-022")
def test_zero_eligible_opportunities_preserves_zero_over_zero_as_unavailable():
    game = initial_game_state(DEFINITIONS["game"])
    for round_state in game["rounds"]:
        for opportunity in round_state["opportunities"]:
            if opportunity["behavior_id"] == "B01":
                opportunity["eligible"] = False
                opportunity["eligible_reason"] = "information_not_available"
    metric = next(item for item in aggregate_game(game) if item["behavior_id"] == "B01")
    assert metric["numerator"] == 0
    assert metric["denominator"] == 0
    assert metric["value"] is None


@pytest.mark.scenario("SCN-066")
def test_information_opened_after_decision_stays_in_denominator_but_not_numerator():
    game = initial_game_state(DEFINITIONS["game"])
    game["round_index"] = 1
    apply_game_action(game, "start")
    apply_game_action(game, "allocate", personal=4, reason="initial")
    round_state = game["rounds"][1]
    round_state["information"]["opened"] = True
    game["state_version"] += 1
    game["events"].append(
        {
            "event_id": "late-info",
            "sequence_no": len(game["events"]) + 1,
            "event_type": "information_opened",
            "server_received_at": "2026-09-16T12:00:08+00:00",
            "round_id": round_state["round_id"],
            "practice_or_main": "main",
            "state_before_ref": "allocated",
            "state_after_ref": "allocated",
            "state_version_before": game["state_version"] - 1,
            "state_version_after": game["state_version"],
            "immutable_parent_ref": f"game_presentation:{game['presentation']['presentation_id']}",
            "value": {"information_id": round_state["information"]["information_id"]},
        }
    )
    metric = next(item for item in aggregate_game(game) if item["behavior_id"] == "B01")
    observation = next(item for item in metric["observations"] if item["round_id"] == "main-1")
    assert metric["denominator"] == 1
    assert metric["numerator"] == 0
    assert observation["reason"] == "after_decision"


@pytest.mark.scenario("SCN-068")
def test_change_before_evidence_is_not_attributed_to_later_evidence():
    game = initial_game_state(DEFINITIONS["game"])
    game["round_index"] = 1
    round_state = game["rounds"][1]
    round_state["revision_outcome"] = "unchanged_after_evidence"
    game["events"] = [
        {"round_id": "main-1", "event_type": "round_started", "sequence_no": 1},
        {"round_id": "main-1", "event_type": "initial_allocation", "sequence_no": 2},
        {"round_id": "main-1", "event_type": "pre_evidence_change", "sequence_no": 3},
        {"round_id": "main-1", "event_type": "new_information_revealed", "sequence_no": 4},
        {"round_id": "main-1", "event_type": "final_allocation", "sequence_no": 5},
    ]
    metric = next(item for item in aggregate_game(game) if item["behavior_id"] == "B03")
    observation = next(item for item in metric["observations"] if item["round_id"] == "main-1")
    assert metric["numerator"] == 0
    assert observation["revision_outcome"] == "unchanged_after_evidence"
    assert observation["reason"] == "unchanged_after_evidence"


@pytest.mark.scenario("SCN-064")
def test_validation_errors_do_not_log_answer_or_key_markers(caplog, monkeypatch, tmp_path):
    monkeypatch.setenv("SYNTHETIC_PROVIDER_KEY", "sk-test-64")
    app = create_app(f"sqlite:///{tmp_path / 'redaction.db'}")
    with TestClient(app) as client:
        register(client)
        run = new_run(client)
        response = client.post(
            f"/api/runs/{run['run_id']}/answers",
            headers=HEADER,
            json=mutation(run, "bad-answer", question_id="missing", text="합성 비밀문장-64"),
        )
        assert response.status_code == 422
        assert response.json() == {"error": "validation_error"}
    logs = caplog.text
    assert "합성 비밀문장-64" not in logs
    assert "sk-test-64" not in logs


def test_analyze_runs_outside_store_guard_and_commits_with_revision(monkeypatch, tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}")
    seen = {}

    def analyze_run(snapshot, definitions):
        seen["revision"] = snapshot["revision"]
        return {
            "extractions": [],
            "metrics": [],
            "comparisons": [],
            "questions": [],
            "report": {"cards": []},
            "runtime_mode": "mock",
        }

    monkeypatch.setitem(sys.modules, "app.analysis", SimpleNamespace(analyze_run=analyze_run))
    with TestClient(app) as client:
        register(client)
        run = new_run(client)
        run = finish_one_main_round(client, run)
        response = client.post(
            f"/api/runs/{run['run_id']}/analyze",
            json=mutation(run, "analyze-1"),
            headers=HEADER,
        )
        assert response.status_code == 200, response.text
        analyzed = response.json()
        assert seen["revision"] == run["revision"]
        assert analyzed["analysis"]["runtime_mode"] == "mock"
        assert analyzed["revision"] == run["revision"] + 1


def test_analyze_exact_retry_returns_prior_result_without_reinvoking_analysis(monkeypatch, tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}")
    calls = []

    def analyze_run(snapshot, definitions):
        calls.append(snapshot["revision"])
        return {"extractions": [], "metrics": [], "comparisons": [], "questions": [], "report": {"cards": []}, "runtime_mode": "mock"}

    monkeypatch.setitem(sys.modules, "app.analysis", SimpleNamespace(analyze_run=analyze_run))
    with TestClient(app) as client:
        register(client)
        run = new_run(client)
        run = finish_one_main_round(client, run)
        body = mutation(run, "analyze-retry")
        first = client.post(f"/api/runs/{run['run_id']}/analyze", json=body, headers=HEADER)
        retry = client.post(f"/api/runs/{run['run_id']}/analyze", json=body, headers=HEADER)
        assert first.status_code == retry.status_code == 200
        assert retry.json() == first.json()
        assert calls == [run["revision"]]


def test_finalize_reanalyzes_when_baseline_answers_were_added_after_analysis(monkeypatch, tmp_path):
    from completion_helpers import finish_required_stages
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}")
    calls = []

    def analyze_run(snapshot, definitions):
        answers = [record for record in snapshot["records"] if record.get("source_type") == "typed_answer"]
        calls.append(len(answers))
        extractions = [
            {
                "extraction_id": f"ext-{record['data']['answer_id']}",
                "version": "1",
                "answer_id": record["data"]["answer_id"],
                "answer_version": record["data"]["answer_version"],
                "question_id": record["data"]["question_id"],
                "question_version": record["data"]["question_version"],
                "mode": "baseline",
                "behavior_id": record["data"]["behavior_id"],
                "criteria": {},
                "answer_evidence_spans": [],
                "lineage": {"cache_key": f"cache-{record['data']['answer_id']}"},
            }
            for record in answers
        ]
        return {
            "extractions": extractions,
            "metrics": [],
            "comparisons": [],
            "questions": [],
            "report": {"cards": [], "lineage": {"conditioned_followup_refs": []}},
            "runtime_mode": "mock",
        }

    monkeypatch.setitem(sys.modules, "app.analysis", SimpleNamespace(analyze_run=analyze_run))
    with TestClient(app) as client:
        user = register(client)
        run = new_run(client)
        run = finish_required_stages(client, run)
        response = client.post(f"/api/runs/{run['run_id']}/analyze", json=mutation(run, "early-analysis"), headers=HEADER)
        assert response.status_code == 200, response.text
        run = response.json()
        assert run["analysis"]["extractions"] == []
        for index, question in enumerate(DEFINITIONS["questions"]):
            response = client.post(
                f"/api/runs/{run['run_id']}/answers",
                json=mutation(run, f"baseline-{index}", question_id=question["question_id"], text=f"answer {index}"),
                headers=HEADER,
            )
            assert response.status_code == 200, response.text
            run = response.json()
        response = client.post(f"/api/runs/{run['run_id']}/finalize", json=mutation(run, "finish-fresh"), headers=HEADER)
        assert response.status_code == 200, response.text
        finalized = response.json()
        assert finalized["status"] == "completed"
        assert len(finalized["analysis"]["extractions"]) == 3
        assert calls == [0, 3]
        first = finalized["analysis"]["extractions"][0]
        cached = app.state.store.get_cache(
            user["user_id"],
            finalized["run_id"],
            finalized["attempt_id"],
            "baseline_extraction",
            first["lineage"]["cache_key"],
        )
        assert cached == {"extraction": first}
