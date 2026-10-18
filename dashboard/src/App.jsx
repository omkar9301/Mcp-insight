import React from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import ServerList from "./components/ServerList.jsx";
import ServerDetail from "./components/ServerDetail.jsx";
import Settings from "./components/Settings.jsx";
import Taxonomy from "./components/Taxonomy.jsx";
import TaxonomyDrilldown from "./components/TaxonomyDrilldown.jsx";
import CategoryPage from "./components/CategoryPage.jsx";
import SeverityPage from "./components/SeverityPage.jsx";
import ConnectivityBadge from "./components/ConnectivityBadge.jsx";
import ToolsPage from "./components/ToolsPage.jsx";
import SecurityPage from "./components/SecurityPage.jsx";
import LostInMiddleInsights from "./components/LostInMiddleInsights.jsx";

function NavItem({ to, end, icon, children }) {
  return (
    <NavLink to={to} end={end} className={({ isActive }) => (isActive ? "active" : "")}>
      <span className="nav-icon" aria-hidden="true">{icon}</span>
      {children}
    </NavLink>
  );
}

export default function App() {
  return (
    <div className="app-shell">
      <div className="sidebar">
        <div className="brand">
          <span className="brand-mark">◆</span>
          <div>
            <h1>mcp-insight</h1>
            <div className="brand-sub">MCP observability</div>
          </div>
        </div>

        <div className="nav-group-label">Monitor</div>
        <nav>
          <NavItem to="/" end icon="📊">Overview</NavItem>
          <NavItem to="/tools" icon="🧰">Tool Registry</NavItem>
          <NavItem to="/taxonomy" icon="🗂️">Fault Taxonomy</NavItem>
        </nav>

        <div className="nav-group-label">Risk</div>
        <nav>
          <NavItem to="/security" icon="🛡️">Security</NavItem>
          <NavItem to="/litm" icon="⚠️">Lost in the Middle</NavItem>
        </nav>

        <div className="nav-group-label">System</div>
        <nav>
          <NavItem to="/settings" icon="⚙️">Settings</NavItem>
        </nav>

        <div className="sidebar-footer">
          <ConnectivityBadge />
        </div>
      </div>
      <div className="main">
        <Routes>
          <Route path="/" element={<ServerList />} />
          <Route path="/servers/:serverId" element={<ServerDetail />} />
          <Route path="/tools" element={<ToolsPage />} />
          <Route path="/security" element={<SecurityPage />} />
          <Route path="/litm" element={<LostInMiddleInsights />} />
          <Route path="/taxonomy" element={<Taxonomy />} />
          <Route path="/taxonomy/:category/:subcategory" element={<TaxonomyDrilldown />} />
          <Route path="/category/:category" element={<CategoryPage />} />
          <Route path="/severity/:severity" element={<SeverityPage />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </div>
    </div>
  );
}
