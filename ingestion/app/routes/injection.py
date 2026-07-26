from __future__ import annotations

"""
mcp_insight ingestion prompt-injection (taxonomy category 28) endpoints.

Kept entirely separate from the 27-category fault taxonomy and its
classifier/health-score pipeline -- injection signals never feed
compute_health_score or /v1/stats/category-counts, since mixing an
adversarial signal into the fault-rate denominator would skew health
scores for something that isn't a functional fault.
"""
import time
from collections import Counter

from fastapi import APIRouter, Depends, Query

from ..auth import require_api_key
from ..db import get_db
from ..rate_limit import enforce_read_rate_limit

router = APIRouter(dependencies=[Depends(require_api_key), Depends(enforce_read_rate_limit)])

_INJECTION_QUERY = {"prompt_injection": {"$exists": True}}


@router.get("/v1/servers/{server_id}/prompt-injection-events")
async def server_injection_events(server_id: str, limit: int = Query(50, ge=1, le=500)):
    db = get_db()
    query = {"server_id": server_id, **_INJECTION_QUERY}
    cursor = db["events"].find(query, {"_id": 0}).sort("ts", -1).limit(limit)
    events = [doc async for doc in cursor]
    return {"server_id": server_id, "events": events}


@router.get("/v1/stats/prompt-injection-summary")
async def prompt_injection_summary(window_minutes: int = Query(43200, ge=1, le=43200)):
    """Fleet-wide: total flagged signals, distinct servers/tools
    affected, and counts by subtype -- the Security page's headline
    numbers."""
    db = get_db()
    since = time.time() - window_minutes * 60
    query = {**_INJECTION_QUERY, "ts": {"$gte": since}}

    subtype_counts: Counter = Counter()
    confidence_counts: Counter = Counter()
    servers_affected: set[str] = set()
    total = 0
    async for doc in db["events"].find(query, {"_id": 0}):
        total += 1
        signal = doc["prompt_injection"]
        servers_affected.add(doc.get("server_id", "unknown"))
        for subtype in signal.get("subtypes") or []:
            subtype_counts[subtype] += 1
        confidence_counts[signal.get("confidence_source", "unknown")] += 1

    return {
        "window_minutes": window_minutes,
        "total_flagged": total,
        "servers_affected": len(servers_affected),
        "subtype_counts": dict(subtype_counts),
        "confidence_source_counts": dict(confidence_counts),
    }


@router.get("/v1/events/prompt-injection")
async def fleet_injection_events(limit: int = Query(50, ge=1, le=500)):
    db = get_db()
    cursor = db["events"].find(_INJECTION_QUERY, {"_id": 0}).sort("ts", -1).limit(limit)
    events = [doc async for doc in cursor]
    return {"events": events}
