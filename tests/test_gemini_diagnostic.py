import io
import json
from urllib.error import HTTPError
from tools.diagnose_gemini import diagnose


def test_key_missing_never_issues_network_call():
    def fail(*a,**k): raise AssertionError('network called')
    assert diagnose('', opener=fail)==['KEY_MISSING']


def test_metadata_http_failure_does_not_generate_or_leak_response():
    def denied(*a,**k):
        raise HTTPError('https://example.invalid/key',403,'secret',None,io.BytesIO(b'secret'))
    result=diagnose('synthetic-secret',opener=denied)
    assert result==['MODEL_HTTP_403']
    assert 'secret' not in str(result)


def test_metadata_invalid_key_reports_safe_reason_only():
    body={'error':{'message':'private input','details':[{'reason':'API_KEY_INVALID','metadata':{'key':'secret'}}]}}
    def denied(*a,**k):
        raise HTTPError('https://example.invalid',400,'sensitive',None,io.BytesIO(json.dumps(body).encode()))
    assert diagnose('synthetic-secret',opener=denied,metadata_only=True)==['MODEL_HTTP_400','API_KEY_INVALID']


def test_metadata_only_never_sends_generation_request():
    class Response:
        status=200
        def __enter__(self): return self
        def __exit__(self,*args): return None
    class ForbiddenProvider:
        def __init__(self,**kwargs): raise AssertionError('generation attempted')
    assert diagnose('key',opener=lambda *a,**k:Response(),provider_class=ForbiddenProvider,metadata_only=True)==['MODEL_METADATA_OK']


def test_synthetic_generation_uses_only_fixture_and_safe_output(monkeypatch):
    import tools.diagnose_gemini as module
    class Response:
        status=200
        def __enter__(self): return self
        def __exit__(self,*args): return None
    class FakeProvider:
        def __init__(self,**kwargs): pass
        def generate(self,structured,**kwargs):
            assert structured['answer']['answer_id']=='synthetic-answer'
            assert 'synthetic-secret' not in str(structured)
            return {'criteria':[]}
    monkeypatch.setattr(module.analysis,'_server_criteria',lambda question,answer,result:None)
    assert diagnose('synthetic-secret',opener=lambda *a,**k:Response(),provider_class=FakeProvider)==['MODEL_METADATA_OK','SYNTHETIC_ANALYSIS_OK']


def test_diagnostic_uses_direct_current_model_and_reports_only_status(monkeypatch):
    import tools.diagnose_gemini as module
    class Response:
        status=200
        def __enter__(self): return self
        def __exit__(self,*args): return None
    class FakeProvider:
        def __init__(self,**kwargs): assert kwargs['model_id']=='gemini-3.6-flash'
        def generate(self,*args,**kwargs): raise module.ProviderError('gemini_http_503')
    assert diagnose('synthetic-secret',opener=lambda *a,**k:Response(),provider_class=FakeProvider)==['MODEL_METADATA_OK','gemini_http_503']


def test_diagnostic_distinguishes_output_limit_from_safety(monkeypatch):
    from tools.diagnose_gemini import DiagnosticProvider
    from app.ai_provider import GeminiProvider, ProviderError
    import pytest
    for reason, code in [('MAX_TOKENS','gemini_finish_max_tokens'),('SAFETY','gemini_finish_safety')]:
        monkeypatch.setattr(GeminiProvider, '_http_transport', lambda *a,**kw: {'candidates':[{'finishReason':reason}]})
        with pytest.raises(ProviderError, match=code):
            DiagnosticProvider._http_transport('endpoint',{},headers={},timeout_ms=1)


def test_diagnostic_payload_uses_low_thinking():
    from tools.diagnose_gemini import DiagnosticProvider
    payload=DiagnosticProvider.payload({},4096,{'type':'object'})
    assert payload['generationConfig']['thinkingConfig']['thinkingLevel']=='low'
    assert payload['generationConfig']['maxOutputTokens']==4096


def test_diagnostic_classifies_failed_citation_without_revealing_quote():
    from tools.diagnose_gemini import citation_failure_reason
    def result(quote): return {'criteria':[{'evidence_spans':[{'quote':quote,'start':0,'end':1}]}]}
    assert citation_failure_reason(result('not in source'),'source')=='CITATION_NOT_IN_SOURCE'
    assert citation_failure_reason(result('repeat'),'repeat repeat')=='CITATION_AMBIGUOUS'
    assert citation_failure_reason(result('source'),'source')=='CITATION_OFFSET_INVALID'
