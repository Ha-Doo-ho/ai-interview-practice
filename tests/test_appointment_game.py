import pytest

from app import appointment_game as game
from app.store import Conflict, Validation


@pytest.fixture
def clock(monkeypatch):
    value = [1000000]
    monkeypatch.setattr(game, '_now', lambda: value[0])
    return value


def act(snapshot, action, **kwargs):
    game.apply_appointment_action(snapshot, {'action': action, **kwargs})


def setup_game(clock, difficulty='easy', kind='day'):
    snapshot = {'appointment_games': game.initial_appointment_games()}
    act(snapshot, 'configure', difficulty=difficulty)
    act(snapshot, 'start', game_type=kind)
    return snapshot


def test_timing_boundaries_and_redaction(clock):
    snapshot = setup_game(clock)
    state = snapshot['appointment_games']
    raw = state['games'][0]['questions'][0]
    for elapsed, phase, person in [(0, 'countdown', None), (2999, 'countdown', None), (3000, 'reveal', 0), (5999, 'reveal', 0), (6000, 'reveal', 1), (9000, 'reveal', 2), (12000, 'answer', None), (18000, 'timeout', None)]:
        clock[0] = 1000000 + elapsed
        public = game.public_appointment_state(state)['games'][0]['current_question']
        assert public['phase'] == phase
        assert public.get('person_index') == person
        assert 'answer' not in public and 'sets' not in public
        assert public.get('person') == (raw['sets'][person] if person is not None else None)
        assert ('choices' in public) == (phase in ('answer', 'timeout'))
    assert raw['outcome'] is None  # passing time is not a recorded answer
    act(snapshot, 'timeout', question_id=raw['id'])
    settled = game.public_appointment_state(state)['games'][0]['questions'][0]
    assert settled['outcome'] == 'timeout' and settled['answer'] == raw['answer']


def test_sequence_scoring_and_ten_questions(clock):
    snapshot = setup_game(clock)
    state = snapshot['appointment_games']
    with pytest.raises(Conflict):
        act(snapshot, 'start', game_type='place')
    for i in range(10):
        raw = state['games'][0]['questions'][-1]
        clock[0] = raw['started_at'] + 12000
        choice = raw['answer'] if i == 0 else next(c for c in raw['choices'] if c != raw['answer'])
        act(snapshot, 'answer', question_id=raw['id'], choice=choice)
        assert raw['score_before'] == (0 if i == 0 or i >= 3 else 10 - 5 * (i - 1))
        assert raw['score_after'] == max(0, raw['score_before'] + (10 if i == 0 else -5))
        assert raw['exposure_opportunities'] == [True, True, True]
        if i < 9:
            act(snapshot, 'next', question_id=raw['id'])
    assert state['games'][0]['status'] == 'complete'
    assert len(state['games'][0]['questions']) == 10
    with pytest.raises(Conflict):
        act(snapshot, 'next', question_id=raw['id'])
    act(snapshot, 'start', game_type='place')
    assert state['games'][1]['difficulty'] == 'easy'
    with pytest.raises(Conflict):
        act(snapshot, 'configure', difficulty='hard')


def test_validation_and_interrupt(clock):
    snapshot = setup_game(clock, 'hard')
    raw = snapshot['appointment_games']['games'][0]['questions'][0]
    with pytest.raises(Conflict):
        act(snapshot, 'answer', question_id=raw['id'], choice=raw['answer'])
    with pytest.raises(Conflict):
        act(snapshot, 'timeout', question_id=raw['id'])
    with pytest.raises(Conflict):
        act(snapshot, 'next', question_id=raw['id'])
    with pytest.raises(Validation):
        act(snapshot, 'answer', question_id=raw['id'], choice=True)
    with pytest.raises(Validation):
        act(snapshot, 'answer', question_id=raw['id'], choice=999)
    with pytest.raises(Validation):
        act(snapshot, 'start', game_type='day', surprise=1)
    clock[0] = raw['started_at'] + 10500
    with pytest.raises(Conflict):
        act(snapshot, 'answer', question_id=raw['id'], choice=raw['answer'])
    act(snapshot, 'timeout', question_id=raw['id'])
    assert raw['outcome'] == 'timeout'
    with pytest.raises(Conflict):
        act(snapshot, 'timeout', question_id=raw['id'])


def test_generated_question_rules(clock):
    snapshot = setup_game(clock)
    q = snapshot['appointment_games']['games'][0]['questions'][0]
    assert len(q['sets']) == 3 and all(len(s) == 3 for s in q['sets'])
    assert set.intersection(*(set(s) for s in q['sets'])) == {q['answer']}
    assert q['version'] and len(q['choices']) == 7

@pytest.mark.parametrize('kind,difficulty,count,choice_count', [
    ('day', 'easy', 3, 7), ('day', 'hard', 4, 7),
    ('place', 'easy', 3, 16), ('place', 'hard', 4, 16),
    ('bus', 'easy', 2, 6), ('bus', 'hard', 2, 6),
])
def test_question_generation_all_rules(kind, difficulty, count, choice_count):
    for _ in range(20):
        q = game._question(kind, difficulty, 1, 123)
        assert len(q['choices']) == choice_count
        assert len(set(q['choices'])) == choice_count
        assert len(q['sets']) == 3 and all(len(set(s)) == count for s in q['sets'])
        if kind == 'bus':
            assert q['answer'] not in set.union(*(set(s) for s in q['sets']))
            assert len(set.union(*(set(s) for s in q['sets']))) == 5
        else:
            assert set.intersection(*(set(s) for s in q['sets'])) == {q['answer']}
