import pytest
from fastapi import HTTPException

from app.auth import require_api_key
from app.config import settings


@pytest.mark.asyncio
async def test_auth_disabled_when_no_key_configured(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "")
    await require_api_key(authorization=None)  # should not raise


@pytest.mark.asyncio
async def test_auth_rejects_missing_header_when_key_configured(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "secret")
    with pytest.raises(HTTPException) as exc:
        await require_api_key(authorization=None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_rejects_malformed_header(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "secret")
    with pytest.raises(HTTPException) as exc:
        await require_api_key(authorization="secret")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_rejects_wrong_key(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "secret")
    with pytest.raises(HTTPException) as exc:
        await require_api_key(authorization="Bearer wrong")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_accepts_correct_key(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "secret")
    await require_api_key(authorization="Bearer secret")  # should not raise
