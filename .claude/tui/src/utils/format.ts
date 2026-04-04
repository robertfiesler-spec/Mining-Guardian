/**
 * Formatting utilities for the TUI
 */

/**
 * Format token counts for display
 * @example formatTokens(1500) => "1.5K"
 * @example formatTokens(245700) => "245.7K"
 * @example formatTokens(1234567) => "1.2M"
 */
export function formatTokens(tokens: number): string {
  if (tokens < 1000) {
    return tokens.toString();
  }

  if (tokens < 1000000) {
    const k = tokens / 1000;
    return `${k.toFixed(1)}K`;
  }

  const m = tokens / 1000000;
  return `${m.toFixed(1)}M`;
}

/**
 * Format currency values for display (rounded to whole dollars)
 * @example formatCurrency(0.4913) => "$0"
 * @example formatCurrency(1.50) => "$2"
 * @example formatCurrency(123.45) => "$123"
 */
export function formatCurrency(amount: number): string {
  return `$${Math.round(amount)}`;
}

/**
 * Format currency with delta indicator
 * @example formatCurrencyWithDelta(5.23, 0.50) => "$5.23 (+$0.50)"
 */
export function formatCurrencyWithDelta(
  amount: number,
  delta?: number,
): string {
  const base = formatCurrency(amount);

  if (delta === undefined || delta === 0) {
    return base;
  }

  const sign = delta > 0 ? "+" : "";
  return `${base} (${sign}${formatCurrency(delta)})`;
}

/**
 * Format percentage for display
 * @example formatPercent(0.75) => "75%"
 * @example formatPercent(75) => "75%" (assumes already percentage)
 */
export function formatPercent(value: number): string {
  // If value is less than 1, assume it's a decimal
  const percent = value <= 1 ? value * 100 : value;
  return `${Math.round(percent)}%`;
}

/**
 * Format memory in GB
 * @example formatMemory(8.5) => "8.5GB"
 */
export function formatMemory(gb: number): string {
  return `${gb.toFixed(1)}GB`;
}

/**
 * Format CPU percentage
 * @example formatCPU(45.2) => "45%"
 */
export function formatCPU(percent: number): string {
  return `${Math.round(percent)}%`;
}

/**
 * Format time as HH:MM:SS
 * @example formatTime(new Date()) => "14:32:05"
 */
export function formatTime(date: Date): string {
  return date.toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/**
 * Format duration in seconds to human readable
 * @example formatDuration(125) => "2m 5s"
 * @example formatDuration(3700) => "1h 1m"
 */
export function formatDuration(seconds: number): string {
  if (seconds < 60) {
    return `${seconds}s`;
  }

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;

  if (minutes < 60) {
    return remainingSeconds > 0
      ? `${minutes}m ${remainingSeconds}s`
      : `${minutes}m`;
  }

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;

  return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
}

/**
 * Format context size for display (similar to tokens but for context window)
 * @example formatContextSize(95000) => "95.0K"
 * @example formatContextSize(128000) => "128.0K"
 */
export function formatContextSize(size: number): string {
  if (size < 1000) {
    return size.toString();
  }

  const k = size / 1000;
  return `${k.toFixed(1)}K`;
}

/**
 * Truncate string with ellipsis
 * @example truncate("Hello World", 8) => "Hello..."
 */
export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) {
    return str;
  }
  return `${str.slice(0, maxLength - 3)}...`;
}

/**
 * Pad string to fixed width
 * @example padRight("Hello", 10) => "Hello     "
 */
export function padRight(str: string, width: number): string {
  return str.padEnd(width);
}

/**
 * Pad string to fixed width (left)
 * @example padLeft("42", 5) => "   42"
 */
export function padLeft(str: string, width: number): string {
  return str.padStart(width);
}
