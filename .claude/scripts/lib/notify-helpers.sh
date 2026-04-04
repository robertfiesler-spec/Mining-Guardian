#!/bin/bash
#
# notify-helpers.sh - Helper functions for notification system
#
# Sources:
# - Config loading from .claude/config.local.json
# - Slack webhook integration
# - macOS system notifications
#

# Find project root (directory containing .claude/)
find_project_root() {
  local dir="$PWD"
  while [[ "$dir" != "/" ]]; do
    if [[ -d "$dir/.claude" ]]; then
      echo "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  echo "$PWD"
}

# Load notification config from .claude/config.local.json
# Returns JSON config or empty string if not found
load_config() {
  local project_root
  project_root=$(find_project_root)
  local config_file="$project_root/.claude/config.local.json"

  if [[ -f "$config_file" ]]; then
    cat "$config_file"
  else
    echo ""
  fi
}

# Check if Slack notifications are enabled
is_slack_enabled() {
  local config="$1"
  if [[ -z "$config" ]]; then
    return 1
  fi

  local enabled
  enabled=$(echo "$config" | jq -r '.notifications.slack.enabled // false')
  [[ "$enabled" == "true" ]]
}

# Check if system notifications are enabled
is_system_enabled() {
  local config="$1"
  if [[ -z "$config" ]]; then
    # Default to true if no config
    return 0
  fi

  local enabled
  enabled=$(echo "$config" | jq -r '.notifications.system.enabled // true')
  [[ "$enabled" == "true" ]]
}

# Get Slack webhook URL from config
get_slack_webhook() {
  local config="$1"
  echo "$config" | jq -r '.notifications.slack.webhookUrl // empty'
}

# Get Slack channel from config
get_slack_channel() {
  local config="$1"
  echo "$config" | jq -r '.notifications.slack.channel // empty'
}

# Get Slack username from config
get_slack_username() {
  local config="$1"
  echo "$config" | jq -r '.notifications.slack.username // "AI Toolkit"'
}

# Get Slack icon emoji from config
get_slack_icon() {
  local config="$1"
  echo "$config" | jq -r '.notifications.slack.icon_emoji // ":robot_face:"'
}

# Get system notification sound from config
get_system_sound() {
  local config="$1"
  echo "$config" | jq -r '.notifications.system.sound // "Glass"'
}

# Map event type to Slack color
get_slack_color() {
  local event_type="$1"
  case "$event_type" in
    loop_complete)
      echo "good"  # Green
      ;;
    iterate_batch_complete)
      echo "#36a64f"  # Green
      ;;
    loop_max_iterations)
      echo "warning"  # Yellow
      ;;
    iterate_error|loop_error)
      echo "danger"  # Red
      ;;
    *)
      echo "#439FE0"  # Blue (info)
      ;;
  esac
}

# Map event type to emoji for Slack
get_slack_emoji() {
  local event_type="$1"
  case "$event_type" in
    loop_complete)
      echo ":white_check_mark:"
      ;;
    iterate_batch_complete)
      echo ":ballot_box_with_check:"
      ;;
    loop_max_iterations)
      echo ":warning:"
      ;;
    iterate_error|loop_error)
      echo ":x:"
      ;;
    *)
      echo ":information_source:"
      ;;
  esac
}

# Send Slack notification via webhook
# Args: webhook_url title message [options...]
send_slack_notification() {
  local webhook_url="$1"
  local title="$2"
  local message="$3"
  local event_type="${4:-info}"
  local progress="${5:-}"
  local plan="${6:-}"
  local channel="${7:-}"
  local username="${8:-AI Toolkit}"
  local icon_emoji="${9:-:robot_face:}"

  local color
  color=$(get_slack_color "$event_type")

  local emoji
  emoji=$(get_slack_emoji "$event_type")

  # Build fields array
  local fields="[]"
  if [[ -n "$progress" ]]; then
    fields=$(echo "$fields" | jq --arg p "$progress" '. + [{"title": "Progress", "value": $p, "short": true}]')
  fi
  if [[ -n "$plan" ]]; then
    fields=$(echo "$fields" | jq --arg p "$plan" '. + [{"title": "Plan", "value": $p, "short": true}]')
  fi

  # Build payload
  local payload
  payload=$(jq -n \
    --arg channel "$channel" \
    --arg username "$username" \
    --arg icon "$icon_emoji" \
    --arg fallback "$title: $message" \
    --arg color "$color" \
    --arg title "$emoji $title" \
    --arg text "$message" \
    --argjson fields "$fields" \
    '{
      username: $username,
      icon_emoji: $icon,
      attachments: [{
        fallback: $fallback,
        color: $color,
        title: $title,
        text: $text,
        fields: $fields,
        footer: "AI Toolkit",
        ts: (now | floor)
      }]
    } | if $channel != "" then .channel = $channel else . end'
  )

  # Send to Slack
  local response
  local http_code
  response=$(curl -s -w "\n%{http_code}" -X POST \
    -H "Content-Type: application/json" \
    -d "$payload" \
    "$webhook_url" 2>/dev/null)

  http_code=$(echo "$response" | tail -n1)

  if [[ "$http_code" == "200" ]]; then
    return 0
  else
    return 1
  fi
}

# Send macOS system notification
# Args: title message [sound]
send_system_notification() {
  local title="$1"
  local message="$2"
  local sound="${3:-Glass}"

  if command -v osascript &> /dev/null; then
    osascript -e "display notification \"$message\" with title \"$title\" sound name \"$sound\"" 2>/dev/null
    return $?
  else
    return 1
  fi
}

# Parse optional arguments in key=value or --key value format
# Sets global variables: NOTIFY_PROGRESS, NOTIFY_PLAN, NOTIFY_EVENT_TYPE
parse_notify_args() {
  NOTIFY_PROGRESS=""
  NOTIFY_PLAN=""
  NOTIFY_EVENT_TYPE="info"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --progress)
        NOTIFY_PROGRESS="$2"
        shift 2
        ;;
      --plan)
        NOTIFY_PLAN="$2"
        shift 2
        ;;
      --event)
        NOTIFY_EVENT_TYPE="$2"
        shift 2
        ;;
      *)
        shift
        ;;
    esac
  done
}
