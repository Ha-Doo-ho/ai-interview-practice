"""Server-owned optional game attempts, manipulation evidence and score summaries.

Store.mutate owns user authorization, revisions, idempotency and run finalization.
This module accepts only player intentions; clients never submit timing or scores.
"""
from __future__ import annotations

import copy
import random
import secrets
import time
from uuid import uuid4

from . import aptitude_path, aptitude_potion, aptitude_rotation
from .aptitude_config import DISCLAIMER, GAME_CONFIG, VERSION, config_for, definitions
from .store import Conflict, Validation

_ALGORITHMS = {'rotation': aptitude_rotation, 'path': aptitude_path, 'potion': aptitude_potion}
_COMMANDS = ('left', 'right', 'flip_h', 'flip_v')
_ID_FIELDS = {'action', 'attempt_id', 'question_id'}
_FIELDS = {'start': {'action', 'game_type', 'mode', 'difficulty'},
           'rotate': _ID_FIELDS | {'command'}, 'cell': _ID_FIELDS | {'row', 'col'},
           'undo': _ID_FIELDS, 'reset': _ID_FIELDS, 'submit': _ID_FIELDS,
           'next': _ID_FIELDS, 'stop': _ID_FIELDS, 'timeout': _ID_FIELDS}
_ACTIVE_HIDDEN = {'red_probability', 'favorable_color', 'favorable_choice', 'seed',
                  'favorable_choice_rate', 'favorable_choice_change'}


def _now() -> int:
    return int(time.time() * 1000)


def _string(value) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 128


def _validate(body: dict) -> None:
    if not isinstance(body, dict) or not isinstance(body.get('action'), str):
        raise Validation('validation_error')
    action = body['action']
    if action not in _FIELDS:
        raise Validation('validation_error')
    expected = _FIELDS[action]
    if action == 'submit' and 'choice' in body:
        expected = expected | {'choice'}
    if set(body) != expected:
        raise Validation('validation_error')
    if action == 'start':
        if (not _string(body['game_type']) or body['game_type'] not in GAME_CONFIG
                or not _string(body['mode']) or body['mode'] not in ('main', 'practice', 'quick')
                or not _string(body['difficulty']) or body['difficulty'] not in ('easy', 'hard')
                or body['mode'] == 'quick' and body['game_type'] != 'potion'):
            raise Validation('validation_error')
        return
    if not _string(body['attempt_id']) or not _string(body['question_id']):
        raise Validation('validation_error')
    if action == 'rotate' and (not _string(body['command']) or body['command'] not in _COMMANDS):
        raise Validation('validation_error')
    if action == 'cell' and (type(body['row']) is not int or type(body['col']) is not int):
        raise Validation('validation_error')
    if 'choice' in body and (not _string(body['choice']) or body['choice'] not in ('red', 'blue')):
        raise Validation('validation_error')


def _legacy_active(snapshot: dict) -> bool:
    return (any(r.get('status') in ('in_progress', 'active')
                for g in snapshot.get('rule_games', {}).get('games', {}).values()
                for r in g.get('rounds', []))
            or any(g.get('status') == 'active'
                   for g in snapshot.get('appointment_games', {}).get('games', [])))


def _new_question(attempt: dict, now: int) -> dict:
    number = len(attempt['questions']) + 1
    rng = random.Random(f"{attempt['seed']}:{number}")
    q = _ALGORITHMS[attempt['type']].generate(rng, number, attempt['difficulty'], attempt['config'])
    q.update(id=str(uuid4()), number=number, started_at=now, operations=0,
             first_action_ms=None, undo_count=0, reset_count=0, events=[])
    if attempt['type'] == 'rotation':
        q['commands'] = []
    if attempt['type'] == 'path':
        q.update(fences={}, fence_changes=0, fence_removals=0)
    return q


def _start(snapshot: dict, body: dict, now: int) -> None:
    state = snapshot.get('aptitude_games', {'version': VERSION, 'attempts': []})
    if any(a['status'] == 'active' for a in state['attempts']) or _legacy_active(snapshot):
        raise Conflict('aptitude_active')
    config = config_for(body['game_type'], body['mode'])
    attempt = {'id': str(uuid4()), 'version': VERSION, 'type': body['game_type'],
               'mode': body['mode'], 'difficulty': body['difficulty'], 'status': 'active',
               'seed': secrets.randbits(128), 'score': 0, 'started_at': now, 'completed_at': None,
               'question_limit': config['question_count'], 'config': config, 'questions': []}
    attempt['max_score'] = 0 if attempt['mode'] == 'practice' else attempt['question_limit'] * config['correct_points']
    attempt['current_question'] = _new_question(attempt, now)
    state['attempts'].append(attempt)
    snapshot['aptitude_games'] = state


def _total_remaining(attempt: dict, now: int) -> int | None:
    duration = attempt['config']['total_duration_ms']
    return None if duration is None else max(0, attempt['started_at'] + duration - now)


def _question_remaining(attempt: dict, q: dict, now: int) -> int | None:
    remaining = _total_remaining(attempt, now)
    duration = attempt['config']['question_duration_ms']
    if duration is not None:
        question_remaining = max(0, q['started_at'] + duration - now)
        remaining = question_remaining if remaining is None else min(remaining, question_remaining)
    return remaining


def _response(attempt: dict, q: dict, body: dict | None) -> dict:
    if attempt['type'] == 'rotation':
        return {'commands': q['commands']}
    if attempt['type'] == 'path':
        return {'fences': q['fences']}
    return {'choice': body['choice']} if body and 'choice' in body else {}


def _settle(attempt: dict, now: int, outcome: str | None = None, body: dict | None = None) -> None:
    q = attempt['current_question']
    response = _response(attempt, q, body)
    result = {}
    # A timeout/interruption is never represented as a potion prediction or draw.
    # Geometry may still report the player's actual saved board/command state.
    if outcome is None or attempt['type'] != 'potion':
        result = _ALGORITHMS[attempt['type']].evaluate(q, response)
    if outcome is None:
        outcome = 'correct' if result['correct'] else 'wrong'
    metrics = copy.deepcopy(result.get('metrics', {}))
    response_time = max(0, now - q['started_at'])
    metrics.update(operations=q['operations'], first_action_ms=q['first_action_ms'],
                   response_time_ms=response_time, undo_count=q['undo_count'], reset_count=q['reset_count'])
    maximum = attempt['config']['max_operations']
    metrics['operation_limit_reached'] = maximum is not None and q['operations'] >= maximum
    if attempt['type'] == 'rotation':
        # Submitted geometry is distinct from all actions actually performed.
        metrics.update(submitted_operations=metrics['used_operations'],
                       submitted_rotation_count=metrics['rotation_count'],
                       submitted_flip_count=metrics['flip_count'],
                       used_operations=q['operations'],
                       excess_operations=max(0, q['operations'] - metrics['min_operations']),
                       rotation_count=sum(e['action'] == 'rotate' and e['command'] in ('left', 'right') for e in q['events']),
                       flip_count=sum(e['action'] == 'rotate' and e['command'] in ('flip_h', 'flip_v') for e in q['events']))
    if attempt['type'] == 'path':
        metrics.update(fence_changes=q['fence_changes'], fence_removals=q['fence_removals'])
    delta = (attempt['config']['correct_points'] if outcome == 'correct'
             else attempt['config']['incorrect_points'] if outcome in ('wrong', 'timeout') else 0)
    if attempt['mode'] == 'practice':
        delta = 0
    score_before = attempt['score']
    attempt['score'] = max(attempt['config']['score_floor'], score_before + delta)
    record = copy.deepcopy(q)
    # q.outcome for potion is a private pregenerated draw, so overwrite it with
    # the settlement state and retain a draw only when a prediction occurred.
    record.update(outcome=outcome, response=copy.deepcopy(response), settled_at=now,
                  response_time_ms=response_time, score_before=score_before,
                  score_after=attempt['score'], score_delta=attempt['score'] - score_before,
                  scoring_delta=delta, metrics=metrics, result=result)
    attempt['questions'].append(record)
    attempt['current_question'] = None
    if len(attempt['questions']) == attempt['question_limit']:
        attempt.update(status='complete', completed_at=now)


def _finish(attempt: dict, now: int, status: str) -> None:
    for number in range(len(attempt['questions']) + 1, attempt['question_limit'] + 1):
        attempt['questions'].append({'id': str(uuid4()), 'number': number, 'outcome': 'unasked',
                                     'response_time_ms': None, 'score_before': attempt['score'],
                                     'score_after': attempt['score'], 'score_delta': 0,
                                     'scoring_delta': 0, 'metrics': {}, 'result': {}})
    attempt.update(status=status, completed_at=now, current_question=None)


def _record_event(q: dict, now: int, action: str, **facts) -> None:
    elapsed = max(0, now - q['started_at'])
    q['events'].append({'sequence_no': len(q['events']) + 1, 'action': action,
                        'server_at': now, 'elapsed_ms': elapsed, **facts})
    q['operations'] += 1
    if q['first_action_ms'] is None:
        q['first_action_ms'] = elapsed


def apply_action(snapshot: dict, body: dict) -> None:
    _validate(body)
    now = _now()
    action = body['action']
    if action == 'start':
        _start(snapshot, body, now)
        return
    attempt = next((a for a in snapshot.get('aptitude_games', {}).get('attempts', [])
                    if a['id'] == body['attempt_id']), None)
    if attempt is None or attempt['status'] != 'active':
        raise Conflict('aptitude_invalid_state')
    kind = attempt['type']
    if (action == 'rotate' and kind != 'rotation' or action in ('undo', 'reset') and kind != 'rotation'
            or action == 'cell' and kind != 'path'
            or action == 'submit' and (('choice' in body) != (kind == 'potion'))):
        raise Validation('validation_error')
    if action == 'cell' and not (0 <= body['row'] < attempt['config']['board_size']
                                 and 0 <= body['col'] < attempt['config']['board_size']):
        raise Validation('validation_error')
    q = attempt['current_question']
    expected = q if q is not None else attempt['questions'][-1] if attempt['questions'] else None
    if expected is None or expected['id'] != body['question_id']:
        raise Conflict('aptitude_stale_question')
    if q is None and action not in ('next', 'stop', 'timeout'):
        raise Conflict('aptitude_invalid_state')
    if q is not None and action == 'next':
        raise Conflict('aptitude_invalid_state')
    if _total_remaining(attempt, now) == 0:
        if q is not None:
            _settle(attempt, now, 'interrupted' if action == 'stop' else 'timeout')
        _finish(attempt, now, 'interrupted' if action == 'stop' else 'complete')
        return
    if q is not None and _question_remaining(attempt, q, now) == 0:
        _settle(attempt, now, 'timeout')
        if action == 'stop':
            _finish(attempt, now, 'interrupted')
        return
    if action == 'stop':
        if q is not None:
            _settle(attempt, now, 'interrupted')
        _finish(attempt, now, 'interrupted')
        return
    if action == 'timeout':
        raise Conflict('aptitude_invalid_state')
    if action == 'next':
        attempt['current_question'] = _new_question(attempt, now)
        return
    if action == 'submit':
        _settle(attempt, now, body=body)
        return
    if q['operations'] >= attempt['config']['max_operations']:
        raise Conflict('aptitude_operation_limit')
    if action == 'rotate':
        q['commands'].append(body['command'])
        _record_event(q, now, action, command=body['command'])
    elif action == 'undo':
        if not q['commands']:
            raise Conflict('aptitude_invalid_state')
        removed = q['commands'].pop()
        q['undo_count'] += 1
        _record_event(q, now, action, removed_command=removed)
    elif action == 'reset':
        if not q['commands']:
            raise Conflict('aptitude_invalid_state')
        removed = q['commands'][:]
        q['commands'].clear()
        q['reset_count'] += 1
        _record_event(q, now, action, removed_commands=removed)
    elif action == 'cell':
        key = f"{body['row']},{body['col']}"
        before = q['fences'].get(key)
        after = '/' if before is None else '\\' if before == '/' else None
        if after is None:
            del q['fences'][key]
            q['fence_removals'] += 1
        else:
            q['fences'][key] = after
            if before is not None:
                q['fence_changes'] += 1
        _record_event(q, now, action, row=body['row'], col=body['col'], before=before, after=after)


def _mean(values):
    return round(sum(values) / len(values), 3) if values else None


def _rate(numerator, denominator):
    return round(numerator / denominator, 6) if denominator else None


def _choice_stats(records: list[dict]) -> dict:
    selected = [q for q in records if q['metrics'].get('choice') in ('red', 'blue')]
    count = len(selected)
    red = sum(q['metrics']['choice'] == 'red' for q in selected)
    return {'choice_count': count, 'red_choice_count': red, 'blue_choice_count': count - red,
            'red_choice_rate': _rate(red, count), 'blue_choice_rate': _rate(count - red, count),
            'favorable_choice_rate': _rate(sum(q['metrics'].get('favorable_choice') is True for q in selected), count)}


def _potion_metrics(attempt: dict, records: list[dict]) -> dict:
    selected = [q for q in records if q['metrics'].get('choice') in ('red', 'blue')]
    # Fixed halves of the planned attempt retain the original exposure order.
    boundary = attempt['question_limit'] // 2
    early = _choice_stats([q for q in selected if q['number'] <= boundary])
    late = _choice_stats([q for q in selected if q['number'] > boundary])
    metrics = {**_choice_stats(selected), 'early': early, 'late': late,
               'prediction_hit_rate': _rate(sum(q['outcome'] == 'correct' for q in selected), len(selected)),
               'by_combination': {}}
    grouped = {}
    for q in selected:
        grouped.setdefault(q['combination_id'], []).append(q)
    for combination, questions in grouped.items():
        stats = _choice_stats(questions)
        first = _choice_stats([q for q in questions if q['number'] <= boundary])
        last = _choice_stats([q for q in questions if q['number'] > boundary])
        transitions = []
        for before, after in zip(questions, questions[1:]):
            previous, current = before['metrics']['choice'], after['metrics']['choice']
            observed = before['metrics']['actual_outcome']
            transitions.append({'from_question': before['number'], 'to_question': after['number'],
                                'previous_choice': previous, 'observed_outcome': observed,
                                'choice': current, 'switched': previous != current,
                                'followed_previous_outcome': current == observed,
                                'previous_prediction_hit': before['outcome'] == 'correct'})
        stats.update(early=first, late=last,
                     favorable_choice_change=(round(last['favorable_choice_rate'] - first['favorable_choice_rate'], 6)
                                               if first['favorable_choice_rate'] is not None and last['favorable_choice_rate'] is not None else None),
                     choice_switch_count=sum(t['switched'] for t in transitions),
                     followed_previous_outcome_count=sum(t['followed_previous_outcome'] for t in transitions),
                     switch_after_miss_count=sum(t['switched'] and not t['previous_prediction_hit'] for t in transitions),
                     stay_after_hit_count=sum(not t['switched'] and t['previous_prediction_hit'] for t in transitions),
                     learning_transitions=transitions,
                     actual_outcomes={color: sum(q['metrics']['actual_outcome'] == color for q in questions) for color in ('red', 'blue')},
                     average_response_time_ms=_mean([q['response_time_ms'] for q in questions]))
        metrics['by_combination'][combination] = stats
    return metrics


def _summary(attempt: dict) -> dict:
    records = attempt['questions']
    shown = [q for q in records if q['outcome'] != 'unasked']
    answered = [q for q in records if q['outcome'] in ('correct', 'wrong')]
    result = {'total_questions': attempt['question_limit'], 'answered_count': len(answered),
              'correct_count': sum(q['outcome'] == 'correct' for q in records),
              'wrong_count': sum(q['outcome'] == 'wrong' for q in records),
              'timeout_count': sum(q['outcome'] == 'timeout' for q in records),
              'unasked_count': sum(q['outcome'] == 'unasked' for q in records),
              'interrupted_count': sum(q['outcome'] == 'interrupted' for q in records),
              'score': attempt['score'], 'max_score': attempt['max_score'],
              'normalized_score': round(attempt['score'] / attempt['max_score'] * 100, 3) if attempt['max_score'] else None,
              'average_response_time_ms': _mean([q['response_time_ms'] for q in answered]),
              'excluded_from_summary': attempt['mode'] == 'practice', 'disclaimer': DISCLAIMER}
    kind = attempt['type']
    if kind == 'potion':
        result['metrics'] = _potion_metrics(attempt, shown)
    else:
        metrics = {'total_operations': sum(q['metrics'].get('operations', 0) for q in shown),
                   'average_operations': _mean([q['metrics'].get('operations', 0) for q in shown]),
                   'operation_limit_reached_count': sum(q['metrics'].get('operation_limit_reached') is True for q in shown),
                   'average_first_action_ms': _mean([q['metrics']['first_action_ms'] for q in shown if q['metrics'].get('first_action_ms') is not None]),
                   'per_question': [{'number': q['number'], 'outcome': q['outcome'], **copy.deepcopy(q['metrics'])} for q in shown]}
        if kind == 'rotation':
            total_used = sum(q['metrics'].get('used_operations', 0) for q in shown)
            total_min = sum(q['metrics'].get('min_operations', 0) for q in shown)
            successful = [q for q in shown if q['outcome'] == 'correct']
            metrics.update(used_operations=total_used, min_operations=total_min,
                           rotation_count=sum(q['metrics'].get('rotation_count', 0) for q in shown),
                           flip_count=sum(q['metrics'].get('flip_count', 0) for q in shown),
                           submitted_operations=sum(q['metrics'].get('submitted_operations', 0) for q in shown),
                           undo_count=sum(q['metrics'].get('undo_count', 0) for q in shown),
                           reset_count=sum(q['metrics'].get('reset_count', 0) for q in shown),
                           operation_efficiency=_mean([min(1.0, q['metrics']['min_operations'] / max(1, q['metrics']['operations'])) for q in successful]))
        else:
            metrics.update(used_fences=sum(q['metrics'].get('used_fences', 0) for q in shown),
                           minimum_fences=sum(q['metrics'].get('minimum_fences', 0) for q in shown),
                           fence_changes=sum(q['metrics'].get('fence_changes', 0) for q in shown),
                           fence_removals=sum(q['metrics'].get('fence_removals', 0) for q in shown))
        result['metrics'] = metrics
    return result


def _redact_active(value):
    if isinstance(value, dict):
        return {k: _redact_active(v) for k, v in value.items() if k not in _ACTIVE_HIDDEN}
    if isinstance(value, list):
        return [_redact_active(item) for item in value]
    return copy.deepcopy(value)


def _public_record(attempt: dict, q: dict) -> dict:
    fields = ('id', 'number', 'outcome', 'started_at', 'settled_at', 'response_time_ms',
              'score_before', 'score_after', 'score_delta', 'scoring_delta', 'response',
              'commands', 'fences', 'events', 'metrics', 'result')
    result = {key: copy.deepcopy(q[key]) for key in fields if key in q}
    if q['outcome'] != 'unasked':
        result.update(_ALGORITHMS[attempt['type']].public_question(q, practice=False))
    if attempt['status'] != 'active' and attempt['type'] == 'potion' and q['outcome'] != 'unasked':
        result.update(red_probability=q['red_probability'], favorable_color=q['favorable_color'])
    return _redact_active(result) if attempt['status'] == 'active' else result


def public_state(state: dict | None) -> dict:
    state = state or {'version': VERSION, 'attempts': []}
    now = _now()
    result = {'version': state['version'], 'attempts': []}
    for attempt in state['attempts']:
        keys = ('id', 'version', 'type', 'mode', 'difficulty', 'status', 'score', 'max_score',
                'question_limit', 'config', 'started_at', 'completed_at')
        public = {key: copy.deepcopy(attempt[key]) for key in keys}
        public['remaining_ms'] = _total_remaining(attempt, now) if attempt['status'] == 'active' else 0
        public['questions'] = [_public_record(attempt, q) for q in attempt['questions']]
        public['summary'] = _summary(attempt)
        public['current_question'] = None
        q = attempt['current_question']
        if q is not None:
            current = _ALGORITHMS[attempt['type']].public_question(q, practice=attempt['mode'] == 'practice')
            current.update({key: copy.deepcopy(q[key]) for key in ('id', 'number', 'started_at', 'operations', 'undo_count', 'reset_count')})
            current['remaining_ms'] = _question_remaining(attempt, q, now)
            maximum = attempt['config']['max_operations']
            current['operation_limit_reached'] = maximum is not None and q['operations'] >= maximum
            for field in ('commands', 'fences'):
                if field in q:
                    current[field] = copy.deepcopy(q[field])
            public['current_question'] = current
        if attempt['status'] == 'active':
            public = _redact_active(public)
        else:
            public['seed'] = attempt['seed']
        result['attempts'].append(public)
    return result
