"""Versioned project choices, independent of any official or clinical scores."""
from copy import deepcopy

VERSION = 'aptitude-games-v1'
DISCLAIMER = '이 결과는 자체 제작 게임의 수행 지표이며, 표준화된 심리검사 점수가 아닙니다.'
SCORING = {'correct_points': 10, 'incorrect_points': -5, 'score_floor': 0}
GAME_CONFIG = {
    'rotation': {'title': '도형 회전하기', 'ability': '공간지각 관련 과제 수행',
                 'question_count': 10, 'total_duration_ms': 240_000,
                 'question_duration_ms': None, 'max_operations': 20},
    'path': {'title': '길 만들기', 'ability': '계획 관련 과제 수행',
             'question_count': 10, 'total_duration_ms': 240_000,
             'question_duration_ms': None, 'max_operations': 19, 'board_size': 5},
    'potion': {'title': '마법약 만들기', 'ability': '확률 학습·작업기억 관련 과제 수행',
               'question_count': 100, 'quick_question_count': 20,
               'total_duration_ms': None, 'question_duration_ms': 15_000,
               'max_operations': None},
}


def config_for(game_type: str, mode: str) -> dict:
    config = {**deepcopy(GAME_CONFIG[game_type]), **SCORING, 'version': VERSION,
              'source': 'project_defined'}
    if mode == 'practice':
        config['question_count'] = 1
    elif mode == 'quick':
        config['question_count'] = config['quick_question_count']
    return config


def definitions() -> dict:
    return {'version': VERSION, 'disclaimer': DISCLAIMER,
            'scoring': deepcopy(SCORING), 'source': 'project_defined',
            'games': [{'type': kind, **deepcopy(config),
                       'modes': ['practice', 'main', 'quick'] if kind == 'potion' else ['practice', 'main'],
                       'difficulties': ['easy', 'hard']}
                      for kind, config in GAME_CONFIG.items()]}
