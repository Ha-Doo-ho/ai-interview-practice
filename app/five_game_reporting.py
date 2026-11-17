"""Source-checked, separate game facts for the current practice run.

This module does not interpret performance or contact a provider. Unsettled
appointment questions are represented without their still-hidden contents.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta

from .appointment_game import RULES, TYPES, VERSION as APPOINTMENT_VERSION
from .evidence_linkage import game_observations
from .rule_games import RULE_GAME_DEFINITIONS
from .store import Validation

VERSION = 'five-game-report-v1'


def _require(condition):
    if not condition:
        raise Validation('five_game_report_invalid')


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def _validate_round_timeline(kind, round_state):
    """Replay issued stimuli and rule transitions against server event times."""
    events = round_state['events']
    _require(isinstance(events, list) and len(events) >= 2)
    start = datetime.fromisoformat(round_state['started_at'])
    deadline = datetime.fromisoformat(round_state['deadline_at'])
    due = datetime.fromisoformat(round_state['reveal_due_at'])
    _require(start.utcoffset() is not None and deadline.utcoffset() is not None and due.utcoffset() is not None)
    definition = round_state['definition_snapshot']
    duration, reveal_after = definition['duration_ms'], definition['reveal_after_ms']
    _require(type(duration) is int and type(reveal_after) is int and 0 < reveal_after < duration)
    _require(round_state['duration_ms'] == duration and deadline == start + timedelta(milliseconds=duration) and due == start + timedelta(milliseconds=reveal_after))
    rule_snapshot = round_state['rule_snapshot']
    current_rule, stimulus = rule_snapshot['initial'], None
    reveal, ended, issue_required = None, None, True
    previous = start
    for index, event in enumerate(events):
        time = datetime.fromisoformat(event['server_at'])
        _require(time.utcoffset() is not None and time >= previous and time >= start)
        _require(type(event.get('elapsed_ms')) is int and event['elapsed_ms'] == max(0, int((time - start).total_seconds() * 1000)))
        previous = time
        typ = event.get('type')
        if index == 0:
            _require(typ == 'round_started' and time == start)
            continue
        _require(ended is None)
        if issue_required:
            _require(typ == 'stimulus_issued' and event.get('rule') == current_rule)
            if stimulus is not None:
                _require(event.get('stimulus') == stimulus)
            stimulus = copy.deepcopy(event.get('stimulus'))
            _require(isinstance(stimulus, dict) and isinstance(stimulus.get('stimulus_id'), str) and bool(stimulus['stimulus_id']))
            if kind == 'card':
                _require(stimulus.get('selected_card_ids') == [])
            issue_required = False
        elif typ == 'response_selected':
            _require(time < deadline and (reveal is not None or time < due))
            _require(event.get('rule') == current_rule and event.get('stimulus') == stimulus)
            if kind == 'card':
                choice = event.get('choice')
                _require(choice not in stimulus['selected_card_ids'])
                stimulus['selected_card_ids'].append(choice)
            else:
                stimulus, issue_required = None, True
        elif typ == 'rule_revealed':
            _require(reveal is None and due <= time < deadline)
            reveal = event
            current_rule = rule_snapshot['changed']
            _require(event.get('rule') == current_rule)
            stimulus = copy.deepcopy(event.get('stimulus'))
            _require(isinstance(stimulus, dict))
            issue_required = True
        elif typ == 'round_ended':
            _require(time >= deadline and index == len(events)-1)
            ended = event
        else:
            _require(typ == 'visibility_reported')
    _require(not issue_required and stimulus == round_state.get('stimulus'))
    _require(round_state.get('rule') == current_rule)
    _require((reveal is None and round_state.get('revealed_at') is None) or
             (reveal is not None and round_state.get('revealed_at') == reveal['server_at']))
    if round_state['status'] == 'completed':
        _require(ended is not None and round_state.get('completed_at') == ended['server_at'] and round_state.get('phase') == 'completed')
        for key in ('score', 'correct_count', 'incorrect_count'):
            _require(type(ended.get(key)) is int and ended[key] == round_state.get(key))
    else:
        _require(ended is None and round_state.get('completed_at') is None and round_state.get('phase') == ('changed' if reveal else 'initial'))


def _appointment(kind, game, state):
    if game is None:
        return {'type': kind, 'status': 'missing', 'conditions': {}, 'totals': {'settled': 0, 'missing': 10}, 'evidence': []}
    _require(game.get('type') == kind and game.get('question_limit') == 10 and bool(game.get('id')))
    status, difficulty = game.get('status'), game.get('difficulty')
    _require(status in ('pending', 'active', 'complete'))
    questions = game.get('questions')
    _require(isinstance(questions, list) and len(questions) <= 10)
    _require((status == 'pending' and not questions and difficulty is None) or
             (status in ('active', 'complete') and difficulty in ('easy', 'hard') and bool(questions)))
    _require(difficulty is None or difficulty == state.get('difficulty'))
    score, evidence, outcomes, ids, last_settled = 0, [], [], set(), None
    for index, q in enumerate(questions, 1):
        _require(isinstance(q, dict) and q.get('number') == index and q.get('version') == APPOINTMENT_VERSION)
        qid = q.get('id')
        _require(isinstance(qid, str) and bool(qid) and qid not in ids)
        ids.add(qid)
        count, reveal, answer_ms = RULES[kind][difficulty]
        _require(q.get('countdown_ms') == 3000 and q.get('reveal_ms') == [reveal] * 3 and q.get('answer_ms') == answer_ms)
        started = q.get('started_at')
        _require(type(started) is int)
        _require(last_settled is None or started >= last_settled)
        sets, choices, answer = q.get('sets'), q.get('choices'), q.get('answer')
        _require(isinstance(sets, list) and len(sets) == 3 and isinstance(choices, list))
        _require(all(isinstance(s, list) and len(s) == count and all(type(v) is int for v in s) and len(set(s)) == count for s in sets))
        _require(all(type(v) is int for v in choices) and len(set(choices)) == len(choices) and type(answer) is int)
        _require(all(v in choices for s in sets for v in s) and answer in choices)
        if kind == 'bus':
            _require(len(choices) == 6 and all(1 <= v < 900 for v in choices))
            solution = set(choices) - set().union(*(set(s) for s in sets))
        else:
            _require(choices == list(range(7 if kind == 'day' else 16)))
            solution = set(sets[0]).intersection(*map(set, sets[1:]))
        _require(solution == {answer})
        ref = {'game_id': game['id'], 'game_version': state['version'], 'question_id': qid, 'question_version': q['version']}
        record = {'source_ref': ref, 'number': index, 'difficulty': difficulty, 'outcome': q.get('outcome'),
                  'started_at': started, 'countdown_ms': q['countdown_ms'], 'reveal_ms': copy.deepcopy(q['reveal_ms']), 'answer_ms': answer_ms}
        outcome = q.get('outcome')
        if outcome is None:
            _require(index == len(questions) and status == 'active' and all(q.get(k) is None for k in ('selection', 'settled_at', 'score_before', 'score_after', 'exposure_opportunities')))
        else:
            _require(outcome in ('correct', 'wrong', 'timeout') and q.get('exposure_opportunities') == [True, True, True])
            settled, selection = q.get('settled_at'), q.get('selection')
            begin = started + q['countdown_ms'] + sum(q['reveal_ms'])
            _require(type(settled) is int and (settled >= begin + answer_ms if outcome == 'timeout' else begin <= settled < begin + answer_ms))
            _require((outcome == 'timeout' and selection is None) or (type(selection) is int and selection in choices and outcome == ('correct' if selection == answer else 'wrong')))
            after = max(0, score + (10 if outcome == 'correct' else -5))
            _require(type(q.get('score_before')) is int and q['score_before'] == score and type(q.get('score_after')) is int and q['score_after'] == after)
            score = after
            last_settled = settled
            outcomes.append(outcome)
            record.update({k: copy.deepcopy(q[k]) for k in ('sets', 'choices', 'answer', 'selection', 'settled_at', 'exposure_opportunities', 'score_before', 'score_after')})
        evidence.append(record)
    _require(type(game.get('score')) is int and game['score'] == score)
    _require((status == 'complete') == (len(outcomes) == 10))
    return {'type': kind, 'game_id': game['id'], 'game_version': state['version'], 'status': status,
            'source_ref': {'game_id': game['id'], 'game_version': state['version']},
            'conditions': {'difficulty': difficulty, 'question_limit': 10,
                           'question_conditions': [{'question_id': e['source_ref']['question_id'], 'countdown_ms': e['countdown_ms'], 'reveal_ms': e['reveal_ms'], 'answer_ms': e['answer_ms']} for e in evidence]},
            'totals': {'settled': len(outcomes), 'missing': 10-len(outcomes), 'correct': outcomes.count('correct'), 'wrong': outcomes.count('wrong'), 'timeout': outcomes.count('timeout'), 'score': score}, 'evidence': evidence}


def _rule_game(kind, game, state, observations, run):
    if game is None:
        return {'type': kind, 'status': 'missing', 'conditions': {}, 'totals': {'completed_rounds': 0, 'missing_rounds': 3}, 'evidence': []}
    definition = RULE_GAME_DEFINITIONS['games'][kind]
    _require(game.get('game_type') == kind and game.get('game_id') == definition['game_id'] and game.get('game_version') == definition['game_version'])
    rounds = game.get('rounds')
    _require(isinstance(rounds, list) and len(rounds) <= 3)
    evidence = []
    for i, round_state in enumerate(rounds, 1):
        _require(round_state.get('index') == i and round_state.get('status') in ('in_progress', 'completed'))
        _require(all(round_state.get('lineage', {}).get(k) == run.get(k) for k in ('user_id', 'run_id', 'attempt_id')))
        matches = [o for o in observations if o['game_type'] == kind and o['round_id'] == round_state.get('round_id')]
        _require(len(matches) == 1)
        observation = matches[0]
        score = correct = wrong = 0
        scoring = round_state.get('scoring_snapshot') or {}
        _require(scoring == {'correct_points': 10, 'incorrect_points': -5, 'score_floor': 0})
        events = round_state.get('events') or []
        _require(all(e.get('sequence_no') == j and bool(e.get('event_id')) for j, e in enumerate(events, 1)))
        _require(len({e['event_id'] for e in events}) == len(events))
        _validate_round_timeline(kind, round_state)
        for event in events:
            if event.get('type') == 'response_selected':
                _require(type(event.get('correct')) is bool and type(event.get('score_before')) is int and event.get('score_before') == score)
                if kind == 'rsp':
                    _require(event.get('choice') in ('rock', 'paper', 'scissors'))
                score = max(0, score + (10 if event['correct'] else -5))
                _require(type(event.get('score_after')) is int and event['score_after'] == score)
                correct += int(event['correct']); wrong += int(not event['correct'])
        _require(all(type(round_state.get(k)) is int for k in ('score', 'correct_count', 'incorrect_count')))
        _require((round_state.get('score'), round_state.get('correct_count'), round_state.get('incorrect_count')) == (score, correct, wrong))
        responses = copy.deepcopy(observation['response_details'])
        events_by_id = {event['event_id']: event for event in events}
        for response in responses:
            event = events_by_id[response['event_id']]
            response.update({k: copy.deepcopy(event.get(k)) for k in ('server_at', 'elapsed_ms', 'score_before', 'score_after')})
        visible_rules = copy.deepcopy(round_state.get('rule_snapshot') or {})
        if observation['disclosure_status'] != 'recorded':
            visible_rules.pop('changed', None)
        evidence.append({'source_ref': {'game_id': game['game_id'], 'game_version': game['game_version'], 'round_id': round_state['round_id'], 'event_refs': observation['event_refs']},
                         'round_index': i, 'status': round_state['status'], 'started_at': round_state.get('started_at'), 'completed_at': round_state.get('completed_at'),
                         'duration_ms': round_state.get('duration_ms'), 'rule_snapshot': visible_rules,
                         'score': score, 'correct_count': correct, 'incorrect_count': wrong, 'responses': responses,
                         'missing_reason': observation['missing_reason']})
    completed = sum(r['status'] == 'completed' for r in rounds)
    status = 'completed' if completed == 3 else 'in_progress' if rounds else 'pending'
    return {'type': kind, 'game_id': game['game_id'], 'game_version': game['game_version'], 'status': status,
            'source_ref': {'game_id': game['game_id'], 'game_version': game['game_version']},
            'conditions': {'round_limit': 3, 'round_conditions': [copy.deepcopy(r.get('definition_snapshot')) for r in rounds]},
            'totals': {'completed_rounds': completed, 'missing_rounds': 3-completed}, 'evidence': evidence}


def build_five_game_report(run: dict) -> dict:
    try:
        _require(isinstance(run, dict))
        rules, appointment = run.get('rule_games'), run.get('appointment_games')
        _require(rules is None or isinstance(rules, dict))
        _require(appointment is None or isinstance(appointment, dict))
        if appointment is not None:
            _require(appointment.get('version') == APPOINTMENT_VERSION and isinstance(appointment.get('games'), list))
            types = [g.get('type') for g in appointment['games']]
            _require(len(types) == 3 and set(types) == set(TYPES))
        observations = game_observations(run)
        rule_games = (rules or {}).get('games', {})
        _require(isinstance(rule_games, dict))
        games = [_rule_game(kind, rule_games.get(kind), rules or {}, observations, run) for kind in ('rsp', 'card')]
        for kind in TYPES:
            game = next((g for g in (appointment or {}).get('games', []) if g.get('type') == kind), None)
            games.append(_appointment(kind, game, appointment or {}))
        return {'version': VERSION, 'source_digest': _digest({'rule_games': rules, 'appointment_games': appointment}), 'games': games}
    except Validation:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, StopIteration, OverflowError):
        raise Validation('five_game_report_invalid') from None
