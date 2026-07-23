import React, { useState } from "react";

// Lightweight info-icon tooltip -- click/tap to toggle rather than
// hover-only, so it works on touch too.
export default function InfoTooltip({ text }) {
  const [open, setOpen] = useState(false);
  return (
    <span style={{ position: "relative", display: "inline-block", marginLeft: 6 }}>
      <span
        onClick={() => setOpen((o) => !o)}
        style={{
          cursor: "pointer",
          fontSize: 11,
          width: 15,
          height: 15,
          borderRadius: "50%",
          border: "1px solid var(--text-dim)",
          color: "var(--text-dim)",
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          userSelect: "none",
        }}
      >
        i
      </span>
      {open && (
        <span
          style={{
            position: "absolute",
            zIndex: 10,
            top: "140%",
            left: 0,
            width: 240,
            background: "var(--bg-panel)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            padding: "8px 10px",
            fontSize: 12,
            fontWeight: 400,
            color: "var(--text)",
            boxShadow: "0 4px 12px rgba(0,0,0,0.25)",
          }}
        >
          {text}
        </span>
      )}
    </span>
  );
}
