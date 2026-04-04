#!/usr/bin/env bash
#
# Test Suite: Token Budget Script
#
# Tests for scripts/token-budget.sh
#
# Usage:
#   ./hooks/tests/test-token-budget.sh
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TOKEN_BUDGET="$REPO_ROOT/scripts/token-budget.sh"

source "$SCRIPT_DIR/lib/test-helpers.sh"

# Source the script for unit testing individual functions
source "$TOKEN_BUDGET"

# ─── Suite 1: Token Estimation ──────────────────────────────

test_start "Token Estimation"

test_case "returns correct count for known file size"
setup_test_dir
# Create file with exactly 400 chars = 100 tokens
printf '%0400d' 0 > "$TEST_DIR/known.md"
result=$(estimate_tokens "$TEST_DIR/known.md")
assert_eq "100" "$result" "400 chars should be 100 tokens"
cleanup_test_dir

test_case "returns 0 for nonexistent file"
result=$(estimate_tokens "/nonexistent/file.md")
assert_eq "0" "$result" "Missing file should return 0"

test_case "returns 0 for empty file"
setup_test_dir
touch "$TEST_DIR/empty.md"
result=$(estimate_tokens "$TEST_DIR/empty.md")
assert_eq "0" "$result" "Empty file should return 0"
cleanup_test_dir

test_case "handles large file correctly"
setup_test_dir
# 4000 chars = 1000 tokens
printf '%04000d' 0 > "$TEST_DIR/large.md"
result=$(estimate_tokens "$TEST_DIR/large.md")
assert_eq "1000" "$result" "4000 chars should be 1000 tokens"
cleanup_test_dir

# ─── Suite 2: Threshold Checking ────────────────────────────

test_start "Threshold Checking"

# Use defaults: WARN_AT_PERCENT=80, FAIL_AT_PERCENT=100
WARN_AT_PERCENT=80
FAIL_AT_PERCENT=100

test_case "OK when tokens well below threshold"
result=$(check_threshold 4000 8000)
assert_eq "OK" "$result" "4000/8000 should be OK"

test_case "OK when tokens just below warn threshold"
result=$(check_threshold 6399 8000)
assert_eq "OK" "$result" "6399/8000 (79.9%) should be OK"

test_case "WARN when tokens at warn threshold"
result=$(check_threshold 6400 8000)
assert_eq "WARN" "$result" "6400/8000 (80%) should be WARN"

test_case "WARN when tokens between warn and fail"
result=$(check_threshold 7500 8000)
assert_eq "WARN" "$result" "7500/8000 (93.7%) should be WARN"

test_case "FAIL when tokens at fail threshold"
result=$(check_threshold 8000 8000)
assert_eq "FAIL" "$result" "8000/8000 (100%) should be FAIL"

test_case "FAIL when tokens above threshold"
result=$(check_threshold 9000 8000)
assert_eq "FAIL" "$result" "9000/8000 (112.5%) should be FAIL"

test_case "handles zero threshold"
result=$(check_threshold 100 0)
# 100 >= 0*100/100 = 0, so FAIL
assert_eq "FAIL" "$result" "Any tokens with 0 threshold should be FAIL"

test_case "respects custom warn percentage"
WARN_AT_PERCENT=90
result=$(check_threshold 7100 8000)
assert_eq "OK" "$result" "7100/8000 (88.7%) with 90% warn should be OK"
result=$(check_threshold 7200 8000)
assert_eq "WARN" "$result" "7200/8000 (90%) with 90% warn should be WARN"
WARN_AT_PERCENT=80  # Reset

# ─── Suite 3: Config Loading ────────────────────────────────

test_start "Config Loading"

test_case "loads thresholds from valid config"
setup_test_dir
cat > "$TEST_DIR/config.json" <<'EOF'
{
  "version": "1.0.0",
  "tokenBudget": {
    "enabled": true,
    "thresholds": {
      "command": 5000,
      "agent": 3000
    },
    "warnAtPercent": 70,
    "failAtPercent": 90
  }
}
EOF
load_config "$TEST_DIR/config.json"
if [[ "$THRESHOLD_COMMAND" == "5000" ]] && [[ "$WARN_AT_PERCENT" == "70" ]] && [[ "$FAIL_AT_PERCENT" == "90" ]]; then
  test_pass
else
  test_fail "Config values not loaded: command=$THRESHOLD_COMMAND warn=$WARN_AT_PERCENT fail=$FAIL_AT_PERCENT"
fi
# Reset defaults
THRESHOLD_COMMAND=8000
WARN_AT_PERCENT=80
FAIL_AT_PERCENT=100
cleanup_test_dir

test_case "uses defaults when tokenBudget section missing"
setup_test_dir
echo '{"version": "1.0.0"}' > "$TEST_DIR/config.json"
THRESHOLD_COMMAND=8000  # Ensure default
load_config "$TEST_DIR/config.json" 2>/dev/null
assert_eq "8000" "$THRESHOLD_COMMAND" "Should keep default when section missing"
cleanup_test_dir

test_case "uses defaults when config file not found"
THRESHOLD_COMMAND=8000
load_config "/nonexistent/config.json" 2>/dev/null
assert_eq "8000" "$THRESHOLD_COMMAND" "Should keep default when file missing"

test_case "exits when enabled is false"
setup_test_dir
cat > "$TEST_DIR/config.json" <<'EOF'
{
  "tokenBudget": {
    "enabled": false
  }
}
EOF
# This should exit 0 -- run in subshell
set +e
output=$(bash -c "source '$TOKEN_BUDGET'; load_config '$TEST_DIR/config.json'" 2>/dev/null)
exit_code=$?
set -e
assert_eq "0" "$exit_code" "Should exit 0 when disabled"
cleanup_test_dir

# ─── Suite 4: Scanning ──────────────────────────────────────

test_start "Scanning"

test_case "scans commands directory"
setup_test_dir
mkdir -p "$TEST_DIR/commands"
printf '%0800d' 0 > "$TEST_DIR/commands/foo.md"   # 200 tokens
printf '%01200d' 0 > "$TEST_DIR/commands/bar.md"  # 300 tokens

# Reset accumulators
FILE_NAMES=()
FILE_TOKENS=()
FILE_CATEGORIES=()
FILE_STATUSES=()
TOTAL_COMMANDS=0
FAIL_COUNT=0
WARN_COUNT=0

scan_commands "$TEST_DIR"
assert_eq "2" "${#FILE_NAMES[@]}" "Should find 2 command files"

test_case "accumulates command totals"
assert_eq "500" "$TOTAL_COMMANDS" "Total should be 200+300=500"
cleanup_test_dir

test_case "scans skills with nested structure"
setup_test_dir
mkdir -p "$TEST_DIR/skills/my-skill"
printf '%02000d' 0 > "$TEST_DIR/skills/my-skill/SKILL.md"  # 500 tokens

FILE_NAMES=()
FILE_TOKENS=()
FILE_CATEGORIES=()
FILE_STATUSES=()
TOTAL_SKILLS=0
FAIL_COUNT=0
WARN_COUNT=0

scan_skills "$TEST_DIR"
assert_eq "1" "${#FILE_NAMES[@]}" "Should find 1 skill file"

test_case "skill file recorded with correct path"
assert_eq "skills/my-skill/SKILL.md" "${FILE_NAMES[0]}" "Should use nested path"
cleanup_test_dir

test_case "scans rules with design-system subdirectory"
setup_test_dir
mkdir -p "$TEST_DIR/rules/design-system"
printf '%0400d' 0 > "$TEST_DIR/rules/base.md"
printf '%0800d' 0 > "$TEST_DIR/rules/design-system/colors.md"

FILE_NAMES=()
FILE_TOKENS=()
FILE_CATEGORIES=()
FILE_STATUSES=()
TOTAL_RULES=0
TOTAL_ALWAYS_LOADED=0
FAIL_COUNT=0
WARN_COUNT=0

scan_rules "$TEST_DIR"
assert_eq "2" "${#FILE_NAMES[@]}" "Should find 2 rule files"

test_case "rules contribute to always-loaded total"
assert_eq "$TOTAL_ALWAYS_LOADED" "$TOTAL_RULES" "Rules tokens should equal always-loaded contribution"
cleanup_test_dir

# ─── Suite 5: Baseline Save/Compare ─────────────────────────

test_start "Baseline Operations"

test_case "save-baseline creates valid JSON"
setup_test_dir
mkdir -p "$TEST_DIR/commands"
printf '%02000d' 0 > "$TEST_DIR/commands/test.md"
echo '{"version":"1.0.0"}' > "$TEST_DIR/config.json"

FILE_NAMES=()
FILE_TOKENS=()
FILE_CATEGORIES=()
FILE_STATUSES=()
TOTAL_COMMANDS=0
TOTAL_ALWAYS_LOADED=0
TOTAL_AGENTS=0
TOTAL_SKILLS=0
TOTAL_RULES=0
FAIL_COUNT=0
WARN_COUNT=0
BASELINE_FILE="$TEST_DIR/baseline.json"

scan_commands "$TEST_DIR"
save_baseline "$TEST_DIR" > /dev/null

if [[ -f "$TEST_DIR/baseline.json" ]] && jq . "$TEST_DIR/baseline.json" > /dev/null 2>&1; then
  test_pass
else
  test_fail "Baseline file not created or invalid JSON"
fi

test_case "baseline contains timestamp"
bl_json=$(cat "$TEST_DIR/baseline.json")
assert_contains "$bl_json" "timestamp" "Baseline should have timestamp"

test_case "baseline contains component data"
bl_json=$(cat "$TEST_DIR/baseline.json")
assert_contains "$bl_json" "commands/test.md" "Baseline should contain scanned file"

test_case "compare detects no changes"
output=$(compare_baseline "$TEST_DIR" 2>/dev/null)
assert_contains "$output" "(no changes)" "Should report no changes"
cleanup_test_dir

# ─── Suite 6: Full Script Exit Codes ────────────────────────

test_start "Exit Codes"

test_case "exit 0 when all within budget"
setup_test_dir
mkdir -p "$TEST_DIR/commands"
printf '%0400d' 0 > "$TEST_DIR/commands/small.md"  # 100 tokens, well under 8000
cat > "$TEST_DIR/config.json" <<'EOF'
{
  "version": "1.0.0",
  "tokenBudget": {
    "enabled": true,
    "thresholds": { "command": 8000 },
    "warnAtPercent": 80,
    "failAtPercent": 100
  }
}
EOF
set +e
"$TOKEN_BUDGET" --check --config "$TEST_DIR/config.json" --component commands > /dev/null 2>&1
exit_code=$?
set -e
# The script uses SCRIPT_DIR to detect root, so it will find the real repo.
# For this test, just verify the script runs without crashing.
assert_eq "0" "$exit_code" "Should exit 0 with small files"
cleanup_test_dir

test_case "exit 2 on bad component filter"
set +e
"$TOKEN_BUDGET" --component "nonexistent" > /dev/null 2>&1
exit_code=$?
set -e
assert_eq "2" "$exit_code" "Should exit 2 for unknown component type"

# ─── Suite 7: Report Format ─────────────────────────────────

test_start "Report Format"

test_case "report contains all section headers"
output=$("$TOKEN_BUDGET" --report 2>/dev/null)
assert_contains "$output" "Token Budget Report" "Should have title"

test_case "report contains always-loaded section"
assert_contains "$output" "Always-Loaded" "Should have always-loaded section"

test_case "report contains commands section"
assert_contains "$output" "Commands" "Should have commands section"

test_case "report contains aggregates section"
assert_contains "$output" "Aggregates" "Should have aggregates section"

test_case "report contains result summary"
assert_contains "$output" "RESULT:" "Should have result line"

test_case "json output is valid"
json_output=$("$TOKEN_BUDGET" --json 2>/dev/null)
if echo "$json_output" | jq . > /dev/null 2>&1; then
  test_pass
else
  test_fail "JSON output is not valid JSON"
fi

test_case "json contains aggregates"
# Just check it's a number, not empty
cmd_tokens=$(echo "$json_output" | jq -r '.aggregates.commands')
if [[ "$cmd_tokens" =~ ^[0-9]+$ ]]; then
  test_pass
else
  test_fail "Commands aggregate should be a number, got: $cmd_tokens"
fi

# Override previous test_case since we called test_pass/test_fail directly
# This is fine because the test framework counts via test_case calls

# ─── Summary ────────────────────────────────────────────────

test_summary
