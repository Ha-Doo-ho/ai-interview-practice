"""Approved policies: main-round threshold and server-side reveal visibility.

These catch premature job writes, future-condition disclosure on any response,
and accidental redaction of immutable stored evidence. Run via tools.run_checks.
"""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.content import DEFINITIONS
from app.main import create_app
from app.store import Base,RunRow,IdempotencyRow
from completion_helpers import HEADERS,send,finish_required_stages

def db(store):
    with Session(store.engine) as s:
        return {t.name: sorted([tuple(r) for r in s.execute(select(t))],key=repr) for t in Base.metadata.sorted_tables}

@pytest.fixture
def fx(tmp_path,monkeypatch):
    clock=[datetime(2026,9,25,tzinfo=timezone.utc)]
    monkeypatch.setattr('app.game._now',lambda:clock[0])
    app=create_app(f"sqlite:///{tmp_path/'disclosure.db'}")
    try:
        with TestClient(app,raise_server_exceptions=False) as client:
            assert client.post('/api/register',headers=HEADERS,json={'username':'policy-demo','password':'synthetic-password'}).status_code==201
            run=client.post('/api/runs',headers=HEADERS,json={}).json()
            yield client,app.state.store,run,clock
    finally:app.state.store.engine.dispose()

def finish(client,run):
    for action,kw in [('start',{}),('allocate',{'personal':4}),('reveal',{}),('revise',{'personal':5})]:
        run=send(client,run,'game',action=action,**kw)
    return run

def assert_hidden(round_state):
    assert 'text' not in round_state['new_information']
    assert 'updated_requirements' not in round_state['new_information']
    assert 'final_requirements' not in round_state
    assert 'reward_table_final' not in round_state

@pytest.mark.parametrize('stage',['new','practice_complete','practice_timeout','main_started','main_allocated','main_revealed'])
def test_analysis_rejects_before_first_main_completion_without_db_writes(fx,stage):
    c,s,r,clock=fx
    if stage=='practice_timeout':
        r=send(c,r,'game',action='start')
        clock[0]=datetime.fromisoformat(r['game']['rounds'][0]['deadline_at'])+timedelta(microseconds=1)
        r=send(c,r,'game',action='timeout')
    elif stage!='new':r=finish(c,r)
    if stage.startswith('main_'):
        r=send(c,r,'game',action='next');r=send(c,r,'game',action='start')
        if stage in {'main_allocated','main_revealed'}:r=send(c,r,'game',action='allocate',personal=4)
        if stage=='main_revealed':r=send(c,r,'game',action='reveal')
    before=db(s)
    response=c.post(f"/api/runs/{r['run_id']}/analyze",headers=HEADERS,json={'expected_revision':r['revision'],'idempotency_key':str(uuid4())})
    assert response.status_code==409 and response.json()=={'error':'main_round_completion_required'}
    assert db(s)==before
    assert c.get(f"/api/runs/{r['run_id']}").json()==r

@pytest.mark.parametrize('ending',['normal','timeout'])
def test_partial_analysis_after_one_main_round_and_continue(fx,ending):
    c,s,r,clock=fx
    r=finish(c,r);r=send(c,r,'game',action='next')
    if ending=='normal':r=finish(c,r)
    else:
        r=send(c,r,'game',action='start')
        clock[0]=datetime.fromisoformat(r['game']['rounds'][1]['deadline_at'])+timedelta(microseconds=1)
        r=send(c,r,'game',action='timeout')
    originals=deepcopy(r['game'])
    r=send(c,r,'analyze')
    assert r['game']==originals and r['status']=='in_progress' and r['report'] is None
    assert r['report_draft']['runtime_mode']=='mock'
    for rr in r['game']['rounds'][2:]:assert_hidden(rr)
    if ending=='timeout':
        assert_hidden(r['game']['rounds'][1])
        b03=next(m for m in r['analysis']['metrics'] if m['behavior_id']=='B03')
        assert b03['denominator']==0 and b03['value'] is None
    r=send(c,r,'game',action='next')
    assert r['game']['round_index']==2
    for q in DEFINITIONS['questions']:r=send(c,r,'answers',question_id=q['question_id'],status='skipped')
    r=finish_required_stages(c,r)
    r=send(c,r,'finalize')
    assert r['status']=='completed' and r['report']['runtime_mode']=='mock'
    assert c.get(f"/api/runs/{r['run_id']}").json()==r
    if ending=='timeout':assert_hidden(r['game']['rounds'][1])

def test_visibility_across_definitions_create_mutations_list_get_and_retry(fx):
    c,s,r,_=fx
    original_definitions=deepcopy(DEFINITIONS)
    definition=c.get('/api/definitions').json()
    for rr in definition['game']['rounds']:assert_hidden(rr)
    for rr in r['game']['rounds']:assert_hidden(rr)
    # All paths return a public projection; storage retains future conditions.
    for endpoint,fields in [('surveys',{'item_id':'O-B01','item_version':'1.0.0','status':'skipped'}),
                            ('answers',{'question_id':'baseline-b01','status':'skipped'}),
                            ('game',{'action':'start'}),('game',{'action':'open_info'}),('game',{'action':'allocate','personal':4})]:
        payload={'expected_revision':r['revision'],'idempotency_key':str(uuid4()),**fields}
        response=c.post(f"/api/runs/{r['run_id']}/{endpoint}",headers=HEADERS,json=payload)
        assert response.status_code==200,response.text
        r=response.json()
        for rr in r['game']['rounds']:assert_hidden(rr)
        assert c.post(f"/api/runs/{r['run_id']}/{endpoint}",headers=HEADERS,json=payload).json()==r
        assert c.get(f"/api/runs/{r['run_id']}").json()==r
        assert c.get('/api/runs').json()['runs'][0]==r
    before_reveal=deepcopy(r)
    old_payload=payload
    r=send(c,r,'game',action='reveal')
    assert r['game']['rounds'][0]['new_information']['text']==DEFINITIONS['game']['rounds'][0]['new_information']['text']
    assert r['game']['rounds'][0]['reward_table']==DEFINITIONS['game']['rounds'][0]['reward_table_final']
    for rr in r['game']['rounds'][1:]:assert_hidden(rr)
    assert c.post(f"/api/runs/{r['run_id']}/game",headers=HEADERS,json=old_payload).json()==before_reveal
    with Session(s.engine) as session:
        stored=session.get(RunRow,r['run_id']).snapshot
        for rr,source in zip(stored['game']['rounds'],DEFINITIONS['game']['rounds']):
            assert rr['final_requirements']==source['final_requirements']
            assert rr['new_information']['text']==source['new_information']['text']
        cache=session.scalars(select(IdempotencyRow).where(IdempotencyRow.run_id==r['run_id'])).all()
        assert cache and all(row.response['game']['rounds'][3]['final_requirements'] for row in cache)
    assert DEFINITIONS==original_definitions

def test_legacy_idempotent_response_is_filtered_without_rewriting_storage(fx):
    c,s,r,_=fx
    payload={'expected_revision':r['revision'],'idempotency_key':'synthetic-pre-policy'}
    # Synthetic historical success with no completed main round.
    saved=s.mutate(r['user_id'],r['run_id'],r['revision'],'analyze',payload['idempotency_key'],payload,lambda snapshot:None)
    before=db(s)
    response=c.post(f"/api/runs/{r['run_id']}/analyze",headers=HEADERS,json=payload)
    assert response.status_code==200
    for rr in response.json()['game']['rounds']:assert_hidden(rr)
    assert db(s)==before
    assert saved['game']['rounds'][0]['final_requirements']

def test_real_mock_all_response_branches_keep_future_canaries_private(fx,monkeypatch):
    c,s,r,_=fx
    marker='SYNTHETIC-FUTURE-CONDITION-NOT-DISCLOSED-9382'
    changed=deepcopy(DEFINITIONS)
    future=changed['game']['rounds'][3]
    future['new_information']['text']=marker
    future['new_information']['updated_requirements']['prerequisite']=marker
    future['final_requirements']['prerequisite']=marker
    future['reward_table_final'][0]['condition']=marker
    # Synthetic definition only, before creating a fresh run. No real data.
    monkeypatch.setattr('app.main.DEFINITIONS',changed)
    monkeypatch.setattr('app.content.DEFINITIONS',changed)
    assert marker not in json.dumps(c.get('/api/definitions').json())
    r=c.post('/api/runs',headers=HEADERS,json={}).json()
    assert marker not in json.dumps(r)
    r=finish(c,r);r=send(c,r,'game',action='next');r=finish(c,r)
    payload={'expected_revision':r['revision'],'idempotency_key':str(uuid4())}
    analyzed=c.post(f"/api/runs/{r['run_id']}/analyze",headers=HEADERS,json=payload)
    assert analyzed.status_code==200,analyzed.text
    r=analyzed.json()
    for response in [r,c.get('/api/runs').json(),c.get(f"/api/runs/{r['run_id']}").json(),
                     c.post(f"/api/runs/{r['run_id']}/analyze",headers=HEADERS,json=payload).json()]:
        assert marker not in json.dumps(response)
    for q in DEFINITIONS['questions']:r=send(c,r,'answers',question_id=q['question_id'],status='skipped')
    # Future main3 times out before reveal. Finalization cannot make it public.
    r=finish_required_stages(c,r,monkeypatch=monkeypatch,timeout=True)
    r=send(c,r,'finalize')
    assert marker not in json.dumps(r)
    with Session(s.engine) as session:
        assert marker in json.dumps(session.get(RunRow,r['run_id']).snapshot)
