"""
mcp_insight.proxy

HTTP/SSE reverse proxy for Streamable-HTTP-transport MCP servers (the "C2"
approach from the architecture doc). Same zero-code-change guarantee as
the stdio wrapper: point your MCP client at this proxy's URL instead of
the real server's URL, and every JSON-RPC message flowing either
direction -- plain JSON responses or an SSE event stream -- is tapped and
forwarded byte-for-byte, unmodified, to its real destination.

Usage:
    mcp-insight proxy --server-id my-server --target http://localhost:9000 \\
        --listen-host 0.0.0.0 --listen-port 8787 \\
        --ingestion-url http://localhost:8000
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from typing import Any, AsyncIterator, Optional

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route

from .capture import CapturedMessage, PendingRequestTracker
from .interceptor import Interceptor
from .metrics import ProcessMetricsSidecar

# Headers that must never be blindly forwarded between hops.
_HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "content-length", "host",
}


def _filtered_headers(headers) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in _HOP_BY_HOP}


def _each_json_message(body: bytes) -> list[dict]:
    """A JSON-RPC HTTP body is either one message or a JSON-RPC batch
    (a JSON array of messages). Normalize to a list."""
    if not body or not body.strip():
        return []
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, list):
        return [m for m in parsed if isinstance(m, dict)]
    if isinstance(parsed, dict):
        return [parsed]
    return []


def _tap_json_messages(interceptor: Interceptor, direction: str, body: bytes) -> None:
    messages = _each_json_message(body)
    if not messages and body and body.strip():
        # Non-empty body that isn't valid/parseable JSON-RPC at all.
        interceptor.handle_message(CapturedMessage(direction=direction, raw=body.decode("utf-8", "replace"), parsed=None))
        return
    for m in messages:
        interceptor.handle_message(CapturedMessage(direction=direction, raw=json.dumps(m), parsed=m))


class SSETapper:
    """Wraps an upstream SSE byte stream: forwards every chunk to the real
    client unmodified while incrementally parsing `data: ...` lines out of
    complete SSE events to tap them as server_to_client JSON-RPC messages."""

    def __init__(self, interceptor: Interceptor) -> None:
        self.interceptor = interceptor
        self._buffer = ""

    def feed(self, chunk: bytes) -> None:
        self._buffer += chunk.decode("utf-8", errors="replace")
        while "\n\n" in self._buffer:
            raw_event, self._buffer = self._buffer.split("\n\n", 1)
            data_lines = [
                line[len("data:"):].lstrip() for line in raw_event.split("\n")
                if line.startswith("data:")
            ]
            if not data_lines:
                continue
            data = "\n".join(data_lines)
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                self.interceptor.handle_message(
                    CapturedMessage(direction="server_to_client", raw=data, parsed=parsed)
                )
            elif isinstance(parsed, list):
                for m in parsed:
                    if isinstance(m, dict):
                        self.interceptor.handle_message(
                            CapturedMessage(direction="server_to_client", raw=json.dumps(m), parsed=m)
                        )


def build_app(interceptor: Interceptor, target_base_url: str, upstream_client: httpx.AsyncClient) -> Starlette:
    async def proxy_all(request: Request) -> Response:
        body = await request.body()
        _tap_json_messages(interceptor, "client_to_server", body)

        target_url = target_base_url + request.url.path
        if request.url.query:
            target_url += f"?{request.url.query}"

        upstream_req = upstream_client.build_request(
            request.method,
            target_url,
            headers=_filtered_headers(request.headers),
            content=body,
        )
        upstream_resp = await upstream_client.send(upstream_req, stream=True)

        content_type = upstream_resp.headers.get("content-type", "")

        if "text/event-stream" in content_type:
            tapper = SSETapper(interceptor)

            async def sse_body() -> AsyncIterator[bytes]:
                try:
                    async for chunk in upstream_resp.aiter_bytes():
                        if chunk:
                            tapper.feed(chunk)
                            yield chunk
                finally:
                    await upstream_resp.aclose()

            return StreamingResponse(
                sse_body(),
                status_code=upstream_resp.status_code,
                headers=_filtered_headers(upstream_resp.headers),
                media_type=content_type,
            )

        # Plain (non-streaming) response: buffer fully, tap, forward.
        resp_body = await upstream_resp.aread()
        await upstream_resp.aclose()
        _tap_json_messages(interceptor, "server_to_client", resp_body)
        return Response(
            content=resp_body,
            status_code=upstream_resp.status_code,
            headers=_filtered_headers(upstream_resp.headers),
            media_type=content_type or None,
        )

    return Starlette(routes=[Route("/{path:path}", proxy_all, methods=["GET", "POST", "DELETE", "PUT"])])


async def run_proxy(
    server_id: str,
    target: str,
    listen_host: str,
    listen_port: int,
    ingestion_url: str,
    api_key: str,
) -> None:
    interceptor = Interceptor(server_id=server_id, ingestion_url=ingestion_url, api_key=api_key)
    upstream_client = httpx.AsyncClient(timeout=None)

    app = build_app(interceptor, target.rstrip("/"), upstream_client)

    buffer_task = asyncio.create_task(interceptor.buffer.run())

    config = uvicorn.Config(app, host=listen_host, port=listen_port, log_level="info")
    server = uvicorn.Server(config)

    try:
        await server.serve()
    finally:
        await interceptor.buffer.stop()
        buffer_task.cancel()
        # See cli.run()'s shutdown for why this await matters: cancelling
        # alone doesn't let the buffer's final flush actually complete.
        await asyncio.gather(buffer_task, return_exceptions=True)
        await upstream_client.aclose()


def add_proxy_subcommand(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("proxy", help="Run an HTTP/SSE reverse proxy in front of a Streamable-HTTP MCP server")
    p.add_argument("--server-id", required=True, help="Stable identifier for this server in the dashboard")
    p.add_argument("--target", required=True, help="Base URL of the real MCP server, e.g. http://localhost:9000")
    p.add_argument("--listen-host", default=os.environ.get("MCP_INSIGHT_LISTEN_HOST", "0.0.0.0"))
    p.add_argument("--listen-port", type=int, default=int(os.environ.get("MCP_INSIGHT_LISTEN_PORT", "8787")))
    p.add_argument(
        "--ingestion-url",
        default=os.environ.get("MCP_INSIGHT_INGESTION_URL", "http://localhost:8000"),
    )
    p.add_argument("--api-key", default=os.environ.get("MCP_INSIGHT_API_KEY", ""))
