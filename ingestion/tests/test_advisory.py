import pytest

from app import advisory as advisory_module
from app.config import settings
from app.routes import advisory as advisory_route
from .conftest import WritableFakeDB


def test_describe_event_includes_available_fields_only():
    event = {
        "type": "rpc_call", "method": "tools/call", "latency_ms": 12.3, "is_error": False,
        "silent_failure": True,
        "schema_violation": {"tool": "add_numbers", "violation": "'sum' is a required property", "path": []},
        "classification": {"category": "Tool", "subcategory": "Tool Result Propagation", "dominant_severity": "major", "dominant_effort": "low"},
    }
    desc = advisory_module._describe_event(event)
    assert "add_numbers" in desc
    assert "'sum' is a required property" in desc
    assert "Tool Result Propagation" in desc


@pytest.mark.asyncio
async def test_generate_advisory_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    result = await advisory_module.generate_advisory({"type": "rpc_call"})
    assert result is None


@pytest.mark.asyncio
async def test_advisory_status_reports_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    result = await advisory_route.advisory_status()
    assert result["configured"] is False


@pytest.mark.asyncio
async def test_get_advisory_returns_unconfigured_without_calling_db(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    db = WritableFakeDB()
    monkeypatch.setattr(advisory_route, "get_db", lambda: db)

    result = await advisory_route.get_advisory("s1", 123.0, force=False)
    assert result == {"configured": False, "advisory": None}


@pytest.mark.asyncio
async def test_get_advisory_404_when_no_matching_event(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key")
    db = WritableFakeDB()
    monkeypatch.setattr(advisory_route, "get_db", lambda: db)

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await advisory_route.get_advisory("s1", 999.0, force=False)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_advisory_returns_cached_without_regenerating(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key")
    db = WritableFakeDB()
    await db["events"].insert_one({"server_id": "s1", "ts": 1.0, "ai_advisory": {"summary": "cached"}})
    monkeypatch.setattr(advisory_route, "get_db", lambda: db)

    called = False

    async def fake_generate(event):
        nonlocal called
        called = True
        return {"summary": "fresh"}

    monkeypatch.setattr(advisory_route, "generate_advisory", fake_generate)

    result = await advisory_route.get_advisory("s1", 1.0, force=False)
    assert result["cached"] is True
    assert result["advisory"]["summary"] == "cached"
    assert called is False


@pytest.mark.asyncio
async def test_get_advisory_force_regenerates_and_persists(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key")
    db = WritableFakeDB()
    await db["events"].insert_one({"server_id": "s1", "ts": 1.0, "ai_advisory": {"summary": "old"}})
    monkeypatch.setattr(advisory_route, "get_db", lambda: db)

    async def fake_generate(event):
        return {"summary": "new"}

    monkeypatch.setattr(advisory_route, "generate_advisory", fake_generate)

    result = await advisory_route.get_advisory("s1", 1.0, force=True)
    assert result["cached"] is False
    assert result["advisory"]["summary"] == "new"
    assert db._collections["events"]._docs[0]["ai_advisory"]["summary"] == "new"


@pytest.mark.asyncio
async def test_get_advisory_502_when_generation_fails(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key")
    db = WritableFakeDB()
    await db["events"].insert_one({"server_id": "s1", "ts": 1.0})
    monkeypatch.setattr(advisory_route, "get_db", lambda: db)

    async def fake_generate(event):
        return None

    monkeypatch.setattr(advisory_route, "generate_advisory", fake_generate)

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await advisory_route.get_advisory("s1", 1.0, force=False)
    assert exc.value.status_code == 502
