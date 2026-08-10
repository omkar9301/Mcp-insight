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
import re

import httpx

from .config import settings

_log = logging.getLogger("mcp_insight.ingestion.advisory")


def _extract_json(raw: str) -> dict:
    """Robustly pulls a JSON object out of an LLM response. Naive
    `raw[raw.index("{"): raw.rindex("}")+1]` slicing (the original
    approach here) breaks on longer, multi-field responses whenever the
    text contains a `}` inside a string value that happens to be the
    last one, or the model wraps the JSON in a ```json fence -- both
    happened in practice with the longer Lost-in-the-Middle report
    prompt. Tries, in order: the whole response as-is, stripped of a
    markdown code fence, then a proper brace-balance scan (not just
    first/last index) as a last resort."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    start = raw.index("{")
    depth = 0
    in_string = False
    escaped = False
    for i, ch in enumerate(raw[start:], start=start):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(raw[start:i + 1])
    raise ValueError("no balanced JSON object found in response")

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        # 45s: the Lost-in-the-Middle deep-dive prompt asks for a much
        # longer, multi-section response (up to 2200 output tokens) than
        # the generic fault advisory -- 20s was tuned for the shorter
        # one and timed out in practice on the longer one.
        _client = httpx.AsyncClient(timeout=45.0)
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


def _describe_litm_event(event: dict) -> str:
    signal = event.get("lost_in_middle") or {}
    lines = [
        f"tool_name: {event.get('tool_name', 'unknown')}",
        f"method: {event.get('method', 'unknown')}",
        f"latency_ms: {event.get('latency_ms')}",
        f"risk_factors_detected: {', '.join(signal.get('risk_factors') or [])}",
        f"result_count: {signal.get('result_count')}",
        f"approx_tokens_in_result: {signal.get('approx_tokens')}",
        f"size_zscore_vs_this_tools_own_history: {signal.get('z_size')}",
    ]
    retrieval = event.get("retrieval")
    if retrieval:
        lines.append(f"retrieval_top_score: {retrieval.get('top_score')}")
        lines.append(f"retrieval_avg_score: {retrieval.get('avg_score')}")
        lines.append(f"retrieval_min_score: {retrieval.get('min_score')}")
    return "\n".join(lines)


_LITM_PROMPT_TEMPLATE = """You are a senior RAG/LLM-systems engineer producing a deep, industry-grade \
incident report for a "Lost in the Middle" (LITM) context-degradation risk flagged on a live MCP \
(Model Context Protocol) server, observed by a transparent traffic-monitoring wrapper.

Background you should reason from: Liu et al., "Lost in the Middle: How Language Models Use Long \
Contexts" (TACL 2023/2024) established that LLM performance on tasks requiring use of retrieved \
information is highest when relevant content is at the very start or end of the context window, \
and degrades significantly -- sometimes below the model's no-context baseline -- when relevant \
content is placed in the middle of a long context. This effect gets worse as context length and \
retrieved-item count grow, and worse still when results aren't ranked by relevance before insertion.

Captured signal (this is ALL the data available -- the wrapper does not capture full tool call \
arguments or the raw retrieved content by design, only metadata and derived risk signals, so do \
not invent specific content that isn't listed below):
{event_description}

Produce a maximally detailed, practitioner-grade report. Respond with ONLY a JSON object with \
these exact keys:
- "summary": one or two sentences on what was flagged and why it matters.
- "when": what about the TIMING/pattern of this call is relevant (e.g. a repeated query shortly \
after a large prior result implies the model likely re-asked because it didn't find what it \
needed the first time; a one-off large result is a different risk profile than a chronic pattern).
- "where": which specific LAYER of the retrieval/context pipeline this traces to -- one or more of: \
query formulation, retrieval/ranking (top-k selection, similarity search), context assembly \
(ordering/concatenation of retrieved chunks into the prompt), or downstream prompt construction. \
Be specific about which layer based on the actual risk factors present.
- "how": the MECHANISM -- concretely, how does this risk factor (large result count / unranked \
ordering / oversized response / repeated query) actually increase the chance the model fails to \
use relevant information, referencing the U-shaped attention/performance curve from the research.
- "why": the ROOT CAUSE -- your best-supported explanation of why the retrieval/context pipeline \
produced this shape (e.g. top-k set too high without a reranking step, no relevance-score \
threshold filtering out weak matches, no post-retrieval reordering, missing deduplication/\
compression before context assembly). Be specific to the actual signal data given, not generic.
- "prevention": an array of 4-8 concrete, named, industry-standard mitigation techniques ordered \
by expected impact, e.g. reranking retrieved results with a cross-encoder before context assembly, \
reducing top-k to a curated few highly-relevant items instead of a large unranked set, Maximal \
Marginal Relevance (MMR) for diversity-aware selection, reordering so the most relevant items sit \
at the start and end of the context (not the middle) per the LITM finding itself, setting a \
minimum relevance-score threshold to filter weak matches, contextual compression/summarization of \
retrieved chunks before insertion, hybrid search (lexical + vector) to improve initial ranking \
quality, query rewriting/decomposition for repeated-query patterns, and RAG evaluation tooling \
(e.g. RAGAS, TruLens) to catch this class of regression before production. Tailor which of these \
you recommend to the actual risk factors present, don't list all of them if only one factor fired.
- "industry_references": an array of 2-5 short strings naming the real technique or paper each \
prevention item is grounded in (e.g. "Liu et al. 2023, Lost in the Middle (TACL)", "cross-encoder \
reranking (e.g. Cohere Rerank, BGE-reranker)", "Maximal Marginal Relevance, Carbonell & Goldstein 1998").
- "data_available": a short note on exactly what data this analysis is grounded in.
- "confidence": one of "high", "medium", "low" -- how confident you are given how much data was \
actually available (a single flagged call is lower-confidence than a chronic per-tool pattern).
"""


async def generate_litm_advisory(event: dict) -> dict | None:
    """Deep-dive Lost-in-the-Middle advisory: when/where/how/why plus a
    ranked, named list of industry-standard prevention techniques.
    Structurally identical failure/logging handling to generate_advisory,
    just a different (much longer) prompt and response shape."""
    if not settings.anthropic_api_key:
        return None

    prompt = _LITM_PROMPT_TEMPLATE.format(event_description=_describe_litm_event(event))
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
                "max_tokens": 2200,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        body = resp.json()
        raw = body["content"][0]["text"]
        parsed = _extract_json(raw)
        return {
            "kind": "lost_in_middle",
            "summary": parsed.get("summary"),
            "when": parsed.get("when"),
            "where": parsed.get("where"),
            "how": parsed.get("how"),
            "why": parsed.get("why"),
            "prevention": parsed.get("prevention") or [],
            "industry_references": parsed.get("industry_references") or [],
            "data_available": parsed.get("data_available"),
            "confidence": parsed.get("confidence"),
        }
    except httpx.HTTPStatusError as e:
        _log.warning(
            "litm_advisory_http_error",
            extra={"extra_fields": {
                "status_code": e.response.status_code,
                "model": settings.anthropic_advisory_model,
                "body": e.response.text[:300],
            }},
        )
        return None
    except Exception:
        _log.warning(
            "litm_advisory_generation_failed",
            exc_info=True,
            extra={"extra_fields": {"model": settings.anthropic_advisory_model}},
        )
        return None


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
        parsed = _extract_json(raw)
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
