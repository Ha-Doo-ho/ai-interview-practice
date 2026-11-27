"""Eight-game interview boundary with real API state transitions and saved progress."""
from uuid import uuid4
from datetime import timedelta
from test_rule_games import api, HEADERS, visit_surveys, post
from completion_helpers import send, finish_all_main_games


def test_partial_memory_game_restores_and_all_eight_gate_new_interview_answers(api, monkeypatch):
    client, app, owner, _, clock=api
    run=visit_surveys(client,client.post('/api/runs',headers=HEADERS,json={'flow_version':'five-game-v2'}).json())
    for kind in ('rsp','card'):
        for _ in range(3):
            run=send(client,run,'rule-games',action='start',game_type=kind)
            rid=run['rule_games']['games'][kind]['rounds'][-1]['round_id']
            clock[0]+=timedelta(seconds=10)
            run=send(client,run,'rule-games',action='reveal',game_type=kind,round_id=rid)
            clock[0]+=timedelta(seconds=10)
            run=send(client,run,'rule-games',action='finish',game_type=kind,round_id=rid)
    now=[1000000];monkeypatch.setattr('app.appointment_game._now',lambda:now[0])
    run=send(client,run,'appointment-games',action='configure',difficulty='easy')
    for index,kind in enumerate(('day','place','bus')):
        run=send(client,run,'appointment-games',action='start',game_type=kind)
        for number in range(10):
            now[0]+=12000
            run=client.get(f"/api/runs/{run['run_id']}/appointment-games").json()['run']
            q=run['appointment_games']['games'][index]['current_question']
            run=send(client,run,'appointment-games',action='answer',question_id=q['id'],choice=q['choices'][0])
            if kind=='day' and number==3:
                saved=run['appointment_games']
                assert client.post('/api/logout',headers=HEADERS).status_code==204
                assert client.post('/api/login',headers=HEADERS,json={'username':'rule-owner','password':'synthetic-password'}).status_code==200
                restored=client.get(f"/api/runs/{run['run_id']}").json()
                assert restored['appointment_games']==saved
                run=restored
            if number<9:run=send(client,run,'appointment-games',action='next',question_id=q['id'])
    before=client.get(f"/api/runs/{run['run_id']}").json()
    for q in (run['questions'][0],run['questions'][3]):
        result=client.post(f"/api/runs/{run['run_id']}/answers",headers=HEADERS,json={
            'expected_revision':run['revision'],'idempotency_key':str(uuid4()),'question_id':q['question_id'],'text':'합성 경험 답변'})
        assert result.status_code==409 and result.json()['error']=='all_games_completion_required'
    assert client.get(f"/api/runs/{run['run_id']}").json()==before
    run=finish_all_main_games(client,app,owner,run,monkeypatch)
    for q in run['questions']:
        run=send(client,run,'answers',question_id=q['question_id'],text='게임 여덟 종류를 완료한 뒤 저장한 합성 경험 답변')
    assert len([r for r in run['records'] if r['source_type']=='typed_answer'])==8
