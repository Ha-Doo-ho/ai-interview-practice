from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tools.inspect_stack import inspect_stack

HEADERS = {"X-Requested-With": "interview-app"}
ROOT = Path(__file__).resolve().parents[1]


def post_run(client, run, endpoint, **payload):
    result = client.post(f"/api/runs/{run['run_id']}/{endpoint}", headers=HEADERS,
                         json={"idempotency_key": str(uuid4()), "expected_revision": run["revision"], **payload})
    assert result.status_code == 200, result.text
    return result.json()


def complete_synthetic_run(client):
    definitions = client.get("/api/definitions").json()
    created = client.post("/api/runs", json={}, headers=HEADERS)
    assert created.status_code == 201
    run = created.json()
    for item in definitions["surveys"]:
        kind = item["type"]
        if kind == "ordinal_6":
            answer = {"selected_position": 5}
        elif kind == "paired_perspective":
            answer = {"self": {"selected_position": 4, "status": "submitted"},
                      "imagined_others": {"selected_position": 5, "status": "submitted"}}
        elif kind == "bipolar_slider":
            answer = {"final_value": 0, "interaction_occurred": False, "explicit_confirmation": True, "change_count": 0}
        else:
            answer = {"selected_ids": [c["option_id"] for c in item["candidates"][:item["requested_k"]]], "selection_events": []}
        run = post_run(client, run, "surveys", item_id=item["item_id"], item_version=item["item_version"], response=answer, status="submitted")
    for _ in definitions["game"]["rounds"]:
        run = post_run(client, run, "game", action="start")
        run = post_run(client, run, "game", action="open_info")
        run = post_run(client, run, "game", action="allocate", personal=4, reason="합성 연습: 두 과제의 조건을 확인했습니다.")
        run = post_run(client, run, "game", action="reveal")
        run = post_run(client, run, "game", action="revise", personal=5, reason="합성 연습: 새 정보 뒤 배분을 수정했습니다.")
        if run["game"]["phase"] != "complete":
            run = post_run(client, run, "game", action="next")
    for question in definitions["questions"]:
        run = post_run(client, run, "answers", question_id=question["question_id"],
                       text="동료에게 먼저 물었어요🙂 그리고 수정했어요. 합성 프로젝트에서 저는 일정 담당이었고 개인과 팀 과제에 시간을 나눴습니다.")
    run = post_run(client, run, "analyze")
    assert run.get("report") is None, "Draft must not bypass adaptive questions"
    baseline = run["analysis"]["extractions"]
    followups = [q for q in run["questions"] if q["question_mode"] != "baseline"]
    assert followups, "Eligible ambiguous evidence must produce grounded adaptive questions"
    for question in followups:
        assert question["conditioned_on_prior_evidence"] is True
        run = post_run(client, run, "answers", question_id=question["question_id"],
                       text="합성 후속 답변입니다. 팀원의 과제 정보를 확인하고 판단 기준을 설명했습니다.")
    run = post_run(client, run, "finalize")
    assert run["report"]["lineage"]["conditioned_followup_refs"], "Submitted followup answers must be extracted separately before final report"
    return run, definitions, baseline


@pytest.mark.scenario("SCN-047")
def test_existing_django_postgresql_stack_is_preserved(tmp_path):
    (tmp_path / "requirements.txt").write_text("Django==5.2\npsycopg==3.2\n", encoding="utf-8")
    before = (tmp_path / "requirements.txt").read_bytes()
    selected = inspect_stack(tmp_path)
    assert selected == {"framework": "django", "database": "postgresql", "action": "preserve_existing"}
    assert (tmp_path / "requirements.txt").read_bytes() == before
    assert inspect_stack(ROOT)["framework"] == "fastapi"


@pytest.mark.scenario("SCN-048")
def test_full_authenticated_mock_journey_has_four_inputs_game_followups_and_report(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path / 'journey.db'}")) as client:
        registered = client.post("/api/register", headers=HEADERS, json={"username": "journey", "password": "synthetic-long-password"})
        assert registered.status_code == 201
        run, definitions, baseline = complete_synthetic_run(client)
        assert len({s["type"] for s in definitions["surveys"]}) == 4
        assert run["status"] == "completed"
        assert len(run["report"]["cards"]) == 3
        assert run["report"]["runtime_mode"] == "mock"
        assert client.get(f"/api/runs/{run['run_id']}").json()["report"] == run["report"]
        assert {c["behavior_id"] for c in run["report"]["cards"]} == {"B01", "B02", "B03"}


@pytest.mark.scenario("SCN-049")
def test_account_deletion_invalidates_session_and_all_saved_runs(tmp_path):
    from completion_helpers import finish_one_main_round
    app = create_app(f"sqlite:///{tmp_path / 'deletion.db'}")
    with TestClient(app) as client:
        assert client.post("/api/register", headers=HEADERS, json={"username": "deleted", "password": "synthetic-long-password"}).status_code == 201
        run = client.post("/api/runs", headers=HEADERS, json={}).json()
        run = finish_one_main_round(client, run)
        run = post_run(client, run, "analyze")
        assert run["analysis"] is not None
        assert client.delete("/api/account", headers=HEADERS).status_code in {200, 204}
        assert client.get("/api/me").status_code == 401
        assert client.get(f"/api/runs/{run['run_id']}").status_code == 401
        assert client.post("/api/register", headers=HEADERS, json={"username": "newuser", "password": "synthetic-long-password"}).status_code == 201
        assert client.get("/api/runs").json()["runs"] == []
        assert client.get(f"/api/runs/{run['run_id']}").status_code == 404


@pytest.mark.scenario("SCN-050")
def test_text_mvp_does_not_offer_camera_or_face_analysis(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path / 'scope.db'}")) as client:
        script = client.get("/static/app.js").text
        assert "getUserMedia" not in script
        assert "mediaDevices" not in script
        assert client.get("/api/video").status_code == 404
        assert client.get("/api/face-score").status_code == 404
        assert "성격을 판정하지 않습니다" in client.get("/").text
