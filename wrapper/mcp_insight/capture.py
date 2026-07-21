"""
mcp_insight.capture

Handles reading/writing newline-delimited JSON-RPC 2.0 messages over stdio,
tapping a copy of every message for observability without altering the
bytes that flow between the real MCP client and the real MCP server.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class CapturedMessage:
    direction: str          # "client_to_server" or "server_to_client"
    raw: str                # original line, forwarded unmodified
    parsed: Optional[dict]  # None if not valid JSON (still forwarded as-is)
    ts: float = field(default_factory=time.time)

    @property
    def method(self) -> Optional[str]:
        if self.parsed:
            return self.parsed.get("method")
        return None

    @property
    def msg_id(self) -> Optional[Any]:
        if self.parsed:
            return self.parsed.get("id")
        return None

    @property
    def is_response(self) -> bool:
        return bool(self.parsed) and ("result" in self.parsed or "error" in self.parsed) and "method" not in self.parsed


def parse_line(direction: str, line: str) -> CapturedMessage:
    """Parse one line of stdio traffic. Never raises -- malformed JSON is
    still forwarded untouched; we just can't inspect it."""
    line_stripped = line.rstrip("\n")
    parsed: Optional[dict] = None
    if line_stripped.strip():
        try:
            parsed = json.loads(line_stripped)
        except json.JSONDecodeError:
            parsed = None
    return CapturedMessage(direction=direction, raw=line, parsed=parsed)


class PendingRequestTracker:
    """Correlates requests with their eventual responses so we can compute
    per-call latency and match responses back to the tool/method that was
    invoked (the response itself usually doesn't carry the method name)."""

    def __init__(self) -> None:
        self._pending: dict[Any, dict] = {}

    def on_request(self, msg: CapturedMessage) -> None:
        if msg.parsed and msg.msg_id is not None and msg.method:
            self._pending[msg.msg_id] = {
                "method": msg.method,
                "params": msg.parsed.get("params"),
                "sent_at": msg.ts,
            }

    def on_response(self, msg: CapturedMessage) -> Optional[dict]:
        """Returns the matched request context (method, params, latency_ms)
        if this response correlates to a known request, else None."""
        if not msg.parsed or msg.msg_id is None:
            return None
        ctx = self._pending.pop(msg.msg_id, None)
        if ctx is None:
            return None
        latency_ms = (msg.ts - ctx["sent_at"]) * 1000.0
        return {
            "method": ctx["method"],
            "params": ctx["params"],
            "latency_ms": latency_ms,
            "is_error": "error" in msg.parsed,
            "result": msg.parsed.get("result"),
            "error": msg.parsed.get("error"),
        }
