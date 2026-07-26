import time

import pytest

from app.routes import stats as stats_module
from .conftest import WritableFakeDB


def _classified_event(server_id, category, subcategory, severity, ts=None):
    return {
        "server_id": server_id,
        "type": "rpc_call",
        "ts": ts or time.time(),
        "is_error": False,
        "classification": {"category": category, "subcategory": subcategory, "dominant_severity": severity},
    }


@pytest.mark.asyncio
async def test_category_counts_groups_and_sorts_descending(monkeypatch):
    db = WritableFakeDB()
    for _ in range(3):
        await db["events"].insert_one(_classified_event("s1", "Tool", "Tool Execution", "major"))
    await db["events"].insert_one(_classified_event("s1", "Security", "Authentication", "critical"))
    monkeypatch.setattr(stats_module, "get_db", lambda: db)

    result = await stats_module.category_counts(window_minutes=1440)
    assert result["rows"][0]["count"] == 3
    assert result["rows"][0]["subcategory"] == "Tool Execution"


@pytest.mark.asyncio
async def test_category_counts_ignores_unclassified_events(monkeypatch):
    db = WritableFakeDB()
    await db["events"].insert_one({"server_id": "s1", "type": "rpc_call", "ts": time.time(), "is_error": True})
    monkeypatch.setattr(stats_module, "get_db", lambda: db)

    result = await stats_module.category_counts(window_minutes=1440)
    assert result["rows"] == []


@pytest.mark.asyncio
async def test_severity_breakdown_counts_by_severity(monkeypatch):
    db = WritableFakeDB()
    await db["events"].insert_one(_classified_event("s1", "Tool", "Tool Execution", "major"))
    await db["events"].insert_one(_classified_event("s1", "Tool", "Tool Execution", "major"))
    await db["events"].insert_one(_classified_event("s1", "Security", "Authentication", "critical"))
    monkeypatch.setattr(stats_module, "get_db", lambda: db)

    result = await stats_module.severity_breakdown(window_minutes=1440)
    assert result["counts"] == {"major": 2, "critical": 1}


@pytest.mark.asyncio
async def test_health_distribution_counts_by_status(monkeypatch):
    db = WritableFakeDB()
    now = time.time()
    await db["servers"].insert_one({"server_id": "a", "last_seen": now, "latest_health": {"status": "healthy"}})
    await db["servers"].insert_one({"server_id": "b", "last_seen": now, "latest_health": {"status": "degraded"}})
    await db["servers"].insert_one({"server_id": "c", "last_seen": now, "latest_health": {"status": "healthy"}})
    monkeypatch.setattr(stats_module, "get_db", lambda: db)

    result = await stats_module.health_distribution(idle_after_minutes=60)
    assert result["total_servers"] == 3
    assert result["counts"] == {"healthy": 2, "degraded": 1}


@pytest.mark.asyncio
async def test_health_distribution_treats_stale_servers_as_idle_not_cached_status(monkeypatch):
    db = WritableFakeDB()
    now = time.time()
    # last_seen 2 hours ago, but cached status still says "healthy" from
    # back when it was last actually ingesting -- must not be trusted.
    await db["servers"].insert_one({
        "server_id": "stale", "last_seen": now - 7200, "latest_health": {"status": "healthy"},
    })
    await db["servers"].insert_one({"server_id": "fresh", "last_seen": now, "latest_health": {"status": "healthy"}})
    monkeypatch.setattr(stats_module, "get_db", lambda: db)

    result = await stats_module.health_distribution(idle_after_minutes=60)
    assert result["counts"] == {"idle": 1, "healthy": 1}


@pytest.mark.asyncio
async def test_health_distribution_treats_never_seen_as_idle(monkeypatch):
    db = WritableFakeDB()
    await db["servers"].insert_one({"server_id": "ghost", "latest_health": {"status": "healthy"}})
    monkeypatch.setattr(stats_module, "get_db", lambda: db)

    result = await stats_module.health_distribution(idle_after_minutes=60)
    assert result["counts"] == {"idle": 1}


@pytest.mark.asyncio
async def test_heatmap_returns_24_hour_cells(monkeypatch):
    db = WritableFakeDB()
    now = time.time()
    await db["events"].insert_one({"server_id": "s1", "type": "rpc_call", "ts": now, "is_error": True})
    monkeypatch.setattr(stats_module, "get_db", lambda: db)

    result = await stats_module.error_rate_heatmap("s1", hours=24)
    assert len(result["cells"]) == 24
    assert sum(c["total_calls"] for c in result["cells"]) == 1


@pytest.mark.asyncio
async def test_events_by_severity_filters_correctly(monkeypatch):
    db = WritableFakeDB()
    await db["events"].insert_one(_classified_event("s1", "Tool", "Tool Execution", "critical"))
    await db["events"].insert_one(_classified_event("s1", "Tool", "Tool Execution", "minor"))
    monkeypatch.setattr(stats_module, "get_db", lambda: db)

    result = await stats_module.events_by_severity(severity="critical", limit=50)
    assert len(result["events"]) == 1
    assert result["events"][0]["classification"]["dominant_severity"] == "critical"
