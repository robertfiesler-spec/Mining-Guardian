#!/usr/bin/env bash
# =============================================================================
# Mining Intelligence Catalog — Idempotent Seed Runner (C4, 2026-04-27)
# =============================================================================
# Runs intelligence-catalog/seed-data/seed_miner_models.sql against the catalog
# Postgres database, but only if the database has not already been seeded.
#
# The seed SQL itself is wrapped in BEGIN/COMMIT and contains no ON CONFLICT
# guards — re-running it on a populated database will fail on duplicate primary
# keys. Rather than rewrite 4,097 lines of seed SQL with ON CONFLICT clauses
# (and risk silently masking data drift), this wrapper checks the row count
# first and skips when already seeded. The seed file stays untouched and
# auditable.
#
# Used by:
#   - The customer Mac Mini installer (May 5+)
#   - The Docker dev box deploy.ps1 (Phase 5 verification)
#   - Any CI / sandbox test that needs a deterministic seeded DB
#
# Usage:
#   scripts/seed_catalog.sh                              # local socket, default
#   PGHOST=/tmp PGPORT=5433 scripts/seed_catalog.sh      # custom socket
#   scripts/seed_catalog.sh --force                      # re-seed even if populated (DANGEROUS)
#
# Required environment:
#   MG_DB_PASSWORD — set in customer secrets.bat / Mac Mini env (see D-1)
#
# Optional environment:
#   PGHOST    (default: /var/run/postgresql for unix socket)
#   PGPORT    (default: 5432)
#   PGUSER    (default: guardian_admin)
#   PGDATABASE (default: mining_guardian)
#   MG_REPO_ROOT — absolute path to repo root (default: derived from script location)
#
# Exit codes:
#   0 — seed loaded OR database was already seeded (idempotent success)
#   1 — runtime error (Postgres unreachable, SQL error, etc.)
#   2 — environment misconfigured (missing password, missing seed file)
# =============================================================================

set -euo pipefail

# ── Resolve repo root (works whether script is symlinked, called by absolute
# path, or run from inside the repo) ─────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${MG_REPO_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"

SEED_SQL="${REPO_ROOT}/intelligence-catalog/seed-data/seed_miner_models.sql"
EXPECTED_MIN_ROWS=313   # The seed inserts exactly 313 miners; base schema seeds 4 more

# ── Argument parsing ─────────────────────────────────────────────────────────
FORCE=0
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=1 ;;
        --help|-h)
            head -42 "$0" | tail -41 | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "ERROR: unknown argument: $arg" >&2
            echo "Usage: $0 [--force] [--help]" >&2
            exit 2
            ;;
    esac
done

# ── Pre-flight ───────────────────────────────────────────────────────────────
if [[ -z "${MG_DB_PASSWORD:-}" ]]; then
    echo "ERROR: MG_DB_PASSWORD is not set in the environment." >&2
    echo "       This is the catalog database password (D-1). The Mac Mini" >&2
    echo "       installer sets it in /etc/mining-guardian/secrets.env." >&2
    exit 2
fi

if [[ ! -f "$SEED_SQL" ]]; then
    echo "ERROR: Seed file not found: $SEED_SQL" >&2
    echo "       Expected location relative to repo root:" >&2
    echo "       intelligence-catalog/seed-data/seed_miner_models.sql" >&2
    exit 2
fi

if ! command -v psql >/dev/null 2>&1; then
    echo "ERROR: psql not found in PATH. Install PostgreSQL client tools." >&2
    exit 2
fi

# ── Connection params with defaults ──────────────────────────────────────────
export PGHOST="${PGHOST:-/var/run/postgresql}"
export PGPORT="${PGPORT:-5432}"
export PGUSER="${PGUSER:-guardian_admin}"
export PGDATABASE="${PGDATABASE:-mining_guardian}"
export PGPASSWORD="$MG_DB_PASSWORD"

# ── Reachability probe ───────────────────────────────────────────────────────
if ! psql -tA -c "SELECT 1" >/dev/null 2>&1; then
    echo "ERROR: cannot connect to Postgres at ${PGHOST}:${PGPORT} as ${PGUSER}/${PGDATABASE}" >&2
    echo "       Verify Postgres is running and MG_DB_PASSWORD is correct." >&2
    exit 1
fi

# ── Schema presence check (deploy_schema.sql must have run first) ───────────
TABLE_EXISTS=$(psql -tA -c "
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'hardware'
          AND table_name = 'miner_models'
    );
" 2>/dev/null || echo "f")

if [[ "$TABLE_EXISTS" != "t" ]]; then
    echo "ERROR: hardware.miner_models table does not exist." >&2
    echo "       Run intelligence-catalog/seed-data/deploy_schema.sql first." >&2
    exit 1
fi

# ── Idempotency check ────────────────────────────────────────────────────────
CURRENT_ROWS=$(psql -tA -c "SELECT COUNT(*) FROM hardware.miner_models;")

echo "[seed_catalog] hardware.miner_models currently has $CURRENT_ROWS rows."

if [[ "$CURRENT_ROWS" -ge "$EXPECTED_MIN_ROWS" ]] && [[ "$FORCE" -eq 0 ]]; then
    echo "[seed_catalog] Already seeded (>= $EXPECTED_MIN_ROWS rows). Skipping."
    echo "[seed_catalog] Use --force to re-seed anyway (will fail on duplicate PKs unless"
    echo "[seed_catalog]   the table is truncated first)."
    exit 0
fi

if [[ "$FORCE" -eq 1 ]] && [[ "$CURRENT_ROWS" -gt 0 ]]; then
    echo "[seed_catalog] WARNING: --force set but $CURRENT_ROWS rows present." >&2
    echo "[seed_catalog]          The seed will likely fail on duplicate primary keys." >&2
    echo "[seed_catalog]          To re-seed cleanly, first run:" >&2
    echo "[seed_catalog]              psql -c 'TRUNCATE hardware.miner_models CASCADE'" >&2
    echo "[seed_catalog]          (this will cascade into model_aliases and other dependents)" >&2
fi

# ── Run the seed ─────────────────────────────────────────────────────────────
echo "[seed_catalog] Running $SEED_SQL ..."
psql -v ON_ERROR_STOP=1 -f "$SEED_SQL"

# ── Post-flight verification ─────────────────────────────────────────────────
NEW_ROWS=$(psql -tA -c "SELECT COUNT(*) FROM hardware.miner_models;")
echo "[seed_catalog] hardware.miner_models now has $NEW_ROWS rows."

if [[ "$NEW_ROWS" -lt "$EXPECTED_MIN_ROWS" ]]; then
    echo "ERROR: post-seed count $NEW_ROWS is below expected minimum $EXPECTED_MIN_ROWS" >&2
    echo "       Something went wrong. Check psql output above for partial commits." >&2
    exit 1
fi

echo "[seed_catalog] Seed complete. C4 satisfied."
exit 0
