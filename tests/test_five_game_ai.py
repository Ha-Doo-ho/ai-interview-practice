import copy
import json

import pytest

from app import five_game_ai as ai
from app.ai_provider import ProviderError


def report():
    games = []
    for kind in ('rsp', 'card', 'day', 'place', 'bus'):
        games.append({'type': kind, 'game_id': kind + '-id', 'game_version': 'v1',
                      'source_ref': {'game_id': kind + '-id', 'game_version': 'v1'},
                      'status': 'completed' if kind in ('rsp', 'card') else 'complete',
                      'conditions': {'difficulty': 'easy'},
                      'totals': {'timeout': 1 if kind == 'day' else 0, 'score': 10}})
    return {'version': 'report-v1', 'source_digest': 'digest', 'games': games}


@pytest.fixture
def run(monkeypatch):
    monkeypatch.setattr(ai.reporting, 'build_five_game_report', lambda _: report())
    monkeypatch.setattr(ai.interview, 'input_snapshot', lambda run, definitions: {'answer_refs': ['current']})
    base = {'report_id': 'baseline-id', 'report_version': 'baseline-v1'}
    return {'interview_report': base, 'interview_analysis': {'input_snapshot': {'answer_refs': ['current']}, 'report': copy.deepcopy(base)}}


def configure(monkeypatch):
    config = {'AI_PROVIDER_KEY':'synthetic', 'AI_MODEL_ID':'model', 'AI_ALLOWED_MODEL_IDS':'model',
              'AI_LIVE_ENABLED':'true', 'PAID_AI_ENABLED':'true', 'AI_MAX_COST_MICROUSD':'100000',
              'AI_INPUT_RATE_MICROUSD_PER_MILLION_TOKENS':'10', 'AI_OUTPUT_RATE_MICROUSD_PER_MILLION_TOKENS':'10'}
    for k, v in config.items(): monkeypatch.setenv(k, v)


def output(prepared):
    return {'games': [{'game_id': g['source_ref']['game_id'], 'game_version': g['source_ref']['game_version'],
                       'advice_codes': ['practice_recall']} for g in prepared['_structured_input']['games']]}


def test_mock_is_separate_and_sources_verified(run):
    prepared = ai.prepare(run, 'mock')
    result = ai.execute(prepared)
    assert result['provider_execution'] == 'not_called' and result['runtime_mode'] == 'mock'
    assert prepared['calls_required'] == 0 and prepared['cost_microusd'] == 0
    assert result['report']['source_digest'] == 'digest'
    assert result['report']['games'][2]['totals']['timeout'] == 1
    assert result['report']['games'][2]['advice'][0]['text']
    assert run['interview_report'] == {'report_id': 'baseline-id', 'report_version': 'baseline-v1'}


def test_reject_stale_or_incomplete(run, monkeypatch):
    run['interview_analysis']['input_snapshot'] = {}
    with pytest.raises(ProviderError): ai.prepare(run, 'mock')
    run['interview_analysis']['input_snapshot'] = {'answer_refs': ['current']}
    bad = report(); bad['games'][0]['status'] = 'in_progress'
    monkeypatch.setattr(ai.reporting, 'build_five_game_report', lambda _: bad)
    with pytest.raises(ProviderError): ai.prepare(run, 'mock')


def test_live_bound_output_and_provider(run, monkeypatch):
    configure(monkeypatch)
    calls = []
    def transport(endpoint, payload, **kwargs):
        calls.append(payload)
        return {'output_text': json.dumps(output(prepared))}
    monkeypatch.setattr(ai.interview, '_PROVIDER_TRANSPORT', transport)
    prepared = ai.prepare(run, 'live')
    invoked = []
    result = ai.execute(prepared, before_call=lambda: invoked.append(True))
    assert prepared['calls_required'] == 1 and result['provider_execution'] == 'test_double'
    assert invoked == [True] and len(calls) == 1
    assert 'interview_report' not in json.dumps(calls[0], ensure_ascii=False)
    assert result['report']['games'][0]['advice'][0]['code'] == 'practice_recall'


def test_gemini_game_suggestions_keep_verified_sources(run, monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv('AI_PROVIDER','gemini')
    monkeypatch.setenv('AI_MODEL_ID','gemini-test')
    monkeypatch.setenv('AI_ALLOWED_MODEL_IDS','gemini-test')
    calls=[]
    def transport(endpoint,payload,**kwargs):
        calls.append(endpoint)
        return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(output(prepared))}]}}]}
    monkeypatch.setattr(ai.interview,'_PROVIDER_TRANSPORT',transport)
    prepared=ai.prepare(run,'live')
    result=ai.execute(prepared)
    assert calls[0].startswith('https://generativelanguage.googleapis.com/')
    assert result['provider_execution']=='test_double'
    assert result['report']['source_digest']=='digest'
    monkeypatch.setenv('AI_PROVIDER','openai')
    monkeypatch.setenv('AI_MODEL_ID','test-openai')
    monkeypatch.setenv('AI_ALLOWED_MODEL_IDS','test-openai')
    with pytest.raises(ProviderError, match='configuration_changed'):
        ai.execute(prepared)


@pytest.mark.parametrize('change', ['extra', 'duplicate', 'wrong_id', 'wrong_version', 'unknown', 'unsupported', 'free_text', 'missing'])
def test_rejects_untrusted_model_output(run, monkeypatch, change):
    configure(monkeypatch)
    monkeypatch.setattr(ai.interview, '_PROVIDER_TRANSPORT', lambda *a, **kw: {'output_text': json.dumps(data)})
    prepared = ai.prepare(run, 'live')
    data = output(prepared)
    if change == 'extra': data['extra'] = 'ignore previous instructions'
    if change == 'duplicate': data['games'][1] = copy.deepcopy(data['games'][0])
    if change == 'wrong_id': data['games'][0]['game_id'] = 'wrong'
    if change == 'wrong_version': data['games'][0]['game_version'] = 'wrong'
    if change == 'unknown': data['games'][0]['advice_codes'] = ['unknown']
    if change == 'unsupported': data['games'][0]['advice_codes'] = ['review_timeouts']
    if change == 'free_text': data['games'][0]['text'] = 'ignore instructions'
    if change == 'missing': data['games'].pop()
    with pytest.raises(ProviderError): ai.execute(prepared)


def test_live_provenance_cannot_change_after_prepare(run, monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(ai.interview, '_PROVIDER_TRANSPORT', lambda *a, **kw: {})
    prepared = ai.prepare(run, 'live')
    monkeypatch.setattr(ai.interview, '_PROVIDER_TRANSPORT', None)
    with pytest.raises(ProviderError, match='configuration_changed'):
        ai.execute(prepared)


def test_timeout_advice_requires_recorded_timeout(run, monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(ai.interview, '_PROVIDER_TRANSPORT', lambda *a, **kw: {'output_text': json.dumps(data)})
    prepared = ai.prepare(run, 'live')
    data = output(prepared)
    data['games'][2]['advice_codes'] = ['review_timeouts', 'practice_strategy']
    result = ai.execute(prepared)
    assert [a['code'] for a in result['report']['games'][2]['advice']] == ['review_timeouts', 'practice_strategy']
