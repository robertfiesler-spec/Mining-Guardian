/**
 * Utility formatters for displaying data
 * Used by dashboard and agent panel components
 */

/**
 * Escape HTML to prevent XSS when rendering untrusted strings into HTML.
 * @param {string} str - String to escape
 * @returns {string} Escaped string safe to interpolate into HTML
 */
function escapeHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

/**
 * Format cost as currency
 */
function formatCost(cost) {
  if (typeof cost !== "number") return "$0.00";
  return `$${cost.toFixed(2)}`;
}

/**
 * Format token count with commas
 */
function formatTokens(tokens) {
  if (typeof tokens !== "number") return "0";
  return tokens.toLocaleString();
}

/**
 * Format duration in seconds to human-readable string
 */
function formatDuration(seconds) {
  if (typeof seconds !== "number" || seconds < 0) return "0s";

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  if (hours > 0) {
    return `${hours}h ${minutes}m ${secs}s`;
  } else if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  } else {
    return `${secs}s`;
  }
}

/**
 * Format timestamp to relative time (e.g., "2 minutes ago")
 */
function formatRelativeTime(timestamp) {
  if (!timestamp) return "Never";

  const now = new Date();
  const then = new Date(timestamp);
  const diffMs = now - then;
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 60) {
    return "Just now";
  } else if (diffMins < 60) {
    return `${diffMins} minute${diffMins !== 1 ? "s" : ""} ago`;
  } else if (diffHours < 24) {
    return `${diffHours} hour${diffHours !== 1 ? "s" : ""} ago`;
  } else {
    return `${diffDays} day${diffDays !== 1 ? "s" : ""} ago`;
  }
}

/**
 * Format percentage
 */
function formatPercentage(value, decimals = 1) {
  if (typeof value !== "number") return "0%";
  return `${value.toFixed(decimals)}%`;
}

/**
 * Format file path to show only the filename
 */
function formatFilename(filePath) {
  if (!filePath) return "";
  return filePath.split("/").pop();
}

/**
 * Truncate text to max length with ellipsis
 */
function truncateText(text, maxLength = 50) {
  if (!text || text.length <= maxLength) return text;
  return text.substring(0, maxLength - 3) + "...";
}

/**
 * Format exit code with human-readable label
 * @param {number} code - Process exit code
 * @returns {string} Formatted exit code with label
 */
function formatExitCode(code) {
  if (typeof code !== "number") return "—";
  const labels = {
    0: "Clean exit",
    1: "Error",
    2: "Misuse",
    126: "Not executable",
    127: "Not found",
    130: "SIGINT",
    137: "SIGKILL",
    143: "SIGTERM",
  };
  const label = labels[code];
  return label ? `${code} (${label})` : String(code);
}

// Enable module imports for testing
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    escapeHtml,
    formatCost,
    formatTokens,
    formatDuration,
    formatRelativeTime,
    formatPercentage,
    formatFilename,
    truncateText,
    formatExitCode,
  };
}
