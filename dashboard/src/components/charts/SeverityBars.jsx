import React from "react";

const ORDER = ["minor", "major", "critical"];
const COLORS = { minor: "var(--healthy)", major: "var(--degraded)", critical: "var(--critical)" };

// Always renders all three severities, even at zero -- a single-category
// stacked bar (e.g. "100% major" when nothing else exists) renders as one
// solid-color bar with no reference point, easy to mistake for a loading
// bar. Three fixed bars with counts printed on them give real comparison
// even when only one severity has ever occurred.
export default function SeverityBars({ counts, onBarClick }) {
  const total = ORDER.reduce((sum, k) => sum + (counts[k] || 0), 0);
  const max = Math.max(1, ...ORDER.map((k) => counts[k] || 0));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {ORDER.map((sev) => {
        const value = counts[sev] || 0;
        const pct = total > 0 ? ((value / total) * 100).toFixed(0) : 0;
        return (
          <div
            key={sev}
            style={{ display: "grid", gridTemplateColumns: "70px 1fr 90px", gap: 10, alignItems: "center", cursor: onBarClick ? "pointer" : "default" }}
            onClick={onBarClick ? () => onBarClick(sev) : undefined}
          >
            <div style={{ fontSize: 13, textTransform: "capitalize" }}>{sev}</div>
            <div style={{ background: "var(--border)", borderRadius: 4, height: 18, overflow: "hidden" }}>
              <div
                style={{
                  width: `${(value / max) * 100}%`,
                  background: COLORS[sev],
                  height: "100%",
                  minWidth: value > 0 ? 3 : 0,
                }}
              />
            </div>
            <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
              {value} {total > 0 ? `(${pct}%)` : ""}
            </div>
          </div>
        );
      })}
      {total === 0 && <div style={{ fontSize: 12, color: "var(--text-dim)" }}>No classified faults in this window.</div>}
    </div>
  );
}
