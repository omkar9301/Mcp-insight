from __future__ import annotations

"""
mcp_insight ingestion lost-in-the-middle risk endpoints.

Aggregates the wrapper's best-effort LITM risk signal (see
wrapper/mcp_insight/lost_in_middle.py) -- known risk factors for context
degradation (oversized/unranked retrieval results, size outliers vs. a
tool's own history, repeated queries after a large prior result), never
a claim that the downstream LLM actually lost context, since this
service has no visibility into that model's attention either.
"""
import time
from collections import Counter, defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import require_api_key
from ..db import get_db
from ..rate_limit import enforce_read_rate_limit

router = APIRouter(dependencies=[Depends(require_api_key), Depends(enforce_read_rate_limit)])

_LITM_QUERY = {"lost_in_middle": {"$exists": True}}


@router.get("/v1/servers/{server_id}/lost-in-middle")
async def server_lost_in_middle(server_id: str, window_minutes: int = Query(1440, ge=1, le=43200)):
    db = get_db()
    server = await db["servers"].find_one({"server_id": server_id})
    if server is None:
        raise HTTPException(status_code=404, detail="Unknown server_id -- no events received yet")

    since = time.time() - window_minutes * 60
    query = {"server_id": server_id, "ts": {"$gte": since}, **_LITM_QUERY}

    by_tool: dict[str, list[dict]] = defaultdict(list)
    async for doc in db["events"].find(query):
        by_tool[doc.get("tool_name", "unknown")].append(doc)

    tools = []
    for name, docs in by_tool.items():
        risk_counts: Counter = Counter()
        tokens = []
        for d in docs:
            signal = d["lost_in_middle"]
            for factor in signal.get("risk_factors") or []:
                risk_counts[factor] += 1
            if signal.get("approx_tokens") is not None:
                tokens.append(signal["approx_tokens"])
        tools.append({
            "tool_name": name,
            "flagged_calls": len(docs),
            "risk_factor_counts": dict(risk_counts),
            "avg_approx_tokens": (sum(tokens) / len(tokens)) if tokens else None,
            "last_seen": max(d["ts"] for d in docs),
        })
    tools.sort(key=lambda t: t["flagged_calls"], reverse=True)

    return {"server_id": server_id, "window_minutes": window_minutes, "tools": tools}


@router.get("/v1/stats/lost-in-middle-summary")
async def lost_in_middle_summary(window_minutes: int = Query(43200, ge=1, le=43200)):
    db = get_db()
    since = time.time() - window_minutes * 60
    query = {"ts": {"$gte": since}, **_LITM_QUERY}

    risk_counts: Counter = Counter()
    servers_affected: set[str] = set()
    total = 0
    async for doc in db["events"].find(query):
        total += 1
        servers_affected.add(doc.get("server_id", "unknown"))
        for factor in doc["lost_in_middle"].get("risk_factors") or []:
            risk_counts[factor] += 1

    return {
        "window_minutes": window_minutes,
        "total_flagged": total,
        "servers_affected": len(servers_affected),
        "risk_factor_counts": dict(risk_counts),
    }


@router.get("/v1/events/lost-in-middle")
async def fleet_lost_in_middle_events(limit: int = Query(50, ge=1, le=500)):
    db = get_db()
    cursor = db["events"].find(_LITM_QUERY, {"_id": 0}).sort("ts", -1).limit(limit)
    events = [doc async for doc in cursor]
    return {"events": events}
