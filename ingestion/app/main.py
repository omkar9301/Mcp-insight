from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .alerting import aclose_client as aclose_alerting_client
from .classifier_client import aclose_client as aclose_classifier_client
from .config import settings
from .db import ensure_indexes
from .logging_config import RequestLoggingMiddleware, configure_logging
from .metrics_prom import PrometheusMiddleware, metrics_endpoint
from .routes import alerts, events, feedback, health, keys, stats

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes()
    yield
    await aclose_classifier_client()
    await aclose_alerting_client()


app = FastAPI(title="MCP Insight Ingestion API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.dashboard_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(PrometheusMiddleware)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(events.router, tags=["events"])
app.include_router(health.router, tags=["health"])
app.include_router(keys.router, tags=["keys"])
app.include_router(alerts.router, tags=["alerts"])
app.include_router(stats.router, tags=["stats"])
app.include_router(feedback.router, tags=["feedback"])

app.add_api_route("/metrics", metrics_endpoint, methods=["GET"])


@app.get("/")
async def root():
    return {"service": "mcp-insight-ingestion", "status": "ok"}
