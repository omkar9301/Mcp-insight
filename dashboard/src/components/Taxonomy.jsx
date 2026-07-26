import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { classifierApi, ingestionApi } from "../api.js";
import InfoTooltip from "./InfoTooltip.jsx";

const SEVERITY_COLORS = { minor: "var(--healthy)", major: "var(--degraded)", critical: "var(--critical)" };
const SEVERITY_ORDER = ["minor", "major", "critical"];

function dominant(dist) {
  if (!dist || Object.keys(dist).length === 0) return "—";
  return Object.entries(dist).sort((a, b) => b[1] - a[1])[0][0];
}

function severityBadgeClass(sev) {
  if (sev === "critical") return "critical";
  if (sev === "major") return "unhealthy";
  return "healthy";
}

function MiniDistributionBar({ dist }) {
  if (!dist || Object.keys(dist).length === 0) return <span style={{ color: "var(--text-dim)" }}>—</span>;
  const total = SEVERITY_ORDER.reduce((sum, k) => sum + (dist[k] || 0), 0);
  if (total === 0) return <span style={{ color: "var(--text-dim)" }}>—</span>;
  const title = SEVERITY_ORDER.map((k) => `${k}: ${dist[k] || 0}%`).join(", ");
  return (
    <div title={title} style={{ display: "flex", height: 10, width: 100, borderRadius: 3, overflow: "hidden", border: "1px solid var(--border)" }}>
      {SEVERITY_ORDER.map((k) =>
        dist[k] ? <div key={k} style={{ width: `${(dist[k] / total) * 100}%`, background: SEVERITY_COLORS[k] }} /> : null
      )}
    </div>
  );
}

export default function Taxonomy() {
  const [taxonomy, setTaxonomy] = useState(null);
  const [counts, setCounts] = useState({});
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [sortByOccurrences, setSortByOccurrences] = useState(false);
  const [showMethodology, setShowMethodology] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([classifierApi.getTaxonomy(), ingestionApi.getCategoryCounts(43200)])
      .then(([t, c]) => {
        setTaxonomy(t.taxonomy);
        const map = {};
        for (const row of c.rows) map[`${row.category}::${row.subcategory}`] = row.count;
        setCounts(map);
      })
      .catch((e) => setError(e.message));
  }, []);

  const categories = useMemo(() => (taxonomy ? [...new Set(taxonomy.map((r) => r.category))] : []), [taxonomy]);

  const rows = useMemo(() => {
    if (!taxonomy) return [];
    let filtered = taxonomy.map((row) => ({
      ...row,
      occurrences: counts[`${row.category}::${row.subcategory}`] || 0,
      dominantSeverity: dominant(row.severity),
    }));
    if (categoryFilter !== "all") filtered = filtered.filter((r) => r.category === categoryFilter);
    if (severityFilter !== "all") filtered = filtered.filter((r) => r.dominantSeverity === severityFilter);
    if (search) {
      const q = search.toLowerCase();
      filtered = filtered.filter(
        (r) => r.category.toLowerCase().includes(q) || r.subcategory.toLowerCase().includes(q) || (r.text || "").toLowerCase().includes(q)
      );
    }
    if (sortByOccurrences) {
      filtered = [...filtered].sort((a, b) => b.occurrences - a.occurrences);
    }
    return filtered;
  }, [taxonomy, counts, categoryFilter, severityFilter, search, sortByOccurrences]);

  if (error) return <div className="error-banner">Failed to load taxonomy: {error}</div>;
  if (!taxonomy) return <div className="empty-state">Loading...</div>;

  const totalSeen = Object.values(counts).reduce((a, b) => a + b, 0);
  const subcategoriesSeen = Object.values(counts).filter((c) => c > 0).length;

  return (
    <div>
      <h2>Real MCP Fault Taxonomy</h2>
      <p style={{ color: "var(--text-dim)", fontSize: 13 }}>
        27 subcategories sourced from Owotogbe et al. (2026), "A Taxonomy of Runtime Faults in Model Context
        Protocol Servers" — 837 confirmed fault threads across 473 real MCP repos, validated by 55 real MCP
        developers. Click a subcategory to see live matching events across all servers.{" "}
        <span style={{ cursor: "pointer", textDecoration: "underline" }} onClick={() => setShowMethodology((s) => !s)}>
          {showMethodology ? "Hide" : "About this taxonomy"}
        </span>
      </p>

      {showMethodology && (
        <div className="panel" style={{ fontSize: 13 }}>
          <strong>Methodology</strong>
          <p style={{ marginBottom: 0 }}>
            The source study mined 837 confirmed runtime-fault threads across 473 real, public MCP server
            repositories, then had 55 practicing MCP developers manually validate that each thread was correctly
            categorized. "Confirmed %" per subcategory reflects how much of the reviewed fault population that
            category actually accounted for -- higher means it's a common, well-established failure mode, not a
            rare edge case invented for this taxonomy. Every fault this platform auto-classifies is matched
            against these exact 27 subcategories (TF-IDF text similarity, with an optional LLM fallback for
            low-confidence matches) -- it isn't inventing its own categories.
          </p>
        </div>
      )}

      <div className="grid">
        <div className="stat-tile">
          <div className="label">
            Subcategories seen in your fleet
            <InfoTooltip text="How many of the 27 real subcategories have actually been auto-classified from your servers' traffic (last 30 days). The rest have simply never happened here yet -- not a gap in coverage." />
          </div>
          <div className="value">
            {subcategoriesSeen} <span style={{ fontSize: 14, color: "var(--text-dim)" }}>/ 27</span>
          </div>
        </div>
        <div className="stat-tile">
          <div className="label">Total classified faults (30d)</div>
          <div className="value">{totalSeen}</div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", margin: "16px 0" }}>
        <input placeholder="Search category, subcategory, description..." value={search} onChange={(e) => setSearch(e.target.value)} style={{ width: 260 }} />
        <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
          <option value="all">All categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)}>
          <option value="all">All severities</option>
          {SEVERITY_ORDER.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <label style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 4 }}>
          <input type="checkbox" checked={sortByOccurrences} onChange={(e) => setSortByOccurrences(e.target.checked)} />
          Sort by occurrences in your fleet
        </label>
      </div>

      {rows.length === 0 ? (
        <div className="empty-state">No taxonomy rows match this filter.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Category</th>
              <th>Subcategory</th>
              <th>
                In your fleet (30d)
                <InfoTooltip text="Count of auto-classified events across all your servers in the last 30 days. Zero doesn't mean broken instrumentation -- it just means this specific fault type hasn't happened on your servers yet." />
              </th>
              <th>Confirmed %</th>
              <th>Severity distribution</th>
              <th>Dominant effort</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} style={row.occurrences === 0 ? { opacity: 0.55 } : undefined}>
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
                <td
                  style={{ cursor: row.occurrences > 0 ? "pointer" : "default" }}
                  onClick={() =>
                    row.occurrences > 0 &&
                    navigate(`/taxonomy/${encodeURIComponent(row.category)}/${encodeURIComponent(row.subcategory)}`)
                  }
                >
                  {row.occurrences > 0 ? (
                    <span className="badge healthy" style={{ background: "var(--accent)" }}>
                      {row.occurrences}
                    </span>
                  ) : (
                    <span style={{ color: "var(--text-dim)" }}>never seen</span>
                  )}
                </td>
                <td>{row.confirmed_pct != null ? `${row.confirmed_pct}%` : "—"}</td>
                <td>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <MiniDistributionBar dist={row.severity} />
                    <span className={`badge ${severityBadgeClass(row.dominantSeverity)}`}>{row.dominantSeverity}</span>
                  </div>
                </td>
                <td>{dominant(row.effort)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
