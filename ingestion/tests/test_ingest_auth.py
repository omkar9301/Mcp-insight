import pytest
from fastapi import HTTPException

from app.auth import require_ingest_auth
from app.config import settings


@pytest.mark.asyncio
async def test_admin_key_authorizes_any_server(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "admin-secret")
    await require_ingest_auth("any-server", "Bearer admin-secret")  # should not raise


@pytest.mark.asyncio
async def test_missing_header_rejected(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "admin-secret")
    with pytest.raises(HTTPException) as exc:
        await require_ingest_auth("srv-1", None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_per_server_key_authorizes_only_its_own_server(monkeypatch):
    from app import keys as keys_module

    monkeypatch.setattr(settings, "api_key", "admin-secret")

    async def fake_verify(server_id: str, token: str) -> bool:
        return server_id == "srv-1" and token == "srv-1-key"

    monkeypatch.setattr(keys_module, "verify_server_key", fake_verify)
    monkeypatch.setattr("app.auth.verify_server_key", fake_verify)

    await require_ingest_auth("srv-1", "Bearer srv-1-key")  # should not raise

    with pytest.raises(HTTPException) as exc:
        await require_ingest_auth("srv-2", "Bearer srv-1-key")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_disabled_when_no_admin_key(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "")
    await require_ingest_auth("srv-1", None)  # should not raise
