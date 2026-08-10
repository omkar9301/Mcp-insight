import React from "react";
import { Link } from "react-router-dom";
import InfoTooltip from "./InfoTooltip.jsx";
import { formatRelativeTime } from "../utils.js";

// Each factor's label now says "Lost in the Middle" explicitly, and the
// title attribute explains *why* this specific factor is a LITM risk --
// a reader shouldn't have to already know the term to understand a chip
// that just says "large result set" or "size outlier".
export const RISK_INFO = {
  large_result_set: {
    label: "Lost in the Middle: large result set",
    detail: "Over 15 items returned to the model in one call -- retrieval accuracy is documented to degrade as context grows this large, especially for items buried in the middle of the list.",
  },
  unranked_results: {
    label: "Lost in the Middle: unranked results",
    detail: "The most relevant match wasn't first in the list -- when results aren't sorted by relevance, the best answer is more likely to land in the middle of the context, where models attend to it least.",
  },
  size_outlier: {
    label: "Lost in the Middle: oversized response",
    detail: "This result was a statistical outlier vs. this tool's own typical response size -- an unusually large context increases the odds relevant content gets lost in the middle.",
  },
  repeated_query_after_large_context: {
    label: "Lost in the Middle: repeated query",
    detail: "The same question was asked again shortly after a large prior result -- a real signal the model may not have found what it needed the first time, consistent with lost-in-the-middle context loss.",
  },
};

function RiskChips({ counts }) {
  const entries = Object.entries(counts || {});
  if (entries.length === 0) return "—";
  return (
    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
      {entries.map(([factor, count]) => {
        const info = RISK_INFO[factor] || { label: factor, detail: factor };
        return (
          <span
            key={factor}
            title={info.detail}
            style={{
              fontSize: 10,
              background: "rgba(210, 153, 34, 0.18)",
              border: "1px solid var(--degraded)",
              color: "var(--degraded)",
              borderRadius: 4,
              padding: "2px 7px",
              whiteSpace: "nowrap",
              fontWeight: 600,
            }}
          >
            {info.label}: {count}
          </span>
        );
      })}
    </div>
  );
}

export default function LostInMiddlePanel({ rows, showServerColumn = false, title = "Lost in the Middle -- context risk" }) {
  return (
    <div className="panel">
      <h3>
        ⚠️ {title}
        <InfoTooltip text="'Lost in the Middle' is a documented LLM failure mode: when a model is given a lot of context, it tends to pay less attention to information buried in the middle (vs. the start or end), even though that information is technically present. This platform can't see the model's actual attention, so it flags known RISK FACTORS from the research instead -- oversized/unranked retrieval results, statistical size outliers, and repeated queries that suggest the first answer wasn't used effectively." />
      </h3>
      <p style={{ fontSize: 12, color: "var(--text-dim)", marginTop: -6 }}>
        Tools below returned context in a shape known to increase the risk of the AI assistant missing relevant
        information -- hover a chip for why it was flagged.
      </p>
      {!rows || rows.length === 0 ? (
        <div className="empty-state">No lost-in-the-middle risk factors flagged.</div>
      ) : (
        <table>
          <thead>
            <tr>
              {showServerColumn && <th>Server</th>}
              <th>Tool</th>
              <th>Flagged calls</th>
              <th>Lost-in-the-Middle risk factors</th>
              <th>Avg approx. tokens</th>
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
                <td>{r.flagged_calls}</td>
                <td>
                  <RiskChips counts={r.risk_factor_counts} />
                </td>
                <td>{r.avg_approx_tokens != null ? Math.round(r.avg_approx_tokens) : "—"}</td>
                <td className="mono">{formatRelativeTime(r.last_seen)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
