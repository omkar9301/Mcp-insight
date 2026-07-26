#!/usr/bin/env python3
"""
Drives the wrapped demo_injection_server.py the way an MCP client would.

Usage:
    python drive_injection_demo.py | mcp-insight run --server-id demo-injection \\
        --ingestion-url http://localhost:8000 --api-key <key> \\
        -- python demo_injection_server.py > /dev/null
"""
import json
import sys


def send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main(n_calls: int = 20) -> None:
    send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    for i in range(2, n_calls + 2):
        send({
            "jsonrpc": "2.0",
            "id": i,
            "method": "tools/call",
            "params": {"name": "helper", "arguments": {"text": f"sample text {i}"}},
        })


if __name__ == "__main__":
    main()
