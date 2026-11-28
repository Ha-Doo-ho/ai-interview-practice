import json
import io
import pytest
from urllib.error import HTTPError
from app.ai_provider import ProviderError


def config(monkeypatch):
    for key, value in {'AI_LIVE_ENABLED':'true','PAID_AI_ENABLED':'true','AI_PROVIDER_KEY':'fake-secret',
                       'AI_MODEL_ID':'gemini-test','AI_ALLOWED_MODEL_IDS':'gemini-test',
                       'AI_MAX_COST_MICROUSD':'1000000'}.items():
        monkeypatch.setenv(key, value)


def test_synthesis_routes_gemini_model_when_provider_is_omitted(monkeypatch):
    from app import synthesis

    config(monkeypatch)
    monkeypatch.delenv('AI_PROVIDER', raising=False)
    monkeypatch.setenv('AI_INPUT_RATE_MICROUSD_PER_MILLION_TOKENS', '1')
    monkeypatch.setenv('AI_OUTPUT_RATE_MICROUSD_PER_MILLION_TOKENS', '1')
    called=[]

    def transport(endpoint,payload,**kwargs):
        called.append(endpoint)
        return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps({k:[] for k in synthesis.SECTIONS})}]}}]}

    monkeypatch.setattr('app.interview_analysis._PROVIDER_TRANSPORT',transport)
    synthesis.execute(synthesis.prepare({'questions':[],'records':[]},'live'))
    assert called==['https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent']

    monkeypatch.setenv('AI_PROVIDER','openai')
    with pytest.raises(ProviderError,match='provider_model_mismatch'):
        synthesis.prepare({'questions':[],'records':[]},'live')
    assert len(called)==1


def test_gemini_sends_schema_and_key_in_header_and_parses_json(monkeypatch):
    from app.ai_provider import GeminiProvider
    config(monkeypatch)
    calls = []
    def transport(endpoint, payload, **kwargs):
        calls.append((endpoint, payload, kwargs))
        return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"answer":1}'}]}}]}
    provider = GeminiProvider(transport=transport, model_id='gemini-test')
    schema={'type':'object','properties':{'answer':{'type':'integer'}},'required':['answer']}
    assert provider.generate({'text':'sample'},input_tokens=100,output_tokens=50,estimated_cost=0.01,output_schema=schema)=={'answer':1}
    endpoint,payload,options=calls[0]
    assert endpoint=='https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent'
    assert options['headers']['x-goog-api-key']=='fake-secret' and 'fake-secret' not in endpoint
    assert payload['store'] is False
    assert payload['generationConfig']['responseFormat']['text']['schema']==schema
    assert json.loads(payload['contents'][0]['parts'][0]['text'])=={'text':'sample'}


def test_gemini_payload_omits_unsupported_string_length_but_preserves_properties():
    from app.ai_provider import GeminiProvider
    from app.interview_analysis import _output_schema
    source=_output_schema()
    payload=GeminiProvider.payload({'sample':'text'},100,source)
    schema=payload['generationConfig']['responseFormat']['text']['schema']
    quote=schema['properties']['criteria']['items']['properties']['evidence_spans']['items']['properties']['quote']
    assert quote=={'type':'string'}
    assert source['properties']['criteria']['items']['properties']['evidence_spans']['items']['properties']['quote']['maxLength']==400


def test_thinking_level_is_enabled_only_for_gemini_three_models():
    from app.ai_provider import GeminiProvider
    v3=GeminiProvider.payload({},4096,{'type':'object'},model_id='gemini-3.6-flash')
    v25=GeminiProvider.payload({},4096,{'type':'object'},model_id='gemini-2.5-flash')
    assert v3['generationConfig']['thinkingConfig']['thinkingLevel']=='low'
    assert 'thinkingConfig' not in v25['generationConfig']


@pytest.mark.parametrize('reply', [{}, {'candidates':[{'finishReason':'MAX_TOKENS','content':{'parts':[{'text':'{}'}]}}]},
                                   {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'not json'}]}}]}])
def test_gemini_rejects_incomplete_or_invalid_results(monkeypatch, reply):
    from app.ai_provider import GeminiProvider
    config(monkeypatch)
    with pytest.raises(ProviderError):
        GeminiProvider(transport=lambda *a,**k:reply,model_id='gemini-test').generate({},input_tokens=1,output_tokens=1,estimated_cost=0)


def test_gemini_refuses_unsafe_model_and_disabled_live_before_transport(monkeypatch):
    from app.ai_provider import GeminiProvider
    config(monkeypatch)
    calls=[]
    monkeypatch.setenv('AI_MODEL_ID','../evil');monkeypatch.setenv('AI_ALLOWED_MODEL_IDS','../evil')
    with pytest.raises(ProviderError):
        GeminiProvider(transport=lambda *a,**k:calls.append(1),model_id='../evil').generate({},input_tokens=1,output_tokens=1,estimated_cost=0)
    monkeypatch.setenv('AI_LIVE_ENABLED','false')
    with pytest.raises(ProviderError):
        GeminiProvider(transport=lambda *a,**k:calls.append(1),model_id='gemini-test').generate({},input_tokens=1,output_tokens=1,estimated_cost=0)
    assert calls==[]


def test_gemini_ignores_non_answer_thought_parts(monkeypatch):
    from app.ai_provider import GeminiProvider
    config(monkeypatch)
    response={'candidates':[{'finishReason':'STOP','content':{'parts':[{'thought':True,'text':'private thought'}, {'text':'{"answer":1}'}]}}]}
    assert GeminiProvider(transport=lambda *a,**kw:response,model_id='gemini-test').generate({},input_tokens=1,output_tokens=1,estimated_cost=0)=={'answer':1}


@pytest.mark.parametrize('status,code', [(400,'gemini_request_invalid'),(401,'gemini_auth_failed'),(403,'gemini_access_denied'),(404,'gemini_model_unavailable'),(429,'gemini_quota_exceeded'),(503,'gemini_http_503')])
def test_gemini_http_failures_have_safe_actionable_codes(monkeypatch,status,code):
    from app.ai_provider import GeminiProvider
    config(monkeypatch)
    def transport(*args,**kwargs):
        raise HTTPError('https://example.invalid/secret',status,'sensitive details',None,None)
    with pytest.raises(ProviderError) as failure:
        GeminiProvider(transport=transport,model_id='gemini-test').generate({},input_tokens=1,output_tokens=1,estimated_cost=0)
    assert str(failure.value)==code
    assert failure.value.__cause__ is None


def test_gemini_http_400_identifies_invalid_key_without_exposing_response(monkeypatch):
    from app.ai_provider import GeminiProvider
    config(monkeypatch)
    body={'error':{'message':'private user text','details':[{'reason':'API_KEY_INVALID','metadata':{'key':'secret'}}]}}
    def transport(*args,**kwargs):
        raise HTTPError('https://example.invalid',400,'error',None,io.BytesIO(json.dumps(body).encode()))
    with pytest.raises(ProviderError) as failure:
        GeminiProvider(transport=transport,model_id='gemini-test').generate({},input_tokens=1,output_tokens=1,estimated_cost=0)
    assert str(failure.value)=='gemini_auth_failed'


def test_gemini_interview_pipeline_validates_actual_answer_and_guard(monkeypatch):
    from app import interview_analysis as analysis
    from app.content import DEFINITIONS
    from test_live_interview_analysis import sample_run, _configure_live, _model_result
    _configure_live(monkeypatch)
    monkeypatch.setenv('AI_PROVIDER', 'gemini')
    monkeypatch.setenv('AI_MODEL_ID', 'gemini-test')
    monkeypatch.setenv('AI_ALLOWED_MODEL_IDS', 'gemini-test')
    run=sample_run(); answer=run['records'][-1]['data']; calls=[]
    def transport(url, payload, **kwargs):
        calls.append(url)
        result=_model_result(answer['text'],run['questions'][0])
        return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(result)}]}}]}
    monkeypatch.setattr(analysis,'_PROVIDER_TRANSPORT',transport)
    prepared=analysis.prepare_analysis(run, DEFINITIONS, 'live')
    output=analysis.execute_analysis(prepared)
    assert calls[0].startswith('https://generativelanguage.googleapis.com/')
    assert output['provider_execution']=='test_double'
    monkeypatch.setenv('AI_PROVIDER','openai')
    with pytest.raises(ProviderError,match='provider_model_mismatch'):
        analysis.execute_analysis(prepared)
    monkeypatch.setenv('AI_MODEL_ID','test-openai')
    monkeypatch.setenv('AI_ALLOWED_MODEL_IDS','test-openai')
    with pytest.raises(ProviderError,match='configuration_changed'):
        analysis.execute_analysis(prepared)
    assert len(calls)==1


def test_gemini_quote_offset_repair_requires_exact_unique_source():
    from app.interview_analysis import _resolve_gemini_quote_offsets
    from copy import deepcopy
    item={'criteria':[{'criterion':'action','status':'explicit','evidence_spans':[{'start':0,'end':2,'quote':'팀원에게'}]}]}
    original=deepcopy(item)
    corrected=_resolve_gemini_quote_offsets(item,'🙂 저는 팀원에게 물었습니다.')
    assert corrected['criteria'][0]['evidence_spans'][0]=={'start':5,'end':9,'quote':'팀원에게'}
    assert item==original
    for text in ('없는 답변', '팀원에게 말하고 팀원에게 물었다'):
        assert _resolve_gemini_quote_offsets(item,text)==original


def test_gemini_pipeline_repairs_unique_offset_but_rejects_invented_quote(monkeypatch):
    from app import interview_analysis as analysis
    from app.content import DEFINITIONS
    from test_live_interview_analysis import sample_run, _configure_live, _model_result
    _configure_live(monkeypatch)
    monkeypatch.setenv('AI_PROVIDER','gemini')
    monkeypatch.setenv('AI_MODEL_ID','gemini-test')
    monkeypatch.setenv('AI_ALLOWED_MODEL_IDS','gemini-test')
    run=sample_run();answer=run['records'][-1]['data']; invented=[False]
    def transport(*args,**kwargs):
        result=_model_result(answer['text'],run['questions'][0])
        span=result['criteria'][3]['evidence_spans'][0]
        span['start']=0;span['end']=1
        if invented[0]: span['quote']='없는 문장'
        return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(result)}]}}]}
    monkeypatch.setattr(analysis,'_PROVIDER_TRANSPORT',transport)
    report=analysis.execute_analysis(analysis.prepare_analysis(run,DEFINITIONS,'live'))['report']
    span=report['cards'][0]['criteria']['action']['evidence_spans'][0]
    assert answer['text'][span['start']:span['end']]==span['quote']
    invented[0]=True
    with pytest.raises(ProviderError,match='citation_invalid'):
        analysis.execute_analysis(analysis.prepare_analysis(run,DEFINITIONS,'live'))
