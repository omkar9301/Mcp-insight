#!/usr/bin/env python3
"""
Drives the wrapped demo server the way an MCP client would: sends
initialize, then a batch of tools/call requests, over stdio.

Usage:
    python drive_demo.py | mcp-insight run --server-id demo-flaky -- python demo_flaky_server.py | python read_responses.py

Simplest usage for a quick manual test is documented in the top-level README.
"""
import json
import random
import sys


def send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main(n_calls: int = 40) -> None:
    send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    for i in range(2, n_calls + 2):
        a, b = random.randint(1, 100), random.randint(1, 100)
        send({
            "jsonrpc": "2.0",
            "id": i,
            "method": "tools/call",
            "params": {"name": "add_numbers", "arguments": {"a": a, "b": b}},
        })


if __name__ == "__main__":
    main()
