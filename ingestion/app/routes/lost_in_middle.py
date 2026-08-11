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


@router.get("/v1/litm/summary")
async def litm_deep_summary(window_minutes: int = Query(43200, ge=1, le=43200), trend_buckets: int = Query(14, ge=2, le=90)):
    """Fleet-wide LITM rollup for the deep-dive insights page: risk-factor
    breakdown, a daily trend, and a worst-offenders leaderboard (by tool,
    across servers) -- everything the fleet overview view needs in one
    call instead of N."""
    db = get_db()
    since = time.time() - window_minutes * 60
    query = {"ts": {"$gte": since}, **_LITM_QUERY}

    risk_counts: Counter = Counter()
    servers_affected: set[str] = set()
    leaderboard: dict[tuple[str, str], dict] = defaultdict(lambda: {"flagged_calls": 0, "risk_factor_counts": Counter(), "last_seen": 0.0})
    total = 0

    now = time.time()
    bucket_span_s = (window_minutes * 60) / trend_buckets
    trend = [0] * trend_buckets

    async for doc in db["events"].find(query):
        total += 1
        server_id = doc.get("server_id", "unknown")
        tool_name = doc.get("tool_name", "unknown")
        servers_affected.add(server_id)
        factors = doc["lost_in_middle"].get("risk_factors") or []
        for factor in factors:
            risk_counts[factor] += 1

        key = (server_id, tool_name)
        row = leaderboard[key]
        row["flagged_calls"] += 1
        row["last_seen"] = max(row["last_seen"], doc["ts"])
        for factor in factors:
            row["risk_factor_counts"][factor] += 1

        age_s = max(0.0, now - doc["ts"])
        bucket_offset = min(trend_buckets - 1, int(age_s // bucket_span_s))
        trend[trend_buckets - 1 - bucket_offset] += 1

    leaderboard_rows = [
        {
            "server_id": server_id,
            "tool_name": tool_name,
            "flagged_calls": row["flagged_calls"],
            "risk_factor_counts": dict(row["risk_factor_counts"]),
            "last_seen": row["last_seen"],
        }
        for (server_id, tool_name), row in leaderboard.items()
    ]
    leaderboard_rows.sort(key=lambda r: r["flagged_calls"], reverse=True)

    trend_points = [
        {"bucket_start": now - (trend_buckets - i) * bucket_span_s, "flagged_calls": count}
        for i, count in enumerate(trend)
    ]

    return {
        "window_minutes": window_minutes,
        "total_flagged": total,
        "servers_affected": len(servers_affected),
        "risk_factor_counts": dict(risk_counts),
        "leaderboard": leaderboard_rows,
        "trend": trend_points,
    }


@router.get("/v1/litm/tools/{server_id}/{tool_name}")
async def litm_tool_detail(server_id: str, tool_name: str, window_minutes: int = Query(43200, ge=1, le=43200), limit: int = Query(20, ge=1, le=100)):
    """Single-tool deep dive for the drill-down view: score distribution,
    result-count distribution, repeat-query rate, and the most recent
    flagged calls with their full decision trail + per-item detail (as
    captured by the wrapper -- see lost_in_middle.py) so the frontend can
    render the position-vs-score chart and counterfactual replay without
    another round trip per event."""
    db = get_db()
    since = time.time() - window_minutes * 60
    query = {"server_id": server_id, "tool_name": tool_name, "ts": {"$gte": since}, **_LITM_QUERY}

    cursor = db["events"].find(query, {"_id": 0}).sort("ts", -1)
    docs = [doc async for doc in cursor]
    if not docs:
        raise HTTPException(status_code=404, detail="No lost-in-the-middle events found for this server/tool in this window")

    all_scores: list[float] = []
    result_counts: list[int] = []
    repeated_count = 0
    risk_counts: Counter = Counter()
    for doc in docs:
        signal = doc["lost_in_middle"]
        for factor in signal.get("risk_factors") or []:
            risk_counts[factor] += 1
            if factor == "repeated_query_after_large_context":
                repeated_count += 1
        if signal.get("result_count") is not None:
            result_counts.append(signal["result_count"])
        for item in signal.get("items") or []:
            if item.get("score") is not None:
                all_scores.append(item["score"])

    return {
        "server_id": server_id,
        "tool_name": tool_name,
        "window_minutes": window_minutes,
        "flagged_calls": len(docs),
        "risk_factor_counts": dict(risk_counts),
        "repeated_query_rate": repeated_count / len(docs) if docs else 0.0,
        "score_distribution": all_scores,
        "result_count_distribution": result_counts,
        "recent_events": docs[:limit],
    }
