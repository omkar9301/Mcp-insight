import React from "react";

// Data-driven pipeline diagram -- the same four stages every time (this is
// a generic RAG/retrieval pipeline shape, not something we can introspect
// from the target system's actual code), but each stage is annotated live
// from the selected event's real captured numbers and highlighted if a
// risk factor implicates that stage. "Live" means: pick a different event
// or tool and the diagram redraws from that event's data -- not a static
// picture.
const STAGES = [
  {
    key: "query",
    label: "1. AI asks a question",
    implicatedBy: ["repeated_query_after_large_context"],
    describe: (d) => (d.repeated ? "⚠️ The AI asked the exact same question again, right after a big answer — a sign the first answer didn't help." : "Normal — no repeated questions."),
  },
  {
    key: "retrieval",
    label: "2. Tool searches and ranks results",
    implicatedBy: ["unranked_results", "large_result_set"],
    describe: (d) => `${d.resultCount ?? "?"} results came back${d.unranked ? ", and they weren't sorted by how good a match they were." : ", sorted best-first."}`,
  },
  {
    key: "assembly",
    label: "3. Results get bundled together",
    implicatedBy: ["size_outlier", "large_result_set"],
    describe: (d) => `About ${d.approxTokens ?? "?"} tokens (words) bundled up to hand to the AI${d.sizeOutlier ? " — much bigger than usual for this tool." : "."}`,
  },
  {
    key: "prompt",
    label: "4. AI reads it and responds",
    implicatedBy: [],
    describe: () => "We can't see this step — we don't have access to what the AI actually says back to the user.",
  },
];

export default function LitmPipelineDiagram({ signal }) {
  const factors = new Set(signal?.risk_factors || []);
  const data = {
    repeated: factors.has("repeated_query_after_large_context"),
    resultCount: signal?.result_count,
    unranked: factors.has("unranked_results"),
    approxTokens: signal?.approx_tokens,
    sizeOutlier: factors.has("size_outlier"),
  };

  return (
    <div style={{ display: "flex", alignItems: "stretch", gap: 4, overflowX: "auto", padding: "4px 0" }}>
      {STAGES.map((stage, i) => {
        const implicated = stage.implicatedBy.some((f) => factors.has(f));
        return (
          <React.Fragment key={stage.key}>
            <div
              style={{
                minWidth: 150,
                border: `1px solid ${implicated ? "var(--degraded)" : "var(--border)"}`,
                background: implicated ? "rgba(210, 153, 34, 0.1)" : "var(--bg-panel)",
                borderRadius: 6,
                padding: 10,
                fontSize: 12,
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: 4, color: implicated ? "var(--degraded)" : undefined }}>
                {implicated ? "⚠️ " : ""}
                {stage.label}
              </div>
              <div style={{ color: "var(--text-dim)", fontSize: 11 }}>{stage.describe(data)}</div>
            </div>
            {i < STAGES.length - 1 && (
              <div style={{ display: "flex", alignItems: "center", color: "var(--text-dim)", fontSize: 16 }}>→</div>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}
