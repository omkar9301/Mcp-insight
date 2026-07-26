import time

import pytest

from app.routes import stats as stats_module
from app.config import settings
from .conftest import WritableFakeDB


@pytest.mark.asyncio
async def test_alerting_status_reports_unconfigured_when_no_webhook(monkeypatch):
    db = WritableFakeDB()
    monkeypatch.setattr(stats_module, "get_db", lambda: db)
    monkeypatch.setattr(settings, "slack_webhook_url", "")

    result = await stats_module.alerting_status()
    assert result["configured"] is False
    assert result["alerts_last_24h"] == 0
    assert result["last_alert_sent_at"] is None


@pytest.mark.asyncio
async def test_alerting_status_counts_recent_alerts(monkeypatch):
    db = WritableFakeDB()
    now = time.time()
    await db["alerts"].insert_one({"server_id": "s1", "kind": "health_score", "sent_at": now - 3600})
    await db["alerts"].insert_one({"server_id": "s1", "kind": "anomaly", "sent_at": now - 90000})  # >24h ago
    monkeypatch.setattr(stats_module, "get_db", lambda: db)
    monkeypatch.setattr(settings, "slack_webhook_url", "https://hooks.slack.com/x")

    result = await stats_module.alerting_status()
    assert result["configured"] is True
    assert result["alerts_last_24h"] == 1
    assert result["last_alert_sent_at"] == now - 3600


@pytest.mark.asyncio
async def test_low_confidence_count(monkeypatch):
    db = WritableFakeDB()
    now = time.time()
    await db["events"].insert_one({"ts": now, "classification": {"low_confidence": True}})
    await db["events"].insert_one({"ts": now, "classification": {"low_confidence": False}})
    await db["events"].insert_one({"ts": now})
    monkeypatch.setattr(stats_module, "get_db", lambda: db)

    result = await stats_module.low_confidence_count(window_minutes=1440)
    assert result["low_confidence_count"] == 1


@pytest.mark.asyncio
async def test_fleet_snapshot_records_and_retrieves(monkeypatch):
    db = WritableFakeDB()
    monkeypatch.setattr(stats_module, "get_db", lambda: db)

    req = stats_module.FleetSnapshotRequest(total_servers=5, active_servers=2, avg_score=80.0, total_calls=100)
    result = await stats_module.record_fleet_snapshot(req)
    assert result["recorded"] is True

    # The snapshot just recorded has ts=now, so it isn't "old enough" for
    # an hours_ago lookup yet -- backdate it to simulate time passing.
    db._collections["fleet_snapshots"]._docs[0]["ts"] = time.time() - 25 * 3600

    fetched = await stats_module.get_fleet_snapshot(hours_ago=24)
    assert fetched["snapshot"]["total_servers"] == 5
    assert fetched["snapshot"]["avg_score"] == 80.0


@pytest.mark.asyncio
async def test_fleet_snapshot_throttled_when_recent(monkeypatch):
    db = WritableFakeDB()
    monkeypatch.setattr(stats_module, "get_db", lambda: db)

    req = stats_module.FleetSnapshotRequest(total_servers=5, active_servers=2, avg_score=80.0, total_calls=100)
    await stats_module.record_fleet_snapshot(req)
    second = await stats_module.record_fleet_snapshot(req)
    assert second["recorded"] is False
    assert len(db._collections["fleet_snapshots"]._docs) == 1


@pytest.mark.asyncio
async def test_fleet_snapshot_returns_none_when_nothing_old_enough(monkeypatch):
    db = WritableFakeDB()
    monkeypatch.setattr(stats_module, "get_db", lambda: db)

    result = await stats_module.get_fleet_snapshot(hours_ago=24)
    assert result["snapshot"] is None
