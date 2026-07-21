from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Query

from ..anomaly import detect_anomalies
from ..auth import require_api_key
from ..db import get_db
from ..health_scoring import compute_health_score
from ..rate_limit import enforce_read_rate_limit

router = APIRouter(dependencies=[Depends(require_api_key), Depends(enforce_read_rate_limit)])


@router.get("/v1/servers/{server_id}/health")
async def get_health(server_id: str, window_minutes: int = Query(60, ge=1, le=1440)):
    db = get_db()
    since = time.time() - window_minutes * 60

    server = await db["servers"].find_one({"server_id": server_id})
    if server is None:
        raise HTTPException(status_code=404, detail="Unknown server_id -- no events received yet")

    cursor = db["events"].find({"server_id": server_id, "ts": {"$gte": since}})
    latencies: list[float] = []
    total_calls = 0
    error_count = 0
    silent_failure_count = 0
    cpu_samples: list[float] = []
    mem_samples: list[int] = []
    severities: list[str] = []

    async for doc in cursor:
        if doc.get("type") == "rpc_call":
            total_calls += 1
            if doc.get("latency_ms") is not None:
                latencies.append(doc["latency_ms"])
            if doc.get("is_error"):
                error_count += 1
            if doc.get("silent_failure"):
                silent_failure_count += 1
        elif doc.get("type") == "process_metrics":
            if doc.get("cpu_percent") is not None:
                cpu_samples.append(doc["cpu_percent"])
            if doc.get("memory_rss_bytes") is not None:
                mem_samples.append(doc["memory_rss_bytes"])

        classification = doc.get("classification")
        if classification and classification.get("dominant_severity"):
            severities.append(classification["dominant_severity"])

    latencies.sort()

    def pct(p: float) -> float | None:
        if not latencies:
            return None
        idx = min(len(latencies) - 1, int(len(latencies) * p))
        return latencies[idx]

    health = compute_health_score(
        total_calls=total_calls,
        error_count=error_count,
        silent_failure_count=silent_failure_count,
        p95_latency_ms=pct(0.95),
        cpu_samples=cpu_samples,
        mem_samples=mem_samples,
        classified_severities=severities,
    )

    return {
        "server_id": server_id,
        "window_minutes": window_minutes,
        "total_calls": total_calls,
        "error_rate": (error_count / total_calls) if total_calls else 0.0,
        "silent_failure_count": silent_failure_count,
        "p50_latency_ms": pct(0.50),
        "p95_latency_ms": pct(0.95),
        "p99_latency_ms": pct(0.99),
        "process_metrics": {
            "avg_cpu_percent": (sum(cpu_samples) / len(cpu_samples)) if cpu_samples else None,
            "latest_memory_rss_bytes": mem_samples[-1] if mem_samples else None,
            "sample_count": len(cpu_samples),
        },
        "health_score": health["score"],
        "health_status": health["status"],
        "health_breakdown": health["breakdown"],
        "dropped_events_total": server.get("dropped_events_total", 0),
        "last_seen": server.get("last_seen"),
    }


@router.get("/v1/servers/{server_id}/anomalies")
async def get_anomalies(server_id: str, window_minutes: int = Query(15, ge=1, le=180)):
    db = get_db()
    server = await db["servers"].find_one({"server_id": server_id})
    if server is None:
        raise HTTPException(status_code=404, detail="Unknown server_id -- no events received yet")
    return await detect_anomalies(server_id, window_minutes=window_minutes)


@router.get("/v1/servers")
async def list_servers():
    db = get_db()
    servers = []
    async for doc in db["servers"].find({}, {"_id": 0}):
        servers.append(doc)
    return {"servers": servers}


@router.get("/v1/servers/{server_id}/events")
async def recent_events(server_id: str, limit: int = Query(50, ge=1, le=500), only_faults: bool = False):
    db = get_db()
    query: dict = {"server_id": server_id}
    if only_faults:
        query["$or"] = [{"is_error": True}, {"silent_failure": True}, {"type": "protocol_violation"}]

    cursor = db["events"].find(query, {"_id": 0}).sort("ts", -1).limit(limit)
    events = [doc async for doc in cursor]
    return {"events": events}
