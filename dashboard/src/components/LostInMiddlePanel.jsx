import React from "react";
import { Link } from "react-router-dom";
import InfoTooltip from "./InfoTooltip.jsx";
import { formatRelativeTime } from "../utils.js";

// Every risk factor is explained in the same 3-part shape so a
// non-technical reader never has to guess what a jargon term means:
// WHAT happened (plain sentence), WHY it matters (the real-world
// consequence), WHAT TO DO (a concrete next step). This is deliberately
// wordier than a one-line tooltip -- clarity for a first-time reader
// matters more here than terseness.
export const RISK_INFO = {
  large_result_set: {
    label: "Too many search results at once",
    what: "This tool sent the AI more than 15 pieces of information in a single answer.",
    why: "When an AI gets a big pile of information, it tends to skim past the middle of the pile and focus mostly on the start and end -- so a good answer buried in the middle can get missed.",
    doNext: "Have the tool return fewer, more relevant results (top 5-8 instead of everything it found).",
  },
  unranked_results: {
    label: "Best answer wasn't listed first",
    what: "The most relevant result was not at the top of the list -- the results weren't sorted by how good a match they were.",
    why: "AI pays the most attention to what it sees first and last. If the best answer is buried in the middle of an unsorted list, it's easy to miss.",
    doNext: "Sort results by relevance/confidence before sending them, best match first.",
  },
  size_outlier: {
    label: "Unusually large response",
    what: "This response was much bigger than what this same tool normally returns.",
    why: "A response this size, out of the ordinary for this tool, raises the same 'stuff gets lost in the middle' risk as above.",
    doNext: "Check why this call returned so much more than usual -- it may be a bug, not just a big query.",
  },
  repeated_query_after_large_context: {
    label: "AI had to ask again",
    what: "The exact same question was asked a second time, right after a large previous answer.",
    why: "This usually means the AI didn't find what it needed the first time -- a real, observable sign that the earlier large answer didn't actually help.",
    doNext: "This is the strongest signal of the four -- investigate this tool call first.",
  },
};

function tooltipText(info) {
  return `WHAT: ${info.what}  WHY IT MATTERS: ${info.why}  WHAT TO DO: ${info.doNext}`;
}

function RiskChips({ counts }) {
  const entries = Object.entries(counts || {});
  if (entries.length === 0) return "—";
  return (
    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
      {entries.map(([factor, count]) => {
        const info = RISK_INFO[factor] || { label: factor, what: factor, why: "", doNext: "" };
        return (
          <span
            key={factor}
            title={tooltipText(info)}
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

export default function LostInMiddlePanel({ rows, showServerColumn = false, serverId = null, title = "AI may be missing information (Lost in the Middle)" }) {
  return (
    <div className="panel">
      <h3>
        ⚠️ {title}
        <InfoTooltip text="WHAT: some tools on this server returned information in a way that makes it easy for the AI to skip over the good part. WHY IT MATTERS: this is a well-documented AI weakness -- when given a lot of information, the AI pays less attention to what's in the middle, even if the answer is technically there. WHAT TO DO: hover any orange tag below for the exact problem and the fix, or open the full report for step-by-step detail." />
      </h3>
      <p style={{ fontSize: 12, color: "var(--text-dim)", marginTop: -6 }}>
        The tools below gave the AI information in a risky shape (too much at once, not sorted, etc.) — hover an
        orange tag to see exactly what happened and what to do about it.{" "}
        <Link to="/litm">Open the full report →</Link>
      </p>
      {!rows || rows.length === 0 ? (
        <div className="empty-state">Nothing flagged — no issues found here.</div>
      ) : (
        <table>
          <thead>
            <tr>
              {showServerColumn && <th>Server</th>}
              <th>Tool</th>
              <th>How many times</th>
              <th>What went wrong</th>
              <th>Avg. response size</th>
              <th>Last happened</th>
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
                <td className="mono">
                  <Link to={`/litm?server=${encodeURIComponent(r.server_id || serverId)}&tool=${encodeURIComponent(r.tool_name)}`}>
                    {r.tool_name} →
                  </Link>
                </td>
                <td>{r.flagged_calls}</td>
                <td>
                  <RiskChips counts={r.risk_factor_counts} />
                </td>
                <td>{r.avg_approx_tokens != null ? `~${Math.round(r.avg_approx_tokens)} tokens` : "—"}</td>
                <td className="mono">{formatRelativeTime(r.last_seen)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
