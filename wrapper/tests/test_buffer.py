import asyncio

import pytest

from mcp_insight.buffer import EventBuffer


def test_put_is_synchronous_and_never_raises():
    buf = EventBuffer(ingestion_url="http://unreachable.invalid", server_id="s1", max_queue=3)
    for i in range(5):
        buf.put({"type": "rpc_call", "ts": i})
    # oldest-dropped semantics: deque(maxlen=3) silently evicts oldest itself
    assert len(buf._queue) == 3
    assert buf._dropped_count == 2


@pytest.mark.asyncio
async def test_flush_swallows_unreachable_ingestion_url():
    buf = EventBuffer(ingestion_url="http://127.0.0.1:1", server_id="s1", flush_interval_s=0.01)
    buf.put({"type": "rpc_call", "ts": 1})
    import httpx

    buf._client = httpx.AsyncClient(timeout=0.2)
    try:
        await buf._flush()  # must not raise even though nothing is listening
    finally:
        await buf._client.aclose()
    assert len(buf._queue) == 0  # popped into the batch regardless of send outcome
