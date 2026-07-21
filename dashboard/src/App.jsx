import React from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import ServerList from "./components/ServerList.jsx";
import ServerDetail from "./components/ServerDetail.jsx";
import Settings from "./components/Settings.jsx";
import Taxonomy from "./components/Taxonomy.jsx";

export default function App() {
  return (
    <div className="app-shell">
      <div className="sidebar">
        <h1>mcp-insight</h1>
        <nav>
          <NavLink to="/" end className={({ isActive }) => (isActive ? "active" : "")}>
            Servers
          </NavLink>
          <NavLink to="/taxonomy" className={({ isActive }) => (isActive ? "active" : "")}>
            Fault Taxonomy
          </NavLink>
          <NavLink to="/settings" className={({ isActive }) => (isActive ? "active" : "")}>
            Settings
          </NavLink>
        </nav>
      </div>
      <div className="main">
        <Routes>
          <Route path="/" element={<ServerList />} />
          <Route path="/servers/:serverId" element={<ServerDetail />} />
          <Route path="/taxonomy" element={<Taxonomy />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </div>
    </div>
  );
}
