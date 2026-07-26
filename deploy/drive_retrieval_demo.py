#!/usr/bin/env python3
"""
Drives the wrapped demo_retrieval_server.py the way an MCP client would.

Usage:
    python drive_retrieval_demo.py | mcp-insight run --server-id demo-retrieval \\
        --ingestion-url http://localhost:8000 --api-key <key> \\
        -- python demo_retrieval_server.py > /dev/null
"""
import json
import sys

QUERIES = ["how do I reset my password", "pricing tiers", "refund policy", "api rate limits", "onboarding steps"]


def send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main(n_calls: int = 30) -> None:
    send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    for i in range(2, n_calls + 2):
        query = QUERIES[i % len(QUERIES)]
        send({
            "jsonrpc": "2.0",
            "id": i,
            "method": "tools/call",
            "params": {"name": "vector_search", "arguments": {"query": query}},
        })


if __name__ == "__main__":
    main()
