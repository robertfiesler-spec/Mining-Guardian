/**
 * Centralized path constants for TUI
 *
 * All runtime state is stored in .claude/state/ for consolidation.
 * These paths must match the bash variables in scripts/lib/session-manager.sh
 */

export const STATE_DIR = ".claude/state";

export const SESSION_FILE = `${STATE_DIR}/session.json`;
export const SESSION_ARCHIVE_DIR = `${STATE_DIR}/sessions`;
export const PROGRESS_FILE = `${STATE_DIR}/progress.txt`;
export const PAUSE_FILE = `${STATE_DIR}/.pause`;
export const QUIT_FILE = `${STATE_DIR}/.quit`;
export const STOP_FILE = `${STATE_DIR}/.stop-loop`;
