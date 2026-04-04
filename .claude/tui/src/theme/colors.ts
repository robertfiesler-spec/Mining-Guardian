/**
 * Extended color palette for TUI
 *
 * Design system based on dark charcoal theme:
 * - Yellow/amber: Primary accent, progress bars, highlights
 * - Green: Success, active states, cost values
 * - Orange: Warning, pending input states
 * - Gray: Borders, secondary text, dimmed elements
 * - White: Primary text, values
 * - Red: Error states
 */

export const COLORS = {
  // Primary accent (yellow/amber)
  primary: "yellow",
  accent: "yellow",

  // Execution modes
  autonomous: "yellow",
  attended: "cyan",

  // Status colors
  running: "yellow",
  paused: "yellow",
  complete: "green",
  crashed: "red",
  pending: "gray",

  // UI elements
  current: "yellow",
  success: "green",
  error: "red",
  warning: "yellow",
  dimmed: "gray",
  header: "white",
  divider: "gray",

  // Text hierarchy
  textPrimary: "white",
  textSecondary: "gray",
  textMuted: "gray",

  // Activity log
  started: "yellow",
  completed: "green",

  // Orchestrator-specific colors
  orchestrator: {
    // Agent status
    active: "green",
    pending: "yellow",
    pendingInput: "yellow",
    completed: "gray",
    idle: "gray",
    error: "red",

    // Cost display
    costValue: "green",
    costPositive: "green",
    costNegative: "red",
    costNeutral: "gray",
    deltaPositive: "green",
    deltaNegative: "red",

    // Context bar (yellow/amber theme)
    contextFilled: "yellow",
    contextEmpty: "gray",
    contextLow: "yellow",
    contextMedium: "yellow",
    contextHigh: "red",

    // Card styling
    cardBorder: "gray",
    cardBorderActive: "green",
    cardBorderPending: "yellow",
    cardBorderError: "red",
    cardBorderSelected: "cyan",

    // Section headers
    sectionBorder: "gray",
    sectionTitle: "gray",

    // Metrics cards
    metricIcon: "gray",
    metricLabel: "gray",
    metricValue: "white",
    metricDelta: "green",

    // Agent card elements
    agentIcon: "gray",
    agentName: "white",
    tokenLabel: "gray",
    tokenValue: "white",
    costLabel: "gray",

    // Tasks
    taskBorder: "gray",
    taskText: "gray",

    // Active command
    cmdPrompt: "yellow",
    cmdText: "gray",
    cmdCursor: "white",

    // System stats
    sysOk: "green",
    sysLabel: "gray",
    memLabel: "cyan",
    cpuLabel: "yellow",

    // Header
    headerTitle: "yellow",
    headerVersion: "gray",
    connectionOk: "green",
    connectionError: "red",
    timestamp: "gray",
  },
} as const;

export type StatusType = "running" | "paused" | "complete" | "crashed";
export type ExecutionMode = "autonomous" | "attended";
export type ActivityType =
  | "story_started"
  | "story_completed"
  | "item_started"
  | "item_completed"
  | "batch_started"
  | "batch_completed"
  | "error"
  | "pause"
  | "resume"
  | "complete";

export function getModeColor(mode: ExecutionMode): string {
  return mode === "autonomous" ? COLORS.autonomous : COLORS.attended;
}

export function getStatusColor(status: StatusType): string {
  switch (status) {
    case "running":
      return COLORS.running;
    case "paused":
      return COLORS.paused;
    case "complete":
      return COLORS.complete;
    case "crashed":
      return COLORS.crashed;
    default:
      return COLORS.dimmed;
  }
}

export function getActivityColor(type: string): string {
  switch (type) {
    case "story_started":
    case "item_started":
    case "batch_started":
      return COLORS.started;
    case "story_completed":
    case "item_completed":
    case "batch_completed":
      return COLORS.completed;
    case "error":
      return COLORS.error;
    case "pause":
      return COLORS.paused;
    case "resume":
      return COLORS.success;
    case "complete":
      return COLORS.success;
    default:
      return COLORS.dimmed;
  }
}

export function getContextBarColor(percentage: number): string {
  // Use yellow/amber for most cases, red only when very high
  if (percentage >= 90) return COLORS.orchestrator.contextHigh;
  return COLORS.orchestrator.contextFilled;
}

export function getCostDeltaColor(delta: number): string {
  if (delta > 0) return COLORS.orchestrator.deltaPositive;
  if (delta < 0) return COLORS.orchestrator.deltaNegative;
  return COLORS.orchestrator.costNeutral;
}

export function getAgentStatusColor(
  status: "active" | "pending" | "completed" | "error" | "idle",
): string {
  switch (status) {
    case "active":
      return COLORS.orchestrator.active;
    case "pending":
      return COLORS.orchestrator.pending;
    case "completed":
      return COLORS.orchestrator.completed;
    case "error":
      return COLORS.orchestrator.error;
    case "idle":
    default:
      return COLORS.orchestrator.idle;
  }
}

export function getCardBorderColor(
  status: "active" | "pending" | "completed" | "error" | "idle",
  selected: boolean = false,
): string {
  if (selected) return COLORS.orchestrator.cardBorderSelected;
  switch (status) {
    case "active":
      return COLORS.orchestrator.cardBorderActive;
    case "pending":
      return COLORS.orchestrator.cardBorderPending;
    case "error":
      return COLORS.orchestrator.cardBorderError;
    default:
      return COLORS.orchestrator.cardBorder;
  }
}
