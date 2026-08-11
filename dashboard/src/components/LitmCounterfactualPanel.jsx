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
    return <div className="empty-state">No per-item scores captured for this event -- nothing to re-simulate.</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 13 }}>
      <p style={{ fontSize: 11, color: "var(--text-dim)", margin: 0 }}>
        Recalculated from this event's actual captured scores -- not a guess at the "correct" answer (this system has
        no ground truth), just what the context would look like under standard mitigations.
      </p>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
        <div className="panel" style={{ margin: 0, padding: 8 }}>
          <div style={{ fontSize: 11, color: "var(--text-dim)" }}>As returned</div>
          <div style={{ fontSize: 16, fontWeight: 600 }}>{sim.originalCount} items</div>
          <div style={{ fontSize: 11, color: "var(--text-dim)" }}>
            best match at position {sim.bestOriginalPosition}
          </div>
        </div>
        <div className="panel" style={{ margin: 0, padding: 8 }}>
          <div style={{ fontSize: 11, color: "var(--text-dim)" }}>If cut to top-{TOP_K}</div>
          <div style={{ fontSize: 16, fontWeight: 600 }}>{sim.topK.count} items</div>
          <div style={{ fontSize: 11, color: "var(--text-dim)" }}>avg score {sim.topK.avgScore.toFixed(2)}</div>
        </div>
        <div className="panel" style={{ margin: 0, padding: 8 }}>
          <div style={{ fontSize: 11, color: "var(--text-dim)" }}>If threshold ≥ {SCORE_THRESHOLD}</div>
          <div style={{ fontSize: 16, fontWeight: 600 }}>{sim.thresholded.count} items</div>
          <div style={{ fontSize: 11, color: "var(--text-dim)" }}>
            {sim.originalCount - sim.thresholded.count} low-confidence items dropped
          </div>
        </div>
      </div>
      <div className="panel" style={{ margin: 0, padding: 8 }}>
        <div style={{ fontSize: 11, color: "var(--text-dim)" }}>If reordered by score (simple rerank)</div>
        <div>
          Best match moves from position <strong>{sim.bestOriginalPosition}</strong> to position{" "}
          <strong>{sim.bestPositionAfterRerank}</strong> — {sim.bestOriginalPosition === 0
            ? "already first, reordering wouldn't change this."
            : "out of the highest attention-loss zone and into the start of the context."}
        </div>
      </div>
    </div>
  );
}
