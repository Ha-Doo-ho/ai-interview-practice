"""Integration policy for versioned five-game runs, using the real API."""
from uuid import uuid4
from datetime import timedelta
import pytest
from test_rule_games import api, HEADERS, visit_surveys, post


def create(client, **extra):
    return client.post('/api/runs', headers=HEADERS, json=extra)


def test_new_flow_creation_is_explicit_idempotent_and_keeps_legacy_run(api):
    client, _, _, legacy, _ = api
    assert legacy.get('flow_version') != 'five-game-v2'
    key = str(uuid4())
    first = create(client, idempotency_key=key, flow_version='five-game-v2')
    assert first.status_code == 201, first.text
    run = first.json()
    assert run['flow_version'] == 'five-game-v2'
    assert create(client, idempotency_key=key, flow_version='five-game-v2').json() == run
    different = create(client, idempotency_key=key)
    assert different.status_code == 409 and different.json()['error'] == 'idempotency_conflict'


def test_new_flow_requires_rsp_before_card_without_changing_legacy(api):
    client, _, _, _, _ = api
    run = create(client, flow_version='five-game-v2').json()
    run = visit_surveys(client, run)
    blocked, _ = post(client, run, game_type='card', action='start')
    assert blocked.status_code == 409 and blocked.json()['error'] == 'game_order_required'
    assert client.get(f"/api/runs/{run['run_id']}").json() == run


def test_changed_rule_is_hidden_until_reveal_including_older_replays(api):
    client, _, _, _, clock = api
    run = visit_surveys(client, create(client, flow_version='five-game-v2').json())
    response, start_body = post(client, run, game_type='rsp', action='start')
    assert response.status_code == 200
    started = response.json()
    assert 'changed' not in started['rule_games']['games']['rsp']['rounds'][0]['rule_snapshot']
    assert 'changed' not in client.get(f"/api/runs/{run['run_id']}").json()['rule_games']['games']['rsp']['rounds'][0]['rule_snapshot']
    clock[0] += timedelta(seconds=10)
    revealed, _ = post(client, started, game_type='rsp', action='reveal', round_id=started['rule_games']['games']['rsp']['rounds'][0]['round_id'])
    assert revealed.status_code == 200
    assert 'changed' in revealed.json()['rule_games']['games']['rsp']['rounds'][0]['rule_snapshot']
    replay=client.post(f"/api/runs/{run['run_id']}/rule-games",headers=HEADERS,json=start_body)
    assert replay.status_code == 200
    assert 'changed' not in replay.json()['rule_games']['games']['rsp']['rounds'][0]['rule_snapshot']


def test_new_flow_cannot_finalize_without_three_memory_games(api):
    client, _, _, _, _ = api
    run = create(client, flow_version='five-game-v2').json()
    response = client.post(f"/api/runs/{run['run_id']}/interview-finalize", headers=HEADERS,
                           json={'expected_revision':run['revision'],'idempotency_key':str(uuid4())})
    assert response.status_code == 409
    assert client.get(f"/api/runs/{run['run_id']}").json() == run


@pytest.mark.parametrize('operation,extra', [
    ('answers', {'question_id':'baseline-b01', 'text':'합성 답변'}),
    ('interview-analysis', {'mode':'mock'}),
    ('finalize', {}),
    ('analyze', {}),
    ('game', {'action':'start'}),
])
def test_new_flow_cannot_bypass_games_through_legacy_or_interview_api(api, operation, extra):
    client, _, _, _, _ = api
    run = create(client, flow_version='five-game-v2').json()
    response = client.post(f"/api/runs/{run['run_id']}/{operation}", headers=HEADERS,
        json={'expected_revision':run['revision'],'idempotency_key':str(uuid4()), **extra})
    expected_error = 'all_games_completion_required' if operation == 'interview-analysis' else 'game_order_required'
    assert response.status_code == 409 and response.json()['error'] == expected_error
