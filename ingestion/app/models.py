from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class RawEvent(BaseModel):
    type: str
    ts: float
    # Fields below are optional because event `type` determines which apply
    method: Optional[str] = None
    latency_ms: Optional[float] = None
    is_error: Optional[bool] = None
    error: Optional[dict] = None
    silent_failure: Optional[bool] = None
    schema_violation: Optional[dict] = None
    subtype: Optional[str] = None
    raw_preview: Optional[str] = None
    # process_metrics fields
    cpu_percent: Optional[float] = None
    memory_rss_bytes: Optional[int] = None
    num_fds: Optional[int] = None
    num_threads: Optional[int] = None
    num_connections: Optional[int] = None


class EventBatch(BaseModel):
    server_id: str
    sent_at: float
    dropped_since_last_flush: int = 0
    events: list[RawEvent] = Field(default_factory=list)


class ServerHealthSummary(BaseModel):
    server_id: str
    window_minutes: int
    total_calls: int
    error_rate: float
    silent_failure_count: int
    p50_latency_ms: Optional[float]
    p95_latency_ms: Optional[float]
    dropped_events: int
    last_seen: Optional[float]
