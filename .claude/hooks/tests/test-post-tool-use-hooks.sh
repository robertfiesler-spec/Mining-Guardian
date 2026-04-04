#!/usr/bin/env bash
#
# Test Suite: Post-Tool-Use Hooks
#
# Tests for hooks that run after tool execution.
# - console-log-guard.sh --check: Warns about debug statements in edits
# - prettier-format.sh: Auto-formats JS/TS files (output only, no file changes)
#
# Usage:
#   ./hooks/tests/test-post-tool-use-hooks.sh
#

set -euo pipefail

# Get the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOKS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FIXTURES_DIR="$SCRIPT_DIR/fixtures/inputs"

# Source test helpers
source "$SCRIPT_DIR/lib/test-helpers.sh"

# ============================================================================
# Test console-log-guard.sh --check
# ============================================================================

test_start "console-log-guard.sh --check Tests"

CONSOLE_LOG_HOOK="$HOOKS_DIR/scripts/console-log-guard.sh"

# Helper: run console-log-guard.sh with --check flag
run_guard_check() {
  local json_input="$1"
  set +e
  HOOK_OUTPUT=$(echo "$json_input" | bash "$CONSOLE_LOG_HOOK" --check 2>&1)
  HOOK_EXIT_CODE=$?
  set -e
}

# Test: Non-Edit tool should pass through (exit 0)
test_case "non-Edit tools pass through"
run_guard_check "$(cat "$FIXTURES_DIR/bash-npm-install.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Non-Edit tools should pass"
assert_not_contains "$HOOK_OUTPUT" "Warning" "No warning for non-Edit tools"

# Test: Edit without console.log should pass quietly
test_case "edit without console.log passes quietly"
run_guard_check "$(cat "$FIXTURES_DIR/edit-typescript.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Edit without console.log should pass"
assert_not_contains "$HOOK_OUTPUT" "console.log" "No warning without console.log"

# Test: Edit with console.log shows warning
test_case "edit with console.log shows warning"
run_guard_check "$(cat "$FIXTURES_DIR/edit-with-console-log.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Edit with console.log should pass (warning only)"
assert_contains "$HOOK_OUTPUT" "Warning" "Should show warning"
assert_contains "$HOOK_OUTPUT" "console.log" "Warning should mention console.log"

# Test: Edit with debugger shows note
test_case "edit with debugger shows note"
run_guard_check "$(cat "$FIXTURES_DIR/edit-with-debugger.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Edit with debugger should pass"
assert_contains "$HOOK_OUTPUT" "Debug statement" "Should note debug statement"

# Test: Edit with console.warn shows note
test_case "edit with console.warn shows note"
run_guard_check "$(cat "$FIXTURES_DIR/edit-with-console-warn.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Edit with console.warn should pass"
assert_contains "$HOOK_OUTPUT" "Debug statement" "Should note debug statement"

# Test: Clean edit without debug statements
test_case "clean edit passes without any output"
run_guard_check "$(cat "$FIXTURES_DIR/edit-without-debug.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Clean edit should pass"
assert_not_contains "$HOOK_OUTPUT" "Warning" "No warning for clean edit"
assert_not_contains "$HOOK_OUTPUT" "Debug" "No debug note for clean edit"

# ============================================================================
# Test prettier-format.sh
# ============================================================================

test_start "prettier-format.sh Tests"

PRETTIER_HOOK="$HOOKS_DIR/post-tool-use/prettier-format.sh"

# Test: Non-Edit tool should pass through (exit 0)
test_case "non-Edit tools pass through"
run_hook "$PRETTIER_HOOK" "$(cat "$FIXTURES_DIR/bash-npm-install.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Non-Edit tools should pass"

# Test: Non-JS/TS file should pass through without formatting
test_case "non-JS/TS files pass through"
run_hook "$PRETTIER_HOOK" "$(cat "$FIXTURES_DIR/edit-config.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Non-JS/TS files should pass"

# Test: JSON file should pass through without formatting
test_case "JSON files pass through"
run_hook "$PRETTIER_HOOK" "$(cat "$FIXTURES_DIR/edit-json-file.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "JSON files should pass"

# Test: TypeScript file edit (file doesn't exist, should pass)
test_case "TS file edit passes (file not found is ok)"
run_hook "$PRETTIER_HOOK" "$(cat "$FIXTURES_DIR/edit-typescript.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "TS file edit should pass"

# Test: TSX file edit (file doesn't exist, should pass)
test_case "TSX file edit passes (file not found is ok)"
run_hook "$PRETTIER_HOOK" "$(cat "$FIXTURES_DIR/edit-tsx-file.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "TSX file edit should pass"

# Test: JS file edit (file doesn't exist, should pass)
test_case "JS file edit passes (file not found is ok)"
run_hook "$PRETTIER_HOOK" "$(cat "$FIXTURES_DIR/edit-js-file.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "JS file edit should pass"

# Print test summary and exit with appropriate code
test_summary
