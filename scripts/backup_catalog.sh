#!/bin/bash
# scripts/backup_catalog.sh
#
# W14 Step 9 (D6) — Daily backup for the CATALOG Postgres instance.
#
# Mining Guardian runs two Postgres containers on the Mini (W14, 2026-05-13):
#   - mining-guardian-db (operational) on 127.0.0.1:5432
#   - mg-catalog-db      (catalog)     on 127.0.0.1:5433
#
# This script dumps ONLY the catalog database. The companion script
# scripts/backup_operational.sh dumps the operational database. Both are
# usually invoked via scripts/daily_backup.sh (the wrapper), which is
# what the scheduled launchd job calls.
#
# Why separate scripts (D6): see scripts/backup_operational.sh header.
#
# What this script does:
#   1. Verify the catalog container is up; bail with FATAL if not
#   2. pg_dump the mining_guardian_catalog database in custom (-Fc) format
#   3. Verify the dump is non-empty and pg_restore --list parses it
#   4. Apply retention: keep last 7 daily dumps, prune older
#
# Pattern compliance (W14_POSTMORTEM_2026-05-13.md §4):
#   - Password sourced via xargs (strips .env's surrounding quotes)
#   - Container's mg user authenticates from inside the container via
#     `docker exec` so no password ever crosses the wire as plaintext
#   - DOCKER_HOST set explicitly because launchd-spawned processes don't
#     inherit the Colima default-context resolution that interactive
#     shells use
#
# Exit codes (consumed by daily_backup.sh wrapper):
#   0 — backup written, verified, and retention applied
#   1 — container down or pg_dump failed
#   2 — pg_dump succeeded but verification failed (corrupted output)
#   3 — environment-setup failure (missing .env, missing docker binary)

set -euo pipefail

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

INSTALL_ROOT="${MG_INSTALL_ROOT:-/Library/Application Support/MiningGuardian}"
ENV_FILE="${INSTALL_ROOT}/.env"
BACKUP_DIR="${INSTALL_ROOT}/backups"
DOCKER_BIN="/usr/local/bin/docker"

CONTAINER="mg-catalog-db"
DB_USER="mg"
DB_NAME="mining_guardian_catalog"
LABEL="catalog"

RETAIN_COUNT="${MG_BACKUP_RETAIN_COUNT:-7}"

# Colima socket — see backup_operational.sh for the full rationale.
export DOCKER_HOST="unix:///Users/miningguardian/.colima/default/docker.sock"
export PATH="/usr/local/bin:${PATH:-}"

ts() { /bin/date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "[$(ts)] [${LABEL}-backup] $*"; }
die() { echo "[$(ts)] [${LABEL}-backup] FATAL $*" >&2; exit "${2:-1}"; }

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

[[ -f "${ENV_FILE}" ]] || die "env file missing: ${ENV_FILE}" 3
[[ -x "${DOCKER_BIN}" ]] || die "docker binary missing or not executable: ${DOCKER_BIN}" 3

mkdir -p "${BACKUP_DIR}" || die "cannot create backup dir: ${BACKUP_DIR}" 3

if [[ -z "$("${DOCKER_BIN}" ps -q -f "name=^${CONTAINER}$" 2>/dev/null)" ]]; then
    die "${CONTAINER} container is not running; cannot back up" 1
fi

# ---------------------------------------------------------------------------
# Dump
# ---------------------------------------------------------------------------

stamp="$(/bin/date +%Y%m%d-%H%M%S)"
out_file="${BACKUP_DIR}/${LABEL}-${stamp}.dump"

log "starting pg_dump of ${DB_NAME} from ${CONTAINER} → ${out_file}"

if ! "${DOCKER_BIN}" exec -i "${CONTAINER}" pg_dump \
        -U "${DB_USER}" -d "${DB_NAME}" \
        -Fc --no-owner --no-privileges \
        > "${out_file}" 2>>"${out_file}.err"; then
    log "pg_dump FAILED — see ${out_file}.err for details"
    exit 1
fi

if [[ ! -s "${out_file}" ]]; then
    log "pg_dump produced 0-byte file"
    exit 2
fi

dump_size="$(/usr/bin/stat -f%z "${out_file}")"
log "pg_dump complete, ${dump_size} bytes written"

# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

if ! "${DOCKER_BIN}" exec -i "${CONTAINER}" pg_restore --list \
        < "${out_file}" > /dev/null 2>&1; then
    log "VERIFICATION FAILED — pg_restore --list rejected the dump"
    exit 2
fi

log "verification passed (pg_restore --list parsed TOC cleanly)"

[[ -f "${out_file}.err" ]] && [[ ! -s "${out_file}.err" ]] && /bin/rm -f "${out_file}.err"

# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------

# Match only this script's dump pattern. pre-w14-catalog-*.dump is
# deliberately not matched — permanent rollback artifact.
pruned_count=0
if old_dumps="$(ls -1t "${BACKUP_DIR}/${LABEL}-"*.dump 2>/dev/null | tail -n +$((RETAIN_COUNT + 1)))"; then
    if [[ -n "${old_dumps}" ]]; then
        pruned_count="$(echo "${old_dumps}" | wc -l | tr -d ' ')"
        echo "${old_dumps}" | xargs /bin/rm -f
        log "retention: pruned ${pruned_count} dump(s) older than the ${RETAIN_COUNT} most recent"
    fi
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

log "OK ${out_file} (${dump_size} bytes); ${RETAIN_COUNT} retained, ${pruned_count} pruned"
exit 0
