import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const {
  formatCost,
  formatTokens,
  formatDuration,
  formatRelativeTime,
  formatPercentage,
  formatFilename,
  truncateText,
} = await import("../formatters.js");

// -- formatCost --

describe("formatCost", () => {
  it("formats a number to $X.XX", () => {
    expect(formatCost(5)).toBe("$5.00");
  });

  it("formats decimals to two places", () => {
    expect(formatCost(1.5)).toBe("$1.50");
    expect(formatCost(99.999)).toBe("$100.00");
  });

  it("returns $0.00 for non-number input", () => {
    expect(formatCost("hello")).toBe("$0.00");
    expect(formatCost(null)).toBe("$0.00");
    expect(formatCost(undefined)).toBe("$0.00");
  });

  it("handles zero", () => {
    expect(formatCost(0)).toBe("$0.00");
  });

  it("handles large numbers", () => {
    expect(formatCost(123456.78)).toBe("$123456.78");
  });
});

// -- formatTokens --

describe("formatTokens", () => {
  it("adds locale separators for large numbers", () => {
    const result = formatTokens(1234567);
    // toLocaleString output varies by environment, but should contain separators
    expect(result).toContain("1");
    expect(result).toContain("234");
    expect(result).toContain("567");
  });

  it('returns "0" for non-number input', () => {
    expect(formatTokens("abc")).toBe("0");
    expect(formatTokens(null)).toBe("0");
    expect(formatTokens(undefined)).toBe("0");
  });

  it("formats small numbers without separators", () => {
    expect(formatTokens(42)).toBe("42");
  });
});

// -- formatDuration --

describe("formatDuration", () => {
  it("returns seconds only when under 60", () => {
    expect(formatDuration(45)).toBe("45s");
  });

  it("returns minutes and seconds", () => {
    expect(formatDuration(125)).toBe("2m 5s");
  });

  it("returns hours, minutes, and seconds", () => {
    expect(formatDuration(3661)).toBe("1h 1m 1s");
  });

  it('returns "0s" for negative values', () => {
    expect(formatDuration(-10)).toBe("0s");
  });

  it('returns "0s" for non-number input', () => {
    expect(formatDuration("fast")).toBe("0s");
    expect(formatDuration(null)).toBe("0s");
  });

  it('returns "0s" for zero', () => {
    expect(formatDuration(0)).toBe("0s");
  });

  it("floors fractional seconds", () => {
    expect(formatDuration(3.9)).toBe("3s");
  });
});

// -- formatRelativeTime --

describe("formatRelativeTime", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-02-05T12:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns "Never" for falsy timestamp', () => {
    expect(formatRelativeTime(null)).toBe("Never");
    expect(formatRelativeTime("")).toBe("Never");
    expect(formatRelativeTime(undefined)).toBe("Never");
  });

  it('returns "Just now" for timestamps less than 60 seconds ago', () => {
    const thirtySecsAgo = new Date("2026-02-05T11:59:35Z").toISOString();
    expect(formatRelativeTime(thirtySecsAgo)).toBe("Just now");
  });

  it('returns singular "1 minute ago"', () => {
    const oneMinAgo = new Date("2026-02-05T11:59:00Z").toISOString();
    expect(formatRelativeTime(oneMinAgo)).toBe("1 minute ago");
  });

  it("returns plural minutes ago", () => {
    const fiveMinAgo = new Date("2026-02-05T11:55:00Z").toISOString();
    expect(formatRelativeTime(fiveMinAgo)).toBe("5 minutes ago");
  });

  it('returns singular "1 hour ago"', () => {
    const oneHourAgo = new Date("2026-02-05T11:00:00Z").toISOString();
    expect(formatRelativeTime(oneHourAgo)).toBe("1 hour ago");
  });

  it("returns plural hours ago", () => {
    const threeHoursAgo = new Date("2026-02-05T09:00:00Z").toISOString();
    expect(formatRelativeTime(threeHoursAgo)).toBe("3 hours ago");
  });

  it('returns singular "1 day ago"', () => {
    const oneDayAgo = new Date("2026-02-04T12:00:00Z").toISOString();
    expect(formatRelativeTime(oneDayAgo)).toBe("1 day ago");
  });

  it("returns plural days ago", () => {
    const threeDaysAgo = new Date("2026-02-02T12:00:00Z").toISOString();
    expect(formatRelativeTime(threeDaysAgo)).toBe("3 days ago");
  });
});

// -- formatPercentage --

describe("formatPercentage", () => {
  it("formats with default 1 decimal place", () => {
    expect(formatPercentage(75.5)).toBe("75.5%");
    expect(formatPercentage(33.3)).toBe("33.3%");
  });

  it("formats with custom decimal places", () => {
    expect(formatPercentage(33.3333, 2)).toBe("33.33%");
  });

  it('returns "0%" for non-number input', () => {
    expect(formatPercentage("high")).toBe("0%");
    expect(formatPercentage(null)).toBe("0%");
  });
});

// -- formatFilename --

describe("formatFilename", () => {
  it("extracts filename from a path", () => {
    expect(formatFilename("/Users/dev/project/index.ts")).toBe("index.ts");
  });

  it("returns empty string for falsy input", () => {
    expect(formatFilename(null)).toBe("");
    expect(formatFilename("")).toBe("");
    expect(formatFilename(undefined)).toBe("");
  });

  it("returns the string itself when no separators are present", () => {
    expect(formatFilename("readme.md")).toBe("readme.md");
  });
});

// -- truncateText --

describe("truncateText", () => {
  it("returns text unchanged when under the limit", () => {
    expect(truncateText("short", 50)).toBe("short");
  });

  it("truncates with ellipsis when over the limit", () => {
    const long = "a".repeat(60);
    const result = truncateText(long, 20);
    expect(result).toBe("a".repeat(17) + "...");
    expect(result.length).toBe(20);
  });

  it("returns falsy input unchanged", () => {
    expect(truncateText(null)).toBe(null);
    expect(truncateText("")).toBe("");
    expect(truncateText(undefined)).toBe(undefined);
  });

  it("uses a default limit of 50", () => {
    const exactly50 = "b".repeat(50);
    expect(truncateText(exactly50)).toBe(exactly50);

    const fiftyOne = "c".repeat(51);
    expect(truncateText(fiftyOne)).toBe("c".repeat(47) + "...");
  });
});
