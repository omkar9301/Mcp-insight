import pytest

from app import injection_llm
from app.config import settings


def test_should_escalate_true_for_structural_only():
    assert injection_llm.should_escalate({"confidence_source": "structural", "subtypes": ["structural_anomaly"]}) is True


def test_should_escalate_true_for_single_keyword_hit():
    assert injection_llm.should_escalate({"confidence_source": "keyword", "subtypes": ["imperative_to_model"]}) is True


def test_should_escalate_false_for_two_plus_keyword_hits():
    assert injection_llm.should_escalate(
        {"confidence_source": "keyword", "subtypes": ["imperative_to_model", "role_authority_spoofing"]}
    ) is False


@pytest.mark.asyncio
async def test_confirm_injection_intent_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    result = await injection_llm.confirm_injection_intent({"subtypes": ["imperative_to_model"], "preview": "x"})
    assert result is None
