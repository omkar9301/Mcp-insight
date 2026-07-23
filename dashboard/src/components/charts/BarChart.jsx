import React from "react";

// Horizontal bar chart, DOM-based (not SVG) -- simplest robust way to
// handle long labels (taxonomy subcategory names) without text wrapping math.
export default function BarChart({ data, labelKey = "label", valueKey = "value", color = "var(--accent)", formatValue }) {
  const max = Math.max(1e-9, ...data.map((d) => d[valueKey]));

  if (data.length === 0) {
    return <div className="empty-state">No data yet.</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {data.map((d, i) => (
        <div key={i} style={{ display: "grid", gridTemplateColumns: "180px 1fr 60px", gap: 10, alignItems: "center" }}>
          <div style={{ fontSize: 13, textAlign: "right", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {d[labelKey]}
          </div>
          <div style={{ background: "var(--border)", borderRadius: 4, height: 16, overflow: "hidden" }}>
            <div
              style={{
                width: `${(d[valueKey] / max) * 100}%`,
                background: d.color || color,
                height: "100%",
                borderRadius: 4,
                minWidth: d[valueKey] > 0 ? 3 : 0,
              }}
            />
          </div>
          <div style={{ fontSize: 13, color: "var(--text-dim)" }}>{formatValue ? formatValue(d[valueKey]) : d[valueKey]}</div>
        </div>
      ))}
    </div>
  );
}
