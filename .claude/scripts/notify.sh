#!/bin/bash
#
# notify.sh - Central notification script for AI Toolkit
#
# Sends notifications to configured channels (Slack, macOS) when
# agent commands need user input or complete their work.
#
# Usage:
#   ./scripts/notify.sh <event_type> <title> <message> [options]
#
# Event Types:
#   iterate_batch_complete  - Batch finished, needs context clear
#   iterate_error           - Hit error/blocker
#   loop_complete           - All stories done
#   loop_max_iterations     - Hit iteration limit
#   loop_error              - Encountered error
#
# Options:
#   --progress "X/Y"        - Progress indicator (e.g., "5/8")
#   --plan "name"           - Plan/feature name
#
# Examples:
#   ./scripts/notify.sh "loop_complete" "Loop Complete" "All 8 stories done!" --progress "8/8" --plan "auth-feature"
#   ./scripts/notify.sh "iterate_error" "Iteration Error" "TypeScript error in auth.ts:45" --plan "auth-feature"
#
# Configuration:
#   Create .claude/config.local.json with Slack webhook URL.
#   See .claude/config.local.example.json for format.
#

set -e

# Get script directory and source helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/notify-helpers.sh"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging functions
log_info() { echo -e "${BLUE}[notify]${NC} $1"; }
log_success() { echo -e "${GREEN}[notify]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[notify]${NC} $1"; }
log_error() { echo -e "${RED}[notify]${NC} $1"; }

# Show usage
usage() {
  cat << 'EOF'
Usage: notify.sh <event_type> <title> <message> [options]

Event Types:
  iterate_batch_complete  - Batch finished, needs context clear
  iterate_error           - Hit error/blocker
  loop_complete           - All stories done
  loop_max_iterations     - Hit iteration limit
  loop_error              - Encountered error

Options:
  --progress "X/Y"  - Progress indicator
  --plan "name"     - Plan/feature name

Examples:
  ./scripts/notify.sh "loop_complete" "Loop Complete" "All stories done!" --progress "8/8"
  ./scripts/notify.sh "iterate_error" "Error" "Build failed" --plan "my-feature"
EOF
}

# Main function
main() {
  # Check required arguments
  if [[ $# -lt 3 ]]; then
    log_error "Missing required arguments"
    usage
    exit 1
  fi

  local event_type="$1"
  local title="$2"
  local message="$3"
  shift 3

  # Parse optional arguments
  parse_notify_args "$@"

  # Load configuration
  local config
  config=$(load_config)

  local slack_sent=false
  local system_sent=false

  # Send Slack notification if enabled
  if is_slack_enabled "$config"; then
    local webhook_url
    webhook_url=$(get_slack_webhook "$config")

    if [[ -n "$webhook_url" ]]; then
      local channel username icon_emoji
      channel=$(get_slack_channel "$config")
      username=$(get_slack_username "$config")
      icon_emoji=$(get_slack_icon "$config")

      if send_slack_notification \
        "$webhook_url" \
        "$title" \
        "$message" \
        "$event_type" \
        "$NOTIFY_PROGRESS" \
        "$NOTIFY_PLAN" \
        "$channel" \
        "$username" \
        "$icon_emoji"; then
        log_success "Slack notification sent"
        slack_sent=true
      else
        log_warn "Slack notification failed (check webhook URL)"
      fi
    else
      log_warn "Slack enabled but no webhook URL configured"
    fi
  fi

  # Send system notification if enabled (macOS)
  if is_system_enabled "$config"; then
    local sound
    sound=$(get_system_sound "$config")

    # Format title with progress if available
    local full_title="$title"
    if [[ -n "$NOTIFY_PROGRESS" ]]; then
      full_title="$title ($NOTIFY_PROGRESS)"
    fi

    if send_system_notification "$full_title" "$message" "$sound"; then
      log_success "System notification sent"
      system_sent=true
    else
      log_warn "System notification not available (macOS only)"
    fi
  fi

  # Report if no notifications were sent
  if [[ "$slack_sent" == "false" && "$system_sent" == "false" ]]; then
    log_info "No notifications sent (none configured or all failed)"
    log_info "Configure notifications in .claude/config.local.json"
  fi
}

# Run main with all arguments
main "$@"
