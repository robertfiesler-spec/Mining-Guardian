#!/bin/bash
# Unified console.log guard: --check (PostToolUse) and --audit (Stop)
#
# Usage:
#   console-log-guard.sh --check   # Warn when console.log added via Edit
#   console-log-guard.sh --audit   # Audit modified files at session end

set -euo pipefail

MODE="${1:---check}"
INPUT=$(cat)

# --check mode: PostToolUse hook for Edit tool
check_edit() {
  TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
  FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
  NEW_STRING=$(echo "$INPUT" | jq -r '.tool_input.new_string // empty')

  if [[ "$TOOL_NAME" != "Edit" ]]; then
    exit 0
  fi

  if echo "$NEW_STRING" | grep -q "console\.log"; then
    FILENAME=$(basename "$FILE_PATH")
    echo "Warning: console.log statement added to $FILENAME" >&2
    echo "Remember to remove debug logs before committing." >&2
  fi

  if echo "$NEW_STRING" | grep -qE "console\.(warn|error|debug|info)|debugger"; then
    echo "Note: Debug statement detected in edit." >&2
  fi
}

# --audit mode: Stop hook scanning recently modified files
audit_files() {
  MODIFIED_FILES=$(find . \
    -type f \
    \( -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" \) \
    -not -path "*/node_modules/*" \
    -not -path "*/.git/*" \
    -not -path "*/dist/*" \
    -not -path "*/build/*" \
    -not -path "*/.next/*" \
    -mtime -1 \
    2>/dev/null || true)

  if [[ -z "$MODIFIED_FILES" ]]; then
    exit 0
  fi

  FOUND_LOGS=""

  while IFS= read -r file; do
    if [[ -f "$file" ]]; then
      MATCHES=$(grep -n "console\.log" "$file" 2>/dev/null || true)
      if [[ -n "$MATCHES" ]]; then
        FOUND_LOGS+="$file:\n$MATCHES\n\n"
      fi
    fi
  done <<< "$MODIFIED_FILES"

  if [[ -n "$FOUND_LOGS" ]]; then
    echo "========================================" >&2
    echo "SESSION END AUDIT: console.log detected" >&2
    echo "========================================" >&2
    echo "" >&2
    echo "The following files contain console.log statements:" >&2
    echo "" >&2
    echo -e "$FOUND_LOGS" >&2
    echo "Consider removing debug logs before committing." >&2
    echo "========================================" >&2
  fi
}

case "$MODE" in
  --check) check_edit ;;
  --audit) audit_files ;;
  *)
    echo "Usage: console-log-guard.sh [--check|--audit]" >&2
    exit 1
    ;;
esac

exit 0
