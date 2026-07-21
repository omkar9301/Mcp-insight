from __future__ import annotations

import os

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://mongo:27017")
DB_NAME = os.environ.get("MONGO_DB", "mcp_insight")

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(MONGO_URI)
    return _client


def get_db():
    return get_client()[DB_NAME]


async def ensure_indexes() -> None:
    db = get_db()
    events = db["events"]
    await events.create_index([("server_id", 1), ("ts", -1)])
    await events.create_index([("server_id", 1), ("type", 1), ("ts", -1)])
    await events.create_index("ts", expireAfterSeconds=60 * 60 * 24 * 30)  # 30-day default retention

    servers = db["servers"]
    await servers.create_index("server_id", unique=True)

    alert_cooldowns = db["alert_cooldowns"]
    await alert_cooldowns.create_index([("server_id", 1), ("alert_kind", 1)], unique=True)
