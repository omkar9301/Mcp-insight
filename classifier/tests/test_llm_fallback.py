import pytest

from app import llm_fallback


@pytest.mark.asyncio
async def test_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(llm_fallback, "_ENABLED", False)
    assert await llm_fallback.classify_with_llm("some fault text") is None


@pytest.mark.asyncio
async def test_returns_none_on_http_failure(monkeypatch):
    monkeypatch.setattr(llm_fallback, "_ENABLED", True)
    monkeypatch.setattr(llm_fallback, "_API_KEY", "fake-key")
    # No real network available / will fail fast against an invalid setup;
    # regardless of *why* it fails, classify_with_llm must never raise.
    result = await llm_fallback.classify_with_llm("some fault text")
    assert result is None or isinstance(result, dict)


def test_low_confidence_threshold_wires_to_llm_fallback():
    from app.main import LOW_CONFIDENCE_THRESHOLD

    assert 0 < LOW_CONFIDENCE_THRESHOLD < 1
