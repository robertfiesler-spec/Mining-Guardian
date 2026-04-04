import { describe, it, expect } from "vitest";

// Provide a Node-compatible escapeHtml global
// (in browser, formatters.js supplies this via DOM; tests need a string-based shim)
globalThis.escapeHtml = (str) => {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
};

const { getContextClass, getStatusBadge, getTypeBadge } =
  await import("../agent-panel.js");

// -- getContextClass --

describe("getContextClass", () => {
  it('returns "context-critical" for percentage >= 90', () => {
    expect(getContextClass(95)).toBe("context-critical");
  });

  it('returns "context-critical" at exact 90 boundary', () => {
    expect(getContextClass(90)).toBe("context-critical");
  });

  it('returns "context-critical" for 100', () => {
    expect(getContextClass(100)).toBe("context-critical");
  });

  it('returns "context-warning" for percentage >= 75 and < 90', () => {
    expect(getContextClass(80)).toBe("context-warning");
  });

  it('returns "context-warning" at exact 75 boundary', () => {
    expect(getContextClass(75)).toBe("context-warning");
  });

  it('returns "context-normal" for percentage < 75', () => {
    expect(getContextClass(50)).toBe("context-normal");
  });

  it('returns "context-normal" for 0', () => {
    expect(getContextClass(0)).toBe("context-normal");
  });
});

// -- getStatusBadge --

describe("getStatusBadge", () => {
  it('returns a success badge for "active"', () => {
    const badge = getStatusBadge("active");
    expect(badge).toContain("badge-success");
    expect(badge).toContain("Active");
  });

  it('returns an info badge for "completed"', () => {
    const badge = getStatusBadge("completed");
    expect(badge).toContain("badge-info");
    expect(badge).toContain("Completed");
  });

  it('returns an error badge for "error"', () => {
    const badge = getStatusBadge("error");
    expect(badge).toContain("badge-error");
    expect(badge).toContain("Error");
  });

  it('returns a warning badge for "pending"', () => {
    const badge = getStatusBadge("pending");
    expect(badge).toContain("badge-warning");
    expect(badge).toContain("Pending");
  });

  it('returns an "Unknown" badge for unrecognized status', () => {
    const badge = getStatusBadge("something-else");
    expect(badge).toContain("badge-secondary");
    expect(badge).toContain("Unknown");
  });
});

// -- getTypeBadge --

describe("getTypeBadge", () => {
  it('returns badge with search icon for "explorer"', () => {
    const badge = getTypeBadge("explorer");
    expect(badge).toContain("Explorer");
    expect(badge).toContain("agent-type-badge");
  });

  it('returns badge with target icon for "orchestrator"', () => {
    const badge = getTypeBadge("orchestrator");
    expect(badge).toContain("Orchestrator");
  });

  it('returns badge with gear icon for "worker"', () => {
    const badge = getTypeBadge("worker");
    expect(badge).toContain("Worker");
  });

  it('returns badge with bug icon for "debugger"', () => {
    const badge = getTypeBadge("debugger");
    expect(badge).toContain("Debugger");
  });

  it('returns a generic badge with "Unknown" for unrecognized type', () => {
    const badge = getTypeBadge(undefined);
    expect(badge).toContain("Unknown");
    expect(badge).toContain("agent-type-badge");
  });
});
