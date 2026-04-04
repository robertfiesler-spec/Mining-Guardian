#!/bin/bash
# PostToolUse Hook: Check for critical accessibility and design issues
# Matcher: Edit tool (*.tsx, *.jsx files)
#
# Warns about critical issues that should never ship:
# - Images without alt text
# - Icon buttons without aria-label
# - outline-none without focus replacement
# - Non-semantic click handlers

set -euo pipefail

# Read hook input from stdin
INPUT=$(cat)

TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
NEW_STRING=$(echo "$INPUT" | jq -r '.tool_input.new_string // empty')

# Only process Edit tool calls on React files
if [[ "$TOOL_NAME" != "Edit" ]]; then
  exit 0
fi

if [[ ! "$FILE_PATH" =~ \.(tsx|jsx)$ ]]; then
  exit 0
fi

WARNINGS=""
FILENAME=$(basename "$FILE_PATH")

# Check for images without alt text
# Pattern: <img with no alt attribute following
if echo "$NEW_STRING" | grep -qE '<img[^>]*src=' && ! echo "$NEW_STRING" | grep -qE '<img[^>]*alt='; then
  WARNINGS="${WARNINGS}\n  - Image may be missing alt text (WCAG 1.1.1)"
fi

# Check for icon-only buttons without aria-label
# Pattern: <button with Icon but no aria-label or text content
if echo "$NEW_STRING" | grep -qE '<button[^>]*>[^<]*<[A-Z][a-zA-Z]*Icon' && ! echo "$NEW_STRING" | grep -qE '<button[^>]*aria-label'; then
  WARNINGS="${WARNINGS}\n  - Icon button may need aria-label (WCAG 4.1.2)"
fi

# Check for outline-none without focus-visible replacement
if echo "$NEW_STRING" | grep -qE 'outline-none|outline:\s*none' && ! echo "$NEW_STRING" | grep -qE 'focus-visible:|focus:ring|:focus-visible'; then
  WARNINGS="${WARNINGS}\n  - outline-none without focus indicator replacement"
fi

# Check for div/span onClick without keyboard handling
if echo "$NEW_STRING" | grep -qE '<(div|span)[^>]*onClick' && ! echo "$NEW_STRING" | grep -qE 'onKeyDown|role=|<button'; then
  WARNINGS="${WARNINGS}\n  - Non-semantic click handler may need keyboard support (WCAG 2.1.1)"
fi

# Check for anchor without href
if echo "$NEW_STRING" | grep -qE '<a[^>]*onClick' && ! echo "$NEW_STRING" | grep -qE '<a[^>]*href='; then
  WARNINGS="${WARNINGS}\n  - Anchor with onClick but no href - consider using button"
fi

# Output warnings if any found
if [[ -n "$WARNINGS" ]]; then
  echo "" >&2
  echo "A11y/Design Check ($FILENAME):" >&2
  echo -e "$WARNINGS" >&2
  echo "" >&2
  echo "Run /rams for full audit." >&2
fi

exit 0
