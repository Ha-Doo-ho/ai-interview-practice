"""Fixed, optional interview self-reports; never input to baseline ability scoring."""
from copy import deepcopy

VERSION = "working-memory-interview-v1"
PROMPTS = (
    "여러 사람에게 받은 요청을 처리하던 중 일부 조건이 바뀐 경험을 설명해 주세요. 처음 요청과 변경된 내용은 무엇이었으며, 최종적으로 어떻게 처리했나요?",
    "그때 동시에 기억해야 했던 정보는 무엇이었나요?",
    "바뀐 조건과 그대로 유지되는 조건을 어떻게 구분했나요?",
    "빠뜨리거나 혼동한 부분은 있었고, 어떻게 확인했나요?",
    "메모나 도구를 사용했다면 어느 단계에서 사용했나요?",
)
QUESTIONS = [
    {
        "question_id": f"wm-experience-{index}",
        "question_version": "1.0.0",
        "question_prompt_version": VERSION,
        "question_text": text,
        "question_mode": "supplemental",
        "question_group": VERSION,
        "parent_question_id": "wm-experience-0" if index else None,
        "behavior_id": None,
        "target_behavior_ids": [],
        "conditioned_on_prior_evidence": False,
        "disclosed_prior_information": [],
        "generated_from_evidence_refs": [],
        "required_for_completion": False,
    }
    for index, text in enumerate(PROMPTS)
]

# Keep the existing working-memory v1 wording and IDs immutable. New topics have
# their own groups and parents so saved answers retain their original meaning.
WORK_GROUPS = (
    ("spatial-work-interview-v1", "spatial-work-experience", (
        "물품이나 장비를 정해진 공간에 배치해야 했던 경험을 말씀해 주세요. 배치안을 어떻게 정했고, 실제 설치 과정은 어땠나요?",
        "설치 전에 예상한 모습과 실제 놓았을 때의 모습은 어떤 점이 같거나 달랐나요?",
        "다른 쪽에서 보았을 때도 위치와 방향이 맞는지 무엇을 기준으로 확인했나요?",
        "배치를 수정했다면, 어느 부분을 어떻게 바꿨나요?",
    )),
    ("repeated-work-interview-v1", "repeated-work-experience", (
        "비슷한 업무를 같은 방식으로 진행했는데도 결과가 달랐던 경험을 말씀해 주세요. 다음 업무에서는 어떤 방식을 선택했고, 무엇을 근거로 결정했나요?",
        "그때 참고한 이전 결과들은 무엇이었고, 서로 어떻게 비교했나요?",
        "기존 방식을 유지하거나 바꾸기로 한 기준은 무엇이었나요?",
        "다음에는 어떤 결과를 예상했으며, 실제 결과를 확인한 뒤에는 어떻게 판단했나요?",
    )),
)
for group, prefix, prompts in WORK_GROUPS:
    QUESTIONS.extend({
        **deepcopy(QUESTIONS[0]),
        "question_id": f"{prefix}-{index}",
        "question_prompt_version": group,
        "question_text": text,
        "question_group": group,
        "parent_question_id": f"{prefix}-0" if index else None,
    } for index, text in enumerate(prompts))

# Keep v1 definitions available for immutable saved history. Current interviews
# use three baseline questions plus these four optional work questions.
CURRENT_VERSION = 'curated-work-interview-v3'
PREVIOUS_VERSION = 'curated-work-interview-v2'
_old = {q['question_id']: q for q in QUESTIONS}
CURRENT_QUESTIONS = [deepcopy(_old[key]) for key in (
    'wm-experience-0', 'wm-experience-3', 'spatial-work-experience-0')]
CURRENT_QUESTIONS.append({**deepcopy(_old['repeated-work-experience-0']),
    'question_id': 'repeated-work-experience-v2-0',
    'question_version': '2.0.0', 'question_prompt_version': 'repeated-work-interview-v2',
    'question_text': ('비슷한 업무를 같은 방식으로 진행했는데도 결과가 달랐던 경험을 말씀해 주세요. '
        '다음 업무에서는 어떤 방식을 선택했나요? 기존 방식을 유지하거나 바꾸기로 한 기준은 무엇이었나요?'),
    'question_group': 'repeated-work-interview-v2',
})


def add_questions(run):
    """Curate an active interview once; never rewrite prior question/answer evidence."""
    if run.get('status') == 'completed':
        return
    version = run.get('supplemental_interview_set_version')
    if version not in (None, PREVIOUS_VERSION, CURRENT_VERSION):
        from .store import Validation
        raise Validation('validation_error')
    previous = run.get('questions', [])
    existing = {q['question_id']: q for q in previous}
    if version != CURRENT_VERSION and any(q.get('question_mode') == 'supplemental' for q in previous):
        run.setdefault('interview_question_history', []).append({
            'version': version or 'legacy-work-interview-v1',
            'questions': deepcopy([q for q in previous if q.get('question_mode') == 'supplemental'])})
    run['questions'] = [deepcopy(q) for q in previous if q.get('question_mode') != 'supplemental'] + [
        deepcopy(existing.get(q['question_id'], q)) for q in CURRENT_QUESTIONS]
    run['supplemental_interview_set_version'] = CURRENT_VERSION


def questions_need_update(run):
    if run.get('status') == 'completed' or run.get('supplemental_interview_set_version') == CURRENT_VERSION:
        return False
    groups={q['question_group'] for q in QUESTIONS}
    return run.get('flow_version') == 'five-game-v2' or any(
        q.get('question_mode') == 'supplemental' and q.get('question_group') in groups
        for q in run.get('questions', []))


def require_current_questions(run):
    """Modern in-progress results must not regenerate a retired question set."""
    if questions_need_update(run):
        from .store import Conflict
        raise Conflict('interview_question_update_required')


def export_answers(run):
    """Freeze latest answer versions, preserving unasked/empty/skipped states."""
    questions = [q for q in run.get("questions", []) if q.get("question_mode") == "supplemental"]
    records = [r.get("data", {}) for r in run.get("records", []) if r.get("source_type") == "typed_answer"]
    superseded = {(a.get("previous_answer_version_ref") or {}).get("answer_id") for a in records}
    latest = {a.get("question_id"): a for a in records if a.get("answer_id") not in superseded}
    exported = []
    for q in questions:
        a = latest.get(q["question_id"], {})
        exported.append({
            **{key: deepcopy(q.get(key)) for key in (
                "question_id", "question_version", "question_text", "question_mode",
                "question_group", "parent_question_id", "conditioned_on_prior_evidence")},
            "answer_id": a.get("answer_id"), "answer_version": a.get("answer_version"),
            "text": a.get("text", ""), "status": a.get("status", "not_answered"),
            "source_kind": "supplemental_self_report",
        })
    return exported
