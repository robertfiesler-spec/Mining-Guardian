#!/usr/bin/env bash
#
# Self-test for test runner - verifies test infrastructure works
#

# Source test helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/test-helpers.sh"

test_start "Test Runner Self-Test"

# Test 1: test_helpers.sh can be sourced
test_case "test-helpers.sh is sourceable"
if [[ -n "$TESTS_RUN" ]]; then
  test_pass
else
  test_fail "TESTS_RUN variable not set"
fi

# Test 2: assert_eq works correctly
test_case "assert_eq passes for equal values"
assert_eq "hello" "hello" "Strings should match"

# Test 3: assert_file_exists works
test_case "assert_file_exists works on existing file"
assert_file_exists "$SCRIPT_DIR/lib/test-helpers.sh" "test-helpers.sh should exist"

# Test 4: assert_dir_exists works
test_case "assert_dir_exists works on existing directory"
assert_dir_exists "$SCRIPT_DIR/lib" "lib directory should exist"

# Test 5: assert_exit_code works
test_case "assert_exit_code works correctly"
true
assert_exit_code "0" "$?" "true should exit with 0"

# Print summary and exit
test_summary
