from __future__ import annotations

from fastapi import Header, HTTPException

from .config import settings
from .keys import verify_server_key


def _extract_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization[len("Bearer "):]


async def require_api_key(authorization: str | None = Header(default=None)) -> None:
    """Admin-only auth: validates the `Authorization: Bearer <key>` header
    against the deployment-wide admin key. Used for every read/management
    endpoint -- dashboards and operators use the admin key, not a
    per-server key (per-server keys can only write events, see
    `require_ingest_auth`).

    If no admin key is configured for this deployment (MCP_INSIGHT_API_KEY
    unset), auth is treated as disabled -- this is a deliberate local-dev
    escape hatch, not a silent security hole: `docker-compose.yml` always
    sets a key, so a production-shaped deployment always has this enforced.
    """
    if not settings.auth_enabled:
        return

    token = _extract_token(authorization)
    if token is None:
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    if token != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


async def require_ingest_auth(server_id: str, authorization: str | None) -> None:
    """Auth for `POST /v1/events`: accepts either the deployment-wide admin
    key, or a key previously minted specifically for this server_id via
    `POST /v1/servers/{server_id}/keys`. A per-server key can only ever
    write events for that one server -- it's scoped, unlike the admin key.
    """
    if not settings.auth_enabled:
        return

    token = _extract_token(authorization)
    if token is None:
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    if token == settings.api_key:
        return
    if await verify_server_key(server_id, token):
        return
    raise HTTPException(status_code=401, detail="Invalid API key for this server_id")
