"""
mcp_insight.retrieval_signals

Best-effort detection of vector/RAG-style retrieval tools and lightweight
quality signals extracted from their results -- entirely heuristic, since
the wrapper only ever sees the MCP protocol boundary, never what happens
inside a tool handler (whether it actually queried a vector DB at all).

Deliberately extracts only small summary numbers (result count, score
min/max/avg) rather than shipping the raw result content -- consistent
with the rest of this wrapper's design: it never sends full tool
arguments or results to ingestion, only derived metadata.
"""
from __future__ import annotations

import re
from typing import Any, Optional

_RETRIEVAL_NAME_PATTERN = re.compile(
    r"search|retriev|lookup|\bquery\b|embed|vector|similar|\bfind\b|\bfetch\b|\brag\b",
    re.IGNORECASE,
)

# Common field names across vector DB / RAG tool conventions
# (Pinecone, Weaviate, Qdrant, LangChain retrievers, custom wrappers, ...).
_LIST_FIELD_NAMES = ("results", "matches", "documents", "docs", "items", "hits", "chunks")
_SCORE_FIELD_NAMES = ("score", "similarity", "relevance", "confidence")
_DISTANCE_FIELD_NAMES = ("distance", "dist")


def looks_like_retrieval_tool(tool_name: str, description: Optional[str]) -> bool:
    haystack = f"{tool_name or ''} {description or ''}"
    return bool(_RETRIEVAL_NAME_PATTERN.search(haystack))


def find_result_list(result: Any) -> Optional[list]:
    """Public: also used by lost_in_middle.py to look at result-set shape
    (count, score ordering) without re-implementing this detection."""
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for field in _LIST_FIELD_NAMES:
            val = result.get(field)
            if isinstance(val, list):
                return val
    return None


def extract_scores(items: list) -> list[float]:
    scores: list[float] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for field in _SCORE_FIELD_NAMES:
            val = item.get(field)
            if isinstance(val, (int, float)):
                scores.append(float(val))
                break
        else:
            # Fall back to distance metrics -- lower is better, so we
            # don't mix them into the same "score" (higher-is-better)
            # series, but still worth capturing separately if present.
            continue
    return scores


def extract_retrieval_signal(tool_name: str, description: Optional[str], result: Any) -> Optional[dict]:
    """Returns a small retrieval-quality summary if this tool looks like a
    retrieval tool AND its result looks like a result list, else None --
    no signal is attached (and nothing extra is sent) for ordinary tools."""
    if not looks_like_retrieval_tool(tool_name, description):
        return None

    items = find_result_list(result)
    if items is None:
        return None

    signal: dict = {"result_count": len(items), "empty": len(items) == 0}

    scores = extract_scores(items)
    if scores:
        signal["top_score"] = max(scores)
        signal["avg_score"] = sum(scores) / len(scores)
        signal["min_score"] = min(scores)

    return signal
