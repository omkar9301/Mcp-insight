import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ingestionApi } from "../api.js";
import InfoTooltip from "./InfoTooltip.jsx";
import { formatRelativeTime } from "../utils.js";

function schemaSummary(schema) {
  if (!schema) return "—";
  if (schema.type !== "object" || !schema.properties) return schema.type || "—";
  const required = new Set(schema.required || []);
  const fields = Object.keys(schema.properties).map((k) => (required.has(k) ? `${k}*` : k));
  return fields.length ? fields.join(", ") : "object";
}

export default function ToolsPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState({});

  useEffect(() => {
    ingestionApi
      .getAllTools()
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="error-banner">{error}</div>;
  if (!data) return <div className="empty-state">Loading...</div>;

  const totalTools = data.servers.reduce((sum, s) => sum + s.tools.length, 0);
  const filtered = data.servers
    .map((s) => ({
      ...s,
      tools: s.tools.filter((t) => (search ? t.name.toLowerCase().includes(search.toLowerCase()) : true)),
    }))
    .filter((s) => s.tools.length > 0 || !search);

  return (
    <div>
      <h2>
        Tool Registry
        <InfoTooltip text="What each connected MCP server declares it can do -- captured live from its `initialize` response or a `tools/list` call, not manually entered. A server with nothing here hasn't been seen doing either yet (e.g. only tools/call traffic was observed, or it uses a transport/pattern the wrapper hasn't captured declarations from)." />
      </h2>
      <p style={{ color: "var(--text-dim)", fontSize: 13 }}>
        {data.servers.length} server{data.servers.length === 1 ? "" : "s"} reporting capabilities, {totalTools} tool
        {totalTools === 1 ? "" : "s"} total.
      </p>

      <div style={{ marginBottom: 16 }}>
        <input placeholder="Search tool name..." value={search} onChange={(e) => setSearch(e.target.value)} style={{ width: 240 }} />
      </div>

      {data.servers.length === 0 ? (
        <div className="empty-state">
          No servers have reported their tool list yet. This is captured automatically from a wrapped server's{" "}
          <span className="mono">initialize</span> response or a <span className="mono">tools/list</span> call -- drive some
          traffic through a wrapped server to populate this page.
        </div>
      ) : (
        filtered.map((s) => (
          <div key={s.server_id} className="panel">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h3 style={{ margin: 0 }}>
                <Link to={`/servers/${encodeURIComponent(s.server_id)}`}>{s.server_id}</Link>
                <span style={{ fontSize: 13, color: "var(--text-dim)", fontWeight: 400, marginLeft: 8 }}>
                  {s.tools.length} tool{s.tools.length === 1 ? "" : "s"}
                </span>
              </h3>
              {s.tools_updated_at && (
                <span style={{ fontSize: 12, color: "var(--text-dim)" }}>updated {formatRelativeTime(s.tools_updated_at)}</span>
              )}
            </div>
            {s.tools.length === 0 ? (
              <div className="empty-state">No tools match this search.</div>
            ) : (
              <table style={{ marginTop: 10 }}>
                <thead>
                  <tr>
                    <th>Tool</th>
                    <th>Description</th>
                    <th>Input fields</th>
                    <th>Output fields</th>
                  </tr>
                </thead>
                <tbody>
                  {s.tools.map((t, i) => {
                    const key = `${s.server_id}:${t.name}`;
                    const isOpen = !!expanded[key];
                    return (
                      <React.Fragment key={i}>
                        <tr style={{ cursor: "pointer" }} onClick={() => setExpanded((p) => ({ ...p, [key]: !p[key] }))}>
                          <td className="mono">
                            {isOpen ? "▾" : "▸"} {t.name}
                          </td>
                          <td style={{ fontSize: 13, color: "var(--text-dim)" }}>{t.description || "—"}</td>
                          <td style={{ fontSize: 12 }}>{schemaSummary(t.input_schema)}</td>
                          <td style={{ fontSize: 12 }}>{schemaSummary(t.output_schema)}</td>
                        </tr>
                        {isOpen && (
                          <tr>
                            <td colSpan={4}>
                              <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                                <div style={{ flex: 1, minWidth: 200 }}>
                                  <div style={{ fontSize: 11, color: "var(--text-dim)", marginBottom: 4 }}>Input schema</div>
                                  <pre className="mono" style={{ fontSize: 11, whiteSpace: "pre-wrap", margin: 0 }}>
                                    {t.input_schema ? JSON.stringify(t.input_schema, null, 2) : "not declared"}
                                  </pre>
                                </div>
                                <div style={{ flex: 1, minWidth: 200 }}>
                                  <div style={{ fontSize: 11, color: "var(--text-dim)", marginBottom: 4 }}>Output schema</div>
                                  <pre className="mono" style={{ fontSize: 11, whiteSpace: "pre-wrap", margin: 0 }}>
                                    {t.output_schema ? JSON.stringify(t.output_schema, null, 2) : "not declared"}
                                  </pre>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        ))
      )}
    </div>
  );
}
