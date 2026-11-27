"""Same-run, real SQLite/API verification for the new appointment games."""
from uuid import uuid4
from datetime import timedelta
import json
from test_completion_pipeline import api, HEADERS, ok
from test_rule_games import visit_surveys
from app.content import DEFINITIONS
from test_five_game_ai import configure


def action(client, run, **values):
    body = {'expected_revision': run['revision'], 'idempotency_key': str(uuid4()), **values}
    response = client.post(f"/api/runs/{run['run_id']}/appointment-games", headers=HEADERS, json=body)
    assert response.status_code == 200, response.text
    return response.json(), body


def test_real_api_30_questions_survive_reload_and_preserve_retry(api, monkeypatch):
    client, app, owner, _, game_clock = api
    now = [1000000]
    monkeypatch.setattr('app.appointment_game._now', lambda: now[0])
    response = client.post('/api/runs', headers=HEADERS, json={'flow_version':'five-game-v2'})
    assert response.status_code == 201
    run = visit_surveys(client, response.json())
    for kind in ('rsp', 'card'):
        for _ in range(3):
            run = ok(client, run, 'rule-games', action='start', game_type=kind)
            round_id = run['rule_games']['games'][kind]['rounds'][-1]['round_id']
            game_clock[0] += timedelta(seconds=10)
            run = ok(client, run, 'rule-games', action='reveal', game_type=kind, round_id=round_id)
            game_clock[0] += timedelta(seconds=10)
            run = ok(client, run, 'rule-games', action='finish', game_type=kind, round_id=round_id)
    run, _ = action(client, run, action='configure', difficulty='easy')
    for index, kind in enumerate(('day', 'place', 'bus')):
        run, start_body = action(client, run, action='start', game_type=kind)
        replay = client.post(f"/api/runs/{run['run_id']}/appointment-games", headers=HEADERS, json=start_body)
        assert replay.status_code == 200 and replay.json() == run
        for qindex in range(10):
            game = run['appointment_games']['games'][index]
            question = game['current_question']
            assert question['number'] == qindex + 1
            assert question['phase'] == 'countdown'
            assert 'answer' not in question and 'sets' not in question and 'choices' not in question
            now[0] += 12000
            current = client.get(f"/api/runs/{run['run_id']}/appointment-games").json()['run']
            question = current['appointment_games']['games'][index]['current_question']
            assert question['phase'] == 'answer'
            assert 'answer' not in question and 'sets' not in question
            run, _ = action(client, current, action='answer', question_id=question['id'], choice=question['choices'][0])
            settled = run['appointment_games']['games'][index]['questions'][-1]
            assert settled['outcome'] in ('correct','wrong')
            if qindex < 9:
                run, _ = action(client, run, action='next', question_id=question['id'])
        assert run['appointment_games']['games'][index]['status'] == 'complete'
    restored = client.get(f"/api/runs/{run['run_id']}").json()
    assert restored['appointment_games'] == run['appointment_games']
    assert [len(g['questions']) for g in restored['appointment_games']['games']] == [10,10,10]
    assert all(g['difficulty'] == 'easy' for g in restored['appointment_games']['games'])
    from completion_helpers import finish_all_main_games
    run = finish_all_main_games(client,app,owner,run,monkeypatch)
    for question in DEFINITIONS['questions']:
        run = ok(client, run, 'answers', question_id=question['question_id'], text='합성 면접 답변입니다.')
    run = ok(client, run, 'interview-analysis', mode='mock')
    report = run['interview_report']['five_games']
    assert [g['type'] for g in report['games']] == ['rsp','card','day','place','bus']
    for i in range(3):
        game = report['games'][i+2]
        assert game['status'] == 'complete'
        assert game['totals']['settled'] == 10
        assert game['totals']['score'] == run['appointment_games']['games'][i]['score']
        assert [e['source_ref']['question_id'] for e in game['evidence']] == [q['id'] for q in run['appointment_games']['games'][i]['questions']]
    baseline = run['interview_report']
    feedback_body={'expected_revision':run['revision'],'idempotency_key':str(uuid4()),'mode':'mock'}
    response=client.post(f"/api/runs/{run['run_id']}/game-analysis",headers=HEADERS,json=feedback_body)
    assert response.status_code == 200, response.text
    run=response.json()
    assert run['interview_report'] == baseline
    assert run['game_analysis']['runtime_mode'] == 'mock'
    assert run['game_analysis']['provider_execution'] == 'not_called'
    assert run['game_analysis_stale'] is False
    from copy import deepcopy
    from app.main import _public_snapshot
    stale = deepcopy(run)
    stale['game_analysis']['input_snapshot']['baseline_report_id'] = 'different-report'
    assert _public_snapshot(stale)['game_analysis_stale'] is True
    assert run['game_analysis']['report']['source_digest'] == report['source_digest']
    assert [g['type'] for g in run['game_analysis']['report']['games']] == ['rsp','card','day','place','bus']
    assert client.post(f"/api/runs/{run['run_id']}/game-analysis",headers=HEADERS,json=feedback_body).json() == run
    configure(monkeypatch)
    calls=[]
    def transport(_endpoint, payload, **_kwargs):
        supplied=json.loads(payload['input'][0]['content'][0]['text'])
        calls.append(supplied)
        return {'output_text':json.dumps({'games':[{'game_id':g['source_ref']['game_id'],
            'game_version':g['source_ref']['game_version'],'advice_codes':['practice_recall']} for g in supplied['games']]})}
    monkeypatch.setattr('app.interview_analysis._PROVIDER_TRANSPORT', transport)
    run=ok(client,run,'game-analysis',mode='live')
    assert run['game_analysis']['provider_execution']=='test_double'
    assert len(calls)==1
    assert [(g['type'],g['conditions'],g['totals']) for g in calls[0]['games']] == [
        (g['type'],g['conditions'],g['totals']) for g in report['games']]
    assert run['interview_report']==baseline
    monkeypatch.setattr('app.interview_analysis._PROVIDER_TRANSPORT', lambda *_a,**_kw: {'output_text':json.dumps({'games':[], 'claim':'invented'})})
    rejected=client.post(f"/api/runs/{run['run_id']}/game-analysis",headers=HEADERS,
        json={'expected_revision':run['revision'],'idempotency_key':str(uuid4()),'mode':'live'})
    assert rejected.status_code == 422 and rejected.json()['error'] == 'provider_schema_invalid'
    assert client.get(f"/api/runs/{run['run_id']}").json() == run
    run = ok(client, run, 'evidence-linkage')
    run = ok(client, run, 'interview-finalize')
    assert run['interview_report'] == baseline
    assert run['game_analysis_stale'] is False
    assert run['report']['source_report_id'] == baseline['report_id']
    assert run['status'] == 'completed'
    assert run['report']['five_games'] == report
    assert run['report']['game_analysis']['source_digest'] == report['source_digest']
    assert run['report']['game_analysis_provenance']['provider_execution'] == 'test_double'
    assert client.get(f"/api/runs/{run['run_id']}").json()['report'] == run['report']
    assert client.post('/api/register',headers=HEADERS,json={'username':'other-reviewer','password':'synthetic-password'}).status_code==201
    assert client.get(f"/api/runs/{run['run_id']}").status_code==404
    assert client.post('/api/login',headers=HEADERS,json={'username':'completion-owner','password':'synthetic-password'}).status_code==200
    assert client.delete(f"/api/runs/{run['run_id']}",headers=HEADERS).status_code==204
    assert client.get(f"/api/runs/{run['run_id']}").status_code==404
