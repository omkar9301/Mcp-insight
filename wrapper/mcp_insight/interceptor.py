"""
mcp_insight.interceptor

Transport-agnostic fault-detection core. Consumes `CapturedMessage`
objects -- it doesn't know or care whether they came from stdio pipes or
an HTTP/SSE reverse proxy, which is what lets both `cli.py` (C1, stdio)
and `proxy.py` (C2, Streamable HTTP) share one implementation of the
actual observability logic.
"""
from __future__ import annotations

from .buffer import EventBuffer
from .capture import CapturedMessage, PendingRequestTracker
from .schema_guard import SchemaGuard


class Interceptor:
    def __init__(self, server_id: str, ingestion_url: str, api_key: str) -> None:
        self.server_id = server_id
        self.buffer = EventBuffer(ingestion_url=ingestion_url, server_id=server_id, api_key=api_key)
        self.tracker = PendingRequestTracker()
        self.schema_guard = SchemaGuard()

    def handle_message(self, msg: CapturedMessage) -> None:
        if msg.parsed is None:
            # Non-JSON stdout/body noise from the server is itself a real,
            # taxonomy-recognized fault (transport contamination).
            if msg.direction == "server_to_client" and msg.raw.strip():
                self.buffer.put({
                    "type": "protocol_violation",
                    "subtype": "non_json_on_stdout",
                    "ts": msg.ts,
                    "raw_preview": msg.raw[:200],
                })
            return

        if msg.direction == "client_to_server":
            self.tracker.on_request(msg)
            if msg.method == "initialize":
                pass  # response handled below carries the capabilities
            return

        # server_to_client
        if msg.method == "initialize" or (msg.parsed.get("result") and "capabilities" in (msg.parsed.get("result") or {})):
            self.schema_guard.ingest_initialize_response(msg.parsed.get("result"))

        matched = self.tracker.on_response(msg)
        if matched is None:
            return

        event = {
            "type": "rpc_call",
            "ts": msg.ts,
            "method": matched["method"],
            "latency_ms": matched["latency_ms"],
            "is_error": matched["is_error"],
        }

        if matched["is_error"]:
            event["error"] = matched["error"]

        # Silent-failure check: only meaningful for tools/call results
        if matched["method"] == "tools/call" and not matched["is_error"]:
            params = matched.get("params") or {}
            tool_name = params.get("name")
            result = matched.get("result")
            if tool_name and result is not None:
                violation = self.schema_guard.check_tool_result(tool_name, result)
                if violation:
                    event["silent_failure"] = True
                    event["schema_violation"] = violation

        self.buffer.put(event)

    def on_process_metrics(self, sample: dict) -> None:
        self.buffer.put(sample)
