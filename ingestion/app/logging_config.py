from __future__ import annotations

"""
mcp_insight ingestion structured logging.

Plain JSON lines to stdout -- container-log-friendly, greppable/parseable
by any log aggregator (CloudWatch, Loki, etc.) without a custom parser.
"""
import json
import logging
import sys
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": record.created,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_fields"):
            payload.update(record.extra_fields)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    # Quiet down the very chatty default access logger -- our own
    # request-logging middleware below replaces it with structured lines.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


_log = logging.getLogger("mcp_insight.ingestion.access")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = (time.time() - start) * 1000.0
            _log.info(
                "request",
                extra={
                    "extra_fields": {
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": response.status_code if response else 500,
                        "duration_ms": round(duration_ms, 2),
                        "client_ip": request.client.host if request.client else None,
                    }
                },
            )
