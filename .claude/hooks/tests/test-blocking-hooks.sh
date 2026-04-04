#!/usr/bin/env bash
#
# Test Suite: Blocking Hooks
#
# Tests for hooks that block operations based on various criteria.
# - block-md-creation.sh: Blocks markdown file creation except allowed files
# - git-push-review.sh: Blocks pushes to protected branches
#
# Usage:
#   ./hooks/tests/test-blocking-hooks.sh
#

set -euo pipefail

# Get the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOKS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FIXTURES_DIR="$SCRIPT_DIR/fixtures/inputs"

# Source test helpers
source "$SCRIPT_DIR/lib/test-helpers.sh"

# ============================================================================
# Test block-md-creation.sh
# ============================================================================

test_start "block-md-creation.sh Tests"

BLOCK_MD_HOOK="$HOOKS_DIR/pre-tool-use/block-md-creation.sh"

# Test: README.md should be allowed (exit 0)
test_case "README.md is allowed"
run_hook "$BLOCK_MD_HOOK" "$(cat "$FIXTURES_DIR/write-readme.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "README.md should pass"

# Test: CLAUDE.md should be allowed (exit 0)
test_case "CLAUDE.md is allowed"
run_hook "$BLOCK_MD_HOOK" "$(cat "$FIXTURES_DIR/write-claude-md.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "CLAUDE.md should pass"

# Test: Random .md file should be blocked (exit 2)
test_case "random.md is blocked"
run_hook "$BLOCK_MD_HOOK" "$(cat "$FIXTURES_DIR/write-random-md.json")"
assert_exit_code 2 "$HOOK_EXIT_CODE" "Random .md should be blocked"

# Test: Checkpoint .md files should be allowed (exit 0)
test_case "checkpoint .md files are allowed"
run_hook "$BLOCK_MD_HOOK" "$(cat "$FIXTURES_DIR/write-checkpoint.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Checkpoint .md should pass"

# Test: Plan .md files should be allowed (exit 0)
test_case "plan .md files are allowed"
run_hook "$BLOCK_MD_HOOK" "$(cat "$FIXTURES_DIR/write-plan.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Plan .md should pass"

# Test: WORKFLOW.md should be allowed (exit 0)
test_case "WORKFLOW.md is allowed"
run_hook "$BLOCK_MD_HOOK" "$(cat "$FIXTURES_DIR/write-workflow.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "WORKFLOW.md should pass"

# Test: Non-Write tool should pass through (exit 0)
test_case "non-Write tools pass through"
run_hook "$BLOCK_MD_HOOK" "$(cat "$FIXTURES_DIR/bash-npm-install.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Non-Write tools should pass"

# Test: Non-.md files should pass through (exit 0)
test_case "non-.md files pass through"
run_hook "$BLOCK_MD_HOOK" "$(cat "$FIXTURES_DIR/edit-typescript.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Non-.md files should pass"

# Test: Blocked output contains BLOCKED message
test_case "blocked output contains BLOCKED message"
run_hook "$BLOCK_MD_HOOK" "$(cat "$FIXTURES_DIR/write-random-md.json")"
assert_contains "$HOOK_OUTPUT" "BLOCKED" "Output should mention BLOCKED"

# ============================================================================
# Test git-push-review.sh
# ============================================================================

test_start "git-push-review.sh Tests"

GIT_PUSH_HOOK="$HOOKS_DIR/pre-tool-use/git-push-review.sh"

# Detect current branch for branch-aware tests
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
IS_PROTECTED_BRANCH=false
if [[ "$CURRENT_BRANCH" == "main" || "$CURRENT_BRANCH" == "master" ]]; then
  IS_PROTECTED_BRANCH=true
fi

# Test: Non-Bash tool should pass through (exit 0)
test_case "non-Bash tools pass through"
run_hook "$GIT_PUSH_HOOK" "$(cat "$FIXTURES_DIR/write-readme.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Non-Bash tools should pass"

# Test: Non-git-push command should pass through (exit 0)
test_case "non-git-push commands pass through"
run_hook "$GIT_PUSH_HOOK" "$(cat "$FIXTURES_DIR/bash-npm-install.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Non-git-push should pass"

# Test: Simple bash command should pass through (exit 0)
test_case "simple bash commands pass through"
run_hook "$GIT_PUSH_HOOK" "$(cat "$FIXTURES_DIR/bash-ls.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Simple bash should pass"

# Test: Git push output contains review header
test_case "git push shows review header"
run_hook "$GIT_PUSH_HOOK" "$(cat "$FIXTURES_DIR/bash-git-push-feature.json")"
assert_contains "$HOOK_OUTPUT" "Git Push Review" "Output should show review header"

# Test: Git push output mentions branch info
test_case "git push shows branch info"
run_hook "$GIT_PUSH_HOOK" "$(cat "$FIXTURES_DIR/bash-git-push-feature.json")"
assert_contains "$HOOK_OUTPUT" "Branch:" "Output should show branch info"

# Test: Git push exit code depends on current branch
# The hook checks the LOCAL current branch, not the push target
# From main/master: exit 1 (warning)
# From other branches: exit 0 (allowed)
test_case "git push exit code correct for current branch"
run_hook "$GIT_PUSH_HOOK" "$(cat "$FIXTURES_DIR/bash-git-push-feature.json")"
if [[ "$IS_PROTECTED_BRANCH" == "true" ]]; then
  assert_exit_code 1 "$HOOK_EXIT_CODE" "Push from main/master should warn (exit 1)"
else
  assert_exit_code 0 "$HOOK_EXIT_CODE" "Push from feature branch should pass (exit 0)"
fi

# Test: Push to main target - exit code still depends on LOCAL branch
test_case "git push origin main respects local branch"
run_hook "$GIT_PUSH_HOOK" "$(cat "$FIXTURES_DIR/bash-git-push-main.json")"
if [[ "$IS_PROTECTED_BRANCH" == "true" ]]; then
  assert_exit_code 1 "$HOOK_EXIT_CODE" "Push from main/master should warn"
else
  assert_exit_code 0 "$HOOK_EXIT_CODE" "Push from feature branch should pass"
fi

# Test: Push to master target - exit code still depends on LOCAL branch
test_case "git push origin master respects local branch"
run_hook "$GIT_PUSH_HOOK" "$(cat "$FIXTURES_DIR/bash-git-push-master.json")"
if [[ "$IS_PROTECTED_BRANCH" == "true" ]]; then
  assert_exit_code 1 "$HOOK_EXIT_CODE" "Push from main/master should warn"
else
  assert_exit_code 0 "$HOOK_EXIT_CODE" "Push from feature branch should pass"
fi

# Test: When on protected branch, output contains warning
if [[ "$IS_PROTECTED_BRANCH" == "true" ]]; then
  test_case "protected branch shows warning message"
  run_hook "$GIT_PUSH_HOOK" "$(cat "$FIXTURES_DIR/bash-git-push-feature.json")"
  assert_contains "$HOOK_OUTPUT" "WARNING" "Output should contain WARNING on protected branch"
fi

# Print test summary and exit with appropriate code
test_summary
