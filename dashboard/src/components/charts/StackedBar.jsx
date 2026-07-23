import React from "react";

const DEFAULT_COLORS = {
  minor: "var(--healthy)",
  major: "var(--degraded)",
  critical: "var(--critical)",
  healthy: "var(--healthy)",
  degraded: "var(--degraded)",
  unhealthy: "var(--unhealthy)",
};

// A single proportional horizontal bar, segmented by category -- good for
// "what fraction of total is each severity" at a glance, complementing
// the donut (which is better for eyeballing absolute share visually).
export default function StackedBar({ counts, colors = DEFAULT_COLORS, height = 28 }) {
  const entries = Object.entries(counts).filter(([, v]) => v > 0);
  const total = entries.reduce((sum, [, v]) => sum + v, 0);

  if (total === 0) {
    return <div className="empty-state">No data yet.</div>;
  }

  return (
    <div>
      <div style={{ display: "flex", height, borderRadius: 6, overflow: "hidden", border: "1px solid var(--border)" }}>
        {entries.map(([label, value]) => (
          <div
            key={label}
            title={`${label}: ${value} (${((value / total) * 100).toFixed(1)}%)`}
            style={{ width: `${(value / total) * 100}%`, background: colors[label] || "var(--accent)" }}
          />
        ))}
      </div>
      <div style={{ display: "flex", gap: 14, marginTop: 8, flexWrap: "wrap" }}>
        {entries.map(([label, value]) => (
          <div key={label} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
            <span style={{ width: 9, height: 9, borderRadius: 2, background: colors[label] || "var(--accent)", display: "inline-block" }} />
            {label}: {value} ({((value / total) * 100).toFixed(0)}%)
          </div>
        ))}
      </div>
    </div>
  );
}
