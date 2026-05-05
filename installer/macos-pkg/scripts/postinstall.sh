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
#   1b. Read + validate the customer-info Desktop conf at
#       /Users/${SUDO_USER}/Desktop/MiningGuardian.conf (D-18 Gap 1).
#       Mirrors B-2 validation rules from setup.sh::mg_validate_site_config.
#       Aborts with a Cocoa dialog + exit 41 on missing / invalid file.
#       Runs BEFORE any system-state change so a bad config never leaves
#       the box half-installed.
#   2. Stand up Colima + the bundled Postgres container (offline).
#   3. Apply every <payload>/migrations/*.sql in lexical order against
#      the operational `mining_guardian` DB (each is idempotent).
#   3b. Create the catalog DB `mining_guardian_catalog`, apply the
#      catalog schema bundle (deploy_schema.sql), and seed the 320-row
#      Bitcoin SHA-256 baseline (seed_miner_models.sql) — D-18 Gap 2.
#      Without this, hardware.miner_models is empty on the customer
#      Mini and the AI tier sees every miner as "unknown."
#   4. Install Ollama and pull the selected LLM model (the ONE network
#      step at first-run; loud failure if unreachable).
#   5. Copy the 8 pre-written launcher wrappers from the .pkg payload
#      into ${MG_INSTALL_ROOT}/bin/, then generate the 9th wrapper
#      (feedback_loop_daemon_launcher.sh) inline.
#   6. Create ${MG_INSTALL_ROOT}/venv from a Homebrew python3.12 and
#      pip-install the full dependency set from vendored wheels at
#      <payload>/python-wheels/ (D-18 Gap 5 — closes the v1.0.2 audit
#      finding that every launchd launcher wrapper was crash-looping
#      because the venv it sources never existed).
#   7. Install the 10 launchd service plists and load them with launchctl
#      bootstrap.
#   7b. Install the 11 launchd scheduled-job plists (D-18 Gap 4 / P-007 —
#       replaces the legacy setup.sh phase_10 cron block) and bootstrap
#       them after the service plists. One generic launcher
#       (scheduled_job_launcher.sh) serves all 11 plists; per-job knobs
#       live in StartCalendarInterval/StartInterval inside each plist.
#       Plists ship under <payload>/resources/launchd/scheduled/.
#   8. Drop /etc/mining-guardian/install-receipt.json with git SHA,
#      version, install timestamp, RAM tier, LLM model.
#   9. Fire a first-run baseline scan so the operator sees green tiles
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
#   38     — Python venv create or vendored pip install failed (D-18 Gap 5)
#   39     — catalog DB / schema / seed apply failed (D-18 Gap 2)
#   40     — scheduled-job plist install or bootstrap failed (D-18 Gap 4)
#   41     — customer-info Desktop conf missing or invalid (D-18 Gap 1)
#
# Vision Anchor 7 honored: only one network call (model pull); every
# other byte is vendored inside the .pkg.
# Vision Anchor 6 honored: no altcoin paths anywhere in the install.
#
# P-016 (2026-05-05) — TWO independent bugs, both addressed in one PR.
# The cf1691e Mac mini install showed only `INFO loaded helper libs` in
# postinstall log, then 600 s of silence, then a PackageKit "exceeded
# 600 seconds of runtime" kill. No FATAL line. The 600-second timeout
# rules out a fast `set -u` crash; bash didn't error out, the script
# was still alive when PackageKit killed it.
#
#   Bug A (the actual hang) — `_cocoa_alert` runs `osascript display
#   dialog` synchronously with no timeout. Postinstall runs as root with
#   no Window Server connection, so `display dialog` blocks forever
#   waiting for a click that can't come. PackageKit's 600 s watchdog
#   eventually kills the whole script. Fix: hardened `_cocoa_alert`
#   with three bounds — `with giving up after 5` (AppleScript), a
#   pure-bash 10 s watchdog (no coreutils `timeout(1)` dependency), and
#   delivery routed through the GUI console user via launchctl asuser
#   so the dialog can actually render when one is logged in.
#
#   Bug B (the wrong target file) — Installer.app exports `USER=root`
#   but does NOT export `SUDO_USER`, so the legacy `${SUDO_USER:-${USER}}`
#   resolves to `root`, and the script reads
#   `/Users/root/Desktop/MiningGuardian.conf` — a file that never exists.
#   Even after fixing Bug A, the install would correctly fail 41 instead
#   of finding the customer's real conf. Fix: `_resolve_install_user()`
#   resolves the operator account via three bounded probes (SUDO_USER →
#   /dev/console owner → /Users/*/Desktop scan) and exports
#   MG_INSTALL_OPERATOR_USER for every later step.
#
# An `INFO env probe` log line in main() makes any future stripped-env
# regression debuggable from the postinstall log alone.

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

# The payload directory at install time — this is where Installer.app
# laid down everything we vendored: Colima, Ollama, the Postgres image,
# the migration .sql files, intelligence-catalog seed data, deploy/
# tree, python-wheels/, requirements.txt, BUILD_STAMP.json.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#
# P-017 (2026-05-05) — `MG_PKG_PAYLOAD` resolution rewritten.
#
# The legacy `${SCRIPT_DIR}/../payload` was wrong for the .pkg install
# path. With `pkgbuild --root ${PAYLOAD_DIR} --scripts ${SCRIPTS_DIR}
# --install-location "/Library/Application Support/MiningGuardian"`,
# Installer.app at install time:
#   * extracts the *scripts* archive into a private sandbox like
#     /tmp/PKInstallSandbox.<rand>/Scripts/com.miningguardian.installer.core.<rand>/
#     and runs preinstall/postinstall from there;
#   * extracts the *payload* archive directly to the install location
#     `/Library/Application Support/MiningGuardian/`.
#
# Those are TWO DIFFERENT directories. `${SCRIPT_DIR}/../payload`
# resolves to a path inside the scripts sandbox that does not exist —
# the scripts sandbox holds only the scripts archive contents, never the
# payload. The 9318062 install attempt on the customer Mini (the first
# build whose postinstall got past P-016 to actually run the colima step)
# exited 31 in `install_colima_runtime` with `vendored colima runtime
# not found at .../Scripts/...../../payload/runtime/colima`. Earlier
# builds in the train (a35728d/2b48f98/cf1691e) failed before this code
# ran — P-013/P-015/P-016 each blocked the install ahead of step 31 — so
# this regression was not visible until P-016 cleared the path.
#
# The payload is at the install location at install time. Same path as
# MG_INSTALL_ROOT. We export both so anything sourcing the helper libs
# below (install_colima.sh, install_ollama.sh) sees the correct paths
# without having to know the pkgbuild internals.
#
# Fallback: if MG_INSTALL_ROOT/runtime/ is absent (e.g. dev / smoke-test
# invocations of postinstall.sh outside of a real .pkg install where the
# payload was never laid down), fall back to ${SCRIPT_DIR}/../payload —
# this matches the historical dev-time path layout used by the test
# suites in tests/installer/. Production .pkg installs always take the
# install-root branch.
if [[ -d "${MG_INSTALL_ROOT}/runtime" ]]; then
    export MG_PKG_PAYLOAD="${MG_INSTALL_ROOT}"
else
    export MG_PKG_PAYLOAD="${SCRIPT_DIR}/../payload"
fi

readonly LIB_COLIMA="${SCRIPT_DIR}/lib/install_colima.sh"
readonly LIB_OLLAMA="${SCRIPT_DIR}/lib/install_ollama.sh"

# launchd plist staging — copied INTO LaunchDaemons/ at install time.
# Source dirs live inside the pkg's Resources tree (set by .pkg build script
# to mirror the repo layout under installer/macos-pkg/resources/).
readonly PLISTS_SRC="${SCRIPT_DIR}/../resources/launchd"
readonly LAUNCHERS_SRC="${SCRIPT_DIR}/../resources/launchd/launchers"
readonly PLISTS_DEST="/Library/LaunchDaemons"

# v1.0.3 D-18 Copy bug 3 / P-008 — bin/uninstall.sh ships from this
# Resources path and lands at ${MG_INSTALL_ROOT}/bin/uninstall.sh. Source
# is committed at installer/macos-pkg/resources/uninstall.sh. Tests in
# tests/installer/test_uninstall_script.sh assert it exists with mode
# 0755 in the source tree.
readonly UNINSTALL_SH_SRC="${SCRIPT_DIR}/../resources/uninstall.sh"

# Bucket 6: 9 services. v1.0.3 D-19 (P-006): 10th service added — the
# customer operator console (com.miningguardian.console).
# The 9 plists that ship from installer/macos-pkg/resources/launchd/ are
# listed first; the 10th (feedback-loop-daemon, PR #41) ships from
# deploy/ via the payload.
readonly PLIST_LABELS=(
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

# 9 launcher wrappers shipped verbatim from PR #74 (Bucket 6a) plus the
# v1.0.3 D-19 console launcher. The filenames mirror the plist labels
# with hyphens swapped for underscores and `_launcher.sh` appended. The
# 10th launcher (feedback_loop_daemon) is generated inline below for
# parity with the other 9.
#
# v1.0.3 D-18 Gap 4 / P-007 also adds `scheduled_job_launcher.sh` — a
# generic wrapper used by all 11 scheduled-job plists (replaces the
# legacy setup.sh phase_10 cron block). One launcher serves all 11
# plists; per-job knobs live in the plists themselves.
readonly LAUNCHER_FILES=(
    "scanner_launcher.sh"
    "dashboard_api_launcher.sh"
    "approval_api_launcher.sh"
    "slack_listener_launcher.sh"
    "slack_commands_launcher.sh"
    "overnight_automation_launcher.sh"
    "alerts_launcher.sh"
    "intelligence_report_launcher.sh"
    "console_launcher.sh"
    "scheduled_job_launcher.sh"
)

# v1.0.3 D-18 Gap 4 / P-007 — scheduled-job plists.
# Source dir: installer/macos-pkg/resources/launchd/scheduled/
# These replace the 11 crontab entries in setup.sh::phase_10_cron. Each
# plist invokes scheduled_job_launcher.sh with the entrypoint + label
# baked into ProgramArguments, so adding a 12th scheduled job is one new
# plist + one new SCHEDULED_PLIST_LABELS row, no launcher edit required.
#
# Labels match the plist_label values declared by the operator console
# (console/task_registry.py). Drift here breaks the console's
# /tasks page launchctl probe.
readonly SCHEDULED_PLISTS_SRC="${SCRIPT_DIR}/../resources/launchd/scheduled"
readonly SCHEDULED_PLIST_LABELS=(
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
# Operator-user resolver (P-016 — Bug B)
# ---------------------------------------------------------------------------
#
# Installer.app runs postinstall as root with a stripped environment: it
# does NOT export SUDO_USER (Installer.app does not invoke scripts via
# sudo) but does export USER=root. The legacy `${SUDO_USER:-${USER}}`
# pattern therefore evaluates to `root` and the script reads
# `/Users/root/Desktop/MiningGuardian.conf` — a file that does not exist
# on the customer Mini, where the conf lives at
# `/Users/miningguardian/Desktop/MiningGuardian.conf` (Rob confirmed,
# 2026-05-04). On the cf1691e attempt the conf-not-found path then hit
# the synchronous osascript hang in `_cocoa_alert` (see Bug A above).
# This resolver fixes the wrong-target-file half independently.
#
# Three bounded probes, none of which reference unset variables:
#   1. SUDO_USER (set when Rob runs `sudo installer ...`; covers the
#      preferred install path).
#   2. /dev/console owner via `stat -f '%Su' /dev/console` (the GUI
#      logged-in user; macOS exposes this without env vars).
#   3. /Users/*/Desktop/MiningGuardian.conf scan (last-ditch; finds the
#      operator by where they put the conf).
#
# Returns "root" only when every probe failed AND no Desktop/conf was
# located — at which point the conf-existence check below fails cleanly
# with exit 41 and a logged FATAL (and the now-bounded `_cocoa_alert`
# guarantees the script returns within ~10 s instead of hanging).
_resolve_install_user() {
    local u=""
    if [[ -n "${SUDO_USER:-}" ]]; then
        u="$SUDO_USER"
    fi
    if [[ -z "$u" || "$u" == "root" ]]; then
        if [[ -e /dev/console ]]; then
            u="$(/usr/bin/stat -f '%Su' /dev/console 2>/dev/null || true)"
        fi
    fi
    if [[ -z "$u" || "$u" == "root" ]]; then
        local d
        for d in /Users/*; do
            [[ -e "${d}/Desktop/MiningGuardian.conf" ]] || continue
            u="$(basename "$d")"
            break
        done
    fi
    if [[ -z "$u" ]]; then
        u="root"
    fi
    printf '%s' "$u"
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
    chown -R "${MG_INSTALL_OPERATOR_USER}:staff" "$MG_INSTALL_ROOT"
    log "INFO laid out install root at ${MG_INSTALL_ROOT}"
}

_cocoa_alert() {
    # Best-effort macOS GUI dialog.
    #
    # P-016 (2026-05-05) HARD CORRECTNESS FIX. The original implementation
    # blocked indefinitely on the cf1691e Mac mini install: postinstall runs
    # as root with no Window Server connection, `osascript display dialog`
    # waits forever for a click that can never come from root, and the only
    # bound is PackageKit's 600-second postinstall watchdog. install.log
    # showed `PKInstallTask exceeded its 600 seconds of runtime` and no
    # FATAL line — proof the script never returned from osascript.
    #
    # Three layers of bounding so this can never hang again:
    #
    #   1. AppleScript-level: `with giving up after 5` — the dialog
    #      auto-dismisses after 5 seconds even if osascript IS connected
    #      to a Window Server. Caps the time the customer can stare at
    #      a dialog that root posted into a session it doesn't own.
    #
    #   2. Process-level: a backgrounded osascript subprocess + a bash
    #      watchdog that kills it after 10 wall-clock seconds. macOS
    #      does not ship coreutils `timeout(1)` so we cannot rely on it;
    #      this pure-bash wrapper has no external-binary dependency.
    #
    #   3. Delivery-level: route through the GUI logged-in user via
    #      `launchctl asuser <uid> sudo -u <user> osascript ...` so the
    #      script actually has a Window Server to talk to. Falls back to
    #      raw osascript only if no console user is resolvable.
    #
    # Any failure (including timeout) is swallowed — the FATAL log line
    # from fail() is the contract, the dialog is best-effort UX.
    local title="$1"; shift
    local msg="$*"

    if ! command -v /usr/bin/osascript >/dev/null 2>&1; then
        return 0
    fi

    local script
    script="display dialog \"${msg//\"/\\\"}\" with title \"${title//\"/\\\"}\" with icon stop buttons {\"OK\"} default button \"OK\" giving up after 5"

    # Probe for a console GUI user. /dev/console owner is what's logged
    # in at the Aqua login window. id -u resolves the uid for launchctl
    # asuser. If either fails, fall through to raw osascript with the
    # bash watchdog still in effect — the dialog won't render but the
    # function will return within ~10s.
    local console_user="" console_uid=""
    console_user="$(/usr/bin/stat -f '%Su' /dev/console 2>/dev/null || true)"
    if [[ -n "${console_user}" && "${console_user}" != "root" ]]; then
        console_uid="$(/usr/bin/id -u "${console_user}" 2>/dev/null || true)"
    fi

    # Run osascript backgrounded; bash watchdog enforces the wall-clock cap.
    # set -e is on, so we explicitly tolerate non-zero from every step.
    local osa_pid
    if [[ -n "${console_uid}" ]]; then
        ( /bin/launchctl asuser "${console_uid}" \
            /usr/bin/sudo -u "${console_user}" \
            /usr/bin/osascript -e "${script}" \
            >/dev/null 2>&1 ) &
    else
        # Last-resort fallback. Will likely no-op (root has no Window
        # Server) but the watchdog below guarantees we return within ~10s.
        ( /usr/bin/osascript -e "${script}" >/dev/null 2>&1 ) &
    fi
    osa_pid=$!

    # Watchdog: poll once per second up to 10 seconds, then SIGKILL the
    # whole process group. Last `wait` swallows the exit status so this
    # function always returns 0 to the caller.
    local i=0
    while (( i < 10 )); do
        if ! kill -0 "$osa_pid" 2>/dev/null; then
            break
        fi
        sleep 1
        i=$(( i + 1 ))
    done
    if kill -0 "$osa_pid" 2>/dev/null; then
        kill -KILL "$osa_pid" 2>/dev/null || true
    fi
    wait "$osa_pid" 2>/dev/null || true
    return 0
}

_conf_fail() {
    # D-18 Gap 1 — customer-info collection. On any failure: surface a
    # Cocoa dialog AND log the specific reason, then exit 41.
    local msg="$1"
    _cocoa_alert "Mining Guardian — install aborted" \
        "Customer-info file problem:\n\n${msg}\n\nFix the file at ~/Desktop/MiningGuardian.conf and run the installer again. No system changes have been made yet.\n\nDetails: ${MG_INSTALL_LOG}"
    fail 41 "customer-info Desktop conf: ${msg}"
}

# Source a key=value config file safely (bash, no eval gymnastics).
# Mirrors scripts/setup.sh::mg_source_config so both install paths agree
# on which keys exist and how unknown keys are handled.
_conf_source() {
    local cf="$1"
    [[ ! -r "$cf" ]] && _conf_fail "config file not readable: ${cf}"

    # Reset every supported key first so a missing line means "unset".
    CUSTOMER_NAME=""; AMS_URL=""; AMS_EMAIL=""; AMS_PASSWORD=""; AMS_WORKSPACE_ID=""
    SLACK_WEBHOOK_URL=""; SLACK_BOT_TOKEN=""; SLACK_SIGNING_SECRET=""
    SLACK_APP_TOKEN=""; AUTHORIZED_SLACK_USER_IDS=""
    SCAN_INTERVAL=""; MG_DRY_RUN=""

    local line key val
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Strip leading/trailing whitespace, skip blanks and comments.
        [[ -z "${line// }" ]] && continue
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        if [[ "$line" =~ ^[[:space:]]*([A-Z_][A-Z0-9_]*)[[:space:]]*=[[:space:]]*(.*)$ ]]; then
            key="${BASH_REMATCH[1]}"; val="${BASH_REMATCH[2]}"
            # Strip surrounding single OR double quotes if present.
            val="${val#\"}"; val="${val%\"}"
            val="${val#\'}"; val="${val%\'}"
            case "$key" in
                CUSTOMER_NAME|AMS_URL|AMS_EMAIL|AMS_PASSWORD|AMS_WORKSPACE_ID|\
                SLACK_WEBHOOK_URL|SLACK_BOT_TOKEN|SLACK_SIGNING_SECRET|\
                SLACK_APP_TOKEN|AUTHORIZED_SLACK_USER_IDS|SCAN_INTERVAL|MG_DRY_RUN)
                    printf -v "$key" '%s' "$val"
                    ;;
                *)
                    log "WARN unknown config key ignored: ${key}"
                    ;;
            esac
        fi
    done < "$cf"
}

# Validate the values we sourced. Mirrors scripts/setup.sh::mg_validate_site_config
# so the .pkg path enforces the same B-2 rules as the operator-side
# setup.sh path. Aborts on the first failure with a specific message.
_conf_validate() {
    [[ -z "${CUSTOMER_NAME:-}" ]]              && _conf_fail "CUSTOMER_NAME is required."
    [[ -z "${AMS_URL:-}" ]]                    && AMS_URL="https://api.bixbit.io/api/v1"
    [[ ! "${AMS_URL}" =~ ^https?:// ]]         && _conf_fail "AMS_URL must start with http:// or https:// (got: ${AMS_URL})"
    [[ -z "${AMS_EMAIL:-}" ]]                  && _conf_fail "AMS_EMAIL is required."
    [[ ! "${AMS_EMAIL}" =~ @ ]]                && _conf_fail "AMS_EMAIL must contain '@' (got: ${AMS_EMAIL})"
    [[ -z "${AMS_PASSWORD:-}" ]]               && _conf_fail "AMS_PASSWORD is required."
    [[ -z "${AMS_WORKSPACE_ID:-}" ]]           && _conf_fail "AMS_WORKSPACE_ID is required."
    [[ ! "${AMS_WORKSPACE_ID}" =~ ^[0-9]+$ ]]  && _conf_fail "AMS_WORKSPACE_ID must be an integer (got: ${AMS_WORKSPACE_ID})"
    [[ -z "${SLACK_WEBHOOK_URL:-}" ]]          && _conf_fail "SLACK_WEBHOOK_URL is required."
    [[ ! "${SLACK_WEBHOOK_URL}" =~ ^https://hooks\.slack\.com/ ]] && \
        _conf_fail "SLACK_WEBHOOK_URL must start with https://hooks.slack.com/ (got: ${SLACK_WEBHOOK_URL})"
    [[ -z "${SLACK_BOT_TOKEN:-}" ]]            && _conf_fail "SLACK_BOT_TOKEN is required."
    [[ ! "${SLACK_BOT_TOKEN}" =~ ^xoxb- ]]     && _conf_fail "SLACK_BOT_TOKEN must start with 'xoxb-' (got: ${SLACK_BOT_TOKEN:0:8}...)"
    [[ -z "${SLACK_SIGNING_SECRET:-}" ]]       && _conf_fail "SLACK_SIGNING_SECRET is required."
    [[ -z "${AUTHORIZED_SLACK_USER_IDS:-}" ]]  && _conf_fail "AUTHORIZED_SLACK_USER_IDS is required (at least one Slack user ID)."
    SCAN_INTERVAL="${SCAN_INTERVAL:-300}"
    [[ ! "${SCAN_INTERVAL}" =~ ^[0-9]+$ ]]     && _conf_fail "SCAN_INTERVAL must be an integer seconds value (got: ${SCAN_INTERVAL})"
    MG_DRY_RUN="${MG_DRY_RUN:-true}"
    case "$MG_DRY_RUN" in
        true|false) ;;
        *) _conf_fail "MG_DRY_RUN must be 'true' or 'false' (got: ${MG_DRY_RUN})" ;;
    esac
    if [[ -n "${SLACK_APP_TOKEN:-}" && ! "${SLACK_APP_TOKEN}" =~ ^xapp- ]]; then
        _conf_fail "SLACK_APP_TOKEN, if set, must start with 'xapp-' (got: ${SLACK_APP_TOKEN:0:8}...)"
    fi
}

step_collect_customer_info() {
    # D-18 Gap 1 — customer-info collection (closes audit Section 5 / Gap 1).
    #
    # The .pkg path (this script) used to write a `.env` with ONLY
    # MG_DB_PASSWORD + Postgres connection bits, leaving every AMS_*,
    # SLACK_*, and customer-tunable key empty. Every launchd service
    # crash-looped on first start because its launcher could not reach
    # AMS or Slack (audit Gap 1 / Integration bug 4 — BLOCKER).
    #
    # Approach (locked in D-18, 2026-05-03):
    #   * Operator hands the customer a USB stick (or AirDrop) with a
    #     pre-filled `MiningGuardian.conf` — see
    #     `installer/macos-pkg/resources/MiningGuardian.conf.template`.
    #   * Customer drops the file on Desktop, double-clicks the .pkg.
    #   * This step reads `/Users/${SUDO_USER}/Desktop/MiningGuardian.conf`,
    #     validates per the same B-2 rules `setup.sh::mg_validate_site_config`
    #     enforces, and exports every sourced value for `step_drop_dotenv`
    #     to consume.
    #   * On any failure: surface a Cocoa dialog telling the customer
    #     exactly what's wrong, log the same reason, exit 41. No system
    #     state has changed at this point — refer to main() ordering:
    #     this step runs BEFORE `step_layout_install_root`, BEFORE
    #     `step_provision_postgres`, etc.
    #
    # Vision Anchor 2 (Mac Mini IS the product) — install must be
    # easy enough for someone who barely knows a computer. The Cocoa
    # dialog tells the customer where the file should be and what
    # specifically failed validation (matching message wording the
    # operator pre-trains the customer on).
    local desktop_user="${MG_INSTALL_OPERATOR_USER}"
    local conf_path="/Users/${desktop_user}/Desktop/MiningGuardian.conf"

    if [[ ! -e "$conf_path" ]]; then
        _conf_fail "${conf_path} not found. Place the pre-filled MiningGuardian.conf on the Desktop and run the installer again."
    fi
    if [[ ! -r "$conf_path" ]]; then
        _conf_fail "${conf_path} exists but is not readable by root. Check file permissions."
    fi

    log "INFO reading customer config: ${conf_path}"
    _conf_source "$conf_path"
    _conf_validate

    # Export every sourced value so step_drop_dotenv (and any future
    # steps) see them without re-sourcing. Customer-tunable values only;
    # secrets (MG_DB_PASSWORD / CATALOG_API_KEY / INTERNAL_API_SECRET)
    # are generated in step_drop_dotenv itself.
    export CUSTOMER_NAME AMS_URL AMS_EMAIL AMS_PASSWORD AMS_WORKSPACE_ID
    export SLACK_WEBHOOK_URL SLACK_BOT_TOKEN SLACK_SIGNING_SECRET
    export SLACK_APP_TOKEN AUTHORIZED_SLACK_USER_IDS
    export SCAN_INTERVAL MG_DRY_RUN

    log "INFO customer config OK: site='${CUSTOMER_NAME}' ams='${AMS_URL}' dry_run='${MG_DRY_RUN}'"
}

step_drop_dotenv() {
    # D-18 Gap 1 + Integration bugs 1, 2, 4 (BLOCKERS — audit Section 5).
    #
    # Generates the canonical /Library/Application Support/MiningGuardian/.env
    # used by every LaunchDaemon launcher wrapper. Shape MUST match
    # scripts/setup.sh::phase_07_secrets so both install paths converge —
    # the Python codebase reads ONE set of env keys, regardless of which
    # installer wrote them.
    #
    # Per-install secrets are generated HERE (Integration bug 1 fix —
    # no out-of-band /tmp/mg_install_env_secret staging step):
    #
    #   * MG_DB_PASSWORD     — fresh openssl rand -hex 32; no two sites
    #                          share a password. Replaces the leaked
    #                          MiningGuardian2026! (CRIT-1 / S-1).
    #   * CATALOG_API_KEY    — fresh openssl rand -hex 32. Closes S-6 —
    #                          never the known default.
    #   * INTERNAL_API_SECRET — fresh openssl rand -hex 32. Used by
    #                          approval_api.py verify_internal()
    #                          fail-closed check.
    #
    # Customer-tunable values come from `step_collect_customer_info`
    # (Desktop conf — D-18 Gap 1).
    #
    # Postgres user keys (Integration bug 2 fix):
    #   * GUARDIAN_PG_USER=mg AND PGUSER=mg are BOTH written so the Python
    #     codebase (which reads GUARDIAN_PG_USER per core/database_pg.py
    #     and dashboard-api) and the bundled psql container (initdb'd as
    #     POSTGRES_USER=mg in lib/install_colima.sh L172) both see the
    #     correct user. Dual-naming is documented as tech debt in
    #     MG_UNIFIED_TODO_LIST; collapse to a single key once the
    #     codebase migration completes.
    #
    # All values land at .env mode 0600, owner ${SUDO_USER}:staff (the
    # services run as that user via launchd). Never logged. Never
    # committed.
    if ! command -v openssl >/dev/null 2>&1; then
        fail 31 "openssl not on PATH; cannot generate per-install secrets"
    fi
    local MG_DB_PASSWORD CATALOG_API_KEY INTERNAL_API_SECRET
    MG_DB_PASSWORD="$(openssl rand -hex 32)"
    CATALOG_API_KEY="$(openssl rand -hex 32)"
    INTERNAL_API_SECRET="$(openssl rand -hex 32)"

    local env_file="${MG_INSTALL_ROOT}/.env"
    # Subshell redirect — no secret value ever touches this script's
    # stdout. Heredoc body MUST stay aligned with setup.sh::phase_07_secrets
    # (any drift = launchd services crash on first start because the
    # Python code looks for keys this file did not write).
    cat > "$env_file" <<EOF
# /Library/Application Support/MiningGuardian/.env  mode=0600  owner=${MG_INSTALL_OPERATOR_USER}:staff
# Generated by Mining Guardian installer postinstall.sh
# Generated at $(date -u +%Y-%m-%dT%H:%M:%SZ)  Site: ${CUSTOMER_NAME}
# DO NOT COMMIT. DO NOT LOG. DO NOT SHARE.

# AMS — Bitcoin SHA-256 miners only (S-4: no creds in query strings)
AMS_BASE_URL=${AMS_URL}
AMS_EMAIL=${AMS_EMAIL}
AMS_PASSWORD=${AMS_PASSWORD}
AMS_WORKSPACE_ID=${AMS_WORKSPACE_ID}

# Postgres — 127.0.0.1 only (S-13: no Tailscale IPs anywhere)
# Integration bug 2: GUARDIAN_PG_USER + PGUSER both written with the
# same value until the Python-codebase dual-naming cleanup completes.
GUARDIAN_PG_HOST=127.0.0.1
GUARDIAN_PG_PORT=5432
GUARDIAN_PG_USER=mg
GUARDIAN_PG_PASSWORD=${MG_DB_PASSWORD}
GUARDIAN_PG_DBNAME=mining_guardian
GUARDIAN_PG_TEST_DBNAME=mining_guardian_test
GUARDIAN_PG_CATALOG_DBNAME=mining_guardian_catalog
PGHOST=127.0.0.1
PGPORT=5432
PGUSER=mg
PGDATABASE=mining_guardian
MG_DB_PASSWORD=${MG_DB_PASSWORD}

# Slack — all values customer-specific (do not copy from VPS; §6.3)
SLACK_WEBHOOK_URL=${SLACK_WEBHOOK_URL}
SLACK_BOT_TOKEN=${SLACK_BOT_TOKEN}
SLACK_SIGNING_SECRET=${SLACK_SIGNING_SECRET}
SLACK_APP_TOKEN=${SLACK_APP_TOKEN:-}
AUTHORIZED_SLACK_USER_IDS=${AUTHORIZED_SLACK_USER_IDS}

# Catalog API key — S-6 fix: generated fresh; crash-on-startup if absent (PR #65/#66)
CATALOG_API_KEY=${CATALOG_API_KEY}

# Internal API secret — approval_api.py verify_internal() fail-closed
INTERNAL_API_SECRET=${INTERNAL_API_SECRET}

# Ollama — local GPU inference on 127.0.0.1 (S-13 fix: no hardcoded Tailscale IPs)
OLLAMA_HOST=http://127.0.0.1:11434

# Runtime config (D-2: auto_approve=false — explicit opt-in required)
MG_DRY_RUN=${MG_DRY_RUN}
MG_SCAN_INTERVAL=${SCAN_INTERVAL}
MG_CUSTOMER_NAME=${CUSTOMER_NAME}
AUTO_APPROVE_ENABLED=false

# Service ports — all 127.0.0.1 (S-13)
GUARDIAN_DASHBOARD_PORT=8585
GUARDIAN_APPROVAL_PORT=8686
GUARDIAN_INTELLIGENCE_PORT=8590

# Install metadata (sourced from preinstall.sh detect_ram.sh — D-13)
MG_INSTALL_RAM_TIER=${MG_INSTALL_RAM_TIER:-}
MG_INSTALL_LLM_MODEL=${MG_INSTALL_LLM_MODEL:-}
EOF
    chmod 0600 "$env_file"
    chown "${MG_INSTALL_OPERATOR_USER}:staff" "$env_file"

    # Defensive: if a stale /tmp/mg_install_env_secret was left from an
    # older v1.0.2 build, scrub it. v1.0.3 postinstall does not consume
    # it (Integration bug 1 fix — secrets are generated in-process).
    if [[ -e "/tmp/mg_install_env_secret" ]]; then
        rm -f "/tmp/mg_install_env_secret" || true
        log "INFO removed stale /tmp/mg_install_env_secret (no longer used by v1.0.3)"
    fi

    log "INFO wrote ${env_file} (mode 0600) with full customer + secret payload"

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
        if ! sudo -u "${MG_INSTALL_OPERATOR_USER}" docker exec -i "$container" \
                psql -U mg -d mining_guardian -v ON_ERROR_STOP=1 < "$sql" \
                2>&1 | tee -a "$MG_INSTALL_LOG"; then
            fail 32 "migration $(basename "$sql") failed"
        fi
    done
    log "INFO all migrations applied"
}

step_provision_catalog_db_and_seed() {
    # D-18 Gap 2 — the v1.0.2 .pkg shipped a Postgres container with only
    # the operational `mining_guardian` DB; the catalog DB
    # `mining_guardian_catalog` (which `hardware.miner_models` lives in)
    # was never created and the 320-row Bitcoin SHA-256 baseline seed
    # (`intelligence-catalog/seed-data/seed_miner_models.sql`) was never
    # applied. Without this, `ai/catalog_context.py` consumers see an
    # empty catalog, every miner is "unknown model," and the Grafana
    # Intelligence Report dropdown is empty (audit Section 5 / Gap 2).
    #
    # This step closes the gap by, in order:
    #   1. Creating the `mining_guardian_catalog` database in the existing
    #      Colima-managed Postgres container (`mining-guardian-db`),
    #      OWNER `mg`. Idempotent — `IF NOT EXISTS` semantics via SELECT.
    #   2. Applying the canonical catalog schema bundle via
    #      `deploy_schema.sql`, which `\ir`-includes
    #      `intelligence_catalog_schema.sql` + v2 + v3 + `staging_schema.sql`,
    #      then performs the manufacturer-brand enum extensions, then
    #      seeds `knowledge.sources`, `knowledge.contributors`, and
    #      `hardware.manufacturers`. All idempotent (`IF NOT EXISTS`,
    #      `ON CONFLICT DO NOTHING`).
    #   3. Applying `seed_miner_models.sql` (320 rows) against the catalog
    #      DB. Idempotent at the row level via the seed's transaction
    #      semantics (each model row is keyed by canonical_name + model
    #      number; re-applies are no-ops on already-seeded models).
    #
    # All three steps target the catalog DB exclusively. The operational
    # DB `mining_guardian` is NOT touched here — its schema was already
    # applied by `step_apply_migrations` (lexical order, all
    # `<payload>/migrations/*.sql`).
    #
    # Source files travel inside the .pkg payload via build_pkg.sh
    # step 4a (`--include 'intelligence-catalog/***'`), so they live at
    #   ${MG_PKG_PAYLOAD}/intelligence-catalog/seed-data/*.sql
    # at install time. No separate payload-staging step is required.
    #
    # Hard rules (Vision Anchor 7 — local-only):
    #   * Network use is the existing Ollama-only budget; this step
    #     issues `psql` against the localhost Colima container ONLY.
    #   * Refuse if any source file is missing — partial catalog seed
    #     would leave the customer Mini in a half-initialized state that
    #     looks healthy at install time but fails the v1.0.3 verification
    #     gate (`SELECT count(*) FROM hardware.miner_models;` must
    #     return 320).
    #   * Idempotent under retries / re-installs.
    #
    # Exit code 39 is reserved for any failure in this step.
    local seed_dir="${MG_PKG_PAYLOAD}/intelligence-catalog/seed-data"
    local schema_file="${seed_dir}/deploy_schema.sql"
    local seed_file="${seed_dir}/seed_miner_models.sql"
    local catalog_db="mining_guardian_catalog"
    local container="mining-guardian-db"

    if [[ ! -d "$seed_dir" ]]; then
        fail 39 "catalog seed directory missing in payload: ${seed_dir} (build_pkg.sh step 4a should have rsync'd intelligence-catalog/***)"
    fi
    if [[ ! -r "$schema_file" ]]; then
        fail 39 "catalog schema deploy file missing: ${schema_file}"
    fi
    if [[ ! -r "$seed_file" ]]; then
        fail 39 "catalog seed file missing: ${seed_file}"
    fi

    # 1. Create the catalog DB. Idempotent via existence check; CREATE
    # DATABASE cannot run inside a transaction, so we issue it with -tAc
    # only when the row count comes back zero.
    local exists
    exists="$(sudo -u "${MG_INSTALL_OPERATOR_USER}" docker exec -i "$container" \
        psql -U mg -d postgres -tAc \
        "SELECT 1 FROM pg_database WHERE datname='${catalog_db}';" \
        2>>"$MG_INSTALL_LOG" || true)"
    exists="$(echo "${exists:-}" | tr -d '[:space:]')"
    if [[ "${exists:-}" != "1" ]]; then
        log "INFO creating catalog database ${catalog_db}"
        # shellcheck disable=SC2024  # log file is owned by root; redirect is opened by parent shell pre-sudo, intentional (matches step_baseline_scan / step_create_venv).
        if ! sudo -u "${MG_INSTALL_OPERATOR_USER}" docker exec -i "$container" \
                psql -U mg -d postgres -v ON_ERROR_STOP=1 -c \
                "CREATE DATABASE ${catalog_db} OWNER mg;" \
                >>"$MG_INSTALL_LOG" 2>&1; then
            fail 39 "CREATE DATABASE ${catalog_db} failed (see ${MG_INSTALL_LOG})"
        fi
    else
        log "INFO catalog database ${catalog_db} already present — re-using"
    fi

    # 2. Apply the catalog schema. deploy_schema.sql uses psql's `\ir`
    # (include relative) directive to pull in the v1/v2/v3 schema files
    # from the same directory; we copy the whole seed-data tree into the
    # container so the relative includes resolve.
    local container_seed_dir="/tmp/mg-catalog-seed-$$"
    # shellcheck disable=SC2024  # see SC2024 disable note above.
    if ! sudo -u "${MG_INSTALL_OPERATOR_USER}" docker exec "$container" \
            mkdir -p "$container_seed_dir" >>"$MG_INSTALL_LOG" 2>&1; then
        fail 39 "could not create staging dir inside container: ${container_seed_dir}"
    fi
    # shellcheck disable=SC2024
    if ! sudo -u "${MG_INSTALL_OPERATOR_USER}" docker cp \
            "${seed_dir}/." "${container}:${container_seed_dir}/" \
            >>"$MG_INSTALL_LOG" 2>&1; then
        fail 39 "docker cp of seed-data into container failed"
    fi

    # deploy_schema.sql contains ALTER TYPE ... ADD VALUE statements that
    # cannot run inside an implicit transaction block. We apply it with
    # ON_ERROR_STOP=0 so the enum-extension warnings do not abort the
    # idempotent re-apply on already-seeded systems; structural CREATE
    # TYPE / CREATE TABLE / CREATE SCHEMA are themselves IF NOT EXISTS.
    log "INFO applying catalog schema (deploy_schema.sql)"
    # shellcheck disable=SC2024
    if ! sudo -u "${MG_INSTALL_OPERATOR_USER}" docker exec -i "$container" \
            psql -U mg -d "$catalog_db" \
            -v ON_ERROR_STOP=0 \
            -f "${container_seed_dir}/deploy_schema.sql" \
            >>"$MG_INSTALL_LOG" 2>&1; then
        fail 39 "deploy_schema.sql apply failed against ${catalog_db}"
    fi

    # 3. Apply the 320-row seed. ON_ERROR_STOP=1 here — the seed file
    # uses `INSERT INTO hardware.miner_models` without ON CONFLICT, but
    # is wrapped in a single BEGIN/COMMIT block so a re-apply against an
    # already-seeded DB will fail cleanly on the first duplicate canonical
    # name. We treat that case as "already seeded — re-use" by checking
    # the row count first.
    local row_count
    row_count="$(sudo -u "${MG_INSTALL_OPERATOR_USER}" docker exec -i "$container" \
        psql -U mg -d "$catalog_db" -tAc \
        "SELECT count(*) FROM hardware.miner_models;" \
        2>>"$MG_INSTALL_LOG" || echo 0)"
    row_count="$(echo "${row_count:-0}" | tr -d '[:space:]')"
    if [[ "${row_count:-0}" -ge 320 ]]; then
        log "INFO catalog already seeded (${row_count} rows) — skipping seed apply"
    else
        log "INFO seeding 320 Bitcoin SHA-256 miner models into ${catalog_db}"
        # shellcheck disable=SC2024
        if ! sudo -u "${MG_INSTALL_OPERATOR_USER}" docker exec -i "$container" \
                psql -U mg -d "$catalog_db" -v ON_ERROR_STOP=1 \
                -f "${container_seed_dir}/seed_miner_models.sql" \
                >>"$MG_INSTALL_LOG" 2>&1; then
            fail 39 "seed_miner_models.sql apply failed against ${catalog_db}"
        fi
    fi

    # Verify final row count meets the v1.0.3 verification-gate floor.
    row_count="$(sudo -u "${MG_INSTALL_OPERATOR_USER}" docker exec -i "$container" \
        psql -U mg -d "$catalog_db" -tAc \
        "SELECT count(*) FROM hardware.miner_models;" \
        2>>"$MG_INSTALL_LOG" || echo 0)"
    row_count="$(echo "${row_count:-0}" | tr -d '[:space:]')"
    if [[ "${row_count:-0}" -lt 320 ]]; then
        fail 39 "catalog seed verification failed: hardware.miner_models has ${row_count} rows (expected >= 320 per D-18 verification gate)"
    fi
    log "INFO catalog seed verified: hardware.miner_models has ${row_count} rows"

    # Best-effort cleanup of the in-container staging dir; not fatal if
    # it fails (the container is ephemeral relative to the install root).
    # shellcheck disable=SC2024
    sudo -u "${MG_INSTALL_OPERATOR_USER}" docker exec "$container" \
        rm -rf "$container_seed_dir" >>"$MG_INSTALL_LOG" 2>&1 || true
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
        install -m 0755 -o "${MG_INSTALL_OPERATOR_USER}" -g staff "$src" "$dst"
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
    install -m 0755 -o "${MG_INSTALL_OPERATOR_USER}" -g staff "$fbd_src" "$fbd_dst"
    log "INFO installed launcher: feedback_loop_daemon_launcher.sh (from deploy/)"

    chown -R "${MG_INSTALL_OPERATOR_USER}:staff" "$bin"
    log "INFO installed 9 launcher wrappers in ${bin}"
}

step_create_venv() {
    # D-18 Gap 5 — every launchd launcher wrapper exec's
    # ${MG_INSTALL_ROOT}/venv/bin/python and exits FATAL when missing
    # (e.g. scanner_launcher.sh line 36-39). The first-run baseline scan
    # in step_baseline_scan also relies on it. v1.0.2 .pkg never created
    # the venv, so every service crash-looped on first start. This step
    # closes that gap.
    #
    # Hard rules:
    #   * No network for pip — vendored wheels only. Vision Anchor 7
    #     (catalog is sacred) extends here: install-time network calls
    #     are budgeted to ONE (the Ollama model pull); pip is not on
    #     that budget. If the wheels payload is missing or the resolver
    #     would need to reach PyPI, this step exits non-zero.
    #   * Python 3.12 is required. The .pkg does not vendor a Python
    #     interpreter (Apple-supplied python3 is 3.9; the operator-side
    #     setup.sh assumes Homebrew python@3.12 from `phase_03_brew_deps`).
    #     v1.0.3 docs the python@3.12 prerequisite in the customer setup
    #     manual; if it is absent at install time, exit with a clear
    #     pointer rather than silently picking a 3.9 interpreter.
    #   * Idempotent. Re-running over an existing venv is a no-op for the
    #     `python -m venv` call (skip-if-present); pip install is run
    #     either way so a partial install heals on re-run.
    #
    # Inputs (all under <payload>/):
    #   python-wheels/      directory of pre-downloaded wheels (sdists are
    #                       NOT permitted — `--only-binary=:all:`).
    #   requirements.txt    pin file the build host wrote during
    #                       step_4_assemble_payload. If absent, falls
    #                       back to <payload>/requirements.txt staged at
    #                       repo root.
    local venv_dir="${MG_INSTALL_ROOT}/venv"
    local wheels_dir="${MG_PKG_PAYLOAD}/python-wheels"
    local req_file="${MG_PKG_PAYLOAD}/requirements.txt"

    if [[ ! -d "$wheels_dir" ]]; then
        fail 38 "vendored python wheels directory missing in payload: ${wheels_dir} (build_pkg.sh step_4_assemble_payload should have copied \${HOME}/MiningGuardian-vendor/python-wheels/)"
    fi

    # Empty-dir guard — find returns 0 even if no .whl files are present;
    # that would cause pip to silently fall through to PyPI on networked
    # hosts. Refuse to proceed.
    local wheel_count
    wheel_count="$(/usr/bin/find "$wheels_dir" -maxdepth 1 -type f -name '*.whl' 2>/dev/null | wc -l | tr -d ' ')"
    if [[ "${wheel_count:-0}" -lt 1 ]]; then
        fail 38 "no .whl files found under ${wheels_dir}; cannot pip install offline"
    fi

    if [[ ! -r "$req_file" ]]; then
        fail 38 "requirements.txt missing in payload: ${req_file}"
    fi

    # Resolve a Python 3.12 interpreter. Order:
    #   1. /opt/homebrew/opt/python@3.12/bin/python3.12 (Apple Silicon Homebrew default)
    #   2. /usr/local/opt/python@3.12/bin/python3.12 (Intel Homebrew fallback; v1.0.3 is Apple-Silicon-only per preinstall gate_apple_silicon, but kept for VM smoke-test paths)
    #   3. `command -v python3.12`
    # We do NOT accept `python3` because Apple-supplied python3 is 3.9 on
    # current macOS and many of the pinned wheels require ≥ 3.12 ABI.
    local py312=""
    local candidate
    for candidate in \
        "/opt/homebrew/opt/python@3.12/bin/python3.12" \
        "/usr/local/opt/python@3.12/bin/python3.12"; do
        if [[ -x "$candidate" ]]; then
            py312="$candidate"
            break
        fi
    done
    if [[ -z "$py312" ]]; then
        py312="$(command -v python3.12 2>/dev/null || true)"
    fi
    if [[ -z "$py312" || ! -x "$py312" ]]; then
        fail 38 "python3.12 not found on this Mac; install Homebrew + python@3.12 before running the .pkg (operator setup manual covers this)"
    fi

    log "INFO using Python interpreter: ${py312} ($(${py312} --version 2>&1))"

    # Create the venv (skip if already present and the python symlink is
    # executable — supports retries / re-installs).
    if [[ -x "${venv_dir}/bin/python" ]]; then
        log "INFO venv already present at ${venv_dir} — re-using"
    else
        if ! "$py312" -m venv "$venv_dir" >>"$MG_INSTALL_LOG" 2>&1; then
            fail 38 "python -m venv failed for ${venv_dir}"
        fi
        log "INFO created venv at ${venv_dir}"
    fi

    # Ownership — the launcher wrappers run as root (LaunchDaemons),
    # but the baseline-scan path drops to ${SUDO_USER}, and operator
    # debug runs the venv as ${SUDO_USER} too. Match the install-root
    # ownership pattern from step_layout_install_root.
    chown -R "${MG_INSTALL_OPERATOR_USER}:staff" "$venv_dir"

    local venv_pip="${venv_dir}/bin/pip"
    if [[ ! -x "$venv_pip" ]]; then
        fail 38 "pip missing inside venv: ${venv_pip}"
    fi

    # Upgrade pip itself from the vendored wheels — keeps the resolver
    # version pinned to whatever build_pkg.sh staged. `--no-index` is the
    # offline guarantee; `--find-links` points at the vendored dir.
    log "INFO upgrading pip from vendored wheels"
    # shellcheck disable=SC2024  # log is owned by root; redirect is opened by parent shell pre-sudo, which is the intended behavior (matches step_baseline_scan).
    if ! sudo -u "${MG_INSTALL_OPERATOR_USER}" \
            "$venv_pip" install \
            --no-index --find-links "$wheels_dir" \
            --upgrade pip \
            >>"$MG_INSTALL_LOG" 2>&1; then
        # Older vendored wheel sets may not include a pip wheel — that
        # is acceptable; the bundled pip from `python -m venv` is fine.
        log "INFO vendored pip upgrade skipped (no pip wheel in payload — using bootstrap pip)"
    fi

    # Install dependencies. `--only-binary=:all:` refuses to fall back to
    # building from source (no compiler on the customer Mini, and would
    # require network anyway). `--no-deps` is NOT used — the vendored
    # wheel set must be the full transitive closure, captured at build
    # time by the operator running `pip download -r requirements.txt -d
    # ${HOME}/MiningGuardian-vendor/python-wheels/` before `make pkg`.
    log "INFO installing python deps from ${req_file} (offline, vendored wheels)"
    # shellcheck disable=SC2024  # log is owned by root; redirect is opened by parent shell pre-sudo, which is the intended behavior (matches step_baseline_scan).
    if ! sudo -u "${MG_INSTALL_OPERATOR_USER}" \
            "$venv_pip" install \
            --no-index --find-links "$wheels_dir" \
            --only-binary=:all: \
            -r "$req_file" \
            >>"$MG_INSTALL_LOG" 2>&1; then
        fail 38 "pip install -r ${req_file} failed (offline); check that vendored wheels cover the full transitive closure"
    fi

    log "INFO venv ready at ${venv_dir} ($(wc -l <"$req_file" | tr -d ' ') requirement lines installed)"
}

step_install_plists_and_bootstrap() {
    install -d -m 0755 "$PLISTS_DEST"

    # 9 plists ship from this PR's resources/launchd dir (PR #74 + the
    # v1.0.3 D-19 console plist). The 10th (feedback-loop-daemon) ships
    # from deploy/ where PR #41 put it.
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

step_install_scheduled_plists_and_bootstrap() {
    # D-18 Gap 4 / P-007 — replace setup.sh::phase_10_cron with launchd.
    #
    # The legacy setup.sh path installed 11 crontab entries via
    # `crontab -` and required the operator to grant Full Disk Access to
    # /usr/sbin/cron in System Settings (macOS 14+ blocks cron from
    # writing /tmp + /var/log without FDA). That path is unsuitable for
    # a customer-facing .pkg install — there is no operator standing by
    # to click through System Settings, the FDA prompt is not surfaceable
    # from postinstall, and silent failure of nightly jobs (deep-dive,
    # briefing, backup) is exactly the "apparent success, real silence"
    # failure mode the v1.0.2 audit flagged.
    #
    # Approach (locked in D-18 Gap 4):
    #   * One plist per scheduled job under
    #     installer/macos-pkg/resources/launchd/scheduled/.
    #   * Each plist uses StartCalendarInterval (or StartInterval=3600
    #     for the hourly benchmark) — launchd is the macOS-native
    #     primitive for scheduled work, no FDA required.
    #   * One generic launcher (`scheduled_job_launcher.sh`) sources
    #     .env, dispatches by file extension (.py → venv python, .sh →
    #     bash), stamps a per-run JSON file under
    #     ${INSTALL_ROOT}/logs/scheduled/ for the operator console.
    #   * Bootstrap order: AFTER the 10 service plists are bootstrapped
    #     (the 10th is the console — D-19 / P-006). If the service
    #     bootstrap fails, the scheduled jobs are not installed; the
    #     install still aborts with the original exit 34, no scheduled
    #     half-state.
    #
    # Idempotent under retries / re-installs: bootout any existing label
    # before bootstrap, identical to step_install_plists_and_bootstrap.
    #
    # Exit 40 is reserved for any failure in this step.

    if [[ ! -d "$SCHEDULED_PLISTS_SRC" ]]; then
        fail 40 "scheduled-plists directory missing in payload: ${SCHEDULED_PLISTS_SRC} (D-18 Gap 4)"
    fi

    install -d -m 0755 "${MG_INSTALL_ROOT}/logs/scheduled"
    chown "${MG_INSTALL_OPERATOR_USER}:staff" "${MG_INSTALL_ROOT}/logs/scheduled"

    local label src
    for label in "${SCHEDULED_PLIST_LABELS[@]}"; do
        src="${SCHEDULED_PLISTS_SRC}/${label}.plist"
        if [[ ! -r "$src" ]]; then
            fail 40 "scheduled plist missing in payload: ${src} (D-18 Gap 4)"
        fi
        install -m 0644 -o root -g wheel "$src" "${PLISTS_DEST}/${label}.plist"
        log "INFO installed scheduled plist: ${label}.plist"
    done
    log "INFO installed ${#SCHEDULED_PLIST_LABELS[@]} scheduled-job launchd plists into ${PLISTS_DEST}"

    # Bootout any previous load (idempotent re-install support), then
    # bootstrap each one fresh.
    for label in "${SCHEDULED_PLIST_LABELS[@]}"; do
        if /bin/launchctl print "system/${label}" >/dev/null 2>&1; then
            /bin/launchctl bootout  "system/${label}" 2>/dev/null || true
        fi
        if ! /bin/launchctl bootstrap system "${PLISTS_DEST}/${label}.plist" \
                2>&1 | tee -a "$MG_INSTALL_LOG"; then
            fail 40 "launchctl bootstrap failed for ${label} (D-18 Gap 4)"
        fi
        log "INFO bootstrapped scheduled plist: ${label}"
    done
}

step_install_uninstall_script() {
    # D-18 Copy bug 3 / P-008 (v1.0.3) — ship a real bin/uninstall.sh in
    # the install root so the conclusion.html `sudo /Library/Application
    # Support/MiningGuardian/bin/uninstall.sh` reference is honored.
    #
    # Source: installer/macos-pkg/resources/uninstall.sh (committed; mode
    # 0755 enforced by tests/installer/test_uninstall_script.sh).
    # Dest:   ${MG_INSTALL_ROOT}/bin/uninstall.sh, root:wheel mode 0755.
    #
    # Owner is root (NOT ${SUDO_USER}) because the script has to run as
    # root via `sudo` and reads /Library/LaunchDaemons; setting it
    # root-owned avoids a stale-permissions trap if the customer's home
    # is moved or their account is renamed post-install.
    local bin="${MG_INSTALL_ROOT}/bin"
    install -d -m 0755 "$bin"
    if [[ ! -r "$UNINSTALL_SH_SRC" ]]; then
        fail 37 "uninstall.sh missing in payload: ${UNINSTALL_SH_SRC} (D-18 Copy bug 3)"
    fi
    install -m 0755 -o root -g wheel "$UNINSTALL_SH_SRC" "${bin}/uninstall.sh"
    log "INFO installed uninstall.sh: ${bin}/uninstall.sh"
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
  "scheduled_job_count": ${#SCHEDULED_PLIST_LABELS[@]},
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
    sudo -u "${MG_INSTALL_OPERATOR_USER}" \
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

    # P-016 — env-state probe. Installer.app's postinstall environment is
    # stripped; SUDO_USER is unset and USER is not reliably exported. Log
    # what we have so future failures are debuggable from the log alone.
    log "INFO env probe: SUDO_USER='${SUDO_USER:-<unset>}' USER='${USER:-<unset>}' LOGNAME='${LOGNAME:-<unset>}' HOME='${HOME:-<unset>}'"

    # P-016 — resolve the operator account ONCE, before any step that
    # needs it. Replaces the 22 in-line `${SUDO_USER:-${USER}}` sites
    # that crashed the script under `set -u` when USER was unset. Export
    # so later steps and helper libs see the same value. Split declare
    # and assign per shellcheck SC2155 (so the resolver's exit status is
    # not masked by `export`).
    MG_INSTALL_OPERATOR_USER="$(_resolve_install_user)"
    export MG_INSTALL_OPERATOR_USER
    log "INFO resolved install operator user: ${MG_INSTALL_OPERATOR_USER}"

    step_source_env
    step_load_libs
    # D-18 Gap 1 — collect + validate customer-info BEFORE any system
    # change. _conf_fail() exits 41 with a Cocoa dialog on missing or
    # invalid Desktop conf, so a bad config never leaves the box
    # half-installed.
    step_collect_customer_info
    step_layout_install_root
    step_drop_dotenv
    step_provision_postgres
    step_apply_migrations
    step_provision_catalog_db_and_seed
    step_install_ollama_and_pull_model
    step_install_launcher_wrappers
    step_create_venv
    step_install_plists_and_bootstrap
    step_install_scheduled_plists_and_bootstrap
    step_install_uninstall_script
    step_write_install_receipt
    step_baseline_scan

    log "All postinstall steps complete. Mining Guardian is running."
    log "Services bootstrapped: ${#PLIST_LABELS[@]}"
    log "Scheduled jobs bootstrapped: ${#SCHEDULED_PLIST_LABELS[@]}"
    log "Dashboard:        http://127.0.0.1:8585/"
    log "Approval API:     http://127.0.0.1:8686/"
    log "Operator console: http://127.0.0.1:8787/"
    log "Logs:             ${MG_INSTALL_ROOT}/logs/"
    return 0
}

main "$@"
