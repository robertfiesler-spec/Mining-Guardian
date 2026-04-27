#!/usr/bin/env bash
# =============================================================================
# Tests for scripts/seed_catalog.sh (C4)
# =============================================================================
# These tests exercise pre-flight validation paths that don't require a real
# Postgres connection. The full happy-path test ran in PR #13 against a live
# Postgres 17 sandbox and is documented in the PR body.
#
# Run with:
#   bash scripts/tests/test_seed_catalog.sh
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEED_RUNNER="$(cd "${SCRIPT_DIR}/.." && pwd)/seed_catalog.sh"

PASS=0
FAIL=0

check() {
    local name="$1"
    local expected="$2"
    local actual="$3"
    if [[ "$expected" == "$actual" ]]; then
        echo "  PASS: $name"
        PASS=$((PASS+1))
    else
        echo "  FAIL: $name (expected=$expected actual=$actual)"
        FAIL=$((FAIL+1))
    fi
}

echo "Test 1: missing MG_DB_PASSWORD exits 2"
( unset MG_DB_PASSWORD; "$SEED_RUNNER" >/dev/null 2>&1 )
check "exit code" 2 "$?"

echo "Test 2: --help exits 0"
"$SEED_RUNNER" --help >/dev/null 2>&1
check "exit code" 0 "$?"

echo "Test 3: unknown flag exits 2"
MG_DB_PASSWORD=test "$SEED_RUNNER" --bogus >/dev/null 2>&1
check "exit code" 2 "$?"

echo "Test 4: seed file path resolves to repo root"
SEED_PATH="$(cd "${SCRIPT_DIR}/../.." && pwd)/intelligence-catalog/seed-data/seed_miner_models.sql"
if [[ -f "$SEED_PATH" ]]; then
    check "seed file exists at expected path" "yes" "yes"
else
    check "seed file exists at expected path" "yes" "no"
fi

echo "Test 5: script is executable"
if [[ -x "$SEED_RUNNER" ]]; then
    check "executable bit set" "yes" "yes"
else
    check "executable bit set" "yes" "no"
fi

echo "Test 6: missing psql exits 2 (when password set)"
# Simulate by building a clean PATH with only bash available (no psql).
# We resolve bash's actual path, then put a symlink to it in a tmp dir,
# and use that tmp dir as the entire PATH for the child invocation.
BASH_BIN="$(command -v bash)"
TMP_PATH_DIR="$(mktemp -d)"
ln -s "$BASH_BIN" "$TMP_PATH_DIR/bash"
( export MG_DB_PASSWORD=test PATH="$TMP_PATH_DIR"; "$BASH_BIN" "$SEED_RUNNER" >/dev/null 2>&1 )
check "exit code without psql" 2 "$?"
rm -rf "$TMP_PATH_DIR"

echo ""
echo "Results: $PASS passed, $FAIL failed"
exit $FAIL
