"""Same-run, real SQLite/API verification for the new appointment games."""
from uuid import uuid4
from datetime import timedelta
from copy import deepcopy
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


def test_synthesis_real_api_freezes_prompt_preserves_baseline_and_detects_new_answers(api, monkeypatch):
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
    url=f"/api/runs/{run['run_id']}/synthesis-analysis"
    body={'expected_revision':run['revision'],'idempotency_key':str(uuid4()),'mode':'mock'}
    assert client.post(url,json=body).status_code==403
    response=client.post(url,headers=HEADERS,json=body)
    assert response.status_code==200,response.text
    run=response.json()
    assert run['synthesis_analysis_stale'] is False
    assert client.post(url,headers=HEADERS,json=body).json()==run
    prompt=client.get(f"/api/runs/{run['run_id']}/synthesis-prompt").json()
    assert prompt==run['synthesis_analysis']['report']['prompt']
    assert {e['source'] for e in prompt['evidence']}=={'survey','game','interview'}
    run=ok(client,run,'answers',question_id='spatial-work-experience-0',text='실제 설치 위치와 방향을 확인하고 결과를 비교했습니다. '*5)
    assert run['synthesis_analysis_stale'] is True
    assert run['interview_report_stale'] is False
    run=ok(client,run,'synthesis-analysis',mode='mock')
    run=ok(client,run,'evidence-linkage')
    run=ok(client,run,'synthesis-analysis',mode='mock')
    # Use the documented default synthesis budget with the complete real flow,
    # including saved surveys, 30 memory tasks, and current conditional questions.
    for q in run['questions']:
        if q['question_mode']=='supplemental' and q['question_id']!='spatial-work-experience-0':
            text=('다음 행사에서는 연락처를 필수 입력으로 바꿨습니다.'
                  if q['question_id']=='repeated-work-experience-v2-0'
                  else '여러 번의 결과를 살펴보고 유지할 조건과 바꿀 조건을 정했습니다. '*4)
            run=ok(client,run,'answers',question_id=q['question_id'],text=text)
    from app import aptitude_games
    from test_aptitude_state import start,solve,act
    def complete_additional_games(snapshot):
        for kind in ('rotation','path','potion'):
            if any(a['type']==kind and a['mode']=='main' and a['status']=='complete' for a in snapshot.get('aptitude_games',{}).get('attempts',[])):
                continue
            _,attempt=start(aptitude_games,kind=kind,snapshot=snapshot)
            while attempt['status']=='active':
                solve(aptitude_games,snapshot,attempt)
                if attempt['status']=='active':act(aptitude_games,snapshot,attempt,'next')
    app.state.store.mutate(owner['user_id'],run['run_id'],run['revision'],'synthetic-complete-games',str(uuid4()),{},complete_additional_games)
    run=client.get(f"/api/runs/{run['run_id']}").json()
    assert all(a['status']=='complete' for a in run['aptitude_games']['attempts'])
    monkeypatch.delenv('AI_MAX_INPUT_TOKENS',raising=False)
    monkeypatch.delenv('AI_SYNTHESIS_MAX_INPUT_TOKENS',raising=False)
    monkeypatch.setenv('AI_PROVIDER','gemini')
    monkeypatch.setenv('AI_MODEL_ID','gemini-test')
    monkeypatch.setenv('AI_ALLOWED_MODEL_IDS','gemini-test')
    synthesis_calls=[]
    def synthesis_transport(endpoint,payload,**kwargs):
        synthesis_calls.append(payload)
        structured=json.loads(payload['contents'][0]['parts'][0]['text'])
        potion=next(e for e in structured['evidence'] if e.get('game_type')=='potion')
        repeated=next(e for e in structured['evidence'] if e.get('question_id')=='repeated-work-experience-v2-0')
        return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps({
            'strengths':[{'finding_type':'observed_evidence','topic_id':'learning','evidence_ids':[repeated['id']],
                'criterion_id':'action','quote':repeated['text']}],
            'gaps':[{'finding_type':'interview_answer_gap','topic_id':'learning','evidence_ids':[repeated['id']],
                'criterion_id':'information','quote':''}],
            'clarifying_questions':[],
            'practice_plan':[
                {'finding_type':'practice_suggestion','topic_id':'learning','evidence_ids':[potion['id']],
                    'criterion_id':'','quote':''},
                {'finding_type':'practice_suggestion','topic_id':'learning','evidence_ids':[repeated['id']],
                    'criterion_id':'result','quote':''},
            ],
        })}]}}]}
    monkeypatch.setattr('app.interview_analysis._PROVIDER_TRANSPORT',synthesis_transport)
    run=ok(client,run,'synthesis-analysis',mode='live')
    assert len(synthesis_calls)==1
    sent=json.loads(synthesis_calls[0]['contents'][0]['parts'][0]['text'])
    assert sent['source_digest']==run['synthesis_analysis']['report']['source_digest']
    assert len([e for e in sent['evidence'] if e['source']=='game'])==8
    assert len(sent['interview_comparison'])==7
    assert all(item['reference_answer'] for item in sent['interview_comparison'].values())
    assert 'result' not in sent['interview_comparison']['spatial-work-experience-0']['criteria']
    result=run['synthesis_analysis']['report']
    assert len(result['game_observations'])==8
    assert '가능성이 더 높은 색 선택' in next(e['text'] for e in result['game_observations'] if '마법약' in e['label'])
    assert '같은 재료 조합' in result['feedback']['practice_plan'][0]['text']
    assert '결과까지 확인했다면' in result['feedback']['practice_plan'][1]['text']
    assert '다음 업무에 실제로 적용한 방식' in result['feedback']['strengths'][0]['text']
    assert result['feedback']['strengths'][0]['quote']=='다음 행사에서는 연락처를 필수 입력으로 바꿨습니다.'
    assert '같은 방식에서 나온 서로 다른 결과' in result['feedback']['gaps'][0]['text']

    from app.synthesis import prepare
    longer_answers=deepcopy(run)
    for record in longer_answers['records']:
        if record['source_type']=='typed_answer' and record['data'].get('question_id') in sent['interview_comparison']:
            record['data']['text']=('요청에 대한 처리 기준과 실제 결과를 정리했습니다. '*40)[:800]
    prepared=prepare(longer_answers,'live')
    assert prepared['max_input_tokens']==80000
    long_input=prepared['_structured_input']['evidence']
    assert sum(len(e.get('text',''))==800 for e in long_input if e.get('question_id') in sent['interview_comparison'])==7

    run = ok(client, run, 'interview-finalize')
    assert run['report']['synthesis_analysis']==run['synthesis_analysis']
    assert client.get(f"/api/runs/{run['run_id']}/synthesis-prompt").json()==run['report']['synthesis_prompt']
    assert client.post(url,headers=HEADERS,json={**body,'expected_revision':run['revision'],'idempotency_key':str(uuid4())}).status_code==409
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
    assert client.get(f"/api/runs/{run['run_id']}/synthesis-prompt").status_code==404
    assert client.post('/api/login',headers=HEADERS,json={'username':'completion-owner','password':'synthetic-password'}).status_code==200
    assert client.delete(f"/api/runs/{run['run_id']}",headers=HEADERS).status_code==204
    assert client.get(f"/api/runs/{run['run_id']}").status_code==404
    assert client.get(f"/api/runs/{run['run_id']}/synthesis-prompt").status_code==404
