import React from "react";
import { Link } from "react-router-dom";
import InfoTooltip from "./InfoTooltip.jsx";
import { formatRelativeTime } from "../utils.js";

function confidenceBadge(source) {
  if (source === "structural") return { label: "structural", color: "var(--degraded)" };
  return { label: "keyword", color: "var(--accent)" };
}

export default function InjectionEventsPanel({ events, showServerColumn = false, title = "Prompt injection signals" }) {
  return (
    <div className="panel">
      <h3>
        {title}
        <InfoTooltip text="Category 28 -- kept separate from the 27 functional-fault categories since this is adversarial, not a fault (it never affects health scores). Detected heuristically from tool descriptions, call results, and error messages -- pattern matches plus statistical anomalies against each field's own historical baseline. Passive tap only: nothing is ever blocked or modified, only flagged for review." />
      </h3>
      {!events || events.length === 0 ? (
        <div className="empty-state">No prompt-injection signals detected.</div>
      ) : (
        <table>
          <thead>
            <tr>
              {showServerColumn && <th>Server</th>}
              <th>Time</th>
              <th>Tool</th>
              <th>Source</th>
              <th>Subtypes</th>
              <th>Confidence</th>
              <th>LLM review</th>
              <th>Preview</th>
            </tr>
          </thead>
          <tbody>
            {events.map((ev, i) => {
              const signal = ev.prompt_injection || {};
              const badge = confidenceBadge(signal.confidence_source);
              const llm = signal.llm_confirmation;
              return (
                <tr key={i}>
                  {showServerColumn && (
                    <td>
                      <Link to={`/servers/${encodeURIComponent(ev.server_id)}`}>{ev.server_id}</Link>
                    </td>
                  )}
                  <td className="mono">{new Date(ev.ts * 1000).toLocaleString()}</td>
                  <td className="mono">{ev.tool_name || "—"}</td>
                  <td style={{ fontSize: 12 }}>{signal.source_field || "—"}</td>
                  <td style={{ fontSize: 12 }}>{(signal.subtypes || []).join(", ")}</td>
                  <td>
                    <span className="badge" style={{ background: badge.color }}>
                      {badge.label}
                    </span>
                  </td>
                  <td style={{ fontSize: 12 }}>
                    {llm ? (
                      <span style={{ color: llm.confirmed ? "var(--critical)" : "var(--text-dim)" }}>
                        {llm.confirmed ? "confirmed" : "not confirmed"} ({llm.confidence})
                      </span>
                    ) : (
                      <span style={{ color: "var(--text-dim)" }}>not reviewed</span>
                    )}
                  </td>
                  <td className="mono" style={{ fontSize: 11, maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={signal.preview}>
                    {signal.preview}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
