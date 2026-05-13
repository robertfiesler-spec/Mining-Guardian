#!/bin/bash
# scripts/daily_backup.sh
#
# W14 Step 9 (D6) — Daily backup wrapper.
#
# Mining Guardian runs two Postgres containers on the Mini (W14, 2026-05-13).
# This wrapper runs both per-instance backup scripts and returns non-zero
# if either fails, so the launchd .last-run.json correctly reports
# partial-failure days to the operator.
#
# Invoked by the scheduled launchd job
#   installer/macos-pkg/resources/launchd/scheduled/com.miningguardian.scheduled.daily-backup.plist
# which calls this wrapper through scripts/scheduled_job_launcher.sh.
#
# Why a wrapper instead of one combined script (D6):
#   - Each instance's dump is independent; one failure shouldn't block
#     the other from attempting
#   - Per-script exit codes give the operator a clearer signal:
#     "operational succeeded, catalog failed" is more actionable than
#     "the backup failed (somewhere)"
#   - When federation (W28) lands, the catalog dump is what ships to
#     master; the operational dump stays local. Keeping the two paths
#     separate now reduces friction then.
#
# Exit codes:
#   0 — both scripts exited 0
#   1 — at least one script exited non-zero (operator must investigate)
#
# This wrapper does NOT back up application-level files (knowledge.json,
# .env, miner_specs.json). Those are handled separately by
# ai/backup_knowledge.py (the existing knowledge-backup scheduled job)
# and the system installer (the .pkg payload contains pristine copies
# of templates; live secrets are operator-supplied at install time and
# not part of automated backup scope). If the scope ever expands to
# include application files, add a third per-domain script here rather
# than mixing concerns in the wrapper.
#
# Historical note: the previous scripts/daily_backup.sh (and its
# companions scripts/backup_db.sh, scripts/backup_mining_guardian.sh)
# were VPS-era SQLite backup scripts. They referenced /root/Mining-Guardian
# and guardian.db — neither of which exist post-cutover. They have been
# preserved as *.legacy-vps-decommissioned alongside this PR so the
# history is traceable but they are not in the execution path.

set -uo pipefail
# NOTE: `set -e` is intentionally not used — we want to run BOTH scripts
# even if the first fails, then report the combined result. Per-script
# failure handling is explicit below.

INSTALL_ROOT="${MG_INSTALL_ROOT:-/Library/Application Support/MiningGuardian}"
SCRIPTS_DIR="${INSTALL_ROOT}/scripts"
LABEL="daily_backup"

ts() { /bin/date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "[$(ts)] [${LABEL}] $*"; }

log "starting daily backup cycle for both Postgres instances"

# Run operational backup
log "→ invoking backup_operational.sh"
operational_rc=0
"${SCRIPTS_DIR}/backup_operational.sh" || operational_rc=$?
if [[ "${operational_rc}" -eq 0 ]]; then
    log "→ backup_operational.sh: OK"
else
    log "→ backup_operational.sh: FAILED (exit ${operational_rc})"
fi

# Run catalog backup (regardless of operational outcome)
log "→ invoking backup_catalog.sh"
catalog_rc=0
"${SCRIPTS_DIR}/backup_catalog.sh" || catalog_rc=$?
if [[ "${catalog_rc}" -eq 0 ]]; then
    log "→ backup_catalog.sh: OK"
else
    log "→ backup_catalog.sh: FAILED (exit ${catalog_rc})"
fi

# Combined result
if [[ "${operational_rc}" -eq 0 ]] && [[ "${catalog_rc}" -eq 0 ]]; then
    log "OK both backups succeeded"
    exit 0
fi

# Summarize the failure mode for the operator
log "FAIL operational_rc=${operational_rc} catalog_rc=${catalog_rc}"
log "    inspect ${INSTALL_ROOT}/backups/ and logs/scheduled/daily_backup.err.log"
exit 1
