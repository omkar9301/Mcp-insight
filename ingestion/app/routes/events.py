from __future__ import annotations

import time

from fastapi import APIRouter, Header

from ..alerting import maybe_alert_anomalies, maybe_alert_health
from ..anomaly import detect_anomalies
from ..auth import require_ingest_auth
from ..classifier_client import classify_event
from ..db import get_db
from ..health_scoring import compute_health_score
from ..metrics_prom import EVENTS_INGESTED, FAULTS_CLASSIFIED
from ..models import EventBatch
from ..rate_limit import enforce_ingest_rate_limit

router = APIRouter()

_FAULT_TYPES = {"rpc_call", "protocol_violation"}


@router.post("/v1/events")
async def ingest_events(batch: EventBatch, authorization: str | None = Header(default=None)):
    await require_ingest_auth(batch.server_id, authorization)
    enforce_ingest_rate_limit(batch.server_id)

    db = get_db()

    # Upsert server registry entry so it shows up in the dashboard immediately,
    # even before any classification or scoring has run.
    await db["servers"].update_one(
        {"server_id": batch.server_id},
        {
            "$set": {"server_id": batch.server_id, "last_seen": time.time()},
            "$setOnInsert": {"first_seen": time.time()},
            "$inc": {"dropped_events_total": batch.dropped_since_last_flush},
        },
        upsert=True,
    )

    if not batch.events:
        return {"accepted": 0}

    docs = []
    for ev in batch.events:
        d = ev.model_dump(exclude_none=True)
        d["server_id"] = batch.server_id
        d["ingested_at"] = time.time()

        # Auto-classify fault-shaped events against the real taxonomy so
        # every stored fault carries a category/severity without a caller
        # having to invoke the classifier separately.
        if d.get("type") in _FAULT_TYPES and (d.get("is_error") or d.get("silent_failure") or d.get("type") == "protocol_violation"):
            classification = await classify_event(d)
            if classification:
                d["classification"] = classification
                FAULTS_CLASSIFIED.inc()

        EVENTS_INGESTED.labels(type=d.get("type", "unknown")).inc()
        docs.append(d)

    if docs:
        await db["events"].insert_many(docs)

    # Best-effort health scoring + anomaly detection + alerting on every
    # ingest, scoped to this batch's server. Never blocks/fails the ingest
    # response -- observability plumbing must not become a new source of
    # failures for the very thing it's observing.
    try:
        await _score_and_alert(batch.server_id)
    except Exception:
        pass

    return {"accepted": len(docs), "dropped_reported": batch.dropped_since_last_flush}


async def _score_and_alert(server_id: str, window_minutes: int = 60) -> None:
    db = get_db()
    since = time.time() - window_minutes * 60

    cursor = db["events"].find({"server_id": server_id, "ts": {"$gte": since}})
    total_calls = 0
    error_count = 0
    silent_failure_count = 0
    latencies: list[float] = []
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
    p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else None

    health = compute_health_score(
        total_calls=total_calls,
        error_count=error_count,
        silent_failure_count=silent_failure_count,
        p95_latency_ms=p95,
        cpu_samples=cpu_samples,
        mem_samples=mem_samples,
        classified_severities=severities,
    )

    await db["servers"].update_one(
        {"server_id": server_id},
        {"$set": {"latest_health": health, "latest_health_at": time.time()}},
    )
    await maybe_alert_health(server_id, health)

    anomaly_report = await detect_anomalies(server_id, window_minutes=15)
    await maybe_alert_anomalies(server_id, anomaly_report)
