#!/usr/bin/env bash
#
# Run All Hook Tests
#
# Discovers and runs all test-*.sh files in the hooks/tests directory.
# Aggregates results and exits with 0 on all pass, 1 on any failure.
#
# Usage:
#   ./hooks/tests/run-all-tests.sh
#   ./hooks/tests/run-all-tests.sh --verbose
#

set -euo pipefail

# Get the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output (disabled if not a tty)
if [[ -t 1 ]]; then
  RED='\033[0;31m'
  GREEN='\033[0;32m'
  YELLOW='\033[0;33m'
  BLUE='\033[0;34m'
  BOLD='\033[1m'
  NC='\033[0m'
else
  RED=''
  GREEN=''
  YELLOW=''
  BLUE=''
  BOLD=''
  NC=''
fi

# Parse arguments
VERBOSE=false
for arg in "$@"; do
  case $arg in
    --verbose|-v)
      VERBOSE=true
      ;;
  esac
done

# Counters
TOTAL_SUITES=0
PASSED_SUITES=0
FAILED_SUITES=0
declare -a FAILED_TESTS=()

# Print header
echo ""
echo -e "${BOLD}========================================${NC}"
echo -e "${BOLD}        Hook Test Runner${NC}"
echo -e "${BOLD}========================================${NC}"
echo ""

# Find all test-*.sh files
TEST_FILES=()
while IFS= read -r -d '' file; do
  TEST_FILES+=("$file")
done < <(find "$SCRIPT_DIR" -maxdepth 1 -name "test-*.sh" -type f -print0 | sort -z)

# Check if any tests found
if [[ ${#TEST_FILES[@]} -eq 0 ]]; then
  echo -e "${YELLOW}No test files found (test-*.sh)${NC}"
  echo "Test runner is ready. Add test-*.sh files to hooks/tests/ to run tests."
  echo ""
  exit 0
fi

echo -e "Found ${#TEST_FILES[@]} test suite(s)"
echo ""

# Run each test file
for test_file in "${TEST_FILES[@]}"; do
  test_name=$(basename "$test_file")
  TOTAL_SUITES=$((TOTAL_SUITES + 1))

  echo -e "${BLUE}▶${NC} Running: $test_name"

  # Make sure it's executable
  if [[ ! -x "$test_file" ]]; then
    chmod +x "$test_file"
  fi

  # Run the test and capture output
  set +e
  if $VERBOSE; then
    # Show all output in verbose mode
    "$test_file"
    exit_code=$?
  else
    # Capture output, show only on failure
    output=$("$test_file" 2>&1)
    exit_code=$?
  fi
  set -e

  if [[ $exit_code -eq 0 ]]; then
    PASSED_SUITES=$((PASSED_SUITES + 1))
    echo -e "  ${GREEN}✓${NC} $test_name passed"
  else
    FAILED_SUITES=$((FAILED_SUITES + 1))
    FAILED_TESTS+=("$test_name")
    echo -e "  ${RED}✗${NC} $test_name failed (exit code: $exit_code)"
    if ! $VERBOSE && [[ -n "${output:-}" ]]; then
      echo ""
      echo "  Output:"
      echo "$output" | sed 's/^/    /'
      echo ""
    fi
  fi
done

# Print summary
echo ""
echo -e "${BOLD}========================================${NC}"
echo -e "${BOLD}               Summary${NC}"
echo -e "${BOLD}========================================${NC}"
echo ""
echo "Test Suites: $PASSED_SUITES/$TOTAL_SUITES passed"

if [[ $FAILED_SUITES -gt 0 ]]; then
  echo ""
  echo -e "${RED}Failed test suites:${NC}"
  for failed in "${FAILED_TESTS[@]}"; do
    echo -e "  ${RED}✗${NC} $failed"
  done
  echo ""
  echo -e "${RED}${BOLD}TESTS FAILED${NC}"
  exit 1
else
  echo ""
  echo -e "${GREEN}${BOLD}ALL TESTS PASSED${NC}"
  exit 0
fi
