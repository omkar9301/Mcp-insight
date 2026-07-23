import React from "react";

// 24-cell hour-of-day strip, color intensity = error rate. Dependency-free
// grid of divs -- no need for a canvas/SVG heatmap library at this scale.
export default function Heatmap({ cells }) {
  const max = Math.max(0.01, ...cells.map((c) => c.error_rate));

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(24, 1fr)", gap: 3 }}>
        {cells.map((c) => {
          const intensity = c.total_calls === 0 ? 0 : c.error_rate / max;
          const bg =
            c.total_calls === 0
              ? "var(--border)"
              : `rgba(248, 81, 73, ${0.15 + intensity * 0.85})`;
          return (
            <div
              key={c.hour}
              title={`${c.hour}:00 UTC — ${c.total_calls} calls, ${(c.error_rate * 100).toFixed(1)}% errors`}
              style={{
                aspectRatio: "1",
                background: bg,
                borderRadius: 3,
                border: "1px solid var(--border)",
              }}
            />
          );
        })}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)", marginTop: 4 }}>
        <span>00:00</span>
        <span>12:00</span>
        <span>23:00</span>
      </div>
      <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 6 }}>Hour-of-day (UTC), color intensity = error rate</div>
    </div>
  );
}
