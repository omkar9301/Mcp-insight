import time

import pytest
from fastapi import HTTPException

from app.routes import feedback as feedback_module
from .conftest import WritableFakeDB


@pytest.mark.asyncio
async def test_submit_feedback_records_on_matching_event(monkeypatch):
    db = WritableFakeDB()
    ts = time.time()
    await db["events"].insert_one({"server_id": "s1", "ts": ts, "classification": {"category": "Tool", "subcategory": "Tool Execution"}})
    monkeypatch.setattr(feedback_module, "get_db", lambda: db)

    req = feedback_module.FeedbackRequest(correct=False, note="wrong category")
    result = await feedback_module.submit_feedback("s1", ts, req)

    assert result["recorded"] is True
    stored = db._collections["events"]._docs[0]
    assert stored["classification_feedback"] == {"correct": False, "note": "wrong category"}


@pytest.mark.asyncio
async def test_submit_feedback_404_when_no_matching_event(monkeypatch):
    db = WritableFakeDB()
    monkeypatch.setattr(feedback_module, "get_db", lambda: db)

    with pytest.raises(HTTPException) as exc:
        await feedback_module.submit_feedback("s1", 12345.0, feedback_module.FeedbackRequest(correct=True))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_classification_accuracy_rolls_up_by_subcategory(monkeypatch):
    db = WritableFakeDB()
    await db["events"].insert_one({
        "server_id": "s1", "ts": 1, "classification": {"category": "Tool", "subcategory": "Tool Execution"},
        "classification_feedback": {"correct": True},
    })
    await db["events"].insert_one({
        "server_id": "s1", "ts": 2, "classification": {"category": "Tool", "subcategory": "Tool Execution"},
        "classification_feedback": {"correct": False},
    })
    await db["events"].insert_one({"server_id": "s1", "ts": 3, "classification": {"category": "Tool", "subcategory": "Tool Execution"}})
    monkeypatch.setattr(feedback_module, "get_db", lambda: db)

    result = await feedback_module.classification_accuracy(limit_per_subcategory=1000)
    row = result["rows"][0]
    assert row["correct"] == 1
    assert row["incorrect"] == 1
    assert row["accuracy"] == 0.5
