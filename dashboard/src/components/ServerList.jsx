import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ingestionApi } from "../api.js";
import HealthBadge from "./HealthBadge.jsx";
import InfoTooltip from "./InfoTooltip.jsx";
import DonutChart from "./charts/DonutChart.jsx";
import BarChart from "./charts/BarChart.jsx";
import SeverityBars from "./charts/SeverityBars.jsx";
import Sparkline from "./Sparkline.jsx";
import { STATUS_BORDER_COLOR, formatRelativeTime, statusRank } from "../utils.js";

const STATUS_OPTIONS = ["all", "critical", "unhealthy", "degraded", "healthy", "idle"];

function isDemoServer(serverId) {
  return /^demo/i.test(serverId);
}

function DeltaLabel({ current, previous, higherIsBetter = true, suffix = "" }) {
  if (current == null || previous == null) return null;
  const diff = current - previous;
  if (Math.abs(diff) < 0.05) return <span style={{ fontSize: 12, color: "var(--text-dim)" }}> · no change vs 24h ago</span>;
  const good = higherIsBetter ? diff > 0 : diff < 0;
  const color = good ? "var(--healthy)" : "var(--critical)";
  const arrow = diff > 0 ? "▲" : "▼";
  return (
    <span style={{ fontSize: 12, color, marginLeft: 6 }}>
      {arrow} {Math.abs(diff).toFixed(1)}{suffix} vs 24h ago
    </span>
  );
}

export default function ServerList() {
  const navigate = useNavigate();
  const [servers, setServers] = useState(null);
  const [healths, setHealths] = useState({});
  const [trends, setTrends] = useState({});
  const [healthDist, setHealthDist] = useState(null);
  const [severityBreakdown, setSeverityBreakdown] = useState(null);
  const [categoryCounts, setCategoryCounts] = useState(null);
  const [alertingStatus, setAlertingStatus] = useState(null);
  const [lowConfidence, setLowConfidence] = useState(null);
  const [prevSnapshot, setPrevSnapshot] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [error, setError] = useState(null);

  const [viewMode, setViewMode] = useState("cards");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortKey, setSortKey] = useState("status");
  const [sortDir, setSortDir] = useState("asc");
  const [muteBusy, setMuteBusy] = useState(null);
  const [, forceTick] = useState(0);

  async function load() {
    try {
      const [data, hd, sb, cc, alertStatus, lowConf, snap] = await Promise.all([
        ingestionApi.listServers(),
        ingestionApi.getHealthDistribution(),
        ingestionApi.getSeverityBreakdown(),
        ingestionApi.getCategoryCounts(),
        ingestionApi.getAlertingStatus(),
        ingestionApi.getLowConfidenceCount(),
        ingestionApi.getFleetSnapshot(24),
      ]);
      setServers(data.servers || []);
      setHealthDist(hd.counts);
      setSeverityBreakdown(sb.counts);
      setCategoryCounts(cc.rows.slice(0, 8));
      setAlertingStatus(alertStatus);
      setLowConfidence(lowConf);
      setPrevSnapshot(snap.snapshot);
      setError(null);

      const entries = await Promise.all(
        (data.servers || []).map(async (s) => {
          try {
            const h = await ingestionApi.getHealth(s.server_id, 60);
            return [s.server_id, h];
          } catch {
            return [s.server_id, null];
          }
        })
      );
      const healthMap = Object.fromEntries(entries);
      setHealths(healthMap);
      setLastUpdated(Date.now() / 1000);

      const trendEntries = await Promise.all(
        (data.servers || []).map(async (s) => {
          try {
            const ts = await ingestionApi.getTimeseries(s.server_id, 15, 8);
            return [s.server_id, ts.buckets.map((b) => b.error_rate)];
          } catch {
            return [s.server_id, null];
          }
        })
      );
      setTrends(Object.fromEntries(trendEntries));

      // Record a fleet-wide snapshot for future delta comparisons. The
      // backend throttles this to at most one per 15 minutes regardless
      // of how often we call it, so calling on every poll is safe.
      const activeServers = Object.values(healthMap).filter((h) => h && h.total_calls > 0).length;
      const scores = Object.values(healthMap).filter((h) => h?.health_score != null).map((h) => h.health_score);
      const avgScore = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null;
      const totalCalls = Object.values(healthMap).reduce((sum, h) => sum + (h?.total_calls || 0), 0);
      ingestionApi
        .postFleetSnapshot({ total_servers: (data.servers || []).length, active_servers: activeServers, avg_score: avgScore, total_calls: totalCalls })
        .catch(() => {});
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    const tickId = setInterval(() => forceTick((n) => n + 1), 5000);
    return () => {
      clearInterval(id);
      clearInterval(tickId);
    };
  }, []);

  async function toggleMute(serverId, currentlyMuted) {
    setMuteBusy(serverId);
    try {
      if (currentlyMuted) await ingestionApi.unmuteAlerts(serverId);
      else await ingestionApi.muteAlerts(serverId, 60);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setMuteBusy(null);
    }
  }

  const rows = useMemo(() => {
    if (!servers) return [];
    return servers
      .map((s) => {
        const h = healths[s.server_id];
        return {
          server_id: s.server_id,
          last_seen: s.last_seen,
          status: h?.health_status || "unknown",
          score: h?.health_score,
          error_rate: h?.error_rate || 0,
          p95: h?.p95_latency_ms,
          silent_failures: h?.silent_failure_count || 0,
          total_calls: h?.total_calls || 0,
          muted: h?.alerts_muted_until && h.alerts_muted_until > Date.now() / 1000,
          trend: trends[s.server_id],
          isDemo: isDemoServer(s.server_id),
        };
      })
      .filter((r) => (statusFilter === "all" ? true : r.status === statusFilter))
      .filter((r) => (search ? r.server_id.toLowerCase().includes(search.toLowerCase()) : true));
  }, [servers, healths, trends, statusFilter, search]);

  const sortedRows = useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => {
      let cmp = 0;
      if (sortKey === "status") cmp = statusRank(a.status) - statusRank(b.status);
      else if (sortKey === "server_id") cmp = a.server_id.localeCompare(b.server_id);
      else if (sortKey === "score") cmp = (a.score ?? -1) - (b.score ?? -1);
      else if (sortKey === "error_rate") cmp = a.error_rate - b.error_rate;
      else if (sortKey === "p95") cmp = (a.p95 ?? -1) - (b.p95 ?? -1);
      else if (sortKey === "silent_failures") cmp = a.silent_failures - b.silent_failures;
      else if (sortKey === "last_seen") cmp = (a.last_seen ?? 0) - (b.last_seen ?? 0);
      return sortDir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [rows, sortKey, sortDir]);

  function onSort(key) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  function sortIndicator(key) {
    if (sortKey !== key) return "";
    return sortDir === "asc" ? " ▲" : " ▼";
  }

  function filterByStatus(status) {
    setStatusFilter(status);
  }

  if (error) return <div className="error-banner">Failed to load servers: {error}</div>;
  if (servers === null) return <div className="empty-state">Loading...</div>;

  const activeServers = Object.values(healths).filter((h) => h && h.total_calls > 0).length;
  const totalCalls = Object.values(healths).reduce((sum, h) => sum + (h?.total_calls || 0), 0);
  const scores = Object.values(healths).filter((h) => h?.health_score != null).map((h) => h.health_score);
  const avgScoreNum = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null;
  const avgScore = avgScoreNum != null ? avgScoreNum.toFixed(1) : "—";
  const avgScoreColor =
    avgScoreNum == null ? "var(--text)" : avgScoreNum >= 90 ? "var(--healthy)" : avgScoreNum >= 70 ? "var(--degraded)" : avgScoreNum >= 40 ? "var(--unhealthy)" : "var(--critical)";

  const worstOffender = [...rows]
    .filter((r) => r.status !== "idle" && r.status !== "unknown" && r.score != null)
    .sort((a, b) => a.score - b.score)[0];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>Overview</h2>
        {lastUpdated && (
          <span style={{ fontSize: 12, color: "var(--text-dim)" }}>Updated {formatRelativeTime(lastUpdated)} · refreshes every 15s</span>
        )}
      </div>

      {activeServers === 0 && (
        <div className="panel" style={{ borderColor: "var(--accent)", marginTop: 16 }}>
          <strong>No live traffic right now.</strong>
          <p style={{ fontSize: 13, color: "var(--text-dim)", marginBottom: 0 }}>
            {servers.length === 0
              ? "No servers have ever reported. "
              : `All ${servers.length} known server(s) are idle (no calls in the last 60 minutes). `}
            Wrap a server to see live data: <span className="mono">mcp-insight run --server-id my-server -- python your_server.py</span>,
            or try the bundled demo in <span className="mono">deploy/</span>.
          </p>
        </div>
      )}

      {worstOffender && (
        <Link to={`/servers/${encodeURIComponent(worstOffender.server_id)}`} className="panel" style={{ display: "block", marginTop: 16, borderColor: STATUS_BORDER_COLOR[worstOffender.status] }}>
          <div style={{ fontSize: 12, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.03em" }}>Needs attention</div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 4 }}>
            <span style={{ fontWeight: 600, fontSize: 16 }}>{worstOffender.server_id}</span>
            <HealthBadge status={worstOffender.status} score={worstOffender.score} />
            <span style={{ fontSize: 13, color: "var(--text-dim)" }}>
              {(worstOffender.error_rate * 100).toFixed(1)}% errors, {worstOffender.silent_failures} silent failures
            </span>
          </div>
        </Link>
      )}

      <div className="grid" style={{ marginTop: 16 }}>
        <div className="stat-tile">
          <div className="label">Servers</div>
          <div className="value">{servers.length}</div>
          <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 2 }}>
            {activeServers} active · {servers.length - activeServers} idle
            <DeltaLabel current={servers.length} previous={prevSnapshot?.total_servers} />
          </div>
        </div>
        <div className="stat-tile">
          <div className="label">
            Avg health score
            <InfoTooltip text="Mean of each ACTIVE server's 0-100 health score (weighted error rate, silent failures, latency, process pressure, and taxonomy severity). Idle servers are excluded -- there's nothing to average when there's no data. See a server's page for the exact formula breakdown." />
          </div>
          <div className="value" style={{ color: avgScoreColor }}>
            {avgScore}
            {avgScoreNum != null ? <span style={{ fontSize: 14, color: "var(--text-dim)" }}> /100</span> : ""}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 2 }}>
            {activeServers > 0 ? `across ${activeServers} active server${activeServers === 1 ? "" : "s"}` : "no active servers"}
            <DeltaLabel current={avgScoreNum} previous={prevSnapshot?.avg_score} />
          </div>
        </div>
        <div className="stat-tile">
          <div className="label">Calls (60m, all servers)</div>
          <div className="value">{totalCalls}</div>
          <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 2 }}>
            {activeServers > 0 ? `from ${activeServers} active server${activeServers === 1 ? "" : "s"}` : " "}
            <DeltaLabel current={totalCalls} previous={prevSnapshot?.total_calls} suffix=" calls" />
          </div>
        </div>
      </div>

      {(alertingStatus || lowConfidence) && (
        <div className="panel">
          <h3>System status</h3>
          <div style={{ display: "flex", gap: 24, flexWrap: "wrap", fontSize: 13 }}>
            {alertingStatus && (
              <span>
                Alerting:{" "}
                {alertingStatus.configured ? (
                  <strong style={{ color: "var(--healthy)" }}>configured</strong>
                ) : (
                  <strong style={{ color: "var(--text-dim)" }}>not configured</strong>
                )}
                {alertingStatus.configured && (
                  <span style={{ color: "var(--text-dim)" }}>
                    {" "}
                    · {alertingStatus.alerts_last_24h} sent in last 24h
                    {alertingStatus.last_alert_sent_at ? `, last ${formatRelativeTime(alertingStatus.last_alert_sent_at)}` : ""}
                  </span>
                )}
                <InfoTooltip text="Whether SLACK_WEBHOOK_URL is set for this deployment, and evidence alerts are actually being sent -- not just configured but silently failing." />
              </span>
            )}
            {lowConfidence && lowConfidence.low_confidence_count > 0 && (
              <span>
                <strong style={{ color: "var(--degraded)" }}>{lowConfidence.low_confidence_count}</strong> faults classified with
                low confidence in the last 24h
                <InfoTooltip text="These faults didn't match any taxonomy category well (below the TF-IDF confidence threshold). Worth reviewing via feedback (👍/👎) on the server detail or taxonomy drill-down pages to help spot classifier gaps." />
              </span>
            )}
          </div>
        </div>
      )}

      {(healthDist || severityBreakdown) && (
        <div className="panel">
          <h3>
            Fleet health
            <InfoTooltip text="How many servers currently fall into each health status bucket (healthy >=90, degraded >=70, unhealthy >=40, critical below that). 'idle' means no calls in the last 60 minutes -- there's nothing to score, so it's kept separate from 'healthy' rather than defaulting to a misleading perfect score. Click a segment to filter the servers list below." />
          </h3>
          <div style={{ display: "flex", gap: 40, flexWrap: "wrap" }}>
            {healthDist && <DonutChart counts={healthDist} onSegmentClick={filterByStatus} />}
            {severityBreakdown && (
              <div style={{ minWidth: 260 }}>
                <div style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 8 }}>
                  Faults by severity (24h)
                  <InfoTooltip text="Dominant severity from the real MCP fault taxonomy study, attached to each auto-classified fault event. Always shows all three levels, even at zero, so a single-severity result isn't mistaken for a progress bar. Click a bar to see every matching event." />
                </div>
                <SeverityBars counts={severityBreakdown} onBarClick={(sev) => navigate(`/severity/${sev}`)} />
              </div>
            )}
          </div>
        </div>
      )}

      {categoryCounts && categoryCounts.length > 0 && (
        <div className="panel">
          <h3>
            Top fault subcategories (24h, all servers)
            <InfoTooltip text="Auto-classification results against the real 27-subcategory taxonomy, ranked by count. Click 'Fault Taxonomy' in the sidebar for the full reference and per-subcategory drill-down." />
          </h3>
          <BarChart data={categoryCounts} labelKey="subcategory" valueKey="count" color="var(--accent)" />
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 24, flexWrap: "wrap", gap: 10 }}>
        <h3 style={{ margin: 0 }}>
          Servers ({sortedRows.length}
          {sortedRows.length !== servers.length ? ` of ${servers.length}` : ""})
          <InfoTooltip text="Sorted worst-first by default: critical > unhealthy > degraded > healthy > idle. 'idle' means no calls in the last 60 minutes -- not the same as healthy. A crashed or disconnected wrapper looks idle too, so check 'last seen' before assuming everything's fine." />
        </h3>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <input placeholder="Search server..." value={search} onChange={(e) => setSearch(e.target.value)} style={{ width: 160 }} />
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s === "all" ? "All statuses" : s}
              </option>
            ))}
          </select>
          <button onClick={() => setViewMode(viewMode === "cards" ? "table" : "cards")}>
            {viewMode === "cards" ? "Table view" : "Card view"}
          </button>
        </div>
      </div>

      {servers.length === 0 ? (
        <div className="empty-state">
          No servers reporting yet. Wrap a server with <span className="mono">mcp-insight run --server-id X -- ...</span> or
          run the demo in <span className="mono">deploy/</span> to see data here.
        </div>
      ) : sortedRows.length === 0 ? (
        <div className="empty-state">No servers match this filter.</div>
      ) : viewMode === "table" ? (
        <table>
          <thead>
            <tr>
              <th style={{ cursor: "pointer" }} onClick={() => onSort("server_id")}>
                Server{sortIndicator("server_id")}
              </th>
              <th style={{ cursor: "pointer" }} onClick={() => onSort("status")}>
                Status{sortIndicator("status")}
              </th>
              <th style={{ cursor: "pointer" }} onClick={() => onSort("score")}>
                Score{sortIndicator("score")}
              </th>
              <th style={{ cursor: "pointer" }} onClick={() => onSort("error_rate")}>
                Error rate{sortIndicator("error_rate")}
              </th>
              <th style={{ cursor: "pointer" }} onClick={() => onSort("p95")}>
                p95 latency{sortIndicator("p95")}
              </th>
              <th style={{ cursor: "pointer" }} onClick={() => onSort("silent_failures")}>
                Silent failures{sortIndicator("silent_failures")}
              </th>
              <th style={{ cursor: "pointer" }} onClick={() => onSort("last_seen")}>
                Last seen{sortIndicator("last_seen")}
              </th>
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((r) => (
              <tr key={r.server_id} style={{ borderLeft: `3px solid ${STATUS_BORDER_COLOR[r.status]}` }}>
                <td>
                  <Link to={`/servers/${encodeURIComponent(r.server_id)}`}>{r.server_id}</Link>
                  {r.isDemo && (
                    <span style={{ fontSize: 10, color: "var(--text-dim)", border: "1px solid var(--border)", borderRadius: 4, padding: "1px 5px", marginLeft: 6 }}>
                      demo/test
                    </span>
                  )}
                </td>
                <td>
                  <HealthBadge status={r.status} score={null} />
                </td>
                <td>{r.score != null ? r.score : "—"}</td>
                <td>{r.total_calls > 0 ? `${(r.error_rate * 100).toFixed(1)}%` : "—"}</td>
                <td>{r.p95 != null ? `${r.p95.toFixed(0)}ms` : "—"}</td>
                <td>{r.silent_failures}</td>
                <td className="mono">{formatRelativeTime(r.last_seen)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        sortedRows.map((r) => (
          <div key={r.server_id} className="server-card" style={{ borderLeft: `3px solid ${STATUS_BORDER_COLOR[r.status]}` }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span>
                <Link to={`/servers/${encodeURIComponent(r.server_id)}`} className="server-id">
                  {r.server_id}
                </Link>
                {r.isDemo && (
                  <span style={{ fontSize: 10, color: "var(--text-dim)", border: "1px solid var(--border)", borderRadius: 4, padding: "1px 5px", marginLeft: 6 }}>
                    demo/test
                  </span>
                )}
              </span>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <HealthBadge status={r.status} score={r.score} />
              </div>
            </div>
            <div className="meta" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
              <span>
                last seen {formatRelativeTime(r.last_seen)}
                {r.total_calls > 0
                  ? ` — ${r.total_calls} calls (60m), ${(r.error_rate * 100).toFixed(1)}% errors, ${r.silent_failures} silent failures`
                  : " — no activity in the last 60 minutes"}
              </span>
              {r.trend && r.trend.some((v) => v > 0) && (
                <span style={{ width: 90, opacity: 0.85 }}>
                  <Sparkline values={r.trend} height={22} color="var(--critical)" formatValue={(v) => `${(v * 100).toFixed(0)}% err`} />
                </span>
              )}
            </div>
            <div style={{ marginTop: 8 }}>
              <button
                style={{ fontSize: 12, padding: "3px 10px" }}
                disabled={muteBusy === r.server_id}
                onClick={(e) => {
                  e.preventDefault();
                  toggleMute(r.server_id, r.muted);
                }}
              >
                {r.muted ? "Unmute alerts" : "Mute alerts (60m)"}
              </button>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
