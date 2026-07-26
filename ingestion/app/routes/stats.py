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
from pydantic import BaseModel

from ..auth import require_api_key
from ..config import settings
from ..db import get_db
from ..rate_limit import enforce_read_rate_limit

router = APIRouter(dependencies=[Depends(require_api_key), Depends(enforce_read_rate_limit)])

FLEET_SNAPSHOT_MIN_INTERVAL_S = 15 * 60


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
async def health_distribution(idle_after_minutes: int = Query(60, ge=1, le=1440)):
    """How many servers are currently healthy/degraded/unhealthy/critical
    -- feeds the fleet-health donut on the Overview page.

    `latest_health.status` is a cache written the last time a server
    ingested a batch -- if a server goes quiet, that cached status goes
    stale and keeps reporting whatever it was last (e.g. still "healthy"
    long after the server stopped sending anything at all). A server is
    only counted by its cached status if it's been seen within
    `idle_after_minutes`; otherwise it's counted as "idle" regardless of
    what's cached, matching the same idle logic `/health` uses per-server.
    """
    db = get_db()
    now = time.time()
    counts: Counter = Counter()
    total = 0
    async for doc in db["servers"].find({}):
        total += 1
        last_seen = doc.get("last_seen")
        if last_seen is None or (now - last_seen) > idle_after_minutes * 60:
            counts["idle"] += 1
        else:
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


@router.get("/v1/stats/alerting-status")
async def alerting_status():
    """Whether alerting is even configured, and evidence it's actually
    working -- the Overview page has no visibility into this otherwise,
    even though alerting is a real feature of the system."""
    db = get_db()
    since_24h = time.time() - 24 * 3600

    last_alert = None
    count_24h = 0
    async for doc in db["alerts"].find({}).sort("sent_at", -1).limit(1):
        last_alert = doc.get("sent_at")
    async for doc in db["alerts"].find({"sent_at": {"$gte": since_24h}}):
        count_24h += 1

    return {
        "configured": bool(settings.slack_webhook_url),
        "alerts_last_24h": count_24h,
        "last_alert_sent_at": last_alert,
    }


@router.get("/v1/stats/low-confidence-count")
async def low_confidence_count(window_minutes: int = Query(1440, ge=1, le=43200)):
    """How many auto-classified faults the classifier itself flagged as
    low-confidence in the window -- surfaces classifier data quality on
    the Overview page instead of leaving it buried per-event."""
    db = get_db()
    since = time.time() - window_minutes * 60
    cursor = db["events"].find({"classification.low_confidence": True, "ts": {"$gte": since}})
    count = 0
    async for _ in cursor:
        count += 1
    return {"window_minutes": window_minutes, "low_confidence_count": count}


class FleetSnapshotRequest(BaseModel):
    total_servers: int
    active_servers: int
    avg_score: float | None
    total_calls: int


@router.post("/v1/stats/fleet-snapshot")
async def record_fleet_snapshot(req: FleetSnapshotRequest):
    """Records a point-in-time fleet-wide summary so KPI tiles can show a
    delta ("+3 vs 24h ago") instead of a bare snapshot with no direction.
    Computing avg_score/active_servers server-side would mean redoing the
    same per-server health aggregation the dashboard already does client
    side -- so the dashboard computes it and posts it here instead.
    Throttled to at most one snapshot per FLEET_SNAPSHOT_MIN_INTERVAL_S so
    frequent polling doesn't flood the collection."""
    db = get_db()
    now = time.time()
    latest = None
    async for doc in db["fleet_snapshots"].find({}).sort("ts", -1).limit(1):
        latest = doc
    if latest and (now - latest["ts"]) < FLEET_SNAPSHOT_MIN_INTERVAL_S:
        return {"recorded": False, "reason": "throttled"}

    await db["fleet_snapshots"].insert_one({
        "ts": now,
        "total_servers": req.total_servers,
        "active_servers": req.active_servers,
        "avg_score": req.avg_score,
        "total_calls": req.total_calls,
    })
    return {"recorded": True}


@router.get("/v1/stats/fleet-snapshot")
async def get_fleet_snapshot(hours_ago: float = Query(24, ge=0.1, le=720)):
    """Returns the fleet snapshot closest to (but not after) `hours_ago`
    in the past, for computing "vs N hours ago" deltas on the Overview
    page. Returns null fields if no snapshot old enough exists yet."""
    db = get_db()
    target = time.time() - hours_ago * 3600
    cursor = db["fleet_snapshots"].find({"ts": {"$lte": target}}, {"_id": 0}).sort("ts", -1).limit(1)
    snapshot = None
    async for doc in cursor:
        snapshot = doc
    return {"hours_ago": hours_ago, "snapshot": snapshot}
