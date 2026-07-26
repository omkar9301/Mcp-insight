from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Query

from ..advisory import generate_advisory
from ..auth import require_api_key
from ..config import settings
from ..db import get_db
from ..rate_limit import enforce_read_rate_limit

router = APIRouter(dependencies=[Depends(require_api_key), Depends(enforce_read_rate_limit)])


@router.get("/v1/advisory/status")
async def advisory_status():
    return {"configured": bool(settings.anthropic_api_key)}


@router.post("/v1/servers/{server_id}/events/{ts}/advisory")
async def get_advisory(server_id: str, ts: float, force: bool = Query(False)):
    """Generates (or returns the cached) AI advisory for one captured
    event -- root cause, solution, and exactly what data it's grounded
    in. Cached on the event itself so repeated views don't re-spend LLM
    calls; pass `force=true` to regenerate."""
    if not settings.anthropic_api_key:
        return {"configured": False, "advisory": None}

    db = get_db()
    event = await db["events"].find_one({"server_id": server_id, "ts": ts})
    if event is None:
        raise HTTPException(status_code=404, detail="No event found for that server_id/ts")

    if not force and event.get("ai_advisory"):
        return {"configured": True, "advisory": event["ai_advisory"], "cached": True}

    advisory = await generate_advisory(event)
    if advisory is None:
        raise HTTPException(status_code=502, detail="Advisory generation failed -- try again")

    advisory["generated_at"] = time.time()
    await db["events"].update_one(
        {"server_id": server_id, "ts": ts}, {"$set": {"ai_advisory": advisory}}
    )
    return {"configured": True, "advisory": advisory, "cached": False}
