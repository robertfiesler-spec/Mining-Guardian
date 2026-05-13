#!/bin/bash
# scripts/db_maintenance_catalog.sh
#
# W14 Step 9c (2026-05-13) — per-instance VACUUM/ANALYZE for the
# CATALOG Postgres container.
#
# Mining Guardian runs two Postgres containers on the Mini (W14, 2026-05-13):
#   - mining-guardian-db (operational) on 127.0.0.1:5432  — see db_maintenance_operational.sh
#   - mg-catalog-db      (catalog)     on 127.0.0.1:5433  — this script
#
# Both are usually invoked via scripts/db_maintenance.sh (wrapper), which
# the scheduled launchd job calls. Run standalone for ad-hoc catalog
# maintenance.
#
# Why catalog needs its own maintenance script (W14 Step 9c):
#   Pre-W14, the catalog DB lived inside the operational container and
#   was vacuumed by the same script. Post-W14 they're on separate
#   containers (W14 split, 2026-05-13), so the operational maintenance
#   script can no longer reach the catalog DB. Mirroring the D6 backup
#   pattern (PR #204): two per-instance scripts + a wrapper.
#
# Output flow:
#   Same as db_maintenance_operational.sh — stdout/stderr captured by
#   the scheduled_job_launcher.sh wrapper to logs/scheduled/db_maintenance.{out,err}.log.
#
# Failure handling:
#   Same per-step counter pattern as the operational script — `set -e`
#   intentionally not used so one step's failure doesn't abort the rest.
#
# Container / DB identity (hardcoded — deployment identities):
#   CONTAINER = mg-catalog-db
#   DB_USER   = mg
#   DB_NAME   = mining_guardian_catalog
#
# Colima socket (W14 Step 9 / 9c, 2026-05-13):
#   launchd-spawned processes default to /var/run/docker.sock which
#   does not exist on macOS+Colima. Setting DOCKER_HOST explicitly
#   bypasses context resolution. Same fix as scripts/backup_catalog.sh
#   and db_maintenance_operational.sh.

# Colima socket — see header for full rationale.
export DOCKER_HOST="unix:///Users/miningguardian/.colima/default/docker.sock"

# Defense in depth on PATH.
export PATH=/usr/local/bin:$PATH

CONTAINER="mg-catalog-db"
DB_USER="mg"
DB_NAME="mining_guardian_catalog"
LABEL="catalog"

# Single helper so every psql call shares the same shape.
db_exec() {
    docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" "$@"
}

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
#    query planner stats. Safe to run while the feedback-loop-daemon
#    is active; uses MVCC, no exclusive locks on active tables.
run_step "Running VACUUM ANALYZE" db_exec -c "VACUUM ANALYZE;"

# 2. ANALYZE alone — redundant after VACUUM ANALYZE but cheap.
run_step "Running ANALYZE" db_exec -c "ANALYZE;"

# 3. Database size reporting.
db_size="$(db_exec -tAc "SELECT pg_size_pretty(pg_database_size('${DB_NAME}'))" 2>/dev/null)"
if [[ -n "$db_size" ]]; then
    echo "  Database size: ${db_size}"
else
    echo "  WARN: could not read database size" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

# 4. Top 10 largest tables. Catalog has tables in hardware/firmware/
#    market/staging/knowledge schemas (vs operational's mg schema) so
#    the SQL is identical — pg_stat_user_tables sees everything user-owned.
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

# 5. Integrity check — confirm we can count rows in the canonical
#    catalog table. hardware.miner_models is the heart of the catalog
#    (324 rows post-W14); if we can't read this table, the catalog DB
#    is in trouble.
rows="$(db_exec -tAc "SELECT COUNT(*) FROM hardware.miner_models" 2>/dev/null)"
if [[ -n "$rows" ]]; then
    echo "  Integrity: OK (hardware.miner_models=${rows})"
else
    echo "  WARN: integrity check failed — could not read hardware.miner_models" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') [${LABEL}] Database maintenance complete (${FAIL_COUNT} step(s) failed)"
echo "---"

if [[ "$FAIL_COUNT" -gt 0 ]]; then
    exit 1
fi
exit 0
