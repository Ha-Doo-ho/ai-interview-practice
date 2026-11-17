"""Malformed JSON must be rejected without changing persisted practice data."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content import DEFINITIONS
from app.main import create_app
from app.store import Base

HEADERS = {'X-Requested-With': 'interview-app'}


def database_snapshot(engine):
    """Read through a new DB session, including idempotency/jobs/cache tables."""
    with Session(engine) as session:
        return {table.name: sorted((tuple(row) for row in session.execute(select(table)).all()), key=repr)
                for table in Base.metadata.sorted_tables}


CASES = [
    ('game', {'action': []}),
    ('ordinal', {'status': []}),
    ('rank', {'response': {'selected_ids': [{}], 'selection_events': []}}),
    ('paired', {'status': 'skipped', 'response': {'self': {'status': []}, 'imagined_others': {'status': 'skipped'}}}),
    ('answers', {'status': []}),
    ('answers', {'status': 'skipped', 'text': []}),
    # Same boundaries reached through other JSON containers or event fields.
    ('game', {'action': {}}),
    ('ordinal', {'status': {}}),
    ('rank', {'response': {'selected_ids': [[]], 'selection_events': []}}),
    ('rank_event', {'event_action': []}),
    ('rank_event', {'event_action': {}}),
    ('answers', {'status': {}}),
    ('answers', {'status': 'asked_no_text', 'text': {}}),
]


@pytest.mark.parametrize('kind,override', CASES, ids=[
    'game-action-list','survey-status-list','rank-dict-option','paired-status-list',
    'answer-status-list','skipped-answer-list-text','game-action-object','survey-status-object',
    'rank-list-option','rank-event-action-list','rank-event-action-object',
    'answer-status-object','missing-answer-object-text'])
def test_malformed_json_is_422_and_database_unchanged(tmp_path, kind, override):
    application = create_app(f"sqlite:///{tmp_path / 'boundary.db'}")
    engine = application.state.store.engine
    try:
        with TestClient(application, raise_server_exceptions=False) as client:
            assert client.post('/api/register', headers=HEADERS,
                               json={'username': 'boundary', 'password': 'synthetic-password'}).status_code == 201
            created = client.post('/api/runs', headers=HEADERS, json={})
            assert created.status_code == 201
            run = created.json()
            payload = {'expected_revision': run['revision'], 'idempotency_key': 'invalid-json'}
            if kind in {'game', 'answers'}:
                operation = kind
                payload.update(question_id=run['questions'][0]['question_id'], text='synthetic answer')
            else:
                operation = 'surveys'
                response_type = {'ordinal': 'ordinal_6', 'paired': 'paired_perspective', 'rank': 'top_k_rank', 'rank_event': 'top_k_rank'}[kind]
                item = next(s for s in DEFINITIONS['surveys'] if s['type'] == response_type)
                payload.update(item_id=item['item_id'], item_version=item['item_version'],
                               status='submitted', response={'selected_position': 3})
                if kind == 'rank_event':
                    selected = [c['option_id'] for c in item['candidates'][:item['requested_k']]]
                    payload['response'] = {'selected_ids': selected,
                        'selection_events': [{'action': override['event_action'], 'option_id': selected[0]}]}
            if kind != 'rank_event':
                payload.update(deepcopy(override))
            before = database_snapshot(engine)
            response = client.post(f"/api/runs/{run['run_id']}/{operation}", headers=HEADERS, json=payload)
            # Preserve evidence of DB behavior even if the error response is wrong.
            assert database_snapshot(engine) == before
            assert response.status_code == 422, response.text
            assert response.json() == {'error': 'validation_error'}
            assert client.get(f"/api/runs/{run['run_id']}").json() == run
    finally:
        engine.dispose()
