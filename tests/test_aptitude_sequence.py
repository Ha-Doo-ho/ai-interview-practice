"""Required games cannot be replaced by optional aptitude attempts."""
from datetime import timedelta
from uuid import uuid4

from test_rule_games import api, HEADERS
from completion_helpers import send, missing_survey
from test_aptitude_api import request


def test_extra_games_wait_for_core_five_and_interview_requires_all_eight(api, monkeypatch):
    client, app, owner, _, rule_clock = api
    response = client.post('/api/runs', headers=HEADERS, json={
        'flow_version':'five-game-v2', 'survey_set_version':'work-behavior-v2'})
    assert response.status_code == 201
    run = response.json()

    def assert_blocked(current):
        for kind, mode in [('rotation','practice'),('rotation','main'),('path','practice'),
                           ('path','main'),('potion','practice'),('potion','main'),('potion','quick')]:
            response, _ = request(client, current, action='start', game_type=kind, mode=mode, difficulty='easy')
            assert response.status_code == 409, (kind, mode, response.text)
            assert response.json()['error'] == 'game_order_required'
            assert client.get(f"/api/runs/{current['run_id']}").json() == current

    assert_blocked(run)
    for item in run['survey_definition_snapshot']:
        run = send(client, run, 'surveys', **missing_survey(item))
    for kind in ('rsp','card'):
        for index in range(3):
            run = send(client, run, 'rule-games', action='start', game_type=kind)
            ident = run['rule_games']['games'][kind]['rounds'][-1]['round_id']
            rule_clock[0] += timedelta(seconds=10)
            run = send(client, run, 'rule-games', action='reveal', game_type=kind, round_id=ident)
            rule_clock[0] += timedelta(seconds=10)
            run = send(client, run, 'rule-games', action='finish', game_type=kind, round_id=ident)
    assert_blocked(run)  # Exact reported boundary: card 3 ended, day not started.

    clock = [1000000]
    monkeypatch.setattr('app.appointment_game._now', lambda:clock[0])
    run = send(client, run, 'appointment-games', action='configure', difficulty='easy')
    for game_index, kind in enumerate(('day','place','bus')):
        run = send(client, run, 'appointment-games', action='start', game_type=kind)
        for question_index in range(10):
            clock[0] += 12000
            run = client.get(f"/api/runs/{run['run_id']}/appointment-games").json()['run']
            question = run['appointment_games']['games'][game_index]['current_question']
            run = send(client, run, 'appointment-games', action='answer', question_id=question['id'], choice=question['choices'][0])
            if question_index < 9:
                run = send(client, run, 'appointment-games', action='next', question_id=question['id'])
        if kind != 'bus':
            assert_blocked(run)
    for kind in ('rotation','path','potion'):
        response, _ = request(client, run, action='start', game_type=kind, mode='practice', difficulty='easy')
        assert response.status_code == 200, response.text
        run = response.json()
        attempt = run['aptitude_games']['attempts'][-1]
        response, _ = request(client, run, action='stop', attempt_id=attempt['id'], question_id=attempt['current_question']['id'])
        assert response.status_code == 200, response.text
        run = response.json()
    rejected=client.post(f"/api/runs/{run['run_id']}/answers",headers=HEADERS,json={
        'expected_revision':run['revision'],'idempotency_key':str(uuid4()),
        'question_id':'baseline-b01','text':'연습이나 중단은 본게임 완료가 아닙니다.'})
    assert rejected.status_code==409 and rejected.json()['error']=='all_games_completion_required'
    from completion_helpers import finish_all_main_games
    run=finish_all_main_games(client,app,owner,run,monkeypatch)
    run = send(client, run, 'answers', question_id='baseline-b01', text='합성 교차 검증용 면접 답변입니다.')
    assert run['records'][-1]['data']['text'] == '합성 교차 검증용 면접 답변입니다.'


def test_pre_fix_active_optional_attempt_can_stop_without_completing_required_games(api):
    client, app, owner, legacy, _ = api
    response, _ = request(client, legacy, action='start', game_type='rotation', mode='practice', difficulty='easy')
    assert response.status_code == 200
    run = response.json()
    # Represents a snapshot saved by the previous permissive version. Write only
    # this fixture's private temporary database, retaining the real game attempt.
    from sqlalchemy.orm import Session
    from app.store import RunRow
    from app.appointment_game import initial_appointment_games
    with Session(app.state.store.engine) as session, session.begin():
        row = session.get(RunRow, run['run_id'])
        snapshot = dict(row.snapshot)
        snapshot.update(flow_version='five-game-v2', appointment_games=initial_appointment_games())
        row.snapshot = snapshot
    run = client.get(f"/api/runs/{run['run_id']}").json()
    attempt = run['aptitude_games']['attempts'][-1]
    response, _ = request(client, run, action='stop', attempt_id=attempt['id'], question_id=attempt['current_question']['id'])
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved['aptitude_games']['attempts'][-1]['status'] == 'interrupted'
    assert saved['appointment_games'] == run['appointment_games']
