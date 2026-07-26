from __future__ import annotations

"""
mcp_insight ingestion AI advisory.

On-demand, per-event root-cause analysis: given one captured fault event
(method, error/violation detail, latency, classification), asks an LLM to
explain what's actually happening -- which layer of the MCP stack it
traces to, why it likely happened, and what to change -- grounded only in
data this platform actually captured for that event. Optional: if
ANTHROPIC_API_KEY isn't set, the endpoint reports itself as unconfigured
rather than failing.

Deliberately does NOT fabricate a request/response payload trace: the
wrapper never sends full tool call arguments or results to ingestion (by
design -- see buffer.py/interceptor.py, only violation summaries and
metadata are captured, to avoid shipping potentially sensitive payloads
off the wrapped server by default). The advisory is explicit about
exactly what data it had to work with, instead of inventing detail that
was never actually observed.
"""
import json
import logging

import httpx

from .config import settings

_log = logging.getLogger("mcp_insight.ingestion.advisory")

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=20.0)
    return _client


async def aclose_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _describe_event(event: dict) -> str:
    lines = [
        f"type: {event.get('type')}",
        f"method: {event.get('method', 'unknown')}",
        f"latency_ms: {event.get('latency_ms')}",
        f"is_error: {event.get('is_error', False)}",
        f"silent_failure: {event.get('silent_failure', False)}",
    ]
    if event.get("error"):
        lines.append(f"error: {json.dumps(event['error'])}")
    if event.get("schema_violation"):
        sv = event["schema_violation"]
        lines.append(f"tool: {sv.get('tool', 'unknown')}")
        lines.append(f"schema_violation: {sv.get('violation')}")
        lines.append(f"violation_path: {sv.get('path')}")
    if event.get("subtype"):
        lines.append(f"protocol_violation_subtype: {event['subtype']}")
    if event.get("raw_preview"):
        lines.append(f"raw_stdout_preview: {event['raw_preview'][:200]}")
    classification = event.get("classification")
    if classification:
        lines.append(
            f"taxonomy_classification: {classification.get('category')} / "
            f"{classification.get('subcategory')} "
            f"(severity={classification.get('dominant_severity')}, "
            f"effort={classification.get('dominant_effort')})"
        )
    return "\n".join(lines)


_PROMPT_TEMPLATE = """You are an expert in the Model Context Protocol (MCP) helping a developer \
debug a captured fault from a live MCP server, observed by a transparent traffic-monitoring wrapper.

Captured event data (this is ALL the data available -- the wrapper does not capture full tool \
call arguments or results by default, only metadata and violation summaries, so do not invent \
specific input/output values that aren't listed below):
{event_description}

Respond with ONLY a JSON object with these exact keys:
- "summary": one or two sentences on what went wrong, in plain language.
- "root_cause": your best-supported explanation of why this likely happened, reasoning through \
the MCP request/response lifecycle (transport -> protocol parsing -> handler/tool execution -> \
result serialization -> schema validation) and pointing at which layer this traces to. If \
something looks like a token/context-length issue, a prompt/response truncation issue, or an \
embedding/vector-retrieval issue upstream of the tool call, say so explicitly -- otherwise say \
plainly that nothing in the captured data points to those causes.
- "solution": concrete, specific steps a developer could take to fix this, tied to the actual \
data given (not generic advice).
- "data_available": a short note on exactly what data this analysis is grounded in (list the \
fields actually present), so the reader knows what's fact vs. inference.
- "confidence": one of "high", "medium", "low" -- how confident you are given how much data was \
actually available.
"""


async def generate_advisory(event: dict) -> dict | None:
    """Returns a structured advisory dict, or None if unconfigured/failed.
    Never raises -- the caller decides how to report "not configured" vs.
    a transient failure."""
    if not settings.anthropic_api_key:
        return None

    prompt = _PROMPT_TEMPLATE.format(event_description=_describe_event(event))
    try:
        resp = await _get_client().post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": settings.anthropic_advisory_model,
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        body = resp.json()
        raw = body["content"][0]["text"]
        parsed = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        return {
            "summary": parsed.get("summary"),
            "root_cause": parsed.get("root_cause"),
            "solution": parsed.get("solution"),
            "data_available": parsed.get("data_available"),
            "confidence": parsed.get("confidence"),
        }
    except httpx.HTTPStatusError as e:
        # Surfaces exactly the failure mode that bit us during testing: a
        # misconfigured/invalid ANTHROPIC_ADVISORY_MODEL fails silently
        # into a bare 502 with zero trace unless this is logged.
        _log.warning(
            "advisory_http_error",
            extra={"extra_fields": {
                "status_code": e.response.status_code,
                "model": settings.anthropic_advisory_model,
                "body": e.response.text[:300],
            }},
        )
        return None
    except Exception:
        _log.warning(
            "advisory_generation_failed",
            exc_info=True,
            extra={"extra_fields": {"model": settings.anthropic_advisory_model}},
        )
        return None
