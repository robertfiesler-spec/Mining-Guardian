#!/usr/bin/env bash
#
# file-claims.sh - File claims registry for multi-agent coordination
#
# Tracks which plan/agent owns which files to prevent concurrent edit conflicts.
# When multiple agents work on different plans, this prevents them from
# stepping on each other's files.
#
# Usage:
#   source file-claims.sh
#   check_claim "path/to/file.ts" "my-plan"  # Returns 0 if can claim, 1 if conflict
#   claim_file "path/to/file.ts" "my-plan" "agent-123"
#   release_claim "path/to/file.ts"
#   release_plan_claims "my-plan"

set -euo pipefail

# Find script directory and source dependencies
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# State directory and files
STATE_DIR=".claude/state"
CLAIMS_FILE="$STATE_DIR/file-claims.json"

# Find jq binary (same pattern as orchestrator-utils.sh)
JQ_BIN=""
for jq_path in /opt/homebrew/bin/jq /usr/local/bin/jq /usr/bin/jq; do
  if [[ -x "$jq_path" ]]; then
    JQ_BIN="$jq_path"
    break
  fi
done

if [[ -z "$JQ_BIN" ]]; then
  echo "Error: jq not found. Install with: brew install jq" >&2
  exit 1
fi

# Wrapper for jq
jq() { "$JQ_BIN" "$@"; }

# =============================================================================
# Core Functions
# =============================================================================

# Ensure claims file exists with valid structure
ensure_claims_file() {
  mkdir -p "$STATE_DIR"

  if [[ ! -f "$CLAIMS_FILE" ]]; then
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    cat > "$CLAIMS_FILE" << EOF
{
  "version": "1.0",
  "created_at": "$timestamp",
  "updated_at": "$timestamp",
  "claims": {},
  "conflicts": []
}
EOF
  fi
}

# Normalize file path (remove leading ./ and make relative to repo root)
normalize_path() {
  local path=$1

  # Remove leading ./
  path="${path#./}"

  # If absolute path, make relative to git root
  if [[ "$path" = /* ]]; then
    local git_root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    path="${path#$git_root/}"
  fi

  echo "$path"
}

# Check if file is claimed by another plan
# Returns: 0 if can claim (not claimed or same plan), 1 if conflict
# Usage: check_claim <file_path> <plan_name>
check_claim() {
  local file_path=$1
  local plan_name=$2

  ensure_claims_file
  file_path=$(normalize_path "$file_path")

  local existing=$(jq -r --arg f "$file_path" '.claims[$f].plan // empty' "$CLAIMS_FILE")

  if [[ -z "$existing" ]]; then
    return 0  # No claim, can proceed
  elif [[ "$existing" == "$plan_name" ]]; then
    return 0  # Same plan owns it, can proceed
  else
    return 1  # Different plan, conflict
  fi
}

# Get claim info for a file
# Returns: JSON object with claim details, or "null" if not claimed
# Usage: get_claim <file_path>
get_claim() {
  local file_path=$1

  ensure_claims_file
  file_path=$(normalize_path "$file_path")

  jq --arg f "$file_path" '.claims[$f] // null' "$CLAIMS_FILE"
}

# Claim a file for a plan/agent
# Usage: claim_file <file_path> <plan_name> <agent_id> [claim_type]
claim_file() {
  local file_path=$1
  local plan_name=$2
  local agent_id=$3
  local claim_type=${4:-"write"}

  ensure_claims_file
  file_path=$(normalize_path "$file_path")
  local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  # Atomic update with temp file
  jq --arg f "$file_path" \
     --arg p "$plan_name" \
     --arg a "$agent_id" \
     --arg t "$claim_type" \
     --arg ts "$timestamp" \
    '.claims[$f] = {plan: $p, agent_id: $a, claimed_at: $ts, type: $t} | .updated_at = $ts' \
    "$CLAIMS_FILE" > "$CLAIMS_FILE.tmp" && mv "$CLAIMS_FILE.tmp" "$CLAIMS_FILE"
}

# Release a file claim
# Usage: release_claim <file_path>
release_claim() {
  local file_path=$1

  ensure_claims_file
  file_path=$(normalize_path "$file_path")
  local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  jq --arg f "$file_path" --arg ts "$timestamp" \
    'del(.claims[$f]) | .updated_at = $ts' \
    "$CLAIMS_FILE" > "$CLAIMS_FILE.tmp" && mv "$CLAIMS_FILE.tmp" "$CLAIMS_FILE"
}

# Release all claims for a plan
# Usage: release_plan_claims <plan_name>
release_plan_claims() {
  local plan_name=$1

  ensure_claims_file
  local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  jq --arg p "$plan_name" --arg ts "$timestamp" \
    '.claims = (.claims | with_entries(select(.value.plan != $p))) | .updated_at = $ts' \
    "$CLAIMS_FILE" > "$CLAIMS_FILE.tmp" && mv "$CLAIMS_FILE.tmp" "$CLAIMS_FILE"
}

# Record a conflict for tracking/debugging
# Usage: record_conflict <file_path> <requesting_plan> <owning_plan>
record_conflict() {
  local file_path=$1
  local requesting_plan=$2
  local owning_plan=$3

  ensure_claims_file
  file_path=$(normalize_path "$file_path")
  local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  # Create conflict entry
  local conflict=$(jq -n \
    --arg f "$file_path" \
    --arg r "$requesting_plan" \
    --arg o "$owning_plan" \
    --arg ts "$timestamp" \
    '{file: $f, requesting_plan: $r, owning_plan: $o, detected_at: $ts}')

  # Add to conflicts array (keep last 100)
  jq --argjson c "$conflict" --arg ts "$timestamp" \
    '.conflicts = ([$c] + .conflicts | .[0:100]) | .updated_at = $ts' \
    "$CLAIMS_FILE" > "$CLAIMS_FILE.tmp" && mv "$CLAIMS_FILE.tmp" "$CLAIMS_FILE"
}

# =============================================================================
# Query Functions
# =============================================================================

# List all claims for a plan
# Returns: JSON array of file paths
# Usage: list_plan_claims <plan_name>
list_plan_claims() {
  local plan_name=$1

  ensure_claims_file

  jq --arg p "$plan_name" \
    '[.claims | to_entries[] | select(.value.plan == $p) | .key]' \
    "$CLAIMS_FILE"
}

# List all active claims
# Returns: JSON object of all claims
# Usage: list_all_claims
list_all_claims() {
  ensure_claims_file
  jq '.claims' "$CLAIMS_FILE"
}

# List all conflicts
# Returns: JSON array of conflict records
# Usage: list_conflicts
list_conflicts() {
  ensure_claims_file
  jq '.conflicts' "$CLAIMS_FILE"
}

# Get claim count for a plan
# Returns: Number of files claimed by the plan
# Usage: count_plan_claims <plan_name>
count_plan_claims() {
  local plan_name=$1

  ensure_claims_file

  jq --arg p "$plan_name" \
    '[.claims | to_entries[] | select(.value.plan == $p)] | length' \
    "$CLAIMS_FILE"
}

# Check if any files are claimed
# Returns: 0 if claims exist, 1 if no claims
# Usage: has_claims
has_claims() {
  ensure_claims_file

  local count=$(jq '.claims | length' "$CLAIMS_FILE")
  [[ "$count" -gt 0 ]]
}

# =============================================================================
# Utility Functions
# =============================================================================

# Clean up stale claims (older than specified hours)
# Usage: cleanup_stale_claims [hours]
cleanup_stale_claims() {
  local hours=${1:-24}
  local cutoff_seconds=$((hours * 3600))
  local now=$(date +%s)

  ensure_claims_file
  local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  # Remove claims older than cutoff
  jq --arg ts "$timestamp" --argjson cutoff "$cutoff_seconds" --argjson now "$now" \
    '.claims = (.claims | with_entries(
      select(
        ($now - (.value.claimed_at | fromdateiso8601)) < $cutoff
      )
    )) | .updated_at = $ts' \
    "$CLAIMS_FILE" > "$CLAIMS_FILE.tmp" && mv "$CLAIMS_FILE.tmp" "$CLAIMS_FILE"
}

# Print claim summary (for debugging)
# Usage: print_claims_summary
print_claims_summary() {
  ensure_claims_file

  echo "=== File Claims Summary ==="
  echo ""

  local total=$(jq '.claims | length' "$CLAIMS_FILE")
  echo "Total claims: $total"
  echo ""

  if [[ "$total" -gt 0 ]]; then
    echo "Claims by plan:"
    jq -r '.claims | to_entries | group_by(.value.plan) | .[] | "  \(.[0].value.plan): \(length) files"' "$CLAIMS_FILE"
    echo ""

    echo "Files claimed:"
    jq -r '.claims | to_entries[] | "  \(.key) -> \(.value.plan)"' "$CLAIMS_FILE"
  fi

  local conflicts=$(jq '.conflicts | length' "$CLAIMS_FILE")
  if [[ "$conflicts" -gt 0 ]]; then
    echo ""
    echo "Recent conflicts: $conflicts"
    jq -r '.conflicts[:5][] | "  \(.file): \(.requesting_plan) blocked by \(.owning_plan)"' "$CLAIMS_FILE"
  fi
}
