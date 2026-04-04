/**
 * Symbol constants for TUI
 *
 * Includes box-drawing characters, progress indicators, and status icons
 * Design aligned with dark theme mockup
 */

export const SYMBOLS = {
  // Progress indicators
  dotFilled: "●",
  dotEmpty: "○",
  dotSmall: "•",

  // Activity icons
  started: "●",
  completed: "✓",
  error: "✗",
  pause: "⏸",
  resume: "▶",
  done: "★",
  bullet: "•",

  // Status indicator
  statusDot: "●",

  // Divider character (box drawing)
  divider: "─",

  // Box drawing characters for cards
  box: {
    topLeft: "╭",
    topRight: "╮",
    bottomLeft: "╰",
    bottomRight: "╯",
    horizontal: "─",
    vertical: "│",
    teeLeft: "├",
    teeRight: "┤",
    teeTop: "┬",
    teeBottom: "┴",
    cross: "┼",
    // Double-line variants for headers
    doubleTopLeft: "╔",
    doubleTopRight: "╗",
    doubleBottomLeft: "╚",
    doubleBottomRight: "╝",
    doubleHorizontal: "═",
    doubleVertical: "║",
  },

  // Progress bar characters
  progressBar: {
    filled: "█",
    empty: "░",
    half: "▓",
    quarter: "▒",
    leftCap: "▐",
    rightCap: "▌",
  },

  // Arrows and indicators
  arrows: {
    right: "→",
    left: "←",
    up: "↑",
    down: "↓",
    upDown: "↕",
    leftRight: "↔",
    prompt: "›",
  },

  // Connection status
  connection: {
    connected: "●",
    disconnected: "○",
    reconnecting: "◐",
    wifi: "≋",
  },

  // Agent status badges
  badges: {
    active: "▶",
    pending: "◯",
    completed: "✓",
    error: "✗",
    idle: "○",
  },

  // Keyboard shortcuts display
  key: {
    leftBracket: "[",
    rightBracket: "]",
  },

  // Robot logo for branding
  robot: {
    // Multi-line ASCII art robot face (3 lines)
    lines: ["╭─┬─╮", "│◉ ◉│", "╰─┴─╯"],
    // Single-line representation for headers
    inline: "[◉─◉]",
  },

  // Orchestrator-specific icons (matching mockup)
  icons: {
    // Header
    app: "[◉─◉]",
    connection: "≋",

    // Metrics
    dollar: "$",
    sessions: "⚡",
    calendar: "▣",

    // Agent card
    agent: "⚙",
    tokens: "✧",
    cost: "$",
    context: "▣",
    tasks: "≡",
    command: "›_",
    cursor: "▌",
    cursorBlink: "█",

    // Status dots
    statusActive: "●",
    statusPending: "●",
    statusCompleted: "●",
    statusError: "●",
  },

  // Section header decorators
  section: {
    left: "─",
    right: "─",
    space: " ",
  },
} as const;

export function getActivityIcon(type: string): string {
  switch (type) {
    case "story_started":
    case "item_started":
    case "batch_started":
      return SYMBOLS.started;
    case "story_completed":
    case "item_completed":
    case "batch_completed":
      return SYMBOLS.completed;
    case "error":
      return SYMBOLS.error;
    case "pause":
      return SYMBOLS.pause;
    case "resume":
      return SYMBOLS.resume;
    case "complete":
      return SYMBOLS.done;
    default:
      return SYMBOLS.bullet;
  }
}

export function getConnectionSymbol(
  status: "connected" | "disconnected" | "reconnecting",
): string {
  return SYMBOLS.connection[status];
}

export function getAgentStatusBadge(
  status: "active" | "pending" | "completed" | "error" | "idle",
): string {
  return SYMBOLS.badges[status];
}
