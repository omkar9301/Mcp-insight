import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ingestionApi } from "../api.js";

export default function TaxonomyDrilldown() {
  const { category, subcategory } = useParams();
  const [events, setEvents] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    ingestionApi
      .getEventsByClassification(category, subcategory, 100)
      .then((d) => setEvents(d.events))
      .catch((e) => setError(e.message));
  }, [category, subcategory]);

  return (
    <div>
      <p>
        <Link to="/taxonomy">&larr; taxonomy</Link>
      </p>
      <h2>
        {category} / {subcategory}
      </h2>
      <p style={{ color: "var(--text-dim)", fontSize: 13 }}>
        Live events classified into this subcategory, across all servers, most recent first.
      </p>
      {error && <div className="error-banner">{error}</div>}
      {!events ? (
        <div className="empty-state">Loading...</div>
      ) : events.length === 0 ? (
        <div className="empty-state">No events classified into this subcategory yet.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Server</th>
              <th>Method</th>
              <th>Confidence</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {events.map((ev, i) => (
              <tr key={i}>
                <td className="mono">{new Date(ev.ts * 1000).toLocaleString()}</td>
                <td>
                  <Link to={`/servers/${encodeURIComponent(ev.server_id)}`}>{ev.server_id}</Link>
                </td>
                <td>{ev.method || "—"}</td>
                <td>
                  {ev.classification?.confidence != null
                    ? `${(ev.classification.confidence * 100).toFixed(0)}%`
                    : ev.classification?.source === "llm"
                      ? "llm"
                      : "—"}
                </td>
                <td>{ev.schema_violation?.violation || ev.error?.message || ev.subtype || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
