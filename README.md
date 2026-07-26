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
      anomaly.py              rolling z-score anomaly/trend detector + bucketed timeseries
      alerting.py              Slack webhook alerts, persisted cooldowns, history, mute
      routes/events.py, routes/health.py, routes/keys.py, routes/alerts.py,
      routes/stats.py (aggregate rollups), routes/feedback.py (classification feedback)
    tests/               pytest unit/integration tests
  classifier/            FastAPI service, TF-IDF + optional LLM fallback match
                          against the 27-category real MCP fault taxonomy
                          (auth-protected, same API key, per-IP rate limited)
    tests/
  dashboard/             React + Vite SPA:
                          components/charts/  BarChart, DonutChart, StackedBar, Heatmap (no deps)
                          Overview (KPIs+charts), ServerDetail (trend/heatmap/alerts/keys/feedback),
                          Taxonomy + CategoryPage + TaxonomyDrilldown, SeverityPage, Settings
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
frequency, and its dominant severity/effort from the source study. If TF-IDF
confidence is below `LOW_CONFIDENCE_THRESHOLD` (0.15), the classifier also
tries an LLM fallback (Claude) and, if it succeeds, puts that pick first in
`results` with `"source": "llm"` (`confidence: null` -- LLM picks aren't
scored the same way). Set `ANTHROPIC_API_KEY` to enable this; without it,
low-confidence queries just keep the best TF-IDF guess (`source: "tfidf"`).

## 6. Alerting

Set `SLACK_WEBHOOK_URL` in `.env` to an incoming webhook URL and restart
`ingestion`. Alerts fire when:
- A server's health score drops below `ALERT_SCORE_THRESHOLD` (default 60).
- An anomaly (error-rate or p95-latency spike, statistically -- see below) is detected.

Each alert kind has a per-server cooldown (`ALERT_COOLDOWN_SECONDS`, default
15 minutes) persisted in Mongo, so restarts don't cause alert storms. Every
sent alert is also logged to Mongo and visible on the dashboard's server
detail page (or `GET /v1/servers/{id}/alerts`), which also has a mute
control (`POST/DELETE /v1/servers/{id}/mute`) to silence a noisy server
for N minutes without touching the threshold config.

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

## 11. Dashboard: trends, drill-down, key management

- **Server detail page** now shows a trend chart (error rate + p95 latency
  over the last ~6h, 15-minute buckets, via `GET /v1/servers/{id}/timeseries`),
  the anomaly panel (z-score based), alert history with a mute control, and
  a per-server API key panel (mint/rotate/revoke inline, no curl needed).
- **Taxonomy reference page** rows are now clickable -- each links to
  `GET /v1/events/by-classification`, a cross-server drill-down page for
  that subcategory: the taxonomy description and confirmed%/severity/
  effort up top, aggregate stats (total occurrences, servers affected,
  first/last seen -- computed server-side over *all* matches, not just
  the page shown), a per-server occurrence bar chart, and an events table
  showing the actual tool name and violation detail (not just the generic
  RPC method) with inline thumbs up/down feedback per event.

## 12. Overview page, charts, category/severity views, classification feedback

- **Overview page** (`/`, now the default landing view) shows fleet-wide
  KPIs above the servers list: server count, average health score, total
  60-minute call volume, a health-status donut (healthy/degraded/
  unhealthy/critical across every server), a severity stacked bar, and a
  bar chart of the top fault subcategories in the last 24h -- all backed
  by new aggregate endpoints (`GET /v1/stats/health-distribution`,
  `/v1/stats/severity-breakdown`, `/v1/stats/category-counts`).
- **Category pages** (`/category/{category}`) roll up all subcategories
  within one taxonomy category -- e.g. every "Tool" fault subcategory
  together with a bar chart of relative volume -- linking into the
  existing per-subcategory drill-down.
- **Severity pages** (`/severity/{minor|major|critical}`) show every fault
  event at that severity across all servers, via
  `GET /v1/events/by-severity`.
- **Error-rate heatmap** on the server detail page groups the last 7 days
  by hour-of-day (UTC) to surface recurring bad windows (`GET
  /v1/servers/{id}/heatmap`).
- **Classification feedback loop**: thumbs up/down on any classified
  fault in the events table (`POST
  /v1/servers/{id}/events/{ts}/feedback`), rolled up per subcategory via
  `GET /v1/stats/classification-accuracy` -- lets you see where the
  classifier is actually right or wrong over time, not just trust it
  blindly.
- **Explanations**: an info-icon (`InfoTooltip`) next to every
  non-obvious metric (error rate, silent failures, p95 latency, CPU,
  dropped events, health score breakdown, anomaly detection, heatmap) --
  click to see what it measures and why it matters, without leaving the
  page.
- All new charts (`BarChart`, `DonutChart`, `StackedBar`, `Heatmap`) are
  dependency-free -- plain SVG/DOM, no charting library added, keeping the
  dashboard's bundle small (~62KB gzipped total).

## 13. Overview page: sorting, comparison table, trends, quick actions

The servers section of the Overview page (`/`) was a flat, arbitrarily-ordered
list -- now:
- **Sorted worst-first by default** (critical > unhealthy > degraded >
  healthy > idle), with a colored left border per card/row matching
  status, so you can scan for trouble without reading every line.
- **Search box + status filter** to narrow down a large fleet.
- **Table view toggle** -- a sortable comparison table (click any column
  header) with server, status, score, error rate, p95 latency, silent
  failures, and last-seen side by side, instead of eyeballing separate
  cards.
- **Relative timestamps** ("3m ago" instead of a full date string).
- **Per-server error-rate trend sparkline** on each card (last ~2h, via
  the existing `/timeseries` endpoint), so you can see whether a server
  is trending up or down, not just its current snapshot.
- **Inline mute/unmute** button on each card -- silence a noisy server's
  alerts for 60 minutes without navigating to its detail page.

## 14. Overview page: context, trust signals, actionability

A round of "what would confuse a brand-new user" review surfaced real
gaps in the KPI tiles and charts -- fixed:
- **KPI tiles now explain themselves.** "Avg health score" shows "/100",
  is color-coded to match its severity, and states inline how many active
  servers it's averaged over (it always excluded idle servers, but that
  was previously only visible in a tooltip). "Servers" breaks down into
  active/idle inline instead of a bare count.
- **KPI deltas** ("▲ 3.2 vs 24h ago") via a new lightweight
  `fleet_snapshots` collection (`POST/GET /v1/stats/fleet-snapshot`,
  throttled server-side to one snapshot per 15 minutes regardless of
  polling frequency) -- so numbers show direction, not just a snapshot.
- **"Needs attention" callout** at the top of the page, highlighting
  whichever active server has the worst score -- instead of making you
  scroll the full list to find it.
- **Fixed the severity chart being unreadable with one category.** A
  stacked bar with only `major` present rendered as one solid bar filling
  100% width -- indistinguishable from a loading bar. Replaced with
  `SeverityBars`, which always renders all three severities (even at
  zero) so there's a real comparison to look at.
- **Donut and severity chart segments are now clickable** -- click
  "unhealthy" on the fleet-health donut to filter the servers list to it;
  click a severity bar to jump straight to `/severity/{level}`.
- **Backend connectivity badge** in the sidebar -- pings both services'
  unauthenticated root endpoints every 20s and shows one clear
  connected/disconnected signal, instead of scattered per-page error
  banners when the API URL or key is misconfigured.
- **System status panel**: alerting configured/not, how many alerts sent
  in the last 24h and when the last one went out (`GET
  /v1/stats/alerting-status`) -- alerting existed before this but was
  completely invisible from the dashboard. Also surfaces a count of
  faults classified with low confidence in the last 24h (`GET
  /v1/stats/low-confidence-count`), connecting the Overview page to the
  feedback loop from section 12.
- **Demo/test tag** on server names matching `^demo` (prefix heuristic,
  not a real tagging system) -- so sample data from the bundled demo
  doesn't read as a real production server to a new user.
- **Onboarding banner** when zero servers have live traffic -- tells the
  user exactly what command to run instead of just showing small numbers
  with no explanation.
- **Last-updated indicator** ("Updated 3s ago · refreshes every 15s") so
  the polling behavior is visible instead of implicit.

## 15. Tool Registry -- what each server actually exposes

A new "Tool Registry" page (`/tools` in the sidebar) and a per-server
panel answer "what tools/APIs does this MCP server actually have,"
captured live, not manually documented:

- The wrapper's `SchemaGuard` already parsed tool declarations from a
  server's `initialize` response (for schema validation) -- it now also
  captures them from a `tools/list` response if a server reports tools
  that way instead, and keeps full metadata per tool (name, description,
  input schema, output schema), not just the output schema it needed for
  validation.
- Whenever the captured tool registry changes, the wrapper sends a
  `server_capabilities` event (deduplicated -- only on actual change, not
  on every message) alongside normal traffic events.
- Ingestion denormalizes this onto the server's document (`tools`,
  `tools_updated_at`) instead of the events collection -- it's a registry
  update, not a traffic event, so `GET /v1/servers/{id}/tools` and the
  fleet-wide `GET /v1/tools` are O(1) lookups, not scans.
- The dashboard's Tool Registry page groups by server, shows each tool's
  name/description/input-output field summary, and expands to the full
  raw JSON Schema on click. The server detail page has a matching compact
  panel.
- This only ever shows what's actually been observed -- a server that
  hasn't sent `initialize` or `tools/list` through the wrapper yet (or a
  proxy session that started mid-conversation) shows an empty registry,
  not a guess.

## 16. AI Advisory -- root-cause analysis per captured fault

An on-demand "Get AI Advisory" button on any classified fault event (in
the taxonomy drill-down and server detail event tables) asks an LLM
(Claude, same `ANTHROPIC_API_KEY` as the classifier's LLM fallback --
section 5) to explain, in depth, what actually happened:

- **Summary** -- plain-language description of the fault.
- **Root cause** -- reasoned through the MCP request/response lifecycle
  (transport -> protocol parsing -> tool handler execution -> result
  serialization -> schema validation), naming which layer it traces to,
  and explicitly calling out token/context-length or
  embedding/vector-retrieval issues *if and only if* the data actually
  points there.
- **Suggested solution** -- concrete steps tied to the real captured
  data, not generic advice.
- **"Grounded in"** -- states exactly which fields the analysis is based
  on. This matters: the wrapper never sends full tool call arguments or
  results to ingestion by design (only metadata and violation summaries
  -- see "Fail-open by design" below), so the advisory is built only from
  what was actually captured (method, latency, error/violation detail,
  taxonomy classification) and says so explicitly rather than inventing
  a request/response payload trace that was never observed.

Generated once per event and cached on the event document (`POST
/v1/servers/{id}/events/{ts}/advisory`, `force=true` to regenerate) so
repeat views don't re-spend an LLM call. Reports itself as
"not configured" rather than erroring if `ANTHROPIC_API_KEY` is unset
(`GET /v1/advisory/status`).

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
- **Anomaly detection is a rolling z-score**, not a fixed ratio. It buckets
  the last `ANOMALY_HISTORY_BUCKETS + 1` windows (default 8+1, 15 min
  each = ~2.25h), treats the most recent as "current" and the rest as
  history, and flags current as anomalous if it's `ANOMALY_ZSCORE_THRESHOLD`
  (default 3.0) standard deviations from the historical mean -- adapts to
  each server's own normal variance instead of one fixed multiplier for
  every server. See `ingestion/app/anomaly.py`.

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
- **ML-based anomaly detection** -- z-score against rolling history is
  statistical, not a trained model (no seasonality awareness, e.g. daily
  traffic cycles).
- **Distributed rate limiting** -- the limiter is in-memory per-process;
  running multiple ingestion replicas or workers means the limit is
  per-worker, not a true global cap. Move to a shared store (Redis) if you
  need one.
- **Dashboard views for Prometheus metrics / rate-limit status** -- key
  minting, alert history, and trend charts are now in the dashboard (see
  section 11); raw `/metrics` output and current rate-limit usage are
  still curl-only.
- **Cross-server comparison table** -- the servers list shows each
  server's headline metrics, but there's no dedicated side-by-side
  comparison/sort view yet.

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

### Stage 2, Phase B (smarter intelligence layer)

Rewrote anomaly detection from a fixed ratio-vs-previous-window heuristic
to a rolling z-score against historical buckets, and added an optional
LLM fallback classifier. Both validated against the live stack: confirmed
the classifier degrades cleanly to `source: "tfidf"` with no
`ANTHROPIC_API_KEY` set, confirmed the `/anomalies` endpoint returns the
new bucketed shape, and re-ran the flaky-server demo end-to-end (41/41
events still captured correctly) to confirm nothing in the ingest path
regressed. One real bug caught by the z-score history-bucketing logic
itself during test-writing (not in production behavior, but the same
code path both use): a doc timestamped fractionally ahead of `now` (clock
skew) could compute a negative bucket index and crash with `IndexError`
-- now clamped to the current bucket. 37 ingestion + 13 classifier tests
pass (ingestion unchanged in count -- anomaly tests were rewritten in
place; classifier up from 8).

Not yet done for Phase B: real embeddings (Bedrock/OpenAI) + vector
search -- still TF-IDF as the primary path, LLM fallback only kicks in
below the confidence threshold and isn't a full replacement; no
seasonality/trend-aware anomaly model.

### Stage 2, Phase C (dashboard depth)

Added a bucketed timeseries endpoint (shared bucketing code with anomaly
detection -- `anomaly.bucket_history`), alert history + mute persisted in
Mongo, and a cross-server classification drill-down endpoint; wired all
three into the dashboard (trend charts, alert panel, taxonomy row
click-through) plus inline per-server key mint/revoke. Validated live:
hit `/timeseries`, `/mute` (POST+DELETE), `/alerts`, and
`/events/by-classification` directly against the running stack and got
real bucketed data / a real classified fault back; confirmed the
dashboard serves the new `/taxonomy/:category/:subcategory` SPA route
(200, not a 404 from client-side routing). 44 ingestion tests pass (up
from 37) covering the new bucketing helper and mute/cooldown/history
logic in `alerting.py`; no new backend logic was added to the classifier
in this phase, so its test count is unchanged.

Not yet done for Phase C: no dedicated cross-server comparison table
(sortable side-by-side view) -- the servers list already shows per-server
headline metrics but isn't literally a comparison UI; `/metrics` and
current rate-limit usage still have no dashboard view, curl only.

### Stage 2, Phase D (visualization, category/severity pages, classification feedback)

Added five new aggregate stats endpoints, a feedback loop for
classification accuracy, four dependency-free chart components, and three
new dashboard pages (Overview KPIs, category rollup, severity
cross-server view). Validated live end-to-end: drove a fresh demo run,
then hit `/stats/category-counts`, `/stats/severity-breakdown`,
`/servers/{id}/heatmap`, and `/events/by-severity` directly and got real
computed data back (not empty stubs); submitted feedback on a real
classified event and confirmed `/stats/classification-accuracy` correctly
rolled it up (1/1 = 100%); confirmed all three new SPA routes
(`/`, `/category/Tool`, `/severity/major`) serve 200. `npm run build`
passes cleanly (~62KB gzipped, no new npm dependencies added for
charting). 53 ingestion tests pass (up from 44); no classifier logic
changed in this phase, so its count is unchanged.

One operational note, not a code bug: `.env`'s `MCP_INSIGHT_API_KEY` was
found rotated to a different value outside of any change made in this
session, twice across this project's history now (once with a live Slack
webhook URL alongside it). Neither the codebase nor anything built in
these sessions writes to `.env` automatically -- if you don't recognize a
value change there, treat it as needing investigation on your end, not as
this system's behavior.

Not yet done for Phase D: no dedicated cross-server comparison table
still; multi-label classification (a fault spanning >1 subcategory) not
implemented; blended TF-IDF+LLM confidence scoring wasn't built as a
single unified number -- the LLM pick is prepended as a separate
`source: "llm"` result alongside the TF-IDF ones, not merged into one
score.

**Follow-up**: the taxonomy drill-down page (`/taxonomy/:category/:subcategory`)
was reworked from a flat event log into the detailed view described in
section 12 -- taxonomy description/severity/effort header, aggregate
stats computed server-side over all matches (not just the displayed
page), per-server occurrence bar chart, tool name + violation detail
columns, and inline feedback. `GET /v1/events/by-classification` now
returns `total_count`/`distinct_servers`/`per_server_counts`/`first_seen`/
`last_seen` alongside the event page. Validated live: hit the endpoint
directly and confirmed the aggregate counts (36 total across 6 servers)
matched real accumulated demo data, including a feedback record from an
earlier test showing up correctly on its event. 55 ingestion tests pass
(up from 53).

**Bug fix (real, user-reported)**: a server with zero calls in the
current 60-minute window was reported as `healthy | 100` -- a perfect
score is not the same thing as "no data," and this made crashed,
disconnected, or never-wrapped servers indistinguishable from genuinely
healthy ones. Fixed at the source: `compute_health_score` now returns
`status: "idle"` and `score: null` when `total_calls == 0`, instead of
scoring an empty window as perfect. This required guarding every
downstream consumer of `health["score"]` that assumed a number
(`alerting.maybe_alert_health` would otherwise crash comparing `None >=
threshold`). A second, related staleness bug was caught in the same pass:
`/v1/stats/health-distribution` (the Overview page's fleet-health donut)
was reading a *cached* `latest_health.status` written the last time a
server ingested data -- a server that went quiet kept reporting whatever
status it had the last time it was active, arbitrarily stale. Now checks
`last_seen` recency and buckets anything stale as `idle` regardless of
the cached value. Dashboard updated to match: `HealthBadge`/`DonutChart`
gained an `idle` style, the servers list shows "no activity in the last
60 minutes" instead of a misleading "0 calls, 0.0% errors" line, and the
server detail page shows an explicit idle banner. Validated live: all 7
stale demo servers (last seen 4+ days ago in wall-clock time) correctly
now show `idle` instead of a cached `healthy`; a freshly driven demo run
correctly still shows a real computed score (`unhealthy | 67.66`, not
`healthy | 100`). 58 ingestion tests pass (up from 55).

### Stage 2, Phase E (Overview page context and trust signals)

Added three new endpoints (`alerting-status`, `low-confidence-count`,
`fleet-snapshot` POST+GET) and reworked the Overview page per section 14.
Validated live: hit all three new endpoints directly and got real values
back (`configured: false` correctly reflecting no `SLACK_WEBHOOK_URL`
set; a posted snapshot correctly retrievable, and correctly throttled on
a second immediate post); confirmed both services' unauthenticated root
endpoints the connectivity badge depends on return 200. `npm run build`
passes (~66KB gzipped, still no new dependencies). 64 ingestion tests
pass (up from 58).

### Stage 2, Phase F (Tool Registry)

Added tool-registry capture to the wrapper (`SchemaGuard.tools`,
`tools/list` support, change-deduplicated `server_capabilities` events),
storage/serving in ingestion (`GET /v1/servers/{id}/tools`, `GET
/v1/tools`), and the dashboard's Tool Registry page + per-server panel.
Validated live end-to-end, not just unit-tested: drove real demo traffic
through the wrapper and confirmed the actual captured schema came back
correctly from both the per-server and fleet-wide endpoints (tool name
`add_numbers`, full input/output JSON Schema, required fields intact),
and confirmed both new dashboard routes serve 200. 67 ingestion tests
pass (up from 64), 18 wrapper tests pass (up from 15, three new
interceptor-level tests covering capture-on-initialize,
no-resend-when-unchanged, and capture-from-`tools/list`).

### Stage 2, Phase G (AI Advisory)

Added `ingestion/app/advisory.py` (LLM root-cause analysis, grounded
strictly in captured event fields, explicit about what wasn't observed),
a caching endpoint (`POST /v1/servers/{id}/events/{ts}/advisory`), and
the `AdvisoryPanel` dashboard component wired into both the taxonomy
drill-down and server detail event tables. Validated live with a real
`ANTHROPIC_API_KEY` configured (not just the disabled/unconfigured path):
generated a real advisory for an actual captured `demo-tools` silent
failure and the model correctly reasoned out the exact root cause (tool
handler returning an incomplete result, missing the required `sum`
field) from metadata alone -- confirmed the caching path returns
`cached: true` on a second call without re-invoking the LLM, and `force:
true` regenerates. One thing worth noting, not a bug: an early raw
response briefly appeared to contain a mangled em-dash
(`â€”`); re-inspecting the raw response bytes directly
confirmed the JSON itself was clean UTF-8 -- the mangling was a Windows
terminal display artifact from piping through `python -m json.tool`, not
an encoding bug in the ingestion service or the LLM response. 75
ingestion tests pass (up from 67).
