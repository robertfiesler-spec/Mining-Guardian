#!/usr/bin/env bash
# tests/installer/test_postinstall_catalog_seed.sh
#
# D-18 Gap 2 — postinstall.sh + build_pkg.sh static checks for the
# catalog DB + 320-row seed step.
#
# This test asserts that the catalog provisioning step is wired up
# correctly in the .pkg installer pipeline. It runs against the source
# tree only — no Mac, no Installer.app, no actual psql apply. The full
# end-to-end smoke test is the v1.0.3 verification gate per D-18
# ("clean macOS 14 VM").
#
# Run from repo root:
#     bash tests/installer/test_postinstall_catalog_seed.sh
#
# Exits 0 on success, non-zero on first failed assertion.
# Requires: bash, grep. shellcheck optional.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

POSTINSTALL="installer/macos-pkg/scripts/postinstall.sh"
BUILD_PKG="installer/macos-pkg/scripts/build_pkg.sh"
SEED_FILE="intelligence-catalog/seed-data/seed_miner_models.sql"
SCHEMA_FILE="intelligence-catalog/seed-data/deploy_schema.sql"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }

section() { echo; echo "## $*"; }

# ---------------------------------------------------------------------
section "1. Source files exist"
# ---------------------------------------------------------------------
for f in "$POSTINSTALL" "$BUILD_PKG" "$SEED_FILE" "$SCHEMA_FILE"; do
    if [[ -r "$f" ]]; then
        ok "$f present"
    else
        fail "$f missing"
    fi
done

# ---------------------------------------------------------------------
section "2. bash -n syntax check"
# ---------------------------------------------------------------------
if bash -n "$POSTINSTALL" 2>/dev/null; then
    ok "postinstall.sh parses"
else
    fail "postinstall.sh has bash syntax errors"
fi
if bash -n "$BUILD_PKG" 2>/dev/null; then
    ok "build_pkg.sh parses"
else
    fail "build_pkg.sh has bash syntax errors"
fi

# ---------------------------------------------------------------------
section "3. step_provision_catalog_db_and_seed defined and wired in"
# ---------------------------------------------------------------------
if /usr/bin/grep -q '^step_provision_catalog_db_and_seed()' "$POSTINSTALL"; then
    ok "step_provision_catalog_db_and_seed() defined"
else
    fail "step_provision_catalog_db_and_seed() missing — D-18 Gap 2 not implemented"
fi

# main() call ordering: step_apply_migrations → step_provision_catalog_db_and_seed
# → step_install_ollama_and_pull_model. The catalog must be seeded BEFORE
# Ollama pull because Ollama is the slow network step; failing the catalog
# seed early avoids waiting 5-15 minutes only to fail.
call_order="$(/usr/bin/awk '/^main\(\)/, /^}/' "$POSTINSTALL" \
    | /usr/bin/grep -oE 'step_(apply_migrations|provision_catalog_db_and_seed|install_ollama_and_pull_model)' \
    | /usr/bin/paste -sd, -)"
expected="step_apply_migrations,step_provision_catalog_db_and_seed,step_install_ollama_and_pull_model"
if [[ "$call_order" == "$expected" ]]; then
    ok "main() ordering: apply_migrations → provision_catalog_db_and_seed → install_ollama"
else
    fail "main() ordering wrong (got '$call_order', expected '$expected')"
fi

# ---------------------------------------------------------------------
section "4. Targets the catalog DB, not the operational DB"
# ---------------------------------------------------------------------
# Extract the function body so we can assert against it specifically.
body="$(/usr/bin/awk '/^step_provision_catalog_db_and_seed\(\)/,/^}/' "$POSTINSTALL")"

if /usr/bin/grep -q 'mining_guardian_catalog' <<<"$body"; then
    ok "function references mining_guardian_catalog"
else
    fail "function does not reference mining_guardian_catalog — wrong DB target"
fi

if /usr/bin/grep -qE 'CREATE DATABASE[[:space:]]+\${catalog_db}[[:space:]]+OWNER' <<<"$body"; then
    ok "function CREATEs the catalog DB with OWNER mg"
else
    fail "function does not CREATE DATABASE for the catalog (idempotent path may also be missing)"
fi

# Idempotency: the function must NOT issue an unconditional CREATE
# DATABASE — there must be a SELECT against pg_database before CREATE.
if /usr/bin/grep -q 'pg_database WHERE datname' <<<"$body"; then
    ok "function pre-checks pg_database before CREATE (idempotent)"
else
    fail "function missing existence check on pg_database — re-installs would fail"
fi

# ---------------------------------------------------------------------
section "5. Applies deploy_schema.sql AND seed_miner_models.sql"
# ---------------------------------------------------------------------
if /usr/bin/grep -q 'deploy_schema.sql' <<<"$body"; then
    ok "function applies deploy_schema.sql"
else
    fail "function does not reference deploy_schema.sql"
fi
if /usr/bin/grep -q 'seed_miner_models.sql' <<<"$body"; then
    ok "function applies seed_miner_models.sql"
else
    fail "function does not reference seed_miner_models.sql"
fi

# ---------------------------------------------------------------------
section "6. Verification gate: hardware.miner_models row count >= 320"
# ---------------------------------------------------------------------
if /usr/bin/grep -q 'SELECT count(\*) FROM hardware.miner_models' <<<"$body"; then
    ok "function verifies hardware.miner_models row count post-seed"
else
    fail "function does not verify the seed actually populated the table"
fi
if /usr/bin/grep -qE 'row_count.*320|320.*expected|320 rows' <<<"$body"; then
    ok "function asserts >= 320 rows (D-18 verification gate floor)"
else
    fail "function does not assert >= 320 rows post-seed"
fi

# ---------------------------------------------------------------------
section "7. Exit code 39 documented and used"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE '^#[[:space:]]+39[[:space:]]+—' "$POSTINSTALL"; then
    ok "exit code 39 documented in header"
else
    fail "exit code 39 not documented in postinstall header"
fi
if /usr/bin/grep -q 'fail 39 "' <<<"$body"; then
    ok "fail 39 used in step_provision_catalog_db_and_seed"
else
    fail "fail 39 not used — Gap 2 errors will report wrong exit code"
fi

# ---------------------------------------------------------------------
section "8. No network call (Vision Anchor 7)"
# ---------------------------------------------------------------------
# Catalog provisioning must NOT introduce a second install-time network
# call. Allowed outbound calls in postinstall today: the Ollama model
# pull only. The catalog-seed step talks to the localhost Colima
# Postgres container exclusively.
if /usr/bin/grep -qE '\bcurl\b|\bwget\b|https?://' <<<"$body"; then
    fail "step_provision_catalog_db_and_seed appears to make a network call — Vision Anchor 7 violated"
else
    ok "no curl/wget/http(s) URL inside catalog-seed step (Vision Anchor 7 honored)"
fi

# ---------------------------------------------------------------------
section "9. build_pkg.sh asserts catalog seed staged in payload"
# ---------------------------------------------------------------------
if /usr/bin/grep -q 'step 4g' "$BUILD_PKG"; then
    ok "build_pkg.sh has step 4g (catalog seed assertion)"
else
    fail "build_pkg.sh missing the 4g catalog-seed assertion"
fi
if /usr/bin/grep -q 'seed_miner_models.sql' "$BUILD_PKG" \
        && /usr/bin/grep -q 'deploy_schema.sql' "$BUILD_PKG"; then
    ok "build_pkg.sh references both seed_miner_models.sql and deploy_schema.sql"
else
    fail "build_pkg.sh does not reference both catalog files (incomplete assertion)"
fi
if /usr/bin/grep -qE '_die 44' "$BUILD_PKG"; then
    ok "build_pkg.sh reserves exit 44 for catalog-seed payload assertion failures"
else
    fail "build_pkg.sh missing exit 44 reservation for the 4g assertion"
fi

# ---------------------------------------------------------------------
section "10. Seed file row-count sanity (>= 320 INSERTs)"
# ---------------------------------------------------------------------
seed_inserts="$(/usr/bin/grep -cE '^INSERT INTO hardware\.miner_models' "$SEED_FILE" || true)"
if (( seed_inserts >= 320 )); then
    ok "seed_miner_models.sql has ${seed_inserts} INSERT rows (≥ 320)"
else
    fail "seed_miner_models.sql has ${seed_inserts} INSERT rows (< 320 — drift vs D-18 gate)"
fi

# ---------------------------------------------------------------------
section "11. shellcheck regression baseline (no NEW warnings)"
# ---------------------------------------------------------------------
# Same baseline policy as test_postinstall_venv.sh §3. Counting bumps
# allowed because Gap 2 adds a new step body — track new ceiling here.
if command -v shellcheck >/dev/null 2>&1; then
    pi_count="$(shellcheck "$POSTINSTALL" 2>&1 | /usr/bin/grep -cE '^In .* line [0-9]+:' || true)"
    bp_count="$(shellcheck "$BUILD_PKG"   2>&1 | /usr/bin/grep -cE '^In .* line [0-9]+:' || true)"
    # Gap 5 baseline was 3 / 5. Gap 2 adds new code; allow the same
    # ceiling and tighten if shellcheck reports zero new findings.
    if [[ "$pi_count" -le 3 ]]; then
        ok "postinstall.sh shellcheck warnings: ${pi_count} (≤ 3 baseline)"
    else
        fail "postinstall.sh shellcheck warnings: ${pi_count} (> 3 baseline — new warning introduced)"
    fi
    if [[ "$bp_count" -le 5 ]]; then
        ok "build_pkg.sh shellcheck warnings: ${bp_count} (≤ 5 baseline)"
    else
        fail "build_pkg.sh shellcheck warnings: ${bp_count} (> 5 baseline — new warning introduced)"
    fi
else
    echo "  SKIP — shellcheck not installed (install: \`brew install shellcheck\` or \`apt-get install shellcheck\`)"
fi

# ---------------------------------------------------------------------
section "Summary"
# ---------------------------------------------------------------------
echo
echo "Passed: $pass_count"
echo "Failed: $fail_count"
if (( fail_count > 0 )); then
    exit 1
fi
exit 0
