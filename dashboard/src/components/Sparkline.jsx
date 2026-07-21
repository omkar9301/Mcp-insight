import React from "react";

// Minimal dependency-free line chart -- avoids pulling in a charting
// library for what's fundamentally a handful of points per server.
export default function Sparkline({ values, width = 560, height = 80, color = "var(--accent)", formatValue }) {
  const clean = values.map((v) => (typeof v === "number" && !Number.isNaN(v) ? v : 0));
  const max = Math.max(1e-9, ...clean);
  const min = Math.min(0, ...clean);
  const range = max - min || 1;

  const points = clean.map((v, i) => {
    const x = clean.length > 1 ? (i / (clean.length - 1)) * width : 0;
    const y = height - ((v - min) / range) * height;
    return [x, y];
  });

  const path = points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const last = clean[clean.length - 1];

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={{ display: "block" }}>
      <path d={path} fill="none" stroke={color} strokeWidth="2" />
      {points.length > 0 && (
        <circle cx={points[points.length - 1][0]} cy={points[points.length - 1][1]} r="3" fill={color} />
      )}
      <title>{formatValue ? formatValue(last) : last}</title>
    </svg>
  );
}
