#!/bin/bash
# Universal hook runner - checks local .claude/ first, then global ~/.claude/
# Usage: run-hook.sh <hook-type> <hook-name>
# Example: run-hook.sh pre-tool-use agent-register.sh

set -euo pipefail

HOOK_TYPE="${1:-}"
HOOK_NAME="${2:-}"

if [[ -z "$HOOK_TYPE" || -z "$HOOK_NAME" ]]; then
  echo "Usage: run-hook.sh <hook-type> <hook-name>" >&2
  exit 0
fi

# Read stdin once and pass to the actual hook
INPUT=$(cat)

# Try local installation first (.claude/)
LOCAL_HOOK=".claude/hooks/$HOOK_TYPE/$HOOK_NAME"
if [[ -f "$LOCAL_HOOK" ]]; then
  echo "$INPUT" | exec bash "$LOCAL_HOOK"
fi

# Fall back to global installation (~/.claude/)
GLOBAL_HOOK="$HOME/.claude/hooks/$HOOK_TYPE/$HOOK_NAME"
if [[ -f "$GLOBAL_HOOK" ]]; then
  echo "$INPUT" | exec bash "$GLOBAL_HOOK"
fi

# Hook not found in either location - exit silently
exit 0
