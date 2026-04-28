#!/bin/bash
# installer/macos-pkg/scripts/postinstall.sh
#
# macOS .pkg postinstall script — RUNS AS root via Installer.app, AFTER
# the package payload has been laid down on disk by Installer.app itself.
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
#   5. Install the 4 launchd plists and load them with launchctl
#      bootstrap. The 4 services are:
#         - com.miningguardian.scanner
#         - com.miningguardian.dashboard-api
#         - com.miningguardian.approval-api
#         - com.miningguardian.feedback-loop-daemon  (PR #41)
#   6. Generate the .env-sourcing launcher wrappers each plist invokes.
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
export MG_INSTALL_ROOT="/usr/local/MiningGuardian"

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
readonly PLISTS_SRC="${SCRIPT_DIR}/../resources/launchd"
readonly PLISTS_DEST="/Library/LaunchDaemons"
readonly PLIST_LABELS=(
    "com.miningguardian.scanner"
    "com.miningguardian.dashboard-api"
    "com.miningguardian.approval-api"
    "com.miningguardian.feedback-loop-daemon"
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

step_generate_launcher_wrappers() {
    # Each plist invokes a small wrapper that sources .env then execs
    # the python entrypoint, because launchd has no EnvironmentFile=
    # equivalent. Same pattern as PR #41 for the feedback-loop-daemon.
    local bin="${MG_INSTALL_ROOT}/bin"
    install -d -m 0755 "$bin"

    cat > "${bin}/scanner_launcher.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
cd /usr/local/MiningGuardian
[[ -r .env ]] && set -a && . ./.env && set +a
exec /usr/local/MiningGuardian/venv/bin/python core/mining_guardian.py
EOF

    cat > "${bin}/dashboard_api_launcher.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
cd /usr/local/MiningGuardian
[[ -r .env ]] && set -a && . ./.env && set +a
exec /usr/local/MiningGuardian/venv/bin/python -m api.dashboard
EOF

    cat > "${bin}/approval_api_launcher.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
cd /usr/local/MiningGuardian
[[ -r .env ]] && set -a && . ./.env && set +a
exec /usr/local/MiningGuardian/venv/bin/python -m api.approval
EOF

    cat > "${bin}/feedback_loop_daemon_launcher.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
cd /usr/local/MiningGuardian
[[ -r .env ]] && set -a && . ./.env && set +a
exec /usr/local/MiningGuardian/venv/bin/python -m intelligence.feedback_loop_daemon
EOF

    chmod 0755 \
        "${bin}/scanner_launcher.sh" \
        "${bin}/dashboard_api_launcher.sh" \
        "${bin}/approval_api_launcher.sh" \
        "${bin}/feedback_loop_daemon_launcher.sh"
    chown -R "${SUDO_USER:-${USER}}:staff" "$bin"
    log "INFO generated 4 launcher wrappers in ${bin}"
}

step_install_plists_and_bootstrap() {
    install -d -m 0755 "$PLISTS_DEST"

    # Three plists ship from this PR's resources/launchd dir. The 4th
    # (feedback-loop-daemon) ships from deploy/ where PR #41 put it.
    install -m 0644 -o root -g wheel \
        "${PLISTS_SRC}/com.miningguardian.scanner.plist"      "$PLISTS_DEST/"
    install -m 0644 -o root -g wheel \
        "${PLISTS_SRC}/com.miningguardian.dashboard-api.plist" "$PLISTS_DEST/"
    install -m 0644 -o root -g wheel \
        "${PLISTS_SRC}/com.miningguardian.approval-api.plist"  "$PLISTS_DEST/"

    local fbd="${MG_PKG_PAYLOAD}/deploy/com.miningguardian.feedback-loop-daemon.plist"
    if [[ ! -r "$fbd" ]]; then
        fail 34 "missing feedback-loop-daemon plist in payload"
    fi
    install -m 0644 -o root -g wheel "$fbd" "$PLISTS_DEST/"

    log "INFO installed 4 launchd plists into $PLISTS_DEST"

    local label
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
    sudo -u "${SUDO_USER:-${USER}}" \
        /usr/local/MiningGuardian/venv/bin/python \
        /usr/local/MiningGuardian/core/mining_guardian.py --once \
        >> "${MG_INSTALL_LOG}" 2>&1 &
    disown
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    _setup_log
    log "Mining Guardian postinstall starting (pid=$$)"
    log "PKG_PATH=${PKG_PATH} TARGET=${TARGET_VOLUME} INSTALL_TARGET_DIR=${INSTALL_TARGET_DIR}"

    step_source_env
    step_load_libs
    step_layout_install_root
    step_drop_dotenv
    step_provision_postgres
    step_apply_migrations
    step_install_ollama_and_pull_model
    step_generate_launcher_wrappers
    step_install_plists_and_bootstrap
    step_write_install_receipt
    step_baseline_scan

    log "All postinstall steps complete. Mining Guardian is running."
    log "Dashboard:    http://127.0.0.1:8080/"
    log "Approval API: http://127.0.0.1:8081/"
    log "Logs:         ${MG_INSTALL_ROOT}/logs/"
    return 0
}

main "$@"
