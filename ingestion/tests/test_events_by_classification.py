import pytest

from app.routes import health as health_module
from .conftest import WritableFakeDB


def _ev(server_id, ts, category="Tool", subcategory="Tool Result Propagation"):
    return {
        "server_id": server_id, "type": "rpc_call", "ts": ts, "is_error": False,
        "classification": {"category": category, "subcategory": subcategory},
    }


@pytest.mark.asyncio
async def test_returns_aggregate_stats_over_all_matches_not_just_page(monkeypatch):
    db = WritableFakeDB()
    for i in range(5):
        await db["events"].insert_one(_ev("s1", 100 + i))
    for i in range(3):
        await db["events"].insert_one(_ev("s2", 200 + i))
    await db["events"].insert_one(_ev("s1", 999, category="Security", subcategory="Authentication"))
    monkeypatch.setattr(health_module, "get_db", lambda: db)

    result = await health_module.events_by_classification(
        category="Tool", subcategory="Tool Result Propagation", limit=2
    )

    assert result["total_count"] == 8
    assert result["distinct_servers"] == 2
    assert result["per_server_counts"] == {"s1": 5, "s2": 3}
    assert len(result["events"]) == 2  # page size respected
    assert result["first_seen"] == 100
    assert result["last_seen"] == 202


@pytest.mark.asyncio
async def test_no_matches_returns_zeroed_stats(monkeypatch):
    db = WritableFakeDB()
    monkeypatch.setattr(health_module, "get_db", lambda: db)

    result = await health_module.events_by_classification(category="X", subcategory="Y", limit=50)
    assert result["total_count"] == 0
    assert result["distinct_servers"] == 0
    assert result["first_seen"] is None
    assert result["last_seen"] is None
