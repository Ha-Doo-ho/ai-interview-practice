"""Server-authoritative appointment memory game; times are UTC epoch milliseconds."""
from __future__ import annotations

import copy
import secrets
import time
import uuid

from app.store import Conflict, Validation

VERSION = 'appointment-memory-v1'
TYPES = ('day', 'place', 'bus')
RULES = {
    'day': {'easy': (3, 3000, 6000), 'hard': (4, 1500, 3000)},
    'place': {'easy': (3, 3000, 5000), 'hard': (4, 1500, 3000)},
    'bus': {'easy': (2, 3000, 5000), 'hard': (2, 1500, 3000)},
}
_rng = secrets.SystemRandom()


def _now():
    return int(time.time() * 1000)


def initial_appointment_games():
    return {'version': VERSION, 'difficulty': None, 'games': [
        {'id': str(uuid.uuid4()), 'type': kind, 'status': 'pending', 'difficulty': None, 'score': 0, 'question_limit': 10, 'questions': []}
        for kind in TYPES
    ]}


def _question(kind, difficulty, number, now):
    count, reveal, answer_time = RULES[kind][difficulty]
    if kind == 'bus':
        numbers = _rng.sample(range(1, 900), 6)
        sets = [[numbers[0], numbers[1]], [numbers[2], numbers[3]],
                [numbers[4], numbers[_rng.randrange(4)]]]
        answer = numbers[5]
        choices = numbers[:]
        _rng.shuffle(choices)
    else:
        choices = list(range(7 if kind == 'day' else 16))
        pool = choices[:]
        _rng.shuffle(pool)
        answer = pool.pop()
        pattern = [[0, 1], [1, 2], [2, 3]] if count == 3 else [[0, 1, 2], [2, 3, 4], [0, 4, 5]]
        sets = [[answer, *(pool[i] for i in indices)] for indices in pattern]
    _rng.shuffle(sets)
    for values in sets:
        _rng.shuffle(values)
    return {'id': str(uuid.uuid4()), 'version': VERSION, 'number': number,
            'sets': sets, 'choices': choices, 'answer': answer,
            'started_at': now, 'countdown_ms': 3000, 'reveal_ms': [reveal] * 3,
            'answer_ms': answer_time, 'selection': None, 'outcome': None,
            'settled_at': None, 'exposure_opportunities': None,
            'score_before': None, 'score_after': None}


def _phase(q, now):
    elapsed = max(0, now - q['started_at'])
    if elapsed < q['countdown_ms']:
        return 'countdown', None, q['countdown_ms'] - elapsed
    boundary = q['countdown_ms']
    for i, duration in enumerate(q['reveal_ms']):
        boundary += duration
        if elapsed < boundary:
            return 'reveal', i, boundary - elapsed
    boundary += q['answer_ms']
    if elapsed < boundary:
        return 'answer', None, boundary - elapsed
    return 'timeout', None, 0


def public_appointment_state(state):
    now = _now()
    result = {'version': state['version'], 'difficulty': state['difficulty'], 'games': []}
    for game in state['games']:
        visible = {key: copy.deepcopy(game[key]) for key in ('id', 'type', 'status', 'difficulty', 'score', 'question_limit')}
        visible['questions'] = [copy.deepcopy(q) for q in game['questions'] if q['outcome'] is not None]
        visible['current_question'] = None
        if game['questions'] and game['questions'][-1]['outcome'] is None:
            q = game['questions'][-1]
            phase, index, remaining = _phase(q, now)
            current = {key: copy.deepcopy(q[key]) for key in ('id', 'version', 'number', 'started_at', 'countdown_ms', 'reveal_ms', 'answer_ms')}
            current.update(phase=phase, remaining_ms=remaining, person_index=index,
                           person=copy.deepcopy(q['sets'][index]) if index is not None else None)
            if phase in ('answer', 'timeout'):
                current['choices'] = copy.deepcopy(q['choices'])
            visible['current_question'] = current
        result['games'].append(visible)
    return result


def apply_appointment_action(snapshot, body):
    fields = {'configure': {'action', 'difficulty'}, 'start': {'action', 'game_type'},
              'answer': {'action', 'question_id', 'choice'}, 'timeout': {'action', 'question_id'},
              'next': {'action', 'question_id'}}
    if not isinstance(body, dict) or not isinstance(body.get('action'), str):
        raise Validation('validation_error')
    action = body['action']
    if action not in fields or set(body) != fields[action]:
        raise Validation('validation_error')
    if action == 'configure' and body['difficulty'] not in ('easy', 'hard'):
        raise Validation('validation_error')
    if action == 'start' and body['game_type'] not in TYPES:
        raise Validation('validation_error')
    if action in ('answer', 'timeout', 'next') and (not isinstance(body['question_id'], str) or not body['question_id']):
        raise Validation('validation_error')
    if action == 'answer' and type(body['choice']) is not int:
        raise Validation('validation_error')
    state = snapshot.setdefault('appointment_games', initial_appointment_games())
    games = state['games']
    if action == 'configure':
        if state['difficulty'] is not None or any(g['status'] != 'pending' for g in games):
            raise Conflict('appointment_already_configured')
        state['difficulty'] = body['difficulty']
        return
    if action == 'start':
        if state['difficulty'] is None:
            raise Conflict('appointment_difficulty_required')
        index = TYPES.index(body['game_type'])
        game = games[index]
        if game['status'] != 'pending' or any(g['status'] != 'complete' for g in games[:index]) or any(g['status'] == 'active' for g in games):
            raise Conflict('appointment_invalid_sequence')
        game['status'] = 'active'
        game['difficulty'] = state['difficulty']
        game['questions'].append(_question(game['type'], game['difficulty'], 1, _now()))
        return
    active = next((g for g in games if g['status'] == 'active'), None)
    if active is None or not active['questions'] or active['questions'][-1]['id'] != body['question_id']:
        raise Conflict('appointment_stale_question')
    q = active['questions'][-1]
    if action == 'answer' and body['choice'] not in q['choices']:
        raise Validation('validation_error')
    if action == 'next':
        if q['outcome'] is None or len(active['questions']) >= 10:
            raise Conflict('appointment_invalid_state')
        active['questions'].append(_question(active['type'], active['difficulty'], len(active['questions']) + 1, _now()))
        return
    if q['outcome'] is not None:
        raise Conflict('appointment_already_settled')
    now = _now()
    phase, _, _ = _phase(q, now)
    if action == 'answer' and phase != 'answer' or action == 'timeout' and phase != 'timeout':
        raise Conflict('appointment_invalid_phase')
    outcome = ('correct' if body['choice'] == q['answer'] else 'wrong') if action == 'answer' else 'timeout'
    q['selection'] = body['choice'] if action == 'answer' else None
    q['outcome'] = outcome
    q['settled_at'] = now
    q['exposure_opportunities'] = [True, True, True]
    q['score_before'] = active['score']
    active['score'] = max(0, active['score'] + (10 if outcome == 'correct' else -5))
    q['score_after'] = active['score']
    if len(active['questions']) == 10:
        active['status'] = 'complete'
