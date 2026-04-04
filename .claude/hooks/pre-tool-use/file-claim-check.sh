#!/usr/bin/env bash
#
# file-claim-check.sh - PreToolUse Hook for file claims checking
#
# Checks file claims before Write/Edit operations to prevent conflicts
# when multiple agents work on different plans simultaneously.
#
# Behavior:
#   - If file is unclaimed: Claims it for current plan, allows operation
#   - If file is claimed by same plan: Allows operation
#   - If file is claimed by different plan: Blocks with conflict message
#
# Override:
#   Set CLAUDE_ALLOW_CONFLICT=1 to proceed despite conflicts (use with caution)
#
# Exit codes:
#   0 - Allow operation
#   2 - Block operation (conflict detected)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$SCRIPT_DIR/../lib"

# Source libraries
if [[ -f "$LIB_DIR/file-claims.sh" ]]; then
  source "$LIB_DIR/file-claims.sh"
else
  # Library not found - allow operation (graceful degradation)
  exit 0
fi
source "$LIB_DIR/git-utils.sh"

if [[ -f "$LIB_DIR/git-utils.sh" ]]; then
  source "$LIB_DIR/git-utils.sh"
else
  # Library not found - allow operation (graceful degradation)
  exit 0
fi

# Read hook input from stdin
INPUT=$(cat)

# Parse tool name and file path from JSON input
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only check Write and Edit tools
if [[ "$TOOL_NAME" != "Write" && "$TOOL_NAME" != "Edit" ]]; then
  exit 0
fi

# Skip if no file path provided
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

# Get current plan context
CURRENT_PLAN=$(get_plan_from_branch)

# If still no plan context, allow operation (single-plan mode / no multi-agent)
if [[ -z "$CURRENT_PLAN" ]]; then
  exit 0
fi

# Check for existing claim by another plan
if ! check_claim "$FILE_PATH" "$CURRENT_PLAN"; then
  # Conflict detected - get details
  CLAIM_INFO=$(get_claim "$FILE_PATH")
  OWNING_PLAN=$(echo "$CLAIM_INFO" | jq -r '.plan')
  CLAIMED_AT=$(echo "$CLAIM_INFO" | jq -r '.claimed_at')
  CLAIMING_AGENT=$(echo "$CLAIM_INFO" | jq -r '.agent_id // "unknown"')

  # Record the conflict for tracking
  record_conflict "$FILE_PATH" "$CURRENT_PLAN" "$OWNING_PLAN"

  # Check for override flag
  if [[ "${CLAUDE_ALLOW_CONFLICT:-}" == "1" ]]; then
    echo "WARNING: Proceeding despite file conflict (CLAUDE_ALLOW_CONFLICT=1)" >&2
    echo "  File: $FILE_PATH" >&2
    echo "  Claimed by: $OWNING_PLAN" >&2
    exit 0
  fi

  # Report the conflict
  echo "" >&2
  echo "╔══════════════════════════════════════════════════════════════╗" >&2
  echo "║  FILE CONFLICT DETECTED                                      ║" >&2
  echo "╚══════════════════════════════════════════════════════════════╝" >&2
  echo "" >&2
  echo "  File:        $FILE_PATH" >&2
  echo "  Claimed by:  $OWNING_PLAN (since $CLAIMED_AT)" >&2
  echo "  Your plan:   $CURRENT_PLAN" >&2
  echo "" >&2
  echo "  This file is being edited by another plan/agent." >&2
  echo "" >&2
  echo "  Options:" >&2
  echo "    1. Work on a different file" >&2
  echo "    2. Switch to plan '$OWNING_PLAN' to continue that work" >&2
  echo "    3. Wait for '$OWNING_PLAN' to complete and release the file" >&2
  echo "    4. Force override: export CLAUDE_ALLOW_CONFLICT=1" >&2
  echo "" >&2
  echo "  To release the claim manually:" >&2
  echo "    source .claude/hooks/lib/file-claims.sh && release_claim '$FILE_PATH'" >&2
  echo "" >&2

  # Block the operation
  exit 2
fi

# No conflict - claim the file for this plan
# Get agent ID from environment or generate one
AGENT_ID="${CLAUDE_AGENT_ID:-}"
if [[ -z "$AGENT_ID" ]]; then
  # Try to get from session marker
  SESSION_KEY=$(tty 2>/dev/null | sed 's/\//_/g' || echo "$$")
  MARKER_FILE=".claude/state/sessions/${SESSION_KEY}.agent"
  if [[ -f "$MARKER_FILE" ]]; then
    AGENT_ID=$(cat "$MARKER_FILE")
  else
    AGENT_ID="agent-$(date +%s)-$$"
  fi
fi

# Claim the file
claim_file "$FILE_PATH" "$CURRENT_PLAN" "$AGENT_ID" "write"

# Allow the operation
exit 0
