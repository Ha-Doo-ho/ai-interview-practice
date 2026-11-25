"""Current question selection and immutable legacy evidence; no participant DB."""
from copy import deepcopy
import pytest
from app import supplemental_interview as extra
from test_rule_games import api, HEADERS

TEXT = ('비슷한 업무를 같은 방식으로 진행했는데도 결과가 달랐던 경험을 말씀해 주세요. '
        '다음 업무에서는 어떤 방식을 선택했나요? 기존 방식을 유지하거나 바꾸기로 한 기준은 무엇이었나요?')

def test_new_run_contains_eight_fixed_questions_and_merged_criterion(api):
    client, *_ = api
    run = client.post('/api/runs', headers=HEADERS, json={'flow_version':'five-game-v2'}).json()
    assert len(run['questions']) == 8
    assert [q['question_text'] for q in run['questions'] if q['question_text']==TEXT] == [TEXT]
    assert run['supplemental_interview_set_version']=='curated-work-interview-v2'

def test_active_legacy_upgrade_preserves_original_questions_answers_and_is_idempotent():
    run={'status':'in_progress','questions':deepcopy(extra.QUESTIONS),'records':[{'source_type':'typed_answer','data':{
        'question_id':'wm-experience-1','answer_id':'a1','text':'  original 🙂  ','answer_version':'1.0.0'}}]}
    before=deepcopy(run)
    extra.add_questions(run)
    assert len(run['questions'])==5
    assert run['records']==before['records']
    assert run['interview_question_history'][0]['questions']==before['questions']
    assert not any(q['question_id']=='wm-experience-1' for q in run['questions'])
    after=deepcopy(run)
    extra.add_questions(run)
    assert run==after

def test_reworded_root_and_child_have_new_ids_and_preserve_old_answer_identity():
    run={'questions':[],'records':[]}
    extra.add_questions(run)
    group=[q for q in run['questions'] if q['question_group']=='repeated-work-interview-v2']
    assert len(group)==2
    root,child=group
    assert root['question_text']==TEXT
    assert root['question_id']!='repeated-work-experience-0'
    assert child['question_id']!='repeated-work-experience-3'
    assert child['parent_question_id']==root['question_id']

def test_completed_question_snapshot_is_not_upgraded():
    run={'status':'completed','questions':deepcopy(extra.QUESTIONS),'records':[],
         'report':{'supplemental_answers':[{'question_text':'historical','text':'original'}]}}
    before=deepcopy(run)
    extra.add_questions(run)
    assert run==before

def test_direct_synthesis_prepare_rejects_unconverted_modern_interview():
    from app.synthesis import prepare
    from app.store import Conflict
    from app.content import QUESTIONS
    run={'flow_version':'five-game-v2','questions':deepcopy(QUESTIONS)+deepcopy(extra.QUESTIONS),'records':[]}
    with pytest.raises(Conflict, match='interview_question_update_required'):
        prepare(run,'mock')

def test_retired_answers_stay_in_history_but_not_current_prompt():
    from app.synthesis import build_prompt
    from app.content import QUESTIONS
    run={'questions':deepcopy(QUESTIONS)+deepcopy(extra.QUESTIONS),'records':[]}
    run['records'].append({'source_type':'typed_answer','data':{'question_id':'wm-experience-1',
        'answer_id':'retired','text':'retired unique answer','status':'asked_answered'}})
    extra.add_questions(run)
    prompt=build_prompt(run)
    assert len([e for e in prompt['evidence'] if e['source']=='interview' and e['mode'] in ('baseline','supplemental')])==8
    assert 'retired unique answer' not in prompt['prompt_text']
    assert run['records'][-1]['data']['text']=='retired unique answer'

def test_archive_does_not_copy_conditioned_disclosures_into_a_new_public_path():
    conditioned={'question_id':'adaptive-private','question_mode':'adaptive_followup',
        'question_text':'private derived question','disclosed_prior_information':['private derived evidence']}
    run={'questions':[conditioned]+deepcopy(extra.QUESTIONS),'records':[]}
    extra.add_questions(run)
    assert run['interview_question_history'][0]['questions']==extra.QUESTIONS
    assert run['questions'][0]==conditioned

def test_legacy_supplemental_set_also_requires_curation_without_modern_flow_flag():
    from app.store import Conflict
    run={'questions':deepcopy(extra.QUESTIONS)}
    with pytest.raises(Conflict,match='interview_question_update_required'):
        extra.require_current_questions(run)

def test_old_client_cannot_write_retired_question_before_curating_an_active_run(api):
    from uuid import uuid4
    client,application,_,run,_=api
    def legacy(snapshot):
        snapshot['flow_version']='five-game-v2'
        snapshot['questions'].extend(deepcopy(extra.QUESTIONS))
    run=application.state.store.mutate(run['user_id'],run['run_id'],run['revision'],'legacy-fixture',str(uuid4()),{},legacy)
    response=client.post(f"/api/runs/{run['run_id']}/answers",headers=HEADERS,json={
        'expected_revision':run['revision'],'idempotency_key':str(uuid4()),'question_id':'wm-experience-1','text':'new retired response'})
    assert response.status_code==409
    assert response.json()['error']=='interview_question_update_required'

def test_legacy_synthesis_is_not_presented_as_current_before_question_upgrade():
    from app.main import _public_snapshot
    from app.synthesis import build_prompt
    run={'questions':deepcopy(extra.QUESTIONS),'records':[],'status':'in_progress'}
    run['synthesis_analysis']={'input_snapshot':{'source_digest':build_prompt(run)['source_digest']}}
    public=_public_snapshot(run)
    assert public['synthesis_analysis_stale'] is True

def test_replayed_old_synthesis_stays_stale_after_current_run_is_upgraded():
    from app.main import _public_snapshot
    from app.synthesis import build_prompt
    old={'questions':deepcopy(extra.QUESTIONS),'records':[],'status':'in_progress'}
    old['synthesis_analysis']={'input_snapshot':{'source_digest':build_prompt(old)['source_digest']}}
    current=deepcopy(old);extra.add_questions(current)
    assert _public_snapshot(old,visibility_snapshot=current)['synthesis_analysis_stale'] is True
