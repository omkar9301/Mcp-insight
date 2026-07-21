from __future__ import annotations

"""
mcp_insight ingestion anomaly & trend detector.

Statistical (rolling z-score) detection: buckets recent history into
equal-length windows, computes the mean/stddev of error rate and p95
latency across the historical buckets, then flags the current bucket if
it's an outlier (|z| >= threshold). This adapts to each server's own
normal variance instead of a fixed ratio-vs-previous-window heuristic --
a server that's naturally bursty won't false-positive on ordinary swings,
and a very stable server gets flagged on smaller relative changes.
"""
import math
import time

from .config import settings
from .db import get_db


def _p95(latencies: list[float]) -> float | None:
    if not latencies:
        return None
    latencies = sorted(latencies)
    idx = min(len(latencies) - 1, int(len(latencies) * 0.95))
    return latencies[idx]


def _bucket_stats(docs: list[dict]) -> dict:
    total = len(docs)
    errors = sum(1 for d in docs if d.get("is_error"))
    latencies = [d["latency_ms"] for d in docs if d.get("latency_ms") is not None]
    return {
        "total_calls": total,
        "error_rate": (errors / total) if total else 0.0,
        "p95_latency_ms": _p95(latencies),
    }


def _zscore(value: float, history: list[float]) -> float | None:
    if len(history) < 2:
        return None
    mean = sum(history) / len(history)
    variance = sum((x - mean) ** 2 for x in history) / len(history)
    stddev = math.sqrt(variance)
    if stddev == 0:
        # A perfectly flat history (e.g. always 0% errors) has no variance
        # to divide by -- any deviation at all is still a real anomaly, so
        # treat it as an extreme (but finite -- `Infinity` isn't valid JSON
        # and would break API consumers) z-score rather than "unknown".
        return None if value == mean else math.copysign(999.0, value - mean)
    return (value - mean) / stddev


async def detect_anomalies(server_id: str, window_minutes: int) -> dict:
    """Buckets the last `settings.anomaly_history_buckets + 1` windows of
    `window_minutes` each, treats the most recent as "current" and the
    rest as history, and z-scores current against that history."""
    db = get_db()
    now = time.time()
    window_s = window_minutes * 60
    n_buckets = settings.anomaly_history_buckets + 1
    lookback_start = now - window_s * n_buckets

    cursor = db["events"].find(
        {"server_id": server_id, "type": "rpc_call", "ts": {"$gte": lookback_start}}
    )
    all_docs = [doc async for doc in cursor]

    buckets: list[list[dict]] = [[] for _ in range(n_buckets)]
    for doc in all_docs:
        # Clamp: an event timestamped fractionally in the future (clock
        # skew between the wrapper and this service) must not overflow
        # the bucket index -- treat it as belonging to the current bucket.
        age_s = max(0.0, now - doc["ts"])
        bucket_offset = min(n_buckets - 1, int(age_s // window_s))
        idx = n_buckets - 1 - bucket_offset
        buckets[idx].append(doc)

    bucket_stats = [_bucket_stats(b) for b in buckets]
    current = bucket_stats[-1]
    history = bucket_stats[:-1]
    history_with_data = [b for b in history if b["total_calls"] > 0]

    anomalies: list[dict] = []

    if len(history_with_data) >= settings.anomaly_min_history_buckets:
        error_history = [b["error_rate"] for b in history_with_data]
        z = _zscore(current["error_rate"], error_history)
        if z is not None and z >= settings.anomaly_zscore_threshold and current["total_calls"] >= 5:
            anomalies.append({
                "kind": "error_rate_spike",
                "current": round(current["error_rate"], 4),
                "baseline": round(sum(error_history) / len(error_history), 4),
                "zscore": round(z, 2),
            })

        latency_history = [b["p95_latency_ms"] for b in history_with_data if b["p95_latency_ms"] is not None]
        if current["p95_latency_ms"] is not None and len(latency_history) >= settings.anomaly_min_history_buckets:
            z = _zscore(current["p95_latency_ms"], latency_history)
            if z is not None and z >= settings.anomaly_zscore_threshold:
                anomalies.append({
                    "kind": "latency_spike",
                    "current": round(current["p95_latency_ms"], 1),
                    "baseline": round(sum(latency_history) / len(latency_history), 1),
                    "zscore": round(z, 2),
                })

    baseline_summary = {
        "total_calls": sum(b["total_calls"] for b in history),
        "error_rate": (sum(b["error_rate"] for b in history_with_data) / len(history_with_data)) if history_with_data else 0.0,
        "p95_latency_ms": None,
    }

    return {
        "server_id": server_id,
        "window_minutes": window_minutes,
        "current": current,
        "baseline": baseline_summary,
        "history_buckets": len(history_with_data),
        "anomalies": anomalies,
    }
