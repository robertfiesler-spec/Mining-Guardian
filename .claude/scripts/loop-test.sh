#!/bin/bash
#
# loop-test.sh - Sanity-check loop infrastructure (no AI calls)
#
# Tests shell plumbing for loop.sh, including:
# 1. jq is installed and parses JSON correctly
# 2. ai-provider.sh sourcing does NOT leak shell flags
# 3. ai_provider_resolve finds claude or codex
# 4. find_prd locates the most-recent .json in docs/plans/
# 5. next_story extracts the correct story from a fixture plan
# 6. all_complete returns correct status for incomplete plans
# 7. all_complete returns correct status for complete plans
# 8. count_stories returns "N/M" format
# 9. init_plan_session creates expected session files
#
# Usage: bash scripts/loop-test.sh
#
# No AI provider required. No network access. Fast (<5s).

set -e

# Script directory for sourcing helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Shared logging (includes log_test, log_pass, log_fail, colors)
source "$SCRIPT_DIR/lib/logging.sh"

# Counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Test workspace
TEST_WORK_DIR=""

# ─── Assert helpers ───────────────────────────────────────────────────────────

run_test() {
  local test_name=$1
  TESTS_RUN=$((TESTS_RUN + 1))
  log_test "$test_name"
}

assert_eq() {
  local actual=$1
  local expected=$2
  local message=$3

  if [[ "$actual" == "$expected" ]]; then
    TESTS_PASSED=$((TESTS_PASSED + 1))
    log_pass "$message"
    return 0
  else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    log_fail "$message"
    log_fail "  Expected: '$expected'"
    log_fail "  Actual:   '$actual'"
    return 1
  fi
}

assert_file_exists() {
  local file=$1
  local message=$2

  if [[ -f "$file" ]]; then
    TESTS_PASSED=$((TESTS_PASSED + 1))
    log_pass "$message"
    return 0
  else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    log_fail "$message"
    log_fail "  File not found: $file"
    return 1
  fi
}

assert_json_field() {
  local file=$1
  local field=$2
  local expected=$3
  local message=$4

  local actual=$(jq -r "$field" "$file" 2>/dev/null || echo "")
  assert_eq "$actual" "$expected" "$message"
}

assert_not_eq() {
  local actual=$1
  local unexpected=$2
  local message=$3

  if [[ "$actual" != "$unexpected" ]]; then
    TESTS_PASSED=$((TESTS_PASSED + 1))
    log_pass "$message"
    return 0
  else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    log_fail "$message"
    log_fail "  Should NOT be: '$unexpected'"
    return 1
  fi
}

# ─── Test workspace ───────────────────────────────────────────────────────────

setup_test_env() {
  log_info "Setting up test environment..."
  TEST_WORK_DIR=$(mktemp -d /tmp/loop-test-XXXXXX)
  mkdir -p "$TEST_WORK_DIR/docs/plans"
  mkdir -p "$TEST_WORK_DIR/.claude/state"
  # Initialize as a git repo so session-manager functions work
  git init -q "$TEST_WORK_DIR"
  (cd "$TEST_WORK_DIR" && git commit -q --allow-empty -m "init")
  log_info "Test workspace: $TEST_WORK_DIR"
}

teardown_test_env() {
  log_info "Cleaning up test environment..."
  rm -rf "$TEST_WORK_DIR"
  unset CLAUDE_PLAN AI_PROVIDER_BIN AI_PROVIDER
}

# Write the fixture plan to a given path
write_fixture_plan() {
  local path="$1"
  cat > "$path" << 'EOF'
{
  "feature": "hello-world-test",
  "stories": [
    {
      "id": "US-1",
      "title": "Hello world story",
      "type": "Core",
      "priority": 1,
      "passes": false
    },
    {
      "id": "US-2",
      "title": "Second hello world story",
      "type": "Core",
      "priority": 2,
      "passes": true
    }
  ]
}
EOF
}

# Write a fully-complete fixture plan
write_complete_plan() {
  local path="$1"
  cat > "$path" << 'EOF'
{
  "feature": "hello-world-complete",
  "stories": [
    {
      "id": "US-1",
      "title": "Hello world story",
      "type": "Core",
      "priority": 1,
      "passes": true
    },
    {
      "id": "US-2",
      "title": "Second hello world story",
      "type": "Core",
      "priority": 2,
      "passes": true
    }
  ]
}
EOF
}

# ─── Loop helper functions (replicated from loop.sh) ─────────────────────────
# These mirror the exact jq logic in loop.sh. We can't source loop.sh directly
# because it calls main "$@" unconditionally at the bottom.

_find_prd() {
  local plan_dir="$1"
  local prd
  prd=$(ls -t "$plan_dir"/*.json 2>/dev/null | head -1)
  if [[ -z "$prd" ]]; then
    return 1
  fi
  echo "$prd"
}

_all_complete() {
  local prd=$1
  local incomplete=$(jq '[.stories[] | select(.passes == false)] | length' "$prd")
  [[ "$incomplete" -eq 0 ]]
}

_next_story() {
  local prd=$1
  jq -r '[.stories[] | select(.passes == false)] | sort_by(.priority) | .[0] | "\(.id): \(.title) [\(.type)]"' "$prd"
}

_count_stories() {
  local prd=$1
  local total=$(jq '.stories | length' "$prd")
  local complete=$(jq '[.stories[] | select(.passes == true)] | length' "$prd")
  echo "$complete/$total"
}

# ─── Test functions ───────────────────────────────────────────────────────────

# Test 1: jq is available and functional
test_jq_available() {
  run_test "jq is available and parses JSON correctly"

  if ! command -v jq >/dev/null 2>&1; then
    TESTS_FAILED=$((TESTS_FAILED + 1))
    log_fail "jq is not installed"
    return 1
  fi

  local result
  result=$(echo '{"x":1}' | jq '.x')
  assert_eq "$result" "1" "jq parses JSON correctly"
}

# Test 2: Sourcing ai-provider.sh does not leak shell flags
test_ai_provider_no_flag_leak() {
  run_test "Sourcing ai-provider.sh does not leak shell flags"

  # Capture shell options before sourcing
  local flags_before flags_after
  flags_before=$(set +o)

  # Source ai-provider.sh (as loop.sh does)
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/lib/ai-provider.sh"

  # Capture shell options after sourcing
  flags_after=$(set +o)

  assert_eq "$flags_after" "$flags_before" \
    "Shell flags unchanged after sourcing ai-provider.sh"
}

# Test 3: ai_provider_resolve detects available provider
test_ai_provider_resolve() {
  run_test "ai_provider_resolve detects available AI provider"

  # Reset provider state
  AI_PROVIDER_BIN=""
  AI_PROVIDER="auto"

  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/lib/ai-provider.sh"

  if ! command -v claude >/dev/null 2>&1 && ! command -v codex >/dev/null 2>&1; then
    TESTS_PASSED=$((TESTS_PASSED + 1))
    log_pass "SKIP: Neither claude nor codex on PATH (acceptable in CI)"
    return 0
  fi

  if ai_provider_resolve; then
    if [[ "$AI_PROVIDER_BIN" == "claude" || "$AI_PROVIDER_BIN" == "codex" ]]; then
      TESTS_PASSED=$((TESTS_PASSED + 1))
      log_pass "AI_PROVIDER_BIN resolved to: $AI_PROVIDER_BIN"
    else
      TESTS_FAILED=$((TESTS_FAILED + 1))
      log_fail "Unknown AI_PROVIDER_BIN: $AI_PROVIDER_BIN"
    fi
  else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    log_fail "ai_provider_resolve returned non-zero"
  fi
}

# Test 4: find_prd locates plan JSON
test_find_prd() {
  run_test "find_prd locates most-recent plan JSON"

  local plan_path="$TEST_WORK_DIR/docs/plans/hello-world-test.json"
  write_fixture_plan "$plan_path"

  local found
  found=$(_find_prd "$TEST_WORK_DIR/docs/plans")
  assert_eq "$found" "$plan_path" "find_prd returns the fixture plan path"
}

# Test 5: next_story extracts first incomplete story by priority
test_next_story() {
  run_test "next_story extracts first incomplete story by priority"

  local plan_path="$TEST_WORK_DIR/docs/plans/hello-world-test.json"
  write_fixture_plan "$plan_path"

  local story
  story=$(_next_story "$plan_path")
  assert_eq "$story" "US-1: Hello world story [Core]" \
    "next_story returns correct story string"
}

# Test 6: all_complete returns false for incomplete plan
test_all_complete_false() {
  run_test "all_complete returns false for incomplete plan"

  local plan_path="$TEST_WORK_DIR/docs/plans/hello-world-test.json"
  write_fixture_plan "$plan_path"

  if _all_complete "$plan_path"; then
    TESTS_FAILED=$((TESTS_FAILED + 1))
    log_fail "all_complete should return false for incomplete plan"
  else
    TESTS_PASSED=$((TESTS_PASSED + 1))
    log_pass "all_complete correctly returns false"
  fi
}

# Test 7: all_complete returns true for completed plan
test_all_complete_true() {
  run_test "all_complete returns true for completed plan"

  local plan_path="$TEST_WORK_DIR/docs/plans/complete-plan.json"
  write_complete_plan "$plan_path"

  if _all_complete "$plan_path"; then
    TESTS_PASSED=$((TESTS_PASSED + 1))
    log_pass "all_complete correctly returns true"
  else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    log_fail "all_complete should return true for completed plan"
  fi
}

# Test 8: count_stories returns N/M format
test_count_stories() {
  run_test "count_stories returns N/M format"

  local plan_path="$TEST_WORK_DIR/docs/plans/hello-world-test.json"
  write_fixture_plan "$plan_path"

  local count
  count=$(_count_stories "$plan_path")
  assert_eq "$count" "1/2" "count_stories returns 1/2 (1 complete, 2 total)"
}

# Test 9: init_plan_session creates correct session file
test_session_init() {
  run_test "init_plan_session creates correct session file"

  local plan_path="$TEST_WORK_DIR/docs/plans/hello-world-test.json"
  write_fixture_plan "$plan_path"

  # Source session manager and run init from within the test workspace
  (
    cd "$TEST_WORK_DIR"
    # Re-source to pick up the test workspace paths
    source "$SCRIPT_DIR/lib/session-manager.sh"

    local session_file
    session_file=$(init_plan_session "$plan_path")

    # Verify file exists
    if [[ ! -f "$session_file" ]]; then
      echo "FAIL:session_file_missing"
      exit 1
    fi

    # Output fields for verification
    echo "version=$(jq -r '.version' "$session_file")"
    echo "status=$(jq -r '.status' "$session_file")"
    echo "plan_name=$(jq -r '.plan.name' "$session_file")"
    echo "total_stories=$(jq -r '.progress.total_stories' "$session_file")"
  )
  local subshell_exit=$?

  if [[ $subshell_exit -ne 0 ]]; then
    TESTS_FAILED=$((TESTS_FAILED + 1))
    log_fail "init_plan_session failed in subshell"
    return 1
  fi

  # Re-run to capture outputs (subshell output was printed above)
  local session_dir="$TEST_WORK_DIR/.claude/state/plans/hello-world-test"
  local session_file="$session_dir/session.json"

  assert_file_exists "$session_file" "Session file created"
  assert_json_field "$session_file" ".version" "2.0" "Version is 2.0"
  assert_json_field "$session_file" ".status" "running" "Initial status is running"
  assert_json_field "$session_file" ".plan.name" "hello-world-test" "Plan name extracted correctly"
  assert_json_field "$session_file" ".progress.total_stories" "2" "Total stories count is correct"
}

# ─── Main ─────────────────────────────────────────────────────────────────────

main() {
  echo ""
  echo "=========================================="
  echo "  Loop Infrastructure Test Suite"
  echo "=========================================="
  echo ""

  setup_test_env

  test_jq_available
  echo ""

  test_ai_provider_no_flag_leak
  echo ""

  test_ai_provider_resolve
  echo ""

  test_find_prd
  echo ""

  test_next_story
  echo ""

  test_all_complete_false
  echo ""

  test_all_complete_true
  echo ""

  test_count_stories
  echo ""

  test_session_init
  echo ""

  teardown_test_env

  echo "=========================================="
  echo "  Test Results"
  echo "=========================================="
  echo "Tests run:    $TESTS_RUN"
  echo "Tests passed: $TESTS_PASSED"
  echo "Tests failed: $TESTS_FAILED"
  echo ""

  if [[ $TESTS_FAILED -eq 0 ]]; then
    log_pass "All tests passed!"
    exit 0
  else
    log_fail "Some tests failed"
    exit 1
  fi
}

main "$@"
