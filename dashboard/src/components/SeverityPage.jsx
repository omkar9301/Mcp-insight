import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ingestionApi } from "../api.js";

export default function SeverityPage() {
  const { severity } = useParams();
  const [events, setEvents] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    ingestionApi
      .getEventsBySeverity(severity, 100)
      .then((d) => setEvents(d.events))
      .catch((e) => setError(e.message));
  }, [severity]);

  return (
    <div>
      <p>
        <Link to="/">&larr; overview</Link>
      </p>
      <h2>
        <span className={`badge ${severity === "critical" ? "critical" : severity === "major" ? "unhealthy" : "healthy"}`}>{severity}</span>{" "}
        faults, all servers
      </h2>
      {error && <div className="error-banner">{error}</div>}
      {!events ? (
        <div className="empty-state">Loading...</div>
      ) : events.length === 0 ? (
        <div className="empty-state">No {severity} faults recorded yet.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Server</th>
              <th>Category / Subcategory</th>
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
                <td>
                  <Link
                    to={`/taxonomy/${encodeURIComponent(ev.classification.category)}/${encodeURIComponent(ev.classification.subcategory)}`}
                  >
                    {ev.classification.category} / {ev.classification.subcategory}
                  </Link>
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
