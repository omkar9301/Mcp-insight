import { describe, it, expect } from "vitest";
import { statusRank, formatRelativeTime } from "./utils.js";

describe("statusRank", () => {
  it("ranks critical worse than healthy", () => {
    expect(statusRank("critical")).toBeLessThan(statusRank("healthy"));
  });

  it("falls back to the unknown rank for an unrecognized status", () => {
    expect(statusRank("something-new")).toBe(statusRank("unknown"));
  });
});

describe("formatRelativeTime", () => {
  it("returns 'never' for a falsy timestamp", () => {
    expect(formatRelativeTime(null)).toBe("never");
    expect(formatRelativeTime(0)).toBe("never");
  });

  it("returns 'just now' for a timestamp within the last few seconds", () => {
    expect(formatRelativeTime(Date.now() / 1000)).toBe("just now");
  });

  it("formats minutes ago", () => {
    const tenMinutesAgo = Date.now() / 1000 - 10 * 60;
    expect(formatRelativeTime(tenMinutesAgo)).toBe("10m ago");
  });

  it("formats days ago", () => {
    const threeDaysAgo = Date.now() / 1000 - 3 * 24 * 60 * 60;
    expect(formatRelativeTime(threeDaysAgo)).toBe("3d ago");
  });
});
