"""Public error contracts and policy observations; use tools.run_checks only.

All HTTP and SQL are real; identities are synthetic and analysis is local mock.
Policy observations record current behavior, not approval of that policy.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import analysis
from app.content import DEFINITIONS
from app.main import create_app, _error_status
from app.store import Base, JobRow, SessionRow
from completion_helpers import finish_required_stages,finish_one_main_round

HEADERS = {'X-Requested-With': 'interview-app'}


@pytest.fixture
def fx(tmp_path, monkeypatch):
    clock = [datetime(2026, 9, 24, tzinfo=timezone.utc)]
    monkeypatch.setattr('app.game._now', lambda: clock[0])
    app = create_app(f"sqlite:///{tmp_path / 'error-policy.db'}")
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            assert client.post('/api/register', headers=HEADERS, json={
                'username': 'error-owner', 'password': 'synthetic-password'}).status_code == 201
            response = client.post('/api/runs', headers=HEADERS, json={})
            assert response.status_code == 201
            yield client, app.state.store, response.json(), clock
    finally:
        app.state.store.engine.dispose()


def body(run, **extra):
    return dict(expected_revision=run['revision'], idempotency_key=str(uuid4()), **extra)


def post(client, run, endpoint, **extra):
    response = client.post(f"/api/runs/{run['run_id']}/{endpoint}", headers=HEADERS, json=body(run, **extra))
    assert response.status_code == 200, response.text
    return response.json()


def snapshot(store):
    with Session(store.engine) as session:
        return {t.name: sorted((tuple(r) for r in session.execute(select(t))), key=repr)
                for t in Base.metadata.sorted_tables}


def analyzed_missing(client, run):
    run = finish_one_main_round(client, run)
    for index, q in enumerate(DEFINITIONS['questions']):
        run = post(client, run, 'answers', question_id=q['question_id'],
                   status='skipped' if index == 1 else 'asked_no_text')
    return post(client, run, 'analyze')


def test_deadline_internal_mapping_matches_public_validation():
    assert _error_status('deadline_not_reached') == _error_status('validation_error') == 422


@pytest.mark.parametrize('case', [
    'malformed_json', 'input_type', 'no_login', 'expired_login', 'bad_credentials',
    'csrf', 'other_owner', 'invalid_phase', 'revision', 'idempotency',
    'duplicate_answer', 'answer_version', 'analysis_required', 'baseline_required',
    'finalized', 'deleted_get', 'deleted_mutation', 'deleted_account', 'duplicate_user',
])
def test_public_error_and_rejected_db_unchanged(fx, case):
    client, store, run, _ = fx
    endpoint = 'game'
    payload = body(run, action='start')
    method, headers, expected, code = 'POST', HEADERS, 422, 'validation_error'
    path = None
    raw = None
    if case == 'malformed_json': raw = '{'
    elif case == 'input_type': payload['action'] = []
    elif case in {'no_login', 'expired_login'}:
        if case == 'no_login': client.cookies.clear()
        else:
            with Session(store.engine) as session:
                for row in session.scalars(select(SessionRow)):
                    row.expires_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
                session.commit()
        expected, code = 401, 'unauthorized'
    elif case == 'bad_credentials':
        path, payload, expected, code = '/api/login', {'username':'error-owner', 'password':'wrong'}, 401, 'invalid_credentials'
    elif case == 'csrf': headers, expected, code = {}, 403, 'csrf_required'
    elif case == 'other_owner':
        assert client.post('/api/register', headers=HEADERS, json={'username':'error-other', 'password':'synthetic-password'}).status_code == 201
        expected, code = 404, 'not_found'
    elif case == 'invalid_phase': payload['action'], expected, code = 'reveal', 409, 'invalid_state'
    elif case == 'revision': payload['expected_revision'], expected, code = 99, 409, 'revision_conflict'
    elif case == 'idempotency':
        accepted = client.post(f"/api/runs/{run['run_id']}/game", headers=HEADERS, json=payload)
        assert accepted.status_code == 200
        payload['action'], expected, code = 'open_info', 409, 'idempotency_conflict'
    elif case in {'duplicate_answer', 'answer_version'}:
        qid = DEFINITIONS['questions'][0]['question_id']
        run = post(client, run, 'answers', question_id=qid, text='Synthetic first answer')
        endpoint, payload = 'answers', body(run, question_id=qid, text='Synthetic second answer')
        expected, code = 409, 'record_already_submitted'
        if case == 'answer_version':
            payload.update(replaces_answer_id=run['records'][-1]['data']['answer_id'], expected_answer_version='9.0.0')
            code = 'answer_version_conflict'
    elif case in {'analysis_required', 'baseline_required'}:
        if case == 'baseline_required': run = post(client, finish_one_main_round(client,run), 'analyze')
        endpoint, payload, expected = 'finalize', body(run), 409
        code = 'analysis_required' if case == 'analysis_required' else 'baseline_answers_required'
    elif case == 'finalized':
        run = post(client, finish_required_stages(client, analyzed_missing(client, run)), 'finalize')
        payload, expected, code = body(run, action='start'), 409, 'stale_after_finalize'
    elif case in {'deleted_get', 'deleted_mutation'}:
        assert client.delete(f"/api/runs/{run['run_id']}", headers=HEADERS).status_code == 204
        expected, code = 404, 'not_found'
        if case == 'deleted_get': method, path = 'GET', f"/api/runs/{run['run_id']}"
    elif case == 'deleted_account':
        assert client.delete('/api/account', headers=HEADERS).status_code == 204
        expected, code = 401, 'unauthorized'
    elif case == 'duplicate_user':
        path, payload, expected, code = '/api/register', {'username':'error-owner', 'password':'synthetic-password'}, 409, 'username_taken'
    before = snapshot(store)
    path = path or f"/api/runs/{run['run_id']}/{endpoint}"
    kwargs = {'content': raw} if raw is not None else {'json': payload}
    response = client.request(method, path, headers=headers, **kwargs)
    assert response.status_code == expected, response.text
    assert response.json() == {'error': code}
    assert snapshot(store) == before, 'Rejected request must preserve all six logical DB tables'


@pytest.mark.parametrize('phase', ['decision', 'allocated', 'revision'])
@pytest.mark.parametrize('offset', [-1, 0, 1], ids=['before', 'exact', 'after'])
def test_timeout_boundary_and_replay(fx, phase, offset):
    client, store, run, clock = fx
    for action, extra in [('start', {}), ('allocate', {'personal':4}), ('reveal', {}), ('revise', {'personal':5}), ('next', {}), ('start', {})]:
        run = post(client, run, 'game', action=action, **extra)
    if phase in {'allocated', 'revision'}: run = post(client, run, 'game', action='allocate', personal=4, reason='Synthetic initial')
    if phase == 'revision': run = post(client, run, 'game', action='reveal')
    old_round = deepcopy(run['game']['rounds'][1])
    clock[0] = datetime.fromisoformat(old_round['deadline_at']) + timedelta(microseconds=offset)
    before = snapshot(store)
    payload = body(run, action='timeout')
    path = f"/api/runs/{run['run_id']}/game"
    response = client.post(path, headers=HEADERS, json=payload)
    if offset < 0:
        assert response.status_code == 422 and response.json() == {'error':'validation_error'}
        assert snapshot(store) == before
        assert client.get(f"/api/runs/{run['run_id']}").json() == run
        return
    assert response.status_code == 200, response.text
    saved = response.json()
    current = saved['game']['rounds'][1]
    reason = {'decision':'timed_out_before_initial_decision', 'allocated':'timed_out_before_new_information', 'revision':'timed_out_without_final_decision'}[phase]
    assert current['missing_reason'] == reason and current['status'] == 'completed'
    assert current['initial_decision'] == old_round['initial_decision'] and current['final_decision'] is None
    assert saved['game']['phase'] == 'round_complete' and saved['status'] == 'in_progress'
    assert saved['revision'] == run['revision'] + 1
    assert saved['game']['state_version'] == run['game']['state_version'] + 1
    assert saved['records'] == run['records']
    assert saved['game']['events'][:-1] == run['game']['events']
    event = saved['game']['events'][-1]
    assert event['event_type'] == 'round_timed_out' and event['value']['missing_reason'] == reason
    metrics = {m['behavior_id']:m for m in saved['game']['metrics']}
    assert metrics['B01']['denominator'] == metrics['B02']['denominator'] == 1
    assert metrics['B03']['denominator'] == (1 if phase == 'revision' else 0)
    assert metrics['B03']['value'] == (0 if phase == 'revision' else None)
    if phase == 'decision':
        assert metrics['B02']['observations'][0]['observed'] is None
    after = snapshot(store)
    retry = client.post(path, headers=HEADERS, json=payload)
    assert retry.status_code == 200 and retry.json() == saved
    assert snapshot(store) == after
    assert client.get(f"/api/runs/{run['run_id']}").json() == saved


def test_job_completion_after_injected_deletion_returns_410(fx, monkeypatch):
    client, store, run, _ = fx
    run = finish_one_main_round(client, run)
    original = analysis.analyze_run
    def delete_before_completion(*args, **kwargs):
        result = original(*args, **kwargs)
        store.delete_run(run['user_id'], run['run_id'])
        return result
    monkeypatch.setattr(analysis, 'analyze_run', delete_before_completion)
    response = client.post(f"/api/runs/{run['run_id']}/analyze", headers=HEADERS, json=body(run))
    assert response.status_code == 410 and response.json() == {'error':'cancelled_after_deletion'}
    assert client.get(f"/api/runs/{run['run_id']}").status_code == 404
    with Session(store.engine) as session:
        job = session.scalar(select(JobRow))
        assert job.status == 'cancelled_after_deletion' and job.result is None


def test_policy_observation_analysis_during_game(fx):
    client, _, run, _ = fx
    run = finish_one_main_round(client, run)
    run = post(client, run, 'game', action='next')
    run = post(client, run, 'game', action='start')
    saved = post(client, run, 'analyze')
    assert saved['game'] == run['game'] and saved['game']['phase'] == 'decision'
    assert saved['status'] == 'in_progress' and saved['analysis'] is not None


def test_policy_requires_stages_before_finalize(fx):
    client, store, run, _ = fx
    run = analyzed_missing(client, run)
    before = snapshot(store)
    response = client.post(f"/api/runs/{run['run_id']}/finalize", headers=HEADERS, json=body(run))
    assert response.status_code == 409 and response.json() == {'error':'survey_responses_required'}
    assert snapshot(store) == before
    assert client.get(f"/api/runs/{run['run_id']}").json() == run


def test_policy_future_information_not_in_http_payload_before_reveal(fx):
    client, _, run, _ = fx
    definitions = client.get('/api/definitions')
    assert definitions.status_code == 200
    for container in [definitions.json()['game'], run['game']]:
        for round_state in container['rounds']:
            assert round_state['information']['text'] and round_state['information']['opened'] is False
            assert 'text' not in round_state['new_information']
            assert 'updated_requirements' not in round_state['new_information']
            assert 'revealed_at' not in round_state['new_information']
            assert 'final_requirements' not in round_state and 'reward_table_final' not in round_state
