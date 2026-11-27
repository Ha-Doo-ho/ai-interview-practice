"""Render game observations from the same saved evidence used by synthesis."""

GAME_NAMES = {
    'rsp': '가위바위보', 'card': '숫자 카드', 'day': '약속 요일',
    'place': '약속 장소', 'bus': '버스 기억하기', 'rotation': '도형 회전',
    'path': '길 만들기', 'potion': '마법약 만들기',
}
ADVICE = {
    'rsp': '규칙이 바뀌면 이겨야 하는지, 져야 하는지부터 확인해 보세요. 다음 시도에서 변경 전후의 정답 수와 응답 수를 비교하세요.',
    'card': '새 규칙의 조건을 한 번 말해 본 뒤 그 조건에 맞는 카드만 골라 보세요. 다음 시도에서 변경 직후에 한 선택을 되짚어 보세요.',
    'day': '요일을 보면서 세 사람이 공통으로 고른 후보를 좁혀 보세요. 다음 시도의 정답·시간 초과 횟수를 확인하세요.',
    'place': '장소 지도의 기준점을 정해 위치를 묶어 기억해 보세요. 다음 시도의 정답·시간 초과 횟수를 확인하세요.',
    'bus': '이미 탑승한 버스를 먼저 제외해 보세요. 다음 시도의 정답·시간 초과 횟수를 확인하세요.',
    'rotation': '원본의 특징점이 목표에서 어디로 옮겨 가는지 먼저 확인해 보세요. 다음 시도에서 목표 도형을 맞힌 수와 조작 수를 확인하세요.',
    'path': '울타리를 놓기 전에 교통수단마다 이동 방향과 도착점을 그려 보세요. 다음 시도에서는 목표 도착과 성공한 문제의 울타리 수를 확인하세요.',
    'potion': '같은 재료 조합에서 나온 여러 결과를 비교한 뒤 색을 골라 보세요. 다음 본게임에서 적중 횟수와 가능성이 더 높은 색을 고른 비율을 각각 비교하세요.',
}


def selected_games(evidence):
    """The evidence list preserves attempt order. Each game uses its last completed main."""
    latest = {}
    for entry in evidence:
        kind = entry.get('game_type')
        if entry.get('source') != 'game' or kind not in GAME_NAMES:
            continue
        if kind in ('rsp', 'card'):
            completed = entry.get('status') == 'completed'
        elif kind in ('day', 'place', 'bus'):
            completed = entry.get('status') == 'complete'
        else:
            completed = entry.get('status') == 'complete' and entry.get('mode') == 'main'
        if completed:
            latest[kind] = entry
    return [latest[kind] for kind in GAME_NAMES if kind in latest]


def _potion_choice(data):
    count = data.get('choice_count', 0)
    favorable = data.get('favorable_choice_count', 0)
    return f'{favorable}/{count}회 ({favorable / count:.0%})' if count else '응답 없음'


def _describe(game):
    kind, totals = game['game_type'], game['totals']
    if kind in ('rsp', 'card'):
        phase = totals['by_rule_phase']
        before, after = phase['before'], phase['after']
        return f"규칙 변경 전 정답 {before['correct']}/{before['responses']}회 · 변경 후 정답 {after['correct']}/{after['responses']}회"
    if kind in ('day', 'place', 'bus'):
        return f"정답 {totals['correct']}회 · 오답 {totals['wrong']}회 · 시간 초과 {totals['timeout']}회 · {totals['score']}점"
    correct, answers = totals['correct_count'], totals['answered_count']
    timeouts = totals.get('timeout_count', 0)
    if kind == 'potion':
        metrics = totals['metrics']
        hits = f'{correct}/{answers}회 ({correct / answers:.0%})' if answers else '응답 없음'
        return (f"제조 결과 적중 {hits} · 예측 불일치 {totals['wrong_count']}회 · 시간 초과 {timeouts}회 · {totals['score']}점. "
                f"가능성이 더 높은 색 선택 {_potion_choice(metrics)} · 전반 {_potion_choice(metrics['early'])} · 후반 {_potion_choice(metrics['late'])}. "
                '가능성이 높은 색을 골라도 실제 제조 결과는 달라질 수 있습니다.')
    remaining = f" · 미제시 {totals['unasked_count']}회" if totals.get('unasked_count') else ''
    result = f"정답 {correct}회 · 오답 {totals['wrong_count']}회 · 시간 초과 {timeouts}회{remaining} · {totals['score']}점"
    metrics = totals.get('metrics', {})
    if kind == 'rotation' and 'used_operations' in metrics:
        return result + f" · 조작 {metrics['used_operations']}회"
    if kind == 'path' and correct and 'successful_fences' in metrics:
        return result + f" · 성공한 문제의 울타리 {metrics['successful_fences']}개 (최소 {metrics['successful_minimum_fences']}개)"
    return result


def observations(prompt):
    result = []
    for game in selected_games(prompt['evidence']):
        difficulty = game.get('difficulty') or game.get('conditions', {}).get('difficulty')
        label = GAME_NAMES[game['game_type']]
        if difficulty in ('easy', 'hard'):
            label += ' · ' + {'easy':'쉬움', 'hard':'어려움'}[difficulty]
        result.append({'evidence_id':game['id'], 'label':label, 'text':_describe(game)})
    return result


def has_success(game):
    totals = game['totals']
    if game['game_type'] == 'potion':
        return totals['metrics']['favorable_choice_count'] > 0
    return totals.get('correct_count', totals.get('correct', 0)) > 0


def has_difficulty(game):
    totals = game['totals']
    if game['game_type'] == 'potion':
        stats = totals['metrics']
        return (stats['favorable_choice_count'] < stats['choice_count'] or totals.get('timeout_count', 0) > 0)
    return any(totals.get(key, 0) > 0 for key in ('wrong_count', 'incorrect_count', 'wrong', 'timeout_count', 'timeout'))
