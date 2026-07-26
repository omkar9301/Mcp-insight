import time

import pytest

from app.routes import retrieval as retrieval_module
from .conftest import WritableFakeDB

NOW = time.time()


def _ev(server_id, tool_name, result_count, top_score=None, latency_ms=50, ts=None):
    ts = NOW if ts is None else NOW - (100 - ts)  # small offsets, always in the recent past
    retrieval = {"result_count": result_count, "empty": result_count == 0}
    if top_score is not None:
        retrieval["top_score"] = top_score
    return {
        "server_id": server_id, "type": "rpc_call", "ts": ts, "latency_ms": latency_ms,
        "tool_name": tool_name, "retrieval": retrieval,
    }


@pytest.mark.asyncio
async def test_server_retrieval_tools_summarizes_per_tool(monkeypatch):
    db = WritableFakeDB()
    await db["servers"].insert_one({"server_id": "s1"})
    await db["events"].insert_one(_ev("s1", "vector_search", 3, top_score=0.9, ts=1))
    await db["events"].insert_one(_ev("s1", "vector_search", 0, ts=2))
    await db["events"].insert_one(_ev("s1", "vector_search", 5, top_score=0.6, ts=3))
    monkeypatch.setattr(retrieval_module, "get_db", lambda: db)

    result = await retrieval_module.server_retrieval_tools("s1", window_minutes=1440)
    tool = result["tools"][0]
    assert tool["tool_name"] == "vector_search"
    assert tool["total_calls"] == 3
    assert tool["empty_result_count"] == 1
    assert round(tool["empty_result_rate"], 3) == round(1 / 3, 3)
    assert tool["avg_top_score"] == 0.75


@pytest.mark.asyncio
async def test_server_retrieval_tools_404_for_unknown_server(monkeypatch):
    db = WritableFakeDB()
    monkeypatch.setattr(retrieval_module, "get_db", lambda: db)

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await retrieval_module.server_retrieval_tools("ghost", window_minutes=1440)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_server_retrieval_tools_empty_when_no_retrieval_events(monkeypatch):
    db = WritableFakeDB()
    await db["servers"].insert_one({"server_id": "s1"})
    await db["events"].insert_one({"server_id": "s1", "type": "rpc_call", "ts": 1, "method": "add_numbers"})
    monkeypatch.setattr(retrieval_module, "get_db", lambda: db)

    result = await retrieval_module.server_retrieval_tools("s1", window_minutes=1440)
    assert result["tools"] == []


@pytest.mark.asyncio
async def test_fleet_retrieval_tools_groups_by_server_and_tool_sorted_by_empty_rate(monkeypatch):
    db = WritableFakeDB()
    # s1/tool-a: 1 of 2 empty (50%)
    await db["events"].insert_one(_ev("s1", "tool-a", 0, ts=1))
    await db["events"].insert_one(_ev("s1", "tool-a", 4, ts=2))
    # s2/tool-b: 0 of 1 empty (0%)
    await db["events"].insert_one(_ev("s2", "tool-b", 2, ts=3))
    monkeypatch.setattr(retrieval_module, "get_db", lambda: db)

    result = await retrieval_module.fleet_retrieval_tools(window_minutes=1440)
    assert len(result["rows"]) == 2
    assert result["rows"][0]["server_id"] == "s1"  # worst empty rate first
    assert result["rows"][0]["empty_result_rate"] == 0.5
    assert result["rows"][1]["server_id"] == "s2"
    assert result["rows"][1]["empty_result_rate"] == 0.0
