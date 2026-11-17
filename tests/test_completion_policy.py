"""Accepted policy: all stages attempted, missingness explicitly preserved."""
from copy import deepcopy
from datetime import datetime,timezone
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.content import DEFINITIONS
from app.main import create_app
from app.store import Base
from completion_helpers import send,missing_survey,finish_required_stages,HEADERS,assert_public_matches_storage
from app.analysis import analyze_run

def db(store):
    with Session(store.engine) as session:
        return {t.name:sorted([tuple(r) for r in session.execute(select(t))],key=repr) for t in Base.metadata.sorted_tables}

@pytest.fixture
def fx(tmp_path,monkeypatch):
    monkeypatch.setattr('app.game._now',lambda:datetime(2026,9,25,tzinfo=timezone.utc))
    app=create_app(f"sqlite:///{tmp_path/'completion.db'}")
    try:
        with TestClient(app,raise_server_exceptions=False) as client:
            assert client.post('/api/register',headers=HEADERS,json={'username':'completion-owner','password':'synthetic-password'}).status_code==201
            created=client.post('/api/runs',headers=HEADERS,json={});assert created.status_code==201
            run=created.json()
            for index,q in enumerate(DEFINITIONS['questions']):
                run=send(client,run,'answers',question_id=q['question_id'],status='skipped' if index==1 else 'asked_no_text')
            # Synthetic pre-threshold analysis lets finalize's independent gate
            # still be checked at every unfinished phase. Not an HTTP analyze.
            def previous_analysis(snapshot):
                result=analyze_run(snapshot,deepcopy(DEFINITIONS))
                snapshot.update(analysis=result,report_draft=deepcopy(result['report']))
            app.state.store.mutate(run['user_id'],run['run_id'],run['revision'],'analyze','synthetic-old-analysis',{},previous_analysis)
            run=client.get(f"/api/runs/{run['run_id']}").json()
            yield client,app.state.store,run
    finally:app.state.store.engine.dispose()

@pytest.mark.parametrize('missing',[s['item_id'] for s in DEFINITIONS['surveys']])
def test_each_unvisited_survey_blocks_finalize_without_writes(fx,missing):
    client,store,run=fx
    # Finish game but leave exactly one of the six required surveys unvisited.
    for i in range(4):
        for action,kw in [('start',{}),('allocate',{'personal':4}),('reveal',{}),('revise',{'personal':4})]:run=send(client,run,'game',action=action,**kw)
        if i<3:run=send(client,run,'game',action='next')
    for item in DEFINITIONS['surveys']:
        if item['item_id']!=missing:run=send(client,run,'surveys',**missing_survey(item))
    before=db(store)
    response=client.post(f"/api/runs/{run['run_id']}/finalize",headers=HEADERS,json={'expected_revision':run['revision'],'idempotency_key':str(uuid4())})
    assert response.status_code==409 and response.json()=={'error':'survey_responses_required'}
    assert db(store)==before
    assert client.get(f"/api/runs/{run['run_id']}").json()==run

@pytest.mark.parametrize('phase',['awaiting_start','decision','allocated','revision','round_complete'])
def test_unfinished_game_blocks_finalize_before_analysis_job(fx,phase):
    client,store,run=fx
    for item in DEFINITIONS['surveys']:run=send(client,run,'surveys',**missing_survey(item))
    for action,kw,target in [('start',{},'decision'),('allocate',{'personal':4},'allocated'),('reveal',{},'revision'),('revise',{'personal':4},'round_complete')]:
        if run['game']['phase']==phase:break
        run=send(client,run,'game',action=action,**kw)
    assert run['game']['phase']==phase
    before=db(store)
    response=client.post(f"/api/runs/{run['run_id']}/finalize",headers=HEADERS,json={'expected_revision':run['revision'],'idempotency_key':str(uuid4())})
    assert response.status_code==409 and response.json()=={'error':'game_completion_required'}
    assert db(store)==before

@pytest.mark.parametrize('status',['skipped','timed_out'])
def test_missing_inputs_and_all_round_timeouts_allow_finalization(fx,monkeypatch,status):
    client,store,run=fx
    for item in DEFINITIONS['surveys']:run=send(client,run,'surveys',**missing_survey(item,status))
    run=finish_required_stages(client,run,monkeypatch=monkeypatch,timeout=True)
    originals=deepcopy(run['records']);game=deepcopy(run['game'])
    assert len(originals)==9 and game['phase']=='complete'
    payload={'expected_revision':run['revision'],'idempotency_key':str(uuid4())}
    response=client.post(f"/api/runs/{run['run_id']}/finalize",headers=HEADERS,json=payload)
    assert response.status_code==200,response.text
    saved=response.json()
    assert saved['status']=='completed' and saved['records']==originals and saved['game']==game
    assert all(r['missing_reason']=='timed_out_before_initial_decision' for r in saved['game']['rounds'])
    assert all(r['status']==status for r in saved['records'] if r['source_type']=='survey')
    assert all(e['criteria']['reasoning']['status'] in {'not_asked','unassessable'} for e in saved['analysis']['extractions'])
    assert saved['report']['limitations'] and all(c['limitations'] for c in saved['report']['cards'])
    assert all(c['comparison_status'] in {'insufficient_evidence','not_comparable','needs_clarification'} for c in saved['report']['cards'])
    assert all(r['initial_decision'] is None and r['final_decision'] is None for r in saved['game']['rounds'])
    assert saved['report']['lineage']['conditioned_followup_refs']==[]
    before=db(store)
    replay=client.post(f"/api/runs/{run['run_id']}/finalize",headers=HEADERS,json=payload)
    assert replay.status_code==200 and replay.json()==saved and db(store)==before
    assert client.get(f"/api/runs/{run['run_id']}").json()==saved


def test_pre_policy_completed_snapshot_and_retry_remain_immutable(fx):
    client,store,run=fx
    # Synthetic old-policy record through Store, never an existing user DB.
    payload={'expected_revision':run['revision'],'idempotency_key':'synthetic-legacy-finalize'}
    def old_finalize(snapshot):
        snapshot.update(status='completed',completed_at='2026-09-24T00:00:00+00:00',report=deepcopy(snapshot['report_draft']))
    saved=store.mutate(run['user_id'],run['run_id'],run['revision'],'finalize',payload['idempotency_key'],payload,old_finalize)
    before=db(store)
    assert assert_public_matches_storage(saved,client.get(f"/api/runs/{run['run_id']}").json())
    replay=client.post(f"/api/runs/{run['run_id']}/finalize",headers=HEADERS,json=payload)
    assert replay.status_code==200 and assert_public_matches_storage(saved,replay.json()) and db(store)==before
    fresh=client.post(f"/api/runs/{run['run_id']}/finalize",headers=HEADERS,json={'expected_revision':saved['revision'],'idempotency_key':'new-finalize'})
    assert fresh.status_code==409 and fresh.json()=={'error':'stale_after_finalize'}
    assert db(store)==before
