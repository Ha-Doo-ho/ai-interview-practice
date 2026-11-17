"""Focused readiness regression: real HTTP/auth/Store/SQLite, local mock only.

Run via tools.run_checks so the global app import also uses a fresh guarded DB.
"""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import analysis
from app.content import DEFINITIONS
from app.main import create_app
from app.store import Base, JobRow, RunRow
from completion_helpers import finish_required_stages,finish_one_main_round

HEADERS={'X-Requested-With':'interview-app'}


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr('app.game._now', lambda: datetime(2026, 9, 24, 12, tzinfo=timezone.utc))
    application=create_app(f"sqlite:///{tmp_path / 'focused.db'}")
    try:
        with TestClient(application, raise_server_exceptions=False) as client:
            user=client.post('/api/register',headers=HEADERS,json={'username':'focused-owner','password':'synthetic-password'})
            assert user.status_code==201
            response=client.post('/api/runs',headers=HEADERS,json={})
            assert response.status_code==201
            yield client, application.state.store, response.json()
    finally:
        application.state.store.engine.dispose()


def body(run, **extra):
    return {'expected_revision':run['revision'],'idempotency_key':str(uuid4()),**extra}


def post(client, run, endpoint, **extra):
    response=client.post(f"/api/runs/{run['run_id']}/{endpoint}",headers=HEADERS,json=body(run,**extra))
    assert response.status_code==200, response.text
    return response.json()


def db_snapshot(store):
    with Session(store.engine) as session:
        return {t.name:sorted((tuple(r) for r in session.execute(select(t)).all()),key=repr)
                for t in Base.metadata.sorted_tables}


def finish_round(client, run):
    for action,extra in [('start',{}),('open_info',{}),('allocate',{'personal':4,'reason':'synthetic initial'}),
                         ('reveal',{}),('revise',{'personal':5,'reason':'synthetic revised'})]:
        run=post(client,run,'game',action=action,**extra)
    return run


def presented_then_changed(client, run):
    for item in DEFINITIONS['surveys']:
        kind=item['type']
        if kind=='ordinal_6': response={'selected_position':4}
        elif kind=='paired_perspective':
            response={'self':{'status':'submitted','selected_position':4},'imagined_others':{'status':'submitted','selected_position':2}}
        elif kind=='bipolar_slider':
            response={'final_value':0,'interaction_occurred':False,'explicit_confirmation':True,'change_count':0}
        else: response={'selected_ids':['growth','autonomy','helping'],'selection_events':[]}
        run=post(client,run,'surveys',item_id=item['item_id'],item_version=item['item_version'],status='submitted',response=response)
    for q in DEFINITIONS['questions']:
        run=post(client,run,'answers',question_id=q['question_id'],text='Synthetic neutral baseline answer.')
    run=finish_one_main_round(client,run)  # approved first-main threshold
    run=post(client,run,'analyze')
    assert all(m['denominator']==1 for m in run['analysis']['metrics'])
    presented=deepcopy(next(q for q in run['questions'] if q['question_id']=='followup:B01:v1'))
    baseline=deepcopy([e for e in run['analysis']['extractions'] if e['mode']=='baseline'])
    run=post(client,run,'answers',question_id=presented['question_id'],text='Synthetic answer to the original question.')
    original_records=deepcopy(run['records'])
    run=post(client,run,'game',action='next')
    run=finish_round(client,run)  # main2 changes opportunity and action counts
    assert next(m for m in run['game']['metrics'] if m['behavior_id']=='B01')['denominator']==2
    raw=analysis.analyze_run(deepcopy(run),deepcopy(DEFINITIONS))
    candidate=next(q for q in raw['questions'] if q['question_id']==presented['question_id'])
    assert candidate['question_text']!=presented['question_text'], 'Fixture must actually change the candidate wording'
    assert candidate['disclosed_prior_information']!=presented['disclosed_prior_information']
    # Keep the changed-evidence probe, then meet the now-approved completion gate.
    run=finish_required_stages(client,run)
    return run,presented,baseline,original_records


@pytest.mark.parametrize('endpoint',['analyze','finalize'])
def test_changed_game_evidence_keeps_presented_question(fixture,endpoint):
    client,store,run=fixture
    run,presented,baseline,original_records=presented_then_changed(client,run)
    payload=body(run)
    response=client.post(f"/api/runs/{run['run_id']}/{endpoint}",headers=HEADERS,json=payload)
    assert response.status_code==200, response.text
    saved=response.json()
    assert next(q for q in saved['questions'] if q['question_id']==presented['question_id'])==presented
    assert next(q for q in saved['analysis']['questions'] if q['question_id']==presented['question_id'])==presented
    report=saved['report'] if endpoint=='finalize' else saved['report_draft']
    assert next(c for c in report['cards'] if c['behavior_id']=='B01')['open_question']==presented['question_text']
    assert saved['records']==original_records
    immutable=('extraction_id','version','answer_id','answer_version','question_id','question_version','mode','criteria','answer_evidence_spans')
    assert [{k:e[k] for k in immutable} for e in saved['analysis']['extractions'] if e['mode']=='baseline']==[{k:e[k] for k in immutable} for e in baseline]
    with Session(store.engine) as session:
        row=session.get(RunRow,run['run_id'])
        assert row.snapshot==saved
        jobs=session.scalars(select(JobRow).where(JobRow.run_id==run['run_id'])).all()
        assert len(jobs)==2 and all(j.status=='succeeded' for j in jobs)
        latest=max(jobs,key=lambda j:j.run_revision)
        assert next(q for q in latest.result['questions'] if q['question_id']==presented['question_id'])==presented
    before_retry=db_snapshot(store)
    retry=client.post(f"/api/runs/{run['run_id']}/{endpoint}",headers=HEADERS,json=payload)
    assert retry.status_code==200 and retry.json()==saved
    assert db_snapshot(store)==before_retry
    assert client.get(f"/api/runs/{run['run_id']}").json()==saved


@pytest.mark.parametrize('endpoint',['analyze','finalize'])
def test_long_key_rejected_before_analysis_and_all_db_writes(fixture,monkeypatch,endpoint):
    client,store,run=fixture
    if endpoint=='finalize': run,*_=presented_then_changed(client,run)
    before=db_snapshot(store)
    calls=[]
    original=analysis.analyze_run
    def counted(*args,**kwargs):
        calls.append(True)
        return original(*args,**kwargs)
    monkeypatch.setattr(analysis,'analyze_run',counted)
    response=client.post(f"/api/runs/{run['run_id']}/{endpoint}",headers=HEADERS,json=body(run,idempotency_key='x'*129))
    assert response.status_code==422 and response.json()=={'error':'validation_error'}
    after=db_snapshot(store)
    assert after==before, 'Rejected key must not create an analysis job or change any business row'
    assert calls==[], 'Reject existing key limit before invoking analysis'


@pytest.mark.parametrize('endpoint',['analyze','finalize'])
def test_analysis_exception_marks_failed_and_preserves_business_data(fixture,monkeypatch,endpoint):
    client,store,run=fixture
    if endpoint=='finalize': run,*_=presented_then_changed(client,run)
    else: run=finish_one_main_round(client,run)
    before=db_snapshot(store)
    with Session(store.engine) as session:
        old_ids=set(session.scalars(select(JobRow.job_id)).all())
    def fail(*args,**kwargs): raise RuntimeError('synthetic analysis failure; not a live provider')
    monkeypatch.setattr(analysis,'analyze_run',fail)
    response=client.post(f"/api/runs/{run['run_id']}/{endpoint}",headers=HEADERS,json=body(run))
    assert response.status_code==500
    after=db_snapshot(store)
    assert {k:v for k,v in after.items() if k!='analysis_jobs'}=={k:v for k,v in before.items() if k!='analysis_jobs'}
    with Session(store.engine) as session:
        new_jobs=[j for j in session.scalars(select(JobRow)).all() if j.job_id not in old_ids]
        assert len(new_jobs)==1
        job=new_jobs[0]
        assert job.status=='failed', 'An analysis exception must not leave its job running'
        assert job.result is None and job.completed_at is not None
    assert client.get(f"/api/runs/{run['run_id']}").json()==run


def test_invalid_analysis_result_marks_failed_without_accepting_run(fixture,monkeypatch):
    client,store,run=fixture
    run=finish_one_main_round(client,run)
    before=db_snapshot(store)
    monkeypatch.setattr(analysis,'analyze_run',lambda *args,**kwargs:{})
    response=client.post(f"/api/runs/{run['run_id']}/analyze",headers=HEADERS,json=body(run))
    assert response.status_code==422 and response.json()=={'error':'analysis_validation_error'}
    after=db_snapshot(store)
    assert {k:v for k,v in after.items() if k!='analysis_jobs'}=={k:v for k,v in before.items() if k!='analysis_jobs'}
    with Session(store.engine) as session:
        job=session.scalar(select(JobRow))
        assert job.status=='failed' and job.result is None and job.completed_at is not None


def test_failure_cleanup_preserves_deletion_cancellation(fixture,monkeypatch):
    client,store,run=fixture
    run=finish_one_main_round(client,run)
    def deleted_then_failed(*args,**kwargs):
        store.delete_run(run['user_id'],run['run_id'])  # real SQL deletion at the injected boundary
        raise RuntimeError('synthetic failure after deletion')
    monkeypatch.setattr(analysis,'analyze_run',deleted_then_failed)
    response=client.post(f"/api/runs/{run['run_id']}/analyze",headers=HEADERS,json=body(run))
    assert response.status_code==500
    assert client.get(f"/api/runs/{run['run_id']}").status_code==404
    with Session(store.engine) as session:
        job=session.scalar(select(JobRow))
        row=session.get(RunRow,run['run_id'])
        assert job.status=='cancelled_after_deletion' and job.result is None
        assert row.status=='deleted' and row.snapshot is None and row.generation==1
