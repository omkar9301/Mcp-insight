import time

import pytest

from app import alerting
from app.config import settings
from .conftest import WritableFakeDB


@pytest.mark.asyncio
async def test_health_alert_recorded_and_sent(monkeypatch):
    db = WritableFakeDB()
    monkeypatch.setattr(alerting, "get_db", lambda: db)
    monkeypatch.setattr(settings, "alert_score_threshold", 60)
    monkeypatch.setattr(settings, "slack_webhook_url", "")  # skip real HTTP

    await alerting.maybe_alert_health("srv-1", {"score": 40, "status": "unhealthy", "breakdown": {"x": 1}})

    alerts = db._collections["alerts"]._docs
    assert len(alerts) == 1
    assert alerts[0]["kind"] == "health_score"


@pytest.mark.asyncio
async def test_health_alert_skipped_when_score_ok(monkeypatch):
    db = WritableFakeDB()
    monkeypatch.setattr(alerting, "get_db", lambda: db)
    monkeypatch.setattr(settings, "alert_score_threshold", 60)

    await alerting.maybe_alert_health("srv-1", {"score": 90, "status": "healthy", "breakdown": {}})
    assert db._collections.get("alerts") is None or db._collections["alerts"]._docs == []


@pytest.mark.asyncio
async def test_health_alert_skipped_when_muted(monkeypatch):
    db = WritableFakeDB()
    monkeypatch.setattr(alerting, "get_db", lambda: db)
    monkeypatch.setattr(settings, "alert_score_threshold", 60)
    await db["servers"].update_one(
        {"server_id": "srv-1"}, {"$set": {"alerts_muted_until": time.time() + 3600}}, upsert=True
    )

    await alerting.maybe_alert_health("srv-1", {"score": 10, "status": "critical", "breakdown": {}})
    assert db._collections.get("alerts") is None or db._collections["alerts"]._docs == []


@pytest.mark.asyncio
async def test_health_alert_respects_cooldown(monkeypatch):
    db = WritableFakeDB()
    monkeypatch.setattr(alerting, "get_db", lambda: db)
    monkeypatch.setattr(settings, "alert_score_threshold", 60)
    monkeypatch.setattr(settings, "alert_cooldown_s", 900)

    await alerting.maybe_alert_health("srv-1", {"score": 40, "status": "unhealthy", "breakdown": {}})
    await alerting.maybe_alert_health("srv-1", {"score": 30, "status": "critical", "breakdown": {}})

    assert len(db._collections["alerts"]._docs) == 1  # second call suppressed by cooldown


@pytest.mark.asyncio
async def test_anomaly_alert_skipped_when_no_anomalies(monkeypatch):
    db = WritableFakeDB()
    monkeypatch.setattr(alerting, "get_db", lambda: db)

    await alerting.maybe_alert_anomalies("srv-1", {"anomalies": []})
    assert db._collections.get("alerts") is None or db._collections["alerts"]._docs == []
