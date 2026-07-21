from __future__ import annotations

"""
mcp_insight ingestion alerting service.

Sends Slack incoming-webhook notifications when a server's health score
drops below threshold or an anomaly is detected. Cooldowns are persisted
in Mongo (not just in-process memory) so a service restart doesn't cause
an alert storm, and so multiple ingestion replicas share one cooldown.
"""
import logging
import time

import httpx

from .config import settings
from .db import get_db
from .metrics_prom import ALERTS_SENT

_log = logging.getLogger("mcp_insight.ingestion.alerting")

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=3.0)
    return _client


async def aclose_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _cooldown_ok(server_id: str, alert_kind: str) -> bool:
    db = get_db()
    now = time.time()
    key = {"server_id": server_id, "alert_kind": alert_kind}
    doc = await db["alert_cooldowns"].find_one(key)
    if doc and (now - doc.get("last_sent_at", 0)) < settings.alert_cooldown_s:
        return False
    await db["alert_cooldowns"].update_one(
        key, {"$set": {"last_sent_at": now}}, upsert=True
    )
    return True


async def _send_slack(text: str, blocks: list[dict] | None = None) -> None:
    if not settings.slack_webhook_url:
        return
    payload: dict = {"text": text}
    if blocks:
        payload["blocks"] = blocks
    try:
        await _get_client().post(settings.slack_webhook_url, json=payload)
    except Exception:
        # Alerting must never crash the ingestion request path.
        _log.warning("slack_webhook_post_failed", extra={"extra_fields": {"text_preview": text[:120]}})


async def maybe_alert_health(server_id: str, health: dict) -> None:
    if health["score"] >= settings.alert_score_threshold:
        return
    if not await _cooldown_ok(server_id, "health_score"):
        return

    breakdown_lines = "\n".join(f"  - {k}: -{v}" for k, v in health["breakdown"].items())
    text = (
        f":rotating_light: *mcp-insight*: server `{server_id}` health is "
        f"*{health['status']}* (score {health['score']}/100)\n{breakdown_lines}"
    )
    ALERTS_SENT.labels(kind="health_score").inc()
    await _send_slack(text)


async def maybe_alert_anomalies(server_id: str, anomaly_report: dict) -> None:
    anomalies = anomaly_report.get("anomalies") or []
    if not anomalies:
        return
    if not await _cooldown_ok(server_id, "anomaly"):
        return

    lines = []
    for a in anomalies:
        if a["kind"] == "error_rate_spike":
            lines.append(
                f"  - error rate spike: {a['current']:.1%} (baseline avg {a['baseline']:.1%}, z={a['zscore']})"
            )
        elif a["kind"] == "latency_spike":
            lines.append(
                f"  - p95 latency spike: {a['current']:.0f}ms (baseline avg {a['baseline']:.0f}ms, z={a['zscore']})"
            )
    text = f":warning: *mcp-insight*: anomaly detected on server `{server_id}`\n" + "\n".join(lines)
    ALERTS_SENT.labels(kind="anomaly").inc()
    await _send_slack(text)
