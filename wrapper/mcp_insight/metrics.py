"""
mcp_insight.metrics

Polls OS-level resource metrics for the spawned MCP server process. This is
what answers "why is it slow" beyond what's visible in the message stream --
climbing memory or file-descriptor counts, CPU saturation, etc.
"""
from __future__ import annotations

import asyncio
import time
from typing import Callable

import psutil


class ProcessMetricsSidecar:
    def __init__(self, pid: int, on_sample: Callable[[dict], None], interval_s: float = 5.0) -> None:
        self.pid = pid
        self.on_sample = on_sample
        self.interval_s = interval_s
        self._stop = False

    async def run(self) -> None:
        try:
            proc = psutil.Process(self.pid)
        except psutil.NoSuchProcess:
            return

        # First call to cpu_percent() primes the measurement; discard it.
        proc.cpu_percent(interval=None)

        while not self._stop:
            await asyncio.sleep(self.interval_s)
            try:
                with proc.oneshot():
                    sample = {
                        "type": "process_metrics",
                        "ts": time.time(),
                        "cpu_percent": proc.cpu_percent(interval=None),
                        "memory_rss_bytes": proc.memory_info().rss,
                        "num_fds": _safe_num_fds(proc),
                        "num_threads": proc.num_threads(),
                        "num_connections": _safe_num_connections(proc),
                    }
                self.on_sample(sample)
            except psutil.NoSuchProcess:
                break

    def stop(self) -> None:
        self._stop = True


def _safe_num_fds(proc: psutil.Process) -> int | None:
    try:
        return proc.num_fds()  # unix only
    except AttributeError:
        return None
    except psutil.AccessDenied:
        return None


def _safe_num_connections(proc: psutil.Process) -> int | None:
    try:
        return len(proc.connections())
    except (psutil.AccessDenied, AttributeError):
        return None
