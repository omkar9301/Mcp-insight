from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth import require_api_key
from ..keys import revoke_server_key, set_server_key

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/v1/servers/{server_id}/keys")
async def rotate_server_key(server_id: str):
    """Mints a new API key scoped to this server_id, invalidating any
    previous one. The plaintext key is returned exactly once -- store it
    in the wrapper's `--api-key` / `MCP_INSIGHT_API_KEY` now, it cannot be
    retrieved again (only the salted hash is stored)."""
    plaintext = await set_server_key(server_id)
    return {
        "server_id": server_id,
        "api_key": plaintext,
        "note": "Store this now -- it will not be shown again. Rotating again invalidates this key.",
    }


@router.delete("/v1/servers/{server_id}/keys")
async def revoke_server_key_route(server_id: str):
    """Revokes this server's scoped key. The deployment-wide admin key can
    still ingest events for this server_id after revocation."""
    await revoke_server_key(server_id)
    return {"server_id": server_id, "revoked": True}
