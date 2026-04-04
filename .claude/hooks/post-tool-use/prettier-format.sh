#!/bin/bash
# PostToolUse Hook: Auto-format JS/TS files with Prettier
# Matcher: Edit tool on .ts, .tsx, .js, .jsx files

set -euo pipefail

# Read hook input from stdin
INPUT=$(cat)

TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only process Edit tool calls
if [[ "$TOOL_NAME" != "Edit" ]]; then
  exit 0
fi

# Check if it's a JS/TS file
if [[ "$FILE_PATH" =~ \.(ts|tsx|js|jsx)$ ]]; then
  # Check if file exists
  if [[ ! -f "$FILE_PATH" ]]; then
    exit 0
  fi

  # Check if prettier is available
  if command -v prettier &>/dev/null; then
    prettier --write "$FILE_PATH" 2>/dev/null || true
  elif command -v npx &>/dev/null; then
    npx prettier --write "$FILE_PATH" 2>/dev/null || true
  else
    echo "Warning: Prettier not found. Skipping auto-format." >&2
  fi
fi

exit 0
