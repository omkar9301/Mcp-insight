import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import ScatterChart from "./ScatterChart.jsx";

describe("ScatterChart", () => {
  it("shows the empty state when there are no scored items", () => {
    render(<ScatterChart points={[]} />);
    expect(screen.getByText(/no per-item score data/i)).toBeInTheDocument();
  });

  it("filters out points missing a position or score instead of crashing", () => {
    const points = [
      { position: 0, score: 0.9 },
      { position: 1 }, // missing score -- must be dropped, not rendered as NaN
      { score: 0.5 }, // missing position -- must be dropped
    ];
    const { container } = render(<ScatterChart points={points} />);
    expect(container.querySelectorAll("circle.scatter-dot").length).toBe(1);
  });

  it("renders one circle per valid point", () => {
    const points = [
      { position: 0, score: 0.9 },
      { position: 1, score: 0.2 },
      { position: 2, score: 0.5 },
    ];
    const { container } = render(<ScatterChart points={points} />);
    expect(container.querySelectorAll("circle.scatter-dot").length).toBe(3);
  });

  it("labels the axis endpoints in human terms", () => {
    render(<ScatterChart points={[{ position: 0, score: 0.9 }, { position: 4, score: 0.1 }]} />);
    expect(screen.getByText(/shown to ai first/i)).toBeInTheDocument();
    expect(screen.getByText(/shown to ai last/i)).toBeInTheDocument();
  });
});
