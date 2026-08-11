import React, { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ingestionApi, ApiError } from "../api.js";
import InfoTooltip from "./InfoTooltip.jsx";
import BarChart from "./charts/BarChart.jsx";
import Histogram from "./charts/Histogram.jsx";
import ScatterChart from "./charts/ScatterChart.jsx";
import Sparkline from "./Sparkline.jsx";
import LitmPipelineDiagram from "./LitmPipelineDiagram.jsx";
import LitmCounterfactualPanel from "./LitmCounterfactualPanel.jsx";
import { formatRelativeTime } from "../utils.js";

const LIMITATIONS_TEXT =
  "What this page can prove: the exact input and output of every flagged call, the exact threshold math behind " +
  "each risk factor, and how the same real scores would look under standard mitigations. What it cannot prove: " +
  "what the AI model actually answered (this system never sees the model's completion), whether there was a " +
  "'correct' answer it missed (no ground truth exists here), or that any of this caused real harm to a user -- " +
  "those all require visibility this MCP-layer wrapper structurally does not have. Every AI-generated explanation " +
  "below is a labeled hypothesis, not a proven fact.";

function DecisionTrailTable({ trail }) {
  if (!trail || trail.length === 0) return <div className="empty-state">No decision trail captured.</div>;
  return (
    <table>
      <thead>
        <tr>
          <th>Check</th>
          <th>Fired?</th>
          <th>Threshold</th>
          <th>Actual</th>
          <th>Detail</th>
        </tr>
      </thead>
      <tbody>
        {trail.map((row, i) => (
          <tr key={i}>
            <td className="mono">{row.check}</td>
            <td style={{ color: row.fired ? "var(--degraded)" : "var(--text-dim)", fontWeight: row.fired ? 600 : 400 }}>
              {row.fired ? "fired" : "no"}
            </td>
            <td className="mono" style={{ fontSize: 11 }}>{String(row.threshold)}</td>
            <td className="mono" style={{ fontSize: 11 }}>
              {Array.isArray(row.actual) ? row.actual.map((v) => v.toFixed(2)).join(", ") : String(row.actual)}
            </td>
            <td style={{ fontSize: 11, color: "var(--text-dim)" }}>{row.detail}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function EventDeepDive({ event }) {
  const signal = event.lost_in_middle;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div>
        <div style={{ fontSize: 11, color: "var(--text-dim)", textTransform: "uppercase", marginBottom: 4 }}>Input</div>
        <div className="mono" style={{ fontSize: 12, background: "var(--border)", padding: 8, borderRadius: 4, wordBreak: "break-word" }}>
          {signal.input_preview || "—"}
        </div>
      </div>

      <div>
        <div style={{ fontSize: 11, color: "var(--text-dim)", textTransform: "uppercase", marginBottom: 4 }}>
          Live pipeline view
        </div>
        <LitmPipelineDiagram signal={signal} />
      </div>

      <div>
        <div style={{ fontSize: 11, color: "var(--text-dim)", textTransform: "uppercase", marginBottom: 4 }}>
          Decision trail -- exact rule evaluation
        </div>
        <DecisionTrailTable trail={signal.decision_trail} />
      </div>

      {signal.items && signal.items.length > 0 && (
        <>
          <div>
            <div style={{ fontSize: 11, color: "var(--text-dim)", textTransform: "uppercase", marginBottom: 4 }}>
              Position vs. relevance score (this call's actual output)
            </div>
            <ScatterChart points={signal.items} />
          </div>

          <div>
            <div style={{ fontSize: 11, color: "var(--text-dim)", textTransform: "uppercase", marginBottom: 4 }}>
              Counterfactual replay -- what a fix would change
            </div>
            <LitmCounterfactualPanel items={signal.items} />
          </div>

          <div>
            <div style={{ fontSize: 11, color: "var(--text-dim)", textTransform: "uppercase", marginBottom: 4 }}>
              Output -- captured items ({signal.items.length})
            </div>
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Score</th>
                  <th>Content preview</th>
                </tr>
              </thead>
              <tbody>
                {signal.items.map((it) => (
                  <tr key={it.position}>
                    <td className="mono">{it.position}</td>
                    <td className="mono">{it.score != null ? it.score.toFixed(3) : "—"}</td>
                    <td style={{ fontSize: 12 }}>{it.preview || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function ToolDrilldown({ serverId, toolName, onBack }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);
  const [selectedTs, setSelectedTs] = useState(null);

  useEffect(() => {
    setDetail(null);
    setError(null);
    setSelectedTs(null);
    ingestionApi
      .getLitmToolDetail(serverId, toolName)
      .then((d) => {
        setDetail(d);
        if (d.recent_events?.length) setSelectedTs(d.recent_events[0].ts);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [serverId, toolName]);

  if (error) return <div className="error-banner">{error}</div>;
  if (!detail) return <div className="empty-state">Loading tool detail...</div>;

  const selectedEvent = detail.recent_events.find((e) => e.ts === selectedTs) || detail.recent_events[0];
  const riskFactorData = Object.entries(detail.risk_factor_counts || {}).map(([factor, count]) => ({ label: factor, value: count }));

  return (
    <div>
      <button style={{ fontSize: 12, marginBottom: 12 }} onClick={onBack}>
        ← Back to fleet overview
      </button>
      <h2>
        {toolName} <span style={{ fontWeight: 400, color: "var(--text-dim)", fontSize: 15 }}>on {serverId}</span>
      </h2>

      <div className="grid">
        <div className="stat-tile">
          <div className="label">Flagged calls</div>
          <div className="value">{detail.flagged_calls}</div>
        </div>
        <div className="stat-tile">
          <div className="label">Repeated-query rate</div>
          <div className="value">{(detail.repeated_query_rate * 100).toFixed(0)}%</div>
        </div>
        <div className="stat-tile">
          <div className="label">Items with scores captured</div>
          <div className="value">{detail.score_distribution.length}</div>
        </div>
      </div>

      <div className="panel">
        <h3>Risk factors for this tool</h3>
        {riskFactorData.length > 0 ? <BarChart data={riskFactorData} color="var(--degraded)" /> : <div className="empty-state">None.</div>}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div className="panel">
          <h3>Score distribution across all flagged calls</h3>
          <Histogram values={detail.score_distribution} bins={10} color="var(--accent)" />
        </div>
        <div className="panel">
          <h3>Result-count distribution</h3>
          <Histogram values={detail.result_count_distribution} bins={8} color="var(--degraded)" formatBin={(a, b) => `${Math.round(a)}–${Math.round(b)} items`} />
        </div>
      </div>

      <div className="panel">
        <h3>Flagged calls -- select one to deep-dive</h3>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
          {detail.recent_events.map((e) => (
            <button
              key={e.ts}
              onClick={() => setSelectedTs(e.ts)}
              style={{
                fontSize: 11,
                padding: "3px 8px",
                background: e.ts === selectedEvent?.ts ? "var(--accent)" : undefined,
                color: e.ts === selectedEvent?.ts ? "#fff" : undefined,
              }}
            >
              {formatRelativeTime(e.ts)}
            </button>
          ))}
        </div>
        {selectedEvent && <EventDeepDive event={selectedEvent} />}
      </div>
    </div>
  );
}

export default function LostInMiddleInsights() {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);
  const [params, setParams] = useSearchParams();

  const drillServer = params.get("server");
  const drillTool = params.get("tool");

  useEffect(() => {
    ingestionApi
      .getLitmDeepSummary()
      .then(setSummary)
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, []);

  function openTool(serverId, toolName) {
    setParams({ server: serverId, tool: toolName });
  }

  function backToOverview() {
    setParams({});
  }

  if (drillServer && drillTool) {
    return <ToolDrilldown serverId={drillServer} toolName={drillTool} onBack={backToOverview} />;
  }

  if (error) return <div className="error-banner">{error}</div>;
  if (!summary) return <div className="empty-state">Loading...</div>;

  const riskData = Object.entries(summary.risk_factor_counts || {}).map(([label, value]) => ({ label, value }));
  const trendValues = (summary.trend || []).map((p) => p.flagged_calls);

  return (
    <div>
      <h2>
        ⚠️ Lost in the Middle -- deep-dive insights
        <InfoTooltip text="Everything this platform can honestly determine about Lost-in-the-Middle risk (Liu et al., TACL 2023/2024), all in one place: input/output capture, the exact rule trace behind every flag, real-data counterfactual replay, position-vs-score visualization, and a live pipeline view. See the limitations note below for what this can and cannot prove." />
      </h2>
      <p style={{ fontSize: 12, color: "var(--text-dim)" }}>{LIMITATIONS_TEXT}</p>

      <div className="grid">
        <div className="stat-tile">
          <div className="label">Total flagged (30d)</div>
          <div className="value">{summary.total_flagged}</div>
        </div>
        <div className="stat-tile">
          <div className="label">Servers affected</div>
          <div className="value">{summary.servers_affected}</div>
        </div>
        <div className="stat-tile">
          <div className="label">Distinct tools flagged</div>
          <div className="value">{summary.leaderboard?.length || 0}</div>
        </div>
      </div>

      <div className="panel">
        <h3>Trend, fleet-wide</h3>
        {trendValues.some((v) => v > 0) ? (
          <Sparkline values={trendValues} height={70} formatValue={(v) => `${v} flagged calls`} />
        ) : (
          <div className="empty-state">No flagged calls in this window.</div>
        )}
      </div>

      <div className="panel">
        <h3>Risk factor breakdown, fleet-wide</h3>
        {riskData.length > 0 ? <BarChart data={riskData} color="var(--degraded)" /> : <div className="empty-state">None flagged.</div>}
      </div>

      <div className="panel">
        <h3>Worst offenders -- click through for the full deep dive</h3>
        {!summary.leaderboard || summary.leaderboard.length === 0 ? (
          <div className="empty-state">Nothing flagged yet.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Server</th>
                <th>Tool</th>
                <th>Flagged calls</th>
                <th>Last seen</th>
              </tr>
            </thead>
            <tbody>
              {summary.leaderboard.map((row, i) => (
                <tr key={i}>
                  <td>
                    <Link to={`/servers/${encodeURIComponent(row.server_id)}`}>{row.server_id}</Link>
                  </td>
                  <td className="mono">
                    <button style={{ fontSize: 12 }} onClick={() => openTool(row.server_id, row.tool_name)}>
                      {row.tool_name} →
                    </button>
                  </td>
                  <td>{row.flagged_calls}</td>
                  <td className="mono">{formatRelativeTime(row.last_seen)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
