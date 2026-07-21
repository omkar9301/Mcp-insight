from __future__ import annotations

"""
mcp_insight ingestion rate limiting.

A minimal in-memory sliding-window limiter -- no Redis dependency, because
this deployment is single-instance ingestion by design (see README). If
you run multiple ingestion replicas behind a load balancer, this limit is
per-replica, not global; move to a shared store (Redis) if you need a
true global limit under horizontal scaling.

Two limiters:
- per server_id, on `POST /v1/events` (protects against a single
  misbehaving/misconfigured wrapper flooding the backend)
- per client IP, on read endpoints (protects the dashboard's polling from
  becoming a self-inflicted DoS, and protects against abuse if this API is
  ever reachable beyond localhost)
"""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from .config import settings


class SlidingWindowLimiter:
    def __init__(self, max_requests: int, window_s: float) -> None:
        self.max_requests = max_requests
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> bool:
        now = time.time()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window_s:
            hits.popleft()
        if len(hits) >= self.max_requests:
            return False
        hits.append(now)
        return True


_ingest_limiter = SlidingWindowLimiter(
    max_requests=settings.rate_limit_ingest_per_minute, window_s=60.0
)
_read_limiter = SlidingWindowLimiter(
    max_requests=settings.rate_limit_read_per_minute, window_s=60.0
)


def enforce_ingest_rate_limit(server_id: str) -> None:
    if not _ingest_limiter.check(server_id):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for server_id={server_id} "
                   f"({settings.rate_limit_ingest_per_minute}/min)",
        )


def enforce_read_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    if not _read_limiter.check(client_ip):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded ({settings.rate_limit_read_per_minute}/min)",
        )
