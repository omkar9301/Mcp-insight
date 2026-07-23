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
  getTimeseries: (serverId, windowMinutes = 15, buckets = 24) =>
    request(
      getSettings().ingestionUrl,
      `/v1/servers/${encodeURIComponent(serverId)}/timeseries?window_minutes=${windowMinutes}&buckets=${buckets}`
    ),
  getAlertHistory: (serverId, limit = 20) =>
    request(getSettings().ingestionUrl, `/v1/servers/${encodeURIComponent(serverId)}/alerts?limit=${limit}`),
  muteAlerts: (serverId, minutes) =>
    request(getSettings().ingestionUrl, `/v1/servers/${encodeURIComponent(serverId)}/mute`, {
      method: "POST",
      body: JSON.stringify({ minutes }),
    }),
  unmuteAlerts: (serverId) =>
    request(getSettings().ingestionUrl, `/v1/servers/${encodeURIComponent(serverId)}/mute`, { method: "DELETE" }),
  mintKey: (serverId) =>
    request(getSettings().ingestionUrl, `/v1/servers/${encodeURIComponent(serverId)}/keys`, { method: "POST" }),
  revokeKey: (serverId) =>
    request(getSettings().ingestionUrl, `/v1/servers/${encodeURIComponent(serverId)}/keys`, { method: "DELETE" }),
  getEventsByClassification: (category, subcategory, limit = 50) =>
    request(
      getSettings().ingestionUrl,
      `/v1/events/by-classification?category=${encodeURIComponent(category)}&subcategory=${encodeURIComponent(subcategory)}&limit=${limit}`
    ),
  getEventsBySeverity: (severity, limit = 50) =>
    request(getSettings().ingestionUrl, `/v1/events/by-severity?severity=${encodeURIComponent(severity)}&limit=${limit}`),
  getCategoryCounts: (windowMinutes = 1440) =>
    request(getSettings().ingestionUrl, `/v1/stats/category-counts?window_minutes=${windowMinutes}`),
  getSeverityBreakdown: (windowMinutes = 1440) =>
    request(getSettings().ingestionUrl, `/v1/stats/severity-breakdown?window_minutes=${windowMinutes}`),
  getHealthDistribution: () => request(getSettings().ingestionUrl, "/v1/stats/health-distribution"),
  getHeatmap: (serverId, hours = 168) =>
    request(getSettings().ingestionUrl, `/v1/servers/${encodeURIComponent(serverId)}/heatmap?hours=${hours}`),
  getClassificationAccuracy: () => request(getSettings().ingestionUrl, "/v1/stats/classification-accuracy"),
  submitFeedback: (serverId, ts, correct, note) =>
    request(getSettings().ingestionUrl, `/v1/servers/${encodeURIComponent(serverId)}/events/${ts}/feedback`, {
      method: "POST",
      body: JSON.stringify({ correct, note }),
    }),
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
