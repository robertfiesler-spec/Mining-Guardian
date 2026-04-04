#!/bin/bash
# PreToolUse Hook: Design system lint guard
# Matcher: Bash (git commit commands)
#
# Runs design-lint.sh --staged --strict before git commit.
# Blocks commit if design system violations are found.
# Uses exit code 2 to block the operation.

set -euo pipefail

INPUT=$(cat)

TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only intercept Bash tool running git commit
if [[ "$TOOL_NAME" != "Bash" ]]; then
  exit 0
fi

if ! echo "$COMMAND" | grep -qE 'git[[:space:]]+commit([[:space:]]|$)'; then
  exit 0
fi

# Check if there are staged UI files
STAGED_UI=$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null \
  | grep -E '\.(tsx|jsx|css|html)$' || true)

if [[ -z "$STAGED_UI" ]]; then
  exit 0
fi

# Find the lint script (check local install, then global, then source)
LINT_SCRIPT=""
for candidate in \
  ".claude/scripts/design-lint.sh" \
  "$HOME/.claude/scripts/design-lint.sh" \
  "$(dirname "$(dirname "$(dirname "${BASH_SOURCE[0]}")")")/scripts/design-lint.sh"; do
  if [[ -f "$candidate" ]]; then
    LINT_SCRIPT="$candidate"
    break
  fi
done

if [[ -z "$LINT_SCRIPT" ]]; then
  # Script not found — warn but don't block
  echo "⚠ design-lint.sh not found, skipping design system check" >&2
  exit 0
fi

# Run the lint on staged files in strict mode
OUTPUT=$(bash "$LINT_SCRIPT" --staged --strict --quiet 2>&1) || {
  echo "" >&2
  echo "Design System Lint Failed:" >&2
  echo "$OUTPUT" >&2
  echo "" >&2
  echo "Fix violations or add ds-exception markers with reasons." >&2
  echo "Run: .claude/scripts/design-lint.sh --staged for details." >&2
  exit 2
}

exit 0
