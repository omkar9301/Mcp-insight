"""
mcp_insight.buffer

Non-blocking local event buffer. Real MCP traffic must NEVER wait on this --
if the ingestion API is slow or down, we drop events (oldest first) rather
than add latency or fail the underlying MCP session. This is the "fail-open"
requirement from the architecture doc.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any

import httpx


class EventBuffer:
    def __init__(
        self,
        ingestion_url: str,
        server_id: str,
        api_key: str = "",
        max_queue: int = 5000,
        flush_interval_s: float = 2.0,
        flush_batch_size: int = 200,
    ) -> None:
        self.ingestion_url = ingestion_url.rstrip("/")
        self.server_id = server_id
        self.api_key = api_key
        self.max_queue = max_queue
        self.flush_interval_s = flush_interval_s
        self.flush_batch_size = flush_batch_size

        self._queue: deque[dict] = deque(maxlen=max_queue)
        self._dropped_count = 0
        self._client: httpx.AsyncClient | None = None
        self._stop = False

    def put(self, event: dict) -> None:
        """Synchronous, O(1), never raises. Called from the hot path."""
        if len(self._queue) >= self.max_queue:
            self._dropped_count += 1
        self._queue.append(event)

    async def run(self) -> None:
        """Background task: periodically flush the queue to the ingestion API."""
        self._client = httpx.AsyncClient(timeout=5.0)
        try:
            while not self._stop:
                await asyncio.sleep(self.flush_interval_s)
                await self._flush()
        finally:
            await self._flush()  # best-effort final flush on shutdown
            await self._client.aclose()

    async def stop(self) -> None:
        self._stop = True

    async def _flush(self) -> None:
        if not self._queue:
            return
        batch = []
        while self._queue and len(batch) < self.flush_batch_size:
            batch.append(self._queue.popleft())

        payload = {
            "server_id": self.server_id,
            "sent_at": time.time(),
            "dropped_since_last_flush": self._dropped_count,
            "events": batch,
        }
        self._dropped_count = 0

        try:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            resp = await self._client.post(
                f"{self.ingestion_url}/v1/events", json=payload, headers=headers
            )
            resp.raise_for_status()
        except Exception:
            # Fail-open: ingestion being unreachable must never crash the
            # wrapper or the MCP session it's observing. We simply lose
            # this batch of observability data.
            pass
