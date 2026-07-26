export const STATUS_RANK = { critical: 0, unhealthy: 1, degraded: 2, healthy: 3, idle: 4, unknown: 5 };

export function statusRank(status) {
  return STATUS_RANK[status] ?? 5;
}

export function formatRelativeTime(unixSeconds) {
  if (!unixSeconds) return "never";
  const diffMs = Date.now() - unixSeconds * 1000;
  const diffSec = Math.round(diffMs / 1000);
  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  return `${diffDay}d ago`;
}

export const STATUS_BORDER_COLOR = {
  critical: "var(--critical)",
  unhealthy: "var(--unhealthy)",
  degraded: "var(--degraded)",
  healthy: "var(--healthy)",
  idle: "var(--border)",
  unknown: "var(--border)",
};
