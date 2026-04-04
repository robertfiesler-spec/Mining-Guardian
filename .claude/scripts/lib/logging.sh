#!/usr/bin/env bash
# Shared logging utilities for AI Dev Toolkit scripts.
#
# Usage:
#   source "$(dirname "${BASH_SOURCE[0]}")/lib/logging.sh"
#
# Environment variables (all optional):
#   LOG_PREFIX  - Custom prefix (e.g. "[pipeline]"). Default: standard tags like [INFO].
#   LOG_FILE    - Append all output to this file via tee.
#   QUIET       - "true" to suppress log_info/log_success.
#   VERBOSE     - "true" to enable log_verbose.
#
# Core functions: log_info, log_success, log_warn, log_error, log_verbose, log_section
# Test functions: log_test, log_pass, log_fail

# ── Colors ────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
GRAY='\033[0;90m'
NC='\033[0m'

# ── Internal helper ───────────────────────────────────────────
_log_emit() {
  local msg="$1"
  local fd="${2:-1}"  # 1=stdout, 2=stderr
  if [[ -n "${LOG_FILE:-}" ]]; then
    echo -e "$msg" | tee -a "$LOG_FILE" >&"$fd"
  else
    echo -e "$msg" >&"$fd"
  fi
}

_log_tag() {
  local color="$1" default_tag="$2"
  shift 2
  if [[ -n "${LOG_PREFIX:-}" ]]; then
    echo "${color}${LOG_PREFIX}${NC} $*"
  else
    echo "${color}${default_tag}${NC} $*"
  fi
}

# ── Core functions ────────────────────────────────────────────
log_info() {
  [[ "${QUIET:-false}" == "true" ]] && return 0
  _log_emit "$(_log_tag "$BLUE" "[INFO]" "$@")"
}

log_success() {
  [[ "${QUIET:-false}" == "true" ]] && return 0
  _log_emit "$(_log_tag "$GREEN" "[SUCCESS]" "$@")"
}

log_warn() {
  _log_emit "$(_log_tag "$YELLOW" "[WARN]" "$@")" 2
}

log_error() {
  _log_emit "$(_log_tag "$RED" "[ERROR]" "$@")" 2
}

log_verbose() {
  [[ "${VERBOSE:-false}" != "true" ]] && return 0
  _log_emit "${GRAY}$*${NC}"
}

log_section() {
  _log_emit "\n${CYAN}=== $* ===${NC}\n"
}

# ── Test helpers ──────────────────────────────────────────────
log_test() { _log_emit "${BLUE}[TEST]${NC} $*"; }
log_pass() { _log_emit "${GREEN}[PASS]${NC} $*"; }
log_fail() { _log_emit "${RED}[FAIL]${NC} $*" 2; }
