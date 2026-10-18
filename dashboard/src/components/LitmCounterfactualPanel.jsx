import React from "react";

// Pure re-simulation over the *same real captured scores* -- deliberately
// not a guess at what the model "should have" answered (we have no ground
// truth for that, see the limitations panel). This is just arithmetic:
// what would the context have looked like under a few well-known
// mitigation strategies, using the actual numbers from this event.
const TOP_K = 5;
const SCORE_THRESHOLD = 0.7;

function simulate(items) {
  const scored = items.filter((it) => typeof it.score === "number");
  if (scored.length === 0) return null;

  const byScoreDesc = [...scored].sort((a, b) => b.score - a.score);
  const topK = byScoreDesc.slice(0, TOP_K);
  const thresholded = scored.filter((it) => it.score >= SCORE_THRESHOLD);

  const bestItem = byScoreDesc[0];
  const bestOriginalPosition = bestItem.position;
  const bestPositionAfterRerank = 0; // by construction, sorted first

  return {
    originalCount: items.length,
    topK: { count: topK.length, avgScore: topK.reduce((s, it) => s + it.score, 0) / topK.length },
    thresholded: { count: thresholded.length, threshold: SCORE_THRESHOLD },
    bestItem,
    bestOriginalPosition,
    bestPositionAfterRerank,
  };
}

export default function LitmCounterfactualPanel({ items }) {
  const sim = simulate(items || []);
  if (!sim) {
    return <div className="empty-state">Not enough data to show a fix preview for this event.</div>;
  }

  const alreadyFirst = sim.bestOriginalPosition === 0;
  const nearStart = sim.bestOriginalPosition <= 2;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 13 }}>
      <p style={{ fontSize: 11, color: "var(--text-dim)", margin: 0 }}>
        This uses this event's real, actual results — recalculated under 3 common fixes. It's math on real numbers,
        not a guess at what the "right" answer should have been.
      </p>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
        <div className="panel" style={{ margin: 0, padding: 8 }}>
          <div style={{ fontSize: 11, color: "var(--text-dim)" }}>What actually happened</div>
          <div style={{ fontSize: 16, fontWeight: 600 }}>{sim.originalCount} results sent</div>
          <div style={{ fontSize: 11, color: "var(--text-dim)" }}>
            best match was #{sim.bestOriginalPosition + 1} in the list
          </div>
        </div>
        <div className="panel" style={{ margin: 0, padding: 8 }}>
          <div style={{ fontSize: 11, color: "var(--text-dim)" }}>Fix 1: show only top {TOP_K}</div>
          <div style={{ fontSize: 16, fontWeight: 600 }}>{sim.topK.count} results</div>
          <div style={{ fontSize: 11, color: "var(--text-dim)" }}>avg quality score {sim.topK.avgScore.toFixed(2)} / 1.0</div>
        </div>
        <div className="panel" style={{ margin: 0, padding: 8 }}>
          <div style={{ fontSize: 11, color: "var(--text-dim)" }}>Fix 2: drop weak matches (below {SCORE_THRESHOLD})</div>
          <div style={{ fontSize: 16, fontWeight: 600 }}>{sim.thresholded.count} results</div>
          <div style={{ fontSize: 11, color: "var(--text-dim)" }}>
            {sim.originalCount - sim.thresholded.count} low-quality results removed
          </div>
        </div>
      </div>
      <div className="panel" style={{ margin: 0, padding: 8 }}>
        <div style={{ fontSize: 11, color: "var(--text-dim)" }}>Fix 3: put the best match first (sort by quality)</div>
        <div>
          Best match moves from position <strong>#{sim.bestOriginalPosition + 1}</strong> to{" "}
          <strong>#1</strong> —{" "}
          {alreadyFirst
            ? "it was already first, so this fix wouldn't change anything here."
            : nearStart
            ? "it was already near the front, so this fix helps a little."
            : "a meaningful move, out of the middle of the list and to the very front where the AI pays the most attention."}
        </div>
      </div>
    </div>
  );
}
