import time

import pytest

from app.routes import injection as injection_module
from .conftest import WritableFakeDB


def _injection_event(server_id, subtypes, confidence_source="keyword", ts=None):
    return {
        "server_id": server_id, "type": "rpc_call", "ts": ts or time.time(),
        "prompt_injection": {"subtypes": subtypes, "confidence_source": confidence_source, "preview": "x"},
    }


@pytest.mark.asyncio
async def test_server_injection_events_filters_by_server(monkeypatch):
    db = WritableFakeDB()
    await db["events"].insert_one(_injection_event("s1", ["imperative_to_model"]))
    await db["events"].insert_one(_injection_event("s2", ["role_authority_spoofing"]))
    monkeypatch.setattr(injection_module, "get_db", lambda: db)

    result = await injection_module.server_injection_events("s1", limit=50)
    assert len(result["events"]) == 1
    assert result["events"][0]["server_id"] == "s1"


@pytest.mark.asyncio
async def test_prompt_injection_summary_aggregates_across_fleet(monkeypatch):
    db = WritableFakeDB()
    now = time.time()
    await db["events"].insert_one(_injection_event("s1", ["imperative_to_model"], ts=now))
    await db["events"].insert_one(_injection_event("s1", ["imperative_to_model", "role_authority_spoofing"], ts=now))
    await db["events"].insert_one(_injection_event("s2", ["exfiltration_trigger"], confidence_source="structural", ts=now))
    monkeypatch.setattr(injection_module, "get_db", lambda: db)

    result = await injection_module.prompt_injection_summary(window_minutes=43200)
    assert result["total_flagged"] == 3
    assert result["servers_affected"] == 2
    assert result["subtype_counts"]["imperative_to_model"] == 2
    assert result["subtype_counts"]["role_authority_spoofing"] == 1
    assert result["confidence_source_counts"]["structural"] == 1


@pytest.mark.asyncio
async def test_fleet_injection_events_returns_most_recent_first(monkeypatch):
    db = WritableFakeDB()
    now = time.time()
    await db["events"].insert_one(_injection_event("s1", ["imperative_to_model"], ts=now - 10))
    await db["events"].insert_one(_injection_event("s2", ["role_authority_spoofing"], ts=now))
    monkeypatch.setattr(injection_module, "get_db", lambda: db)

    result = await injection_module.fleet_injection_events(limit=50)
    assert result["events"][0]["server_id"] == "s2"


@pytest.mark.asyncio
async def test_summary_empty_when_no_injection_events(monkeypatch):
    db = WritableFakeDB()
    monkeypatch.setattr(injection_module, "get_db", lambda: db)

    result = await injection_module.prompt_injection_summary(window_minutes=43200)
    assert result["total_flagged"] == 0
    assert result["servers_affected"] == 0
