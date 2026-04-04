#!/bin/bash
# PreToolUse Hook: Remind user about tmux for long-running commands
# Matcher: Bash commands containing npm, pnpm, yarn, cargo, pytest

set -euo pipefail

# Read hook input from stdin
INPUT=$(cat)

TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only process Bash tool calls
if [[ "$TOOL_NAME" != "Bash" ]]; then
  exit 0
fi

# Check for long-running command patterns
LONG_RUNNING_PATTERNS="npm install|npm run build|npm run dev|npm test|pnpm install|pnpm build|pnpm dev|yarn install|yarn build|yarn dev|cargo build|cargo test|pytest"

if echo "$COMMAND" | grep -qE "$LONG_RUNNING_PATTERNS"; then
  # Check if already in tmux
  if [[ -z "${TMUX:-}" ]]; then
    echo "Consider running in tmux for long-running commands: $COMMAND" >&2
    echo "Tip: Use 'tmux new -s claude' to create a session" >&2
  fi
fi

exit 0
