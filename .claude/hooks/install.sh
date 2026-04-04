#!/bin/bash
# Install hooks to a target project directory
# Usage: ./install.sh [target_directory]

set -euo pipefail

TARGET_DIR="${1:-.}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing Claude Code hooks to: $TARGET_DIR"

# Create hooks directory in target
mkdir -p "$TARGET_DIR/hooks/pre-tool-use"
mkdir -p "$TARGET_DIR/hooks/post-tool-use"
mkdir -p "$TARGET_DIR/hooks/stop"
mkdir -p "$TARGET_DIR/hooks/lib"

# Copy hook scripts
cp "$SCRIPT_DIR/pre-tool-use/"*.sh "$TARGET_DIR/hooks/pre-tool-use/"
cp "$SCRIPT_DIR/post-tool-use/"*.sh "$TARGET_DIR/hooks/post-tool-use/"
cp "$SCRIPT_DIR/stop/"*.sh "$TARGET_DIR/hooks/stop/"
cp "$SCRIPT_DIR/lib/"*.sh "$TARGET_DIR/hooks/lib/"

# Make executable
chmod +x "$TARGET_DIR/hooks/pre-tool-use/"*.sh
chmod +x "$TARGET_DIR/hooks/post-tool-use/"*.sh
chmod +x "$TARGET_DIR/hooks/stop/"*.sh
chmod +x "$TARGET_DIR/hooks/lib/"*.sh

# Copy configuration
cp "$SCRIPT_DIR/hooks.json" "$TARGET_DIR/hooks/"

echo ""
echo "Hooks installed successfully!"
echo ""
echo "To activate, merge hooks/hooks.json into your .claude/settings.json"
echo "or add the hooks configuration to your project's Claude settings."
echo ""
echo "Installed hooks:"
echo "  PreToolUse:"
echo "    - agent-register.sh (registers agent for TUI tracking)"
echo "    - tmux-reminder.sh (warns about tmux for long-running commands)"
echo "    - block-md-creation.sh (blocks .md files except README/CLAUDE)"
echo "    - git-push-review.sh (review before git push)"
echo "  PostToolUse:"
echo "    - prettier-format.sh (auto-format JS/TS with Prettier)"
echo "    - console-log-guard.sh --check (warns about console.log)"
echo "  Stop:"
echo "    - agent-deregister.sh (deregisters agent with cost tracking)"
echo "    - console-log-guard.sh --audit (audits for console.log on session end)"
echo "  Lib:"
echo "    - orchestrator-utils.sh (shared utilities for agent tracking)"
