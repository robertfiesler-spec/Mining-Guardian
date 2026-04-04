#!/usr/bin/env bash
# TUI wrapper script - launches Ink TUI with error handling
# Usage: ./scripts/tui-wrapper.sh

set -euo pipefail

# Save original working directory (project root)
PROJECT_ROOT="$(pwd)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source session manager for path variables
source "$SCRIPT_DIR/lib/session-manager.sh"

# Find TUI directory - check both source and installed locations
if [[ -d "$SCRIPT_DIR/tui" ]]; then
  # Source layout: scripts/tui/
  TUI_DIR="$SCRIPT_DIR/tui"
elif [[ -d "$SCRIPT_DIR/../tui" ]]; then
  # Installed layout: .claude/scripts/../tui = .claude/tui/
  TUI_DIR="$SCRIPT_DIR/../tui"
else
  TUI_DIR=""
fi

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

# Check if TUI directory exists
if [[ -z "$TUI_DIR" || ! -d "$TUI_DIR" ]]; then
  echo -e "${RED}Error: TUI directory not found${NC}"
  echo "Searched: $SCRIPT_DIR/tui and $SCRIPT_DIR/../tui"
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
  echo -e "${YELLOW}Warning: No active session found ($SESSION_FILE)${NC}"
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
