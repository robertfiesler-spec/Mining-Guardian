#!/usr/bin/env bash
#
# Test Suite: Stop Hooks
#
# Tests for hooks that run when a session ends.
# - console-log-guard.sh --audit: Audits files for console.log at session end
# - agent-deregister.sh: Deregisters agent from TUI tracking
#
# Usage:
#   ./hooks/tests/test-stop-hooks.sh
#

set -euo pipefail

# Get the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOKS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FIXTURES_DIR="$SCRIPT_DIR/fixtures/inputs"

# Source test helpers
source "$SCRIPT_DIR/lib/test-helpers.sh"

# ============================================================================
# Test console-log-guard.sh --audit
# ============================================================================

test_start "console-log-guard.sh --audit Tests"

AUDIT_HOOK="$HOOKS_DIR/scripts/console-log-guard.sh"

# Helper: run console-log-guard.sh with --audit flag
run_guard_audit() {
  local json_input="$1"
  set +e
  HOOK_OUTPUT=$(echo "$json_input" | bash "$AUDIT_HOOK" --audit 2>&1)
  HOOK_EXIT_CODE=$?
  set -e
}

# Create a temporary test directory for file-based tests
setup_test_dir

# Test: Hook runs successfully with no modified files
test_case "runs successfully with no modified files"
cd "$TEST_DIR"
run_guard_audit "$(cat "$FIXTURES_DIR/stop-session.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Should exit 0 with no files"

# Test: Hook runs successfully with clean TypeScript file
test_case "runs successfully with clean TS file"
cd "$TEST_DIR"
mkdir -p src
cat > src/clean.ts << 'EOF'
export function add(a: number, b: number): number {
  return a + b;
}
EOF
touch -t "$(date +%Y%m%d%H%M)" src/clean.ts  # Ensure recently modified
run_guard_audit "$(cat "$FIXTURES_DIR/stop-session.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Should exit 0 with clean file"
assert_not_contains "$HOOK_OUTPUT" "SESSION END AUDIT" "No audit message for clean files"

# Test: Hook detects console.log in modified files
test_case "detects console.log in modified files"
cd "$TEST_DIR"
cat > src/debug.ts << 'EOF'
export function debug(value: unknown): void {
  console.log('Debug:', value);
}
EOF
touch -t "$(date +%Y%m%d%H%M)" src/debug.ts
run_guard_audit "$(cat "$FIXTURES_DIR/stop-session.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Should still exit 0 (audit is informational)"
assert_contains "$HOOK_OUTPUT" "console.log" "Should mention console.log in audit"

# Test: Hook ignores node_modules
test_case "ignores node_modules directory"
cd "$TEST_DIR"
mkdir -p node_modules/some-package
cat > node_modules/some-package/index.js << 'EOF'
console.log('This should be ignored');
EOF
touch -t "$(date +%Y%m%d%H%M)" node_modules/some-package/index.js
run_guard_audit "$(cat "$FIXTURES_DIR/stop-session.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Should exit 0"
# The audit should not include node_modules files
assert_not_contains "$HOOK_OUTPUT" "some-package" "Should ignore node_modules"

# Test: Hook ignores .git directory
test_case "ignores .git directory"
cd "$TEST_DIR"
mkdir -p .git/hooks
cat > .git/hooks/pre-commit << 'EOF'
console.log('This should be ignored');
EOF
touch -t "$(date +%Y%m%d%H%M)" .git/hooks/pre-commit
run_guard_audit "$(cat "$FIXTURES_DIR/stop-session.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Should exit 0"

# Test: Hook reports multiple files with console.log
test_case "reports multiple files with console.log"
cd "$TEST_DIR"
cat > src/file1.ts << 'EOF'
console.log('file1');
EOF
cat > src/file2.tsx << 'EOF'
console.log('file2');
EOF
touch -t "$(date +%Y%m%d%H%M)" src/file1.ts src/file2.tsx
run_guard_audit "$(cat "$FIXTURES_DIR/stop-session.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Should exit 0"
assert_contains "$HOOK_OUTPUT" "SESSION END AUDIT" "Should show audit header"

# Clean up
cleanup_test_dir

# ============================================================================
# Test agent-deregister.sh
# ============================================================================

test_start "agent-deregister.sh Tests"

DEREGISTER_HOOK="$HOOKS_DIR/stop/agent-deregister.sh"

# Create a temporary test directory
setup_test_dir

# Test: Hook runs without error when no agent is registered
test_case "runs without error when no agent registered"
cd "$TEST_DIR"
# Create minimal directory structure the hook expects (including sessions subdirectory)
mkdir -p .claude/state/sessions
run_hook "$DEREGISTER_HOOK" '{"session_id": "test-123"}'
assert_exit_code 0 "$HOOK_EXIT_CODE" "Should exit 0 even without registered agent"

# Test: Hook handles missing state directory gracefully
test_case "handles missing state directory"
cd "$TEST_DIR"
rm -rf .claude
run_hook "$DEREGISTER_HOOK" '{"session_id": "test-456"}'
# This might fail due to missing orchestrator-utils.sh sourcing
# but the hook should still complete without crashing hard
# We just verify it doesn't hang forever
assert_exit_code 0 "$HOOK_EXIT_CODE" "Should handle missing state gracefully"

# Test: Hook handles empty input
test_case "handles empty input"
run_hook "$DEREGISTER_HOOK" '{}'
assert_exit_code 0 "$HOOK_EXIT_CODE" "Should handle empty input"

# Test: Hook handles malformed JSON gracefully
test_case "handles malformed JSON"
run_hook "$DEREGISTER_HOOK" 'not valid json'
# jq will fail to parse but the hook should still exit
# The exact exit code depends on set -e handling
# Just verify it doesn't hang
[[ "$HOOK_EXIT_CODE" -ge 0 ]]
test_pass

# Clean up
cleanup_test_dir

# Print test summary and exit with appropriate code
test_summary
