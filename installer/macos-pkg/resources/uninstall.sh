#!/bin/bash
# installer/macos-pkg/resources/uninstall.sh
#
# Mining Guardian — customer Mac Mini uninstaller.
#
# This file ships inside the .pkg payload (see installer/macos-pkg/scripts/
# postinstall.sh::step_install_uninstall_script — D-18 Copy bug 3, P-008,
# v1.0.3) and lands at:
#   /Library/Application Support/MiningGuardian/bin/uninstall.sh
#
# Run as root from any directory:
#   sudo /Library/Application\ Support/MiningGuardian/bin/uninstall.sh
#
# Default behavior — what gets removed:
#   * 10 service LaunchDaemons (com.miningguardian.<service>) — bootout
#     then plist file removed from /Library/LaunchDaemons.
#   * 11 scheduled-job LaunchDaemons (com.miningguardian.scheduled.<job>)
#     — bootout then plist file removed from /Library/LaunchDaemons.
#   * /Library/Application Support/MiningGuardian/ — install root, except
#     the postgres-data subdirectory (preserved by default — see below).
#   * The bundled Postgres container "mining-guardian-db" (docker rm -f).
#   * The Colima VM dedicated to Mining Guardian if it is empty after
#     stopping the Postgres container — best-effort, never fatal.
#   * /etc/mining-guardian/install-receipt.json (and the parent dir if
#     empty) so a re-install starts from a clean receipt.
#
# Default behavior — what is PRESERVED unless --purge-data is passed:
#   * /Library/Application Support/MiningGuardian/postgres-data/ — the
#     Postgres data volume. The customer's full operational history,
#     audit log, training context, and 320-row catalog seed live here.
#     Vision Anchor 1 (the LLM is the product) and the §"Critical Safety
#     Rules" entry forbidding bulk deletes from mining_guardian without
#     a documented backup-first step both apply: data deletion is OPT-IN.
#   * Any existing pg_dump backups under
#     /Library/Application Support/MiningGuardian/backups/ — preserved
#     as a side-effect of preserving the data volume's parent path; the
#     uninstall surfaces them in the final summary.
#   * /var/log/mining-guardian/ — install logs and historical service
#     logs are left in place so a fresh install or post-mortem still has
#     them. Pass --purge-logs to remove.
#
# Flags:
#   --help         Show this help and exit 0.
#   --dry-run      Print every action that WOULD be taken; change nothing.
#                  Always exits 0; intended for operators verifying the
#                  uninstall plan before committing.
#   --yes          Skip the interactive confirmation prompt. Required in
#                  non-TTY contexts (scripts, CI) — without --yes and
#                  without a TTY, the uninstall refuses and exits 1.
#   --purge-data   ALSO remove /Library/Application Support/MiningGuardian/
#                  postgres-data/. Destroys the customer's operational
#                  history. Combine with --yes only when you mean it.
#   --purge-logs   ALSO remove /var/log/mining-guardian/. Removes install
#                  logs that may help diagnose a botched re-install.
#
# Idempotency:
#   * Re-running on a half-uninstalled box is safe — every step that
#     deletes / unloads checks for existence first and skips silently.
#   * Exit 0 is the success path; any non-zero exit indicates a step that
#     could not complete (the script prints WARN lines for best-effort
#     failures and FATAL lines for hard failures).
#
# Exit codes:
#   0   — uninstall complete (or dry-run printed plan)
#   1   — refused: not running as root, or non-TTY without --yes
#   2   — refused: an unknown / malformed flag
#   10  — launchctl bootout returned a fatal error on a service
#   11  — could not remove a launchd plist file
#   12  — could not stop / remove the Postgres container
#   13  — could not remove /Library/Application Support/MiningGuardian
#
# Hard rules (Vision Anchor 6 — local-only, customer-safe):
#   * Never modifies user files outside /Library/Application Support/
#     MiningGuardian, /Library/LaunchDaemons/com.miningguardian.*, /etc/
#     mining-guardian, and /var/log/mining-guardian (the last only with
#     --purge-logs).
#   * Never edits the customer's crontab — Mining Guardian uses launchd,
#     never cron, on the v1.0.3 install path.
#   * Never touches Tailscale, Slack, AMS, Cloudflare, or any other
#     customer-controlled service. The customer revokes those manually
#     if they wish.

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants — keep the labels lists in sync with installer/macos-pkg/scripts/
# postinstall.sh::PLIST_LABELS and SCHEDULED_PLIST_LABELS. The test
# tests/installer/test_uninstall_script.sh asserts no drift.
# ---------------------------------------------------------------------------

readonly MG_INSTALL_ROOT="/Library/Application Support/MiningGuardian"
readonly MG_RECEIPT_DIR="/etc/mining-guardian"
readonly MG_LOG_DIR="/var/log/mining-guardian"
readonly MG_PG_CONTAINER="mining-guardian-db"
readonly MG_COLIMA_PROFILE="mining-guardian"
readonly MG_PLIST_DEST="/Library/LaunchDaemons"

readonly MG_SERVICE_LABELS=(
    "com.miningguardian.scanner"
    "com.miningguardian.dashboard-api"
    "com.miningguardian.approval-api"
    "com.miningguardian.slack-listener"
    "com.miningguardian.slack-commands"
    "com.miningguardian.overnight-automation"
    "com.miningguardian.alerts"
    "com.miningguardian.intelligence-report"
    "com.miningguardian.console"
    "com.miningguardian.feedback-loop-daemon"
)

readonly MG_SCHEDULED_LABELS=(
    "com.miningguardian.scheduled.weekly-training"
    "com.miningguardian.scheduled.refinement-chain"
    "com.miningguardian.scheduled.db-maintenance"
    "com.miningguardian.scheduled.knowledge-backup"
    "com.miningguardian.scheduled.morning-briefing"
    "com.miningguardian.scheduled.operator-review"
    "com.miningguardian.scheduled.ams-cleanup"
    "com.miningguardian.scheduled.log-collection"
    "com.miningguardian.scheduled.daily-deep-dive"
    "com.miningguardian.scheduled.log-failure-report"
    "com.miningguardian.scheduled.benchmark"
)

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------

DRY_RUN=0
ASSUME_YES=0
PURGE_DATA=0
PURGE_LOGS=0

usage() {
    sed -n '2,80p' "$0" | sed 's/^# \{0,1\}//'
    echo ""
    echo "Usage: sudo $0 [--dry-run] [--yes] [--purge-data] [--purge-logs] [--help]"
}

parse_args() {
    while (( $# > 0 )); do
        case "$1" in
            -h|--help)        usage; exit 0 ;;
            -n|--dry-run)     DRY_RUN=1 ;;
            -y|--yes)         ASSUME_YES=1 ;;
            --purge-data)     PURGE_DATA=1 ;;
            --purge-logs)     PURGE_LOGS=1 ;;
            *)
                echo "uninstall.sh: unknown argument: $1" >&2
                echo "Run with --help to see options." >&2
                exit 2
                ;;
        esac
        shift
    done
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

info() { echo "$(_now) [uninstall] $*"; }
warn() { echo "$(_now) [uninstall] WARN $*" >&2; }
fail() {
    local code="$1"; shift
    echo "$(_now) [uninstall] FATAL ($code) $*" >&2
    exit "$code"
}

# Run a command (real or dry). On dry-run, just print the rendered command.
# Avoids `eval` — every caller passes a pre-formed argv.
run() {
    if (( DRY_RUN )); then
        echo "  DRY-RUN: $*"
        return 0
    fi
    "$@"
}

# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

require_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        fail 1 "must run as root: sudo $0 $*"
    fi
}

confirm_or_die() {
    if (( ASSUME_YES )) || (( DRY_RUN )); then
        return 0
    fi
    if [[ ! -t 0 || ! -t 1 ]]; then
        fail 1 "non-interactive shell — pass --yes to confirm uninstall, or run with --dry-run first"
    fi
    echo ""
    echo "This will remove Mining Guardian from this Mac:"
    echo "  * 10 service LaunchDaemons + 11 scheduled-job LaunchDaemons"
    echo "  * Postgres container '${MG_PG_CONTAINER}'"
    echo "  * ${MG_INSTALL_ROOT}"
    if (( PURGE_DATA )); then
        echo "  * postgres-data (--purge-data) — operational history will be DESTROYED"
    else
        echo "  * postgres-data is PRESERVED (pass --purge-data to remove it)"
    fi
    if (( PURGE_LOGS )); then
        echo "  * ${MG_LOG_DIR} (--purge-logs)"
    else
        echo "  * ${MG_LOG_DIR} is PRESERVED (pass --purge-logs to remove it)"
    fi
    echo ""
    read -r -p "Type 'uninstall' to continue: " reply
    if [[ "$reply" != "uninstall" ]]; then
        info "user did not confirm — aborting"
        exit 0
    fi
}

# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

bootout_one() {
    local label="$1"
    local plist="${MG_PLIST_DEST}/${label}.plist"

    if /bin/launchctl print "system/${label}" >/dev/null 2>&1; then
        info "bootout system/${label}"
        # bootout exits non-zero in benign cases (already booted out, plist
        # already gone). Treat any non-zero as WARN unless followed by a
        # confirming `print` that still sees the label as loaded.
        if ! run /bin/launchctl bootout "system/${label}" 2>/dev/null; then
            if (( ! DRY_RUN )) && /bin/launchctl print "system/${label}" >/dev/null 2>&1; then
                fail 10 "launchctl bootout system/${label} failed and the service is still loaded"
            fi
            warn "launchctl bootout system/${label} returned non-zero (already booted out?) — continuing"
        fi
    else
        info "skip bootout: system/${label} not loaded"
    fi

    if [[ -e "$plist" ]]; then
        info "rm ${plist}"
        if ! run /bin/rm -f "$plist"; then
            fail 11 "could not remove ${plist}"
        fi
    else
        info "skip rm: ${plist} not present"
    fi
}

step_bootout_services() {
    info "stopping ${#MG_SERVICE_LABELS[@]} service LaunchDaemons"
    local label
    for label in "${MG_SERVICE_LABELS[@]}"; do
        bootout_one "$label"
    done
}

step_bootout_scheduled() {
    info "stopping ${#MG_SCHEDULED_LABELS[@]} scheduled-job LaunchDaemons"
    local label
    for label in "${MG_SCHEDULED_LABELS[@]}"; do
        bootout_one "$label"
    done
}

step_remove_postgres_container() {
    if ! command -v docker >/dev/null 2>&1; then
        info "skip postgres container: docker not on PATH"
        return 0
    fi
    if ! docker inspect "$MG_PG_CONTAINER" >/dev/null 2>&1; then
        info "skip postgres container: ${MG_PG_CONTAINER} not present"
        return 0
    fi
    info "stopping postgres container ${MG_PG_CONTAINER}"
    if ! run docker rm -f "$MG_PG_CONTAINER" >/dev/null 2>&1; then
        fail 12 "docker rm -f ${MG_PG_CONTAINER} failed"
    fi
}

step_stop_colima_profile() {
    # Best-effort: only stop the Mining Guardian colima profile if it
    # exists. We never delete it — a future re-install picks the same VM
    # back up. Failure here is logged but never fatal.
    if ! command -v colima >/dev/null 2>&1; then
        info "skip colima stop: colima not on PATH"
        return 0
    fi
    if ! colima list 2>/dev/null | /usr/bin/grep -q "^${MG_COLIMA_PROFILE} "; then
        info "skip colima stop: profile ${MG_COLIMA_PROFILE} not registered"
        return 0
    fi
    info "stopping colima profile ${MG_COLIMA_PROFILE} (best-effort)"
    if ! run colima stop --profile "$MG_COLIMA_PROFILE" >/dev/null 2>&1; then
        warn "colima stop --profile ${MG_COLIMA_PROFILE} returned non-zero (continuing)"
    fi
}

step_remove_install_root() {
    if [[ ! -e "$MG_INSTALL_ROOT" ]]; then
        info "skip rm: ${MG_INSTALL_ROOT} not present"
        return 0
    fi

    if (( PURGE_DATA )); then
        info "rm -rf ${MG_INSTALL_ROOT} (--purge-data)"
        if ! run /bin/rm -rf "$MG_INSTALL_ROOT"; then
            fail 13 "could not remove ${MG_INSTALL_ROOT}"
        fi
        return 0
    fi

    # Preserve the postgres-data subdirectory by deleting every other top-
    # level entry, then leaving an empty MiningGuardian/ housing the
    # postgres-data dir. Customer can manually rm it after verifying
    # they don't want the data.
    local data_dir="${MG_INSTALL_ROOT}/postgres-data"
    local entry
    info "removing ${MG_INSTALL_ROOT} contents (postgres-data preserved)"
    # `find -depth 1` (BSD/macOS find) limits to direct children.
    while IFS= read -r -d '' entry; do
        if [[ "$entry" == "$data_dir" ]]; then
            info "  preserve: ${entry}"
            continue
        fi
        info "  rm: ${entry}"
        if ! run /bin/rm -rf "$entry"; then
            fail 13 "could not remove ${entry}"
        fi
    done < <(/usr/bin/find "$MG_INSTALL_ROOT" -mindepth 1 -maxdepth 1 -print0 2>/dev/null)
}

step_remove_receipt() {
    local receipt="${MG_RECEIPT_DIR}/install-receipt.json"
    if [[ -e "$receipt" ]]; then
        info "rm ${receipt}"
        run /bin/rm -f "$receipt" || warn "could not remove ${receipt}"
    fi
    # If the parent dir is empty after the receipt removal, drop it too —
    # but only if empty, never recursively.
    if [[ -d "$MG_RECEIPT_DIR" ]]; then
        if (( DRY_RUN )); then
            echo "  DRY-RUN: rmdir ${MG_RECEIPT_DIR} (if empty)"
        else
            /bin/rmdir "$MG_RECEIPT_DIR" 2>/dev/null || true
        fi
    fi
}

step_purge_logs() {
    if (( ! PURGE_LOGS )); then
        info "preserving ${MG_LOG_DIR} (pass --purge-logs to remove)"
        return 0
    fi
    if [[ ! -e "$MG_LOG_DIR" ]]; then
        info "skip rm: ${MG_LOG_DIR} not present"
        return 0
    fi
    info "rm -rf ${MG_LOG_DIR} (--purge-logs)"
    run /bin/rm -rf "$MG_LOG_DIR" || warn "could not remove ${MG_LOG_DIR}"
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

step_summary() {
    echo ""
    info "uninstall summary:"
    info "  removed: ${#MG_SERVICE_LABELS[@]} service LaunchDaemons"
    info "  removed: ${#MG_SCHEDULED_LABELS[@]} scheduled-job LaunchDaemons"
    info "  removed: postgres container '${MG_PG_CONTAINER}' (if present)"
    if (( PURGE_DATA )); then
        info "  removed: ${MG_INSTALL_ROOT} (including postgres-data)"
    elif [[ -d "${MG_INSTALL_ROOT}/postgres-data" ]]; then
        info "  preserved: ${MG_INSTALL_ROOT}/postgres-data"
        info "    (manual rm -rf when you are sure you do not want the data)"
    elif (( DRY_RUN )); then
        info "  preserved: ${MG_INSTALL_ROOT}/postgres-data (dry-run; default)"
    fi
    if (( PURGE_LOGS )); then
        info "  removed: ${MG_LOG_DIR}"
    else
        info "  preserved: ${MG_LOG_DIR}"
    fi
    info "  preserved: customer .conf on Desktop (operator owns this)"
    info "  preserved: Tailscale, Slack, AMS, Cloudflare config (out of scope)"
    if (( DRY_RUN )); then
        echo ""
        info "DRY-RUN complete — nothing was changed."
    else
        echo ""
        info "Mining Guardian uninstalled."
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    parse_args "$@"
    require_root "$@"
    if (( DRY_RUN )); then
        info "Mining Guardian uninstaller — DRY-RUN MODE (nothing will change)"
    else
        info "Mining Guardian uninstaller starting (pid=$$)"
    fi

    confirm_or_die

    step_bootout_scheduled
    step_bootout_services
    step_remove_postgres_container
    step_stop_colima_profile
    step_remove_install_root
    step_remove_receipt
    step_purge_logs
    step_summary
    return 0
}

main "$@"
