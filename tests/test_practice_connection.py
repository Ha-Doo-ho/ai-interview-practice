"""Local synthetic acceptance checks. Execute through tools.run_checks only."""
import pytest
import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app
from completion_helpers import HEADERS
from app.content import SURVEYS
from app.survey import build_survey_record, SurveyValidation


@pytest.mark.scenario('SCN-012')
def test_keyed_run_creation_retry_ownership_and_deleted_run_never_returns(tmp_path):
    app = create_app(f"sqlite:///{tmp_path/'practice.db'}")
    try:
        with TestClient(app) as client:
            assert client.post('/api/runs', headers=HEADERS, json={}).status_code == 401
            owner = client.post('/api/register', headers=HEADERS, json={'username': 'practice-owner', 'password': 'synthetic-password'}).json()
            body = {'idempotency_key': 'synthetic-create-key', 'expected_user_id': owner['user_id']}
            first = client.post('/api/runs', headers=HEADERS, json=body)
            assert first.status_code == 201
            run = first.json()
            assert client.post('/api/runs', headers=HEADERS, json=body).json() == run
            assert len(client.get('/api/runs').json()['runs']) == 1
            assert client.post('/api/runs', headers=HEADERS, json={**body, 'expected_user_id': 'other-user'}).status_code == 409
            assert client.post('/api/runs', headers=HEADERS, json={'idempotency_key': ''}).status_code == 422
            client.post('/api/logout', headers=HEADERS)
            other = client.post('/api/register', headers=HEADERS, json={'username': 'practice-other', 'password': 'synthetic-password'}).json()
            assert client.get('/api/runs').json()['runs'] == []
            assert client.get('/api/runs/' + run['run_id']).status_code == 404
            own = client.post('/api/runs', headers=HEADERS, json={**body, 'expected_user_id': other['user_id']}).json()
            assert own['run_id'] != run['run_id']
            assert client.delete('/api/runs/' + own['run_id'], headers=HEADERS).status_code == 204
            assert client.post('/api/runs', headers=HEADERS, json={**body, 'expected_user_id': other['user_id']}).status_code == 404
            assert client.get('/api/runs').json()['runs'] == []
    finally:
        app.state.store.engine.dispose()


@pytest.mark.scenario('SCN-009')
def test_partial_rank_keeps_actual_second_slot_and_rejects_forged_slots():
    definition = next(item for item in SURVEYS if item['type'] == 'top_k_rank')
    response = {'selected_ids': ['helping'], 'selection_events': [], 'ranked_selection': [{'option_id': 'helping', 'rank': 2}]}
    def build(value):
        return build_survey_record(definition=definition, user_id='synthetic', run_id='synthetic', attempt_id='synthetic', presentation_order=6, response=value, status='timed_out', elapsed_ms=45000)
    record = build(response)
    assert record['data']['ranked_selection'] == [{'option_id': 'helping', 'rank': 2}]
    assert record['data']['submitted_count'] == 1
    for rank in [0, 4, True, 1.5]:
        with pytest.raises(SurveyValidation):
            build({**response, 'ranked_selection': [{'option_id': 'helping', 'rank': rank}]})
    with pytest.raises(SurveyValidation):
        build({**response, 'ranked_selection': [{'option_id': 'growth', 'rank': 2}]})


@pytest.mark.scenario('SCN-001', 'SCN-004', 'SCN-007', 'SCN-009', 'SCN-012')
def test_real_ui_payloads_save_restore_retry_and_reject_other_owner(tmp_path):
    payloads = json.loads(Path('tests/fixtures/practice_ui_payloads.json').read_text(encoding='utf-8'))
    app = create_app(f"sqlite:///{tmp_path/'survey-ui.db'}")
    try:
        with TestClient(app) as client:
            credentials = {'username': 'ui-payload-owner', 'password': 'synthetic-password'}
            client.post('/api/register', headers=HEADERS, json=credentials)
            run = client.post('/api/runs', headers=HEADERS, json={'idempotency_key': 'ui-six'}).json()
            create_snapshot = run
            for index, body in enumerate(payloads):
                request = {**body, 'expected_revision': run['revision'], 'idempotency_key': f'ui-item-{index}'}
                response = client.post('/api/runs/' + run['run_id'] + '/surveys', headers=HEADERS, json=request)
                assert response.status_code == 200, response.text
                run = response.json()
                assert client.post('/api/runs/' + run['run_id'] + '/surveys', headers=HEADERS, json=request).json() == run
                assert run['revision'] == index + 1
                record = run['records'][-1]
                assert record['item_version'] == body['item_version']
                assert record['context']['submitted_elapsed_ms'] == 1200
                assert record['status'] == 'submitted'
            assert client.post('/api/runs', headers=HEADERS, json={'idempotency_key': 'ui-six'}).json() == create_snapshot
            by_id = {r['item_id']: r['data'] for r in run['records']}
            assert by_id['O-B01']['selected_label_snapshot'] == '그렇다'
            assert by_id['P-B01']['self']['selected_position'] == 4
            assert by_id['P-B01']['imagined_others']['selected_position'] == 5
            assert by_id['S-B02']['final_value'] == 0
            assert by_id['S-B02']['explicit_confirmation'] is True
            assert by_id['S-B02']['interaction_occurred'] is False
            assert by_id['R-UNMAPPED']['ranked_selection'] == payloads[-1]['response']['ranked_selection']
            assert len(client.get('/api/runs').json()['runs']) == 1
            client.post('/api/logout', headers=HEADERS)
            client.post('/api/register', headers=HEADERS, json={'username': 'ui-payload-other', 'password': 'synthetic-password'})
            assert client.get('/api/runs/' + run['run_id']).status_code == 404
            assert client.post('/api/runs/' + run['run_id'] + '/surveys', headers=HEADERS, json={**payloads[0], 'expected_revision': 6, 'idempotency_key': 'other-attempt'}).status_code == 404
            client.post('/api/logout', headers=HEADERS)
            client.post('/api/login', headers=HEADERS, json=credentials)
            assert client.get('/api/runs/' + run['run_id']).json() == run
    finally:
        app.state.store.engine.dispose()


def test_concurrent_create_retries_are_one_run_and_deletion_keeps_tombstone(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from app.store import Store, NotFound
    store = Store(f"sqlite:///{tmp_path/'creation-race.db'}")
    try:
        user = store.create_user('race-owner', 'synthetic-password')
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: store.create_run(user['user_id'], 'same-key'), range(4)))
        assert all(run == results[0] for run in results)
        assert len(store.list_runs(user['user_id'])) == 1
        store.delete_run(user['user_id'], results[0]['run_id'])
        with pytest.raises(NotFound):
            store.create_run(user['user_id'], 'same-key')
        assert store.list_runs(user['user_id']) == []
    finally:
        store.engine.dispose()
