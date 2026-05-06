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
section "8. P-019B FK-safe staging apply"
# ---------------------------------------------------------------------
# 2026-05-06 install-day failure: Tier-1 alias seed apply hit FATAL (42)
# because the seed's frozen miner_model_id UUIDs do not match the live
# DB's randomly-generated UUIDs from seed_miner_models.sql. The fix
# (P-019B) stages the seed in a TEMP scratch table without the FK,
# then promotes only rows whose miner_model_id exists in the live
# hardware.miner_models. This section asserts the staging shim is
# present and shaped correctly.

# 8.1: function defines the scratch staging table.
if echo "$fn_body" | grep -qE 'CREATE TEMP TABLE _tier1_alias_seed_scratch'; then
    ok "Tier-1 staging table created (CREATE TEMP TABLE _tier1_alias_seed_scratch)"
else
    fail "step_apply_alias_seeds is missing the P-019B staging table CREATE TEMP TABLE"
fi

# 8.2: scratch table copies the real table's shape MINUS constraints.
if echo "$fn_body" | grep -qE 'LIKE hardware\.model_aliases.*EXCLUDING CONSTRAINTS'; then
    ok "scratch table inherits shape but excludes FK / UNIQUE constraints"
else
    fail "P-019B scratch table must use LIKE hardware.model_aliases ... EXCLUDING CONSTRAINTS"
fi

# 8.3: promote step has the FK-existence gate. The SQL spans multiple
# lines so we verify the relevant keywords appear in the function body
# (`WHERE EXISTS (` on one line, `SELECT 1 FROM hardware.miner_models`
# on the next).
if echo "$fn_body" | grep -qE 'WHERE EXISTS \(' \
        && echo "$fn_body" | grep -qE 'SELECT 1 FROM hardware\.miner_models'; then
    ok "Tier-1 promote step has the FK-existence gate (WHERE EXISTS …hardware.miner_models)"
else
    fail "P-019B promote step must filter by EXISTS (SELECT 1 FROM hardware.miner_models WHERE m.id = s.miner_model_id)"
fi

# 8.4: sed rewrite redirects the seed at the scratch table. The actual
# sed expression in postinstall.sh is
#   's/INSERT INTO hardware\.model_aliases/INSERT INTO _tier1_alias_seed_scratch/g'
# We use fixed-string grep (`-F`) to dodge regex-escaping confusion.
if echo "$fn_body" | grep -F -q 'INSERT INTO _tier1_alias_seed_scratch'; then
    ok "sed rewrite redirects the seed's INSERTs at the scratch table"
else
    fail "P-019B sed rewrite of seed INSERTs is missing"
fi

# 8.5: sed strips the seed's own BEGIN/COMMIT (the wrapper owns the
# transaction; nested BEGIN inside an open transaction is a NOTICE
# and second COMMIT closes the wrapper too early).
if echo "$fn_body" | grep -qE "/\\^BEGIN;\\\$/d" && \
   echo "$fn_body" | grep -qE "/\\^COMMIT;\\\$/d"; then
    ok "sed strips the seed's own BEGIN; / COMMIT; envelope"
else
    fail "P-019B must strip the seed's own BEGIN/COMMIT to avoid nested transactions"
fi

# 8.6: ON CONFLICT (miner_model_id, alias) DO NOTHING is preserved on
# the FINAL insert (real table) but stripped on the SCRATCH insert
# (no UNIQUE on the scratch).
if echo "$fn_body" | grep -qE "ON CONFLICT \\(miner_model_id, alias\\) DO NOTHING//g"; then
    ok "sed strips the seed's ON CONFLICT clause for the scratch insert"
else
    fail "P-019B must strip ON CONFLICT from scratch INSERTs (scratch has no UNIQUE)"
fi
# And the post-wrapper's INSERT into the real table re-adds ON CONFLICT.
if echo "$fn_body" | grep -qE 'INSERT INTO hardware\.model_aliases.*\n.*\n.*\n.*FROM _tier1_alias_seed_scratch'; then
    ok "post-wrapper INSERTs into hardware.model_aliases from scratch"
else
    # awk scan instead — multi-line grep is finicky.
    if awk '/INSERT INTO hardware\.model_aliases \(/,/ON CONFLICT \(miner_model_id, alias\) DO NOTHING/' "$POSTINSTALL" \
            | grep -q '_tier1_alias_seed_scratch'; then
        ok "post-wrapper INSERTs into hardware.model_aliases from _tier1_alias_seed_scratch"
    else
        fail "P-019B post-wrapper missing INSERT INTO hardware.model_aliases SELECT … FROM _tier1_alias_seed_scratch"
    fi
fi

# 8.7: ON COMMIT DROP — scratch table cleaned up at COMMIT.
if echo "$fn_body" | grep -q 'ON COMMIT DROP'; then
    ok "scratch table is ON COMMIT DROP (no manual cleanup needed)"
else
    fail "P-019B scratch table must use ON COMMIT DROP"
fi

# 8.8: Verify section now distinguishes ZERO (FATAL) from LOW (WARN).
# Three thresholds: 0, 100, 5000. We pull the whole step body and grep
# the `tier1_count` lines — easier than slicing around the awk range.
if echo "$fn_body" | grep -qE '"\$\{tier1_count:-0\}" -eq 0' \
        && echo "$fn_body" | grep -F -q 'fail 42 "Tier-1 alias seed verification failed: hardware.model_aliases has 0 rows'; then
    ok "verify: 0-row case aborts with FATAL (42)"
else
    fail "P-019B verify must FATAL on tier1_count == 0"
fi
if echo "$fn_body" | grep -qE '"\$\{tier1_count:-0\}" -lt 100'; then
    ok "verify: < 100 emits a clear ERROR-level WARN (drift detector)"
else
    fail "P-019B verify must WARN at tier1_count < 100"
fi
if echo "$fn_body" | grep -qE '"\$\{tier1_count:-0\}" -lt 5000'; then
    ok "verify: < 5000 emits an INFO partial-coverage note"
else
    fail "P-019B verify must distinguish partial coverage at < 5000"
fi

# 8.9: The seed FILE on disk is UNCHANGED — sed rewrite is at apply
# time only. This protects the seed file as canonical reference data.
if grep -q "^BEGIN;$" "$TIER1_SEED" && grep -q "^COMMIT;$" "$TIER1_SEED" \
       && grep -q "ON CONFLICT (miner_model_id, alias) DO NOTHING" "$TIER1_SEED"; then
    ok "seed file on disk preserves BEGIN; / COMMIT; / ON CONFLICT (canonical reference data)"
else
    fail "seed file on disk has been mutated — P-019B fix must NOT alter the seed source"
fi

# 8.10: Document the UUID-drift root cause. The seed file's
# miner_model_id values are 317 frozen UUIDs from a generator snapshot;
# seed_miner_models.sql uses uuid_generate_v4() and produces fresh
# random UUIDs at every install. This drift is the entire reason the
# staging shim exists. The header comment block must explain this so a
# future operator who regenerates the seed knows the correct fix is
# making seed_miner_models.sql deterministic — not patching the staging.
# `grep -oE` exits 1 on zero matches, which under `set -euo pipefail`
# kills the whole test. `|| true` swallows the no-match exit so the
# count comes back as `0` cleanly — exactly the value we want to
# assert against for seed_miner_models.sql (which has zero frozen
# UUIDs by design — every row uses uuid_generate_v4()).
seed_uuid_count="$( (grep -oE "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}" "$TIER1_SEED" || true) | sort -u | wc -l | tr -d ' ')"
miner_uuid_count="$( (grep -oE "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}" "intelligence-catalog/seed-data/seed_miner_models.sql" || true) | sort -u | wc -l | tr -d ' ')"
# Use [[ -gt / -eq ]] (not (( … ))) — under `set -e`, the (( N == 0 ))
# arithmetic test exits when the LITERAL VALUE is 0 (the actual case
# we want to assert here), defeating the test.
if [[ "${seed_uuid_count}" -gt 200 ]] && [[ "${miner_uuid_count}" -eq 0 ]]; then
    ok "drift confirmed: Tier-1 seed has ${seed_uuid_count} frozen UUIDs; seed_miner_models.sql has ${miner_uuid_count} (uuid_generate_v4 at runtime)"
else
    fail "drift assertion broken: Tier-1=${seed_uuid_count}, miner_models=${miner_uuid_count}; staging shim assumption may not hold"
fi

# 8.11: Header comment in step_apply_alias_seeds must mention P-019B
# so the next reader understands why the staging table exists.
if grep -E "P-019B|FK-safe|miner_model_id UUIDs" "$POSTINSTALL" \
        | grep -q "step_apply_alias_seeds\|P-019B (2026-05-06)\|frozen miner_model_id\|FK-safe staging"; then
    ok "step_apply_alias_seeds documents the P-019B staging shim"
else
    fail "step_apply_alias_seeds is missing the P-019B explanatory comment"
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
