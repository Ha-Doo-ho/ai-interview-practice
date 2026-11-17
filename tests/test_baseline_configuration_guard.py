import pytest
from app import interview_analysis as subject
from app.ai_provider import ProviderError
from app.content import DEFINITIONS
from test_live_interview_analysis import sample_run, _configure_live


@pytest.mark.parametrize('key', ['AI_INPUT_RATE_MICROUSD_PER_MILLION_TOKENS','AI_OUTPUT_RATE_MICROUSD_PER_MILLION_TOKENS'])
def test_changed_price_after_reservation_is_rejected_before_transport(monkeypatch, key):
    _configure_live(monkeypatch)
    calls=[]
    monkeypatch.setattr(subject, '_PROVIDER_TRANSPORT', lambda *a, **kw: calls.append(1))
    prepared=subject.prepare_analysis(sample_run(), DEFINITIONS, 'live')
    monkeypatch.setenv(key, '9999999')
    with pytest.raises(ProviderError, match='configuration_changed'):
        subject.execute_analysis(prepared)
    assert calls==[]
