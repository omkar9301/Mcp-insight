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

export default function App() {
  return (
    <div className="app-shell">
      <div className="sidebar">
        <h1>mcp-insight</h1>
        <nav>
          <NavLink to="/" end className={({ isActive }) => (isActive ? "active" : "")}>
            Overview
          </NavLink>
          <NavLink to="/tools" className={({ isActive }) => (isActive ? "active" : "")}>
            Tool Registry
          </NavLink>
          <NavLink to="/security" className={({ isActive }) => (isActive ? "active" : "")}>
            Security
          </NavLink>
          <NavLink to="/litm" className={({ isActive }) => (isActive ? "active" : "")}>
            ⚠️ Lost in the Middle
          </NavLink>
          <NavLink to="/taxonomy" className={({ isActive }) => (isActive ? "active" : "")}>
            Fault Taxonomy
          </NavLink>
          <NavLink to="/settings" className={({ isActive }) => (isActive ? "active" : "")}>
            Settings
          </NavLink>
        </nav>
        <ConnectivityBadge />
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
