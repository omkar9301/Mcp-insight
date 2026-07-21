import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ingestionApi } from "../api.js";
import HealthBadge from "./HealthBadge.jsx";

function StatTile({ label, value }) {
  return (
    <div className="stat-tile">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}

export default function ServerDetail() {
  const { serverId } = useParams();
  const [health, setHealth] = useState(null);
  const [anomalies, setAnomalies] = useState(null);
  const [events, setEvents] = useState(null);
  const [onlyFaults, setOnlyFaults] = useState(true);
  const [error, setError] = useState(null);

  async function load() {
    try {
      const [h, a, e] = await Promise.all([
        ingestionApi.getHealth(serverId, 60),
        ingestionApi.getAnomalies(serverId, 15),
        ingestionApi.getEvents(serverId, { onlyFaults, limit: 50 }),
      ]);
      setHealth(h);
      setAnomalies(a);
      setEvents(e.events);
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

      {anomalies && (
        <div className="panel">
          <h3>Anomalies (last 15m vs. previous 15m)</h3>
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
                  <td>
                    {ev.classification
                      ? `${ev.classification.category} / ${ev.classification.subcategory} (${(ev.classification.confidence * 100).toFixed(0)}%)`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
