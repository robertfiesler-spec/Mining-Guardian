#!/usr/bin/env bash
# Shared utilities for orchestrator agent tracking
# Used by agent registration/deregistration hooks

set -euo pipefail

# Find the real jq binary (not the npm package)
JQ_BIN=""
for jq_path in /opt/homebrew/bin/jq /usr/local/bin/jq /usr/bin/jq; do
  if [[ -x "$jq_path" ]]; then
    JQ_BIN="$jq_path"
    break
  fi
done

if [[ -z "$JQ_BIN" ]]; then
  echo "Error: jq not found. Please install jq." >&2
  exit 1
fi

# Use jq via the found path
jq() {
  "$JQ_BIN" "$@"
}

# File paths
STATE_DIR=".claude/state"
ORCHESTRATOR_FILE="$STATE_DIR/orchestrator.json"
# Session marker file - created on first tool use, contains agent ID
# Uses terminal TTY as unique identifier for the session
SESSION_MARKER_DIR="$STATE_DIR/sessions"

# Ensure state directory exists
ensure_state_dir() {
  mkdir -p "$STATE_DIR"
  mkdir -p "$SESSION_MARKER_DIR"
}

# Get a session identifier based on TTY or fallback to PPID
get_session_key() {
  # Try to get TTY name (unique per terminal session)
  local tty_name
  tty_name=$(tty 2>/dev/null | tr '/' '_' || echo "")

  if [[ -n "$tty_name" && "$tty_name" != "not_a_tty" && "$tty_name" != "_dev_tty" ]]; then
    echo "tty${tty_name}"
  else
    # Fallback: use PPID (parent process - the Claude process)
    echo "ppid${PPID:-$$}"
  fi
}

# Get session marker file path
get_session_marker_file() {
  local session_key
  session_key=$(get_session_key)
  echo "$SESSION_MARKER_DIR/${session_key}.agent"
}

# Generate a unique agent ID
generate_agent_id() {
  if [[ -n "${CLAUDE_SESSION_ID:-}" ]]; then
    echo "$CLAUDE_SESSION_ID"
  else
    local timestamp
    timestamp=$(date +%s)
    local random_suffix
    random_suffix=$(head -c 4 /dev/urandom | od -An -tx1 | tr -d ' \n' || echo "$$")
    echo "agent-${timestamp}-${random_suffix}"
  fi
}

# Get agent ID from session marker file (if already registered this session)
get_registered_agent_id() {
  local marker_file
  marker_file=$(get_session_marker_file)

  if [[ -f "$marker_file" ]]; then
    cat "$marker_file"
  else
    echo ""
  fi
}

# Register this session's agent ID
register_session_agent_id() {
  local agent_id="$1"

  ensure_state_dir

  local marker_file
  marker_file=$(get_session_marker_file)
  echo "$agent_id" > "$marker_file"
}

# Clean up session marker file
cleanup_session_marker() {
  local marker_file
  marker_file=$(get_session_marker_file)
  rm -f "$marker_file" 2>/dev/null || true
}

# Get current orchestrator state or create empty one
get_orchestrator_state() {
  if [[ -f "$ORCHESTRATOR_FILE" ]]; then
    cat "$ORCHESTRATOR_FILE"
  else
    cat <<'EOF'
{
  "version": "1.1.0",
  "updated_at": "",
  "agents": {
    "agents": [],
    "activeCount": 0,
    "pendingCount": 0,
    "completedCount": 0,
    "errorCount": 0
  },
  "costs": {
    "today": 0,
    "sessions": 0,
    "sevenDay": 0,
    "thirtyDay": 0
  }
}
EOF
  fi
}

# Update agent counts based on current agents
update_agent_counts() {
  local state="$1"

  echo "$state" | jq '
    .agents.activeCount = ([.agents.agents[] | select(.status == "active")] | length) |
    .agents.pendingCount = ([.agents.agents[] | select(.status == "pending")] | length) |
    .agents.completedCount = ([.agents.agents[] | select(.status == "completed")] | length) |
    .agents.errorCount = ([.agents.agents[] | select(.status == "error")] | length)
  '
}

# Save orchestrator state with atomic write and validation
save_orchestrator_state() {
  local state="$1"
  ensure_state_dir

  # Update timestamp and counts
  local updated_state
  updated_state=$(echo "$state" | jq --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '.updated_at = $ts')
  updated_state=$(update_agent_counts "$updated_state")

  # Validate JSON before writing
  if ! echo "$updated_state" | jq empty 2>/dev/null; then
    echo "Error: Invalid JSON state, not saving" >&2
    return 1
  fi

  # Atomic write: write to temp file then rename
  local temp_file="${ORCHESTRATOR_FILE}.tmp.$$"
  echo "$updated_state" > "$temp_file"
  mv "$temp_file" "$ORCHESTRATOR_FILE"
}

# Check if agent exists in orchestrator
agent_exists() {
  local agent_id="$1"
  local state
  state=$(get_orchestrator_state)

  local exists
  exists=$(echo "$state" | jq --arg id "$agent_id" '[.agents.agents[] | select(.id == $id)] | length')

  [[ "$exists" -gt 0 ]]
}

# Add or update agent in orchestrator
upsert_agent() {
  local agent_json="$1"
  local agent_id
  agent_id=$(echo "$agent_json" | jq -r '.id')

  local state
  state=$(get_orchestrator_state)

  local updated_state
  if agent_exists "$agent_id"; then
    # Update existing agent
    updated_state=$(echo "$state" | jq --argjson agent "$agent_json" '
      .agents.agents = [.agents.agents[] | if .id == $agent.id then $agent else . end]
    ')
  else
    # Add new agent
    updated_state=$(echo "$state" | jq --argjson agent "$agent_json" '
      .agents.agents += [$agent]
    ')
  fi

  save_orchestrator_state "$updated_state"
}

# Update agent status
update_agent_status() {
  local agent_id="$1"
  local new_status="$2"
  local end_time="${3:-}"

  local state
  state=$(get_orchestrator_state)

  local updated_state
  if [[ -n "$end_time" ]]; then
    updated_state=$(echo "$state" | jq --arg id "$agent_id" --arg status "$new_status" --arg end "$end_time" '
      .agents.agents = [.agents.agents[] |
        if .id == $id then
          .status = $status |
          .metrics.endTime = $end |
          .metrics.duration = (now - (.metrics.startTime | fromdateiso8601) | floor)
        else .
        end
      ]
    ')
  else
    updated_state=$(echo "$state" | jq --arg id "$agent_id" --arg status "$new_status" '
      .agents.agents = [.agents.agents[] | if .id == $id then .status = $status else . end]
    ')
  fi

  save_orchestrator_state "$updated_state"
}

# Update agent's current command
update_agent_command() {
  local agent_id="$1"
  local command="$2"

  local state
  state=$(get_orchestrator_state)

  local updated_state
  updated_state=$(echo "$state" | jq --arg id "$agent_id" --arg cmd "$command" '
    .agents.agents = [.agents.agents[] | if .id == $id then .currentCommand = $cmd else . end]
  ')

  save_orchestrator_state "$updated_state"
}

# Increment session count in costs
increment_session_count() {
  local state
  state=$(get_orchestrator_state)

  local updated_state
  updated_state=$(echo "$state" | jq '.costs.sessions += 1')

  save_orchestrator_state "$updated_state"
}

# Update agent's cost metrics
update_agent_costs() {
  local agent_id="$1"
  local tokens_in="$2"
  local tokens_out="$3"
  local cost="$4"

  local state
  state=$(get_orchestrator_state)

  local total_tokens=$((tokens_in + tokens_out))

  local updated_state
  updated_state=$(echo "$state" | jq --arg id "$agent_id" \
    --argjson tokensIn "$tokens_in" \
    --argjson tokensOut "$tokens_out" \
    --argjson totalTokens "$total_tokens" \
    --argjson cost "$cost" '
    .agents.agents = [.agents.agents[] |
      if .id == $id then
        .metrics.tokensIn = $tokensIn |
        .metrics.tokensOut = $tokensOut |
        .metrics.totalTokens = $totalTokens |
        .metrics.cost = $cost
      else .
      end
    ]
  ')

  save_orchestrator_state "$updated_state"
}

# Update cost aggregates (today, 7-day, 30-day)
update_cost_aggregates() {
  local session_cost="$1"

  local state
  state=$(get_orchestrator_state)

  # Add session cost to all time periods
  # Note: For proper time-based aggregation, we'd need to track
  # individual session costs with timestamps. For now, we accumulate.
  local updated_state
  updated_state=$(echo "$state" | jq --argjson cost "$session_cost" '
    .costs.today = ((.costs.today // 0) + $cost) |
    .costs.sevenDay = ((.costs.sevenDay // 0) + $cost) |
    .costs.thirtyDay = ((.costs.thirtyDay // 0) + $cost)
  ')

  save_orchestrator_state "$updated_state"
}

# Clean up stale agents (completed agents older than 1 hour)
cleanup_stale_agents() {
  local state
  state=$(get_orchestrator_state)

  # Get cutoff time (1 hour ago) - works on both macOS and Linux
  local cutoff_epoch
  cutoff_epoch=$(($(date +%s) - 3600))

  local updated_state
  updated_state=$(echo "$state" | jq --arg cutoff "$cutoff_epoch" '
    .agents.agents = [.agents.agents[] |
      select(
        (.status == "active") or
        (.status == "pending") or
        ((.status == "completed" or .status == "error") and
         ((.metrics.endTime // .metrics.startTime) |
          if . then (. | fromdateiso8601) > ($cutoff | tonumber) else true end))
      )
    ]
  ')

  save_orchestrator_state "$updated_state"
}

# Clean up old session markers (older than 24 hours)
cleanup_session_markers() {
  find "$SESSION_MARKER_DIR" -name "*.agent" -mtime +1 -delete 2>/dev/null || true
}
