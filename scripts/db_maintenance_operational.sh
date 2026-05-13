#!/bin/bash
# scripts/db_maintenance_operational.sh
#
# W14 Step 9c (2026-05-13) — per-instance VACUUM/ANALYZE for the
# OPERATIONAL Postgres container.
#
# Mining Guardian runs two Postgres containers on the Mini (W14, 2026-05-13):
#   - mining-guardian-db (operational) on 127.0.0.1:5432  — this script
#   - mg-catalog-db      (catalog)     on 127.0.0.1:5433  — see db_maintenance_catalog.sh
#
# Both are usually invoked via scripts/db_maintenance.sh (wrapper), which
# the scheduled launchd job calls. Run standalone for ad-hoc operational
# maintenance.
#
# History (P-038 #6, 2026-05-11):
#   Originally a single-DB script written for a Linux host with a native
#   `postgres` Unix user and `psql` on PATH. The Mac Mini deployment runs
#   Postgres inside a Docker container, so `sudo -u postgres psql` does
#   not work — there is no `postgres` Unix user on macOS. Rewritten
#   2026-05-11 to invoke psql via `docker exec`. Split into per-instance
#   scripts plus a wrapper on 2026-05-13 to mirror the D6 backup-script
#   pattern landed in W14 Step 9 (PR #204).
#
# Output flow:
#   This script writes ALL output to stdout/stderr. The LaunchDaemon
#   that schedules it (com.miningguardian.scheduled.db-maintenance) runs
#   through scheduled_job_launcher.sh, which captures stdout to
#   ${MG_INSTALL_ROOT}/logs/scheduled/db_maintenance.out.log and stderr
#   to db_maintenance.err.log. No /var/log/ writes; the launcher's
#   canonical Mac log location is the single source of truth.
#
# Failure handling:
#   `set -e` is intentionally NOT used. Each step has explicit per-command
#   error handling so one step's failure does not silently abort the rest
#   (and so the operator sees the failed step name on stderr instead of an
#   empty .err.log). A counter tracks failures and the script exits non-
#   zero at the end if any step failed, so the launcher's .last-run.json
#   stamps exit_code=1 and the operator sees something is off.
#
# Container / DB identity:
#   Hardcoded — these names are deployment identities baked into the
#   .pkg install layout, not env-configurable. Changing them is a
#   coordinated install-time change (postinstall, plist, payload).
#     CONTAINER = mining-guardian-db
#     DB_USER   = mg
#     DB_NAME   = mining_guardian
#
# Colima socket (W14 Step 9 / 9c, 2026-05-13):
#   launchd-spawned processes do not load `docker context use colima`
#   from the interactive user's shell config, so they default to
#   /var/run/docker.sock which does not exist on macOS+Colima. Setting
#   DOCKER_HOST explicitly bypasses context resolution. Pre-W14 this
#   bug was failing every step of this script with
#       `dial unix /var/run/docker.sock: connect: no such file or directory`
#   for ≥2 days. Same fix as scripts/backup_operational.sh.

# Colima socket — see header for full rationale.
export DOCKER_HOST="unix:///Users/miningguardian/.colima/default/docker.sock"

# Ensure docker is reachable. The plist's EnvironmentVariables.PATH
# already includes /usr/local/bin, but defense-in-depth costs one line —
# if a future plist edit drops the override, the script still finds
# docker.
export PATH=/usr/local/bin:$PATH

CONTAINER="mining-guardian-db"
DB_USER="mg"
DB_NAME="mining_guardian"
LABEL="operational"

# Single helper so every psql call shares the same shape and is easy
# to audit. Args are passed straight through to psql inside the
# container.
db_exec() {
    docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" "$@"
}

# Each step uses explicit if/else error handling. A step's failure
# logs to stderr (caught by the launcher's .err.log) but the script
# continues so the operator still sees the size report and integrity
# check even if VACUUM ANALYZE hiccups. If ANY step fails, the script
# exits non-zero at the end so the launcher's .last-run.json shows
# exit_code=1 and the operator notices something is off rather than
# silently swallowing the failure.
FAIL_COUNT=0
run_step() {
    local label="$1"
    shift
    echo "  ${label}..."
    if ! "$@"; then
        echo "  FAIL: ${label} returned non-zero" >&2
        FAIL_COUNT=$((FAIL_COUNT + 1))
        return 1
    fi
}

echo "$(date '+%Y-%m-%d %H:%M:%S') [${LABEL}] Starting database maintenance (Postgres in Docker)..."

# 1. VACUUM ANALYZE — reclaims space from deleted rows AND updates
#    query planner stats. Safe to run while services are active; uses
#    MVCC, no exclusive locks on active tables.
run_step "Running VACUUM ANALYZE" db_exec -c "VACUUM ANALYZE;"

# 2. ANALYZE alone — redundant after VACUUM ANALYZE but cheap and
#    catches the case where VACUUM ANALYZE was skipped.
run_step "Running ANALYZE" db_exec -c "ANALYZE;"

# 3. Database size reporting.
db_size="$(db_exec -tAc "SELECT pg_size_pretty(pg_database_size('${DB_NAME}'))" 2>/dev/null)"
if [[ -n "$db_size" ]]; then
    echo "  Database size: ${db_size}"
else
    echo "  WARN: could not read database size" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

# 4. Top 10 largest tables.
echo "  Top 10 largest tables:"
if ! db_exec -c "
SELECT
    schemaname || '.' || relname AS table_name,
    pg_size_pretty(pg_total_relation_size(schemaname || '.' || relname)) AS total_size,
    n_live_tup AS live_rows
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(schemaname || '.' || relname) DESC
LIMIT 10;
"; then
    echo "  WARN: top-10 tables report failed" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

# 5. Integrity check — confirm we can count rows in a key table.
rows="$(db_exec -tAc "SELECT COUNT(*) FROM scans" 2>/dev/null)"
if [[ -n "$rows" ]]; then
    echo "  Integrity: OK (scans=${rows})"
else
    echo "  WARN: integrity check failed — could not read scans table" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') [${LABEL}] Database maintenance complete (${FAIL_COUNT} step(s) failed)"
echo "---"

# Exit non-zero if ANY step failed, so the launcher's .last-run.json
# stamps exit_code=1 and the operator notices. Pure-success day gets
# exit_code=0.
if [[ "$FAIL_COUNT" -gt 0 ]]; then
    exit 1
fi
exit 0
