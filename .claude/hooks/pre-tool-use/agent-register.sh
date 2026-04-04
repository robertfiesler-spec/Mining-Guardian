#!/bin/bash
# Agent Registration Hook
# Registers the Claude agent in orchestrator.json on first tool use
# This enables the TUI to track manual agent sessions in realtime

set -euo pipefail

# Get script directory and source utilities
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/orchestrator-utils.sh"
source "$SCRIPT_DIR/../lib/git-utils.sh"

# Read hook input
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')

# Skip if no tool name (shouldn't happen, but be safe)
if [[ -z "$TOOL_NAME" ]]; then
  exit 0
fi

# Check if we already have an agent ID for this session
AGENT_ID=$(get_registered_agent_id)

if [[ -z "$AGENT_ID" ]]; then
  # First tool use - register new agent
  AGENT_ID=$(generate_agent_id)
  register_session_agent_id "$AGENT_ID"

  # Get agent name from environment or generate one
  AGENT_NAME="${CLAUDE_AGENT_NAME:-Manual Agent}"

  # Detect agent type from tool being used
  AGENT_TYPE="general"
  case "$TOOL_NAME" in
    Bash) AGENT_TYPE="executor" ;;
    Read|Glob|Grep) AGENT_TYPE="explorer" ;;
    Write|Edit) AGENT_TYPE="editor" ;;
    Task) AGENT_TYPE="orchestrator" ;;
  esac

  # Get current working directory name for context
  CWD_NAME=$(basename "$(pwd)")

  # Get current plan context for multi-agent coordination
  CURRENT_PLAN=$(get_plan_from_branch)

  # Create agent entry with plan binding
  START_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  AGENT_JSON=$(cat <<EOF
{
  "id": "$AGENT_ID",
  "name": "$AGENT_NAME",
  "type": "$AGENT_TYPE",
  "status": "active",
  "plan": "$CURRENT_PLAN",
  "metrics": {
    "tokensIn": 0,
    "tokensOut": 0,
    "totalTokens": 0,
    "cost": 0,
    "startTime": "$START_TIME"
  },
  "context": {
    "used": 0,
    "total": 200000,
    "percentage": 0
  },
  "tasks": [],
  "currentCommand": "Starting session in $CWD_NAME..."
}
EOF
)

  # Register agent with plan session if plan is active
  if [[ -n "$CURRENT_PLAN" ]]; then
    # Source session manager for plan registration
    SESSION_MGR="$SCRIPT_DIR/../../scripts/lib/session-manager.sh"
    if [[ -f "$SESSION_MGR" ]]; then
      source "$SESSION_MGR"
      register_agent_with_plan "$CURRENT_PLAN" "$AGENT_ID" "worker" 2>/dev/null || true
    fi
    # Export for child processes
    export CLAUDE_PLAN="$CURRENT_PLAN"
    export CLAUDE_AGENT_ID="$AGENT_ID"
  fi

  # Register agent and increment session count
  upsert_agent "$AGENT_JSON"
  increment_session_count

  # Log registration (to stderr so it doesn't interfere with hook output)
  echo "Agent registered: $AGENT_ID ($AGENT_NAME)" >&2
else
  # Subsequent tool use - update agent activity
  # Extract command info for display
  COMMAND_INFO=""
  case "$TOOL_NAME" in
    Bash)
      COMMAND_INFO=$(echo "$INPUT" | jq -r '.tool_input.command // empty' | head -c 50)
      [[ -n "$COMMAND_INFO" ]] && COMMAND_INFO="Running: $COMMAND_INFO..."
      ;;
    Read)
      FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' | xargs basename 2>/dev/null || echo "")
      [[ -n "$FILE_PATH" ]] && COMMAND_INFO="Reading: $FILE_PATH"
      ;;
    Write)
      FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' | xargs basename 2>/dev/null || echo "")
      [[ -n "$FILE_PATH" ]] && COMMAND_INFO="Writing: $FILE_PATH"
      ;;
    Edit)
      FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' | xargs basename 2>/dev/null || echo "")
      [[ -n "$FILE_PATH" ]] && COMMAND_INFO="Editing: $FILE_PATH"
      ;;
    Glob|Grep)
      PATTERN=$(echo "$INPUT" | jq -r '.tool_input.pattern // empty' | head -c 30)
      [[ -n "$PATTERN" ]] && COMMAND_INFO="Searching: $PATTERN"
      ;;
    Task)
      COMMAND_INFO="Delegating to subagent..."
      ;;
    *)
      COMMAND_INFO="Using: $TOOL_NAME"
      ;;
  esac

  # Update agent's current command if we have info
  if [[ -n "$COMMAND_INFO" ]]; then
    update_agent_command "$AGENT_ID" "$COMMAND_INFO"
  fi
fi

# Always exit successfully - don't block tool execution
exit 0
