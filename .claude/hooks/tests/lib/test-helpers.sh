#!/usr/bin/env bash
#
# Test Helper Functions for Hook Testing
# Source this file in test scripts to use assertion functions.
#
# Usage:
#   source "$(dirname "$0")/lib/test-helpers.sh"
#

# Colors for output (disabled if not a tty)
if [[ -t 1 ]]; then
  RED='\033[0;31m'
  GREEN='\033[0;32m'
  YELLOW='\033[0;33m'
  NC='\033[0m' # No Color
else
  RED=''
  GREEN=''
  YELLOW=''
  NC=''
fi

# Counters (per-suite, reset by test_start)
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0
CURRENT_TEST=""

# Cumulative counters (never reset, used by test_summary)
TOTAL_TESTS_RUN=0
TOTAL_TESTS_PASSED=0
TOTAL_TESTS_FAILED=0

# Initialize test suite
# Usage: test_start "Test Suite Name"
test_start() {
  local suite_name="$1"
  
  # Accumulate previous suite's results before resetting
  TOTAL_TESTS_RUN=$((TOTAL_TESTS_RUN + TESTS_RUN))
  TOTAL_TESTS_PASSED=$((TOTAL_TESTS_PASSED + TESTS_PASSED))
  TOTAL_TESTS_FAILED=$((TOTAL_TESTS_FAILED + TESTS_FAILED))
  
  echo ""
  echo "========================================"
  echo " $suite_name"
  echo "========================================"
  
  # Reset per-suite counters
  TESTS_RUN=0
  TESTS_PASSED=0
  TESTS_FAILED=0
}

# Begin a test case
# Usage: test_case "Test description"
test_case() {
  CURRENT_TEST="$1"
  TESTS_RUN=$((TESTS_RUN + 1))
}

# Mark current test as passed
test_pass() {
  TESTS_PASSED=$((TESTS_PASSED + 1))
  echo -e "${GREEN}✓${NC} $CURRENT_TEST"
}

# Mark current test as failed with message
# Usage: test_fail "reason"
test_fail() {
  local reason="$1"
  TESTS_FAILED=$((TESTS_FAILED + 1))
  echo -e "${RED}✗${NC} $CURRENT_TEST"
  echo -e "  ${RED}→ $reason${NC}"
}

# Print test summary and return appropriate exit code
# Usage: test_summary
test_summary() {
  # Add current suite's results to totals
  local total_run=$((TOTAL_TESTS_RUN + TESTS_RUN))
  local total_passed=$((TOTAL_TESTS_PASSED + TESTS_PASSED))
  local total_failed=$((TOTAL_TESTS_FAILED + TESTS_FAILED))
  
  echo ""
  echo "----------------------------------------"
  echo "Results: $total_passed/$total_run passed"
  if [[ $total_failed -gt 0 ]]; then
    echo -e "${RED}$total_failed test(s) failed${NC}"
    return 1
  else
    echo -e "${GREEN}All tests passed${NC}"
    return 0
  fi
}

# Assert two values are equal
# Usage: assert_eq "expected" "actual" ["message"]
assert_eq() {
  local expected="$1"
  local actual="$2"
  local message="${3:-Values should be equal}"

  if [[ "$expected" == "$actual" ]]; then
    test_pass
    return 0
  else
    test_fail "$message: expected '$expected', got '$actual'"
    return 1
  fi
}

# Assert two values are not equal
# Usage: assert_ne "unexpected" "actual" ["message"]
assert_ne() {
  local unexpected="$1"
  local actual="$2"
  local message="${3:-Values should not be equal}"

  if [[ "$unexpected" != "$actual" ]]; then
    test_pass
    return 0
  else
    test_fail "$message: got unwanted value '$actual'"
    return 1
  fi
}

# Assert file exists
# Usage: assert_file_exists "/path/to/file" ["message"]
assert_file_exists() {
  local filepath="$1"
  local message="${2:-File should exist}"

  if [[ -f "$filepath" ]]; then
    test_pass
    return 0
  else
    test_fail "$message: '$filepath' does not exist"
    return 1
  fi
}

# Assert directory exists
# Usage: assert_dir_exists "/path/to/dir" ["message"]
assert_dir_exists() {
  local dirpath="$1"
  local message="${2:-Directory should exist}"

  if [[ -d "$dirpath" ]]; then
    test_pass
    return 0
  else
    test_fail "$message: '$dirpath' does not exist"
    return 1
  fi
}

# Assert file does not exist
# Usage: assert_file_not_exists "/path/to/file" ["message"]
assert_file_not_exists() {
  local filepath="$1"
  local message="${2:-File should not exist}"

  if [[ ! -f "$filepath" ]]; then
    test_pass
    return 0
  else
    test_fail "$message: '$filepath' exists but should not"
    return 1
  fi
}

# Assert a JSON field has expected value
# Requires jq to be installed
# Usage: assert_json_field "json_string" ".field.path" "expected_value" ["message"]
assert_json_field() {
  local json="$1"
  local jq_path="$2"
  local expected="$3"
  local message="${4:-JSON field should match}"

  if ! command -v jq &>/dev/null; then
    test_fail "jq is required for JSON assertions but not installed"
    return 1
  fi

  local actual
  actual=$(echo "$json" | jq -r "$jq_path" 2>/dev/null)
  local jq_exit=$?

  if [[ $jq_exit -ne 0 ]]; then
    test_fail "$message: invalid JSON or jq path"
    return 1
  fi

  if [[ "$expected" == "$actual" ]]; then
    test_pass
    return 0
  else
    test_fail "$message: at '$jq_path' expected '$expected', got '$actual'"
    return 1
  fi
}

# Assert exit code of last command
# Usage: assert_exit_code "expected_code" "actual_code" ["message"]
assert_exit_code() {
  local expected="$1"
  local actual="$2"
  local message="${3:-Exit code should match}"

  if [[ "$expected" == "$actual" ]]; then
    test_pass
    return 0
  else
    test_fail "$message: expected exit code $expected, got $actual"
    return 1
  fi
}

# Assert string contains substring
# Usage: assert_contains "haystack" "needle" ["message"]
assert_contains() {
  local haystack="$1"
  local needle="$2"
  local message="${3:-String should contain substring}"

  if [[ "$haystack" == *"$needle"* ]]; then
    test_pass
    return 0
  else
    test_fail "$message: '$haystack' does not contain '$needle'"
    return 1
  fi
}

# Assert string does not contain substring
# Usage: assert_not_contains "haystack" "needle" ["message"]
assert_not_contains() {
  local haystack="$1"
  local needle="$2"
  local message="${3:-String should not contain substring}"

  if [[ "$haystack" != *"$needle"* ]]; then
    test_pass
    return 0
  else
    test_fail "$message: '$haystack' contains unwanted '$needle'"
    return 1
  fi
}

# Assert command succeeds (exit code 0)
# Usage: assert_success "command" ["message"]
assert_success() {
  local cmd="$1"
  local message="${2:-Command should succeed}"

  eval "$cmd" &>/dev/null
  local exit_code=$?

  if [[ $exit_code -eq 0 ]]; then
    test_pass
    return 0
  else
    test_fail "$message: command failed with exit code $exit_code"
    return 1
  fi
}

# Assert command fails (non-zero exit code)
# Usage: assert_failure "command" ["message"]
assert_failure() {
  local cmd="$1"
  local message="${2:-Command should fail}"

  eval "$cmd" &>/dev/null
  local exit_code=$?

  if [[ $exit_code -ne 0 ]]; then
    test_pass
    return 0
  else
    test_fail "$message: command succeeded but should have failed"
    return 1
  fi
}

# Run a hook script with JSON input and capture exit code
# Usage: run_hook "/path/to/hook.sh" '{"json":"input"}'
#        result in $HOOK_EXIT_CODE, output in $HOOK_OUTPUT
run_hook() {
  local hook_path="$1"
  local json_input="$2"

  # Disable errexit temporarily to capture non-zero exit codes
  set +e
  HOOK_OUTPUT=$(echo "$json_input" | "$hook_path" 2>&1)
  HOOK_EXIT_CODE=$?
  set -e
}

# Create a temporary directory for test isolation
# Usage: setup_test_dir
#        directory path in $TEST_DIR
setup_test_dir() {
  TEST_DIR=$(mktemp -d)
  export TEST_DIR
}

# Clean up temporary test directory
# Usage: cleanup_test_dir
cleanup_test_dir() {
  if [[ -n "$TEST_DIR" && -d "$TEST_DIR" ]]; then
    rm -rf "$TEST_DIR"
  fi
}

# Skip test with message
# Usage: skip_test "reason"
skip_test() {
  local reason="$1"
  TESTS_RUN=$((TESTS_RUN - 1)) # Don't count skipped tests
  echo -e "${YELLOW}⊘${NC} $CURRENT_TEST (skipped: $reason)"
}
