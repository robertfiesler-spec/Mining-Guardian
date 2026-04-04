#!/usr/bin/env bash
# Shared git utilities for hooks.
#
# Usage:
#   source "$SCRIPT_DIR/../lib/git-utils.sh"
#   plan=$(get_plan_from_branch)

# Resolve the current plan context.
# Checks CLAUDE_PLAN env var first, then falls back to the git branch name
# with common prefixes stripped, verifying a plan file exists.
# Prints the plan name to stdout (empty string if none detected).
get_plan_from_branch() {
  local plan="${CLAUDE_PLAN:-}"

  if [[ -z "$plan" ]]; then
    local branch
    branch=$(git branch --show-current 2>/dev/null || true)
    if [[ -n "$branch" ]]; then
      plan="${branch#feature/}"
      plan="${plan#fix/}"
      plan="${plan#refactor/}"

      # Verify plan file exists
      if [[ ! -f "docs/plans/${plan}.json" && ! -f "docs/plans/${plan}.md" ]]; then
        plan=""
      fi
    fi
  fi

  echo "$plan"
}
