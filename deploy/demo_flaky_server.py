#!/usr/bin/env python3
"""
A minimal, deliberately imperfect stdio MCP server used to demonstrate
mcp-insight end to end. It implements just enough of the protocol to be
wrapped: initialize, tools/list-via-initialize, and tools/call for one
tool, `add_numbers`. It has two intentional, real-taxonomy-style faults
baked in so the wrapper has something to actually catch:

1. ~1 in 5 calls returns a result missing the schema's required field
   (a silent failure -- reports JSON-RPC success, violates its own schema).
2. Occasionally sleeps to simulate a slow tool call.

This is a test fixture, not a reference implementation of MCP.
"""
import json
import random
import sys
import time

TOOL_SCHEMA = {
    "type": "object",
    "properties": {"sum": {"type": "number"}},
    "required": ["sum"],
}


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
                        "name": "add_numbers",
                        "description": "Adds two numbers",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                        },
                        "outputSchema": TOOL_SCHEMA,
                    }
                ]
            },
            "serverInfo": {"name": "demo-flaky-server", "version": "0.1.0"},
        },
    })


def handle_tools_call(req: dict) -> None:
    params = req.get("params", {})
    if params.get("name") != "add_numbers":
        send({"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32601, "message": "unknown tool"}})
        return

    args = params.get("arguments", {})
    a = args.get("a", 0)
    b = args.get("b", 0)

    # Occasionally simulate slowness.
    if random.random() < 0.15:
        time.sleep(random.uniform(0.5, 1.5))

    # ~1 in 5 calls: return a JSON-RPC SUCCESS with a result that silently
    # violates the declared output schema (missing required "sum" field).
    # This is the exact fault class mcp-insight's schema guard exists to catch.
    if random.random() < 0.2:
        result = {"total": a + b}  # wrong key name -- violates TOOL_SCHEMA
    else:
        result = {"sum": a + b}

    send({"jsonrpc": "2.0", "id": req["id"], "result": result})


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
            pass  # no response required
        elif "id" in req:
            send({"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32601, "message": f"unhandled method {method}"}})


if __name__ == "__main__":
    main()
