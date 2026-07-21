# mcp-insight

A universal observability platform for MCP (Model Context Protocol) servers:
transparent interceptors (stdio wrapper + HTTP/SSE reverse proxy, zero
server code changes), a backend that stores events, auto-classifies faults
against a real evidence-grounded taxonomy, computes health scores and
anomalies, sends alerts, and a dashboard to see all of it.

## What's included

```
mcp-insight/
  wrapper/             pip-installable CLI
    mcp_insight/
      cli.py             `mcp-insight run -- <server command>` (stdio wrapper, C1)
      proxy.py           `mcp-insight proxy --target <url>` (HTTP/SSE reverse proxy, C2)
      interceptor.py     shared, transport-agnostic fault-detection core
      capture.py         JSON-RPC parsing + request/response correlation
      schema_guard.py     captures tool schemas, validates results -> silent failures
      buffer.py           async, non-blocking, fail-open local event buffer
      metrics.py          process resource sidecar (CPU, memory, FDs, threads)
    tests/               pytest unit tests
  ingestion/            FastAPI + MongoDB service
    app/
      main.py, db.py, models.py, config.py, auth.py
      keys.py                 per-server scoped API keys (mint/rotate/revoke)
      rate_limit.py            in-memory sliding-window limiter (ingest + read)
      logging_config.py       structured JSON request logging
      metrics_prom.py          Prometheus /metrics self-observability
      classifier_client.py   auto-classifies fault events against the taxonomy
      health_scoring.py      weighted 0-100 health score engine
      anomaly.py              window-over-window anomaly/trend detector
      alerting.py              Slack webhook alerts with persisted cooldowns
      routes/events.py, routes/health.py, routes/keys.py
    tests/               pytest unit/integration tests
  classifier/            FastAPI service, TF-IDF match against the 27-category
                          real MCP fault taxonomy (auth-protected, same API key,
                          per-IP rate limited)
    tests/
  dashboard/             React + Vite SPA: servers list, per-server health/
                          events/anomalies, taxonomy reference, settings
  deploy/
    demo_flaky_server.py   test MCP server with a baked-in ~20% silent-failure rate
    drive_demo.py            sends realistic traffic against the demo server
  docker-compose.yml     mongo + ingestion + classifier + dashboard (dev-shaped)
  docker-compose.prod.yml  production overlay: no exposed mongo port, restart
                            policies, resource limits, multi-worker uvicorn
  .github/workflows/ci.yml  tests (all 3 services) + dashboard build + image builds
  .env.example            copy to .env and fill in before `docker compose up`
```

## 1. Configure and start the backend

```bash
cp .env.example .env
# edit .env: set MCP_INSIGHT_API_KEY to a real secret, optionally SLACK_WEBHOOK_URL
docker compose up --build
```

This starts:
- MongoDB on `27017`
- Ingestion API on `http://localhost:8000` (auth-protected by `MCP_INSIGHT_API_KEY`)
- Classifier API on `http://localhost:8100` (same API key)
- Dashboard on `http://localhost:5173`

Open the dashboard, go to **Settings**, and enter the ingestion/classifier
URLs and the API key (same value as `MCP_INSIGHT_API_KEY` in `.env`). It's
stored in the browser's `localStorage`, not baked into the build.

## 2. Install the wrapper CLI

```bash
cd wrapper
pip install -e .
```

## 3a. Wrap a stdio MCP server (C1 -- most universal)

No code changes to the server. Just run it through the wrapper instead of directly:

```bash
mcp-insight run --server-id my-server \
  --ingestion-url http://localhost:8000 \
  --api-key <your MCP_INSIGHT_API_KEY> \
  -- python my_server.py
```

Your MCP client connects to this command exactly as it would connect to
`python my_server.py` directly -- the wrapper is fully transparent on stdin/stdout.

## 3b. Reverse-proxy a Streamable-HTTP MCP server (C2)

For servers that speak Streamable HTTP instead of stdio, point your client
at the proxy's URL instead of the server's:

```bash
mcp-insight proxy --server-id my-http-server \
  --target http://localhost:9000 \
  --listen-port 8787 \
  --ingestion-url http://localhost:8000 \
  --api-key <your MCP_INSIGHT_API_KEY>
```

Point your MCP client at `http://localhost:8787` instead of
`http://localhost:9000`. Every JSON-RPC message -- plain JSON responses and
SSE event streams alike -- is tapped and forwarded byte-for-byte to its
real destination.

## 4. Try it with the included demo (no real MCP server needed)

The demo server intentionally returns a schema-violating "successful" response
~20% of the time, and is occasionally slow -- so you can see the wrapper catch
both a silent failure and a latency signal without needing a real server:

```bash
cd deploy
python drive_demo.py | mcp-insight run --server-id demo-flaky \
  --ingestion-url http://localhost:8000 --api-key <your key> \
  -- python demo_flaky_server.py > /dev/null
```

Then either open the dashboard at `http://localhost:5173` and click into
`demo-flaky`, or query the API directly:

```bash
curl -H "Authorization: Bearer <your key>" http://localhost:8000/v1/servers/demo-flaky/health | python -m json.tool
curl -H "Authorization: Bearer <your key>" "http://localhost:8000/v1/servers/demo-flaky/events?only_faults=true&limit=10" | python -m json.tool
curl -H "Authorization: Bearer <your key>" http://localhost:8000/v1/servers/demo-flaky/anomalies | python -m json.tool
```

You should see `silent_failure_count` > 0 and a `health_score` below 100 in
the health summary, each flagged event carrying an automatic `classification`
against the real taxonomy, and (if traffic is bursty enough relative to the
15-minute baseline) entries under `anomalies`.

## 5. Classify a fault manually against the real taxonomy

Faults are classified automatically as they're ingested (see `classification`
on stored events), but you can also call the classifier directly:

```bash
curl -X POST http://localhost:8100/v1/classify \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your key>" \
  -d '{"text": "tool call returned success but the result was missing a required field"}'
```

Returns the best-matching real fault subcategory, its practitioner-confirmed
frequency, and its dominant severity/effort from the source study.

## 6. Alerting

Set `SLACK_WEBHOOK_URL` in `.env` to an incoming webhook URL and restart
`ingestion`. Alerts fire when:
- A server's health score drops below `ALERT_SCORE_THRESHOLD` (default 60).
- An anomaly (error-rate or latency spike vs. the previous window) is detected.

Each alert kind has a per-server cooldown (`ALERT_COOLDOWN_SECONDS`, default
15 minutes) persisted in Mongo, so restarts don't cause alert storms.

## 7. Per-server API keys

The admin key (`MCP_INSIGHT_API_KEY`) can do anything, including reading
every server's data and minting/rotating/revoking scoped keys. For a real
deployment with multiple independently-owned servers, give each one its
own key instead of sharing the admin key with every wrapper deployment:

```bash
# Mint (or rotate -- this invalidates any previous key) a key for one server.
# Admin-only. The plaintext is shown exactly once.
curl -X POST -H "Authorization: Bearer <admin key>" \
  http://localhost:8000/v1/servers/my-server/keys

# Revoke it (the admin key can still ingest for this server_id afterwards).
curl -X DELETE -H "Authorization: Bearer <admin key>" \
  http://localhost:8000/v1/servers/my-server/keys
```

Use the returned key as `--api-key` on the wrapper for that one server. A
per-server key can only ever write events for its own `server_id` -- using
it for a different server, or for any read endpoint, returns 401. Read
endpoints (`/health`, `/events`, `/anomalies`, `/servers`) and key
management remain admin-key-only.

## 8. Rate limiting

Ingestion enforces a per-`server_id` sliding-window limit on
`POST /v1/events` (`RATE_LIMIT_INGEST_PER_MINUTE`, default 120/min) and a
per-client-IP limit on read endpoints (`RATE_LIMIT_READ_PER_MINUTE`,
default 300/min). The classifier enforces its own per-IP limit on
`/v1/classify` (`RATE_LIMIT_CLASSIFY_PER_MINUTE`, default 300/min).
Exceeding a limit returns `429`. These are in-memory, per-process limiters
-- see "Architecture notes" below for what that means if you scale out.

## 9. Observability of the platform itself

- `GET /metrics` on both ingestion and classifier exposes Prometheus
  metrics: request counts/latency by route+status, events ingested by
  type, faults auto-classified, and alerts sent by kind.
- Both services log structured JSON lines to stdout (one line per request:
  method, path, status, duration, client IP) -- pipe straight into any log
  aggregator without a custom parser.

## 10. Production deployment

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

Differs from the dev-shaped base file: Mongo's port isn't published to the
host (reachable only from other containers on the compose network),
`restart: unless-stopped` on every service, conservative CPU/memory
limits, and 2 uvicorn workers each for ingestion/classifier.

## Running tests

Each service has its own virtualenv and test suite:

```bash
cd wrapper    && python -m venv .venv && .venv/bin/pip install -e ".[dev]"       && .venv/bin/pytest tests/
cd classifier && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/pytest tests/
cd ingestion  && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/pytest tests/
```

(On Windows, use `.venv\Scripts\pip`/`.venv\Scripts\pytest` instead.)

## Architecture notes

- **Fail-open by design.** The local event buffer (`wrapper/mcp_insight/buffer.py`)
  never blocks or fails the real MCP session if the ingestion API is slow or
  down -- it drops events instead. This means observability data loss is
  possible under backend outages by design, not by accident.
- **Auth is two-tier.** The admin key (`MCP_INSIGHT_API_KEY`) can do
  anything; per-server keys (minted via `POST /v1/servers/{id}/keys`) can
  only write events for their own `server_id` -- see section 7. All
  endpoints are admin-key-only except `POST /v1/events`, which accepts
  either. If no admin key is configured, auth is disabled -- a deliberate
  local-dev escape hatch (docker-compose always sets one).
- **Classification is automatic.** `ingestion/app/routes/events.py` calls
  the classifier for every error/silent-failure/protocol-violation event as
  it's ingested and stores the result on the event document -- callers don't
  need to invoke `/v1/classify` themselves except for ad-hoc lookups.
- **Health scoring is a transparent weighted formula**, not a black box --
  see `ingestion/app/health_scoring.py` for the exact weights and
  `health_breakdown` in the `/health` response for the per-factor penalty.
- **Anomaly detection compares equal-length adjacent windows** (default:
  last 15 minutes vs. the 15 minutes before that), flagging ratio-based
  spikes in error rate or p95 latency -- see `ingestion/app/anomaly.py`.

## What's NOT in this build

- **Cloud embeddings / MongoDB Atlas Vector Search** -- the classifier uses
  local TF-IDF so this is deployable without cloud credentials. Swapping to
  Bedrock embeddings + Atlas Vector Search for better semantic matching at
  scale is a contained change inside `classifier/app/main.py` -- the
  `/v1/classify` request/response contract doesn't need to change.
- **Multi-tenancy / user accounts** -- there's an admin key plus per-server
  scoped keys now, but no user accounts, orgs, or RBAC beyond that
  two-tier model.
- **Optional SDK hook** -- the opt-in decorator layer from the architecture
  doc (deeper internal traces for servers willing to add one import) isn't
  built; only interception-based capture exists.
- **Learned anomaly detection** -- the anomaly detector is a ratio-based
  heuristic over adjacent windows, not a statistical/ML model.
- **Distributed rate limiting** -- the limiter is in-memory per-process;
  running multiple ingestion replicas or workers means the limit is
  per-worker, not a true global cap. Move to a shared store (Redis) if you
  need one.
- **Dashboard views for keys/alerts/metrics** -- key minting, Prometheus
  metrics, and rate-limit status are API/curl-only right now, not
  surfaced in the React dashboard yet.

## Honest state of this code

This has been run end-to-end via `docker compose up --build`, driven with
real traffic through both the fixed request-ordering race and the
shutdown-flush race described below, and verified via the dashboard and API
directly -- not just reviewed for logical correctness. 45 automated tests
pass across the three services.

Two real bugs were found and fixed during this validation pass (not
theoretical -- both reproduced with real traffic before the fix):
1. `wrapper/mcp_insight/cli.py`'s stdout pump called `.drain()` on a plain
   synchronous `BufferedWriter` (`sys.stdout.buffer`), which doesn't have
   that method -- this silently killed the pump task after the first
   forwarded message and dropped everything after it. `sys.stdin` also
   can't be reliably wrapped as an async pipe on Windows via
   `connect_read_pipe`; both are now handled without relying on either.
2. Request taps were registered *after* forwarding the request to the
   child process, racing against fast (non-sleeping) child responses and
   silently dropping the correlated `rpc_call` event; and cancelled tasks
   were never awaited on shutdown, so the event buffer's final flush could
   be cut off mid-flight. Both are now ordered/awaited correctly.

Not yet done: load testing, testing against a real (non-demo) production
MCP server, and multi-instance/HA deployment of the ingestion service.

### Stage 2, Phase A (production hardening) -- also validated live

Per-server API keys, rate limiting, structured logging, Prometheus
metrics, and the production compose overlay were all exercised against
the live running stack, not just written and reviewed: minted a scoped
key via the API, confirmed it authorizes writes for its own `server_id`
and gets rejected (401) for a different one, confirmed the admin key
still works after that, confirmed revocation actually blocks further use,
confirmed `/metrics` serves real Prometheus output, confirmed structured
JSON request logs appear in `docker compose logs`, and confirmed the prod
overlay actually removes Mongo's published port (`docker compose ps`
shows `27017/tcp` with no host binding, and the host-side port is
unreachable) while ingestion stays fully functional. 37 ingestion + 8
classifier tests pass (up from 23 and 7).

Not yet done for Phase A: CI has not been run on GitHub itself (no remote
configured for this local repo yet -- the workflow file is written and
the individual steps were run locally, but the workflow itself hasn't
executed in Actions); no secrets-manager integration (still plain env
vars); no TLS/reverse-proxy termination is included (add your own, e.g.
Caddy or an ALB, in front of the prod overlay).
