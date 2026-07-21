from __future__ import annotations

"""
mcp_insight ingestion health scoring engine.

Combines message-level signals (error rate, silent-failure rate, latency),
process-level signals (CPU/memory pressure), and taxonomy-weighted fault
severity (from the classifier) into a single 0-100 health score per server.

This is intentionally a transparent, hand-tunable weighted formula rather
than a learned model -- the weights are documented inline so they can be
adjusted as real-world data comes in.
"""

LATENCY_WARN_MS = 2000.0
LATENCY_CRITICAL_MS = 8000.0
CPU_WARN_PCT = 80.0
MEM_GROWTH_WARN_RATIO = 1.5  # last sample vs first sample in window

_SEVERITY_WEIGHT = {"minor": 0.5, "major": 1.5, "critical": 3.0}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _latency_penalty(p95_latency_ms: float | None) -> float:
    if p95_latency_ms is None:
        return 0.0
    if p95_latency_ms <= LATENCY_WARN_MS:
        return 0.0
    if p95_latency_ms >= LATENCY_CRITICAL_MS:
        return 15.0
    frac = (p95_latency_ms - LATENCY_WARN_MS) / (LATENCY_CRITICAL_MS - LATENCY_WARN_MS)
    return 15.0 * frac


def _process_penalty(cpu_samples: list[float], mem_samples: list[int]) -> float:
    penalty = 0.0
    if cpu_samples:
        avg_cpu = sum(cpu_samples) / len(cpu_samples)
        if avg_cpu > CPU_WARN_PCT:
            penalty += min(10.0, (avg_cpu - CPU_WARN_PCT) / 2.0)
    if len(mem_samples) >= 2 and mem_samples[0] > 0:
        ratio = mem_samples[-1] / mem_samples[0]
        if ratio > MEM_GROWTH_WARN_RATIO:
            penalty += min(10.0, (ratio - MEM_GROWTH_WARN_RATIO) * 10.0)
    return penalty


def _severity_penalty(classified_severities: list[str]) -> float:
    total = sum(_SEVERITY_WEIGHT.get(sev, 0.5) for sev in classified_severities)
    return min(20.0, total)


def compute_health_score(
    total_calls: int,
    error_count: int,
    silent_failure_count: int,
    p95_latency_ms: float | None,
    cpu_samples: list[float],
    mem_samples: list[int],
    classified_severities: list[str],
) -> dict:
    """Returns {"score": float, "breakdown": {...}} -- the breakdown makes
    the score auditable instead of a black box."""
    breakdown: dict[str, float] = {}

    error_rate = (error_count / total_calls) if total_calls else 0.0
    silent_rate = (silent_failure_count / total_calls) if total_calls else 0.0

    breakdown["error_rate_penalty"] = round(error_rate * 40.0, 2)
    breakdown["silent_failure_penalty"] = round(silent_rate * 35.0, 2)
    breakdown["latency_penalty"] = round(_latency_penalty(p95_latency_ms), 2)
    breakdown["process_penalty"] = round(_process_penalty(cpu_samples, mem_samples), 2)
    breakdown["severity_penalty"] = round(_severity_penalty(classified_severities), 2)

    score = 100.0 - sum(breakdown.values())
    score = _clamp(score)

    if score >= 90:
        status = "healthy"
    elif score >= 70:
        status = "degraded"
    elif score >= 40:
        status = "unhealthy"
    else:
        status = "critical"

    return {"score": round(score, 2), "status": status, "breakdown": breakdown}
