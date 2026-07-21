import time

import pytest

from app import anomaly
from app.config import settings
from .conftest import FakeDB


def _events(server_id, ts_list, is_error=False, latency_ms=100):
    return [
        {"server_id": server_id, "type": "rpc_call", "ts": ts, "is_error": is_error, "latency_ms": latency_ms}
        for ts in ts_list
    ]


@pytest.mark.asyncio
async def test_detects_error_rate_spike(monkeypatch):
    monkeypatch.setattr(settings, "anomaly_min_history_buckets", 3)
    monkeypatch.setattr(settings, "anomaly_history_buckets", 5)
    now = time.time()
    window_s = 15 * 60

    events = []
    # 5 quiet history buckets (0% errors), then a spiking current bucket
    for bucket in range(1, 6):
        ts_base = now - bucket * window_s + 10
        events += _events("s1", [ts_base + i for i in range(10)], is_error=False)
    events += _events("s1", [now - 5 + i for i in range(10)], is_error=True)

    monkeypatch.setattr(anomaly, "get_db", lambda: FakeDB(events))

    report = await anomaly.detect_anomalies("s1", window_minutes=15)
    kinds = [a["kind"] for a in report["anomalies"]]
    assert "error_rate_spike" in kinds


@pytest.mark.asyncio
async def test_detects_latency_spike(monkeypatch):
    monkeypatch.setattr(settings, "anomaly_min_history_buckets", 3)
    monkeypatch.setattr(settings, "anomaly_history_buckets", 5)
    now = time.time()
    window_s = 15 * 60

    events = []
    for bucket in range(1, 6):
        ts_base = now - bucket * window_s + 10
        events += _events("s1", [ts_base + i for i in range(10)], latency_ms=100)
    events += _events("s1", [now - 5 + i for i in range(10)], latency_ms=5000)

    monkeypatch.setattr(anomaly, "get_db", lambda: FakeDB(events))

    report = await anomaly.detect_anomalies("s1", window_minutes=15)
    kinds = [a["kind"] for a in report["anomalies"]]
    assert "latency_spike" in kinds


@pytest.mark.asyncio
async def test_no_anomalies_when_stable(monkeypatch):
    monkeypatch.setattr(settings, "anomaly_min_history_buckets", 3)
    monkeypatch.setattr(settings, "anomaly_history_buckets", 5)
    now = time.time()
    window_s = 15 * 60

    events = []
    for bucket in range(1, 7):
        ts_base = now - bucket * window_s + 10
        events += _events("s1", [ts_base + i for i in range(10)], latency_ms=100, is_error=False)

    monkeypatch.setattr(anomaly, "get_db", lambda: FakeDB(events))

    report = await anomaly.detect_anomalies("s1", window_minutes=15)
    assert report["anomalies"] == []


@pytest.mark.asyncio
async def test_insufficient_history_skips_detection(monkeypatch):
    monkeypatch.setattr(settings, "anomaly_min_history_buckets", 5)
    monkeypatch.setattr(settings, "anomaly_history_buckets", 5)
    now = time.time()
    events = _events("s1", [now - i for i in range(10)], is_error=True)

    monkeypatch.setattr(anomaly, "get_db", lambda: FakeDB(events))

    report = await anomaly.detect_anomalies("s1", window_minutes=15)
    assert report["anomalies"] == []
