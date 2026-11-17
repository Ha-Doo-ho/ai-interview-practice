"""Optional games exercise the real authenticated SQLite/API boundary."""
from uuid import uuid4
import json
from test_completion_pipeline import api, HEADERS


def request(client, run, **values):
    body = {'expected_revision': run['revision'], 'idempotency_key': str(uuid4()), **values}
    return client.post(f"/api/runs/{run['run_id']}/aptitude-games", headers=HEADERS, json=body), body


def test_optional_game_owned_persisted_replay_and_no_existing_game_changes(api):
    client, app, owner, run, _ = api
    definitions = client.get('/api/aptitude-games/definitions')
    assert definitions.status_code == 200
    original = run.copy()
    response, body = request(client, run, action='start', game_type='rotation', mode='practice', difficulty='easy')
    assert response.status_code == 200, response.text
    run = response.json()
    attempt = run['aptitude_games']['attempts'][-1]
    assert attempt['type'] == 'rotation' and attempt['mode'] == 'practice'
    assert 'solution' not in str(attempt['current_question'])
    for field in ('rule_games', 'appointment_games', 'records'):
        assert run.get(field) == original.get(field)
    replay = client.post(f"/api/runs/{run['run_id']}/aptitude-games", headers=HEADERS, json=body)
    assert replay.status_code == 200
    assert replay.json()['revision'] == run['revision']
    restored = client.get(f"/api/runs/{run['run_id']}/aptitude-games").json()['run']
    assert restored['aptitude_games']['attempts'][-1]['id'] == attempt['id']
    assert client.post(f"/api/runs/{run['run_id']}/aptitude-games",json=body).status_code == 403
    body['difficulty'] = 'hard'
    assert client.post(f"/api/runs/{run['run_id']}/aptitude-games",headers=HEADERS,json=body).status_code == 409
    assert client.post('/api/register',headers=HEADERS,json={'username':'aptitude-other','password':'synthetic-password'}).status_code == 201
    assert client.get(f"/api/runs/{run['run_id']}/aptitude-games").status_code == 404
    response, _ = request(client, run, action='stop', attempt_id=attempt['id'], question_id=attempt['current_question']['id'])
    assert response.status_code == 404


def test_private_potion_values_filtered_from_all_run_routes(api):
    client, app, owner, run, _ = api
    response, _ = request(client, run, action='start', game_type='potion', mode='quick', difficulty='easy')
    assert response.status_code == 200, response.text
    run = response.json()
    for path in (f"/api/runs/{run['run_id']}",f"/api/runs/{run['run_id']}/aptitude-games",'/api/runs'):
        payload = client.get(path).json()
        if isinstance(payload, list):
            payload = next(r for r in payload if r['run_id'] == run['run_id'])
        if 'runs' in payload:
            payload = next(r for r in payload['runs'] if r['run_id'] == run['run_id'])
        content = json.dumps(payload.get('run', payload)['aptitude_games'])
        for private in ('red_probability','favorable_color','seed','solution'):
            assert private not in content


def test_legacy_finalization_cannot_freeze_an_active_optional_game(api):
    client, _, _, run, _ = api
    response, _ = request(client, run, action='start', game_type='rotation', mode='main', difficulty='easy')
    run = response.json()
    response = client.post(f"/api/runs/{run['run_id']}/finalize", headers=HEADERS,
                           json={'expected_revision':run['revision'], 'idempotency_key':str(uuid4())})
    assert response.status_code == 409
    assert response.json()['error'] == 'aptitude_active'
