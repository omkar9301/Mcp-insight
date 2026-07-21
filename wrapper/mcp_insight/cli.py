"""
mcp_insight.cli

Entry point: `mcp-insight run --server-id my-server -- python server.py`

Spawns the real MCP server as a child process and transparently relays
stdin/stdout between the real MCP client (whatever launched *this* wrapper)
and the child, while tapping every line for observability. The child never
knows it's being observed; the client never knows either.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from .capture import CapturedMessage, parse_line
from .interceptor import Interceptor
from .metrics import ProcessMetricsSidecar


async def _pump(reader: asyncio.StreamReader, sink, direction: str, interceptor: Interceptor) -> None:
    """Pumps from an asyncio StreamReader (the child process's stdout pipe --
    natively async and cross-platform via asyncio.subprocess) to a plain
    synchronous sink (our own real `sys.stdout.buffer`).

    `sink` is a plain `BufferedWriter`, not an async `StreamWriter` -- it
    has no `.drain()`. An earlier version of this code called
    `await sink.drain()` here, which raised `AttributeError` on the very
    first line and silently killed this fire-and-forget task, so every
    message after the first was dropped without any error surfacing.
    A direct synchronous `.write()`/`.flush()` is correct here: pipe writes
    of single JSON-RPC lines are small and effectively non-blocking, so we
    don't need (and per the above, don't reliably have) async pipe writing.
    """
    while True:
        line = await reader.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace")
        sink.write(line)
        sink.flush()
        interceptor.handle_message(parse_line(direction, text))


async def _pump_stdin(writer, direction: str, interceptor: Interceptor) -> None:
    """Pumps from this process's own real stdin (the real MCP client's side).

    `loop.connect_read_pipe(sys.stdin)` is unreliable on Windows -- the
    ProactorEventLoop doesn't consistently support wrapping a real stdin
    handle as an async pipe. A thread-backed blocking read via
    run_in_executor works identically on every platform.
    """
    loop = asyncio.get_event_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.buffer.readline)
        if not line:
            break
        text = line.decode("utf-8", errors="replace")
        # Tap (register the pending request) BEFORE forwarding to the
        # child. A fast child can respond before this coroutine gets
        # rescheduled after `await writer.drain()` -- if the request isn't
        # registered in the tracker yet when that response is read on the
        # other pump task, `on_response` finds no match and the whole
        # rpc_call event is silently lost. Tapping first closes that race.
        interceptor.handle_message(parse_line(direction, text))
        writer.write(line)
        await writer.drain()
    writer.close()


async def run(server_id: str, ingestion_url: str, api_key: str, cmd: list[str]) -> int:
    interceptor = Interceptor(server_id=server_id, ingestion_url=ingestion_url, api_key=api_key)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=sys.stderr,  # pass server logs straight through, untouched
    )

    sidecar = ProcessMetricsSidecar(pid=proc.pid, on_sample=interceptor.on_process_metrics)

    tasks = [
        asyncio.create_task(interceptor.buffer.run()),
        asyncio.create_task(sidecar.run()),
        asyncio.create_task(_pump_stdin(proc.stdin, "client_to_server", interceptor)),
        asyncio.create_task(_pump(proc.stdout, sys.stdout.buffer, "server_to_client", interceptor)),
    ]

    returncode = await proc.wait()

    sidecar.stop()
    await interceptor.buffer.stop()
    for t in tasks:
        t.cancel()
    # Cancelling doesn't wait for the tasks to actually unwind -- the
    # buffer's own `finally: await self._flush()` (its last-chance flush of
    # whatever's still queued) needs a real turn of the event loop to run
    # to completion. Returning immediately after `.cancel()` let the
    # process exit mid-flush, silently dropping the tail of the batch.
    await asyncio.gather(*tasks, return_exceptions=True)

    return returncode


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mcp-insight",
        description="Transparent observability wrapper for any stdio-based MCP server.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Wrap and run an MCP server")
    run_parser.add_argument("--server-id", required=True, help="Stable identifier for this server in the dashboard")
    run_parser.add_argument(
        "--ingestion-url",
        default=os.environ.get("MCP_INSIGHT_INGESTION_URL", "http://localhost:8000"),
    )
    run_parser.add_argument("--api-key", default=os.environ.get("MCP_INSIGHT_API_KEY", ""))
    run_parser.add_argument("cmd", nargs=argparse.REMAINDER, help="-- the real server command, e.g. -- python server.py")

    from .proxy import add_proxy_subcommand
    add_proxy_subcommand(sub)

    args = parser.parse_args()

    if args.command == "run":
        cmd = args.cmd
        if cmd and cmd[0] == "--":
            cmd = cmd[1:]
        if not cmd:
            parser.error("You must provide the server command after '--', e.g. mcp-insight run --server-id x -- python server.py")
        exit_code = asyncio.run(run(args.server_id, args.ingestion_url, args.api_key, cmd))
        sys.exit(exit_code)
    elif args.command == "proxy":
        from .proxy import run_proxy
        asyncio.run(run_proxy(
            server_id=args.server_id,
            target=args.target,
            listen_host=args.listen_host,
            listen_port=args.listen_port,
            ingestion_url=args.ingestion_url,
            api_key=args.api_key,
        ))


if __name__ == "__main__":
    main()
