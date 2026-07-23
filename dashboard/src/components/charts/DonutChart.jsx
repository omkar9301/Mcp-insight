import React from "react";

const DEFAULT_COLORS = {
  healthy: "var(--healthy)",
  degraded: "var(--degraded)",
  unhealthy: "var(--unhealthy)",
  critical: "var(--critical)",
  minor: "var(--healthy)",
  major: "var(--degraded)",
  unknown: "var(--text-dim)",
};

// Dependency-free SVG donut via stroke-dasharray segments on a circle.
export default function DonutChart({ counts, size = 160, strokeWidth = 24, colors = DEFAULT_COLORS }) {
  const entries = Object.entries(counts).filter(([, v]) => v > 0);
  const total = entries.reduce((sum, [, v]) => sum + v, 0);
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  if (total === 0) {
    return <div className="empty-state">No data yet.</div>;
  }

  let offset = 0;
  const segments = entries.map(([label, value]) => {
    const fraction = value / total;
    const dash = fraction * circumference;
    const seg = { label, value, dash, offset, color: colors[label] || "var(--accent)" };
    offset += dash;
    return seg;
  });

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <g transform={`rotate(-90 ${size / 2} ${size / 2})`}>
          {segments.map((s, i) => (
            <circle
              key={i}
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={s.color}
              strokeWidth={strokeWidth}
              strokeDasharray={`${s.dash} ${circumference - s.dash}`}
              strokeDashoffset={-s.offset}
            >
              <title>{`${s.label}: ${s.value}`}</title>
            </circle>
          ))}
        </g>
        <text x={size / 2} y={size / 2} textAnchor="middle" dominantBaseline="middle" fontSize="22" fontWeight="600" fill="var(--text)">
          {total}
        </text>
      </svg>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {segments.map((s, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
            <span style={{ width: 10, height: 10, borderRadius: 3, background: s.color, display: "inline-block" }} />
            {s.label} ({s.value})
          </div>
        ))}
      </div>
    </div>
  );
}
