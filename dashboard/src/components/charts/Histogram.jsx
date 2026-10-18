import React from "react";

// Dependency-free bucketed histogram -- bins raw numeric values client-side
// (no backend binning needed, the values array is already small: capped at
// MAX_ITEMS_CAPTURED per event in the wrapper) and renders as a bar strip.
// Self-labeled: an axis title and per-bar counts are drawn on the chart
// itself so it means something without an external caption to explain it.
export default function Histogram({ values, bins = 10, width = 480, height = 150, color = "var(--accent)", formatBin, xLabel = "value", yLabel = "how many" }) {
  const clean = (values || []).filter((v) => typeof v === "number" && !Number.isNaN(v));
  if (clean.length === 0) {
    return <div className="empty-state">No data yet.</div>;
  }

  const padTop = 40; // room for the title text (row 1) AND the count label above the tallest bar (row 2) without them touching
  const padBottom = 28;
  const plotH = height - padTop - padBottom;

  const min = Math.min(...clean);
  const max = Math.max(...clean);
  const span = max - min || 1;
  const binWidth = span / bins;

  const counts = new Array(bins).fill(0);
  for (const v of clean) {
    const idx = Math.min(bins - 1, Math.floor((v - min) / binWidth));
    counts[idx]++;
  }
  const maxCount = Math.max(1, ...counts);
  const barSlot = width / bins;

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} style={{ display: "block" }}>
        <text x={0} y={12} fontSize="11" fill="var(--text-dim)">
          {yLabel} — grouped by {xLabel}
        </text>
        {counts.map((c, i) => {
          const barHeight = maxCount > 0 ? (c / maxCount) * plotH : 0;
          const binStart = min + i * binWidth;
          const binEnd = binStart + binWidth;
          const x = i * barSlot + 1;
          const barW = Math.max(1, barSlot - 2);
          return (
            <g key={i}>
              <rect x={x} y={padTop + plotH - barHeight} width={barW} height={barHeight} fill={color} rx={2}>
                <title>
                  {formatBin ? formatBin(binStart, binEnd) : `${binStart.toFixed(2)}–${binEnd.toFixed(2)}`}: {c}
                </title>
              </rect>
              {c > 0 && barW > 10 && (
                <text x={x + barW / 2} y={padTop + plotH - barHeight - 3} fontSize="9" fill="var(--text-dim)" textAnchor="middle">
                  {c}
                </text>
              )}
            </g>
          );
        })}
        <line x1={0} y1={padTop + plotH} x2={width} y2={padTop + plotH} stroke="var(--border)" strokeWidth="1" />
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)", marginTop: 2 }}>
        <span>low: {min.toFixed(2)}</span>
        <span style={{ fontStyle: "italic" }}>{xLabel} →</span>
        <span>high: {max.toFixed(2)}</span>
      </div>
    </div>
  );
}
