/**
 * Theme constants for TUI visual styling
 *
 * This file re-exports from the theme/ directory for backward compatibility.
 * For new code, import directly from './theme/index.js'
 */

// Re-export everything from the theme directory
export {
  COLORS,
  SYMBOLS,
  getModeColor,
  getStatusColor,
  getActivityColor,
  getActivityIcon,
  getContextBarColor,
  getCostDeltaColor,
  getConnectionSymbol,
  getAgentStatusBadge,
} from "./theme/index.js";

export type { StatusType, ExecutionMode, ActivityType } from "./theme/index.js";
