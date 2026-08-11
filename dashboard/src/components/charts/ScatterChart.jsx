import React from "react";

// Dependency-free scatter plot: position (x) vs. relevance score (y) --
// makes the "high-relevance item buried mid-list" shape of a Lost-in-the-
// Middle risk visible directly, instead of only described in prose.
// Draws the documented U-shaped attention-risk curve (Liu et al.) as a
// reference band across the middle third of the x-axis.
export default function ScatterChart({ points, width = 480, height = 220, color = "var(--accent)" }) {
  const clean = (points || []).filter((p) => typeof p.position === "number" && typeof p.score === "number");
  if (clean.length === 0) {
    return <div className="empty-state">No per-item score data captured for this event.</div>;
  }

  const maxPos = Math.max(1, ...clean.map((p) => p.position));
  const pad = 24;
  const plotW = width - pad * 2;
  const plotH = height - pad * 2;

  const xFor = (pos) => pad + (maxPos > 0 ? (pos / maxPos) * plotW : plotW / 2);
  const yFor = (score) => pad + plotH - Math.max(0, Math.min(1, score)) * plotH;

  const midStart = pad + plotW / 3;
  const midEnd = pad + (plotW * 2) / 3;

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={{ display: "block" }}>
        <rect x={midStart} y={pad} width={midEnd - midStart} height={plotH} fill="var(--degraded)" opacity="0.08" />
        <text x={(midStart + midEnd) / 2} y={pad - 6} fontSize="9" fill="var(--text-dim)" textAnchor="middle">
          highest attention-loss zone
        </text>
        <line x1={pad} y1={pad + plotH} x2={pad + plotW} y2={pad + plotH} stroke="var(--border)" strokeWidth="1" />
        <line x1={pad} y1={pad} x2={pad} y2={pad + plotH} stroke="var(--border)" strokeWidth="1" />
        {clean.map((p, i) => (
          <circle key={i} cx={xFor(p.position)} cy={yFor(p.score)} r="4" fill={p.score >= 0.7 ? "var(--healthy)" : color} opacity="0.85">
            <title>
              position {p.position}, score {p.score.toFixed(3)}
              {p.preview ? ` — "${p.preview.slice(0, 60)}${p.preview.length > 60 ? "…" : ""}"` : ""}
            </title>
          </circle>
        ))}
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)" }}>
        <span>position 0 (start of context)</span>
        <span>position {maxPos} (end of context)</span>
      </div>
    </div>
  );
}
