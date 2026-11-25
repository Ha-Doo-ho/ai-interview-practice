from copy import deepcopy
import pytest
from test_rule_games import api, HEADERS

def complete_snapshot():
    return {'flow_version':'five-game-v2','status':'in_progress',
        'rule_games':{'games':{k:{'rounds':[{'status':'completed'} for _ in range(3)]} for k in ('rsp','card')}},
        'appointment_games':{'games':[{'type':k,'status':'complete','questions':[{} for _ in range(10)]} for k in ('day','place','bus')]},
        'aptitude_games':{'attempts':[{'type':k,'mode':'main','status':'complete'} for k in ('rotation','path','potion')]}}

def test_all_types_need_completed_main_and_active_attempt_blocks_results():
    from app.game_completion import all_games_complete
    ready=complete_snapshot()
    assert all_games_complete(ready)
    for mode,status in [('practice','complete'),('quick','complete'),('main','interrupted'),('main','active')]:
        partial=deepcopy(ready);partial['aptitude_games']['attempts'][-1].update(mode=mode,status=status)
        partial['aptitude_games']['attempts'].append({'type':'rotation','mode':'main','status':'complete'})
        assert not all_games_complete(partial), (mode,status)
    for kind in ('rsp','card'):
        partial=deepcopy(ready);partial['rule_games']['games'][kind]['rounds'].pop()
        assert not all_games_complete(partial)
    for index in range(3):
        partial=deepcopy(ready);partial['appointment_games']['games'][index]['status']='pending'
        assert not all_games_complete(partial)
    ready['aptitude_games']['attempts'].append({'type':'potion','mode':'main','status':'interrupted'})
    assert all_games_complete(ready)

def test_unfinished_run_cannot_preview_prompt_or_generate_results(api):
    client,app,owner,_,clock=api
    run=client.post('/api/runs',headers=HEADERS,json={'flow_version':'five-game-v2'}).json()
    result=client.get(f"/api/runs/{run['run_id']}/synthesis-prompt")
    assert result.status_code==409
    assert result.json()['error']=='all_games_completion_required'
    from uuid import uuid4
    for route in ('interview-analysis','game-analysis','synthesis-analysis','evidence-linkage','interview-finalize'):
        body={'expected_revision':run['revision'],'idempotency_key':str(uuid4())}
        if route.endswith('analysis'):body['mode']='mock'
        result=client.post(f"/api/runs/{run['run_id']}/{route}",headers=HEADERS,json=body)
        assert result.status_code==409,(route,result.text)
        assert result.json()['error']=='all_games_completion_required',(route,result.text)
    assert client.get(f"/api/runs/{run['run_id']}").json()['revision']==run['revision']

def test_cached_partial_results_are_hidden_without_erasing_storage(api):
    client,app,owner,_,clock=api
    run=client.post('/api/runs',headers=HEADERS,json={'flow_version':'five-game-v2'}).json()
    from sqlalchemy.orm import Session
    from app.store import RunRow
    fields=('analysis','report','report_draft','interview_report','interview_analysis','game_analysis','synthesis_analysis',
            'interview_analysis_history','game_analysis_history','synthesis_analysis_history','evidence_linkage','evidence_linkage_history')
    with Session(app.state.store.engine) as session,session.begin():
        row=session.get(RunRow,run['run_id']);snapshot=deepcopy(row.snapshot)
        for field in fields:snapshot[field]={'secret_result_sentinel':'PRIVATE-RESULT'}
        snapshot['questions'].append({'question_id':'conditioned-old','question_mode':'adaptive_followup',
            'question_text':'PRIVATE-RESULT','conditioned_on_prior_evidence':True})
        snapshot['records'].append({'source_type':'typed_answer','data':{'question_id':'conditioned-old','text':'PRIVATE-RESULT'}})
        row.snapshot=snapshot
    for endpoint in ('', '/rule-games','/appointment-games','/aptitude-games'):
        response=client.get(f"/api/runs/{run['run_id']}"+endpoint)
        assert response.status_code==200,response.text
        assert 'PRIVATE-RESULT' not in response.text,endpoint
    response=client.get('/api/runs');assert 'PRIVATE-RESULT' not in response.text
    stored=app.state.store.get_run(owner['user_id'],run['run_id'])
    assert stored['report']['secret_result_sentinel']=='PRIVATE-RESULT'

def test_explicit_stop_at_overall_deadline_is_not_completion(monkeypatch):
    from app import aptitude_games as game
    from test_aptitude_state import start,act
    now=[1000000];monkeypatch.setattr(game,'_now',lambda:now[0])
    run,attempt=start(game,kind='rotation',mode='main')
    now[0]+=attempt['config']['total_duration_ms']
    act(game,run,attempt,'stop')
    assert attempt['status']=='interrupted'

def test_seven_games_practice_duplicates_and_cached_results_remain_locked():
    from app.game_completion import all_games_complete, hide_partial_results
    ready=complete_snapshot()
    ready['report']={'sentinel':'final-result'}
    ready['questions']=[];ready['records']=[]
    partial=deepcopy(ready)
    partial['aptitude_games']['attempts'][-1]['mode']='quick'
    partial['aptitude_games']['attempts'].append({'type':'rotation','mode':'main','status':'complete'})
    assert not all_games_complete(partial)
    hide_partial_results(partial)
    assert 'report' not in partial
    hide_partial_results(ready)
    assert ready['report']['sentinel']=='final-result'

def test_historical_finalized_report_and_prompt_remain_readable(api):
    client,app,owner,_,clock=api
    run=client.post('/api/runs',headers=HEADERS,json={'flow_version':'five-game-v2'}).json()
    from sqlalchemy.orm import Session
    from app.store import RunRow
    with Session(app.state.store.engine) as session,session.begin():
        row=session.get(RunRow,run['run_id']);snapshot=deepcopy(row.snapshot)
        snapshot.update(status='completed',report={'status':'finalized','synthesis_prompt':{'frozen':'historical'}})
        row.status='completed';row.snapshot=snapshot
    response=client.get(f"/api/runs/{run['run_id']}/synthesis-prompt")
    assert response.status_code==200 and response.json()=={'frozen':'historical'}

def test_old_ready_receipt_uses_current_run_visibility(api,monkeypatch):
    from datetime import datetime,timezone
    from uuid import uuid4
    from sqlalchemy.orm import Session
    from app.store import RunRow,IdempotencyRow,_digest
    client,app,owner,_,clock=api
    run=client.post('/api/runs',headers=HEADERS,json={'flow_version':'five-game-v2'}).json()
    body={'expected_revision':run['revision'],'idempotency_key':str(uuid4())}
    ready=deepcopy(run);ready.update(complete_snapshot())
    ready['report']={'sentinel':'OLD-READY-RESULT'}
    ready['evidence_linkage']={'sentinel':'OLD-READY-RESULT'}
    # Isolate response visibility from algorithm projection in this receipt test.
    monkeypatch.setattr('app.aptitude_games.public_state',deepcopy)
    monkeypatch.setattr('app.appointment_game.public_appointment_state',deepcopy)
    with Session(app.state.store.engine) as session,session.begin():
        row=session.get(RunRow,run['run_id']);current=deepcopy(ready)
        current['aptitude_games']['attempts'].append({'type':'rotation','mode':'practice','status':'active'})
        row.snapshot=current
        session.add(IdempotencyRow(user_id=owner['user_id'],run_id=run['run_id'],operation='evidence_linkage',
            idempotency_key=body['idempotency_key'],request_digest=_digest(body),response=ready,created_at=datetime.now(timezone.utc)))
    response=client.post(f"/api/runs/{run['run_id']}/evidence-linkage",headers=HEADERS,json=body)
    assert response.status_code==200,response.text
    assert 'OLD-READY-RESULT' not in response.text
    assert 'report' not in response.json()
