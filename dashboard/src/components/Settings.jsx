import React, { useState } from "react";
import { getSettings, saveSettings } from "../api.js";

export default function Settings() {
  const [settings, setSettings] = useState(getSettings());
  const [saved, setSaved] = useState(false);

  function update(key, value) {
    setSettings((s) => ({ ...s, [key]: value }));
    setSaved(false);
  }

  function onSave() {
    saveSettings(settings);
    setSaved(true);
  }

  return (
    <div>
      <h2>Settings</h2>
      <div className="panel" style={{ maxWidth: 480 }}>
        <div className="form-row">
          <label>Ingestion API URL</label>
          <input value={settings.ingestionUrl} onChange={(e) => update("ingestionUrl", e.target.value)} />
        </div>
        <div className="form-row">
          <label>Classifier API URL</label>
          <input value={settings.classifierUrl} onChange={(e) => update("classifierUrl", e.target.value)} />
        </div>
        <div className="form-row">
          <label>API key (matches MCP_INSIGHT_API_KEY on the backend)</label>
          <input type="password" value={settings.apiKey} onChange={(e) => update("apiKey", e.target.value)} />
        </div>
        <button onClick={onSave}>Save</button>
        {saved && <span style={{ marginLeft: 10, fontSize: 13, color: "var(--healthy)" }}>Saved.</span>}
      </div>
    </div>
  );
}
