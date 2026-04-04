#!/usr/bin/env bash
# Agent Deregistration Hook
# 1. Calculates session costs from transcript
# 2. Marks the Claude agent as completed in orchestrator.json
# This ensures the TUI shows accurate agent status and cost metrics

set -euo pipefail

# Get script directory and source utilities
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/orchestrator-utils.sh"

# Model pricing (per million tokens) - Updated Jan 2025
# Source: https://www.anthropic.com/pricing
# Using functions to avoid unbound variable errors with associative arrays under set -u
get_input_price() {
  local model="${1:-default}"
  case "$model" in
    claude-opus-4-5-20251101) echo "15.00" ;;
    claude-sonnet-4-20250514) echo "3.00" ;;
    claude-haiku-3-5-20241022) echo "0.80" ;;
    *) echo "3.00" ;;
  esac
}

get_output_price() {
  local model="${1:-default}"
  case "$model" in
    claude-opus-4-5-20251101) echo "75.00" ;;
    claude-sonnet-4-20250514) echo "15.00" ;;
    claude-haiku-3-5-20241022) echo "4.00" ;;
    *) echo "15.00" ;;
  esac
}

# Read hook input
INPUT=$(cat)
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // empty')

# Get the agent ID for this session
AGENT_ID=$(get_registered_agent_id)

if [[ -n "$AGENT_ID" ]]; then
  # Calculate costs from transcript if available
  if [[ -n "$TRANSCRIPT_PATH" && -f "$TRANSCRIPT_PATH" ]]; then
    total_input=0
    total_output=0
    model="default"

    # Track different token types separately for accurate pricing
    total_input=0
    total_output=0
    total_cache_write=0
    total_cache_read=0

    # Parse transcript for token usage
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue

      msg_type=$(echo "$line" | jq -r '.type // empty' 2>/dev/null) || continue

      if [[ "$msg_type" == "assistant" ]]; then
        usage=$(echo "$line" | jq -r '.message.usage // empty' 2>/dev/null) || continue

        if [[ -n "$usage" && "$usage" != "null" ]]; then
          input_tokens=$(echo "$line" | jq -r '.message.usage.input_tokens // 0' 2>/dev/null) || input_tokens=0
          output_tokens=$(echo "$line" | jq -r '.message.usage.output_tokens // 0' 2>/dev/null) || output_tokens=0
          cache_creation=$(echo "$line" | jq -r '.message.usage.cache_creation_input_tokens // 0' 2>/dev/null) || cache_creation=0
          cache_read=$(echo "$line" | jq -r '.message.usage.cache_read_input_tokens // 0' 2>/dev/null) || cache_read=0

          # Track each type separately
          total_input=$((total_input + input_tokens))
          total_output=$((total_output + output_tokens))
          total_cache_write=$((total_cache_write + cache_creation))
          total_cache_read=$((total_cache_read + cache_read))

          msg_model=$(echo "$line" | jq -r '.message.model // empty' 2>/dev/null) || msg_model=""
          if [[ -n "$msg_model" ]]; then
            model="$msg_model"
          fi
        fi
      fi
    done < "$TRANSCRIPT_PATH"

    # Calculate cost with proper cache pricing
    # Cache write: 25% MORE than base input price
    # Cache read: 90% LESS than base input price (i.e., 10% of base)
    input_price=$(get_input_price "$model")
    output_price=$(get_output_price "$model")

    if command -v bc &>/dev/null; then
      session_cost=$(echo "scale=6; \
        ($total_input * $input_price / 1000000) + \
        ($total_cache_write * $input_price * 1.25 / 1000000) + \
        ($total_cache_read * $input_price * 0.10 / 1000000) + \
        ($total_output * $output_price / 1000000)" | bc)
    else
      session_cost=0
    fi

    # Total tokens for display (all input types combined)
    total_input=$((total_input + total_cache_write + total_cache_read))

    # Update agent costs
    if [[ "$total_input" -gt 0 || "$total_output" -gt 0 ]]; then
      update_agent_costs "$AGENT_ID" "$total_input" "$total_output" "$session_cost"
      update_cost_aggregates "$session_cost"
      echo "Cost tracked: \$${session_cost} (${total_input} in / ${total_output} out)" >&2
    fi
  fi

  # Mark agent as completed
  END_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  update_agent_status "$AGENT_ID" "completed" "$END_TIME"

  # Update final command status
  update_agent_command "$AGENT_ID" "Session completed"

  # Update plan session with agent departure (multi-agent coordination)
  # Get agent's plan from orchestrator or environment
  AGENT_PLAN="${CLAUDE_PLAN:-}"
  if [[ -z "$AGENT_PLAN" ]]; then
    # Try to get from orchestrator.json
    AGENT_PLAN=$(jq -r --arg id "$AGENT_ID" \
      '.agents.agents[] | select(.id == $id) | .plan // empty' \
      ".claude/state/orchestrator.json" 2>/dev/null || true)
  fi

  if [[ -n "$AGENT_PLAN" ]]; then
    # Source session manager for plan deregistration
    SESSION_MGR="$SCRIPT_DIR/../../scripts/lib/session-manager.sh"
    if [[ -f "$SESSION_MGR" ]]; then
      source "$SESSION_MGR"
      deregister_agent_from_plan "$AGENT_PLAN" "$AGENT_ID" 2>/dev/null || true
      echo "Agent deregistered from plan: $AGENT_PLAN" >&2
    fi
  fi

  # Clean up session marker
  cleanup_session_marker

  echo "Agent deregistered: $AGENT_ID" >&2
fi

# Clean up stale agents and old session markers periodically
cleanup_stale_agents 2>/dev/null || true
cleanup_session_markers 2>/dev/null || true

# Always exit successfully
exit 0
