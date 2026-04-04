#!/usr/bin/env bash
#
# Test Suite: Pre-Tool-Use Hooks
#
# Tests for hooks that run before tool execution.
# - tmux-reminder.sh: Reminds about tmux for long-running commands
#
# Usage:
#   ./hooks/tests/test-pre-tool-use-hooks.sh
#

set -euo pipefail

# Get the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOKS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FIXTURES_DIR="$SCRIPT_DIR/fixtures/inputs"

# Source test helpers
source "$SCRIPT_DIR/lib/test-helpers.sh"

# ============================================================================
# Test tmux-reminder.sh
# ============================================================================

test_start "tmux-reminder.sh Tests"

TMUX_HOOK="$HOOKS_DIR/pre-tool-use/tmux-reminder.sh"

# Save and unset TMUX to simulate not being in tmux
SAVED_TMUX="${TMUX:-}"
unset TMUX 2>/dev/null || true

# Test: Non-Bash tool should pass through (exit 0)
test_case "non-Bash tools pass through"
run_hook "$TMUX_HOOK" "$(cat "$FIXTURES_DIR/write-readme.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Non-Bash tools should pass"

# Test: Simple bash command should pass (no warning)
test_case "simple bash commands pass without warning"
run_hook "$TMUX_HOOK" "$(cat "$FIXTURES_DIR/bash-ls.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Simple bash should pass"
assert_not_contains "$HOOK_OUTPUT" "tmux" "No tmux reminder for simple commands"

# Test: npm install triggers tmux reminder (outside tmux)
test_case "npm install triggers tmux reminder"
run_hook "$TMUX_HOOK" "$(cat "$FIXTURES_DIR/bash-npm-install.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "npm install should pass (warning only)"
assert_contains "$HOOK_OUTPUT" "tmux" "Should mention tmux"

# Test: npm run build triggers tmux reminder
test_case "npm run build triggers tmux reminder"
run_hook "$TMUX_HOOK" "$(cat "$FIXTURES_DIR/bash-npm-run-build.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "npm run build should pass"
assert_contains "$HOOK_OUTPUT" "tmux" "Should mention tmux"

# Test: npm run dev triggers tmux reminder
test_case "npm run dev triggers tmux reminder"
run_hook "$TMUX_HOOK" "$(cat "$FIXTURES_DIR/bash-npm-run-dev.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "npm run dev should pass"
assert_contains "$HOOK_OUTPUT" "tmux" "Should mention tmux"

# Test: npm test triggers tmux reminder
test_case "npm test triggers tmux reminder"
run_hook "$TMUX_HOOK" "$(cat "$FIXTURES_DIR/bash-npm-test.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "npm test should pass"
assert_contains "$HOOK_OUTPUT" "tmux" "Should mention tmux"

# Test: yarn install triggers tmux reminder
test_case "yarn install triggers tmux reminder"
run_hook "$TMUX_HOOK" "$(cat "$FIXTURES_DIR/bash-yarn-install.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "yarn install should pass"
assert_contains "$HOOK_OUTPUT" "tmux" "Should mention tmux"

# Test: pnpm build triggers tmux reminder
test_case "pnpm build triggers tmux reminder"
run_hook "$TMUX_HOOK" "$(cat "$FIXTURES_DIR/bash-pnpm-build.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "pnpm build should pass"
assert_contains "$HOOK_OUTPUT" "tmux" "Should mention tmux"

# Test: cargo build triggers tmux reminder
test_case "cargo build triggers tmux reminder"
run_hook "$TMUX_HOOK" "$(cat "$FIXTURES_DIR/bash-cargo-build.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "cargo build should pass"
assert_contains "$HOOK_OUTPUT" "tmux" "Should mention tmux"

# Test: pytest triggers tmux reminder
test_case "pytest triggers tmux reminder"
run_hook "$TMUX_HOOK" "$(cat "$FIXTURES_DIR/bash-pytest.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "pytest should pass"
assert_contains "$HOOK_OUTPUT" "tmux" "Should mention tmux"

# Test: Inside tmux, no reminder shown
test_case "inside tmux, no reminder shown"
export TMUX="/tmp/tmux-test/default,12345,0"
run_hook "$TMUX_HOOK" "$(cat "$FIXTURES_DIR/bash-npm-install.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Should pass inside tmux"
assert_not_contains "$HOOK_OUTPUT" "tmux" "No reminder inside tmux"
unset TMUX

# Test: git push does not trigger tmux reminder
test_case "git push does not trigger tmux reminder"
run_hook "$TMUX_HOOK" "$(cat "$FIXTURES_DIR/bash-git-push-feature.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "git push should pass"
assert_not_contains "$HOOK_OUTPUT" "Consider running in tmux" "No tmux reminder for git push"

# Restore TMUX if it was set
if [[ -n "$SAVED_TMUX" ]]; then
  export TMUX="$SAVED_TMUX"
fi

# Print test summary and exit with appropriate code
test_summary
