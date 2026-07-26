import time

import pytest

from app.routes import events as events_module
from app import alerting as alerting_module
from app.config import settings
from .conftest import WritableFakeDB


@pytest.mark.asyncio
async def test_process_injection_signal_alerts_without_llm_when_unconfigured(monkeypatch):
    db = WritableFakeDB()
    monkeypatch.setattr(events_module, "get_db", lambda: db)
    monkeypatch.setattr(alerting_module, "get_db", lambda: db)
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "slack_webhook_url", "")  # no real HTTP

    doc = {"server_id": "s1", "ts": time.time(), "tool_name": "helper"}
    signal = {"subtypes": ["imperative_to_model"], "confidence_source": "keyword", "preview": "x"}

    await events_module._process_injection_signal("s1", doc, signal)

    alerts = db._collections["alerts"]._docs
    assert len(alerts) == 1
    assert alerts[0]["kind"] == "prompt_injection"


@pytest.mark.asyncio
async def test_process_injection_signal_escalates_and_persists_confirmation(monkeypatch):
    db = WritableFakeDB()
    await db["events"].insert_one({"server_id": "s1", "ts": 1.0, "tool_name": "helper"})
    monkeypatch.setattr(events_module, "get_db", lambda: db)
    monkeypatch.setattr(alerting_module, "get_db", lambda: db)
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key")
    monkeypatch.setattr(settings, "slack_webhook_url", "")

    async def fake_confirm(signal):
        return {"confirmed": True, "confidence": "high", "reasoning": "clearly imperative"}

    monkeypatch.setattr(events_module, "confirm_injection_intent", fake_confirm)

    doc = {"server_id": "s1", "ts": 1.0, "tool_name": "helper"}
    # Single-subtype signal -- should_escalate() is True for this.
    signal = {"subtypes": ["imperative_to_model"], "confidence_source": "keyword", "preview": "x"}

    await events_module._process_injection_signal("s1", doc, signal)

    stored = db._collections["events"]._docs[0]
    assert stored["prompt_injection"]["llm_confirmation"]["confirmed"] is True

    alerts = db._collections["alerts"]._docs
    assert "LLM review: confirmed" in alerts[0]["text"]


@pytest.mark.asyncio
async def test_process_injection_signal_does_not_escalate_strong_keyword_signal(monkeypatch):
    db = WritableFakeDB()
    monkeypatch.setattr(events_module, "get_db", lambda: db)
    monkeypatch.setattr(alerting_module, "get_db", lambda: db)
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key")
    monkeypatch.setattr(settings, "slack_webhook_url", "")

    called = False

    async def fake_confirm(signal):
        nonlocal called
        called = True
        return {"confirmed": True, "confidence": "high", "reasoning": "x"}

    monkeypatch.setattr(events_module, "confirm_injection_intent", fake_confirm)

    doc = {"server_id": "s1", "ts": 1.0, "tool_name": "helper"}
    # 2+ subtypes -- strong enough that should_escalate() is False.
    signal = {"subtypes": ["imperative_to_model", "role_authority_spoofing"], "confidence_source": "keyword", "preview": "x"}

    await events_module._process_injection_signal("s1", doc, signal)
    assert called is False
