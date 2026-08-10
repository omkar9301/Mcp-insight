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
from .lost_in_middle import LostInMiddleDetector
from .prompt_injection import PromptInjectionDetector
from .retrieval_signals import extract_retrieval_signal
from .schema_guard import SchemaGuard


class Interceptor:
    def __init__(self, server_id: str, ingestion_url: str, api_key: str) -> None:
        self.server_id = server_id
        self.buffer = EventBuffer(ingestion_url=ingestion_url, server_id=server_id, api_key=api_key)
        self.tracker = PendingRequestTracker()
        self.schema_guard = SchemaGuard()
        self.injection_detector = PromptInjectionDetector()
        self.lost_in_middle_detector = LostInMiddleDetector()
        self._last_tools_sent: dict | None = None
        self._descriptions_scanned: set[str] = set()

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

        # Some servers report their tool list via a dedicated `tools/list`
        # call instead of (or in addition to) inline in `initialize` --
        # capture that path too so the tool registry doesn't stay empty
        # for those servers.
        if matched["method"] == "tools/list" and not matched["is_error"]:
            result = matched.get("result") or {}
            tools = result.get("tools")
            if isinstance(tools, list):
                self.schema_guard.ingest_tools_list(tools)

        self._maybe_send_capabilities(msg.ts)

        event = {
            "type": "rpc_call",
            "ts": msg.ts,
            "method": matched["method"],
            "latency_ms": matched["latency_ms"],
            "is_error": matched["is_error"],
        }

        if matched["is_error"]:
            event["error"] = matched["error"]

        tool_name = None
        if matched["method"] == "tools/call":
            params = matched.get("params") or {}
            tool_name = params.get("name")

        # Silent-failure check: only meaningful for tools/call results
        if matched["method"] == "tools/call" and not matched["is_error"]:
            result = matched.get("result")
            if tool_name and result is not None:
                violation = self.schema_guard.check_tool_result(tool_name, result)
                if violation:
                    event["silent_failure"] = True
                    event["schema_violation"] = violation

                # Best-effort vector/RAG retrieval quality signal -- only
                # attached for tools that heuristically look like
                # retrieval tools AND whose result looks like a result
                # list; extracts small summary numbers only (never the
                # raw retrieved content), same privacy posture as the
                # rest of this wrapper.
                tool_meta = self.schema_guard.tools.get(tool_name, {})
                retrieval = extract_retrieval_signal(tool_name, tool_meta.get("description"), result)
                if retrieval:
                    event["retrieval"] = retrieval

                injection = self.injection_detector.scan_call_result(tool_name, result)
                if injection:
                    event["prompt_injection"] = injection

                # Lost-in-the-middle risk factors (oversized/unranked
                # context, repeated queries after a large prior result) --
                # see lost_in_middle.py for exactly what this can and
                # can't honestly claim to detect.
                arguments = params.get("arguments")
                litm = self.lost_in_middle_detector.check_call(tool_name, tool_meta.get("description"), arguments, result)
                if litm:
                    event["lost_in_middle"] = litm

        # Prompt-injection scan of the error channel (28.5) -- run
        # regardless of method, since error text is an underscanned
        # vector in most pipelines and can appear on any call, not just
        # tools/call.
        if matched["is_error"]:
            injection = self.injection_detector.scan_error(tool_name or matched["method"], matched["error"])
            if injection:
                event["prompt_injection"] = injection

        if tool_name:
            event["tool_name"] = tool_name

        self.buffer.put(event)

    def on_process_metrics(self, sample: dict) -> None:
        self.buffer.put(sample)

    def _maybe_send_capabilities(self, ts: float) -> None:
        """Sends the current tool registry as a `server_capabilities`
        event whenever it changes -- lets the dashboard show "what does
        this server expose" without polling; only sent on actual change,
        not on every message, to avoid flooding the buffer."""
        tools = self.schema_guard.tools
        if not tools or tools == self._last_tools_sent:
            return
        self._last_tools_sent = dict(tools)
        self.buffer.put({
            "type": "server_capabilities",
            "ts": ts,
            "tools": list(tools.values()),
        })
        self._scan_tool_descriptions(tools, ts)

    def _scan_tool_descriptions(self, tools: dict, ts: float) -> None:
        """Scans every declared tool description for prompt-injection
        patterns (28.1-28.3, 28.6) -- a malicious/compromised server can
        embed instruction-like text in its own tool metadata, which an
        orchestrating LLM may read as legitimate context. Scanned once
        per distinct (name, description) pair, not on every capabilities
        resend."""
        for name, meta in tools.items():
            description = meta.get("description")
            key = f"{name}:{description}"
            if key in self._descriptions_scanned:
                continue
            self._descriptions_scanned.add(key)

            signal = self.injection_detector.scan_tool_description(name, description)
            if signal:
                self.buffer.put({
                    "type": "prompt_injection_alert",
                    "ts": ts,
                    "tool_name": name,
                    "prompt_injection": signal,
                })
