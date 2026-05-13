#!/bin/bash
# scripts/backup_operational.sh
#
# W14 Step 9 (D6) — Daily backup for the OPERATIONAL Postgres instance.
#
# Mining Guardian runs two Postgres containers on the Mini (W14, 2026-05-13):
#   - mining-guardian-db (operational) on 127.0.0.1:5432
#   - mg-catalog-db      (catalog)     on 127.0.0.1:5433
#
# This script dumps ONLY the operational database. The companion script
# scripts/backup_catalog.sh dumps the catalog database. Both are usually
# invoked via scripts/daily_backup.sh (the wrapper), which is what the
# scheduled launchd job calls.
#
# Why separate scripts (D6):
#   - Clearer rollback if one fails — partial success is visible to the
#     operator instead of hidden inside a combined script
#   - Aligns with federation (W28) where catalog ships to master and
#     operational stays local; the two paths diverge anyway
#   - Each script is short and obvious; failures are easy to read
#
# What this script does:
#   1. Verify the operational container is up; bail with FATAL if not
#   2. pg_dump the mining_guardian database in custom (-Fc) format
#   3. Verify the dump is non-empty and pg_restore --list parses it
#   4. Apply retention: keep last 7 daily dumps, prune older
#
# Pattern compliance (W14_POSTMORTEM_2026-05-13.md §4):
#   - Password sourced via xargs (strips .env's surrounding quotes)
#   - Container's mg user authenticates from inside the container via
#     `docker exec` so no password ever crosses the wire as plaintext
#   - DOCKER_HOST set explicitly because launchd-spawned processes don't
#     inherit the Colima default-context resolution that interactive
#     shells use (see "Colima socket" comment below)
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

CONTAINER="mining-guardian-db"
DB_USER="mg"
DB_NAME="mining_guardian"
LABEL="operational"

# Retention: keep the most recent N daily dumps. Older ones are deleted
# at the end of a successful run. Operator can tune via env var.
RETAIN_COUNT="${MG_BACKUP_RETAIN_COUNT:-7}"

# Colima socket — launchd-spawned processes do not load
# `docker context use colima` from the interactive user's shell config,
# so they default to /var/run/docker.sock (which does not exist on
# macOS+Colima). Setting DOCKER_HOST explicitly bypasses context
# resolution.
#
# The socket path is determined by the installing user's home directory.
# postinstall.sh::step_install_colima creates the colima profile under
# that user's $HOME/.colima/default/.
export DOCKER_HOST="unix:///Users/miningguardian/.colima/default/docker.sock"

# Defense in depth on PATH so /usr/local/bin/docker is findable even if
# a future plist edit drops the EnvironmentVariables.PATH override.
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

# Verify the operational container is up. `docker ps -q -f` returns the
# container ID if running, empty otherwise — cheaper than `docker inspect`.
if [[ -z "$("${DOCKER_BIN}" ps -q -f "name=^${CONTAINER}$" 2>/dev/null)" ]]; then
    die "${CONTAINER} container is not running; cannot back up" 1
fi

# ---------------------------------------------------------------------------
# Dump
# ---------------------------------------------------------------------------

stamp="$(/bin/date +%Y%m%d-%H%M%S)"
out_file="${BACKUP_DIR}/${LABEL}-${stamp}.dump"

log "starting pg_dump of ${DB_NAME} from ${CONTAINER} → ${out_file}"

# pg_dump runs INSIDE the container against the local Postgres on
# port 5432 (the container's perspective). It authenticates via PAM
# (the postgres user inside the image trusts local connections), so no
# password is sent over the wire. The dump is streamed to stdout and
# captured into the host-side file via the redirection — this avoids
# allocating a TTY (`-t`) which would interfere with binary output.
#
# `--no-owner --no-privileges` makes the dump portable across role
# names; useful if a future restore happens into a fresh container
# whose `mg` role hasn't yet been created with identical OID.
if ! "${DOCKER_BIN}" exec -i "${CONTAINER}" pg_dump \
        -U "${DB_USER}" -d "${DB_NAME}" \
        -Fc --no-owner --no-privileges \
        > "${out_file}" 2>>"${out_file}.err"; then
    log "pg_dump FAILED — see ${out_file}.err for details"
    # Leave the partial file + .err for forensics. The wrapper marks the
    # job failed; the operator can inspect.
    exit 1
fi

# Confirm something was actually written
if [[ ! -s "${out_file}" ]]; then
    log "pg_dump produced 0-byte file"
    exit 2
fi

dump_size="$(/usr/bin/stat -f%z "${out_file}")"
log "pg_dump complete, ${dump_size} bytes written"

# ---------------------------------------------------------------------------
# Verify (cheap — `pg_restore --list` parses TOC without writing data)
# ---------------------------------------------------------------------------

if ! "${DOCKER_BIN}" exec -i "${CONTAINER}" pg_restore --list \
        < "${out_file}" > /dev/null 2>&1; then
    log "VERIFICATION FAILED — pg_restore --list rejected the dump"
    exit 2
fi

log "verification passed (pg_restore --list parsed TOC cleanly)"

# Clean up the .err file if pg_dump didn't actually error
[[ -f "${out_file}.err" ]] && [[ ! -s "${out_file}.err" ]] && /bin/rm -f "${out_file}.err"

# ---------------------------------------------------------------------------
# Retention — keep last RETAIN_COUNT dumps for this label, prune older
# ---------------------------------------------------------------------------

# Match only this script's dump pattern. The pre-W14 dumps
# (pre-w14-operational-*.dump) are deliberately NOT matched — those are
# permanent rollback artifacts retained per W14_POSTMORTEM §3.
#
# `ls -t` sorts newest first; `tail -n +$((N+1))` returns everything
# beyond position N; xargs deletes those. BSD `ls -t` and `tail -n +N`
# match GNU semantics here.
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
