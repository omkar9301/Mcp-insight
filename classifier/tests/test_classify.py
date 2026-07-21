import os

os.environ.setdefault("MCP_INSIGHT_API_KEY", "")  # auth disabled for these tests

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["categories_loaded"] == 27


def test_taxonomy_returns_all_categories():
    resp = client.get("/v1/taxonomy")
    assert resp.status_code == 200
    assert len(resp.json()["taxonomy"]) == 27


def test_classify_silent_failure_text_matches_tool_result_propagation():
    resp = client.post(
        "/v1/classify",
        json={"text": "tool call returned success but the result was missing a required field", "top_k": 3},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["results"]) == 3
    top = body["results"][0]
    assert top["subcategory"] == "Tool Result Propagation"
    assert top["confidence"] > 0.2


def test_classify_returns_low_confidence_for_unrelated_text():
    resp = client.post("/v1/classify", json={"text": "zzz qqq unrelated gibberish nonsense", "top_k": 1})
    body = resp.json()
    assert body["low_confidence"] is True


def test_classify_result_carries_severity_and_effort():
    resp = client.post("/v1/classify", json={"text": "missing required json-rpc id field", "top_k": 1})
    top = resp.json()["results"][0]
    assert top["dominant_severity"] in ("minor", "major", "critical")
    assert top["dominant_effort"] in ("low", "medium", "high")


def test_auth_rejects_missing_key_when_configured(monkeypatch):
    monkeypatch.setattr("app.main._API_KEY", "secret123")
    resp = client.post("/v1/classify", json={"text": "anything", "top_k": 1})
    assert resp.status_code == 401


def test_auth_accepts_correct_key(monkeypatch):
    monkeypatch.setattr("app.main._API_KEY", "secret123")
    resp = client.post(
        "/v1/classify",
        json={"text": "anything", "top_k": 1},
        headers={"Authorization": "Bearer secret123"},
    )
    assert resp.status_code == 200


def test_llm_fallback_prepended_when_low_confidence(monkeypatch):
    async def fake_llm(text):
        return {
            "category": "Tool", "subcategory": "Tool Execution", "confidence": None,
            "dominant_severity": "major", "dominant_effort": "medium",
            "practitioner_confirmed_pct": 73, "source": "llm",
        }

    monkeypatch.setattr("app.main.classify_with_llm", fake_llm)
    resp = client.post("/v1/classify", json={"text": "zzz qqq unrelated gibberish nonsense", "top_k": 1})
    body = resp.json()
    assert body["low_confidence"] is True
    assert body["results"][0]["source"] == "llm"
    assert body["results"][0]["subcategory"] == "Tool Execution"


def test_llm_fallback_not_called_when_confident(monkeypatch):
    called = False

    async def fake_llm(text):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr("app.main.classify_with_llm", fake_llm)
    client.post(
        "/v1/classify",
        json={"text": "tool call returned success but the result was missing a required field", "top_k": 1},
    )
    assert called is False


def test_rate_limit_returns_429_when_exceeded(monkeypatch):
    from app import main as main_module

    monkeypatch.setattr(main_module, "_RATE_LIMIT_PER_MINUTE", 2)
    from collections import defaultdict, deque

    monkeypatch.setattr(main_module, "_hits", defaultdict(deque))

    r1 = client.post("/v1/classify", json={"text": "a", "top_k": 1})
    r2 = client.post("/v1/classify", json={"text": "b", "top_k": 1})
    r3 = client.post("/v1/classify", json={"text": "c", "top_k": 1})

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
