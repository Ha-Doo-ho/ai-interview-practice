"""Separate bounded practice suggestions based only on verified game facts."""
from __future__ import annotations

import copy
import json
from uuid import uuid4

from . import five_game_reporting as reporting
from . import interview_analysis as interview
from .ai_provider import BudgetLimits, LiveProvider, GeminiProvider, ProviderError
from .content import DEFINITIONS

VERSION = 'five-game-practice-v1'
SCHEMA_VERSION = 'five-game-practice-schema-v1'
ADVICE = {
    'practice_recall': '다음 연습에서 제시된 정보를 차례로 떠올려 보세요.',
    'practice_strategy': '다음 연습에서 정보를 확인하는 순서를 정해 보세요.',
    'review_timeouts': '시간 초과가 기록된 문항의 조건을 살펴보고 다음 연습을 준비해 보세요.',
}
KINDS = ('rsp', 'card', 'day', 'place', 'bus')


def _error(code):
    return ProviderError(code)


def _schema():
    entry = {'type': 'object', 'properties': {
        'game_id': {'type': 'string'}, 'game_version': {'type': 'string'},
        'advice_codes': {'type': 'array', 'items': {'type': 'string', 'enum': list(ADVICE)}, 'minItems': 1, 'maxItems': 2}},
        'required': ['game_id', 'game_version', 'advice_codes'], 'additionalProperties': False}
    return {'type': 'object', 'properties': {'games': {'type': 'array', 'items': entry, 'minItems': 5, 'maxItems': 5}},
            'required': ['games'], 'additionalProperties': False}


def prepare(run, mode):
    if mode not in ('mock', 'live'):
        raise _error('mode_invalid')
    if not isinstance(run, dict):
        raise _error('baseline_report_required')
    analysis, baseline = run.get('interview_analysis'), run.get('interview_report')
    if not isinstance(analysis, dict) or not isinstance(baseline, dict) or baseline != analysis.get('report'):
        raise _error('baseline_report_required')
    if not baseline.get('report_id') or not baseline.get('report_version'):
        raise _error('baseline_report_required')
    if analysis.get('input_snapshot') != interview.input_snapshot(run, DEFINITIONS):
        raise _error('interview_report_stale')
    source = reporting.build_five_game_report(run)
    games = source.get('games')
    if not isinstance(games, list) or len(games) != 5 or [g.get('type') for g in games] != list(KINDS):
        raise _error('game_completion_required')
    if any(g.get('status') != ('completed' if g['type'] in ('rsp', 'card') else 'complete') for g in games):
        raise _error('game_completion_required')
    refs = [g.get('source_ref') for g in games]
    if any(not isinstance(r, dict) or not isinstance(r.get('game_id'), str) or not r['game_id'] or not isinstance(r.get('game_version'), str) or not r['game_version'] for r in refs):
        raise _error('five_game_report_invalid')
    if len({r['game_id'] for r in refs}) != 5:
        raise _error('five_game_report_invalid')
    structured = {'schema_version': SCHEMA_VERSION, 'games': [
        {k: copy.deepcopy(g[k]) for k in ('type', 'source_ref', 'status', 'conditions', 'totals')}
        for g in games], 'allowed_advice_codes': list(ADVICE)}
    input_ref = {'source_digest': source['source_digest'], 'report_id': 'five-game-report:' + source['source_digest'],
                 'report_version': source['version'], 'baseline_report_id': baseline['report_id'],
                 'baseline_report_version': baseline['report_version']}
    result = {'requested_mode': mode, 'runtime_mode': 'mock', 'provider_execution': 'not_called', 'model_id': None,
              'input_snapshot': input_ref, 'calls_required': 0, 'cost_microusd': 0,
              'max_calls_per_run': 0, 'max_cost_microusd': 0, 'max_input_tokens': 0,
              'max_output_tokens': 0, 'timeout_ms': 0, 'max_retries': 0,
              '_structured_input': structured, '_input_tokens': 0}
    if mode == 'mock':
        return result
    config = interview._live_config()
    bound = {'model': config['model_id'], 'store': False, 'tools': [], 'max_output_tokens': config['max_output_tokens'],
             'instructions': LiveProvider.instructions,
             'input': [{'role': 'user', 'content': [{'type': 'input_text', 'text': json.dumps(structured, ensure_ascii=False)}]}],
             'text': {'format': {'type': 'json_schema', 'name': 'interview_analysis', 'strict': True, 'schema': _schema()}}}
    tokens = interview._conservative_tokens(bound)
    if config['provider'] == 'gemini':
        tokens = max(tokens, interview._conservative_tokens(GeminiProvider.payload(structured, config['max_output_tokens'], _schema(), model_id=config['model_id'])))
    cost = interview._cost_microusd(tokens, config['max_output_tokens'], config['input_rate'], config['output_rate'])
    if tokens > config['max_input_tokens'] or cost > config['max_cost_microusd'] or config['max_calls_per_run'] < 1:
        raise _error('budget_exceeded')
    result.update(runtime_mode='mock' if interview._PROVIDER_TRANSPORT is not None else 'live',
                  provider_execution='test_double' if interview._PROVIDER_TRANSPORT is not None else 'provider_completed',
                  model_id=config['model_id'], calls_required=1, cost_microusd=cost, _provider=config['provider'],
                  max_calls_per_run=config['max_calls_per_run'], max_cost_microusd=config['max_cost_microusd'],
                  max_input_tokens=config['max_input_tokens'], max_output_tokens=config['max_output_tokens'],
                  timeout_ms=config['timeout_ms'], max_retries=0, _input_tokens=tokens,
                  _input_rate=config['input_rate'], _output_rate=config['output_rate'])
    return result


def _validate_output(output, games):
    if not isinstance(output, dict) or set(output) != {'games'} or not isinstance(output['games'], list) or len(output['games']) != 5:
        raise _error('provider_schema_invalid')
    source = {g['source_ref']['game_id']: g for g in games}
    seen, by_id = set(), {}
    for item in output['games']:
        if not isinstance(item, dict) or set(item) != {'game_id', 'game_version', 'advice_codes'}:
            raise _error('provider_schema_invalid')
        gid, version, codes = item['game_id'], item['game_version'], item['advice_codes']
        if not isinstance(gid, str) or gid not in source or gid in seen or version != source[gid]['source_ref']['game_version']:
            raise _error('provider_schema_invalid')
        if not isinstance(codes, list) or not 1 <= len(codes) <= 2 or any(not isinstance(c, str) or c not in ADVICE for c in codes) or len(set(codes)) != len(codes):
            raise _error('provider_schema_invalid')
        if 'review_timeouts' in codes and not (type(source[gid]['totals'].get('timeout')) is int and source[gid]['totals']['timeout'] > 0):
            raise _error('provider_schema_invalid')
        seen.add(gid)
        by_id[gid] = codes
    return by_id


def execute(prepared, *, before_call=None):
    if not isinstance(prepared, dict) or prepared.get('requested_mode') not in ('mock', 'live'):
        raise _error('prepared_invalid')
    games = prepared['_structured_input']['games']
    if prepared['requested_mode'] == 'mock':
        output = {'games': [{'game_id': g['source_ref']['game_id'], 'game_version': g['source_ref']['game_version'],
                             'advice_codes': ['practice_recall']} for g in games]}
    else:
        current = interview._live_config()
        guarded = ('model_id', 'max_input_tokens', 'max_output_tokens', 'timeout_ms', 'max_retries', 'max_calls_per_run', 'max_cost_microusd')
        if (any(current[k] != prepared[k] for k in guarded)
                or current['provider'] != prepared.get('_provider', 'openai')
                or current['input_rate'] != prepared['_input_rate'] or current['output_rate'] != prepared['_output_rate']
                or (interview._PROVIDER_TRANSPORT is not None) != (prepared['provider_execution'] == 'test_double')):
            raise _error('configuration_changed')
        provider_class = GeminiProvider if current['provider'] == 'gemini' else LiveProvider
        provider = provider_class(transport=interview._PROVIDER_TRANSPORT,
            limits=BudgetLimits(max_input_tokens=prepared['max_input_tokens'], max_output_tokens=prepared['max_output_tokens'],
                max_timeout_ms=prepared['timeout_ms'], max_retries=0, max_calls_per_run=prepared['max_calls_per_run']), model_id=prepared['model_id'])
        if before_call is not None:
            before_call()
        output = provider.generate(prepared['_structured_input'], input_tokens=prepared['_input_tokens'],
            output_tokens=prepared['max_output_tokens'], timeout_ms=prepared['timeout_ms'], retries=0,
            calls_per_run=1, estimated_cost=prepared['cost_microusd']/1_000_000, output_schema=_schema())
    codes = _validate_output(output, games)
    ref = prepared['input_snapshot']
    report = {'report_id': str(uuid4()), 'report_version': VERSION, 'source_digest': ref['source_digest'],
              'source_report_id': ref['report_id'], 'source_report_version': ref['report_version'],
              'baseline_report_id': ref['baseline_report_id'], 'baseline_report_version': ref['baseline_report_version'],
              'games': [], 'limitations': ['게임 기록을 바탕으로 한 연습 제안이며 채용이나 성격 판단이 아닙니다.']}
    for g in games:
        report['games'].append({**{k: copy.deepcopy(g[k]) for k in ('type', 'source_ref', 'conditions', 'totals')},
            'advice': [{'code': c, 'text': ADVICE[c]} for c in codes[g['source_ref']['game_id']]]})
    return {**{k: copy.deepcopy(prepared[k]) for k in ('runtime_mode', 'requested_mode', 'provider_execution', 'model_id', 'input_snapshot')}, 'report': report}
