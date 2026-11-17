import copy

import pytest

from app.appointment_game import apply_appointment_action
from app.store import Validation


def appointment(monkeypatch, kind='day', outcome='correct'):
    clock = [1000]
    monkeypatch.setattr('app.appointment_game._now', lambda: clock[0])
    run = {}
    apply_appointment_action(run, {'action': 'configure', 'difficulty': 'easy'})
    # Create the later games directly with their production question generator;
    # this isolates validation of each game without replaying 20 questions.
    from app.appointment_game import _question
    state = run['appointment_games']
    game = next(g for g in state['games'] if g['type'] == kind)
    game['status'], game['difficulty'] = 'active', 'easy'
    q = _question(kind, 'easy', 1, clock[0])
    game['questions'].append(q)
    clock[0] += q['countdown_ms'] + sum(q['reveal_ms'])
    if outcome == 'timeout':
        clock[0] += q['answer_ms']
        apply_appointment_action(run, {'action': 'timeout', 'question_id': q['id']})
    else:
        choice = q['answer'] if outcome == 'correct' else next(c for c in q['choices'] if c != q['answer'])
        apply_appointment_action(run, {'action': 'answer', 'question_id': q['id'], 'choice': choice})
    return run


@pytest.mark.parametrize('kind,outcome', [('day', 'correct'), ('place', 'wrong'), ('bus', 'timeout')])
def test_report_preserves_actual_question_and_each_game_separately(monkeypatch, kind, outcome):
    from app.five_game_reporting import build_five_game_report
    run = appointment(monkeypatch, kind, outcome)
    report = build_five_game_report(run)
    assert report['version'] == 'five-game-report-v1'
    assert [g['type'] for g in report['games']] == ['rsp', 'card', 'day', 'place', 'bus']
    game = next(g for g in report['games'] if g['type'] == kind)
    source = next(g for g in run['appointment_games']['games'] if g['type'] == kind)['questions'][0]
    assert game['status'] == 'active'
    assert game['conditions']['difficulty'] == 'easy'
    assert game['totals']['settled'] == 1 and game['totals']['missing'] == 9
    assert game['evidence'][0]['outcome'] == outcome
    assert game['evidence'][0]['sets'] == source['sets']
    assert game['evidence'][0]['answer'] == source['answer']
    assert game['evidence'][0]['source_ref']['question_id'] == source['id']


@pytest.mark.parametrize('field,value', [('answer', 9999), ('outcome', 'wrong'), ('score_after', 99), ('settled_at', 1001)])
def test_tampered_settled_question_is_rejected(monkeypatch, field, value):
    from app.five_game_reporting import build_five_game_report
    run = appointment(monkeypatch)
    run['appointment_games']['games'][0]['questions'][0][field] = value
    with pytest.raises(Validation):
        build_five_game_report(run)


def test_unsettled_question_does_not_disclose_hidden_content(monkeypatch):
    from app.five_game_reporting import build_five_game_report
    run = appointment(monkeypatch)
    game = run['appointment_games']['games'][0]
    from app.appointment_game import _question
    game['questions'].append(_question('day', 'easy', 2, 20000))
    report = build_five_game_report(run)
    current = report['games'][2]['evidence'][1]
    assert current['outcome'] is None
    assert 'answer' not in current and 'sets' not in current and 'choices' not in current
    changed = copy.deepcopy(run)
    changed['appointment_games']['games'][0]['questions'][1]['started_at'] += 1
    assert report['source_digest'] != build_five_game_report(changed)['source_digest']


def test_rule_game_events_and_round_score_are_checked(monkeypatch):
    from datetime import datetime, timezone
    from app.five_game_reporting import build_five_game_report
    from app.rule_games import apply_rule_game_action
    monkeypatch.setattr('app.rule_games._now', lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
    run = {'user_id': 'u', 'run_id': 'r', 'attempt_id': 'a'}
    apply_rule_game_action(run, {'game_type': 'rsp', 'action': 'start'})
    round_state = run['rule_games']['games']['rsp']['rounds'][0]
    apply_rule_game_action(run, {'game_type': 'rsp', 'action': 'answer', 'round_id': round_state['round_id'],
                                 'stimulus_id': round_state['stimulus']['stimulus_id'], 'choice': 'rock'})
    report = build_five_game_report(run)
    evidence = report['games'][0]['evidence'][0]
    assert evidence['status'] == 'in_progress'
    assert len(evidence['responses']) == 1
    assert 'changed' not in evidence['rule_snapshot']
    round_state['score'] += 1
    with pytest.raises(Validation):
        build_five_game_report(run)


def rule_round(monkeypatch, kind='rsp', *, reveal=True, answer=True):
    from datetime import datetime, timedelta, timezone
    from app.rule_games import apply_rule_game_action
    clock = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr('app.rule_games._now', lambda: clock[0])
    run = {'user_id': 'u', 'run_id': 'r', 'attempt_id': 'a'}
    apply_rule_game_action(run, {'game_type': kind, 'action': 'start'})
    r = run['rule_games']['games'][kind]['rounds'][0]
    def choose():
        stimulus = r['stimulus']
        choice = 'rock' if kind == 'rsp' else stimulus['cards'][0]['card_id']
        apply_rule_game_action(run, {'game_type': kind, 'action': 'answer', 'round_id': r['round_id'],
                                     'stimulus_id': stimulus['stimulus_id'], 'choice': choice})
    if answer:
        choose()
    clock[0] += timedelta(seconds=10)
    if reveal:
        apply_rule_game_action(run, {'game_type': kind, 'action': 'reveal', 'round_id': r['round_id']})
        if answer:
            choose()
    clock[0] += timedelta(seconds=10)
    apply_rule_game_action(run, {'game_type': kind, 'action': 'finish', 'round_id': r['round_id']})
    return run, r


@pytest.mark.parametrize('kind,reveal,answer', [('rsp', True, True), ('card', True, True), ('card', False, False)])
def test_real_rule_event_timelines_are_accepted(monkeypatch, kind, reveal, answer):
    from app.five_game_reporting import build_five_game_report
    run, _ = rule_round(monkeypatch, kind, reveal=reveal, answer=answer)
    game = next(g for g in build_five_game_report(run)['games'] if g['type'] == kind)
    assert game['totals']['completed_rounds'] == 1


@pytest.mark.parametrize('mutation', ['unissued_stimulus', 'missing_end', 'early_end', 'early_reveal', 'wrong_end_score', 'late_response'])
def test_corrupted_rule_timeline_is_rejected(monkeypatch, mutation):
    from datetime import datetime, timedelta
    from app.five_game_reporting import build_five_game_report
    run, r = rule_round(monkeypatch)
    if mutation == 'unissued_stimulus':
        next(e for e in r['events'] if e['type'] == 'response_selected')['stimulus']['stimulus_id'] = 'not-issued'
    elif mutation == 'missing_end':
        r['events'].pop()
    elif mutation == 'early_end':
        event = r['events'][-1]
        event['server_at'] = r['revealed_at']
        event['elapsed_ms'] = 10000
        r['completed_at'] = event['server_at']
    elif mutation == 'early_reveal':
        event = next(e for e in r['events'] if e['type'] == 'rule_revealed')
        event['server_at'] = (datetime.fromisoformat(r['started_at']) + timedelta(seconds=9)).isoformat()
        event['elapsed_ms'] = 9000
        r['revealed_at'] = event['server_at']
    elif mutation == 'wrong_end_score':
        r['events'][-1]['score'] += 1
    else:
        response = [e for e in r['events'] if e['type'] == 'response_selected'][-1]
        following = r['events'][response['sequence_no']]
        response['server_at'] = following['server_at'] = r['deadline_at']
        response['elapsed_ms'] = following['elapsed_ms'] = 20000
    with pytest.raises(Validation):
        build_five_game_report(run)


def test_multiple_card_selections_and_visibility_are_accepted(monkeypatch):
    from datetime import datetime, timezone
    from app.rule_games import apply_rule_game_action
    from app.five_game_reporting import build_five_game_report
    monkeypatch.setattr('app.rule_games._now', lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
    run = {'user_id': 'u', 'run_id': 'r', 'attempt_id': 'a'}
    apply_rule_game_action(run, {'game_type': 'card', 'action': 'start'})
    r = run['rule_games']['games']['card']['rounds'][0]
    for card in r['stimulus']['cards'][:2]:
        apply_rule_game_action(run, {'game_type': 'card', 'action': 'answer', 'round_id': r['round_id'],
                                     'stimulus_id': r['stimulus']['stimulus_id'], 'choice': card['card_id']})
    apply_rule_game_action(run, {'game_type': 'card', 'action': 'visibility', 'round_id': r['round_id'], 'hidden': True})
    game = build_five_game_report(run)['games'][1]
    assert len(game['evidence'][0]['responses']) == 2


def test_wrong_bus_missing_answer_is_rejected(monkeypatch):
    from app.five_game_reporting import build_five_game_report
    run = appointment(monkeypatch, 'bus')
    q = run['appointment_games']['games'][2]['questions'][0]
    q['sets'][0][0] = q['answer']
    with pytest.raises(Validation):
        build_five_game_report(run)


def test_ten_completed_questions_keep_order_and_score(monkeypatch):
    from app.five_game_reporting import build_five_game_report
    clock = [1000]
    monkeypatch.setattr('app.appointment_game._now', lambda: clock[0])
    run = {}
    apply_appointment_action(run, {'action': 'configure', 'difficulty': 'hard'})
    apply_appointment_action(run, {'action': 'start', 'game_type': 'day'})
    for index in range(10):
        q = run['appointment_games']['games'][0]['questions'][-1]
        clock[0] += q['countdown_ms'] + sum(q['reveal_ms'])
        apply_appointment_action(run, {'action': 'answer', 'question_id': q['id'], 'choice': q['answer']})
        if index != 9:
            clock[0] += 1
            apply_appointment_action(run, {'action': 'next', 'question_id': q['id']})
    game = build_five_game_report(run)['games'][2]
    assert game['status'] == 'complete'
    assert game['totals'] == {'settled': 10, 'missing': 0, 'correct': 10, 'wrong': 0, 'timeout': 0, 'score': 100}
    assert [q['number'] for q in game['evidence']] == list(range(1, 11))
    second = run['appointment_games']['games'][0]['questions'][1]
    second['started_at'] = 1
    second['settled_at'] = 1 + second['countdown_ms'] + sum(second['reveal_ms'])
    with pytest.raises(Validation):
        build_five_game_report(run)
