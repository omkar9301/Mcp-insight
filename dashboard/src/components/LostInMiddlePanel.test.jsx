import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import LostInMiddlePanel, { RISK_INFO } from "./LostInMiddlePanel.jsx";

function renderPanel(props) {
  return render(
    <MemoryRouter>
      <LostInMiddlePanel {...props} />
    </MemoryRouter>
  );
}

describe("RISK_INFO", () => {
  it("gives every risk factor a plain-language label and a what/why/do explanation", () => {
    for (const [factor, info] of Object.entries(RISK_INFO)) {
      expect(info.label, `${factor} missing a label`).toBeTruthy();
      expect(info.what, `${factor} missing 'what'`).toBeTruthy();
      expect(info.why, `${factor} missing 'why'`).toBeTruthy();
      expect(info.doNext, `${factor} missing 'doNext'`).toBeTruthy();
    }
  });
});

describe("LostInMiddlePanel", () => {
  it("shows a reassuring empty state when nothing is flagged", () => {
    renderPanel({ rows: [] });
    expect(screen.getByText(/nothing flagged/i)).toBeInTheDocument();
  });

  it("renders a plain-language risk chip, not the raw factor code", () => {
    renderPanel({
      rows: [{ tool_name: "search_kb", flagged_calls: 2, risk_factor_counts: { large_result_set: 2 }, avg_approx_tokens: 500, last_seen: Date.now() / 1000 }],
      serverId: "demo-litm",
    });
    expect(screen.getByText(/too many search results at once/i)).toBeInTheDocument();
    expect(screen.queryByText(/large_result_set/)).not.toBeInTheDocument();
  });

  it("links the tool name into the /litm deep-dive with the right query params", () => {
    renderPanel({
      rows: [{ tool_name: "search_kb", flagged_calls: 1, risk_factor_counts: {}, avg_approx_tokens: null, last_seen: Date.now() / 1000 }],
      serverId: "demo-litm",
    });
    const link = screen.getByRole("link", { name: /search_kb/ });
    expect(link.getAttribute("href")).toBe("/litm?server=demo-litm&tool=search_kb");
  });
});
