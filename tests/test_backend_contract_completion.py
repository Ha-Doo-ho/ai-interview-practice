"""Fill the concrete API/DB gaps in command3. Run only via tools.run_checks.

The contract's requests are fixtures; explicit assertions below check business
meaning as well as SQL persistence. No policy change or external model call.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest
from httpx import Cookies
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import analysis
from app.content import DEFINITIONS
from app.main import create_app
from app.store import Base, RunRow, UserRow, SessionRow, JobRow, CacheRow, IdempotencyRow, _digest
from completion_helpers import finish_required_stages,finish_one_main_round,assert_public_matches_storage

HEADERS={'X-Requested-With':'interview-app'}
PASSWORD='synthetic-password'
CONTRACT=Path(__file__).resolve().parents[1]/'docs/ai-interview/backend-readiness/20260920-003025-KST/API_SCENARIOS.json'
CASES={c['id']:c for c in json.loads(CONTRACT.read_text(encoding='utf-8'))['cases']}


def db(store):
    with Session(store.engine) as session:
        return {t.name:sorted([dict(r) for r in session.execute(select(t)).mappings()],key=repr) for t in Base.metadata.sorted_tables}


class Harness:
    def __init__(self, client, app, url, clock):
        self.client,self.app,self.store,self.url,self.clock=client,app,app.state.store,url,clock
        self.user=self.register('contract-owner')
        self.run=self.create()

    def register(self, name):
        response=self.client.post('/api/register',headers=HEADERS,json={'username':name,'password':PASSWORD})
        assert response.status_code==201,response.text
        assert set(response.json())=={'user_id','username'}
        cookie=response.headers['set-cookie'].lower()
        assert all(s in cookie for s in ['httponly','samesite=strict','path=/','max-age=43200']) and '; secure' not in cookie
        token=self.client.cookies.get('interview_session')
        with Session(self.store.engine) as session:
            user=session.get(UserRow,response.json()['user_id'])
            assert user.password_hash and PASSWORD not in user.password_hash
            assert session.get(SessionRow,hashlib.sha256(token.encode()).hexdigest()).user_id==user.user_id
            assert token not in repr(db(self.store))
        return response.json()

    def create(self):
        before=db(self.store)
        response=self.client.post('/api/runs',headers=HEADERS,json={})
        assert response.status_code==201,response.text
        after=db(self.store)
        assert len(after['practice_runs'])==len(before['practice_runs'])+1
        assert all(before[t]==after[t] for t in before if t!='practice_runs')
        with Session(self.store.engine) as session:
            row=session.get(RunRow,response.json()['run_id'])
            assert assert_public_matches_storage(row.snapshot,response.json()) and row.revision==0
        return response.json()

    def payload(self, **kw):
        return {'expected_revision':self.run['revision'],'idempotency_key':str(uuid4()),**kw}

    def resolve(self, value):
        if isinstance(value,dict):return {k:self.resolve(v) for k,v in value.items()}
        if isinstance(value,list):return [self.resolve(v) for v in value]
        if value=='${run.revision}':return self.run['revision']
        if value=='${case_id}-${request_index}':return str(uuid4())
        return value

    def saved(self):
        assert self.client.get('/api/runs/'+self.run['run_id']).json()==self.run
        with Session(self.store.engine) as session:
            row=session.get(RunRow,self.run['run_id'])
            assert assert_public_matches_storage(row.snapshot,self.run) and row.revision==self.run['revision'] and row.status==self.run['status']

    def accept(self, endpoint, **kw):
        payload=self.payload(**kw)
        before=db(self.store);old=deepcopy(self.run)
        response=self.client.post(f"/api/runs/{old['run_id']}/{endpoint}",headers=HEADERS,json=payload)
        assert response.status_code==200,response.text
        self.run=response.json();after=db(self.store)
        assert self.run['revision']==old['revision']+1
        assert len(after['idempotency_results'])==len(before['idempotency_results'])+1
        with Session(self.store.engine) as session:
            entry=session.scalar(select(IdempotencyRow).where(IdempotencyRow.idempotency_key==payload['idempotency_key']))
            assert assert_public_matches_storage(entry.response,self.run) and entry.request_digest==_digest(payload)
            operation={'surveys':'survey','answers':'answer'}.get(endpoint,endpoint)
            assert (entry.user_id,entry.run_id,entry.operation)==(self.user['user_id'],old['run_id'],operation)
        for table in ['users','auth_sessions']+(['analysis_jobs','derived_cache'] if endpoint in {'game','surveys','answers'} else []):
            assert before[table]==after[table]
        assert [r for r in before['practice_runs'] if r['run_id']!=old['run_id']]==[r for r in after['practice_runs'] if r['run_id']!=old['run_id']]
        self.saved()
        return payload

    def reject(self, endpoint, code, status=422, payload=None):
        before=db(self.store)
        response=self.client.post(f"/api/runs/{self.run['run_id']}/{endpoint}",headers=HEADERS,json=payload)
        assert response.status_code==status and response.json()=={'error':code},response.text
        assert db(self.store)==before
        self.saved()

    def finish_round(self):
        for action,kw in [('start',{}),('open_info',{}),('allocate',{'personal':4}),('reveal',{}),('revise',{'personal':5})]:
            self.accept('game',action=action,**kw)

    def full(self):
        for item in DEFINITIONS['surveys']:
            kind=item['type']
            response={'selected_position':3} if kind=='ordinal_6' else (
                {'self':{'status':'submitted','selected_position':4},'imagined_others':{'status':'submitted','selected_position':2}} if kind=='paired_perspective' else (
                {'final_value':0,'interaction_occurred':False,'explicit_confirmation':True,'change_count':0} if kind=='bipolar_slider' else
                {'selected_ids':['growth','autonomy','helping'],'selection_events':[]}))
            self.accept('surveys',item_id=item['item_id'],item_version=item['item_version'],status='submitted',response=response)
        for i in range(4):
            self.finish_round()
            if i<3:self.accept('game',action='next')
        for q in DEFINITIONS['questions']:
            self.accept('answers',question_id=q['question_id'],text='합성 기본 답변: 저는 팀원에게 조건을 물었습니다.')


@pytest.fixture
def h(tmp_path,monkeypatch):
    clock=[datetime(2026,9,25,tzinfo=timezone.utc)]
    monkeypatch.setattr('app.game._now',lambda:clock[0])
    url=f"sqlite:///{tmp_path/'contract.db'}"
    app=create_app(url)
    try:
        with TestClient(app,raise_server_exceptions=False) as client:
            yield Harness(client,app,url,clock)
    finally:app.state.store.engine.dispose()


REJECT_CASES=['API-REV-BOOL','API-REV-NEG','API-KEY-NULL','API-KEY-LONG','API-REV-STALE',
 'API-SURVEY-BAD-POSITION','API-SURVEY-BAD-VERSION','API-SURVEY-BAD-RANK-DUP','API-SURVEY-BAD-SLIDER-CONFIRM',
 'API-SURVEY-DUP','API-GAME-STAGE','API-GAME-DOUBLE-OPEN','API-GAME-BOUND','API-GAME-LAST','API-ANSWER-BAD']


@pytest.mark.parametrize('cid',REJECT_CASES)
def test_contract_rejections_preserve_every_table(h,cid):
    fixture=CASES[cid]['preconditions']['fixture']
    if fixture in {'started','opened'}:
        h.accept('game',action='start')
        if fixture=='opened':h.accept('game',action='open_info')
    elif fixture=='game_complete':
        for i in range(4):
            h.finish_round()
            if i<3:h.accept('game',action='next')
    elif fixture=='survey_o_b01':
        h.accept('surveys',item_id='O-B01',item_version='1.0.0',status='submitted',response={'selected_position':3})
    else:assert fixture=='owner_run',fixture
    expected=CASES[cid]['expected_response']
    statuses=expected['http_status']
    code=expected['assertions'][0].removeprefix('error ')
    for index,request in enumerate(CASES[cid]['requests']):
        h.reject(request['path'].rsplit('/',1)[1],code,statuses[index] if isinstance(statuses,list) else statuses,h.resolve(request['json']))


@pytest.mark.parametrize('item_id',['O-B01','P-B01','S-B02','R-UNMAPPED'])
def test_survey_original_values_sql_and_exact_retry(h,item_id):
    request=deepcopy(CASES['API-SURVEY-'+item_id]['requests'][0]['json'])
    payload=h.resolve(request)
    payload.pop('expected_revision');payload.pop('idempotency_key')
    old=deepcopy(h.run)
    actual_payload=h.accept('surveys',**payload)
    record=h.run['records'][-1];data=record['data']
    assert h.run['records'][:-1]==old['records'] and record['source_type']=='survey'
    assert record['item_id']==item_id and record['item_version']=='1.0.0'
    def keys(value):
        if isinstance(value,dict):return set(value)|set().union(*(keys(v) for v in value.values()))
        if isinstance(value,list):return set().union(*(keys(v) for v in value))
        return set()
    assert not {'probability','personality_score','trait_score','ability_score','truth_probability','consistency_score','percent','normalized_score'}&keys(record)
    original=payload['response']
    if item_id=='O-B01':
        assert data['selected_position']==original['selected_position'] and len(data['ordered_options_snapshot'])==6
    elif item_id=='P-B01':
        for perspective in ['self','imagined_others']:
            assert data[perspective]['selected_position']==original[perspective]['selected_position']
            assert data[perspective]['perspective']==perspective
    elif item_id=='S-B02':
        for field in ['final_value','interaction_occurred','explicit_confirmation','change_count']:assert data[field]==original[field]
    else:
        assert data['ranked_selection']==[{'option_id':v,'rank':i+1} for i,v in enumerate(original['selected_ids'])]
        assert data['selection_events']==original['selection_events']
    before=db(h.store)
    retry=h.client.post(f"/api/runs/{h.run['run_id']}/surveys",headers=HEADERS,json=actual_payload)
    assert retry.status_code==200 and retry.json()==h.run and db(h.store)==before
    changed=deepcopy(actual_payload);changed['elapsed_ms']=1
    h.reject('surveys','idempotency_conflict',409,changed)


def test_missing_surveys_and_missing_answers_preserve_absence(h):
    for request in CASES['API-SURVEY-MISSING']['requests']:
        kw=h.resolve(request['json']);kw.pop('expected_revision');kw.pop('idempotency_key')
        h.accept('surveys',**kw)
    ordinal,paired,slider,ranked=[r['data'] for r in h.run['records']]
    assert len(ordinal['ordered_options_snapshot'])==6 and not any(k.startswith('selected_') for k in ordinal)
    assert paired['self']['selected_position']==4 and 'selected_position' not in paired['imagined_others']
    assert slider['final_value'] is None and slider['missing_reason']=='timed_out_without_interaction'
    assert ranked['submitted_count']==1 and ranked['ranked_selection']==[{'option_id':'growth','rank':1}]
    before_answers=db(h.store);revision=h.run['revision'];record_count=len(h.run['records'])
    for index,(q,status) in enumerate(zip(DEFINITIONS['questions'],['asked_no_text','skipped','asked_no_text'])):
        h.accept('answers',question_id=q['question_id'],status=status)
        assert h.run['records'][-1]['data']['text']=='' and h.run['records'][-1]['status']==status
        if index==1:
            assert len(h.run['records'])==record_count+2 and h.run['revision']==revision+2
            assert len(db(h.store)['idempotency_results'])==len(before_answers['idempotency_results'])+2
    originals=deepcopy(h.run['records'])
    h.run=finish_one_main_round(h.client,h.run)
    h.accept('analyze')
    h.run=finish_required_stages(h.client,h.run)
    h.accept('finalize')
    assert h.run['status']=='completed' and h.run['completed_at'] and h.run['report']['runtime_mode']=='mock'
    assert h.run['records'][:len(originals)]==originals and h.run['game']['phase']=='complete'


def test_answer_versions_keep_original_and_reject_wrong_or_reused_reference(h):
    q=DEFINITIONS['questions'][0]
    submitted='  합성 이전 답변🙂  '
    h.accept('answers',question_id=q['question_id'],text=submitted)
    original=deepcopy(h.run['records'][0]);d=original['data']
    assert d['text']==submitted
    assert d['question_text_snapshot']==q['question_text'] and d['answer_version']=='1.0.0'
    assert original['record_id']!=d['answer_id'] and original['source_version']=='1.0.0'
    assert d['previous_answer_version_ref'] is None and d['question_version']==q['question_version']
    assert d['question_mode']==q['question_mode'] and d['disclosed_prior_information']==q.get('disclosed_prior_information',[])
    h.accept('answers',question_id=q['question_id'],text='합성 정정 답변',replaces_answer_id=d['answer_id'],expected_answer_version='1.0.0')
    latest=h.run['records'][-1]
    assert h.run['records'][0]==original
    assert latest['data']['answer_id']!=d['answer_id'] and latest['data']['answer_version']==latest['source_version']=='2.0.0'
    assert latest['record_version']=='1.0.0'
    assert latest['data']['previous_answer_version_ref']=={'answer_id':d['answer_id'],'answer_version':'1.0.0'}
    for ref in [latest['data']['answer_id'],d['answer_id']]:
        h.reject('answers','answer_version_conflict',409,h.payload(question_id=q['question_id'],text='합성',replaces_answer_id=ref,expected_answer_version='1.0.0'))


def test_auth_cookie_csrf_json_and_definition_contract(h):
    before=db(h.store)
    saved_cookie=Cookies(h.client.cookies);h.client.cookies.clear()
    definitions=h.client.get('/api/definitions')
    assert definitions.status_code==200 and {'version','scale','surveys','behaviors','mappings','game','questions','runtime_mode'}<=definitions.json().keys()
    assert len(definitions.json()['surveys'])==6 and len(definitions.json()['questions'])==3 and definitions.json()['runtime_mode']=='mock'
    assert db(h.store)==before
    h.client.cookies.update(saved_cookie)
    assert h.client.get('/api/me').json()==h.user and set(h.user)=={'user_id','username'}
    assert db(h.store)==before
    old_cookie=h.client.cookies.get('interview_session')
    logout=h.client.post('/api/logout',headers=HEADERS)
    assert logout.status_code==204 and logout.content==b'' and h.client.cookies.get('interview_session') is None
    with Session(h.store.engine) as session:assert session.get(SessionRow,hashlib.sha256(old_cookie.encode()).hexdigest()) is None
    assert h.client.get('/api/me').status_code==401
    before=db(h.store)
    csrf=h.client.post(f"/api/runs/{h.run['run_id']}/game",json={'action':'start'})
    assert csrf.status_code==403 and csrf.json()=={'error':'csrf_required'} and db(h.store)==before
    login=h.client.post('/api/login',headers=HEADERS,json={'username':'contract-owner','password':PASSWORD})
    assert login.status_code==200 and login.json()==h.user
    cookie=login.headers['set-cookie'].lower()
    assert all(s in cookie for s in ['httponly','samesite=strict','path=/','max-age=43200']) and '; secure' not in cookie
    assert h.client.cookies.get('interview_session')!=old_cookie
    with Session(h.store.engine) as session:
        assert session.get(SessionRow,hashlib.sha256(h.client.cookies.get('interview_session').encode()).hexdigest()).user_id==h.user['user_id']
    for raw in ['null','[]','{']:
        before=db(h.store)
        response=h.client.post('/api/runs',headers=HEADERS,content=raw)
        assert response.status_code==422 and response.json()=={'error':'validation_error'} and db(h.store)==before
    for path,payload,status,code in [('/api/login',{'username':[],'password':None},401,'invalid_credentials'),
            ('/api/register',{'username':[],'password':PASSWORD},422,'validation_error'),
            ('/api/register',{'username':'contract-owner','password':PASSWORD},409,'username_taken')]:
        cookies=Cookies(h.client.cookies);h.client.cookies.clear()
        before=db(h.store);response=h.client.post(path,headers=HEADERS,json=payload)
        assert response.status_code==status and response.json()=={'error':code} and db(h.store)==before
        h.client.cookies.update(cookies)
    with Session(h.store.engine) as session:
        for row in session.scalars(select(SessionRow)):row.expires_at=datetime(2000,1,1,tzinfo=timezone.utc)
        session.commit()
    before=db(h.store)
    expired=h.client.get('/api/runs/'+h.run['run_id'])
    assert expired.status_code==401 and expired.json()=={'error':'unauthorized'} and db(h.store)==before


def test_new_runs_listing_and_missing_only_finalize_contract(h):
    first=deepcopy(h.run)
    assert first['revision']==0 and first['generation']==0 and first['status']=='in_progress'
    assert first['records']==[] and first['game']['phase']=='awaiting_start'
    assert first['questions']==DEFINITIONS['questions']
    assert all(first[k] is None for k in ['analysis','report_draft','report','completed_at'])
    second=h.create()
    assert second['run_id']!=first['run_id'] and second['attempt_id']!=first['attempt_id']
    assert h.client.get('/api/runs').json()['runs']==[second,first]
    h.saved()
    for index,q in enumerate(DEFINITIONS['questions']):
        h.accept('answers',question_id=q['question_id'],status='skipped' if index==1 else 'asked_no_text')
    h.run=finish_one_main_round(h.client,h.run)
    original=deepcopy(h.run)
    h.accept('analyze')
    h.reject('finalize','survey_responses_required',409,h.payload())
    assert h.run['status']=='in_progress' and h.run['completed_at'] is None and h.run['report'] is None
    assert h.run['records']==original['records'] and h.run['game']==original['game']
    assert len(h.run['records'])==3 and all(r['source_type']=='typed_answer' for r in h.run['records'])
    assert all(m['denominator']==1 for m in h.run['analysis']['metrics'])


def test_full_mock_pipeline_restart_versions_and_read_only_queries(h):
    h.full()
    originals=deepcopy(h.run['records'])
    analyze_payload=h.accept('analyze')
    baseline=deepcopy([e for e in h.run['analysis']['extractions'] if e['mode']=='baseline'])
    assert len(baseline)==3 and h.run['report'] is None
    before=db(h.store)
    retry=h.client.post(f"/api/runs/{h.run['run_id']}/analyze",headers=HEADERS,json=analyze_payload)
    assert retry.status_code==200 and retry.json()==h.run and db(h.store)==before
    for q in h.run['questions']:
        if q['question_mode']=='baseline':
            assert len(q['asked_criteria'])==(6 if q['behavior_id']=='B02' else 7)
            if q['behavior_id']=='B02':assert 'other_information' not in q['asked_criteria']
        else:assert q['asked_criteria']==['reasoning'] and q['conditioned_on_prior_evidence'] is True
    questions={q['question_id']:deepcopy(q) for q in h.run['questions']}
    followups=[q for q in h.run['questions'] if q['question_mode']=='adaptive_followup']
    assert followups
    for q in followups:h.accept('answers',question_id=q['question_id'],text='합성 후속 답변: 조건을 확인했습니다.')
    finalize_payload=h.accept('finalize')
    assert h.run['status']=='completed' and h.run['completed_at']
    report=h.run['report']
    assert report['runtime_mode']=='mock' and report['model_id'] is None
    assert report['lineage']['conditioned_followup_refs']
    assert all(c['runtime_mode']=='mock' for c in report['cards'])
    immutable=('extraction_id','version','answer_id','answer_version','question_id','question_version','mode','criteria','answer_evidence_spans')
    actual=[e for e in h.run['analysis']['extractions'] if e['mode']=='baseline']
    assert [{k:e[k] for k in immutable} for e in actual]==[{k:e[k] for k in immutable} for e in baseline]
    assert h.run['records'][:len(originals)]==originals
    assert any(e['mode']=='conditioned_followup' for e in h.run['analysis']['extractions'])
    records={r['data']['answer_id']:r for r in h.run['records'] if r['source_type']=='typed_answer'}
    for e in h.run['analysis']['extractions']:
        record=records[e['answer_id']];q=questions[e['question_id']]
        assert e['answer_version']==record['data']['answer_version']
        assert e['question_version']==q['question_version']
        assert (e['mode']=='baseline')==(q['question_mode']=='baseline')
        for criterion,item in e['criteria'].items():
            assert item['status']==('unassessable' if criterion in q['asked_criteria'] else 'not_asked')
            assert item['missing_reason']==('mock_semantic_assessment_not_performed' if criterion in q['asked_criteria'] else 'criterion_not_asked')
        for span in e['answer_evidence_spans']:
            assert span['source_id']==e['answer_id'] and span['source_version']==e['answer_version']
            assert record['data']['text'][span['start']:span['end']]==span['quote']
    before=db(h.store)
    replay=h.client.post(f"/api/runs/{h.run['run_id']}/finalize",headers=HEADERS,json=finalize_payload)
    assert replay.status_code==200 and replay.json()==h.run and db(h.store)==before
    for endpoint,kw in [('game',{'action':'start'}),('surveys',{'item_id':'O-B01','item_version':'1.0.0','status':'submitted','response':{'selected_position':3}}),('answers',{'question_id':'baseline-b01','text':'합성'}),('analyze',{})]:
        h.reject(endpoint,'stale_after_finalize',409,h.payload(**kw))
    with Session(h.store.engine) as session:
        jobs=session.scalars(select(JobRow)).all();caches=session.scalars(select(CacheRow)).all()
        assert jobs and caches
        for row in jobs+caches:
            assert row.user_id==h.user['user_id'] and row.run_id==h.run['run_id'] and row.attempt_id==h.run['attempt_id']
        assert all(j.status=='succeeded' and j.result is not None for j in jobs)
    # A separate application and engine load the same fixture DB and existing cookie.
    restarted=create_app(h.url)
    try:
        with TestClient(restarted) as other:
            other.cookies.update(h.client.cookies)
            assert other.get('/api/runs/'+h.run['run_id']).json()==h.run
            listing=other.get('/api/runs').json()['runs']
            assert h.run['run_id'] in [r['run_id'] for r in listing]
            assert db(restarted.state.store)==before
    finally:restarted.state.store.engine.dispose()


@pytest.mark.parametrize('target',['run','account'])
def test_two_users_ownership_deletion_and_associated_sql_records(h,target):
    h.full();h.accept('analyze')
    owner_cookie=Cookies(h.client.cookies)
    owner_run=deepcopy(h.run)
    other_user=h.register('contract-other');other_run=h.create()
    other_cookie=Cookies(h.client.cookies)
    before=db(h.store)
    # A foreign cookie must not read, mutate, analyze, finalize or delete the owner run.
    for method,suffix,payload in [('GET','',None),('DELETE','',None),('POST','/game',h.payload(action='start')),
             ('POST','/surveys',h.payload(item_id='O-B01',item_version='1.0.0',status='submitted',response={'selected_position':3})),
             ('POST','/answers',h.payload(question_id='baseline-b01',text='합성')),('POST','/analyze',h.payload()),('POST','/finalize',h.payload())]:
        response=h.client.request(method,'/api/runs/'+owner_run['run_id']+suffix,headers=HEADERS,json=payload)
        assert response.status_code==404 and response.json()=={'error':'not_found'},response.text
        assert db(h.store)==before
    assert [r['run_id'] for r in h.client.get('/api/runs').json()['runs']]==[other_run['run_id']]
    h.client.cookies.clear();h.client.cookies.update(owner_cookie)
    assert [r['run_id'] for r in h.client.get('/api/runs').json()['runs']]==[owner_run['run_id']]
    second=None
    if target=='account':
        second=h.create()  # All active owner runs must be scrubbed.
    before=db(h.store)
    path='/api/account' if target=='account' else '/api/runs/'+owner_run['run_id']
    deleted=h.client.delete(path,headers=HEADERS)
    assert deleted.status_code==204 and deleted.content==b''
    if target=='account':assert h.client.cookies.get('interview_session') is None
    after=db(h.store)
    for table,rows in before.items():
        assert [r for r in rows if r.get('user_id')==other_user['user_id']]==[r for r in after[table] if r.get('user_id')==other_user['user_id']]
    with Session(h.store.engine) as session:
        for rid in [owner_run['run_id']]+([second['run_id']] if second else []):
            row=session.get(RunRow,rid)
            assert row.snapshot is None and row.status=='deleted' and row.deleted_at and row.generation==1
        for model in [IdempotencyRow,CacheRow]:
            assert not session.scalars(select(model).where(model.user_id==h.user['user_id'])).all()
        assert all(j.status=='cancelled_after_deletion' and j.result is None for j in session.scalars(select(JobRow).where(JobRow.user_id==h.user['user_id'])))
        if target=='account':
            user=session.get(UserRow,h.user['user_id'])
            assert user.deleted_at and user.generation==1 and user.password_hash=='' and user.username.startswith('deleted-')
            assert not session.scalars(select(SessionRow).where(SessionRow.user_id==h.user['user_id'])).all()
    # Reuse the OLD cookie explicitly, rather than merely observing cookie removal.
    h.client.cookies.clear();h.client.cookies.update(owner_cookie)
    expected=401 if target=='account' else 404
    before=db(h.store)
    assert h.client.get('/api/runs/'+owner_run['run_id']).status_code==expected
    assert h.client.post('/api/runs/'+owner_run['run_id']+'/game',headers=HEADERS,json=h.payload(action='start')).status_code==expected
    assert db(h.store)==before
    if target=='run':assert h.client.get('/api/runs').json()['runs']==[]
    else:assert h.client.get('/api/me').status_code==401
    h.client.cookies.clear();h.client.cookies.update(other_cookie)
    assert h.client.get('/api/runs/'+other_run['run_id']).json()==other_run


@pytest.mark.parametrize('phase',['decision','allocated','revision'])
@pytest.mark.parametrize('mode',['early','exact','late','late_action'])
def test_timeout_full_storage_and_opportunities(h,phase,mode):
    h.finish_round();h.accept('game',action='next');h.accept('game',action='start')
    if phase in {'allocated','revision'}:h.accept('game',action='allocate',personal=4,reason='합성 최초')
    if phase=='revision':h.accept('game',action='reveal')
    before_run=deepcopy(h.run);round_state=before_run['game']['rounds'][1]
    deadline=datetime.fromisoformat(round_state['deadline_at'])
    h.clock[0]=deadline+timedelta(microseconds=-1 if mode=='early' else (0 if mode=='exact' else 1))
    action={'decision':'allocate','allocated':'reveal','revision':'revise'}[phase] if mode=='late_action' else 'timeout'
    if mode=='early':
        h.reject('game','validation_error',422,h.payload(action=action));return
    payload=h.accept('game',action=action,personal=9,reason='합성 만료 이후 입력은 저장되지 않음')
    now=h.run['game']['rounds'][1]
    expected_reason={'decision':'timed_out_before_initial_decision','allocated':'timed_out_before_new_information','revision':'timed_out_without_final_decision'}[phase]
    assert now['status']=='completed' and now['completed_at'] and now['missing_reason']==expected_reason
    assert now['initial_decision']==round_state['initial_decision'] and now['final_decision'] is None
    allowed_timeout_fields={'status','completed_at','missing_reason'}
    assert {k:v for k,v in now.items() if k not in allowed_timeout_fields}=={k:v for k,v in round_state.items() if k not in allowed_timeout_fields}
    assert h.run['game']['phase']=='round_complete' and h.run['status']=='in_progress'
    assert h.run['game']['state_version']==before_run['game']['state_version']+1
    assert h.run['game']['events'][:-1]==before_run['game']['events']
    assert h.run['game']['events'][-1]['event_type']=='round_timed_out'
    assert h.run['game']['events'][-1]['value']=={'missing_reason':expected_reason}
    for k in ['records','questions','analysis','report_draft','report']:assert h.run[k]==before_run[k]
    for index in [0,2,3]:assert h.run['game']['rounds'][index]==before_run['game']['rounds'][index]
    metrics={m['behavior_id']:m for m in h.run['game']['metrics']}
    for bid in ['B01','B02']:
        assert metrics[bid]['denominator']==1
        if phase=='decision':
            assert metrics[bid]['numerator']==0 and metrics[bid]['observations'][0]['observed'] is None
            assert metrics[bid]['observations'][0]['reason']==expected_reason
    b03=metrics['B03']
    assert b03['denominator']==(1 if phase=='revision' else 0) and b03['numerator']==0
    assert b03['value']==(0 if phase=='revision' else None)
    if phase=='revision':assert b03['observations'][0]['reason']=='no_final_decision'
    assert all(any(e['reason']=='practice_excluded' for e in m['excluded_opportunities_with_reasons']) for m in metrics.values())
    before=db(h.store);h.clock[0]=deadline+timedelta(seconds=2)
    replay=h.client.post('/api/runs/'+h.run['run_id']+'/game',headers=HEADERS,json=payload)
    assert replay.status_code==200 and replay.json()==h.run and db(h.store)==before


def test_game_actions_individual_writes_and_inactive_timeouts(h):
    h.reject('game','invalid_state',409,h.payload(action='timeout'))
    expected=['decision','decision','allocated','revision','round_complete','awaiting_start']
    for request,phase in zip(CASES['API-GAME-FLOW']['requests'],expected):
        kw=h.resolve(request['json']);kw.pop('expected_revision');kw.pop('idempotency_key')
        previous=deepcopy(h.run['game'])
        accepted=h.accept('game',**kw)
        game=h.run['game'];r=game['rounds'][0]
        assert game['phase']==phase and game['state_version']==previous['state_version']+1
        assert game['events'][:-1]==previous['events']
        action=kw['action']
        if action=='start':
            assert datetime.fromisoformat(r['deadline_at'])-datetime.fromisoformat(r['started_at'])==timedelta(milliseconds=r['time_limit_ms'])
            before=db(h.store)
            replay=h.client.post('/api/runs/'+h.run['run_id']+'/game',headers=HEADERS,json=accepted)
            assert replay.status_code==200 and replay.json()==h.run and db(h.store)==before
            changed=deepcopy(accepted);changed['action']='open_info'
            h.reject('game','idempotency_conflict',409,changed)
        if action=='open_info':assert r['information']['opened'] is True
        if action=='allocate':assert r['initial_decision']['personal']==4 and r['initial_decision']['team']==6 and r['initial_decision']['reason_self_report']==kw['reason']
        if action=='reveal':assert r['new_information']['revealed_at'] and r['reward_table']==r['reward_table_final']
        if action=='revise':
            assert r['final_decision']['personal']==4 and r['final_decision']['reason_self_report']==kw['reason']
            assert r['revision_outcome']=='unchanged_after_evidence'
            h.reject('game','invalid_state',409,h.payload(action='timeout'))
    assert h.run['game']['round_index']==1 and h.run['game']['state_version']==6
    assert [e['sequence_no'] for e in h.run['game']['events']]==list(range(1,7))
    assert [e['event_type'] for e in h.run['game']['events']]==['round_started','information_opened','initial_allocation','new_information_revealed','final_allocation','round_advanced']
    for i in range(3):
        h.finish_round()
        if i<2:h.accept('game',action='next')
    h.reject('game','invalid_state',409,h.payload(action='timeout'))


def test_expired_unknown_action_still_rejected(h):
    h.accept('game',action='start')
    h.clock[0]=datetime.fromisoformat(h.run['game']['rounds'][0]['deadline_at'])+timedelta(seconds=1)
    h.reject('game','validation_error',422,h.payload(action='not_registered'))


@pytest.mark.parametrize('practice',['empty','practice_only'])
def test_zero_opportunity_empty_analysis_and_unmapped_source(h,practice):
    if practice=='practice_only':
        h.finish_round()
        h.accept('surveys',item_id='R-UNMAPPED',item_version='1.0.0',status='submitted',response={'selected_ids':['growth','autonomy','helping'],'selection_events':[]})
    before=deepcopy(h.run)
    # New HTTP policy rejects zero-main inputs. Pure computation still preserves
    # no-opportunity meanings, without claiming a successful HTTP/cache write.
    h.reject('analyze','main_round_completion_required',409,h.payload())
    result=analysis.analyze_run(h.store.get_run(h.user['user_id'],h.run['run_id']),deepcopy(DEFINITIONS))
    h.run['analysis']=result
    h.run['report_draft']=result['report']
    h.run['questions']+=result['questions']
    assert h.run['records']==before['records'] and h.run['game']==before['game']
    if practice=='empty':
        assert h.run['questions']==before['questions']
        assert h.run['analysis']['metrics']==[]
    else:
        assert h.run['questions'][:len(before['questions'])]==before['questions']
        assert len(h.run['analysis']['metrics'])==3
        new_questions=h.run['questions'][len(before['questions']):]
        assert len(new_questions)==3
        for q in new_questions:
            assert q['question_mode']=='adaptive_followup' and q['conditioned_on_prior_evidence'] is True
            assert q['disclosed_prior_information']==['game observation: no eligible opportunity']
    assert h.run['analysis']['runtime_mode']=='mock' and h.run['analysis']['extractions']==[]
    assert all(m['denominator']==0 and m['value'] is None for m in h.run['analysis']['metrics'])
    for card in h.run['report_draft']['cards']:
        assert card['comparison_status']=='insufficient_evidence'
        assert card['comparison']['reason']=='no_eligible_opportunity_or_relevant_evidence'
        assert card['comparison']['causal_claim'] is False
        assert not card['survey_evidence']
        assert not {'truth_probability','personality_score','consistency_score'}&card.keys()
    with Session(h.store.engine) as session:
        jobs=session.scalars(select(JobRow).where(JobRow.run_id==h.run['run_id'])).all()
        caches=session.scalars(select(CacheRow).where(CacheRow.run_id==h.run['run_id'])).all()
        assert jobs==[] and caches==[]
        for row in jobs+caches:
            assert row.user_id==h.user['user_id'] and row.attempt_id==h.run['attempt_id'] and row.generation==h.run['generation']


def test_http_deletion_while_analysis_pending_prevents_resurrection(h,monkeypatch):
    h.full()
    ready,resume=Event(),Event()
    original=analysis.analyze_run
    def paused(*args,**kw):
        result=original(*args,**kw)
        ready.set()
        assert resume.wait(10),'Deletion request never resumed analysis'
        return result
    monkeypatch.setattr(analysis,'analyze_run',paused)
    delete_app=create_app(h.url)
    try:
        with TestClient(delete_app) as deleting,ThreadPoolExecutor(max_workers=1) as executor:
            deleting.cookies.update(h.client.cookies)
            future=executor.submit(h.client.post,'/api/runs/'+h.run['run_id']+'/analyze',headers=HEADERS,json=h.payload())
            try:
                assert ready.wait(10),'Analysis did not reach deterministic pause'
                deleted=deleting.delete('/api/runs/'+h.run['run_id'],headers=HEADERS)
                assert deleted.status_code==204
            finally:resume.set()
            response=future.result(timeout=10)
            assert response.status_code==410 and response.json()=={'error':'cancelled_after_deletion'}
            assert deleting.get('/api/runs/'+h.run['run_id']).status_code==404
        with Session(h.store.engine) as session:
            row=session.get(RunRow,h.run['run_id'])
            assert row.snapshot is None and row.status=='deleted' and row.generation==1
            assert all(j.status=='cancelled_after_deletion' and j.result is None for j in session.scalars(select(JobRow)))
            assert not session.scalars(select(CacheRow)).all() and not session.scalars(select(IdempotencyRow)).all()
    finally:
        resume.set();delete_app.state.store.engine.dispose()
