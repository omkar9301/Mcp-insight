#!/usr/bin/env python3
"""
A minimal stdio MCP server exposing one vector-search-shaped tool, used
to demonstrate mcp-insight's retrieval-tool quality feature (see
wrapper/mcp_insight/retrieval_signals.py). ~30% of calls intentionally
return zero matches, simulating a degrading/misconfigured index -- the
exact pattern the "empty-result rate" signal exists to catch.

This is a test fixture, not a reference implementation of MCP or of any
real vector database integration.
"""
import json
import random
import sys

TOOL_NAME = "vector_search"


def send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def handle_initialize(req: dict) -> None:
    send({
        "jsonrpc": "2.0",
        "id": req["id"],
        "result": {
            "protocolVersion": "2025-06-18",
            "capabilities": {
                "tools": [
                    {
                        "name": TOOL_NAME,
                        "description": "Embeds the query and searches the vector index for similar documents",
                        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
                        "outputSchema": {
                            "type": "object",
                            "properties": {
                                "matches": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {"text": {"type": "string"}, "score": {"type": "number"}},
                                    },
                                }
                            },
                        },
                    }
                ]
            },
            "serverInfo": {"name": "demo-retrieval-server", "version": "0.1.0"},
        },
    })


def handle_tools_call(req: dict) -> None:
    params = req.get("params", {})
    if params.get("name") != TOOL_NAME:
        send({"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32601, "message": "unknown tool"}})
        return

    # ~30% of the time: the index/embedding step silently returns nothing
    # useful -- no protocol error, no schema violation, just an empty
    # (but perfectly valid) result. This is invisible to schema
    # validation and only shows up as a retrieval-quality signal.
    if random.random() < 0.3:
        matches = []
    else:
        n = random.randint(1, 5)
        matches = [{"text": f"chunk-{i}", "score": round(random.uniform(0.3, 0.98), 3)} for i in range(n)]

    send({"jsonrpc": "2.0", "id": req["id"], "result": {"matches": matches}})


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = req.get("method")
        if method == "initialize":
            handle_initialize(req)
        elif method == "tools/call":
            handle_tools_call(req)
        elif method == "notifications/initialized":
            pass
        elif "id" in req:
            send({"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32601, "message": f"unhandled method {method}"}})


if __name__ == "__main__":
    main()
