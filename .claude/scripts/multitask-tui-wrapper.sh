#!/usr/bin/env bash
# Multitask TUI wrapper - launches Ink-based dashboard for monitoring parallel instances
# Usage: ./scripts/multitask-tui-wrapper.sh

set -euo pipefail

# Save original working directory (project root)
PROJECT_ROOT="$(pwd)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Session file path
STATE_DIR=".claude/state"
SESSION_FILE="$STATE_DIR/multitask-session.json"

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Check if Node.js is available
if ! command -v node &> /dev/null; then
  echo -e "${RED}Error: Node.js is not installed${NC}"
  echo "Please install Node.js to use the TUI"
  exit 1
fi

# Find TUI directory
TUI_DIR=""
if [[ -d "$SCRIPT_DIR/multitask-tui" ]]; then
  TUI_DIR="$SCRIPT_DIR/multitask-tui"
elif [[ -d "$SCRIPT_DIR/../multitask-tui" ]]; then
  TUI_DIR="$SCRIPT_DIR/../multitask-tui"
fi

if [[ -z "$TUI_DIR" || ! -d "$TUI_DIR" ]]; then
  echo -e "${RED}Error: Multitask TUI directory not found${NC}"
  echo "Searched: $SCRIPT_DIR/multitask-tui and $SCRIPT_DIR/../multitask-tui"
  echo ""
  echo "The TUI component is optional. You can still use multitask with --no-tui flag:"
  echo "  /multitask --no-tui --plans ..."
  exit 1
fi

# Check if TUI dependencies are installed
if [[ ! -d "$TUI_DIR/node_modules" ]]; then
  echo -e "${YELLOW}Installing TUI dependencies...${NC}"
  cd "$TUI_DIR"
  npm install
  if [[ $? -ne 0 ]]; then
    echo -e "${RED}Error: Failed to install TUI dependencies${NC}"
    exit 1
  fi
fi

# Build TUI if dist doesn't exist
if [[ ! -d "$TUI_DIR/dist" ]]; then
  echo -e "${YELLOW}Building TUI...${NC}"
  cd "$TUI_DIR"
  npm run build
  if [[ $? -ne 0 ]]; then
    echo -e "${RED}Error: Failed to build TUI${NC}"
    exit 1
  fi
fi

# Check if session file exists
if [[ ! -f "$SESSION_FILE" ]]; then
  echo -e "${YELLOW}Warning: No active multitask session found ($SESSION_FILE)${NC}"
  echo "The TUI will wait for a session to start..."
fi

# Launch TUI from project root (so relative paths work)
cd "$PROJECT_ROOT"
node "$TUI_DIR/dist/index.js"

# Capture exit code
EXIT_CODE=$?

if [[ $EXIT_CODE -ne 0 ]]; then
  echo -e "${RED}TUI exited with error code $EXIT_CODE${NC}"
  exit $EXIT_CODE
fi

exit 0
