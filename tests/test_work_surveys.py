"""Run-versioned work questionnaire; synthetic, no provider calls."""
from copy import deepcopy
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.content import DEFINITIONS
from app.synthesis import build_prompt

H = {'X-Requested-With':'interview-app'}
VERSION = 'work-behavior-v2'
IDS = ['O-B01','O-B02','O-B03','O-PLAN-COMPARE','O-RESULT-LEARNING']
LABELS = ['전혀 그렇지 않다','그렇지 않다','그렇지 않은 편이다','그런 편이다','그렇다','매우 그렇다']

@pytest.fixture
def client(tmp_path):
    application = create_app(f"sqlite:///{tmp_path / 'work-survey.db'}")
    with TestClient(application) as c:
        assert c.post('/api/register',headers=H,json={'username':'work-survey-owner','password':'synthetic-password'}).status_code==201
        yield c
    application.state.store.engine.dispose()

def create(client, **extra):
    r=client.post('/api/runs',headers=H,json=extra)
    assert r.status_code==201, r.text
    return r.json()

def submit(client, run, item, *, status='submitted', response=None, reason=None):
    body={'expected_revision':run['revision'],'idempotency_key':str(uuid4()),
        'item_id':item['item_id'],'item_version':item['item_version'],'status':status,
        'elapsed_ms':100,'response':response if response is not None else {'selected_position':6}}
    if reason is not None: body['nonresponse_reason']=reason
    return client.post(f"/api/runs/{run['run_id']}/surveys",headers=H,json=body),body

def test_new_work_set_is_pinned_and_has_five_six_choice_items(client):
    run=create(client,flow_version='five-game-v2',survey_set_version=VERSION)
    assert run['survey_set_version']==VERSION
    items=run['survey_definition_snapshot']
    assert [i['item_id'] for i in items]==IDS
    assert all(i['type']=='ordinal_6' and [o['label'] for o in i['ordered_options']]==LABELS for i in items)
    assert items[-2]['prompt']=='처리 방법을 선택해야 하는 업무에서는, 방법별로 예상되는 결과를 비교한다.'
    assert items[-1]['prompt']=='비슷한 업무를 반복할 때, 여러 차례의 결과를 비교해 다음 처리 방법을 선택한다.'
    assert client.get(f"/api/runs/{run['run_id']}").json()['survey_definition_snapshot']==items
    assert all(i['item_id'] not in {'P-B01','S-B02','R-UNMAPPED'} for i in items)

def test_legacy_creation_and_prompt_do_not_lose_perspective_or_rank(client):
    legacy=create(client,flow_version='five-game-v2')
    assert 'survey_set_version' not in legacy
    before=build_prompt(legacy)
    assert len([e for e in before['evidence'] if e['source']=='survey'])==6
    assert next(t for t in before['topics'] if t['id']=='preferences')['survey_ids']==['S-B02','R-UNMAPPED']
    assert client.post('/api/runs',headers=H,json={'survey_set_version':'invented'}).status_code==422

def test_no_experience_and_unsure_are_not_disagreement_and_replay_exactly(client):
    run=create(client,flow_version='five-game-v2',survey_set_version=VERSION)
    items=run['survey_definition_snapshot']
    for index,reason in enumerate(('no_experience','unsure')):
        r,body=submit(client,run,items[index],status='skipped',response={},reason=reason)
        assert r.status_code==200,r.text
        run=r.json(); data=run['records'][-1]['data']
        assert data['nonresponse_reason']==reason and 'selected_position' not in data
        assert client.post(f"/api/runs/{run['run_id']}/surveys",headers=H,json=body).json()==run
    for response,status,reason in (({'selected_position':1},'submitted','no_experience'),
                                   ({'selected_position':2},'skipped','unsure'),({},'skipped','invented')):
        r,_=submit(client,run,items[2],status=status,response=response,reason=reason)
        assert r.status_code==422,r.text
    prompt=build_prompt(run)
    e=next(e for e in prompt['evidence'] if e.get('item_id')=='O-B01')
    assert e['status']=='skipped' and e['data']['nonresponse_reason']=='no_experience'
    assert 'selected_position' not in e['data']

def test_wrong_set_is_rejected_and_five_visits_unlock_rule_games(client):
    run=create(client,flow_version='five-game-v2',survey_set_version=VERSION)
    forbidden=next(i for i in DEFINITIONS['surveys'] if i['item_id']=='P-B01')
    assert submit(client,run,forbidden)[0].status_code==422
    for item in run['survey_definition_snapshot']:
        r,_=submit(client,run,item)
        assert r.status_code==200,r.text
        run=r.json()
    r=client.post(f"/api/runs/{run['run_id']}/rule-games",headers=H,json={
        'expected_revision':run['revision'],'idempotency_key':str(uuid4()),'action':'start','game_type':'rsp'})
    assert r.status_code==200,r.text
    prompt=build_prompt(run)
    surveys=[e for e in prompt['evidence'] if e['source']=='survey']
    assert [e['item_id'] for e in surveys]==IDS
    assert all(e['response_type']=='ordinal_6' for e in surveys)
    assert 'O-PLAN-COMPARE' in next(t for t in prompt['topics'] if t['id']=='planning')['survey_ids']
    assert next(t for t in prompt['topics'] if t['id']=='learning')['survey_ids']==['O-RESULT-LEARNING']
    assert next(t for t in prompt['topics'] if t['id']=='working_memory')['survey_ids']==[]

def test_create_idempotency_includes_questionnaire_version(client):
    key=str(uuid4())
    run=create(client,idempotency_key=key,survey_set_version=VERSION,flow_version='five-game-v2')
    assert create(client,idempotency_key=key,survey_set_version=VERSION,flow_version='five-game-v2')==run
    assert client.post('/api/runs',headers=H,json={'idempotency_key':key,'flow_version':'five-game-v2'}).status_code==409

def test_work_set_completion_freezes_nonresponse_and_original_format(client):
    from completion_helpers import finish_required_stages, send
    run=create(client,survey_set_version=VERSION)
    for item in run['survey_definition_snapshot']:
        r,_=submit(client,run,item,status='skipped',response={},reason='no_experience')
        assert r.status_code==200,r.text
        run=r.json()
    run=finish_required_stages(client,run)
    for question in run['questions']:
        run=send(client,run,'answers',question_id=question['question_id'],status='asked_no_text')
    run=send(client,run,'analyze')
    run=send(client,run,'finalize')
    assert run['status']=='completed'
    surveys=[r for r in run['records'] if r['source_type']=='survey']
    assert len(surveys)==5 and all(r['data']['nonresponse_reason']=='no_experience' for r in surveys)
    snapshot=deepcopy(run)
    assert client.get(f"/api/runs/{run['run_id']}").json()==snapshot
    assert submit(client,run,run['survey_definition_snapshot'][0])[0].status_code==409

def test_marked_questionnaire_never_falls_back_to_legacy_on_corrupt_snapshot():
    from app.survey_sets import survey_items, create_snapshot
    items=create_snapshot(VERSION)
    for snapshot in (None,[],items[:1],[items[0]]*5):
        with pytest.raises(ValueError):
            survey_items({'survey_set_version':VERSION,'survey_definition_snapshot':snapshot})

def test_nonresponse_instructions_reach_the_structured_gemini_input(client):
    from app import synthesis
    run=create(client,survey_set_version=VERSION)
    prepared=synthesis.prepare(run,'mock')
    structured=prepared['_structured_input']
    assert 'survey_interpretation' in structured
    wire=synthesis.SynthesisGemini.payload(structured,128,synthesis.schema(),model_id='gemini-2.5-flash')
    assert '판단 어려움' in str(wire)
    assert '비동의가 아닌 결측' in str(wire)
