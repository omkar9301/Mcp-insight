import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { pingService, getSettings } from "../api.js";

// Sidebar status dot -- pings both backend services' unauthenticated root
// endpoints so misconfiguration (wrong URL, backend down) shows up as one
// clear signal instead of scattered per-page error banners.
export default function ConnectivityBadge() {
  const [ingestionUp, setIngestionUp] = useState(null);
  const [classifierUp, setClassifierUp] = useState(null);

  async function check() {
    const { ingestionUrl, classifierUrl } = getSettings();
    setIngestionUp(await pingService(ingestionUrl));
    setClassifierUp(await pingService(classifierUrl));
  }

  useEffect(() => {
    check();
    const id = setInterval(check, 20000);
    return () => clearInterval(id);
  }, []);

  if (ingestionUp === null) return null;

  const allUp = ingestionUp && classifierUp;
  const color = allUp ? "var(--healthy)" : "var(--critical)";
  const label = allUp ? "Connected" : "Connection problem";

  return (
    <Link
      to="/settings"
      style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-dim)", marginTop: 16, textDecoration: "none" }}
      title={`Ingestion: ${ingestionUp ? "up" : "unreachable"} · Classifier: ${classifierUp ? "up" : "unreachable"}`}
    >
      <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, display: "inline-block" }} />
      {label}
    </Link>
  );
}
