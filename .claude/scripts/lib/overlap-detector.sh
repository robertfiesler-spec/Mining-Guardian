#!/usr/bin/env bash
#
# overlap-detector.sh - Detect file overlaps between active plans
#
# Identifies when multiple plans modify the same files, helping
# prevent merge conflicts and coordination issues in multi-agent workflows.
#
# Usage:
#   source overlap-detector.sh
#   detect_overlaps           # Find all overlapping files between active plans
#   report_overlaps           # Generate formatted overlap report
#   check_plan_start "plan"   # Check if starting a plan would cause conflicts

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR=".claude/state"
PLANS_DIR="docs/plans"

# Source dependencies
if [[ -f "$SCRIPT_DIR/session-manager.sh" ]]; then
  source "$SCRIPT_DIR/session-manager.sh"
fi

# Find jq binary
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

jq() { "$JQ_BIN" "$@"; }

# =============================================================================
# Core Functions
# =============================================================================

# Get all files associated with a plan (from plan file and session)
# Usage: get_plan_files <plan_name>
get_plan_files() {
  local plan_name=$1
  local files=()

  # Get files from plan file (stories.files arrays)
  local plan_file="$PLANS_DIR/${plan_name}.json"
  if [[ -f "$plan_file" ]]; then
    while IFS= read -r file; do
      [[ -n "$file" ]] && files+=("$file")
    done < <(jq -r '.stories[].files[]? // empty' "$plan_file" 2>/dev/null | sort -u)
  fi

  # Get files from session state (modified files, claims)
  local session_file="$STATE_DIR/plans/$plan_name/session.json"
  if [[ -f "$session_file" ]]; then
    while IFS= read -r file; do
      [[ -n "$file" ]] && files+=("$file")
    done < <(jq -r '.git.modified_files[]? // empty' "$session_file" 2>/dev/null)

    while IFS= read -r file; do
      [[ -n "$file" ]] && files+=("$file")
    done < <(jq -r '.file_claims[]? // empty' "$session_file" 2>/dev/null)
  fi

  # Get files from global claims registry
  local claims_file="$STATE_DIR/file-claims.json"
  if [[ -f "$claims_file" ]]; then
    while IFS= read -r file; do
      [[ -n "$file" ]] && files+=("$file")
    done < <(jq -r --arg p "$plan_name" \
      '.claims | to_entries[] | select(.value.plan == $p) | .key' \
      "$claims_file" 2>/dev/null)
  fi

  # Output unique files
  printf '%s\n' "${files[@]}" | sort -u
}

# Get list of active plans (running or paused status)
# Usage: get_active_plans
get_active_plans() {
  local plans=()

  # Check plan-scoped sessions
  if [[ -d "$STATE_DIR/plans" ]]; then
    for session in "$STATE_DIR/plans"/*/session.json; do
      if [[ -f "$session" ]]; then
        local status=$(jq -r '.status // "unknown"' "$session" 2>/dev/null)
        if [[ "$status" == "running" || "$status" == "paused" ]]; then
          local plan_name=$(jq -r '.plan.name // empty' "$session" 2>/dev/null)
          [[ -n "$plan_name" ]] && plans+=("$plan_name")
        fi
      fi
    done
  fi

  # Check legacy global session
  if [[ -f "$STATE_DIR/session.json" ]]; then
    local status=$(jq -r '.status // "unknown"' "$STATE_DIR/session.json" 2>/dev/null)
    if [[ "$status" == "running" || "$status" == "paused" ]]; then
      local plan_name=$(jq -r '.plan.name // empty' "$STATE_DIR/session.json" 2>/dev/null)
      if [[ -n "$plan_name" ]]; then
        # Check if not already in list
        local found=0
        for p in "${plans[@]:-}"; do
          [[ "$p" == "$plan_name" ]] && found=1 && break
        done
        [[ $found -eq 0 ]] && plans+=("$plan_name")
      fi
    fi
  fi

  printf '%s\n' "${plans[@]:-}"
}

# Detect overlapping files between active plans
# Output format: file|plan1|plan2
# Usage: detect_overlaps
detect_overlaps() {
  local -A file_plans

  # Build map of files to plans
  while IFS= read -r plan; do
    [[ -z "$plan" ]] && continue

    while IFS= read -r file; do
      [[ -z "$file" ]] && continue

      if [[ -n "${file_plans[$file]:-}" ]]; then
        # File already seen - this is an overlap
        echo "$file|${file_plans[$file]}|$plan"
      else
        file_plans[$file]="$plan"
      fi
    done < <(get_plan_files "$plan")
  done < <(get_active_plans)
}

# Generate formatted overlap report
# Usage: report_overlaps
report_overlaps() {
  local overlaps=$(detect_overlaps)

  echo "=== File Overlap Report ==="
  echo ""

  if [[ -z "$overlaps" ]]; then
    echo "No file overlaps detected between active plans."
    return 0
  fi

  echo "WARNING: The following files are claimed by multiple plans:"
  echo ""

  local prev_file=""
  while IFS='|' read -r file plan1 plan2; do
    if [[ "$file" != "$prev_file" ]]; then
      echo "  $file"
      prev_file="$file"
    fi
    echo "    - $plan1"
    echo "    - $plan2"
  done <<< "$overlaps"

  echo ""
  echo "Recommendation: Coordinate with the other plan or use"
  echo "CLAUDE_ALLOW_CONFLICT=1 to proceed with caution."

  return 1
}

# Check if starting a new plan would cause conflicts with active plans
# Usage: check_plan_start <plan_name>
check_plan_start() {
  local new_plan=$1
  local plan_file=""

  # Find plan file
  if [[ -f "$PLANS_DIR/${new_plan}.json" ]]; then
    plan_file="$PLANS_DIR/${new_plan}.json"
  elif [[ -f "$PLANS_DIR/${new_plan}.md" ]]; then
    plan_file="$PLANS_DIR/${new_plan}.md"
  else
    echo "Error: Plan file not found: $new_plan" >&2
    return 1
  fi

  # Get files this plan will modify
  local planned_files=()
  if [[ "$plan_file" == *.json ]]; then
    while IFS= read -r file; do
      [[ -n "$file" ]] && planned_files+=("$file")
    done < <(jq -r '.stories[].files[]? // empty' "$plan_file" 2>/dev/null | sort -u)
  else
    # For markdown, try to extract file paths
    while IFS= read -r file; do
      [[ -n "$file" ]] && planned_files+=("$file")
    done < <(grep -oE '\`[^`]+\.(ts|tsx|js|jsx|sh|md|json)\`' "$plan_file" 2>/dev/null | tr -d '`' | sort -u)
  fi

  if [[ ${#planned_files[@]} -eq 0 ]]; then
    echo "No files identified in plan: $new_plan"
    echo "Cannot check for conflicts without file information."
    return 0
  fi

  # Check against active plan claims
  local conflicts=()
  local claims_file="$STATE_DIR/file-claims.json"

  if [[ -f "$claims_file" ]]; then
    for file in "${planned_files[@]}"; do
      local claim=$(jq -r --arg f "$file" '.claims[$f].plan // empty' "$claims_file" 2>/dev/null)
      if [[ -n "$claim" && "$claim" != "$new_plan" ]]; then
        conflicts+=("$file (claimed by $claim)")
      fi
    done
  fi

  if [[ ${#conflicts[@]} -gt 0 ]]; then
    echo "=== Potential Conflicts ==="
    echo ""
    echo "Starting plan '$new_plan' may conflict with active plans:"
    echo ""
    for conflict in "${conflicts[@]}"; do
      echo "  - $conflict"
    done
    echo ""
    echo "Options:"
    echo "  1. Complete or pause the conflicting plan first"
    echo "  2. Use a different branch/worktree for isolation"
    echo "  3. Proceed with CLAUDE_ALLOW_CONFLICT=1 (may cause merge conflicts)"
    return 1
  fi

  echo "No conflicts detected for plan: $new_plan"
  return 0
}

# =============================================================================
# Summary Functions
# =============================================================================

# Get summary of all active plans and their file claims
# Usage: get_plans_summary
get_plans_summary() {
  echo "=== Active Plans Summary ==="
  echo ""

  local plan_count=0
  while IFS= read -r plan; do
    [[ -z "$plan" ]] && continue
    ((plan_count++))

    local session_file="$STATE_DIR/plans/$plan/session.json"
    local status="unknown"
    local progress="?"
    local total="?"

    if [[ -f "$session_file" ]]; then
      status=$(jq -r '.status // "unknown"' "$session_file")
      progress=$(jq -r '.progress.completed // 0' "$session_file")
      total=$(jq -r '.progress.total_stories // 0' "$session_file")
    fi

    local file_count=$(get_plan_files "$plan" | wc -l | tr -d ' ')

    echo "$plan_count. $plan ($status)"
    echo "   Progress: $progress/$total stories"
    echo "   Files: $file_count claimed/modified"
    echo ""
  done < <(get_active_plans)

  if [[ $plan_count -eq 0 ]]; then
    echo "No active plans found."
  fi
}

# Show claimed files grouped by plan
# Usage: show_file_claims
show_file_claims() {
  local claims_file="$STATE_DIR/file-claims.json"

  echo "=== File Claims ==="
  echo ""

  if [[ ! -f "$claims_file" ]]; then
    echo "No file claims registry found."
    return 0
  fi

  local claim_count=$(jq '.claims | length' "$claims_file")
  if [[ "$claim_count" -eq 0 ]]; then
    echo "No files currently claimed."
    return 0
  fi

  echo "Total claims: $claim_count"
  echo ""

  # Group by plan
  jq -r '.claims | to_entries | group_by(.value.plan) | .[] |
    "Plan: \(.[0].value.plan)\n" +
    ([.[] | "  - \(.key)"] | join("\n"))' "$claims_file"
}
