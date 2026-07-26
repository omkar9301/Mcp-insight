import React, { useEffect, useState } from "react";
import { ingestionApi } from "../api.js";
import InfoTooltip from "./InfoTooltip.jsx";
import BarChart from "./charts/BarChart.jsx";
import InjectionEventsPanel from "./InjectionEventsPanel.jsx";

export default function SecurityPage() {
  const [summary, setSummary] = useState(null);
  const [events, setEvents] = useState(null);
  const [error, setError] = useState(null);

  async function load() {
    try {
      const [s, e] = await Promise.all([
        ingestionApi.getInjectionSummary(43200),
        ingestionApi.getFleetInjectionEvents(100),
      ]);
      setSummary(s);
      setEvents(e.events);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 20000);
    return () => clearInterval(id);
  }, []);

  if (error) return <div className="error-banner">{error}</div>;
  if (!summary) return <div className="empty-state">Loading...</div>;

  const subtypeData = Object.entries(summary.subtype_counts || {})
    .map(([subtype, count]) => ({ subtype, count }))
    .sort((a, b) => b.count - a.count);

  return (
    <div>
      <h2>
        Security
        <InfoTooltip text="Prompt injection detection (fault taxonomy category 28): a malicious or compromised MCP server can embed instruction-like text in tool descriptions, results, or error messages, aiming to manipulate the AI assistant reading them rather than the human. This is best-effort heuristic detection (regex patterns + statistical anomaly against each field's own baseline), not proof -- and it's a passive tap only, nothing is ever blocked automatically." />
      </h2>
      <p style={{ color: "var(--text-dim)", fontSize: 13 }}>
        Kept entirely separate from the 27 functional-fault categories and health scoring -- this is adversarial
        signal, not a fault rate.
      </p>

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
          <div className="label">
            Keyword vs. structural
            <InfoTooltip text="'Keyword' means a regex pattern actually matched (imperative language, role spoofing, exfiltration triggers, obfuscation). 'Structural' means no keyword matched, but the field's length/entropy was a statistical outlier vs. its own history -- catches novel or obfuscated payloads pattern-matching alone would miss." />
          </div>
          <div className="value" style={{ fontSize: 16 }}>
            {summary.confidence_source_counts?.keyword || 0} / {summary.confidence_source_counts?.structural || 0}
          </div>
        </div>
      </div>

      {subtypeData.length > 0 && (
        <div className="panel">
          <h3>Flagged by subtype (30d)</h3>
          <BarChart data={subtypeData} labelKey="subtype" valueKey="count" color="var(--critical)" />
        </div>
      )}

      <InjectionEventsPanel events={events} showServerColumn title="Recent signals, fleet-wide" />
    </div>
  );
}
