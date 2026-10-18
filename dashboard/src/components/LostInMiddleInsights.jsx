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
import { RISK_INFO } from "./LostInMiddlePanel.jsx";
import { formatRelativeTime } from "../utils.js";

// Every technical check has a plain-English name, shown everywhere
// instead of the raw code (e.g. "unranked_results") -- a first-time
// reader should never have to decode a variable name to follow the page.
const CHECK_LABELS = {
  large_result_set: "Too many results at once",
  unranked_results: "Best answer wasn't listed first",
  size_outlier: "Unusually large response",
  repeated_query_after_large_context: "AI had to ask again",
};

function plainCheckName(check) {
  return CHECK_LABELS[check] || check;
}

const WHAT_TEXT =
  "WHAT: some AI tools on your servers are sending back information in a shape that's known to confuse AI models -- " +
  "too much at once, not sorted by usefulness, or asked again because the first answer didn't help.";
const WHY_TEXT =
  "WHY IT MATTERS: AI models pay less attention to information buried in the middle of a large answer, even though " +
  "it's technically there. If the right answer is buried, the AI may give a worse response without anyone noticing.";
const WHAT_CAN_PROVE =
  "WHAT WE CAN SHOW YOU: exactly what went in and came out of each flagged call, exactly why it was flagged (down " +
  "to the numbers), and what the same real data would look like if it were fixed.";
const WHAT_WE_CANT_PROVE =
  "WHAT WE CAN'T SHOW YOU: what the AI actually said to the user afterward, or proof that this caused a real " +
  "mistake -- this tool can only see the search results, not the AI's final answer or the 'correct' answer. Any " +
  "AI-written explanation below is a best-guess, clearly labeled as such, not a fact.";

function DecisionTrailTable({ trail }) {
  if (!trail || trail.length === 0) return <div className="empty-state">Nothing to show.</div>;
  return (
    <table>
      <thead>
        <tr>
          <th>Rule checked</th>
          <th>Did it trigger?</th>
          <th>Limit</th>
          <th>What we actually saw</th>
        </tr>
      </thead>
      <tbody>
        {trail.map((row, i) => (
          <tr key={i}>
            <td>{plainCheckName(row.check)}</td>
            <td style={{ color: row.fired ? "var(--degraded)" : "var(--healthy)", fontWeight: 600 }}>
              {row.fired ? "⚠️ Yes, triggered" : "✓ No, fine"}
            </td>
            <td className="mono" style={{ fontSize: 11 }}>{String(row.threshold)}</td>
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
        <div style={{ fontSize: 11, color: "var(--text-dim)", textTransform: "uppercase", marginBottom: 4 }}>
          What was asked
        </div>
        <div className="mono" style={{ fontSize: 12, background: "var(--border)", padding: 8, borderRadius: 4, wordBreak: "break-word" }}>
          {signal.input_preview || "—"}
        </div>
      </div>

      <div>
        <div style={{ fontSize: 11, color: "var(--text-dim)", textTransform: "uppercase", marginBottom: 4 }}>
          How the request moved through the system
        </div>
        <LitmPipelineDiagram signal={signal} />
      </div>

      <div>
        <div style={{ fontSize: 11, color: "var(--text-dim)", textTransform: "uppercase", marginBottom: 4 }}>
          Why this was flagged (the exact rules we checked)
        </div>
        <DecisionTrailTable trail={signal.decision_trail} />
      </div>

      {signal.items && signal.items.length > 0 && (
        <>
          <div>
            <div style={{ fontSize: 11, color: "var(--text-dim)", textTransform: "uppercase", marginBottom: 4 }}>
              Where the best answer ended up
            </div>
            <ScatterChart points={signal.items} />
          </div>

          <div>
            <div style={{ fontSize: 11, color: "var(--text-dim)", textTransform: "uppercase", marginBottom: 4 }}>
              What a fix would look like
            </div>
            <LitmCounterfactualPanel items={signal.items} />
          </div>

          <div>
            <div style={{ fontSize: 11, color: "var(--text-dim)", textTransform: "uppercase", marginBottom: 4 }}>
              What actually came back ({signal.items.length} results)
            </div>
            <table>
              <thead>
                <tr>
                  <th>Position</th>
                  <th>Relevance score</th>
                  <th>Preview</th>
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
    let firstLoad = true;
    function load() {
      ingestionApi
        .getLitmToolDetail(serverId, toolName)
        .then((d) => {
          setDetail(d);
          // Only default the selection on the initial load -- a refresh
          // tick must never yank a manually-picked incident out from
          // under the reader mid-review.
          if (firstLoad && d.recent_events?.length) setSelectedTs(d.recent_events[0].ts);
          firstLoad = false;
          setError(null);
        })
        .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
    }
    load();
    const id = setInterval(load, 20000);
    return () => clearInterval(id);
  }, [serverId, toolName]);

  if (error) return <div className="error-banner">{error}</div>;
  if (!detail) return <div className="empty-state">Loading...</div>;

  const selectedEvent = detail.recent_events.find((e) => e.ts === selectedTs) || detail.recent_events[0];
  const riskFactorData = Object.entries(detail.risk_factor_counts || {}).map(([factor, count]) => ({
    label: RISK_INFO[factor]?.label || factor,
    value: count,
  }));

  return (
    <div>
      <button style={{ fontSize: 12, marginBottom: 12 }} onClick={onBack}>
        ← Back to overview
      </button>
      <h2>
        {toolName} <span style={{ fontWeight: 400, color: "var(--text-dim)", fontSize: 15 }}>on {serverId}</span>
      </h2>
      <p style={{ fontSize: 12, color: "var(--text-dim)", marginTop: -6 }}>
        A closer look at this one tool: how often it's happened, what the results looked like overall, and a
        pick-one-incident deep dive below.
      </p>

      <div className="grid">
        <div className="stat-tile">
          <div className="label">How many times this happened</div>
          <div className="value">{detail.flagged_calls}</div>
        </div>
        <div className="stat-tile">
          <div className="label">% of times AI had to ask again</div>
          <div className="value">{(detail.repeated_query_rate * 100).toFixed(0)}%</div>
        </div>
        <div className="stat-tile">
          <div className="label">Total results looked at</div>
          <div className="value">{detail.score_distribution.length}</div>
        </div>
      </div>

      <div className="panel">
        <h3>What kind of problem is it?</h3>
        {riskFactorData.length > 0 ? <BarChart data={riskFactorData} color="var(--degraded)" /> : <div className="empty-state">Nothing flagged.</div>}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div className="panel">
          <h3>
            How good were the results, overall?
            <InfoTooltip text="Each result the tool ever returned has a relevance score from 0 (useless) to 1 (perfect match). This chart groups all of them together so you can see if this tool tends to return good matches or a lot of noise." />
          </h3>
          <Histogram
            values={detail.score_distribution}
            bins={10}
            color="var(--accent)"
            xLabel="match quality score (0 = bad, 1 = perfect)"
            yLabel="number of results"
          />
        </div>
        <div className="panel">
          <h3>
            How many results came back each time?
            <InfoTooltip text="How many items this tool sent to the AI, per call. Higher bars on the right mean this tool often sends a lot at once — the more it sends, the more likely something gets buried and missed." />
          </h3>
          <Histogram
            values={detail.result_count_distribution}
            bins={8}
            color="var(--degraded)"
            xLabel="results sent in one call"
            yLabel="number of calls"
          />
        </div>
      </div>

      <div className="panel">
        <h3>Pick one incident to inspect closely</h3>
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
    function load() {
      ingestionApi
        .getLitmDeepSummary()
        .then((d) => {
          setSummary(d);
          setError(null);
        })
        .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
    }
    load();
    const id = setInterval(load, 20000);
    return () => clearInterval(id);
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

  const riskData = Object.entries(summary.risk_factor_counts || {}).map(([factor, value]) => ({
    label: RISK_INFO[factor]?.label || factor,
    value,
  }));
  const trendValues = (summary.trend || []).map((p) => p.flagged_calls);

  return (
    <div>
      <h2>
        ⚠️ Is the AI missing information? (Lost in the Middle)
        <InfoTooltip text={`${WHAT_TEXT}  ${WHY_TEXT}`} />
      </h2>
      <div className="panel" style={{ background: "rgba(76, 158, 255, 0.06)", borderColor: "var(--accent)" }}>
        <p style={{ fontSize: 13, margin: "0 0 6px 0" }}>{WHAT_TEXT}</p>
        <p style={{ fontSize: 13, margin: "0 0 6px 0" }}>{WHY_TEXT}</p>
        <p style={{ fontSize: 12, color: "var(--text-dim)", margin: "8px 0 2px 0" }}>{WHAT_CAN_PROVE}</p>
        <p style={{ fontSize: 12, color: "var(--text-dim)", margin: 0 }}>{WHAT_WE_CANT_PROVE}</p>
      </div>

      <div className="grid">
        <div className="stat-tile">
          <div className="label">Times flagged (last 30 days)</div>
          <div className="value">{summary.total_flagged}</div>
        </div>
        <div className="stat-tile">
          <div className="label">Servers with an issue</div>
          <div className="value">{summary.servers_affected}</div>
        </div>
        <div className="stat-tile">
          <div className="label">Tools that need a look</div>
          <div className="value">{summary.leaderboard?.length || 0}</div>
        </div>
      </div>

      <div className="panel">
        <h3>Is this getting more common over time?</h3>
        {trendValues.some((v) => v > 0) ? (
          <Sparkline values={trendValues} height={70} formatValue={(v) => `${v} flagged calls`} />
        ) : (
          <div className="empty-state">Nothing flagged in this time window.</div>
        )}
      </div>

      <div className="panel">
        <h3>What kind of problem is it, across everything?</h3>
        {riskData.length > 0 ? <BarChart data={riskData} color="var(--degraded)" /> : <div className="empty-state">Nothing flagged.</div>}
      </div>

      <div className="panel">
        <h3>Which tools need attention first? (click a tool to inspect it)</h3>
        {!summary.leaderboard || summary.leaderboard.length === 0 ? (
          <div className="empty-state">Nothing flagged yet — nothing to review.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Server</th>
                <th>Tool</th>
                <th>How many times</th>
                <th>Last happened</th>
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
