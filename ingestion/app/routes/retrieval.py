from __future__ import annotations

"""
mcp_insight ingestion retrieval-tool quality endpoints.

Aggregates the best-effort retrieval signal the wrapper attaches to
tools/call events for tools that heuristically look like vector/RAG
retrieval (see wrapper/mcp_insight/retrieval_signals.py). This is
inference from the outside, not ground truth -- the wrapper never sees
whether a tool actually queried a vector DB, only whether its result
*looks like* one (a list of items, optionally with score/similarity
fields). Tools that don't match the heuristic simply never show up here.
"""
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import require_api_key
from ..db import get_db
from ..rate_limit import enforce_read_rate_limit

router = APIRouter(dependencies=[Depends(require_api_key), Depends(enforce_read_rate_limit)])


def _summarize(docs: list[dict]) -> dict:
    total = len(docs)
    empty_count = sum(1 for d in docs if d["retrieval"].get("empty"))
    result_counts = [d["retrieval"]["result_count"] for d in docs if "result_count" in d["retrieval"]]
    top_scores = [d["retrieval"]["top_score"] for d in docs if "top_score" in d["retrieval"]]
    latencies = [d["latency_ms"] for d in docs if d.get("latency_ms") is not None]

    return {
        "total_calls": total,
        "empty_result_count": empty_count,
        "empty_result_rate": (empty_count / total) if total else 0.0,
        "avg_result_count": (sum(result_counts) / len(result_counts)) if result_counts else None,
        "avg_top_score": (sum(top_scores) / len(top_scores)) if top_scores else None,
        "worst_top_score": min(top_scores) if top_scores else None,
        "avg_latency_ms": (sum(latencies) / len(latencies)) if latencies else None,
        "last_seen": max(d["ts"] for d in docs) if docs else None,
    }


@router.get("/v1/servers/{server_id}/retrieval-tools")
async def server_retrieval_tools(server_id: str, window_minutes: int = Query(1440, ge=1, le=43200)):
    db = get_db()
    server = await db["servers"].find_one({"server_id": server_id})
    if server is None:
        raise HTTPException(status_code=404, detail="Unknown server_id -- no events received yet")

    since = time.time() - window_minutes * 60
    cursor = db["events"].find({
        "server_id": server_id,
        "retrieval": {"$exists": True},
        "ts": {"$gte": since},
    })

    by_tool: dict[str, list[dict]] = defaultdict(list)
    async for doc in cursor:
        by_tool[doc.get("tool_name", "unknown")].append(doc)

    tools = [{"tool_name": name, **_summarize(docs)} for name, docs in by_tool.items()]
    tools.sort(key=lambda t: t["empty_result_rate"], reverse=True)

    return {"server_id": server_id, "window_minutes": window_minutes, "tools": tools}


@router.get("/v1/retrieval-tools")
async def fleet_retrieval_tools(window_minutes: int = Query(1440, ge=1, le=43200)):
    """Fleet-wide: every (server, tool) pair that's ever looked like a
    retrieval tool, ranked by empty-result rate -- the tools most likely
    to be silently failing to retrieve anything useful."""
    db = get_db()
    since = time.time() - window_minutes * 60
    cursor = db["events"].find({"retrieval": {"$exists": True}, "ts": {"$gte": since}})

    by_key: dict[tuple, list[dict]] = defaultdict(list)
    async for doc in cursor:
        key = (doc.get("server_id", "unknown"), doc.get("tool_name", "unknown"))
        by_key[key].append(doc)

    rows = [
        {"server_id": server_id, "tool_name": tool_name, **_summarize(docs)}
        for (server_id, tool_name), docs in by_key.items()
    ]
    rows.sort(key=lambda t: t["empty_result_rate"], reverse=True)

    return {"window_minutes": window_minutes, "rows": rows}
