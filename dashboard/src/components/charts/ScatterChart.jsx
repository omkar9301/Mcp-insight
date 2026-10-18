import React from "react";

// Dependency-free scatter plot: position (x) vs. relevance score (y) --
// makes the "high-relevance item buried mid-list" shape of a Lost-in-the-
// Middle risk visible directly, instead of only described in prose.
// Self-labeled: axis titles, tick values, and a legend are drawn INSIDE
// the chart itself, not left to a caption underneath -- a chart that
// needs a paragraph next to it to be readable has failed at being a chart.
export default function ScatterChart({ points, width = 520, height = 260 }) {
  const clean = (points || []).filter((p) => typeof p.position === "number" && typeof p.score === "number");
  if (clean.length === 0) {
    return <div className="empty-state">No per-item score data captured for this event.</div>;
  }

  const maxPos = Math.max(1, ...clean.map((p) => p.position));
  const padLeft = 44;
  const padRight = 16;
  const padTop = 68; // room for title (row 1), legend (row 2), and the zone label (row 3) -- three stacked rows, never overlapping
  const padBottom = 40;
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;

  const xFor = (pos) => padLeft + (maxPos > 0 ? (pos / maxPos) * plotW : plotW / 2);
  const yFor = (score) => padTop + plotH - Math.max(0, Math.min(1, score)) * plotH;

  const midStart = padLeft + plotW / 3;
  const midEnd = padLeft + (plotW * 2) / 3;
  const yTicks = [0, 0.25, 0.5, 0.75, 1.0];

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} style={{ display: "block" }}>
        {/* Chart title -- row 1 */}
        <text x={padLeft} y={16} fontSize="12" fill="var(--text)" fontWeight="600">
          How relevant was each result, and where did it land in the list?
        </text>

        {/* Legend -- row 2, its own line, never sharing space with the title */}
        <g transform={`translate(${padLeft}, 26)`}>
          <circle cx={6} cy={5} r="5" fill="var(--healthy)" />
          <text x={16} y={9} fontSize="10" fill="var(--text-dim)">good match (≥ 0.70)</text>
          <circle cx={150} cy={5} r="5" fill="var(--accent)" />
          <text x={160} y={9} fontSize="10" fill="var(--text-dim)">weaker match (&lt; 0.70)</text>
        </g>

        {/* "Easy to miss" reference zone -- the middle third of the list -- row 3 */}
        <rect x={midStart} y={padTop} width={midEnd - midStart} height={plotH} fill="var(--degraded)" opacity="0.08" />
        <text x={(midStart + midEnd) / 2} y={padTop - 6} fontSize="9" fill="var(--degraded)" textAnchor="middle" fontWeight="600">
          ⚠ easy-to-miss zone (middle of the list)
        </text>

        {/* Y-axis gridlines + tick labels: relevance score */}
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={padLeft} y1={yFor(t)} x2={padLeft + plotW} y2={yFor(t)} stroke="var(--border)" strokeWidth="1" opacity={t === 0 ? 1 : 0.4} />
            <text x={padLeft - 8} y={yFor(t) + 3} fontSize="9" fill="var(--text-dim)" textAnchor="end">
              {t.toFixed(2)}
            </text>
          </g>
        ))}
        <text x={12} y={padTop + plotH / 2} fontSize="9" fill="var(--text-dim)" textAnchor="middle" transform={`rotate(-90 12 ${padTop + plotH / 2})`}>
          match quality (1.0 = perfect)
        </text>

        {/* X-axis */}
        <line x1={padLeft} y1={padTop + plotH} x2={padLeft + plotW} y2={padTop + plotH} stroke="var(--border)" strokeWidth="1" />
        <text x={padLeft} y={height - 24} fontSize="9" fill="var(--text-dim)" textAnchor="start">
          #1 (shown to AI first)
        </text>
        <text x={padLeft + plotW} y={height - 24} fontSize="9" fill="var(--text-dim)" textAnchor="end">
          #{maxPos + 1} (shown to AI last)
        </text>
        <text x={padLeft + plotW / 2} y={height - 10} fontSize="9" fill="var(--text-dim)" textAnchor="middle">
          order the AI saw the results in
        </text>

        {clean.map((p, i) => (
          <circle className="scatter-dot" key={i} cx={xFor(p.position)} cy={yFor(p.score)} r="5" fill={p.score >= 0.7 ? "var(--healthy)" : "var(--accent)"} opacity="0.9" stroke="var(--bg)" strokeWidth="1">
            <title>
              Result #{p.position + 1}: match quality {p.score.toFixed(2)} out of 1.0
              {p.preview ? ` — "${p.preview.slice(0, 60)}${p.preview.length > 60 ? "…" : ""}"` : ""}
            </title>
          </circle>
        ))}
      </svg>
    </div>
  );
}
