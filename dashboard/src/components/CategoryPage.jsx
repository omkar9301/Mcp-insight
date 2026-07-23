import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { classifierApi, ingestionApi } from "../api.js";
import BarChart from "./charts/BarChart.jsx";

export default function CategoryPage() {
  const { category } = useParams();
  const [taxonomyRows, setTaxonomyRows] = useState(null);
  const [counts, setCounts] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([classifierApi.getTaxonomy(), ingestionApi.getCategoryCounts(1440 * 30)])
      .then(([t, c]) => {
        setTaxonomyRows(t.taxonomy.filter((row) => row.category === category));
        setCounts(c.rows.filter((row) => row.category === category));
      })
      .catch((e) => setError(e.message));
  }, [category]);

  if (error) return <div className="error-banner">{error}</div>;
  if (!taxonomyRows) return <div className="empty-state">Loading...</div>;

  const chartData = taxonomyRows.map((row) => ({
    subcategory: row.subcategory,
    count: counts.find((c) => c.subcategory === row.subcategory)?.count || 0,
  }));

  return (
    <div>
      <p>
        <Link to="/taxonomy">&larr; taxonomy</Link>
      </p>
      <h2>{category}</h2>

      <div className="panel">
        <h3>Fault volume by subcategory (last 30 days, all servers)</h3>
        <BarChart data={chartData} labelKey="subcategory" valueKey="count" />
      </div>

      <div className="panel">
        <h3>Subcategories</h3>
        <table>
          <thead>
            <tr>
              <th>Subcategory</th>
              <th>Description</th>
              <th>Confirmed %</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {taxonomyRows.map((row, i) => (
              <tr key={i}>
                <td>{row.subcategory}</td>
                <td style={{ fontSize: 13, color: "var(--text-dim)" }}>{row.text}</td>
                <td>{row.confirmed_pct != null ? `${row.confirmed_pct}%` : "—"}</td>
                <td>
                  <Link to={`/taxonomy/${encodeURIComponent(category)}/${encodeURIComponent(row.subcategory)}`}>
                    view events
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
