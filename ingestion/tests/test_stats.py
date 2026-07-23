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
    await db["servers"].insert_one({"server_id": "a", "latest_health": {"status": "healthy"}})
    await db["servers"].insert_one({"server_id": "b", "latest_health": {"status": "degraded"}})
    await db["servers"].insert_one({"server_id": "c", "latest_health": {"status": "healthy"}})
    monkeypatch.setattr(stats_module, "get_db", lambda: db)

    result = await stats_module.health_distribution()
    assert result["total_servers"] == 3
    assert result["counts"] == {"healthy": 2, "degraded": 1}


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
