import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { classifierApi } from "../api.js";

export default function Taxonomy() {
  const [taxonomy, setTaxonomy] = useState(null);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    classifierApi
      .getTaxonomy()
      .then((d) => setTaxonomy(d.taxonomy))
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="error-banner">Failed to load taxonomy: {error}</div>;
  if (!taxonomy) return <div className="empty-state">Loading...</div>;

  return (
    <div>
      <h2>Real MCP Fault Taxonomy</h2>
      <p style={{ color: "var(--text-dim)", fontSize: 13 }}>
        27 subcategories sourced from Owotogbe et al. (2026), "A Taxonomy of Runtime Faults in Model Context
        Protocol Servers" — 837 confirmed fault threads across 473 real MCP repos, validated by 55 real MCP
        developers. Click a row to see live matching events across all servers.
      </p>
      <table>
        <thead>
          <tr>
            <th>Category</th>
            <th>Subcategory</th>
            <th>Confirmed %</th>
            <th>Dominant severity</th>
            <th>Dominant effort</th>
          </tr>
        </thead>
        <tbody>
          {taxonomy.map((row, i) => (
            <tr key={i}>
              <td>
                <Link to={`/category/${encodeURIComponent(row.category)}`} onClick={(e) => e.stopPropagation()}>
                  {row.category}
                </Link>
              </td>
              <td
                style={{ cursor: "pointer" }}
                onClick={() => navigate(`/taxonomy/${encodeURIComponent(row.category)}/${encodeURIComponent(row.subcategory)}`)}
              >
                {row.subcategory}
              </td>
              <td>{row.confirmed_pct != null ? `${row.confirmed_pct}%` : "—"}</td>
              <td>{dominant(row.severity)}</td>
              <td>{dominant(row.effort)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function dominant(dist) {
  if (!dist || Object.keys(dist).length === 0) return "—";
  return Object.entries(dist).sort((a, b) => b[1] - a[1])[0][0];
}
