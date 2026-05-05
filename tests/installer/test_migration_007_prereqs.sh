#!/usr/bin/env bash
# tests/installer/test_migration_007_prereqs.sh
#
# P-023 — Migration 007 layer-2 resolver prerequisite guards.
#
# Background: 007_layer2_resolver.sql was relocated from
# `mg_import_tool/sql/migrations/002_layer2_and_learning_foundation.sql`
# (D-20 reconciliation, P-004) into the canonical operational migrations
# chain. The importer-side original ran against the catalog DB, where its
# prerequisites — the `uuid-ossp` extension, `public.set_updated_at()`, and
# the `hardware.miner_models` / `pool.mining_pools` FK target tables — are
# created by `intelligence-catalog/seed-data/intelligence_catalog_schema.sql`.
# The operational DB `mining_guardian` has none of those, so on the customer
# Mac mini install, 007 hard-failed at:
#
#   ERROR: function uuid_generate_v4() does not exist
#   [postinstall] FATAL (32) migration 007_layer2_resolver.sql failed
#
# Fix landed in `migrations/006a_layer2_prereqs.sql` (P-023): the new
# migration runs lexically between 006 and 007, creates the extensions,
# `set_updated_at()`, and FK-target stub schemas/tables, and is fully
# idempotent.
#
# This test guards three things, all static (no Postgres needed for §1-§3):
#
#   §1  006a_layer2_prereqs.sql exists and parses (basic file presence
#       + a small syntactic sanity check).
#
#   §2  EVERY migration that uses `uuid_generate_v4()` is preceded
#       (lexically, in the same `migrations/*.sql` glob applied by
#       `step_apply_migrations`) by a migration that runs
#       `CREATE EXTENSION IF NOT EXISTS "uuid-ossp"`. Catches the future
#       regression where a fresh migration adds `uuid_generate_v4()` calls
#       without ensuring the extension is present (or where 006a is
#       deleted/renamed).
#
#   §3  EVERY migration that calls `EXECUTE FUNCTION set_updated_at()` is
#       preceded by a migration that defines the function. Same regression
#       class as §2, different missing prerequisite.
#
#   §4  EVERY migration that declares `REFERENCES hardware.miner_models(id)`
#       or `REFERENCES pool.mining_pools(id)` is preceded by a migration
#       that creates those FK target tables in the operational DB.
#
#   §5  006a header references P-023 (audit marker for future readers).
#
#   §6  postinstall.sh `step_apply_migrations` still globs
#       `<payload>/migrations/*.sql` (no hand-picked subset), so 006a is
#       picked up automatically. (Mirrors the equivalent guard in
#       `test_d20_importer_payload_reconciliation.sh §10`, but framed as a
#       P-023 regression: a future refactor that hand-picks 006/007 would
#       skip 006a and the bug would recur.)
#
#   §7  RUNTIME — if `psql` is on PATH AND `MG_RUN_PG_TESTS=1` is set,
#       create a throwaway database and apply every `migrations/*.sql` in
#       lexical order with `-v ON_ERROR_STOP=1`. Mirrors the customer Mac
#       mini install path. This is opt-in because a bare CI runner usually
#       won't have a Postgres cluster up; the static checks (§1-§6) carry
#       the regression coverage by default.
#
# Run from repo root:
#     bash tests/installer/test_migration_007_prereqs.sh
#
# Optional, with Postgres:
#     MG_RUN_PG_TESTS=1 bash tests/installer/test_migration_007_prereqs.sh
#
# Exits 0 on success, non-zero on first failed assertion.
# Requires: bash, grep, awk. shellcheck optional. psql optional (for §7).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PREREQS="migrations/006a_layer2_prereqs.sql"
RESOLVER="migrations/007_layer2_resolver.sql"
POSTINSTALL="installer/macos-pkg/scripts/postinstall.sh"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }
section() { echo; echo "## $*"; }

# Return the lexically-sorted basename list of migrations as a bash array.
_migration_basenames() {
    local f
    for f in migrations/*.sql; do
        [[ -f "$f" ]] || continue
        basename "$f"
    done | sort
}

# Returns 0 if migration $1 (basename) lexically precedes migration $2.
_lex_before() {
    [[ "$1" < "$2" ]]
}

# ---------------------------------------------------------------------
section "1. 006a_layer2_prereqs.sql exists and parses"
# ---------------------------------------------------------------------
if [[ -r "$PREREQS" ]]; then
    ok "$PREREQS present"
else
    fail "$PREREQS missing — P-023 fix not in place"
fi

# Postgres SQL is not bash, so we can't `bash -n` it; do a trivial
# balanced-BEGIN/COMMIT check (006a wraps its body in a single
# transaction, just like 007).
if [[ -r "$PREREQS" ]]; then
    begin_count=$(/usr/bin/grep -cE '^BEGIN[[:space:]]*;[[:space:]]*$' "$PREREQS" || true)
    commit_count=$(/usr/bin/grep -cE '^COMMIT[[:space:]]*;[[:space:]]*$' "$PREREQS" || true)
    if [[ "$begin_count" == "1" && "$commit_count" == "1" ]]; then
        ok "$PREREQS body is wrapped in a single BEGIN/COMMIT pair"
    else
        fail "$PREREQS BEGIN=${begin_count} COMMIT=${commit_count} — expected 1/1"
    fi
fi

# ---------------------------------------------------------------------
section "2. uuid_generate_v4() callers are preceded by uuid-ossp creator"
# ---------------------------------------------------------------------
# Build the list of migrations that USE uuid_generate_v4(), and the list
# of migrations that CREATE the extension. For every user, assert at
# least one creator lexically precedes it (or equals it — same file
# providing both is fine).
_collect_users() {
    local pattern="$1"
    local f
    for f in migrations/*.sql; do
        [[ -f "$f" ]] || continue
        if /usr/bin/grep -vE '^[[:space:]]*--' "$f" | /usr/bin/grep -qE "$pattern"; then
            basename "$f"
        fi
    done | sort
}
mapfile -t uuid_users < <(_collect_users 'uuid_generate_v4[[:space:]]*\(')
mapfile -t uuid_creators < <(/usr/bin/grep -lE 'CREATE[[:space:]]+EXTENSION[[:space:]]+IF[[:space:]]+NOT[[:space:]]+EXISTS[[:space:]]+"?uuid-ossp"?' migrations/*.sql 2>/dev/null | xargs -n1 basename | sort)

if [[ "${#uuid_users[@]}" -eq 0 ]]; then
    ok "no migration uses uuid_generate_v4() — nothing to guard"
else
    if [[ "${#uuid_creators[@]}" -eq 0 ]]; then
        fail "${#uuid_users[@]} migration(s) call uuid_generate_v4() but NO migration creates the uuid-ossp extension"
    else
        for user in "${uuid_users[@]}"; do
            covered=0
            for creator in "${uuid_creators[@]}"; do
                if [[ "$creator" < "$user" || "$creator" == "$user" ]]; then
                    covered=1
                    break
                fi
            done
            if [[ "$covered" == "1" ]]; then
                ok "$user uuid_generate_v4() callers covered by an earlier/same uuid-ossp creator"
            else
                fail "$user calls uuid_generate_v4() but no migration <= $user creates the uuid-ossp extension — fresh-DB install will hard-fail like P-023"
            fi
        done
    fi
fi

# ---------------------------------------------------------------------
section "3. set_updated_at() trigger users are preceded by a function definer"
# ---------------------------------------------------------------------
mapfile -t setupd_users < <(_collect_users 'EXECUTE[[:space:]]+FUNCTION[[:space:]]+(public\.)?set_updated_at[[:space:]]*\(')
mapfile -t setupd_definers < <(/usr/bin/grep -lE 'CREATE[[:space:]]+(OR[[:space:]]+REPLACE[[:space:]]+)?FUNCTION[[:space:]]+(public\.)?set_updated_at[[:space:]]*\(' migrations/*.sql 2>/dev/null | xargs -n1 basename | sort)

if [[ "${#setupd_users[@]}" -eq 0 ]]; then
    ok "no migration calls EXECUTE FUNCTION set_updated_at() — nothing to guard"
else
    if [[ "${#setupd_definers[@]}" -eq 0 ]]; then
        fail "${#setupd_users[@]} migration(s) reference set_updated_at() but NO migration defines it"
    else
        for user in "${setupd_users[@]}"; do
            covered=0
            for definer in "${setupd_definers[@]}"; do
                if [[ "$definer" < "$user" || "$definer" == "$user" ]]; then
                    covered=1
                    break
                fi
            done
            if [[ "$covered" == "1" ]]; then
                ok "$user EXECUTE FUNCTION set_updated_at() covered by an earlier/same definer"
            else
                fail "$user calls EXECUTE FUNCTION set_updated_at() but no migration <= $user defines it — install will hard-fail"
            fi
        done
    fi
fi

# ---------------------------------------------------------------------
section "4. FK targets hardware.miner_models / pool.mining_pools precede their users"
# ---------------------------------------------------------------------
for fk_target in 'hardware\.miner_models' 'pool\.mining_pools'; do
    pretty="${fk_target//\\\./.}"
    # Match the FK only on real (non-comment) lines so prose like
    # `-- REFERENCES hardware.miner_models(id)` in a header doesn't count.
    fk_user_files=()
    for f in migrations/*.sql; do
        [[ -f "$f" ]] || continue
        if /usr/bin/grep -vE '^[[:space:]]*--' "$f" \
                | /usr/bin/grep -qE "REFERENCES[[:space:]]+${fk_target}[[:space:]]*\("; then
            fk_user_files+=("$(basename "$f")")
        fi
    done
    mapfile -t fk_users < <(printf '%s\n' "${fk_user_files[@]}" | sort)
    # FK target tables are created by either:
    #   (a) `CREATE TABLE [IF NOT EXISTS] <fully qualified target> (...)`, or
    #   (b) `CREATE TABLE [IF NOT EXISTS] <unqualified> ...` after a
    #       `SET search_path` to the right schema — we only support (a)
    #       in canonical migrations, which is what 006a uses.
    mapfile -t fk_creators < <(/usr/bin/grep -lE "CREATE[[:space:]]+TABLE[[:space:]]+(IF[[:space:]]+NOT[[:space:]]+EXISTS[[:space:]]+)?${fk_target}[[:space:]]*\(" migrations/*.sql 2>/dev/null | xargs -n1 basename | sort)

    if [[ "${#fk_users[@]}" -eq 0 ]]; then
        ok "no migration references ${pretty} — nothing to guard"
        continue
    fi
    if [[ "${#fk_creators[@]}" -eq 0 ]]; then
        fail "${#fk_users[@]} migration(s) reference ${pretty} but NO migration creates that table"
        continue
    fi
    for user in "${fk_users[@]}"; do
        covered=0
        for creator in "${fk_creators[@]}"; do
            if [[ "$creator" < "$user" || "$creator" == "$user" ]]; then
                covered=1; break
            fi
        done
        if [[ "$covered" == "1" ]]; then
            ok "$user FK to ${pretty} covered by an earlier/same creator"
        else
            fail "$user references ${pretty} but no migration <= $user creates it — install will hard-fail"
        fi
    done
done

# ---------------------------------------------------------------------
section "5. P-023 audit marker present in 006a header"
# ---------------------------------------------------------------------
if [[ -r "$PREREQS" ]] && /usr/bin/grep -qE 'P-023' "$PREREQS"; then
    ok "$PREREQS references P-023"
else
    fail "$PREREQS missing P-023 audit marker — future readers won't trace this migration to the install bug"
fi

# ---------------------------------------------------------------------
section "6. postinstall.sh step_apply_migrations still globs *.sql"
# ---------------------------------------------------------------------
if [[ -r "$POSTINSTALL" ]]; then
    apply_body="$(/usr/bin/awk '/^step_apply_migrations\(\)/,/^}/' "$POSTINSTALL")"
    if /usr/bin/grep -qE '\*\.sql' <<<"$apply_body"; then
        ok "step_apply_migrations glob is *.sql (006a will be picked up automatically)"
    else
        fail "step_apply_migrations no longer globs *.sql — hand-picked subset would skip 006a"
    fi
else
    fail "$POSTINSTALL missing"
fi

# ---------------------------------------------------------------------
section "7. RUNTIME — fresh-DB end-to-end apply (opt-in)"
# ---------------------------------------------------------------------
if [[ "${MG_RUN_PG_TESTS:-0}" != "1" ]]; then
    echo "  SKIP — set MG_RUN_PG_TESTS=1 with psql on PATH to enable this section"
elif ! command -v psql >/dev/null 2>&1; then
    echo "  SKIP — psql not on PATH"
else
    db="mg_p023_$(date +%s)_$$"
    pg_super="${MG_PG_SUPERUSER:-postgres}"
    pg_runas="${MG_PG_RUNAS:-postgres}"
    sudo_cmd=""
    if [[ "$(/usr/bin/id -un)" != "$pg_runas" ]]; then
        sudo_cmd="sudo -u $pg_runas"
    fi

    echo "  INFO — using throwaway DB $db (super=$pg_super, runas=$pg_runas)"
    if $sudo_cmd psql -U "$pg_super" -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"$db\";" >/dev/null 2>&1; then
        ok "throwaway DB $db created"
        runtime_failed=0
        for sql in migrations/*.sql; do
            if ! $sudo_cmd psql -U "$pg_super" -d "$db" -v ON_ERROR_STOP=1 -f "$sql" >/dev/null 2>&1; then
                fail "migration $(basename "$sql") failed against fresh DB"
                runtime_failed=1
                break
            fi
        done
        if [[ "$runtime_failed" == "0" ]]; then
            ok "all migrations applied cleanly on fresh DB (mirrors customer Mac mini install path)"
        fi
        # Verify the four post-conditions P-023 explicitly bootstraps.
        check() {
            local label="$1"; shift
            if $sudo_cmd psql -U "$pg_super" -d "$db" -tAc "$1" 2>/dev/null | /usr/bin/grep -qE "$2"; then
                ok "post-apply state: $label"
            else
                fail "post-apply state: $label"
            fi
        }
        check "uuid-ossp extension installed" \
              "SELECT extname FROM pg_extension WHERE extname='uuid-ossp';" \
              '^uuid-ossp$'
        check "set_updated_at() function defined" \
              "SELECT proname FROM pg_proc WHERE proname='set_updated_at';" \
              '^set_updated_at$'
        check "hardware.miner_models exists" \
              "SELECT to_regclass('hardware.miner_models')::text;" \
              '^hardware\.miner_models$'
        check "pool.mining_pools exists" \
              "SELECT to_regclass('pool.mining_pools')::text;" \
              '^pool\.mining_pools$'
        check "mg.* layer-2 resolver tables exist" \
              "SELECT count(*) FROM information_schema.tables WHERE table_schema='mg' AND table_name IN ('model_family_aliases','unresolved_models','rma_records','dormant_miners','pool_observations');" \
              '^5$'
        # Re-apply 006a + 007 to confirm idempotency.
        if $sudo_cmd psql -U "$pg_super" -d "$db" -v ON_ERROR_STOP=1 -f "$PREREQS" >/dev/null 2>&1 \
           && $sudo_cmd psql -U "$pg_super" -d "$db" -v ON_ERROR_STOP=1 -f "$RESOLVER" >/dev/null 2>&1; then
            ok "006a + 007 are idempotent on re-apply"
        else
            fail "006a + 007 re-apply failed — idempotency contract broken"
        fi
        $sudo_cmd psql -U "$pg_super" -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE \"$db\";" >/dev/null 2>&1 || true
    else
        echo "  SKIP — could not create throwaway DB (psql/super-user setup mismatch)"
    fi
fi

# ---------------------------------------------------------------------
section "Summary"
# ---------------------------------------------------------------------
echo "  $pass_count passed, $fail_count failed"
if [[ "$fail_count" -gt 0 ]]; then
    exit 1
fi
exit 0
