import React from "react";

export default function HealthBadge({ status, score }) {
  if (!status) return <span className="badge">unknown</span>;
  return (
    <span className={`badge ${status}`}>
      {status} {typeof score === "number" ? `| ${score}` : ""}
    </span>
  );
}
