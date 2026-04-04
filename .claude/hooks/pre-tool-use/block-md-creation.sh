#!/bin/bash
# PreToolUse Hook: Block unnecessary markdown file creation
# Matcher: Write tool creating .md files (except README.md, CLAUDE.md)

set -euo pipefail

# Read hook input from stdin
INPUT=$(cat)

TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only process Write tool calls
if [[ "$TOOL_NAME" != "Write" ]]; then
  exit 0
fi

# Check if it's a markdown file
if [[ "$FILE_PATH" == *.md ]]; then
  FILENAME=$(basename "$FILE_PATH")

  # Allow README.md and CLAUDE.md variants
  if [[ "$FILENAME" =~ ^(README|CLAUDE)\.md$ ]] || \
     [[ "$FILENAME" =~ ^(README|CLAUDE)\..+\.md$ ]]; then
    exit 0
  fi

  # Allow checkpoints (workflow requirement)
  if [[ "$FILE_PATH" == */.claude/checkpoints/*.md ]] || \
     [[ "$FILE_PATH" == *.claude/checkpoints/*.md ]]; then
    exit 0
  fi

  # Allow plan files (workflow requirement)
  if [[ "$FILE_PATH" == */docs/plans/*.md ]] || \
     [[ "$FILE_PATH" == *docs/plans/*.md ]]; then
    exit 0
  fi

  # Allow WORKFLOW.md
  if [[ "$FILENAME" == "WORKFLOW.md" ]]; then
    exit 0
  fi

  # Allow agent files (agents/ directory)
  if [[ "$FILE_PATH" == */agents/*.md ]] || \
     [[ "$FILE_PATH" == *agents/*.md ]]; then
    exit 0
  fi

  # Allow command files (commands/ directory)
  if [[ "$FILE_PATH" == */commands/*.md ]] || \
     [[ "$FILE_PATH" == *commands/*.md ]]; then
    exit 0
  fi

  # Block other .md file creation
  echo "BLOCKED: Creating markdown file '$FILENAME' is not allowed." >&2
  echo "Only README.md and CLAUDE.md files are permitted." >&2
  echo "If this documentation is necessary, add it to an existing file or request approval." >&2
  exit 2
fi

exit 0
