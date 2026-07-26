import React, { useState } from "react";
import { ingestionApi, ApiError } from "../api.js";

const CONFIDENCE_COLOR = { high: "var(--healthy)", medium: "var(--degraded)", low: "var(--critical)" };

// Inline, on-demand AI root-cause analysis for one captured fault event.
// Cached server-side on the event itself (`initialAdvisory`, if the event
// was already fetched with one attached) -- generating costs a real LLM
// call, so this never fires automatically, only on click.
export default function AdvisoryPanel({ serverId, ts, initialAdvisory }) {
  const [open, setOpen] = useState(false);
  const [advisory, setAdvisory] = useState(initialAdvisory || null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [unconfigured, setUnconfigured] = useState(false);

  async function fetchAdvisory(force) {
    setLoading(true);
    setError(null);
    try {
      const resp = await ingestionApi.getAdvisory(serverId, ts, force);
      if (!resp.configured) {
        setUnconfigured(true);
      } else {
        setAdvisory(resp.advisory);
        setUnconfigured(false);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  function onToggle() {
    const willOpen = !open;
    setOpen(willOpen);
    if (willOpen && !advisory && !unconfigured) {
      fetchAdvisory(false);
    }
  }

  return (
    <div>
      <button style={{ fontSize: 12, padding: "3px 10px" }} onClick={onToggle}>
        {open ? "Hide" : advisory ? "AI Advisory" : "Get AI Advisory"}
      </button>

      {open && (
        <div className="panel" style={{ marginTop: 8, marginBottom: 0 }}>
          {loading && <div className="empty-state">Analyzing...</div>}

          {!loading && unconfigured && (
            <div style={{ fontSize: 13, color: "var(--text-dim)" }}>
              AI Advisory isn't configured for this deployment -- set <span className="mono">ANTHROPIC_API_KEY</span> on
              the ingestion service to enable it.
            </div>
          )}

          {!loading && error && <div className="error-banner">{error}</div>}

          {!loading && !unconfigured && !error && advisory && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: 13 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <strong>AI Advisory</strong>
                {advisory.confidence && (
                  <span style={{ fontSize: 11, color: CONFIDENCE_COLOR[advisory.confidence] || "var(--text-dim)" }}>
                    confidence: {advisory.confidence}
                  </span>
                )}
              </div>

              <div>
                <div style={{ fontSize: 11, color: "var(--text-dim)", textTransform: "uppercase" }}>Summary</div>
                <div>{advisory.summary}</div>
              </div>

              <div>
                <div style={{ fontSize: 11, color: "var(--text-dim)", textTransform: "uppercase" }}>Root cause</div>
                <div style={{ whiteSpace: "pre-wrap" }}>{advisory.root_cause}</div>
              </div>

              <div>
                <div style={{ fontSize: 11, color: "var(--text-dim)", textTransform: "uppercase" }}>Suggested solution</div>
                <div style={{ whiteSpace: "pre-wrap" }}>{advisory.solution}</div>
              </div>

              {advisory.data_available && (
                <div>
                  <div style={{ fontSize: 11, color: "var(--text-dim)", textTransform: "uppercase" }}>
                    Grounded in (exactly what data this used)
                  </div>
                  <div style={{ color: "var(--text-dim)", fontSize: 12 }}>{advisory.data_available}</div>
                </div>
              )}

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 11, color: "var(--text-dim)" }}>
                  {advisory.generated_at ? `generated ${new Date(advisory.generated_at * 1000).toLocaleString()}` : ""}
                </span>
                <button style={{ fontSize: 11, padding: "2px 8px" }} onClick={() => fetchAdvisory(true)}>
                  Regenerate
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
