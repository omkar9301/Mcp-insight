const DEFAULTS = {
  ingestionUrl: import.meta.env.VITE_INGESTION_URL || "http://localhost:8000",
  classifierUrl: import.meta.env.VITE_CLASSIFIER_URL || "http://localhost:8100",
  apiKey: import.meta.env.VITE_API_KEY || "",
};

export function getSettings() {
  const stored = localStorage.getItem("mcp_insight_settings");
  if (stored) {
    try {
      return { ...DEFAULTS, ...JSON.parse(stored) };
    } catch {
      return DEFAULTS;
    }
  }
  return DEFAULTS;
}

export function saveSettings(settings) {
  localStorage.setItem("mcp_insight_settings", JSON.stringify(settings));
}

class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `Request failed with status ${status}`);
    this.status = status;
  }
}

async function request(baseUrl, path, options = {}) {
  const { apiKey } = getSettings();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

  const resp = await fetch(`${baseUrl}${path}`, { ...options, headers });
  if (!resp.ok) {
    let detail;
    try {
      detail = (await resp.json()).detail;
    } catch {
      detail = resp.statusText;
    }
    throw new ApiError(resp.status, detail);
  }
  return resp.json();
}

export const ingestionApi = {
  listServers: () => request(getSettings().ingestionUrl, "/v1/servers"),
  getHealth: (serverId, windowMinutes = 60) =>
    request(getSettings().ingestionUrl, `/v1/servers/${encodeURIComponent(serverId)}/health?window_minutes=${windowMinutes}`),
  getAnomalies: (serverId, windowMinutes = 15) =>
    request(getSettings().ingestionUrl, `/v1/servers/${encodeURIComponent(serverId)}/anomalies?window_minutes=${windowMinutes}`),
  getEvents: (serverId, { onlyFaults = false, limit = 50 } = {}) =>
    request(
      getSettings().ingestionUrl,
      `/v1/servers/${encodeURIComponent(serverId)}/events?limit=${limit}&only_faults=${onlyFaults}`
    ),
};

export const classifierApi = {
  getTaxonomy: () => request(getSettings().classifierUrl, "/v1/taxonomy"),
  classify: (text, topK = 3) =>
    request(getSettings().classifierUrl, "/v1/classify", {
      method: "POST",
      body: JSON.stringify({ text, top_k: topK }),
    }),
};

export { ApiError };
