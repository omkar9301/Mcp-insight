import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import LitmCounterfactualPanel from "./LitmCounterfactualPanel.jsx";

describe("LitmCounterfactualPanel", () => {
  it("shows a fallback when no items have scores", () => {
    render(<LitmCounterfactualPanel items={[{ position: 0, score: null }]} />);
    expect(screen.getByText(/not enough data/i)).toBeInTheDocument();
  });

  it("computes the real result count and best-match position from captured scores", () => {
    const items = [
      { position: 0, score: 0.1 },
      { position: 1, score: 0.2 },
      { position: 2, score: 0.3 },
      { position: 3, score: 0.9 }, // the actual best match, buried in the middle of the list
    ];
    render(<LitmCounterfactualPanel items={items} />);
    expect(screen.getByText("4 results sent")).toBeInTheDocument();
    // best match was #4 in the 1-indexed list (position 3)
    expect(screen.getByText(/best match was #4 in the list/i)).toBeInTheDocument();
    // far enough back that reordering is a real, meaningful improvement
    expect(screen.getByText(/meaningful move/i)).toBeInTheDocument();
  });

  it("says reordering wouldn't help when the best match is already first", () => {
    const items = [
      { position: 0, score: 0.9 },
      { position: 1, score: 0.1 },
    ];
    render(<LitmCounterfactualPanel items={items} />);
    expect(screen.getByText(/already first/i)).toBeInTheDocument();
  });
});
