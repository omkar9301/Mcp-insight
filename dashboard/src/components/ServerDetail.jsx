import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ingestionApi } from "../api.js";
import HealthBadge from "./HealthBadge.jsx";
import Sparkline from "./Sparkline.jsx";

function StatTile({ label, value }) {
  return (
    <div className="stat-tile">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}

function classificationLabel(c) {
  if (!c) return "—";
  const conf = c.confidence != null ? ` (${(c.confidence * 100).toFixed(0)}%)` : c.source === "llm" ? " (llm)" : "";
  return `${c.category} / ${c.subcategory}${conf}`;
}

export default function ServerDetail() {
  const { serverId } = useParams();
  const [health, setHealth] = useState(null);
  const [anomalies, setAnomalies] = useState(null);
  const [events, setEvents] = useState(null);
  const [timeseries, setTimeseries] = useState(null);
  const [alertHistory, setAlertHistory] = useState(null);
  const [onlyFaults, setOnlyFaults] = useState(true);
  const [error, setError] = useState(null);
  const [keyResult, setKeyResult] = useState(null);
  const [muteMinutes, setMuteMinutes] = useState(60);

  async function load() {
    try {
      const [h, a, e, ts, al] = await Promise.all([
        ingestionApi.getHealth(serverId, 60),
        ingestionApi.getAnomalies(serverId, 15),
        ingestionApi.getEvents(serverId, { onlyFaults, limit: 50 }),
        ingestionApi.getTimeseries(serverId, 15, 24),
        ingestionApi.getAlertHistory(serverId, 20),
      ]);
      setHealth(h);
      setAnomalies(a);
      setEvents(e.events);
      setTimeseries(ts.buckets);
      setAlertHistory(al.alerts);
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverId, onlyFaults]);

  async function onMint() {
    try {
      setKeyResult(await ingestionApi.mintKey(serverId));
    } catch (e) {
      setError(e.message);
    }
  }

  async function onRevoke() {
    try {
      await ingestionApi.revokeKey(serverId);
      setKeyResult(null);
    } catch (e) {
      setError(e.message);
    }
  }

  async function onMute() {
    try {
      await ingestionApi.muteAlerts(serverId, muteMinutes);
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  async function onUnmute() {
    try {
      await ingestionApi.unmuteAlerts(serverId);
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  const muted = health?.alerts_muted_until && health.alerts_muted_until > Date.now() / 1000;

  return (
    <div>
      <p>
        <Link to="/">&larr; all servers</Link>
      </p>
      <h2>
        {serverId} <HealthBadge status={health?.health_status} score={health?.health_score} />
      </h2>

      {error && <div className="error-banner">{error}</div>}

      {health && (
        <>
          <div className="grid">
            <StatTile label="Total calls (60m)" value={health.total_calls} />
            <StatTile label="Error rate" value={`${(health.error_rate * 100).toFixed(1)}%`} />
            <StatTile label="Silent failures" value={health.silent_failure_count} />
            <StatTile label="p50 latency" value={health.p50_latency_ms ? `${health.p50_latency_ms.toFixed(0)}ms` : "—"} />
            <StatTile label="p95 latency" value={health.p95_latency_ms ? `${health.p95_latency_ms.toFixed(0)}ms` : "—"} />
            <StatTile label="p99 latency" value={health.p99_latency_ms ? `${health.p99_latency_ms.toFixed(0)}ms` : "—"} />
            <StatTile
              label="Avg CPU"
              value={health.process_metrics?.avg_cpu_percent != null ? `${health.process_metrics.avg_cpu_percent.toFixed(1)}%` : "—"}
            />
            <StatTile
              label="Memory (RSS)"
              value={
                health.process_metrics?.latest_memory_rss_bytes != null
                  ? `${(health.process_metrics.latest_memory_rss_bytes / 1024 / 1024).toFixed(1)} MB`
                  : "—"
              }
            />
            <StatTile label="Dropped events" value={health.dropped_events_total} />
          </div>

          <div className="panel">
            <h3>Health score breakdown</h3>
            <table>
              <tbody>
                {Object.entries(health.health_breakdown || {}).map(([k, v]) => (
                  <tr key={k}>
                    <td>{k.replace(/_/g, " ")}</td>
                    <td>-{v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {timeseries && timeseries.some((b) => b.total_calls > 0) && (
        <div className="panel">
          <h3>Trend (last 6h, 15m buckets)</h3>
          <div style={{ marginBottom: 16 }}>
            <div className="label" style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 4 }}>
              Error rate
            </div>
            <Sparkline values={timeseries.map((b) => b.error_rate)} color="var(--critical)" formatValue={(v) => `${(v * 100).toFixed(1)}%`} />
          </div>
          <div>
            <div className="label" style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 4 }}>
              p95 latency (ms)
            </div>
            <Sparkline values={timeseries.map((b) => b.p95_latency_ms || 0)} color="var(--accent)" />
          </div>
        </div>
      )}

      {anomalies && (
        <div className="panel">
          <h3>Anomalies (z-score vs. rolling history)</h3>
          {anomalies.anomalies.length === 0 ? (
            <div className="empty-state">No anomalies detected.</div>
          ) : (
            <ul>
              {anomalies.anomalies.map((a, i) => (
                <li key={i}>
                  <strong>{a.kind.replace(/_/g, " ")}</strong>: current {JSON.stringify(a.current)}, baseline avg {JSON.stringify(a.baseline)}
                  {a.zscore ? ` (z=${a.zscore})` : ""}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="panel">
        <h3>Alerts</h3>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12 }}>
          {muted ? (
            <>
              <span className="badge degraded">muted</span>
              <button onClick={onUnmute}>Unmute</button>
            </>
          ) : (
            <>
              <input
                type="number"
                value={muteMinutes}
                onChange={(e) => setMuteMinutes(Number(e.target.value))}
                style={{ width: 70 }}
              />
              <span style={{ fontSize: 13 }}>minutes</span>
              <button onClick={onMute}>Mute</button>
            </>
          )}
        </div>
        {!alertHistory || alertHistory.length === 0 ? (
          <div className="empty-state">No alerts sent yet.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Kind</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              {alertHistory.map((a, i) => (
                <tr key={i}>
                  <td className="mono">{new Date(a.sent_at * 1000).toLocaleString()}</td>
                  <td>{a.kind}</td>
                  <td style={{ whiteSpace: "pre-wrap" }}>{a.text}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel">
        <h3>Per-server API key</h3>
        <p style={{ fontSize: 13, color: "var(--text-dim)" }}>
          Mint a key scoped to this server_id only -- use it as <span className="mono">--api-key</span> on the
          wrapper instead of the admin key. Rotating invalidates the previous key.
        </p>
        <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
          <button onClick={onMint}>Mint / rotate key</button>
          <button onClick={onRevoke}>Revoke key</button>
        </div>
        {keyResult && (
          <div className="error-banner" style={{ borderColor: "var(--healthy)", color: "var(--text)" }}>
            <div className="mono" style={{ wordBreak: "break-all" }}>{keyResult.api_key}</div>
            <div style={{ fontSize: 12, marginTop: 4, color: "var(--text-dim)" }}>{keyResult.note}</div>
          </div>
        )}
      </div>

      <div className="panel">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <h3 style={{ margin: 0 }}>Recent events</h3>
          <label style={{ fontSize: 13 }}>
            <input type="checkbox" checked={onlyFaults} onChange={(e) => setOnlyFaults(e.target.checked)} /> faults only
          </label>
        </div>
        {!events || events.length === 0 ? (
          <div className="empty-state">No events yet.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Type</th>
                <th>Method</th>
                <th>Latency</th>
                <th>Fault</th>
                <th>Classification</th>
              </tr>
            </thead>
            <tbody>
              {events.map((ev, i) => (
                <tr key={i}>
                  <td className="mono">{new Date(ev.ts * 1000).toLocaleTimeString()}</td>
                  <td>{ev.type}</td>
                  <td>{ev.method || "—"}</td>
                  <td>{ev.latency_ms != null ? `${ev.latency_ms.toFixed(0)}ms` : "—"}</td>
                  <td>
                    {ev.is_error && "error "}
                    {ev.silent_failure && "silent-failure "}
                    {ev.type === "protocol_violation" && ev.subtype}
                  </td>
                  <td>{classificationLabel(ev.classification)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
