#!/bin/bash
# scripts/db_maintenance.sh
#
# W14 Step 9c (2026-05-13) — daily DB maintenance wrapper.
#
# Mining Guardian runs two Postgres containers on the Mini (W14, 2026-05-13).
# This wrapper runs both per-instance maintenance scripts and returns
# non-zero if either fails, so the launchd .last-run.json correctly
# reports partial-failure days to the operator.
#
# Invoked by the scheduled launchd job
#   installer/macos-pkg/resources/launchd/scheduled/com.miningguardian.scheduled.db-maintenance.plist
# which calls this wrapper through scripts/scheduled_job_launcher.sh.
#
# Why a wrapper instead of one combined script:
#   Mirrors the D6 backup-script pattern (PR #204). Each instance's
#   maintenance is independent; one failure shouldn't block the other
#   from attempting. Per-script exit codes give the operator a clearer
#   signal: "operational ok, catalog failed" is more actionable than
#   "maintenance failed (somewhere)".
#
# Exit codes:
#   0 — both scripts exited 0
#   1 — at least one script exited non-zero (operator must investigate)
#
# History:
#   Pre-W14: a single combined script (Linux-VPS era → Mac Mini rewrite
#   P-038 #6 on 2026-05-11) maintained one Postgres container holding
#   both DBs. Post-W14 split into two containers (2026-05-13), so this
#   wrapper + the two per-instance scripts replace the previous combined
#   shape. The previous combined script also had the same Colima socket
#   bug we're fixing here — `dial unix /var/run/docker.sock: connect:
#   no such file or directory` for every step under launchd context.
#   Fixed by setting DOCKER_HOST explicitly inside each per-instance
#   script (W14 Step 9 / 9c).

set -uo pipefail
# NOTE: `set -e` is intentionally not used — we want to run BOTH scripts
# even if the first fails, then report the combined result. Per-script
# failure handling is explicit below.

INSTALL_ROOT="${MG_INSTALL_ROOT:-/Library/Application Support/MiningGuardian}"
SCRIPTS_DIR="${INSTALL_ROOT}/scripts"
LABEL="db_maintenance"

ts() { /bin/date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "[$(ts)] [${LABEL}] $*"; }

log "starting daily maintenance cycle for both Postgres instances"

# Run operational maintenance
log "→ invoking db_maintenance_operational.sh"
operational_rc=0
"${SCRIPTS_DIR}/db_maintenance_operational.sh" || operational_rc=$?
if [[ "${operational_rc}" -eq 0 ]]; then
    log "→ db_maintenance_operational.sh: OK"
else
    log "→ db_maintenance_operational.sh: FAILED (exit ${operational_rc})"
fi

# Run catalog maintenance (regardless of operational outcome)
log "→ invoking db_maintenance_catalog.sh"
catalog_rc=0
"${SCRIPTS_DIR}/db_maintenance_catalog.sh" || catalog_rc=$?
if [[ "${catalog_rc}" -eq 0 ]]; then
    log "→ db_maintenance_catalog.sh: OK"
else
    log "→ db_maintenance_catalog.sh: FAILED (exit ${catalog_rc})"
fi

# Combined result
if [[ "${operational_rc}" -eq 0 ]] && [[ "${catalog_rc}" -eq 0 ]]; then
    log "OK both maintenance runs succeeded"
    exit 0
fi

log "FAIL operational_rc=${operational_rc} catalog_rc=${catalog_rc}"
log "    inspect ${INSTALL_ROOT}/logs/scheduled/db_maintenance.{out,err}.log"
exit 1
