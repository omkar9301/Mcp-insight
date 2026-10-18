import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import Histogram from "./Histogram.jsx";

describe("Histogram", () => {
  it("shows the empty state when there are no values", () => {
    render(<Histogram values={[]} />);
    expect(screen.getByText(/no data yet/i)).toBeInTheDocument();
  });

  it("ignores non-numeric and NaN values instead of crashing", () => {
    render(<Histogram values={[1, 2, null, undefined, NaN, "x", 3]} />);
    expect(screen.queryByText(/no data yet/i)).not.toBeInTheDocument();
  });

  it("labels the axis with the provided xLabel/yLabel", () => {
    render(<Histogram values={[0.1, 0.5, 0.9]} xLabel="quality score" yLabel="results" />);
    expect(screen.getByText(/results — grouped by quality score/i)).toBeInTheDocument();
  });

  it("shows the correct low/high range in the footer", () => {
    render(<Histogram values={[2, 5, 9]} />);
    expect(screen.getByText(/low: 2\.00/)).toBeInTheDocument();
    expect(screen.getByText(/high: 9\.00/)).toBeInTheDocument();
  });
});
