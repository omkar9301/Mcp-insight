from __future__ import annotations

"""
mcp_insight ingestion per-server API keys.

The admin key (MCP_INSIGHT_API_KEY) is deployment-wide and can do anything,
including minting/rotating per-server keys. Per-server keys are scoped to
ingesting events for that one server_id only -- a compromised wrapper
deployment for server A can't be used to write fake data for server B, and
can't read anything at all (read endpoints are admin-only).

Keys are generated with `secrets.token_urlsafe` and stored only as a
salted SHA-256 hash -- the plaintext key is returned exactly once, at
creation/rotation time, the same way most API providers do it.
"""
import hashlib
import hmac
import secrets
import time

from .db import get_db

_KEY_PREFIX = "mcpi_"


def generate_key() -> str:
    return _KEY_PREFIX + secrets.token_urlsafe(32)


def _hash_key(key: str, salt: str) -> str:
    return hmac.new(salt.encode(), key.encode(), hashlib.sha256).hexdigest()


async def set_server_key(server_id: str) -> str:
    """Generates and stores a new key for server_id, invalidating any
    previous one. Returns the plaintext key -- caller must show it now."""
    db = get_db()
    plaintext = generate_key()
    salt = secrets.token_hex(16)
    key_hash = _hash_key(plaintext, salt)

    await db["servers"].update_one(
        {"server_id": server_id},
        {
            "$set": {
                "server_id": server_id,
                "api_key_hash": key_hash,
                "api_key_salt": salt,
                "api_key_rotated_at": time.time(),
            },
            "$setOnInsert": {"first_seen": time.time()},
        },
        upsert=True,
    )
    return plaintext


async def revoke_server_key(server_id: str) -> None:
    db = get_db()
    await db["servers"].update_one(
        {"server_id": server_id},
        {"$unset": {"api_key_hash": "", "api_key_salt": ""}},
    )


async def verify_server_key(server_id: str, presented_key: str) -> bool:
    db = get_db()
    server = await db["servers"].find_one({"server_id": server_id})
    if not server or not server.get("api_key_hash") or not server.get("api_key_salt"):
        return False
    expected = _hash_key(presented_key, server["api_key_salt"])
    return hmac.compare_digest(expected, server["api_key_hash"])
