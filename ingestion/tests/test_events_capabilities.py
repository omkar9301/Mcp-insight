import pytest

from app.routes import events as events_module
from app.routes import health as health_module
from app.models import EventBatch
from app.config import settings
from .conftest import WritableFakeDB


@pytest.mark.asyncio
async def test_server_capabilities_event_upserts_tools_not_events(monkeypatch):
    db = WritableFakeDB()
    monkeypatch.setattr(events_module, "get_db", lambda: db)
    monkeypatch.setattr(settings, "api_key", "")  # auth disabled for this test

    batch = EventBatch(
        server_id="s1",
        sent_at=1,
        events=[{
            "type": "server_capabilities",
            "ts": 1,
            "tools": [{"name": "add_numbers", "description": "adds", "input_schema": None, "output_schema": {"type": "object"}}],
        }],
    )

    result = await events_module.ingest_events(batch, authorization=None)

    assert result["accepted"] == 0  # not stored as a traffic event
    assert db._collections.get("events") is None or db._collections["events"]._docs == []
    server = db._collections["servers"]._docs[0]
    assert server["tools"][0]["name"] == "add_numbers"
    assert "tools_updated_at" in server


@pytest.mark.asyncio
async def test_get_server_tools_returns_registry(monkeypatch):
    db = WritableFakeDB()
    monkeypatch.setattr(health_module, "get_db", lambda: db)
    await db["servers"].update_one(
        {"server_id": "s1"}, {"$set": {"tools": [{"name": "x"}], "tools_updated_at": 123}}, upsert=True
    )

    result = await health_module.get_server_tools("s1")
    assert result["tools"] == [{"name": "x"}]
    assert result["tools_updated_at"] == 123


@pytest.mark.asyncio
async def test_get_all_tools_only_includes_servers_with_tools(monkeypatch):
    db = WritableFakeDB()
    monkeypatch.setattr(health_module, "get_db", lambda: db)
    await db["servers"].update_one({"server_id": "s1"}, {"$set": {"tools": [{"name": "x"}]}}, upsert=True)
    await db["servers"].update_one({"server_id": "s2"}, {"$set": {"last_seen": 1}}, upsert=True)  # no tools

    result = await health_module.get_all_tools()
    assert len(result["servers"]) == 1
    assert result["servers"][0]["server_id"] == "s1"
