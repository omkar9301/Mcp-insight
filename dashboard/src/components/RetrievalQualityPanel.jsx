import React from "react";
import { Link } from "react-router-dom";
import InfoTooltip from "./InfoTooltip.jsx";
import { formatRelativeTime } from "../utils.js";

function emptyRateColor(rate) {
  if (rate >= 0.4) return "var(--critical)";
  if (rate >= 0.1) return "var(--degraded)";
  return "var(--healthy)";
}

export default function RetrievalQualityPanel({ rows, showServerColumn = false, title = "Retrieval tool quality" }) {
  return (
    <div className="panel">
      <h3>
        {title}
        <InfoTooltip text="Best-effort, not ground truth: the wrapper never sees whether a tool actually queried a vector DB, only whether its result LOOKS like a retrieval result (a list, optionally with score/similarity fields) on a tool whose name/description suggests search/retrieval/embedding. A high empty-result rate is the strongest signal here -- it usually means queries are returning nothing useful, which is worth investigating regardless of what's happening internally." />
      </h3>
      {!rows || rows.length === 0 ? (
        <div className="empty-state">
          No retrieval-shaped tool calls observed yet. This only appears for tools whose name/description looks
          like search/retrieval/embedding AND whose result looks like a list of matches.
        </div>
      ) : (
        <table>
          <thead>
            <tr>
              {showServerColumn && <th>Server</th>}
              <th>Tool</th>
              <th>Calls</th>
              <th>Empty-result rate</th>
              <th>Avg results</th>
              <th>Avg top score</th>
              <th>Worst top score</th>
              <th>Avg latency</th>
              <th>Last seen</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                {showServerColumn && (
                  <td>
                    <Link to={`/servers/${encodeURIComponent(r.server_id)}`}>{r.server_id}</Link>
                  </td>
                )}
                <td className="mono">{r.tool_name}</td>
                <td>{r.total_calls}</td>
                <td>
                  <span style={{ color: emptyRateColor(r.empty_result_rate), fontWeight: 600 }}>
                    {(r.empty_result_rate * 100).toFixed(0)}%
                  </span>
                  <span style={{ color: "var(--text-dim)", fontSize: 11 }}> ({r.empty_result_count}/{r.total_calls})</span>
                </td>
                <td>{r.avg_result_count != null ? r.avg_result_count.toFixed(1) : "—"}</td>
                <td>{r.avg_top_score != null ? r.avg_top_score.toFixed(3) : "—"}</td>
                <td>{r.worst_top_score != null ? r.worst_top_score.toFixed(3) : "—"}</td>
                <td>{r.avg_latency_ms != null ? `${r.avg_latency_ms.toFixed(0)}ms` : "—"}</td>
                <td className="mono">{formatRelativeTime(r.last_seen)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
