"""Synthetic HTTP-only setup for accepted report completion policy."""
from datetime import datetime,timedelta
from uuid import uuid4
from app.content import DEFINITIONS
from copy import deepcopy

HEADERS={'X-Requested-With':'interview-app'}

def send(client,run,endpoint,**extra):
    response=client.post(f"/api/runs/{run['run_id']}/{endpoint}",headers=HEADERS,
        json={'expected_revision':run['revision'],'idempotency_key':str(uuid4()),**extra})
    assert response.status_code==200,response.text
    return response.json()

def missing_survey(item,status='skipped'):
    kind=item['type']
    if kind=='ordinal_6':response=None
    elif kind=='paired_perspective':response={'self':{'status':status},'imagined_others':{'status':status}}
    elif kind=='bipolar_slider':response={'final_value':None,'interaction_occurred':False,'explicit_confirmation':False,'change_count':0}
    else:response={'selected_ids':[],'selection_events':[]}
    return {'item_id':item['item_id'],'item_version':item['item_version'],'status':status,'response':response}

def finish_required_stages(client,run,*,monkeypatch=None,timeout=False):
    recorded={r['item_id'] for r in run['records'] if r['source_type']=='survey'}
    for item in run.get('survey_definition_snapshot', DEFINITIONS['surveys']):
        if item['item_id'] not in recorded:run=send(client,run,'surveys',**missing_survey(item))
    while run['game']['phase']!='complete':
        phase=run['game']['phase']
        if phase=='round_complete':run=send(client,run,'game',action='next');continue
        if phase=='awaiting_start':run=send(client,run,'game',action='start')
        if timeout:
            assert monkeypatch is not None
            round_state=run['game']['rounds'][run['game']['round_index']]
            now=datetime.fromisoformat(round_state['deadline_at'])+timedelta(microseconds=1)
            monkeypatch.setattr('app.game._now',lambda:now)
            run=send(client,run,'game',action='timeout')
        else:
            if run['game']['phase']=='decision':run=send(client,run,'game',action='allocate',personal=4)
            if run['game']['phase']=='allocated':run=send(client,run,'game',action='reveal')
            run=send(client,run,'game',action='revise',personal=4)
    return run

def finish_one_main_round(client,run):
    """Explicit HTTP setup for tests requiring successful analysis."""
    while not any(r['practice_or_main']=='main' and r['status']=='completed' for r in run['game']['rounds']):
        phase=run['game']['phase']
        if phase=='round_complete':run=send(client,run,'game',action='next')
        elif phase=='awaiting_start':run=send(client,run,'game',action='start')
        elif phase=='decision':run=send(client,run,'game',action='allocate',personal=4)
        elif phase=='allocated':run=send(client,run,'game',action='reveal')
        elif phase=='revision':run=send(client,run,'game',action='revise',personal=4)
        else:raise AssertionError(phase)
    return run

def assert_public_matches_storage(stored,public):
    """Verify all persistence, allowing only approved hidden response fields.

    Reconstruct stored data from the response after asserting private fields
    absent. This does not call the production projection.
    """
    reconstructed=deepcopy(public)
    assert len(stored['game']['rounds'])==len(public['game']['rounds'])
    for source,target in zip(stored['game']['rounds'],reconstructed['game']['rounds']):
        if not source['new_information'].get('revealed_at'):
            for key in ['text','updated_requirements']:
                assert key not in target['new_information']
                target['new_information'][key]=deepcopy(source['new_information'][key])
            for key in ['final_requirements','reward_table_final']:
                assert key not in target
                target[key]=deepcopy(source[key])
    assert reconstructed==stored
    return True

def finish_all_main_games(client,app,owner,run,monkeypatch):
    """Complete three genuine main attempts by authoritative total expiry.

    Timeout/unasked outcomes are intentional in this report fixture. They are
    not manual stops, practice or quick attempts. Separate journey tests exercise
    answering all questions and exact score computation.
    """
    from app import aptitude_games
    clock=[1000000]
    monkeypatch.setattr(aptitude_games,'_now',lambda:clock[0])
    for kind in ('rotation','path','potion'):
        run=send(client,run,'aptitude-games',action='start',game_type=kind,mode='main',difficulty='easy')
        attempt=run['aptitude_games']['attempts'][-1]
        duration=attempt['config']['total_duration_ms']
        if duration is not None:
            clock[0]+=duration
            run=send(client,run,'aptitude-games',action='timeout',attempt_id=attempt['id'],question_id=attempt['current_question']['id'])
        else:
            # Potion main has individual questions and no overall deadline.
            # Actually submit all 100 synthetic predictions through its API.
            for index in range(attempt['question_limit']):
                attempt=run['aptitude_games']['attempts'][-1]
                run=send(client,run,'aptitude-games',action='submit',attempt_id=attempt['id'],
                         question_id=attempt['current_question']['id'],choice='red')
                if index+1<attempt['question_limit']:
                    attempt=run['aptitude_games']['attempts'][-1]
                    run=send(client,run,'aptitude-games',action='next',attempt_id=attempt['id'],question_id=attempt['questions'][-1]['id'])
        assert run['aptitude_games']['attempts'][-1]['status']=='complete'
    return run
