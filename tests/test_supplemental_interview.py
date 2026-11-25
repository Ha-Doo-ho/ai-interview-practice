"""Real API regression checks for optional interview persistence, not ability scoring."""
from copy import deepcopy
from uuid import uuid4
from fastapi.testclient import TestClient

from test_rule_games import api, HEADERS
from test_interview_connection import mutate
from test_evidence_linkage import prepared_run


def extra_questions(run):
    return [q for q in run["questions"] if q.get("question_mode") == "supplemental"]


def test_existing_working_memory_run_curates_questions_and_preserves_original_evidence():
    from app.supplemental_interview import QUESTIONS, add_questions, export_answers
    old = deepcopy([q for q in QUESTIONS if q["question_group"] == "working-memory-interview-v1"])
    run = {"questions": old, "records": [{"source_type": "typed_answer", "data": {
        "question_id": "wm-experience-0", "answer_id": "old-answer", "text": "기존 답변",
        "answer_version": "1.0.0", "status": "asked_answered"}}]}
    before = deepcopy(run)
    add_questions(run)
    assert run["interview_question_history"][0]["questions"] == before["questions"]
    assert run['questions'][0] == before['questions'][0]
    assert run['questions'][1] == before['questions'][3]
    assert run["records"] == before["records"]
    assert len(run["questions"]) == 5
    added = run["questions"][2:]
    assert len({q["question_group"] for q in added}) == 2
    assert all(q["behavior_id"] is None and not q["required_for_completion"] for q in added)
    add_questions(run)
    assert len(run["questions"]) == 5
    for q in added:
        run["records"].append({"source_type": "typed_answer", "data": {
            "question_id": q["question_id"], "answer_id": q["question_id"],
            "text": "업무 경험", "answer_version": "1.0.0", "status": "asked_answered"}})
    exported = export_answers(run)
    assert exported[0]["text"] == "기존 답변"
    assert all(a["text"] == "업무 경험" for a in exported[2:])
    assert len(exported) == 5


def test_new_flow_has_three_experience_groups_without_changing_baseline(api):
    client, _, _, legacy, _ = api
    run = client.post("/api/runs", headers=HEADERS, json={"flow_version": "five-game-v2"}).json()
    assert len(extra_questions(run)) == 5
    assert [q for q in run["questions"] if q["question_mode"] == "baseline"] == legacy["questions"]
    assert len({q["question_id"] for q in run["questions"]}) == 8
    roots = [q for q in extra_questions(run) if q["parent_question_id"] is None]
    assert len(roots) == 3
    for root in roots:
        children = [q for q in extra_questions(run) if q["parent_question_id"] == root["question_id"]]
        assert len(children) in (0, 1)
        assert all(q["question_group"] == root["question_group"] for q in children)
    blocked = client.post(f"/api/runs/{run['run_id']}/answers", headers=HEADERS,
        json={"expected_revision": run["revision"], "idempotency_key": str(uuid4()),
              "question_id": extra_questions(run)[0]["question_id"], "text": "아직 게임 전"})
    assert blocked.status_code == 409


def test_existing_run_add_save_revise_reload_and_access_protection(api):
    client, application, _, run, _ = api
    original_questions = deepcopy(run["questions"])
    url = f"/api/runs/{run['run_id']}/supplemental-interview"
    body = {"expected_revision": run["revision"], "idempotency_key": str(uuid4())}
    with TestClient(application) as stranger:
        stranger.post("/api/register", headers=HEADERS,
            json={"username": "wm-stranger", "password": "synthetic-password"})
        assert stranger.post(url, headers=HEADERS, json=body).status_code == 404
    assert client.post(url, json=body).status_code == 403
    response = client.post(url, headers=HEADERS, json=body)
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["questions"][:3] == original_questions
    assert len(extra_questions(run)) == 5
    assert client.post(url, headers=HEADERS, json=body).json() == run
    run, _ = mutate(client, run, "supplemental-interview")
    assert len(extra_questions(run)) == 5
    for index, question in enumerate(extra_questions(run)):
        run, _ = mutate(client, run, "answers", question_id=question["question_id"],
            text=f"  응답 {index} 🙂\n유지한 조건과 바뀐 조건  ", status="asked_answered")
    qid = extra_questions(run)[1]["question_id"]
    previous = next(r["data"] for r in run["records"] if r["data"].get("question_id") == qid)
    run, _ = mutate(client, run, "answers", question_id=qid, text="  수정한 답변\n ",
        replaces_answer_id=previous["answer_id"], expected_answer_version=previous["answer_version"])
    restored = client.get(f"/api/runs/{run['run_id']}").json()
    assert restored == run
    assert len(restored["records"]) == 6
    assert restored["records"][-1]["data"]["text"] == "  수정한 답변\n "
    assert restored["records"][-1]["data"]["answer_version"] == "2.0.0"


def test_supplemental_answers_do_not_contaminate_baseline_and_are_frozen_in_report():
    from app.supplemental_interview import add_questions
    from app.evidence_linkage import build_linkage, finalize_report, linkage_is_current
    from app.content import DEFINITIONS
    from app.interview_analysis import input_snapshot
    run = prepared_run()
    before = input_snapshot(run, DEFINITIONS)
    add_questions(run)
    run["evidence_linkage"] = build_linkage(run, DEFINITIONS)
    run["questions"].extend(deepcopy(run["evidence_linkage"]["questions"]))
    question = extra_questions(run)[0]
    run["records"].append({"record_id": "wm-first", "source_type": "typed_answer", "data": {
        "question_id": question["question_id"], "question_version": question["question_version"],
        "question_mode": "supplemental", "conditioned_on_prior_evidence": False,
        "answer_id": "wm-first", "answer_version": "1.0.0",
        "text": "원문 🙂", "status": "asked_answered"}})
    assert input_snapshot(run, DEFINITIONS) == before
    assert linkage_is_current(run, DEFINITIONS)
    final = finalize_report(run, DEFINITIONS)
    assert len(final["supplemental_answers"]) == 5
    assert final["supplemental_answers"][0]["text"] == "원문 🙂"
    assert final["supplemental_answers"][1]["status"] == "not_answered"
    assert final["cards"] == run["interview_report"]["cards"]
    run["records"][-1]["data"]["text"] = "나중 변경"
    assert final["supplemental_answers"][0]["text"] == "원문 🙂"


def test_legacy_analysis_and_finalize_with_optional_answers_and_read_only_afterwards(api):
    from completion_helpers import finish_required_stages
    client, _, _, run, _ = api
    run = finish_required_stages(client, run)
    for question in run["questions"]:
        run, _ = mutate(client, run, "answers", question_id=question["question_id"], text="상황과 행동의 합성 답변")
    run, _ = mutate(client, run, "analyze")
    neutral = deepcopy([e for e in run["analysis"]["extractions"] if e["mode"] == "baseline"])
    old_input = deepcopy(run["analysis"]["input_snapshot"])
    run, _ = mutate(client, run, "supplemental-interview")
    run, _ = mutate(client, run, "answers", question_id=extra_questions(run)[0]["question_id"], text="새로운 자기보고")
    from app.main import _analysis_input_snapshot
    assert _analysis_input_snapshot(run) == old_input
    run, _ = mutate(client, run, "analyze")
    assert [e for e in run["analysis"]["extractions"] if e["mode"] == "baseline"] == neutral
    run, _ = mutate(client, run, "finalize")
    assert run["status"] == "completed"
    assert run["report"]["supplemental_answers"][0]["text"] == "새로운 자기보고"
    for endpoint, extra in (("supplemental-interview", {}), ("answers", {
        "question_id": "wm-experience-1", "text": "확정 뒤 답변"})):
        denied = client.post(f"/api/runs/{run['run_id']}/{endpoint}", headers=HEADERS, json={
            "expected_revision": run["revision"], "idempotency_key": str(uuid4()), **extra})
        assert denied.status_code == 409
