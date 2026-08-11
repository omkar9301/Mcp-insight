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
    label: "Query formulation",
    implicatedBy: ["repeated_query_after_large_context"],
    describe: (d) => (d.repeated ? "Re-query detected: same arguments issued again shortly after a large prior result." : "Single query, no repeat pattern detected."),
  },
  {
    key: "retrieval",
    label: "Retrieval / ranking",
    implicatedBy: ["unranked_results", "large_result_set"],
    describe: (d) => `${d.resultCount ?? "?"} results returned${d.unranked ? ", not sorted by relevance" : ", sorted by relevance"}.`,
  },
  {
    key: "assembly",
    label: "Context assembly",
    implicatedBy: ["size_outlier", "large_result_set"],
    describe: (d) => `~${d.approxTokens ?? "?"} tokens assembled into context${d.sizeOutlier ? " — statistical outlier vs. this tool's own history" : ""}.`,
  },
  {
    key: "prompt",
    label: "Prompt construction",
    implicatedBy: [],
    describe: () => "Context handed to the model — outside this system's visibility (see limitations).",
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
                background: implicated ? "rgba(210, 153, 34, 0.1)" : "var(--panel-bg, transparent)",
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
