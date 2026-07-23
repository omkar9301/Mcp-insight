from __future__ import annotations

"""
mcp_insight ingestion classification feedback.

A thumbs up/down loop for auto-classified faults: lets an operator mark
whether the classifier's pick was right. Stored on the event itself so
it's visible next to the classification in the dashboard, and aggregable
later (e.g. "which subcategories does the classifier get wrong most
often") without a separate reporting pipeline.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth import require_api_key
from ..db import get_db
from ..rate_limit import enforce_read_rate_limit

router = APIRouter(dependencies=[Depends(require_api_key), Depends(enforce_read_rate_limit)])


class FeedbackRequest(BaseModel):
    correct: bool
    note: str | None = None


@router.post("/v1/servers/{server_id}/events/{ts}/feedback")
async def submit_feedback(server_id: str, ts: float, req: FeedbackRequest):
    db = get_db()
    result = await db["events"].update_one(
        {"server_id": server_id, "ts": ts},
        {"$set": {"classification_feedback": {"correct": req.correct, "note": req.note}}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="No event found for that server_id/ts")
    return {"server_id": server_id, "ts": ts, "recorded": True}


@router.get("/v1/stats/classification-accuracy")
async def classification_accuracy(limit_per_subcategory: int = Query(1000, ge=1, le=10000)):
    """Rolls up recorded feedback per taxonomy subcategory -- how often
    the classifier's pick has been confirmed vs. flagged wrong, where
    feedback exists. Subcategories with no feedback yet aren't included."""
    db = get_db()
    cursor = db["events"].find({"classification_feedback": {"$exists": True}})

    from collections import defaultdict
    tally: dict[tuple, dict] = defaultdict(lambda: {"correct": 0, "incorrect": 0})
    async for doc in cursor:
        c = doc.get("classification") or {}
        key = (c.get("category", "unknown"), c.get("subcategory", "unknown"))
        if doc["classification_feedback"]["correct"]:
            tally[key]["correct"] += 1
        else:
            tally[key]["incorrect"] += 1

    rows = []
    for (cat, sub), counts in tally.items():
        total = counts["correct"] + counts["incorrect"]
        rows.append({
            "category": cat,
            "subcategory": sub,
            "correct": counts["correct"],
            "incorrect": counts["incorrect"],
            "accuracy": round(counts["correct"] / total, 3) if total else None,
        })
    return {"rows": rows}
