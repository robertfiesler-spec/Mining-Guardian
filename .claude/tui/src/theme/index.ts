/**
 * Theme index - re-exports for backward compatibility
 *
 * Import from here to get all theme utilities:
 * import { COLORS, SYMBOLS, getStatusColor } from './theme/index.js'
 */

export {
  COLORS,
  getModeColor,
  getStatusColor,
  getActivityColor,
  getContextBarColor,
  getCostDeltaColor,
} from "./colors.js";
export type { StatusType, ExecutionMode, ActivityType } from "./colors.js";

export {
  SYMBOLS,
  getActivityIcon,
  getConnectionSymbol,
  getAgentStatusBadge,
} from "./symbols.js";
