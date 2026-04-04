#!/bin/bash
# PreToolUse Hook: Review before git push
# Matcher: Bash commands containing "git push"

set -euo pipefail

# Read hook input from stdin
INPUT=$(cat)

TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only process Bash tool calls
if [[ "$TOOL_NAME" != "Bash" ]]; then
  exit 0
fi

# Check for git push commands
if echo "$COMMAND" | grep -qE "git\s+push"; then
  # Get current branch
  BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")

  # Get remote info
  REMOTE=$(echo "$COMMAND" | grep -oE "git\s+push\s+\S+" | awk '{print $3}' || echo "origin")
  REMOTE=${REMOTE:-origin}

  # Show what will be pushed
  echo "=== Git Push Review ===" >&2
  echo "Branch: $BRANCH" >&2
  echo "Remote: $REMOTE" >&2
  echo "" >&2

  # Show commits to be pushed
  echo "Commits to push:" >&2
  git log --oneline "$REMOTE/$BRANCH..HEAD" 2>/dev/null | head -10 >&2 || echo "  (unable to determine)" >&2
  echo "" >&2

  # Show changed files summary
  echo "Files changed:" >&2
  git diff --stat "$REMOTE/$BRANCH..HEAD" 2>/dev/null | tail -5 >&2 || echo "  (unable to determine)" >&2
  echo "========================" >&2

  # Check for protected branches
  if [[ "$BRANCH" == "main" || "$BRANCH" == "master" ]]; then
    echo "WARNING: Pushing directly to $BRANCH branch!" >&2
    # Exit with code 1 to prompt user confirmation
    exit 1
  fi
fi

exit 0
