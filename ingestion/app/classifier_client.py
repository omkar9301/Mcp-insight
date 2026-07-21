from __future__ import annotations

from typing import Any, Optional

import httpx

from .config import settings

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


def describe_fault(event: dict) -> Optional[str]:
    """Builds a free-text description of a fault event suitable for the
    classifier's TF-IDF matcher. Returns None for events that aren't
    fault-shaped (nothing to classify)."""
    if event.get("silent_failure"):
        violation = event.get("schema_violation") or {}
        return (
            f"tool {violation.get('tool', event.get('method', 'unknown'))} call "
            f"returned success but the result violated its declared schema: "
            f"{violation.get('violation', 'schema mismatch')}"
        )

    if event.get("is_error"):
        error = event.get("error") or {}
        return (
            f"method {event.get('method', 'unknown')} call failed with "
            f"error code {error.get('code', 'unknown')}: {error.get('message', '')}"
        )

    if event.get("type") == "protocol_violation":
        subtype = event.get("subtype", "unknown")
        return f"protocol violation ({subtype}): non-JSON-RPC data on the transport stream"

    return None


async def classify_fault(text: str) -> Optional[dict]:
    """Calls the classifier service; best-effort -- returns None on any
    failure so a classifier outage never blocks event ingestion."""
    try:
        headers = {"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}
        resp = await _get_client().post(
            f"{settings.classifier_url}/v1/classify",
            json={"text": text, "top_k": 1},
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results") or []
        if not results:
            return None
        top = results[0]
        return {
            "category": top["category"],
            "subcategory": top["subcategory"],
            "confidence": top["confidence"],
            "dominant_severity": top.get("dominant_severity"),
            "dominant_effort": top.get("dominant_effort"),
            "low_confidence": data.get("low_confidence", False),
        }
    except Exception:
        return None


async def classify_event(event: dict) -> Optional[dict]:
    text = describe_fault(event)
    if text is None:
        return None
    return await classify_fault(text)
