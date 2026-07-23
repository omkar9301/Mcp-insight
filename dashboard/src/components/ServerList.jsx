import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ingestionApi } from "../api.js";
import HealthBadge from "./HealthBadge.jsx";
import InfoTooltip from "./InfoTooltip.jsx";
import DonutChart from "./charts/DonutChart.jsx";
import BarChart from "./charts/BarChart.jsx";
import StackedBar from "./charts/StackedBar.jsx";

export default function ServerList() {
  const [servers, setServers] = useState(null);
  const [healths, setHealths] = useState({});
  const [healthDist, setHealthDist] = useState(null);
  const [severityBreakdown, setSeverityBreakdown] = useState(null);
  const [categoryCounts, setCategoryCounts] = useState(null);
  const [error, setError] = useState(null);

  async function load() {
    try {
      const [data, hd, sb, cc] = await Promise.all([
        ingestionApi.listServers(),
        ingestionApi.getHealthDistribution(),
        ingestionApi.getSeverityBreakdown(),
        ingestionApi.getCategoryCounts(),
      ]);
      setServers(data.servers || []);
      setHealthDist(hd.counts);
      setSeverityBreakdown(sb.counts);
      setCategoryCounts(cc.rows.slice(0, 8));
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
      setHealths(Object.fromEntries(entries));
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, []);

  if (error) return <div className="error-banner">Failed to load servers: {error}</div>;
  if (servers === null) return <div className="empty-state">Loading...</div>;

  const totalCalls = Object.values(healths).reduce((sum, h) => sum + (h?.total_calls || 0), 0);
  const avgScore = (() => {
    const scores = Object.values(healths).filter((h) => h?.health_score != null).map((h) => h.health_score);
    return scores.length ? (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1) : "—";
  })();

  return (
    <div>
      <h2>Overview</h2>

      <div className="grid">
        <div className="stat-tile">
          <div className="label">Servers</div>
          <div className="value">{servers.length}</div>
        </div>
        <div className="stat-tile">
          <div className="label">
            Avg health score
            <InfoTooltip text="Mean of each server's 0-100 health score (weighted error rate, silent failures, latency, process pressure, and taxonomy severity). See a server's page for the exact formula breakdown." />
          </div>
          <div className="value">{avgScore}</div>
        </div>
        <div className="stat-tile">
          <div className="label">Calls (60m, all servers)</div>
          <div className="value">{totalCalls}</div>
        </div>
      </div>

      {(healthDist || severityBreakdown) && (
        <div className="panel">
          <h3>
            Fleet health
            <InfoTooltip text="How many servers currently fall into each health status bucket (healthy >=90, degraded >=70, unhealthy >=40, critical below that)." />
          </h3>
          <div style={{ display: "flex", gap: 40, flexWrap: "wrap" }}>
            {healthDist && <DonutChart counts={healthDist} />}
            {severityBreakdown && Object.keys(severityBreakdown).length > 0 && (
              <div style={{ minWidth: 260 }}>
                <div style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 8 }}>
                  Faults by severity (24h)
                  <InfoTooltip text="Dominant severity from the real MCP fault taxonomy study, attached to each auto-classified fault event." />
                </div>
                <StackedBar counts={severityBreakdown} />
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

      <h3 style={{ marginTop: 24 }}>Servers</h3>
      {servers.length === 0 ? (
        <div className="empty-state">
          No servers reporting yet. Wrap a server with <span className="mono">mcp-insight run --server-id X -- ...</span> or
          run the demo in <span className="mono">deploy/</span> to see data here.
        </div>
      ) : (
        servers.map((s) => {
          const h = healths[s.server_id];
          return (
            <Link key={s.server_id} to={`/servers/${encodeURIComponent(s.server_id)}`} className="server-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="server-id">{s.server_id}</span>
                <HealthBadge status={h?.health_status} score={h?.health_score} />
              </div>
              <div className="meta">
                last seen {s.last_seen ? new Date(s.last_seen * 1000).toLocaleString() : "never"}
                {h ? ` — ${h.total_calls} calls, ${(h.error_rate * 100).toFixed(1)}% errors, ${h.silent_failure_count} silent failures` : ""}
              </div>
            </Link>
          );
        })
      )}
    </div>
  );
}
