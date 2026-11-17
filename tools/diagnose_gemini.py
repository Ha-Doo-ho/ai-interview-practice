"""One synthetic diagnostic; prints only fixed status messages, never secrets or answers."""
from __future__ import annotations

import os
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import interview_analysis as analysis
from app.ai_provider import BudgetLimits, GeminiProvider, ProviderError
from app.content import DEFINITIONS


class DiagnosticProvider(GeminiProvider):
    @classmethod
    def payload(cls, structured_input, output_tokens, output_schema, *, model_id=None):
        result=super().payload(structured_input, output_tokens, output_schema, model_id=model_id)
        result['generationConfig']['thinkingConfig']={'thinkingLevel':'low'}
        return result

    @staticmethod
    def _http_transport(endpoint, payload, *, headers, timeout_ms):
        try:
            result=GeminiProvider._http_transport(endpoint, payload, headers=headers, timeout_ms=timeout_ms)
            if isinstance(result, dict):
                candidates=result.get('candidates')
                if isinstance(candidates, list) and len(candidates)==1 and isinstance(candidates[0], dict):
                    reason=candidates[0].get('finishReason')
                    if reason in ('MAX_TOKENS','SAFETY'):
                        raise ProviderError('gemini_finish_' + reason.lower())
            return result
        except HTTPError as exc:
            code = exc.code if isinstance(exc.code, int) and 400 <= exc.code <= 599 else 0
            raise ProviderError('gemini_http_' + str(code)) from None


def citation_failure_reason(output, source):
    if not isinstance(output, dict) or not isinstance(output.get('criteria'), list):
        return 'CITATION_UNCLASSIFIED'
    seen_ambiguous = False
    for item in output['criteria']:
        if not isinstance(item, dict) or not isinstance(item.get('evidence_spans'), list):
            continue
        for span in item['evidence_spans']:
            if not isinstance(span, dict) or not isinstance(span.get('quote'), str) or not span['quote']:
                continue
            quote=span['quote']; start=span.get('start'); end=span.get('end')
            if type(start) is int and type(end) is int and 0<=start<end<=len(source) and source[start:end]==quote:
                continue
            first=source.find(quote)
            if first<0:
                return 'CITATION_NOT_IN_SOURCE'
            if source.find(quote,first+1)>=0:
                seen_ambiguous=True
    return 'CITATION_AMBIGUOUS' if seen_ambiguous else 'CITATION_OFFSET_INVALID'


def diagnose(key, *, opener=urlopen, provider_class=DiagnosticProvider, metadata_only=False):
    if not key:
        return ['KEY_MISSING']
    model = 'gemini-3.6-flash'
    # Test the current model directly, rather than the deprecated 3.5 alias.
    req = Request('https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash',
                  headers={'x-goog-api-key': key}, method='GET')
    try:
        with opener(req, timeout=15) as response:
            if response.status != 200:
                return ['MODEL_HTTP_ERROR']
    except HTTPError as exc:
        result=['MODEL_HTTP_' + str(exc.code)]
        try:
            body=json.loads(exc.read(65536))
            details=body.get('error', {}).get('details', [])
            reasons={item.get('reason') for item in details if isinstance(item, dict)}
            for reason in ('API_KEY_INVALID','API_KEY_SERVICE_BLOCKED','SERVICE_DISABLED','API_KEY_EXPIRED'):
                if reason in reasons:
                    result.append(reason)
        except (ValueError, TypeError, AttributeError, OSError):
            pass
        return result
    except (URLError, OSError):
        return ['MODEL_NETWORK_ERROR']
    status = ['MODEL_METADATA_OK']
    if metadata_only:
        return status
    question = DEFINITIONS['questions'][0]
    answer = {'answer_id':'synthetic-answer', 'answer_version':'1.0.0', 'status':'asked_answered',
              'text':'회의 전에 팀원에게 일정을 물어보고 계획에 반영했습니다.'}
    mapping, error = analysis._interview_mapping(DEFINITIONS, question, use='baseline_extraction')
    if error:
        return status + ['LOCAL_MAPPING_ERROR']
    structured = analysis._model_input(question, answer, DEFINITIONS, mapping)
    schema = analysis._output_schema()
    tokens = analysis._conservative_tokens(DiagnosticProvider.payload(structured, 4096, schema))
    try:
        provider = provider_class(model_id=model, limits=BudgetLimits(max_input_tokens=12000,
            max_output_tokens=4096, max_timeout_ms=30000, max_retries=0, max_calls_per_run=1))
        result = provider.generate(structured, input_tokens=tokens, output_tokens=4096,
            timeout_ms=30000, retries=0, calls_per_run=1, estimated_cost=0.05, output_schema=schema)
        result = analysis._resolve_gemini_quote_offsets(result, answer['text'])
        analysis._server_criteria(question, answer, result)
        return status + ['SYNTHETIC_ANALYSIS_OK']
    except ProviderError as exc:
        permitted = {'gemini_request_invalid','gemini_auth_failed','gemini_access_denied',
            'gemini_model_unavailable','gemini_quota_exceeded','gemini_service_unavailable',
            'provider_schema_invalid','provider_incomplete','provider_failed','citation_invalid',
            'budget_exceeded','live_disabled','paid_ai_not_approved','live_not_configured',
            'model_not_allowed','cost_budget_unknown','gemini_finish_max_tokens','gemini_finish_safety'}
        code = str(exc).split(':',1)[0]
        if code == 'citation_invalid':
            return status + [code, citation_failure_reason(result, answer['text'])]
        return status + [code if code in permitted or code in {f'gemini_http_{i}' for i in range(400,600)} else 'OTHER_FAILURE']
    except Exception:
        return status + ['OTHER_FAILURE']


if __name__ == '__main__':
    for item in diagnose(os.getenv('AI_PROVIDER_KEY', ''), metadata_only='--metadata-only' in sys.argv[1:]):
        print(item)
