from __future__ import annotations

"""
mcp_insight ingestion self-observability: Prometheus metrics for the
ingestion service itself (not to be confused with the process metrics the
wrapper collects *about wrapped MCP servers* -- this is "who watches the
watcher"). Scrape `GET /metrics`.
"""
import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_COUNT = Counter(
    "mcp_insight_ingestion_requests_total", "Total requests", ["method", "path", "status"]
)
REQUEST_LATENCY = Histogram(
    "mcp_insight_ingestion_request_duration_seconds", "Request latency", ["method", "path"]
)
EVENTS_INGESTED = Counter(
    "mcp_insight_events_ingested_total", "Total events ingested", ["type"]
)
FAULTS_CLASSIFIED = Counter(
    "mcp_insight_faults_classified_total", "Total fault events auto-classified"
)
ALERTS_SENT = Counter(
    "mcp_insight_alerts_sent_total", "Total alerts sent", ["kind"]
)


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", request.url.path)


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start
        path = _route_template(request)
        REQUEST_COUNT.labels(method=request.method, path=path, status=response.status_code).inc()
        REQUEST_LATENCY.labels(method=request.method, path=path).observe(duration)
        return response


async def metrics_endpoint() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
