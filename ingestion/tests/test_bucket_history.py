import time

import pytest

from app import anomaly
from .conftest import FakeDB


@pytest.mark.asyncio
async def test_bucket_history_returns_oldest_first_with_timestamps(monkeypatch):
    now = time.time()
    window_s = 60
    events = [
        {"server_id": "s1", "type": "rpc_call", "ts": now - window_s * 2 + 5, "latency_ms": 50},
        {"server_id": "s1", "type": "rpc_call", "ts": now - 5, "latency_ms": 200},
    ]
    monkeypatch.setattr(anomaly, "get_db", lambda: FakeDB(events))

    buckets = await anomaly.bucket_history("s1", window_minutes=1, n_buckets=3)

    assert len(buckets) == 3
    assert buckets[-1]["total_calls"] == 1  # most recent bucket has the recent event
    assert buckets[0]["bucket_start"] < buckets[-1]["bucket_start"]  # oldest first


@pytest.mark.asyncio
async def test_bucket_history_empty_when_no_events(monkeypatch):
    monkeypatch.setattr(anomaly, "get_db", lambda: FakeDB([]))
    buckets = await anomaly.bucket_history("s1", window_minutes=15, n_buckets=4)
    assert len(buckets) == 4
    assert all(b["total_calls"] == 0 for b in buckets)
