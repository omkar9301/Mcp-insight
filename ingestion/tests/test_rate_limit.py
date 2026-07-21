import pytest
from fastapi import HTTPException

from app.rate_limit import SlidingWindowLimiter, enforce_ingest_rate_limit
from app.config import settings


def test_sliding_window_allows_up_to_max():
    limiter = SlidingWindowLimiter(max_requests=3, window_s=60)
    assert limiter.check("a") is True
    assert limiter.check("a") is True
    assert limiter.check("a") is True
    assert limiter.check("a") is False


def test_sliding_window_is_per_key():
    limiter = SlidingWindowLimiter(max_requests=1, window_s=60)
    assert limiter.check("a") is True
    assert limiter.check("b") is True  # separate key, separate budget
    assert limiter.check("a") is False


def test_sliding_window_expires_old_hits():
    limiter = SlidingWindowLimiter(max_requests=1, window_s=0.05)
    assert limiter.check("a") is True
    assert limiter.check("a") is False
    import time

    time.sleep(0.1)
    assert limiter.check("a") is True


def test_enforce_ingest_rate_limit_raises_429(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_ingest_per_minute", 1)
    import app.rate_limit as rl

    monkeypatch.setattr(rl, "_ingest_limiter", rl.SlidingWindowLimiter(max_requests=1, window_s=60))

    enforce_ingest_rate_limit("srv-x")  # first call ok
    with pytest.raises(HTTPException) as exc:
        enforce_ingest_rate_limit("srv-x")
    assert exc.value.status_code == 429
