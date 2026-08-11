import React from "react";

// Dependency-free bucketed histogram -- bins raw numeric values client-side
// (no backend binning needed, the values array is already small: capped at
// MAX_ITEMS_CAPTURED per event in the wrapper) and renders as a bar strip.
export default function Histogram({ values, bins = 10, width = 480, height = 120, color = "var(--accent)", formatBin }) {
  const clean = (values || []).filter((v) => typeof v === "number" && !Number.isNaN(v));
  if (clean.length === 0) {
    return <div className="empty-state">No data yet.</div>;
  }

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
  const barWidth = width / bins;

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={{ display: "block" }}>
        {counts.map((c, i) => {
          const barHeight = (c / maxCount) * (height - 4);
          const binStart = min + i * binWidth;
          const binEnd = binStart + binWidth;
          return (
            <rect
              key={i}
              x={i * barWidth + 1}
              y={height - barHeight}
              width={Math.max(1, barWidth - 2)}
              height={barHeight}
              fill={color}
              rx={2}
            >
              <title>
                {formatBin ? formatBin(binStart, binEnd) : `${binStart.toFixed(2)}–${binEnd.toFixed(2)}`}: {c}
              </title>
            </rect>
          );
        })}
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)", marginTop: 4 }}>
        <span>{formatBin ? formatBin(min, min) : min.toFixed(2)}</span>
        <span>{formatBin ? formatBin(max, max) : max.toFixed(2)}</span>
      </div>
    </div>
  );
}
