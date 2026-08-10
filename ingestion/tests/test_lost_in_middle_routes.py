import time

import pytest

from app.routes import lost_in_middle as litm_module
from .conftest import WritableFakeDB


def _litm_event(server_id, tool_name, risk_factors, approx_tokens=100, ts=None):
    return {
        "server_id": server_id, "type": "rpc_call", "ts": ts or time.time(), "tool_name": tool_name,
        "lost_in_middle": {"risk_factors": risk_factors, "approx_tokens": approx_tokens, "result_count": None, "z_size": None},
    }


@pytest.mark.asyncio
async def test_server_lost_in_middle_summarizes_per_tool(monkeypatch):
    db = WritableFakeDB()
    await db["servers"].insert_one({"server_id": "s1"})
    await db["events"].insert_one(_litm_event("s1", "search", ["large_result_set"], approx_tokens=500))
    await db["events"].insert_one(_litm_event("s1", "search", ["large_result_set", "unranked_results"], approx_tokens=700))
    monkeypatch.setattr(litm_module, "get_db", lambda: db)

    result = await litm_module.server_lost_in_middle("s1", window_minutes=1440)
    tool = result["tools"][0]
    assert tool["tool_name"] == "search"
    assert tool["flagged_calls"] == 2
    assert tool["risk_factor_counts"]["large_result_set"] == 2
    assert tool["risk_factor_counts"]["unranked_results"] == 1
    assert tool["avg_approx_tokens"] == 600


@pytest.mark.asyncio
async def test_server_lost_in_middle_404_for_unknown_server(monkeypatch):
    db = WritableFakeDB()
    monkeypatch.setattr(litm_module, "get_db", lambda: db)

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await litm_module.server_lost_in_middle("ghost", window_minutes=1440)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_lost_in_middle_summary_aggregates_fleet_wide(monkeypatch):
    db = WritableFakeDB()
    await db["events"].insert_one(_litm_event("s1", "search", ["large_result_set"]))
    await db["events"].insert_one(_litm_event("s2", "summarize", ["size_outlier"]))
    await db["events"].insert_one(_litm_event("s2", "summarize", ["repeated_query_after_large_context"]))
    monkeypatch.setattr(litm_module, "get_db", lambda: db)

    result = await litm_module.lost_in_middle_summary(window_minutes=43200)
    assert result["total_flagged"] == 3
    assert result["servers_affected"] == 2
    assert result["risk_factor_counts"]["large_result_set"] == 1
    assert result["risk_factor_counts"]["size_outlier"] == 1


@pytest.mark.asyncio
async def test_fleet_lost_in_middle_events_most_recent_first(monkeypatch):
    db = WritableFakeDB()
    now = time.time()
    await db["events"].insert_one(_litm_event("s1", "search", ["large_result_set"], ts=now - 10))
    await db["events"].insert_one(_litm_event("s2", "summarize", ["size_outlier"], ts=now))
    monkeypatch.setattr(litm_module, "get_db", lambda: db)

    result = await litm_module.fleet_lost_in_middle_events(limit=50)
    assert result["events"][0]["server_id"] == "s2"


@pytest.mark.asyncio
async def test_summary_empty_when_nothing_flagged(monkeypatch):
    db = WritableFakeDB()
    monkeypatch.setattr(litm_module, "get_db", lambda: db)

    result = await litm_module.lost_in_middle_summary(window_minutes=43200)
    assert result["total_flagged"] == 0
