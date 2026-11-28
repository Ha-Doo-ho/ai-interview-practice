"""Server state tests use real algorithms, synthetic choices and a controlled clock."""
from collections import Counter
import copy
import importlib
import json

import pytest

from app.store import Conflict, Validation


@pytest.fixture
def game():
    assert importlib.util.find_spec('app.aptitude_games') is not None, 'aptitude state implementation is missing'
    return importlib.import_module('app.aptitude_games')


@pytest.fixture
def clock(game, monkeypatch):
    now = [1_000_000]
    monkeypatch.setattr(game, '_now', lambda: now[0])
    return now


def start(game, kind='rotation', mode='main', difficulty='easy', snapshot=None):
    snapshot = {} if snapshot is None else snapshot
    game.apply_action(snapshot, {'action': 'start', 'game_type': kind, 'mode': mode, 'difficulty': difficulty})
    return snapshot, snapshot['aptitude_games']['attempts'][-1]


def act(game, snapshot, attempt, action, **extra):
    q = attempt['current_question'] or attempt['questions'][-1]
    game.apply_action(snapshot, {'action': action, 'attempt_id': attempt['id'], 'question_id': q['id'], **extra})


def solve(game, snapshot, attempt):
    q = attempt['current_question']
    if attempt['type'] == 'rotation':
        for command in q['solution']:
            act(game, snapshot, attempt, 'rotate', command=command)
    elif attempt['type'] == 'path':
        for key, orientation in q['solution'].items():
            row, col = map(int, key.split(','))
            for _ in range(1 if orientation == '/' else 2):
                act(game, snapshot, attempt, 'cell', row=row, col=col)
    act(game, snapshot, attempt, 'submit', **({'choice': q['outcome']} if attempt['type'] == 'potion' else {}))


def test_rotation_saved_actions_undo_reset_practice_preview_and_operation_limit(game, clock):
    snapshot, attempt = start(game, mode='practice')
    initial = copy.deepcopy(attempt['current_question']['initial_points'])
    clock[0] += 123
    act(game, snapshot, attempt, 'rotate', command='right')
    current = game.public_state(snapshot['aptitude_games'])['attempts'][0]['current_question']
    assert current['commands'] == ['right'] and current['operations'] == 1
    assert current['transformed_points'] != initial
    restored = json.loads(json.dumps(snapshot))
    assert game.public_state(restored['aptitude_games']) == game.public_state(snapshot['aptitude_games'])
    act(game, snapshot, attempt, 'undo')
    assert attempt['current_question']['commands'] == []
    act(game, snapshot, attempt, 'rotate', command='flip_h')
    act(game, snapshot, attempt, 'reset')
    q = attempt['current_question']
    assert q['commands'] == [] and q['undo_count'] == q['reset_count'] == 1
    assert q['first_action_ms'] == 123 and q['operations'] == 4
    for _ in range(16):
        act(game, snapshot, attempt, 'rotate', command='left')
    before = copy.deepcopy(snapshot)
    with pytest.raises(Conflict, match='aptitude_operation_limit'):
        act(game, snapshot, attempt, 'rotate', command='left')
    assert snapshot == before
    act(game, snapshot, attempt, 'submit')
    metrics = attempt['questions'][0]['metrics']
    assert metrics['rotation_count'] == 17 and metrics['flip_count'] == 1
    assert metrics['used_operations'] == 20 and metrics['submitted_operations'] == 16
    assert metrics['submitted_rotation_count'] == 16 and metrics['submitted_flip_count'] == 0
    assert metrics['operation_limit_reached'] is True
    summary_metrics = game.public_state(snapshot['aptitude_games'])['attempts'][0]['summary']['metrics']
    assert summary_metrics['rotation_count'] == 17 and summary_metrics['flip_count'] == 1
    assert summary_metrics['operation_limit_reached_count'] == 1


@pytest.mark.parametrize('kind', ['rotation', 'path', 'potion'])
def test_practice_is_unscored_and_completed_attempt_cannot_change(game, clock, kind):
    snapshot, attempt = start(game, kind, mode='practice')
    solve(game, snapshot, attempt)
    assert attempt['status'] == 'complete' and attempt['score'] == 0
    public = game.public_state(snapshot['aptitude_games'])['attempts'][0]
    assert public['summary']['excluded_from_summary'] is True
    assert public['summary']['max_score'] == 0 and public['summary']['normalized_score'] is None
    before = copy.deepcopy(attempt)
    with pytest.raises(Conflict):
        act(game, snapshot, attempt, 'submit', **({'choice': 'red'} if kind == 'potion' else {}))
    start(game, kind, snapshot=snapshot)
    assert snapshot['aptitude_games']['attempts'][0] == before


def test_path_cycles_are_persistent_count_changes_and_removals_and_limit(game, clock):
    snapshot, attempt = start(game, 'path', difficulty='hard')
    for i in range(19):
        clock[0] += 10
        act(game, snapshot, attempt, 'cell', row=0, col=0)
    q = attempt['current_question']
    assert q['fences'] == {'0,0': '/'}
    assert q['operations'] == 19 and q['fence_changes'] == 6 and q['fence_removals'] == 6
    assert q['first_action_ms'] == 10
    with pytest.raises(Conflict, match='aptitude_operation_limit'):
        act(game, snapshot, attempt, 'cell', row=1, col=1)
    act(game, snapshot, attempt, 'submit')
    metrics = attempt['questions'][0]['metrics']
    assert metrics['operations'] == 19 and metrics['fence_removals'] == 6
    assert len(metrics['vehicle_results']) >= 2


@pytest.mark.parametrize('kind', ['rotation', 'path'])
def test_complete_ten_question_journey_and_normalization(game, clock, kind):
    snapshot, attempt = start(game, kind)
    for i in range(10):
        clock[0] += 200
        solve(game, snapshot, attempt)
        assert attempt['score'] == (i + 1) * 10
        if i < 9:
            act(game, snapshot, attempt, 'next')
    public = game.public_state(snapshot['aptitude_games'])['attempts'][0]
    assert public['status'] == 'complete'
    summary = public['summary']
    assert summary['correct_count'] == 10 and summary['max_score'] == 100
    assert summary['normalized_score'] == 100 and summary['average_response_time_ms'] == 200
    assert len(public['questions']) == 10 and public['current_question'] is None


def test_floor_scoring_uses_each_question_order_and_rejects_double_submit(game, clock):
    snapshot, attempt = start(game, 'potion', 'quick')
    for correct, expected in [(False, 0), (True, 10), (False, 5), (False, 0), (True, 10)]:
        q = attempt['current_question']
        choice = q['outcome'] if correct else ('blue' if q['outcome'] == 'red' else 'red')
        act(game, snapshot, attempt, 'submit', choice=choice)
        assert attempt['score'] == expected
        before = copy.deepcopy(snapshot)
        with pytest.raises(Conflict):
            act(game, snapshot, attempt, 'submit', choice=choice)
        assert snapshot == before
        act(game, snapshot, attempt, 'next')


def test_total_expiry_settles_only_shown_question_and_preserves_unasked(game, clock):
    snapshot, attempt = start(game)
    solve(game, snapshot, attempt)
    act(game, snapshot, attempt, 'next')
    clock[0] += 240_000
    assert game.public_state(snapshot['aptitude_games'])['attempts'][0]['current_question']['remaining_ms'] == 0
    act(game, snapshot, attempt, 'submit')
    assert attempt['status'] == 'complete' and attempt['score'] == 5
    outcomes = [q['outcome'] for q in attempt['questions']]
    assert outcomes == ['correct', 'timeout'] + ['unasked'] * 8
    summary = game.public_state(snapshot['aptitude_games'])['attempts'][0]['summary']
    assert summary['timeout_count'] == 1 and summary['unasked_count'] == 8
    assert all(q.get('response_time_ms') is None and q['score_delta'] == 0 for q in attempt['questions'][2:])


def test_deadline_between_questions_does_not_invent_another_timeout(game, clock):
    snapshot, attempt = start(game)
    solve(game, snapshot, attempt)
    clock[0] += 240_000
    act(game, snapshot, attempt, 'next')
    assert [q['outcome'] for q in attempt['questions']] == ['correct'] + ['unasked'] * 9
    assert attempt['score'] == 10 and attempt['status'] == 'complete'


def test_potion_timeout_boundaries_and_stop_retain_records(game, clock):
    snapshot, attempt = start(game, 'potion', 'quick')
    with pytest.raises(Conflict):
        act(game, snapshot, attempt, 'timeout')
    clock[0] += 15_000
    act(game, snapshot, attempt, 'submit', choice='red')
    q = attempt['questions'][0]
    assert q['outcome'] == 'timeout' and q['metrics'].get('choice') is None
    assert q['result'].get('outcome') is None
    act(game, snapshot, attempt, 'next')
    act(game, snapshot, attempt, 'stop')
    assert attempt['status'] == 'interrupted'
    assert [q['outcome'] for q in attempt['questions']] == ['timeout', 'interrupted'] + ['unasked'] * 18
    start(game, 'potion', 'quick', snapshot=snapshot)
    assert len(snapshot['aptitude_games']['attempts']) == 2


def test_potion_all_active_surfaces_hide_seed_probabilities_and_favorable_color(game, clock):
    snapshot, attempt = start(game, 'potion', 'quick')
    for _ in range(2):
        solve(game, snapshot, attempt)
        act(game, snapshot, attempt, 'next')
    public = game.public_state(snapshot['aptitude_games'])
    encoded = json.dumps(public)
    for secret in ['red_probability', 'favorable_color', 'favorable_choice', 'seed', 'probabilities']:
        assert secret not in encoded
    records = public['attempts'][0]['questions']
    assert records[0]['result']['outcome'] in ('red', 'blue')
    assert 'outcome' not in public['attempts'][0]['current_question']
    act(game, snapshot, attempt, 'stop')
    ended = game.public_state(snapshot['aptitude_games'])['attempts'][0]
    assert isinstance(ended['seed'], int)
    assert ended['questions'][0]['red_probability'] in (0.8, 0.2, 0.65, 0.35, 0.7, 0.3)
    assert 'favorable_choice_rate' in ended['summary']['metrics']


def test_potion_learning_tracks_observed_outcomes_separately_from_favorable_choices(game, clock):
    snapshot, attempt = start(game, 'potion', 'quick')
    # A hand-checked controlled combination makes all later choices favorable,
    # but generated outcomes alternate; this tests state aggregation, not RNG.
    for i in range(20):
        q = attempt['current_question']
        q.update(combination_id='fixture-combo', red_probability=0.8, favorable_color='red', outcome='blue' if i % 2 == 0 else 'red')
        clock[0] += 100
        act(game, snapshot, attempt, 'submit', choice='blue' if i < 10 else 'red')
        if i < 19:
            act(game, snapshot, attempt, 'next')
    public = game.public_state(snapshot['aptitude_games'])['attempts'][0]
    metrics = public['summary']['metrics']
    assert metrics['prediction_hit_rate'] == 0.5
    assert metrics['favorable_choice_rate'] == 0.5
    assert metrics['early']['favorable_choice_rate'] == 0 and metrics['late']['favorable_choice_rate'] == 1
    combo = metrics['by_combination']['fixture-combo']
    assert combo['choice_count'] == 20 and combo['red_choice_rate'] == combo['blue_choice_rate'] == 0.5
    assert combo['choice_switch_count'] == 1 and combo['favorable_choice_change'] == 1
    assert combo['actual_outcomes'] == {'red': 10, 'blue': 10}
    assert len(combo['learning_transitions']) == 19
    assert public['summary']['max_score'] == 200


@pytest.mark.parametrize('body', [
    None, [], {'action': []}, {'action': 'start', 'game_type': [], 'mode': 'main', 'difficulty': 'easy'},
    {'action': 'start', 'game_type': 'rotation', 'mode': 'quick', 'difficulty': 'easy'},
    {'action': 'start', 'game_type': 'rotation', 'mode': True, 'difficulty': 'easy'},
    {'action': 'start', 'game_type': 'path', 'mode': 'main', 'difficulty': []},
    {'action': 'start', 'game_type': 'potion', 'mode': 'main', 'difficulty': 'easy', 'seed': 1},
])
def test_malformed_start_is_validation_without_mutating_snapshot(game, clock, body):
    snapshot = {}
    with pytest.raises(Validation):
        game.apply_action(snapshot, body)
    assert snapshot == {}


@pytest.mark.parametrize('extra', [
    {'action': 'cell', 'row': True, 'col': 0}, {'action': 'cell', 'row': 5, 'col': 0},
    {'action': 'cell', 'row': 0, 'col': -1}, {'action': 'cell', 'row': '0', 'col': 0},
    {'action': 'submit', 'fences': {}}, {'action': 'rotate', 'command': []},
    {'action': 'submit', 'question_id': []}, {'action': 'stop', 'attempt_id': False},
])
def test_malformed_actions_are_validation_not_server_errors(game, clock, extra):
    snapshot, attempt = start(game, 'path')
    before = copy.deepcopy(snapshot)
    body = {'action': 'submit', 'attempt_id': attempt['id'], 'question_id': attempt['current_question']['id'], **extra}
    with pytest.raises(Validation):
        game.apply_action(snapshot, body)
    assert snapshot == before


@pytest.mark.parametrize('limit', [48, 100])
def test_potion_main_completes_with_its_saved_limit_and_maximum(game, clock, monkeypatch, limit):
    from app.aptitude_config import GAME_CONFIG

    if limit == 100:
        with monkeypatch.context() as old:
            old.setitem(GAME_CONFIG['potion'], 'question_count', 100)
            snapshot, _ = start(game, 'potion', 'main', 'hard')
        snapshot = json.loads(json.dumps(snapshot))
        attempt = snapshot['aptitude_games']['attempts'][0]
    else:
        snapshot, attempt = start(game, 'potion', 'main', 'hard')
    assert attempt['question_limit'] == limit
    for number in range(limit):
        solve(game, snapshot, attempt)
        if number < limit - 1:
            assert attempt['status'] == 'active'
            act(game, snapshot, attempt, 'next')
    public = game.public_state(snapshot['aptitude_games'])['attempts'][0]
    assert public['status'] == 'complete' and public['question_limit'] == limit
    assert public['score'] == public['summary']['max_score'] == limit * 10
    assert public['summary']['normalized_score'] == 100
    assert public['summary']['correct_count'] == limit
    assert len(public['summary']['metrics']['by_combination']) == 6
    if limit == 48:
        for half in (attempt['questions'][:24], attempt['questions'][24:]):
            assert sorted(Counter(question['combination_id'] for question in half).values()) == [4] * 6


def test_config_snapshot_and_public_reads_cannot_change_attempt(game, clock, monkeypatch):
    snapshot, attempt = start(game)
    before = copy.deepcopy(snapshot)
    public = game.public_state(snapshot['aptitude_games'])
    public['attempts'][0]['config']['correct_points'] = 1000
    public['attempts'][0]['current_question']['commands'].append('left')
    assert snapshot == before
    from app import aptitude_config
    monkeypatch.setitem(aptitude_config.SCORING, 'correct_points', 999)
    solve(game, snapshot, attempt)
    assert attempt['score'] == 10 and attempt['max_score'] == 100


def test_stale_ids_active_lock_and_legacy_active_lock(game, clock):
    snapshot, attempt = start(game)
    with pytest.raises(Conflict, match='aptitude_active'):
        start(game, 'path', snapshot=snapshot)
    with pytest.raises(Conflict, match='aptitude_stale_question'):
        game.apply_action(snapshot, {'action': 'submit', 'attempt_id': attempt['id'], 'question_id': 'old-id'})
    for legacy in [
        {'rule_games': {'games': {'rsp': {'rounds': [{'status': 'in_progress'}]}}}},
        {'appointment_games': {'games': [{'status': 'active'}]}},
    ]:
        before = copy.deepcopy(legacy)
        with pytest.raises(Conflict, match='aptitude_active'):
            start(game, snapshot=legacy)
        assert legacy == before
