from __future__ import annotations

"""
mcp_insight ingestion aggregate stats -- cross-server rollups that power
the dashboard's Overview page and chart views. Kept as plain Python-side
aggregation (fetch + group in memory) rather than Mongo aggregation
pipelines, matching the rest of this codebase (anomaly.py, events.py) and
keeping every endpoint testable against the same FakeDB harness.
"""
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from ..auth import require_api_key
from ..db import get_db
from ..rate_limit import enforce_read_rate_limit

router = APIRouter(dependencies=[Depends(require_api_key), Depends(enforce_read_rate_limit)])


@router.get("/v1/stats/category-counts")
async def category_counts(window_minutes: int = Query(1440, ge=1, le=43200)):
    """Fault counts grouped by taxonomy category/subcategory, across every
    server -- the data behind the Overview page's fault-by-category bar
    chart."""
    db = get_db()
    since = time.time() - window_minutes * 60
    cursor = db["events"].find({"classification": {"$exists": True}, "ts": {"$gte": since}})

    counts: Counter = Counter()
    async for doc in cursor:
        c = doc["classification"]
        counts[(c["category"], c["subcategory"])] += 1

    rows = [
        {"category": cat, "subcategory": sub, "count": n}
        for (cat, sub), n in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return {"window_minutes": window_minutes, "rows": rows}


@router.get("/v1/stats/severity-breakdown")
async def severity_breakdown(window_minutes: int = Query(1440, ge=1, le=43200)):
    """Fault counts grouped by dominant severity (minor/major/critical),
    across every server -- feeds the severity donut chart."""
    db = get_db()
    since = time.time() - window_minutes * 60
    cursor = db["events"].find({"classification": {"$exists": True}, "ts": {"$gte": since}})

    counts: Counter = Counter()
    async for doc in cursor:
        sev = doc["classification"].get("dominant_severity")
        if sev:
            counts[sev] += 1

    return {"window_minutes": window_minutes, "counts": dict(counts)}


@router.get("/v1/stats/health-distribution")
async def health_distribution():
    """How many servers are currently healthy/degraded/unhealthy/critical
    -- feeds the fleet-health donut on the Overview page."""
    db = get_db()
    counts: Counter = Counter()
    total = 0
    async for doc in db["servers"].find({}):
        total += 1
        status = (doc.get("latest_health") or {}).get("status", "unknown")
        counts[status] += 1
    return {"total_servers": total, "counts": dict(counts)}


@router.get("/v1/servers/{server_id}/heatmap")
async def error_rate_heatmap(server_id: str, hours: int = Query(24 * 7, ge=1, le=24 * 30)):
    """Error rate grouped by hour-of-day over the lookback window -- feeds
    the heatmap chart (which hours tend to be worst for this server)."""
    db = get_db()
    since = time.time() - hours * 3600
    cursor = db["events"].find({"server_id": server_id, "type": "rpc_call", "ts": {"$gte": since}})

    by_hour: dict[int, list[dict]] = defaultdict(list)
    async for doc in cursor:
        hour = datetime.fromtimestamp(doc["ts"], tz=timezone.utc).hour
        by_hour[hour].append(doc)

    cells = []
    for hour in range(24):
        docs = by_hour.get(hour, [])
        total = len(docs)
        errors = sum(1 for d in docs if d.get("is_error"))
        cells.append({
            "hour": hour,
            "total_calls": total,
            "error_rate": (errors / total) if total else 0.0,
        })
    return {"server_id": server_id, "hours": hours, "cells": cells}


@router.get("/v1/events/by-severity")
async def events_by_severity(severity: str = Query(...), limit: int = Query(50, ge=1, le=500)):
    """Cross-server view: every stored fault event whose classification's
    dominant severity matches, most recent first."""
    db = get_db()
    query = {"classification.dominant_severity": severity}
    cursor = db["events"].find(query, {"_id": 0}).sort("ts", -1).limit(limit)
    events = [doc async for doc in cursor]
    return {"severity": severity, "events": events}
