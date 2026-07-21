from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth import require_api_key
from ..db import get_db
from ..rate_limit import enforce_read_rate_limit

router = APIRouter(dependencies=[Depends(require_api_key), Depends(enforce_read_rate_limit)])


@router.get("/v1/servers/{server_id}/alerts")
async def alert_history(server_id: str, limit: int = Query(50, ge=1, le=500)):
    db = get_db()
    cursor = db["alerts"].find({"server_id": server_id}, {"_id": 0}).sort("sent_at", -1).limit(limit)
    alerts = [doc async for doc in cursor]
    return {"server_id": server_id, "alerts": alerts}


class MuteRequest(BaseModel):
    minutes: int = 60


@router.post("/v1/servers/{server_id}/mute")
async def mute_alerts(server_id: str, req: MuteRequest):
    if req.minutes <= 0:
        raise HTTPException(status_code=400, detail="minutes must be positive")
    db = get_db()
    until = time.time() + req.minutes * 60
    await db["servers"].update_one(
        {"server_id": server_id}, {"$set": {"alerts_muted_until": until}}, upsert=True
    )
    return {"server_id": server_id, "muted_until": until}


@router.delete("/v1/servers/{server_id}/mute")
async def unmute_alerts(server_id: str):
    db = get_db()
    await db["servers"].update_one({"server_id": server_id}, {"$unset": {"alerts_muted_until": ""}})
    return {"server_id": server_id, "muted": False}
