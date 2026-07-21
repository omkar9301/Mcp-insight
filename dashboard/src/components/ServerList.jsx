import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ingestionApi } from "../api.js";
import HealthBadge from "./HealthBadge.jsx";

export default function ServerList() {
  const [servers, setServers] = useState(null);
  const [healths, setHealths] = useState({});
  const [error, setError] = useState(null);

  async function load() {
    try {
      const data = await ingestionApi.listServers();
      setServers(data.servers || []);
      setError(null);

      const entries = await Promise.all(
        (data.servers || []).map(async (s) => {
          try {
            const h = await ingestionApi.getHealth(s.server_id, 60);
            return [s.server_id, h];
          } catch {
            return [s.server_id, null];
          }
        })
      );
      setHealths(Object.fromEntries(entries));
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, []);

  if (error) return <div className="error-banner">Failed to load servers: {error}</div>;
  if (servers === null) return <div className="empty-state">Loading...</div>;
  if (servers.length === 0) {
    return (
      <div className="empty-state">
        No servers reporting yet. Wrap a server with <span className="mono">mcp-insight run --server-id X -- ...</span> or
        run the demo in <span className="mono">deploy/</span> to see data here.
      </div>
    );
  }

  return (
    <div>
      <h2>Servers</h2>
      {servers.map((s) => {
        const h = healths[s.server_id];
        return (
          <Link key={s.server_id} to={`/servers/${encodeURIComponent(s.server_id)}`} className="server-card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span className="server-id">{s.server_id}</span>
              <HealthBadge status={h?.health_status} score={h?.health_score} />
            </div>
            <div className="meta">
              last seen {s.last_seen ? new Date(s.last_seen * 1000).toLocaleString() : "never"}
              {h ? ` — ${h.total_calls} calls, ${(h.error_rate * 100).toFixed(1)}% errors, ${h.silent_failure_count} silent failures` : ""}
            </div>
          </Link>
        );
      })}
    </div>
  );
}
