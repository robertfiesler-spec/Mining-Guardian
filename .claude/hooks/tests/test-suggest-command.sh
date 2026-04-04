#!/usr/bin/env bash
#
# Test Suite: Command Suggestion System
#
# Tests for:
# - compile-suggestions.js: Compiles frontmatter → registry JSON
# - suggest-actions.js: PostToolUse hook for mid-session suggestions
#
# Usage:
#   ./hooks/tests/test-suggest-command.sh
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOKS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TOOLKIT_ROOT="$(cd "$HOOKS_DIR/.." && pwd)"
FIXTURES_DIR="$SCRIPT_DIR/fixtures/inputs"

source "$SCRIPT_DIR/lib/test-helpers.sh"

# Helper: run a Node.js hook script with JSON input
# Usage: run_node_hook "/path/to/hook.js" '{"json":"input"}'
#        result in $HOOK_EXIT_CODE, output in $HOOK_OUTPUT
run_node_hook() {
  local hook_path="$1"
  local json_input="$2"
  set +e
  HOOK_OUTPUT=$(echo "$json_input" | node "$hook_path" 2>&1)
  HOOK_EXIT_CODE=$?
  set -e
}

# ============================================================================
# Test compile-suggestions.js
# ============================================================================

test_start "compile-suggestions.js Tests"

COMPILE_SCRIPT="$TOOLKIT_ROOT/scripts/compile-suggestions.js"

# Test: Compiles from commands directory
test_case "compiles triggers from commands with frontmatter"
TEMP_OUT=$(mktemp)
node "$COMPILE_SCRIPT" --output "$TEMP_OUT" 2>/dev/null
if [ -f "$TEMP_OUT" ] && [ -s "$TEMP_OUT" ]; then
  test_pass
else
  test_fail "Output file should exist and be non-empty"
fi

# Test: Output is valid JSON
test_case "output is valid JSON"
if node -e "JSON.parse(require('fs').readFileSync('$TEMP_OUT','utf8'))" 2>/dev/null; then
  test_pass
else
  test_fail "Output should be valid JSON"
fi

# Test: Registry has triggers array
test_case "registry contains triggers array"
TRIGGER_COUNT=$(node -e "const r=JSON.parse(require('fs').readFileSync('$TEMP_OUT','utf8')); console.log(r.triggers.length)" 2>/dev/null)
if [ "$TRIGGER_COUNT" -gt 0 ]; then
  test_pass
else
  test_fail "Should have at least one trigger, got $TRIGGER_COUNT"
fi

# Test: Triggers have required fields
test_case "triggers have required fields (command, signal, message)"
VALID=$(node -e "
  const r=JSON.parse(require('fs').readFileSync('$TEMP_OUT','utf8'));
  const valid = r.triggers.every(t => t.command && t.signal && t.message);
  console.log(valid ? 'true' : 'false');
" 2>/dev/null)
if [ "$VALID" = "true" ]; then
  test_pass
else
  test_fail "All triggers should have command, signal, and message fields"
fi

# Test: Compiles from empty directory gracefully
test_case "handles empty directory (no frontmatter)"
EMPTY_DIR=$(mktemp -d)
TEMP_OUT2=$(mktemp)
node "$COMPILE_SCRIPT" --source "$EMPTY_DIR" --output "$TEMP_OUT2" 2>/dev/null
EMPTY_COUNT=$(node -e "const r=JSON.parse(require('fs').readFileSync('$TEMP_OUT2','utf8')); console.log(r.triggers.length)" 2>/dev/null)
if [ "$EMPTY_COUNT" = "0" ]; then
  test_pass
else
  test_fail "Empty directory should produce 0 triggers"
fi
rm -rf "$EMPTY_DIR" "$TEMP_OUT2"

# Test: Handles command files without frontmatter
test_case "skips commands without frontmatter"
PARTIAL_DIR=$(mktemp -d)
echo "# No Frontmatter Command" > "$PARTIAL_DIR/no-fm.md"
cat > "$PARTIAL_DIR/with-fm.md" << 'YAMLEOF'
---
suggest_when:
  - signal: total_tool_calls
    value: 10
    cooldown: 15
    message: "Test message"
---
# With Frontmatter
YAMLEOF
TEMP_OUT3=$(mktemp)
node "$COMPILE_SCRIPT" --source "$PARTIAL_DIR" --output "$TEMP_OUT3" 2>/dev/null
PARTIAL_COUNT=$(node -e "const r=JSON.parse(require('fs').readFileSync('$TEMP_OUT3','utf8')); console.log(r.triggers.length)" 2>/dev/null)
if [ "$PARTIAL_COUNT" = "1" ]; then
  test_pass
else
  test_fail "Should compile 1 trigger from mixed directory, got $PARTIAL_COUNT"
fi
rm -rf "$PARTIAL_DIR" "$TEMP_OUT3"

rm -f "$TEMP_OUT"

# ============================================================================
# Test suggest-actions.js
# ============================================================================

test_start "suggest-actions.js Tests"

SUGGEST_HOOK="$HOOKS_DIR/scripts/suggest-actions.js"

# Clean up any existing state for test isolation
ORIG_SESSION_ID="${CLAUDE_SESSION_ID:-}"
export CLAUDE_SESSION_ID="test-suggest-$$"

cleanup_suggest_state() {
  node -e "
    const os = require('os');
    const fs = require('fs');
    const prefix = os.tmpdir() + '/claude-suggest-state-';
    try {
      fs.readdirSync(os.tmpdir())
        .filter(f => f.startsWith('claude-suggest-state-test-suggest'))
        .forEach(f => fs.unlinkSync(os.tmpdir() + '/' + f));
    } catch {}
  " 2>/dev/null || true
  export CLAUDE_SESSION_ID="$ORIG_SESSION_ID"
}

# Test: Hook exits 0 on basic Edit input
test_case "exits 0 on Edit input"
run_node_hook "$SUGGEST_HOOK" "$(cat "$FIXTURES_DIR/edit-typescript.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Should always exit 0"

# Test: Hook exits 0 on Bash input
test_case "exits 0 on Bash input"
run_node_hook "$SUGGEST_HOOK" "$(cat "$FIXTURES_DIR/bash-npm-install.json")"
assert_exit_code 0 "$HOOK_EXIT_CODE" "Should always exit 0"

# Test: No suggestion on first edit (below threshold)
test_case "no suggestion on first few edits"
cleanup_suggest_state
export CLAUDE_SESSION_ID="test-suggest-$$"
run_node_hook "$SUGGEST_HOOK" '{"tool_name":"Edit","tool_input":{"file_path":"/project/src/app.ts","old_string":"a","new_string":"b"}}'
assert_not_contains "$HOOK_OUTPUT" "[suggest]" "Should not suggest below threshold"

# Test: Suggestion appears after threshold edits
test_case "suggests /create-commit after 8+ edits"
cleanup_suggest_state
export CLAUDE_SESSION_ID="test-suggest-threshold-$$"
ALL_OUTPUT=""
# Simulate 9 edits — suggestion should fire on the 8th (when threshold met)
for i in $(seq 1 9); do
  run_node_hook "$SUGGEST_HOOK" "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"/project/src/file$i.ts\",\"old_string\":\"a\",\"new_string\":\"b\"}}"
  ALL_OUTPUT="${ALL_OUTPUT}${HOOK_OUTPUT}"
done
if [[ "$ALL_OUTPUT" == *"[suggest]"* ]]; then
  test_pass
else
  test_fail "Should suggest after reaching edit threshold"
fi
# Clean up using Node to resolve correct tmpdir
node -e "require('fs').unlinkSync(require('os').tmpdir() + '/claude-suggest-state-test-suggest-threshold-$$.json')" 2>/dev/null || true

# Test: Git commit resets edit counter
test_case "git commit resets edits_since_commit"
cleanup_suggest_state
export CLAUDE_SESSION_ID="test-suggest-reset-$$"
# Simulate 5 edits
for i in $(seq 1 5); do
  run_node_hook "$SUGGEST_HOOK" "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"/project/src/file$i.ts\",\"old_string\":\"a\",\"new_string\":\"b\"}}"
done
# Simulate git commit
run_node_hook "$SUGGEST_HOOK" '{"tool_name":"Bash","tool_input":{"command":"git commit -m \"test\""}}'
# Check state was reset — use Node to find the correct tmpdir path
EDITS=$(node -e "
  const os = require('os');
  const fs = require('fs');
  const p = os.tmpdir() + '/claude-suggest-state-test-suggest-reset-$$.json';
  try {
    const s = JSON.parse(fs.readFileSync(p, 'utf8'));
    console.log(s.edits_since_commit);
  } catch { console.log('ERROR'); }
" 2>/dev/null)
if [ "$EDITS" = "0" ]; then
  test_pass
else
  test_fail "edits_since_commit should be 0 after git commit, got $EDITS"
fi
node -e "require('fs').unlinkSync(require('os').tmpdir() + '/claude-suggest-state-test-suggest-reset-$$.json')" 2>/dev/null || true

# Test: Handles missing registry gracefully
test_case "handles missing registry gracefully"
cleanup_suggest_state
export CLAUDE_SESSION_ID="test-suggest-no-registry-$$"
# Temporarily rename the registry
REGISTRY="$HOOKS_DIR/scripts/suggest-triggers.json"
if [ -f "$REGISTRY" ]; then
  mv "$REGISTRY" "${REGISTRY}.bak"
fi
run_node_hook "$SUGGEST_HOOK" '{"tool_name":"Edit","tool_input":{"file_path":"/project/src/app.ts","old_string":"a","new_string":"b"}}'
assert_exit_code 0 "$HOOK_EXIT_CODE" "Should exit 0 even without registry"
# Restore registry
if [ -f "${REGISTRY}.bak" ]; then
  mv "${REGISTRY}.bak" "$REGISTRY"
fi
node -e "require('fs').unlinkSync(require('os').tmpdir() + '/claude-suggest-state-test-suggest-no-registry-$$.json')" 2>/dev/null || true

# Test: Handles corrupt state file gracefully
test_case "handles corrupt state file gracefully"
export CLAUDE_SESSION_ID="test-suggest-corrupt-$$"
node -e "require('fs').writeFileSync(require('os').tmpdir() + '/claude-suggest-state-test-suggest-corrupt-$$.json', 'not json')" 2>/dev/null
run_node_hook "$SUGGEST_HOOK" '{"tool_name":"Edit","tool_input":{"file_path":"/project/src/app.ts","old_string":"a","new_string":"b"}}'
assert_exit_code 0 "$HOOK_EXIT_CODE" "Should exit 0 with corrupt state"
node -e "require('fs').unlinkSync(require('os').tmpdir() + '/claude-suggest-state-test-suggest-corrupt-$$.json')" 2>/dev/null || true

# Test: Tracks file extensions
test_case "tracks file extensions for .tsx edits"
cleanup_suggest_state
export CLAUDE_SESSION_ID="test-suggest-ext-$$"
for i in $(seq 1 4); do
  run_node_hook "$SUGGEST_HOOK" "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"/project/src/Component$i.tsx\",\"old_string\":\"a\",\"new_string\":\"b\"}}"
done
TSX_COUNT=$(node -e "
  const os = require('os');
  const fs = require('fs');
  const p = os.tmpdir() + '/claude-suggest-state-test-suggest-ext-$$.json';
  try {
    const s = JSON.parse(fs.readFileSync(p, 'utf8'));
    console.log(s.extension_counts['.tsx'] || 0);
  } catch { console.log('ERROR'); }
" 2>/dev/null)
if [ "$TSX_COUNT" = "4" ]; then
  test_pass
else
  test_fail "Should track 4 .tsx edits, got $TSX_COUNT"
fi
node -e "require('fs').unlinkSync(require('os').tmpdir() + '/claude-suggest-state-test-suggest-ext-$$.json')" 2>/dev/null || true

# Test: Handles empty stdin
test_case "handles empty stdin"
cleanup_suggest_state
export CLAUDE_SESSION_ID="test-suggest-empty-$$"
run_node_hook "$SUGGEST_HOOK" ""
assert_exit_code 0 "$HOOK_EXIT_CODE" "Should exit 0 with empty stdin"
node -e "require('fs').unlinkSync(require('os').tmpdir() + '/claude-suggest-state-test-suggest-empty-$$.json')" 2>/dev/null || true

# Cleanup
cleanup_suggest_state

# ============================================================================
# Summary
# ============================================================================

test_summary
