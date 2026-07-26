import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { classifierApi, ingestionApi } from "../api.js";
import InfoTooltip from "./InfoTooltip.jsx";
import BarChart from "./charts/BarChart.jsx";
import AdvisoryPanel from "./AdvisoryPanel.jsx";

function dominant(dist) {
  if (!dist || Object.keys(dist).length === 0) return "—";
  return Object.entries(dist).sort((a, b) => b[1] - a[1])[0][0];
}

function severityBadgeClass(sev) {
  if (sev === "critical") return "critical";
  if (sev === "major") return "unhealthy";
  return "healthy";
}

export default function TaxonomyDrilldown() {
  const { category, subcategory } = useParams();
  const [data, setData] = useState(null);
  const [taxonomyRow, setTaxonomyRow] = useState(null);
  const [error, setError] = useState(null);
  const [feedbackGiven, setFeedbackGiven] = useState({});

  async function load() {
    try {
      const [d, t] = await Promise.all([
        ingestionApi.getEventsByClassification(category, subcategory, 100),
        classifierApi.getTaxonomy(),
      ]);
      setData(d);
      setTaxonomyRow(t.taxonomy.find((row) => row.category === category && row.subcategory === subcategory));
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category, subcategory]);

  async function onFeedback(ev, correct) {
    try {
      await ingestionApi.submitFeedback(ev.server_id, ev.ts, correct);
      setFeedbackGiven((prev) => ({ ...prev, [`${ev.server_id}:${ev.ts}`]: correct }));
    } catch (e) {
      setError(e.message);
    }
  }

  if (error) return <div className="error-banner">{error}</div>;
  if (!data || !taxonomyRow) return <div className="empty-state">Loading...</div>;

  const events = data.events;
  const perServerChart = Object.entries(data.per_server_counts || {})
    .map(([server_id, count]) => ({ server_id, count }))
    .sort((a, b) => b.count - a.count);

  return (
    <div>
      <p>
        <Link to="/taxonomy">&larr; taxonomy</Link>
      </p>
      <h2>
        {category} / {subcategory}
      </h2>

      <div className="panel">
        <p style={{ fontSize: 14, marginTop: 0 }}>{taxonomyRow.text}</p>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", fontSize: 13 }}>
          <span>
            Practitioner-confirmed:{" "}
            <strong>{taxonomyRow.confirmed_pct != null ? `${taxonomyRow.confirmed_pct}%` : "—"}</strong> of studied fault
            threads
            <InfoTooltip text="Of the real bug reports studied for this taxonomy, this is the percentage that were confirmed to actually be this exact fault type -- higher means it's a common, well-established problem, not a rare edge case." />
          </span>
          <span>
            Dominant severity:{" "}
            <span className={`badge ${severityBadgeClass(dominant(taxonomyRow.severity))}`}>{dominant(taxonomyRow.severity)}</span>
          </span>
          <span>
            Dominant effort: <strong>{dominant(taxonomyRow.effort)}</strong>
            <InfoTooltip text="How much engineering effort fixing this fault type usually takes, per the source study -- low/medium/high." />
          </span>
        </div>
      </div>

      <div className="grid">
        <div className="stat-tile">
          <div className="label">Total occurrences</div>
          <div className="value">{data.total_count}</div>
        </div>
        <div className="stat-tile">
          <div className="label">Servers affected</div>
          <div className="value">{data.distinct_servers}</div>
        </div>
        <div className="stat-tile">
          <div className="label">First seen</div>
          <div className="value" style={{ fontSize: 14 }}>
            {data.first_seen ? new Date(data.first_seen * 1000).toLocaleString() : "—"}
          </div>
        </div>
        <div className="stat-tile">
          <div className="label">Last seen</div>
          <div className="value" style={{ fontSize: 14 }}>
            {data.last_seen ? new Date(data.last_seen * 1000).toLocaleString() : "—"}
          </div>
        </div>
      </div>

      {perServerChart.length > 1 && (
        <div className="panel">
          <h3>Occurrences by server</h3>
          <BarChart data={perServerChart} labelKey="server_id" valueKey="count" color="var(--critical)" />
        </div>
      )}

      <div className="panel">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ margin: 0 }}>
            Events (most recent {events.length} of {data.total_count})
          </h3>
        </div>
        {events.length === 0 ? (
          <div className="empty-state">No events classified into this subcategory yet.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Server</th>
                <th>Tool / Method</th>
                <th>Confidence</th>
                <th>Issue</th>
                <th>Is this right?</th>
                <th>AI Advisory</th>
              </tr>
            </thead>
            <tbody>
              {events.map((ev, i) => {
                const key = `${ev.server_id}:${ev.ts}`;
                return (
                  <tr key={i}>
                    <td className="mono">{new Date(ev.ts * 1000).toLocaleString()}</td>
                    <td>
                      <Link to={`/servers/${encodeURIComponent(ev.server_id)}`}>{ev.server_id}</Link>
                    </td>
                    <td>{ev.schema_violation?.tool || ev.method || "—"}</td>
                    <td>
                      {ev.classification?.confidence != null
                        ? `${(ev.classification.confidence * 100).toFixed(0)}%`
                        : ev.classification?.source === "llm"
                          ? "llm"
                          : "—"}
                    </td>
                    <td>
                      {ev.schema_violation?.violation || ev.error?.message || ev.subtype || "—"}
                      {ev.schema_violation?.path && ev.schema_violation.path.length > 0 && (
                        <div style={{ fontSize: 11, color: "var(--text-dim)" }}>
                          at: {ev.schema_violation.path.join(".")}
                        </div>
                      )}
                    </td>
                    <td>
                      {feedbackGiven[key] !== undefined ? (
                        <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
                          {feedbackGiven[key] ? "marked correct" : "marked wrong"}
                        </span>
                      ) : (
                        <span style={{ display: "flex", gap: 6 }}>
                          <button style={{ padding: "2px 8px" }} onClick={() => onFeedback(ev, true)} title="Classification is correct">
                            👍
                          </button>
                          <button style={{ padding: "2px 8px" }} onClick={() => onFeedback(ev, false)} title="Classification is wrong">
                            👎
                          </button>
                        </span>
                      )}
                    </td>
                    <td>
                      <AdvisoryPanel serverId={ev.server_id} ts={ev.ts} initialAdvisory={ev.ai_advisory} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
