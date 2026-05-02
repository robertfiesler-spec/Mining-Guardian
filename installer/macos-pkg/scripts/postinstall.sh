#!/bin/bash
# installer/macos-pkg/scripts/postinstall.sh
#
# macOS .pkg postinstall script — RUNS AS root via Installer.app, AFTER
# the package payload has been laid down on disk by Installer.app itself.
#
# ============================================================================
# Bucket 6 final close-out (2026-04-29) — 9-service refresh
# Bucket 7.5 follow-up (2026-04-29) — fix feedback_loop_daemon launcher path
# ----------------------------------------------------------------------------
# This file was originally PR #45 (4 services). Bucket 6 grew the install
# matrix to 9 services to match what the Mac-Mini production node actually
# runs (mirrors `scripts/setup.sh` Phase 9 from PR #75 / Bucket 6b).
#
# Service matrix (9):
#   plists from installer/macos-pkg/resources/launchd/        (8 plists)
#       com.miningguardian.scanner
#       com.miningguardian.dashboard-api
#       com.miningguardian.approval-api
#       com.miningguardian.slack-listener
#       com.miningguardian.slack-commands
#       com.miningguardian.overnight-automation
#       com.miningguardian.alerts
#       com.miningguardian.intelligence-report
#   plist from deploy/                                         (1 plist)
#       com.miningguardian.feedback-loop-daemon  (PR #41)
#
# Launcher wrappers (9) are ALL sourced from canonical files in git — zero
# inline heredocs:
#   8 wrappers from installer/macos-pkg/resources/launchd/launchers/*.sh
#     (written by PR #74 / Bucket 6a)
#   1 wrapper from deploy/feedback_loop_daemon_launcher.sh
#     (canonical D-14 PR 4b; invokes daemon by file path to dodge the
#      hyphenated-package import issue — the daemon lives at
#      intelligence-catalog/db/feedback_loop_daemon.py and `python -m`
#      cannot import a package whose top-level dir contains a hyphen).
# ============================================================================
#
# Job: bring the freshly-laid-down Mining Guardian install up to a
# running state. Specifically:
#
#   1. Resolve install paths and re-source the env file written by
#      preinstall.sh (RAM tier + LLM model from D-13).
#   2. Stand up Colima + the bundled Postgres container (offline).
#   3. Apply migrations 000_bootstrap, 002_layer2, 003_c5_notify_triggers.
#   4. Install Ollama and pull the selected LLM model (the ONE network
#      step at first-run; loud failure if unreachable).
#   5. Copy the 8 pre-written launcher wrappers from the .pkg payload
#      into ${MG_INSTALL_ROOT}/bin/, then generate the 9th wrapper
#      (feedback_loop_daemon_launcher.sh) inline.
#   6. Install the 9 launchd plists and load them with launchctl
#      bootstrap.
#   7. Drop /etc/mining-guardian/install-receipt.json with git SHA,
#      version, install timestamp, RAM tier, LLM model.
#   8. Fire a first-run baseline scan so the operator sees green tiles
#      on the dashboard within ~30 s of the install completing.
#
# Refuses to silently degrade. Any failure exits non-zero so
# Installer.app shows the standard "install failed" dialog with a
# pointer to the install log.
#
# Exit codes:
#   0      — install complete; services running
#   30     — env file from preinstall missing (preinstall didn't run?)
#   31     — Colima / Postgres provisioning failed
#   32     — migration apply failed
#   33     — Ollama install or model pull failed
#   34     — launchd bootstrap failed
#   35     — install receipt could not be written
#   36     — first-run baseline scan failed
#   37     — launcher wrapper or plist source missing in payload (Bucket 6)
#
# Vision Anchor 7 honored: only one network call (model pull); every
# other byte is vendored inside the .pkg.
# Vision Anchor 6 honored: no altcoin paths anywhere in the install.

set -euo pipefail

# ---------------------------------------------------------------------------
# Paths + environment
# ---------------------------------------------------------------------------

# Same convention as preinstall.sh.
export MG_INSTALL_LOG="/var/log/mining-guardian/install-postinstall.log"
export MG_INSTALL_ENV="/tmp/mg_install_env"
export MG_INSTALL_ROOT="/Library/Application Support/MiningGuardian"

# Installer.app sets these positional args; we just take note of them.
PKG_PATH="${1:-}"            # full path to the installed pkg
INSTALL_TARGET_DIR="${2:-}"  # where the payload was extracted (often /)
TARGET_VOLUME="${3:-/}"      # the disk the user picked
INSTALL_KIND="${4:-}"        # "/" or system identifier

# The payload directory inside the pkg — this is where we vendored
# Colima, Ollama, the Postgres image, and the migration .sql files.
# Installer.app stages the package into a working dir under
# /private/tmp/.../<pkgname>/Resources at script time.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MG_PKG_PAYLOAD="${SCRIPT_DIR}/../payload"

readonly LIB_COLIMA="${SCRIPT_DIR}/lib/install_colima.sh"
readonly LIB_OLLAMA="${SCRIPT_DIR}/lib/install_ollama.sh"

# launchd plist staging — copied INTO LaunchDaemons/ at install time.
# Source dirs live inside the pkg's Resources tree (set by .pkg build script
# to mirror the repo layout under installer/macos-pkg/resources/).
readonly PLISTS_SRC="${SCRIPT_DIR}/../resources/launchd"
readonly LAUNCHERS_SRC="${SCRIPT_DIR}/../resources/launchd/launchers"
readonly PLISTS_DEST="/Library/LaunchDaemons"

# Bucket 6: 9 services. The 8 entries that ship from
# installer/macos-pkg/resources/launchd/ are listed first; the 9th
# (feedback-loop-daemon, PR #41) ships from deploy/ via the payload.
readonly PLIST_LABELS=(
    "com.miningguardian.scanner"
    "com.miningguardian.dashboard-api"
    "com.miningguardian.approval-api"
    "com.miningguardian.slack-listener"
    "com.miningguardian.slack-commands"
    "com.miningguardian.overnight-automation"
    "com.miningguardian.alerts"
    "com.miningguardian.intelligence-report"
    "com.miningguardian.feedback-loop-daemon"
)

# 8 launcher wrappers shipped verbatim from PR #74 (Bucket 6a). The
# filenames mirror the plist labels with hyphens swapped for underscores
# and `_launcher.sh` appended. The 9th launcher (feedback_loop_daemon)
# is generated inline below for parity with the other 8.
readonly LAUNCHER_FILES=(
    "scanner_launcher.sh"
    "dashboard_api_launcher.sh"
    "approval_api_launcher.sh"
    "slack_listener_launcher.sh"
    "slack_commands_launcher.sh"
    "overnight_automation_launcher.sh"
    "alerts_launcher.sh"
    "intelligence_report_launcher.sh"
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_setup_log() {
    local log_dir
    log_dir="$(dirname "$MG_INSTALL_LOG")"
    mkdir -p "$log_dir"
    chown root:wheel "$log_dir"
    chmod 0750 "$log_dir"
    : > "$MG_INSTALL_LOG"
    chmod 0640 "$MG_INSTALL_LOG"
}

log() {
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) [postinstall] $*" \
        | tee -a "$MG_INSTALL_LOG" >&2
}

fail() {
    local code="$1"; shift
    log "FATAL ($code) $*"
    log "Aborting install. See $MG_INSTALL_LOG and /var/log/mining-guardian/install-preinstall.log."
    exit "$code"
}

# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

step_source_env() {
    if [[ ! -r "$MG_INSTALL_ENV" ]]; then
        fail 30 "$MG_INSTALL_ENV missing; preinstall.sh did not run cleanly"
    fi
    # shellcheck disable=SC1090
    source "$MG_INSTALL_ENV"
    log "INFO sourced env: RAM_TIER=${MG_INSTALL_RAM_TIER:-?} LLM=${MG_INSTALL_LLM_MODEL:-?}"
}

step_load_libs() {
    if [[ ! -r "$LIB_COLIMA" ]]; then
        fail 31 "missing $LIB_COLIMA"
    fi
    if [[ ! -r "$LIB_OLLAMA" ]]; then
        fail 33 "missing $LIB_OLLAMA"
    fi
    # shellcheck disable=SC1090
    source "$LIB_COLIMA"
    # shellcheck disable=SC1090
    source "$LIB_OLLAMA"
    log "INFO loaded helper libs"
}

step_layout_install_root() {
    install -d -m 0755 "$MG_INSTALL_ROOT"
    install -d -m 0755 "${MG_INSTALL_ROOT}/bin"
    install -d -m 0755 "${MG_INSTALL_ROOT}/logs"
    install -d -m 0700 "${MG_INSTALL_ROOT}/postgres-data"
    chown -R "${SUDO_USER:-${USER}}:staff" "$MG_INSTALL_ROOT"
    log "INFO laid out install root at ${MG_INSTALL_ROOT}"
}

step_drop_dotenv() {
    # MG_DB_PASSWORD is generated fresh per-install by the .pkg build
    # script (NOT shipped in git). The build script writes it into
    # /tmp/mg_install_env_secret BEFORE Installer.app runs us; we read
    # it from there and write it into the canonical .env, then erase
    # the temp file.
    local secret_file="/tmp/mg_install_env_secret"
    if [[ ! -r "$secret_file" ]]; then
        fail 31 "missing per-install secret file at ${secret_file}; was the pkg built correctly?"
    fi
    # shellcheck disable=SC1090
    source "$secret_file"
    if [[ -z "${MG_DB_PASSWORD:-}" ]]; then
        fail 31 "MG_DB_PASSWORD not set after sourcing ${secret_file}"
    fi

    local env_file="${MG_INSTALL_ROOT}/.env"
    {
        echo "# Generated by Mining Guardian installer postinstall.sh"
        echo "# Generated at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo "# Permissions: 0600. Do NOT commit. Do NOT share."
        echo
        echo "MG_DB_PASSWORD=${MG_DB_PASSWORD}"
        echo "PGHOST=127.0.0.1"
        echo "PGPORT=5432"
        echo "PGUSER=mg"
        echo "PGDATABASE=mining_guardian"
        echo
        echo "MG_INSTALL_RAM_TIER=${MG_INSTALL_RAM_TIER}"
        echo "MG_INSTALL_LLM_MODEL=${MG_INSTALL_LLM_MODEL}"
    } > "$env_file"
    chown "${SUDO_USER:-${USER}}:staff" "$env_file"
    chmod 0600 "$env_file"

    # Erase the staging file so it doesn't linger in /tmp.
    rm -f "$secret_file"
    log "INFO wrote ${env_file} (mode 0600) and erased ${secret_file}"

    # Re-export so subsequent steps (Postgres provisioning) see it.
    export MG_DB_PASSWORD
}

step_provision_postgres() {
    install_colima_runtime || fail 31 "colima runtime install failed"
    load_postgres_image    || fail 31 "postgres image load failed"
    provision_postgres     || fail 31 "postgres container provisioning failed"
}

step_apply_migrations() {
    # The .pkg payload ships the canonical migrations as plain .sql files
    # under <payload>/migrations/. Apply them in numerical order; each
    # is fully idempotent (IF NOT EXISTS, etc.) so re-runs are safe.
    local mig_dir="${MG_PKG_PAYLOAD}/migrations"
    if [[ ! -d "$mig_dir" ]]; then
        fail 32 "migrations directory not in payload: ${mig_dir}"
    fi

    local container="mining-guardian-db"
    local sql
    for sql in "${mig_dir}"/*.sql; do
        [[ -f "$sql" ]] || continue
        log "INFO applying $(basename "$sql")"
        if ! sudo -u "${SUDO_USER:-${USER}}" docker exec -i "$container" \
                psql -U mg -d mining_guardian -v ON_ERROR_STOP=1 < "$sql" \
                2>&1 | tee -a "$MG_INSTALL_LOG"; then
            fail 32 "migration $(basename "$sql") failed"
        fi
    done
    log "INFO all migrations applied"
}

step_install_ollama_and_pull_model() {
    install_ollama_runtime || fail 33 "ollama runtime install failed"
    pull_llm_model         || fail 33 "ollama pull of ${MG_INSTALL_LLM_MODEL:-?} failed"
}

step_install_launcher_wrappers() {
    # Bucket 6 refresh: all 9 wrappers ship verbatim from the .pkg
    # payload as canonical files in git — NO inline heredocs:
    #
    #   8 wrappers from installer/macos-pkg/resources/launchd/launchers/
    #     (PR #74 / Bucket 6a)
    #   1 wrapper from deploy/feedback_loop_daemon_launcher.sh
    #     (PR #41, the canonical D-14 PR 4b launcher).
    #
    # The deploy/ launcher is the correct one because it invokes the
    # daemon by file path
    # (/Library/Application Support/MiningGuardian/intelligence-catalog/db/feedback_loop_daemon.py),
    # which sidesteps the directory-with-hyphen Python import problem.
    # An earlier draft of this function used an inline heredoc that ran
    # `python -m intelligence.feedback_loop_daemon` — that module path
    # never existed (the file lives at intelligence-catalog/db/, not
    # intelligence/). Bucket 7.5 corrects that by pulling from deploy/.
    local bin="${MG_INSTALL_ROOT}/bin"
    install -d -m 0755 "$bin"

    if [[ ! -d "$LAUNCHERS_SRC" ]]; then
        fail 37 "launcher wrappers directory missing in payload: ${LAUNCHERS_SRC}"
    fi

    local f src dst
    for f in "${LAUNCHER_FILES[@]}"; do
        src="${LAUNCHERS_SRC}/${f}"
        dst="${bin}/${f}"
        if [[ ! -r "$src" ]]; then
            fail 37 "launcher wrapper missing in payload: ${src}"
        fi
        install -m 0755 -o "${SUDO_USER:-${USER}}" -g staff "$src" "$dst"
        log "INFO installed launcher: ${f}"
    done

    # 9th wrapper — feedback_loop_daemon, copied from the deploy/ tree
    # (canonical D-14 PR 4b launcher; uses file path to dodge the
    # hyphenated-package import issue).
    local fbd_src="${MG_PKG_PAYLOAD}/deploy/feedback_loop_daemon_launcher.sh"
    local fbd_dst="${bin}/feedback_loop_daemon_launcher.sh"
    if [[ ! -r "$fbd_src" ]]; then
        fail 37 "feedback_loop_daemon launcher missing in payload: ${fbd_src}"
    fi
    install -m 0755 -o "${SUDO_USER:-${USER}}" -g staff "$fbd_src" "$fbd_dst"
    log "INFO installed launcher: feedback_loop_daemon_launcher.sh (from deploy/)"

    chown -R "${SUDO_USER:-${USER}}:staff" "$bin"
    log "INFO installed 9 launcher wrappers in ${bin}"
}

step_install_plists_and_bootstrap() {
    install -d -m 0755 "$PLISTS_DEST"

    # 8 plists ship from this PR's resources/launchd dir (PR #74). The
    # 9th (feedback-loop-daemon) ships from deploy/ where PR #41 put it.
    local label src
    for label in "${PLIST_LABELS[@]}"; do
        if [[ "$label" == "com.miningguardian.feedback-loop-daemon" ]]; then
            src="${MG_PKG_PAYLOAD}/deploy/${label}.plist"
        else
            src="${PLISTS_SRC}/${label}.plist"
        fi
        if [[ ! -r "$src" ]]; then
            fail 37 "plist missing in payload: ${src}"
        fi
        install -m 0644 -o root -g wheel "$src" "${PLISTS_DEST}/${label}.plist"
        log "INFO installed plist: ${label}.plist"
    done
    log "INFO installed ${#PLIST_LABELS[@]} launchd plists into $PLISTS_DEST"

    # bootout any previous load (idempotent re-install support), then
    # bootstrap each one fresh. Order here mirrors PLIST_LABELS so the
    # log timeline reads the same as the install matrix in the runbook.
    for label in "${PLIST_LABELS[@]}"; do
        if /bin/launchctl print "system/${label}" >/dev/null 2>&1; then
            /bin/launchctl bootout  "system/${label}" 2>/dev/null || true
        fi
        if ! /bin/launchctl bootstrap system "${PLISTS_DEST}/${label}.plist" \
                2>&1 | tee -a "$MG_INSTALL_LOG"; then
            fail 34 "launchctl bootstrap failed for ${label}"
        fi
        log "INFO bootstrapped ${label}"
    done
}

step_write_install_receipt() {
    local receipt_dir="/etc/mining-guardian"
    install -d -m 0755 "$receipt_dir"
    local receipt="${receipt_dir}/install-receipt.json"

    # version + git SHA come from a small file the build script wrote
    # into the payload (so the receipt knows exactly what was installed
    # without having to ship .git/ in the .pkg).
    local stamp_file="${MG_PKG_PAYLOAD}/BUILD_STAMP.json"
    local stamp_payload="{}"
    if [[ -r "$stamp_file" ]]; then
        stamp_payload="$(cat "$stamp_file")"
    fi

    cat > "$receipt" <<EOF
{
  "installed_at_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "ram_tier_gb": ${MG_INSTALL_RAM_TIER:-null},
  "llm_model": "${MG_INSTALL_LLM_MODEL:-unknown}",
  "install_root": "${MG_INSTALL_ROOT}",
  "service_count": ${#PLIST_LABELS[@]},
  "build_stamp": ${stamp_payload}
}
EOF
    chmod 0644 "$receipt"
    log "INFO wrote install receipt: ${receipt}"
}

step_baseline_scan() {
    # Fire a single scan so the dashboard has data on first load. We do
    # NOT block on its result — if it fails the operator can re-run from
    # the dashboard. We DO log the outcome.
    log "INFO triggering first-run baseline scan (non-blocking)"
    # Quoted because MG_INSTALL_ROOT now contains a space
    # ("/Library/Application Support/MiningGuardian" — B-13 fix, v1.0.1).
    sudo -u "${SUDO_USER:-${USER}}" \
        "${MG_INSTALL_ROOT}/venv/bin/python" \
        "${MG_INSTALL_ROOT}/core/mining_guardian.py" --once \
        >> "${MG_INSTALL_LOG}" 2>&1 &
    disown
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    _setup_log
    log "Mining Guardian postinstall starting (pid=$$) — Bucket 6 refresh, 9 services"
    log "PKG_PATH=${PKG_PATH} TARGET=${TARGET_VOLUME} INSTALL_TARGET_DIR=${INSTALL_TARGET_DIR}"

    step_source_env
    step_load_libs
    step_layout_install_root
    step_drop_dotenv
    step_provision_postgres
    step_apply_migrations
    step_install_ollama_and_pull_model
    step_install_launcher_wrappers
    step_install_plists_and_bootstrap
    step_write_install_receipt
    step_baseline_scan

    log "All postinstall steps complete. Mining Guardian is running."
    log "Services bootstrapped: ${#PLIST_LABELS[@]}"
    log "Dashboard:    http://127.0.0.1:8080/"
    log "Approval API: http://127.0.0.1:8081/"
    log "Logs:         ${MG_INSTALL_ROOT}/logs/"
    return 0
}

main "$@"
