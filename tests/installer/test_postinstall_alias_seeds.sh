#!/usr/bin/env bash
# tests/installer/test_postinstall_alias_seeds.sh
#
# P-018D — postinstall.sh + seed-file static checks for the alias seed
# apply step. Asserts:
#
#   1. The two alias seed files live under
#      intelligence-catalog/seed-data/aliases/ (NOT under mg_import_tool/
#      where they would violate D-20).
#   2. The Tier-1 seed's ON CONFLICT clause matches the canonical UNIQUE
#      constraint on hardware.model_aliases (i.e. (miner_model_id, alias)
#      per N6 / 2026-04-27, NOT alias_normalized which would hard-fail
#      at apply).
#   3. postinstall.sh defines step_apply_alias_seeds and wires it into
#      the main install flow between catalog seed and ollama install.
#   4. step_apply_alias_seeds applies Tier-1 against the catalog DB and
#      Tier-2 against the operational DB.
#   5. Exit code 42 is reserved for alias-seed apply failures and is
#      documented in the header. No collision with the other 4x codes.
#   6. Idempotency: every INSERT row in both seeds carries an
#      ON CONFLICT … DO NOTHING clause.
#   7. D-20: zero references to mg_import_tool/sql/seed/ remain in the
#      tree (those files moved to intelligence-catalog/seed-data/aliases).
#
# Source-tree static checks only — no live psql, no Mac, no Installer.app.
# The full end-to-end check belongs in the v1.0.3 verification gate
# ("clean macOS VM") and the operator verification commands in the
# P-018D handoff.
#
# Run from repo root:
#     bash tests/installer/test_postinstall_alias_seeds.sh
#
# Exits 0 on success, non-zero on first failed assertion summary.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

POSTINSTALL="installer/macos-pkg/scripts/postinstall.sh"
BUILD_PKG="installer/macos-pkg/scripts/build_pkg.sh"
TIER1_SEED="intelligence-catalog/seed-data/aliases/001_hardware_model_aliases_tier1.sql"
TIER2_SEED="intelligence-catalog/seed-data/aliases/002_mg_family_aliases_tier2.sql"

pass_count=0
fail_count=0
ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }
section() { echo; echo "## $*"; }


# ---------------------------------------------------------------------
section "1. Source files exist at the customer-payload-safe location"
# ---------------------------------------------------------------------
for f in "$POSTINSTALL" "$BUILD_PKG" "$TIER1_SEED" "$TIER2_SEED"; do
    if [[ -r "$f" ]]; then
        ok "$f present"
    else
        fail "$f missing"
    fi
done

if [[ -d intelligence-catalog/seed-data/aliases ]]; then
    ok "intelligence-catalog/seed-data/aliases/ directory present"
else
    fail "intelligence-catalog/seed-data/aliases/ missing"
fi


# ---------------------------------------------------------------------
section "2. Tier-1 seed ON CONFLICT clause matches the schema"
# ---------------------------------------------------------------------
# The actual UNIQUE constraint on hardware.model_aliases is
# (miner_model_id, alias) per intelligence-catalog/seed-data/
# intelligence_catalog_schema.sql line 897 (N6, 2026-04-27). The
# pre-P-018D seed used `ON CONFLICT (alias_normalized)` which would
# hard-fail at apply because no such constraint exists.

bad_count="$(grep -c 'ON CONFLICT (alias_normalized) DO NOTHING' "$TIER1_SEED" || true)"
if [[ "$bad_count" -eq 0 ]]; then
    ok "Tier-1 seed has no ON CONFLICT (alias_normalized) rows"
else
    fail "Tier-1 seed still has ${bad_count} ON CONFLICT (alias_normalized) row(s) — pre-P-018D shape"
fi

good_count="$(grep -c 'ON CONFLICT (miner_model_id, alias) DO NOTHING' "$TIER1_SEED" || true)"
if [[ "$good_count" -ge 12000 ]]; then
    ok "Tier-1 seed has ${good_count} ON CONFLICT (miner_model_id, alias) rows (>= 12000 floor)"
else
    fail "Tier-1 seed has ${good_count} ON CONFLICT (miner_model_id, alias) rows (expected >= 12000)"
fi

# Also confirm the catalog schema's UNIQUE constraint hasn't drifted
# back to alias_normalized (which would make our fix wrong). Pull the
# whole CREATE TABLE block (terminated by the closing `);` line) out
# of the schema and grep inside it.
schema_file="intelligence-catalog/seed-data/intelligence_catalog_schema.sql"
schema_block="$(awk '/^CREATE TABLE hardware\.model_aliases/{flag=1} flag{print} flag && /^\);/{exit}' "$schema_file")"
if echo "$schema_block" | grep -qE 'UNIQUE \(miner_model_id, alias\)' ; then
    ok "schema confirms UNIQUE (miner_model_id, alias) on hardware.model_aliases"
else
    fail "schema's UNIQUE on hardware.model_aliases is NOT (miner_model_id, alias) — fix Tier-1 seed conflict clause"
fi


# ---------------------------------------------------------------------
section "3. postinstall.sh defines step_apply_alias_seeds and wires it"
# ---------------------------------------------------------------------
if grep -q '^step_apply_alias_seeds()' "$POSTINSTALL"; then
    ok "step_apply_alias_seeds() function defined"
else
    fail "step_apply_alias_seeds() function not defined in postinstall.sh"
fi

# The step must be invoked between the catalog-seed step and the
# ollama-install step in the main flow.
order_block="$(awk '/step_provision_catalog_db_and_seed/,/step_install_ollama_and_pull_model/' "$POSTINSTALL")"
if echo "$order_block" | grep -q 'step_apply_alias_seeds'; then
    ok "step_apply_alias_seeds wired between provision_catalog and install_ollama"
else
    fail "step_apply_alias_seeds is NOT invoked in the main install flow between catalog and ollama"
fi


# ---------------------------------------------------------------------
section "4. step_apply_alias_seeds targets the right DBs"
# ---------------------------------------------------------------------
fn_body="$(awk '/^step_apply_alias_seeds\(\)/,/^step_install_ollama_and_pull_model\(\)/' "$POSTINSTALL")"

# Tier-1 → mining_guardian_catalog
if echo "$fn_body" | grep -q '001_hardware_model_aliases_tier1.sql' && \
   echo "$fn_body" | grep -qE 'psql -U mg -d "?\$catalog_db"?'; then
    ok "Tier-1 applied to catalog DB"
else
    fail "Tier-1 not applied to catalog DB inside step_apply_alias_seeds"
fi

# Tier-2 → mining_guardian (operational)
if echo "$fn_body" | grep -q '002_mg_family_aliases_tier2.sql' && \
   echo "$fn_body" | grep -qE 'psql -U mg -d "?\$op_db"?'; then
    ok "Tier-2 applied to operational DB"
else
    fail "Tier-2 not applied to operational DB inside step_apply_alias_seeds"
fi

# Specifically — Tier-1 must NOT be applied to the operational DB and
# Tier-2 must NOT be applied to the catalog DB. This is the boundary
# guard the diagnostic flagged.
if echo "$fn_body" | grep -E 'tier1.*"\$op_db"|"\$op_db".*tier1' >/dev/null 2>&1; then
    fail "Tier-1 reaches the operational DB — wrong target"
else
    ok "Tier-1 is NOT applied to the operational DB"
fi
if echo "$fn_body" | grep -E 'tier2.*"\$catalog_db"|"\$catalog_db".*tier2' >/dev/null 2>&1; then
    fail "Tier-2 reaches the catalog DB — wrong target"
else
    ok "Tier-2 is NOT applied to the catalog DB"
fi


# ---------------------------------------------------------------------
section "5. Exit code 42 reserved + documented; no collision"
# ---------------------------------------------------------------------
# Header table must list 42.
if grep -qE '^#\s+42\s+— ' "$POSTINSTALL"; then
    ok "exit code 42 is documented in the header table"
else
    fail "exit code 42 not documented in the header"
fi

# Every fail call inside step_apply_alias_seeds uses 42, not 41/39.
if echo "$fn_body" | grep -qE 'fail (39|41|40) '; then
    fail "step_apply_alias_seeds uses a non-42 exit code (collides with another step)"
else
    ok "step_apply_alias_seeds uses exit code 42 exclusively"
fi

# The other meanings of 41 (customer-info conf) must still be there.
if grep -q 'fail 41 "customer-info Desktop conf' "$POSTINSTALL"; then
    ok "exit code 41 still reserved for customer-info Desktop conf"
else
    fail "customer-info Desktop conf no longer guarded by exit 41 — accidental collision?"
fi


# ---------------------------------------------------------------------
section "6. Idempotency: every seed INSERT carries ON CONFLICT"
# ---------------------------------------------------------------------
# Each INSERT line ends with the matching ON CONFLICT clause, so the
# floor for the conflict-clause count is the INSERT count. The header
# comment in the seed file may mention "ON CONFLICT" prose without an
# actual SQL clause, which is why we anchor the count to start-of-line
# `INSERT INTO`.

# Tier 1
t1_inserts="$(grep -c '^INSERT INTO hardware.model_aliases' "$TIER1_SEED" || true)"
t1_conflicts="$(grep -c 'ON CONFLICT (miner_model_id, alias) DO NOTHING' "$TIER1_SEED" || true)"
if [[ "$t1_inserts" -gt 0 ]] && [[ "$t1_conflicts" -ge "$t1_inserts" ]]; then
    ok "Tier-1: ${t1_inserts} INSERTs, ${t1_conflicts} ON CONFLICT clauses (>= floor)"
else
    fail "Tier-1: ${t1_inserts} INSERTs but only ${t1_conflicts} ON CONFLICT clauses"
fi

# Tier 2
t2_inserts="$(grep -c '^INSERT INTO mg.model_family_aliases' "$TIER2_SEED" || true)"
t2_conflicts="$(grep -c 'ON CONFLICT (alias_normalized) DO NOTHING' "$TIER2_SEED" || true)"
if [[ "$t2_inserts" -gt 0 ]] && [[ "$t2_conflicts" -ge "$t2_inserts" ]]; then
    ok "Tier-2: ${t2_inserts} INSERTs, ${t2_conflicts} ON CONFLICT clauses (>= floor)"
else
    fail "Tier-2: ${t2_inserts} INSERTs but only ${t2_conflicts} ON CONFLICT clauses"
fi


# ---------------------------------------------------------------------
section "7. D-20: no mg_import_tool/sql/seed/ paths remain in the repo"
# ---------------------------------------------------------------------
# The directory itself was removed by P-018D (files moved to the
# customer-payload-safe location).
if [[ -e mg_import_tool/sql/seed ]]; then
    fail "mg_import_tool/sql/seed/ still present — D-20 violation if anything reaches the customer payload"
else
    ok "mg_import_tool/sql/seed/ removed (alias seeds live at intelligence-catalog/seed-data/aliases/)"
fi

# Make sure no LIVE shell/python/SQL code reads from the old path.
# Documentation references (in comments / *.md) explaining the
# historical location are intentional and allowed — they protect
# future readers from re-introducing the wrong path. We flag only
# rsync / cp / psql -f / open() / Path() / shell-`cat`-style live
# uses of the literal.
live_refs="$(grep -rn --exclude-dir=.git --exclude-dir=archive \
    -E "(rsync|cp|psql -f|open\\()\\s*[\"']?[^\"' ]*mg_import_tool/sql/seed" \
    . 2>/dev/null || true)"
if [[ -z "$live_refs" ]]; then
    ok "no LIVE references to mg_import_tool/sql/seed/ (doc mentions are allowed)"
else
    echo "    live references found:" >&2
    echo "$live_refs" | head -5 >&2
    fail "live reference(s) to mg_import_tool/sql/seed/ remain — would reintroduce the path"
fi


# ---------------------------------------------------------------------
section "Summary"
# ---------------------------------------------------------------------
echo
echo "Passed: ${pass_count}"
echo "Failed: ${fail_count}"
if [[ "$fail_count" -gt 0 ]]; then
    exit 1
fi
echo "ALL OK"
