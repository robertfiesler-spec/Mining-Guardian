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
#   6. Create ${MG_INSTALL_ROOT}/venv from the installer-owned Python
#      3.12 runtime at <payload>/runtime/python/bin/python3.12 (P-026)
#      and pip-install the full dependency set from vendored wheels at
#      <payload>/python-wheels/ (D-18 Gap 5 — closes the v1.0.2 audit
#      finding that every launchd launcher wrapper was crash-looping
#      because the venv it sources never existed). Pre-P-026 this step
#      reached for `/opt/homebrew/opt/python@3.12/bin/python3.12` from
#      the customer's Homebrew install — a hidden customer prerequisite
#      that surfaced as a postinstall exit-38 failure on Round 9 of the
#      Mac mini install (2026-05-05). Customers are not expected to have
#      Homebrew or python@3.12; the .pkg now carries its own.
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
#   42     — alias-seed apply failed (P-018D — Tier-1 hardware.model_aliases
#            on catalog DB or Tier-2 mg.model_family_aliases on operational)
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
#
# P-029 (2026-05-06) — shell-safe .env writer + DB-password reconcile +
# config.json materializer. Round-9b smoke on the customer Mac mini
# (postinstall round following 23a5af7) found three follow-on bugs once
# the install completed cleanly:
#
#   Bug 1 — shell-unsafe values in the generated .env. `step_drop_dotenv`
#   wrote `KEY=${VALUE}` raw, so a customer name like `R & D` produced
#   `MG_CUSTOMER_NAME=R & D` on disk. Every launcher wrapper does
#   `set -a; source "${ENV_FILE}"; set +a` — bash interprets the line as
#   `MG_CUSTOMER_NAME=R` (assignment) followed by `&` (background) and
#   `D` (a command). The customer Mini logged
#       /Library/Application Support/MiningGuardian/.env: line 47: D:
#       command not found
#   for every service, exit 127, all 10 LaunchDaemons failed to start.
#   Same trap fires for `&`, `$`, `` ` ``, `"`, `'`, `;`, `(`, `)`, `\`,
#   `*`, `?`, `[`, `]`, `<`, `>`, `|`, `#`, leading/trailing whitespace,
#   and globs that may match a real file. Customer-supplied fields run
#   through `_conf_source` / `_conf_validate` first, but those validators
#   trim only surrounding quote pairs — the value itself can still
#   contain any of the trap characters above. Fix: a `_shq` helper that
#   wraps every value in single quotes (POSIX-portable, the only quoting
#   form bash will not interpret further) and escapes any embedded
#   single quote via the `'\''` close-reopen idiom; pre-compute *_Q
#   variables for every customer-tunable + secret value before the
#   heredoc, and interpolate ONLY the *_Q variant inside the heredoc.
#   The result is bytes that round-trip exactly under `set -a; source`
#   regardless of input. The .env still parses cleanly via
#   `awk -F= '/^KEY=/'` for tooling that grep/sed-extracts a key.
#
#   Bug 2 — stale Postgres password on retry. `provision_postgres`
#   (lib/install_colima.sh L355-369) does `docker rm -f <container>`
#   then `docker run … -v "${pgdata_dir}:/var/lib/postgresql/data" -e
#   POSTGRES_PASSWORD="$MG_DB_PASSWORD"`. Postgres ONLY runs initdb on
#   first boot of a fresh data directory; a re-install over an existing
#   pgdata directory inherits the prior install's role passwords and
#   ignores the new POSTGRES_PASSWORD entirely. Round-9b followed an
#   earlier failed install whose `mg` role still carried the previous
#   `openssl rand -hex 32` value — `psql -U mg` from the dashboard hit
#   `password authentication failed for user "mg"` and the `/` route
#   returned 500. Fix: a new `step_reconcile_postgres_password` runs
#   right after `provision_postgres` returns. It always issues `ALTER
#   USER mg PASSWORD '...'` against the running container. The
#   statement is idempotent and harmless on a brand-new initdb (where
#   the ENV-supplied password is already the same), and self-healing
#   on a re-install over existing pgdata. The password value is sent
#   to psql via stdin (not the command line), so it never appears in
#   `ps` output.
#
#   Bug 3 — no `config.json` materialized at install time. Every
#   long-running service that imports `core.mining_guardian` or
#   `api.approval_api` reads `config.json` from the install root for
#   profile_map, model_aliases, miner_filters, scan/slack intervals,
#   and approval_mode. Pre-P-029 the postinstall never wrote that file,
#   so `core/mining_guardian.py::__main__` fell into its
#   `write_example_config()` fallback and exited with `Create config.json
#   from config.example.json, then re-run.`, scanner / approval_api /
#   ams_alert_listener crash-looped, dashboard root returned 500. Fix:
#   a new `step_drop_config_json` writes `${MG_INSTALL_ROOT}/config.json`
#   from a vendored template (config/config_template.json — now staged
#   into the payload via build_pkg.sh `--include 'config/***'`) merged
#   with the AMS_*/SLACK_* keys as `env:KEY` placeholders that
#   `GuardianConfig._resolve` looks up at runtime from the .env every
#   service already sources. Idempotent — refuses to overwrite an
#   operator-edited config.json on re-install (the customer can tune
#   profile_map between rounds).
#
# P-022 (2026-05-05) — env handoff from step_drop_dotenv to
# step_provision_postgres. The e514c12 install on the customer Mac mini
# successfully started Colima (P-019/P-020/P-021 all green) and loaded
# the postgres:16-bookworm image, then crashed in
# provision_postgres() with
#     `FATAL MG_DB_PASSWORD missing from environment; postinstall did
#     not source .env`
# Root cause: step_drop_dotenv declared MG_DB_PASSWORD / CATALOG_API_KEY
# / INTERNAL_API_SECRET as `local` and called `export MG_DB_PASSWORD`
# as the last line of the function. In bash, `export` on a `local`
# variable only marks it for export within the function frame; once
# the function returns, the local goes out of scope and the calling
# shell never sees the value. Fix: declare the secrets unscoped (so
# they land in the script-shell scope) and explicitly `export` every
# key the helper libs consume directly, including the GUARDIAN_PG_*
# / PG* family. A defensive preflight check at the head of
# step_provision_postgres asserts the contract before any colima or
# docker call runs, so a future regression fails fast with a self-
# pointing log line BEFORE Colima is touched.

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

# D-18 P-025 (2026-05-05) — installer-owned resources resolver.
#
# The legacy `${SCRIPT_DIR}/../resources/...` paths only resolve in the
# repo source tree. At .pkg install time, Installer.app extracts the
# scripts archive (lib/ + preinstall + postinstall) into a private sandbox
# like `/tmp/PKInstallSandbox.<rand>/Scripts/com.miningguardian.installer.core.<rand>/`.
# `${SCRIPT_DIR}/../resources` then resolves to a path inside that
# sandbox that does NOT exist — productbuild --resources content (which
# IS where resources/launchd/ and resources/uninstall.sh live in the
# .pkg) is metadata-only and does not get laid down on disk.
#
# Fix: build_pkg.sh step 4k stages `installer/macos-pkg/resources/launchd/`
# and `installer/macos-pkg/resources/uninstall.sh` into the customer
# payload at `<payload>/installer-resources/`. At install time, that
# directory lives at `${MG_INSTALL_ROOT}/installer-resources/` (=
# `${MG_PKG_PAYLOAD}/installer-resources/`).
#
# Fallback: if `${MG_PKG_PAYLOAD}/installer-resources/` is absent
# (smoke-test invocations of postinstall.sh in the source tree, where
# tests run preinstall/postinstall directly without a real Installer.app
# round-trip), fall back to `${SCRIPT_DIR}/../resources`. The dev tests
# under tests/installer/ use the source tree and rely on this branch.
if [[ -d "${MG_PKG_PAYLOAD}/installer-resources" ]]; then
    INSTALLER_RESOURCES_SRC="${MG_PKG_PAYLOAD}/installer-resources"
else
    INSTALLER_RESOURCES_SRC="${SCRIPT_DIR}/../resources"
fi
readonly INSTALLER_RESOURCES_SRC

# launchd plist staging — copied INTO LaunchDaemons/ at install time.
# D-18 P-025: resolved through INSTALLER_RESOURCES_SRC (payload-staged at
# install time, source-tree at dev time).
readonly PLISTS_SRC="${INSTALLER_RESOURCES_SRC}/launchd"
readonly LAUNCHERS_SRC="${INSTALLER_RESOURCES_SRC}/launchd/launchers"
readonly PLISTS_DEST="/Library/LaunchDaemons"

# v1.0.3 D-18 Copy bug 3 / P-008 — bin/uninstall.sh ships in the payload's
# installer-resources/ tree (D-18 P-025) and lands at
# ${MG_INSTALL_ROOT}/bin/uninstall.sh. Source is committed at
# installer/macos-pkg/resources/uninstall.sh. Tests in
# tests/installer/test_uninstall_script.sh assert it exists with mode
# 0755 in the source tree.
readonly UNINSTALL_SH_SRC="${INSTALLER_RESOURCES_SRC}/uninstall.sh"

# P-029 (knowledge — 2026-05-08). Baseline knowledge.json seed staged into
# `<payload>/installer-resources/knowledge/knowledge.json` by build_pkg.sh
# step 4l. step_install_knowledge_json reads it from this path.
# Active runtime knowledge lives at `${MG_INSTALL_ROOT}/knowledge/knowledge.json`
# (design D-29). A compatibility symlink at `${MG_INSTALL_ROOT}/knowledge.json`
# points to the active file so existing callers (ai/ai_score.py,
# ai/action_diversity.py, ai/backup_knowledge.py, core/mining_guardian.py,
# etc., which compute the path as `_ROOT / "knowledge.json"`) keep working
# without code change. See docs/MONTHLY_KNOWLEDGE_UPDATE.md for the merge
# workflow that consumes `${MG_INSTALL_ROOT}/knowledge/incoming/`.
readonly KNOWLEDGE_SEED_SRC="${INSTALLER_RESOURCES_SRC}/knowledge/knowledge.json"

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
readonly SCHEDULED_PLISTS_SRC="${INSTALLER_RESOURCES_SRC}/launchd/scheduled"
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
    "com.miningguardian.scheduled.catalog-import"
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
# PATH propagation under `sudo -u` (P-019, 2026-05-05)
# ---------------------------------------------------------------------------
#
# The 32ec2dcad973 install on the customer Mac mini exited 31 in
# `install_colima_runtime` with `lima compatibility error: error checking
# Lima version: exec: "limactl": executable file not found in $PATH`.
# Root cause: `sudo -u <op>` on macOS strips PATH and substitutes
# sudoers' `secure_path` (typically /usr/bin:/bin:/usr/sbin:/sbin —
# /usr/local/bin is NOT included), so colima/docker — both of which
# use Go's `os/exec.LookPath` to find limactl/colima/lima — cannot see
# the binaries we just installed two lines earlier.
#
# `_op_path` returns the PATH every `sudo -u` site that invokes
# colima/docker MUST pass through `env PATH=…`. install_colima.sh
# defines an identical helper for its own use; this one covers the
# postinstall sites (migrations, catalog seed apply, baseline scan).
# Order: /usr/local/bin first so vendored binaries shadow homebrew.
_op_path() {
    printf '%s' "/usr/local/bin:/usr/local/sbin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
}

# ---------------------------------------------------------------------------
# Shell-safe quoting helper (P-029, 2026-05-06)
# ---------------------------------------------------------------------------
#
# Returns a single-quoted, fully-escaped representation of $1 that is safe
# to drop into a `KEY=…` line of an .env file consumed by every launchd
# launcher wrapper via `set -a; source "${ENV_FILE}"; set +a`.
#
# Round-9b on the customer Mac mini (post-23a5af7 install) tripped on a
# customer name of `R & D` written into the heredoc as `MG_CUSTOMER_NAME=R
# & D`. With `set -a; source` that line parses as:
#     MG_CUSTOMER_NAME=R       (assignment)
#     &                         (background marker, terminates the cmd)
#     D                         (lookup of command `D`)
# producing `D: command not found` and exit 127 from every wrapper. The
# `&` is one of many trap characters; the full set in unquoted bash is
# space, tab, newline, `&`, `;`, `(`, `)`, `<`, `>`, `|`, `*`, `?`, `[`,
# `]`, `{`, `}`, `$`, `` ` ``, `\`, `"`, `'`, `#` (when leading), and any
# non-ASCII byte that happens to be a shell metachar in the operator's
# locale.
#
# The only POSIX-portable quoting that bash does NOT further interpret is
# single quotes. So:
#   • Wrap the entire value in single quotes.
#   • If the value contains a literal single quote, close the surrounding
#     single quotes, emit an escaped single quote (`\'`), and re-open the
#     surrounding single quotes — i.e. replace every `'` with `'\''`.
# This is the canonical bash shell-escape idiom. printf %s with a sed
# substitution does the work in one pass and never touches stdout (the
# function captures via $() in the caller).
#
# Empty input → `''` (a literal empty single-quoted string), which is
# valid in `set -a; source` and round-trips to an empty string. We keep
# the explicit `printf "''\n"` branch so a missing optional value (e.g.
# SLACK_APP_TOKEN) does NOT trigger an unbound-variable error under the
# script's `set -u`.
_shq() {
    local v="${1-}"
    if [[ -z "$v" ]]; then
        printf "''"
        return 0
    fi
    # P-020-fix (2026-05-07) — escape single quotes via sed instead of
    # bash parameter substitution. The legacy form
    #     printf "'%s'" "${v//\'/\'\\\'\'}"
    # works on bash 4+ but bash 3.2 (Apple's stock /bin/bash) parses the
    # replacement string differently, double-escaping the backslashes
    # and producing a `.env` line whose embedded `'\''` becomes
    # `'\\\\''` — every value containing a single quote breaks
    # `set -a; source .env` with `unexpected EOF while looking for
    # matching '`. The sed pipeline is identical on bash 3.2/4+ and
    # GNU/BSD sed, and is the same idiom Apple uses internally for
    # shell-safe value escaping.
    #
    # Replacement is `'\''` (close-tick, escaped-tick, reopen-tick) —
    # the canonical bash idiom. The sed script substitutes `'` →
    # `'\''` globally; we then wrap the whole thing in outer single
    # quotes.
    local escaped
    escaped="$(printf '%s' "$v" | /usr/bin/sed "s/'/'\\\\''/g")"
    printf "'%s'" "$escaped"
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
    # P-019C (2026-05-06) — bin/ and logs/ carry LaunchDaemon artifacts
    # that launchd reads as root; macOS refuses to bootstrap a root
    # LaunchDaemon if either the script directory OR the StandardOut/Err
    # parent directory is writable by non-root, surfacing as
    # `Bootstrap failed: 5: Input/output error`.
    chown root:wheel "${MG_INSTALL_ROOT}/bin"
    chown root:wheel "${MG_INSTALL_ROOT}/logs"
    chmod 0755 "${MG_INSTALL_ROOT}/bin" "${MG_INSTALL_ROOT}/logs"
    log "INFO laid out install root at ${MG_INSTALL_ROOT} (bin/+logs/ root:wheel, rest miningguardian:staff)"
}

# P-028 (2026-05-08) — payload-scripts allowlist for the upgrade
# cleanup. MUST stay byte-aligned with the per-file `--include`
# `scripts/...` block in installer/macos-pkg/scripts/build_pkg.sh
# step 4a (P-024). Drift between the two is asserted by
# tests/installer/test_p028_upgrade_stale_scripts_cleanup.sh §2 so a
# future change that adds a new scheduled-job entrypoint to the
# payload but forgets to add it here cannot quietly land.
#
# Read these as: "the only files that should remain inside
# `${MG_INSTALL_ROOT}/scripts/` after a clean install or upgrade." Any
# other file under that path on an already-installed Mini is stale
# residue from a pre-P-024 payload — pkgbuild does not remove files
# dropped by an older payload, only adds and overwrites, so the
# upgrade path silently inherits operator-only scripts (backup_db.sh,
# backup_mining_guardian.sh, start_guardian.sh, setup.sh, the
# branding/ and diagnostics/ subdirs) unless this step explicitly
# quarantines them.
readonly MG_P028_ALLOWED_PAYLOAD_SCRIPTS=(
    "__init__.py"
    "cleanup_ams_logs.py"
    "db_maintenance.sh"
    "direct_collect_logs.py"
    "daily_log_failure_report.py"
    "morning_briefing.py"
    "daily_operator_review.py"
)

step_quarantine_stale_payload_scripts() {
    # P-028 (2026-05-08) — quarantine stale scripts left in
    # `${MG_INSTALL_ROOT}/scripts/` from pre-P-024 installs.
    #
    # Live Mini finding (after install of build b1999c25346f on
    # 2026-05-08): the package payload was clean (P-024 allowlist
    # honoured), but `${MG_INSTALL_ROOT}/scripts/` on the upgraded
    # Mini still contained `backup_db.sh`, `backup_mining_guardian.sh`,
    # `start_guardian.sh`, `setup.sh`, plus other operator/dead
    # scripts from the pre-P-024 payload. `pkgbuild` ADDS and
    # OVERWRITES files but never removes files that were dropped by
    # an older payload but omitted from the new one — so the upgrade
    # path silently inherits operator-only scripts that reference
    # `BigBobby`, `100.103.185.53`, the retired Hostinger VPS, and
    # `/Volumes/Big-Bobby-T9/...`.
    #
    # Strategy: quarantine, not delete. Move every non-allowlisted
    # entry under `${MG_INSTALL_ROOT}/scripts/` into a timestamped
    # quarantine directory at
    # `${MG_INSTALL_ROOT}/quarantine/scripts-<ts>/` and chmod 0700
    # root:wheel. The quarantine is OUTSIDE
    # `${MG_INSTALL_ROOT}/scripts/` so no scheduled-job launcher can
    # exec it, and operators can recover or delete it later without
    # the next install reverting their decision. Matches the
    # `cp config.json config.json.bak.$(date +%Y%m%d-%H%M%S)` pattern
    # documented in CLAUDE.md "Failure Mode 6" / "Stop-and-check
    # before irreversible actions".
    #
    # Idempotent: on a fresh install the scripts dir contains only
    # allowlisted files and the quarantine dir is never created. On a
    # second install over an already-cleaned tree the scan also finds
    # nothing to move.
    local scripts_dir="${MG_INSTALL_ROOT}/scripts"
    if [[ ! -d "$scripts_dir" ]]; then
        log "INFO P-028: ${scripts_dir} absent; nothing to quarantine"
        return 0
    fi

    # Bash-3.2-safe membership check (no associative arrays).
    _p028_is_allowed() {
        local name="$1" allowed
        for allowed in "${MG_P028_ALLOWED_PAYLOAD_SCRIPTS[@]}"; do
            if [[ "$name" == "$allowed" ]]; then return 0; fi
        done
        return 1
    }

    # First pass: collect stale entries WITHOUT moving anything, so
    # the quarantine dir is only created when there is something to
    # move.
    local stale_entries=()
    local entry name
    # `find -mindepth 1 -maxdepth 1` lists scripts/ children only —
    # subdirs like `branding/` and `diagnostics/` (left behind by a
    # pre-P-024 install) are quarantined as a unit.
    while IFS= read -r entry; do
        [[ -z "$entry" ]] && continue
        name="$(basename "$entry")"
        if ! _p028_is_allowed "$name"; then
            stale_entries+=("$entry")
        fi
    done < <(find "$scripts_dir" -mindepth 1 -maxdepth 1 2>/dev/null)

    if (( ${#stale_entries[@]} == 0 )); then
        log "INFO P-028: ${scripts_dir} already clean (no stale entries)"
        unset -f _p028_is_allowed
        return 0
    fi

    local ts quarantine_root quarantine_dir
    ts="$(date -u +%Y%m%dT%H%M%SZ)"
    quarantine_root="${MG_INSTALL_ROOT}/quarantine"
    quarantine_dir="${quarantine_root}/scripts-${ts}"

    install -d -m 0700 -o root -g wheel "$quarantine_root"
    install -d -m 0700 -o root -g wheel "$quarantine_dir"

    local moved=0 failed=0
    for entry in "${stale_entries[@]}"; do
        name="$(basename "$entry")"
        if /bin/mv "$entry" "${quarantine_dir}/${name}" 2>>"$MG_INSTALL_LOG"; then
            moved=$((moved + 1))
        else
            failed=$((failed + 1))
        fi
    done
    # Quarantined contents must NOT be world- or group-readable;
    # files like `backup_db.sh` reference operator-only paths the
    # customer should never copy/paste.
    chmod -R go-rwx "$quarantine_dir" 2>>"$MG_INSTALL_LOG" || true

    log "INFO P-028: quarantined ${moved} stale entr(y/ies) from ${scripts_dir} -> ${quarantine_dir} (failed=${failed})"
    if (( failed > 0 )); then
        # Non-fatal warn rather than a hard fail: install should
        # still complete with services up. Operator can investigate
        # via `ls ${scripts_dir}` post-install.
        log "WARN P-028: ${failed} entr(y/ies) could not be quarantined; ${scripts_dir} may still contain stale residue"
    fi
    unset -f _p028_is_allowed
    return 0
}

step_normalize_discovery_sink_perms() {
    # P-027 (2026-05-08) — pre-create the P-022 scanner discovery sink
    # directory tree under MG_INSTALL_ROOT and (re-)normalise ownership
    # and mode on every install. Bakes in the manual repair Rob applied
    # on the live Mini after installing build b1999c25346f, where the
    # scanner had logged repeated:
    #   discovery_sink: failed to persist ... [Errno 13] Permission
    #   denied: '${MG_INSTALL_ROOT}/cron_tracking/scanner_discovery/events-YYYY-MM-DD.jsonl'
    # because the directory was `miningguardian:staff` 0755 but
    # `events-*.jsonl` had been created `root:staff` 0644 by an earlier
    # process and the next writer could not append. The repair was:
    #   chown -R miningguardian:staff <sink-dir>
    #   chmod 0775 <sink-dir>
    #   chmod 0664 <sink-dir>/events-*.jsonl <sink-dir>/latest_findings.json
    #
    # This step replays that exact repair as a build-time idempotent
    # normalisation. On a fresh install the dir does not exist yet and
    # we only create it. On an upgrade over a Mini that already has
    # root-owned event files, this step heals them BEFORE the scanner's
    # next run, so subsequent appends succeed.
    #
    # The sink directory and on-disk format are owned by
    # `core/discovery_sink.py` (P-022). The path here must stay in sync
    # with `core.discovery_sink.resolve_sink_dir()`'s default. Override
    # remains available via `MG_DISCOVERY_SINK_DIR` in `.env` for
    # operator-side relocation.
    local sink_parent="${MG_INSTALL_ROOT}/cron_tracking"
    local sink_dir="${sink_parent}/scanner_discovery"

    install -d -m 0775 "$sink_parent"
    install -d -m 0775 "$sink_dir"
    chown "${MG_INSTALL_OPERATOR_USER}:staff" "$sink_parent" "$sink_dir"
    # 0775 (g+w) so the scanner — whatever uid it ends up running as —
    # can append. group=staff is the LaunchDaemon's effective primary
    # group on macOS regardless of the active console user.
    chmod 0775 "$sink_parent" "$sink_dir"

    # Self-heal upgrade case: if a prior install left files behind under
    # an unexpected uid (e.g., `root:staff`), bring them back to
    # `${MG_INSTALL_OPERATOR_USER}:staff` and 0664. Globs are best-effort
    # because the sink may legitimately have zero files on a fresh
    # install. `2>/dev/null || true` matches the manual repair shape.
    chown -R "${MG_INSTALL_OPERATOR_USER}:staff" "$sink_dir" 2>/dev/null || true
    chmod 0664 "$sink_dir"/events-*.jsonl 2>/dev/null || true
    chmod 0664 "$sink_dir/latest_findings.json" 2>/dev/null || true

    log "INFO normalised discovery sink ${sink_dir} (${MG_INSTALL_OPERATOR_USER}:staff, dir=0775, files=0664)"
}

step_install_knowledge_json() {
    # P-029 (knowledge — 2026-05-08). Baseline-seed install + upgrade
    # preservation for the local-LLM `knowledge.json` learning artifact.
    #
    # Background. v1.0.3 shipped without a baseline knowledge.json in the
    # installer payload. Every fresh customer install therefore started
    # cold — no `miner_profiles`, no `miner_fingerprints`, no
    # `refined_insights`, no `operator_decisions`, no `baselines`. The
    # local-LLM analysis loop in `core/mining_guardian.py::loop()` and the
    # 8 AI features under `ai/` all degrade silently to "first scan" shape
    # (Vision Anchor 1: the LLM IS the product). A 96-profile / 133-
    # fingerprint / 61-insight superset (SHA-256 prefix 2edea974d711,
    # last_updated 2026-04-29) was identified as the canonical baseline
    # in the inventory at docs/MONTHLY_KNOWLEDGE_UPDATE.md and committed
    # into the repo at installer/macos-pkg/resources/knowledge/knowledge.json.
    # build_pkg.sh step 4l stages it into the payload at
    # <payload>/installer-resources/knowledge/knowledge.json (validated
    # at build time — JSON parse + at least one of the three primary
    # sections; build hard-fails if the seed regresses).
    #
    # Behavior:
    #   FRESH INSTALL (active runtime knowledge.json absent):
    #     - Create ${MG_INSTALL_ROOT}/knowledge/{,backups,incoming} as
    #       ${MG_INSTALL_OPERATOR_USER}:staff dirs=0775.
    #     - Copy the packaged seed to
    #       ${MG_INSTALL_ROOT}/knowledge/knowledge.json
    #       and ${MG_INSTALL_ROOT}/knowledge.json (compat symlink).
    #     - chown miningguardian:staff, chmod 0664 the file.
    #     - Validate JSON parse + emit a single P-029 proof log line with
    #       path / size / sha256 / miner_profiles / miner_fingerprints /
    #       refined_insights counts.
    #
    #   UPGRADE (active runtime knowledge.json already exists):
    #     - DO NOT overwrite. Site-specific learned knowledge —
    #       operator_decisions, refined_insights from the operator's own
    #       fleet, baselines, llm_scan_analyses — must survive a re-install.
    #     - Stage the packaged seed alongside as
    #       ${MG_INSTALL_ROOT}/knowledge/incoming/knowledge-seed-<version>-<sha>.json
    #       so the monthly merge workflow (docs/MONTHLY_KNOWLEDGE_UPDATE.md)
    #       can consume it deterministically.
    #     - Validate the staged seed JSON parse and log preservation +
    #       seed-staging proof lines.
    #
    # No network, no DB call. The active file's lifecycle is otherwise
    # owned by the runtime — ai/backup_knowledge.py rotates it to
    # ${MG_INSTALL_ROOT}/knowledge_backup.json on the daily backup cron;
    # the merge workflow rotates older copies into knowledge/backups/.
    #
    # Idempotent. A second install over an already-installed Mini takes
    # the upgrade branch even if the seed itself is unchanged — the
    # `incoming/` filename is version+sha-tagged so duplicate stages
    # write to the same path harmlessly.
    if [[ ! -r "$KNOWLEDGE_SEED_SRC" ]]; then
        # The build-time assertion in build_pkg.sh step 4l should have
        # caught this. Belt-and-suspenders here so a future repackage
        # that breaks the staging cannot silently ship cold-start to
        # customers — surface an exit-43 the operator can debug from
        # ${MG_INSTALL_LOG} alone.
        fail 43 "P-029 (knowledge): baseline seed missing in payload at ${KNOWLEDGE_SEED_SRC}"
    fi

    local kdir="${MG_INSTALL_ROOT}/knowledge"
    local active="${kdir}/knowledge.json"
    local compat="${MG_INSTALL_ROOT}/knowledge.json"
    local incoming_dir="${kdir}/incoming"
    local backups_dir="${kdir}/backups"

    install -d -m 0775 "$kdir"
    install -d -m 0775 "$incoming_dir"
    install -d -m 0775 "$backups_dir"
    chown "${MG_INSTALL_OPERATOR_USER}:staff" "$kdir" "$incoming_dir" "$backups_dir" 2>/dev/null || true

    # Resolve packaged seed identity for proof + incoming filename. Use
    # /usr/bin/python3 for JSON parse + counts so the helper survives
    # without `jq` (D-13 customer Mini may not have jq installed).
    local seed_size seed_sha kpi_line
    seed_size="$(/usr/bin/wc -c < "$KNOWLEDGE_SEED_SRC" | /usr/bin/tr -d ' ')"
    seed_sha="$(/usr/bin/shasum -a 256 "$KNOWLEDGE_SEED_SRC" | /usr/bin/awk '{print $1}')"
    kpi_line="$(/usr/bin/python3 - "$KNOWLEDGE_SEED_SRC" <<'PY'
import json, sys
p = sys.argv[1]
try:
    with open(p, 'rb') as fh:
        d = json.load(fh)
except Exception as e:
    sys.stderr.write('P-029_PARSE_FAIL %s\n' % e)
    sys.exit(1)
def _count(obj):
    if isinstance(obj, (list, dict)):
        return len(obj)
    return 0
mp = _count(d.get('miner_profiles'))
mf = _count(d.get('miner_fingerprints'))
ri = _count(d.get('refined_insights'))
print('miner_profiles=%d miner_fingerprints=%d refined_insights=%d' % (mp, mf, ri))
PY
)"
    if [[ -z "$kpi_line" ]]; then
        fail 43 "P-029 (knowledge): packaged seed at ${KNOWLEDGE_SEED_SRC} failed JSON parse — refusing to proceed"
    fi

    # Resolve packaged version + git sha for the incoming filename.
    local stamp_file="${MG_PKG_PAYLOAD}/BUILD_STAMP.json"
    local pkg_version="unknown" pkg_sha="unknown"
    if [[ -r "$stamp_file" ]]; then
        pkg_version="$(/usr/bin/python3 -c "
import json, sys
try:
    print(json.load(open(sys.argv[1])).get('version','unknown'))
except Exception:
    print('unknown')
" "$stamp_file" 2>/dev/null || echo unknown)"
        pkg_sha="$(/usr/bin/python3 -c "
import json, sys
try:
    print(json.load(open(sys.argv[1])).get('git_sha','unknown'))
except Exception:
    print('unknown')
" "$stamp_file" 2>/dev/null || echo unknown)"
    fi

    if [[ -e "$active" ]]; then
        # UPGRADE: preserve learned runtime knowledge. Stage the new
        # packaged seed under incoming/ for the monthly merge workflow.
        local incoming_path="${incoming_dir}/knowledge-seed-${pkg_version}-${pkg_sha}.json"
        install -m 0664 "$KNOWLEDGE_SEED_SRC" "$incoming_path"
        chown "${MG_INSTALL_OPERATOR_USER}:staff" "$incoming_path" 2>/dev/null || true
        log "INFO P-029: preserved existing runtime knowledge.json path=\"${active}\""
        log "INFO P-029: staged packaged seed path=\"${incoming_path}\" size=${seed_size} sha256=${seed_sha} ${kpi_line}"
        return 0
    fi

    # FRESH INSTALL: copy seed into active runtime path + compat symlink.
    install -m 0664 "$KNOWLEDGE_SEED_SRC" "$active"
    chown "${MG_INSTALL_OPERATOR_USER}:staff" "$active" 2>/dev/null || true

    # Compatibility symlink at ${MG_INSTALL_ROOT}/knowledge.json — the
    # path most existing runtime callers compute as `_ROOT / "knowledge.json"`
    # (ai/ai_score.py, ai/action_diversity.py, ai/backup_knowledge.py,
    # core/mining_guardian.py:2403). Without this, fresh installs would
    # read the active file at the new design path but those callers would
    # still see `FileNotFoundError`. Symlink (not copy) so writes from
    # either path land in one file. Removed first if it already exists
    # (e.g., re-install after the active file was deleted manually).
    if [[ -L "$compat" || -e "$compat" ]]; then
        rm -f "$compat"
    fi
    /bin/ln -s "${kdir}/knowledge.json" "$compat"

    # Post-copy validation: the on-disk file must still parse as JSON.
    if ! /usr/bin/python3 -c "import json; json.load(open('${active}'))" >/dev/null 2>&1; then
        fail 43 "P-029 (knowledge): active runtime knowledge.json failed post-copy JSON parse at ${active}"
    fi

    log "INFO P-029: installed knowledge.json path=\"${active}\" size=${seed_size} sha256=${seed_sha} ${kpi_line}"
    log "INFO P-029: compat symlink ${compat} -> ${kdir}/knowledge.json"
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
    # P-022 (2026-05-05) — these MUST NOT be `local`. The legacy code
    # declared them `local` and then `export`-ed at the end of the
    # function, but `local` confines the variable to the function
    # frame; the trailing `export` only sets the export attribute on
    # that local — once `step_drop_dotenv` returns, the variable is
    # gone. The next step (`step_provision_postgres` →
    # `provision_postgres` in lib/install_colima.sh) then ran with
    # MG_DB_PASSWORD unset and exited 31 with
    #     `FATAL MG_DB_PASSWORD missing from environment; postinstall
    #     did not source .env`
    # — observed live on the e514c12 install on the customer Mac mini
    # (postinstall round 4, 2026-05-05). Leaving these unscoped (i.e.
    # at function-shell scope, not function-local) allows the explicit
    # `export` below to propagate them to every later step.
    MG_DB_PASSWORD="$(openssl rand -hex 32)"
    CATALOG_API_KEY="$(openssl rand -hex 32)"
    INTERNAL_API_SECRET="$(openssl rand -hex 32)"

    # P-029 (2026-05-06) — pre-quote every interpolated value through
    # _shq so the .env round-trips exactly under `set -a; source` for
    # arbitrary input (`R & D`, names with `$`, `'`, `"`, `\`, `;`, `&`,
    # `(`, `)`, leading whitespace, glob chars, etc.). The values BEFORE
    # quoting may contain anything the customer typed into MiningGuardian.conf;
    # the values AFTER _shq are bytes the launcher wrappers can safely
    # interpret. We compute a *_Q twin for each value and feed those into
    # the heredoc — the heredoc itself does NOT do any further bash
    # parsing of the value content.
    # NOTE: the *_Q twins below are declared `local` (function-scope
    # only) — unlike MG_DB_PASSWORD / CATALOG_API_KEY / INTERNAL_API_SECRET
    # which are deliberately UNSCOPED above (P-022). The *_Q twins are
    # ephemeral input to the heredoc on this single function call and
    # never need to escape the function frame. test_postinstall_env_handoff.sh
    # (§1) asserts that the unsuffixed secret names are NOT on a `local`
    # line — that contract is preserved here.
    local _MG_PWD_Q _CAT_KEY_Q _INT_SEC_Q
    local CUSTOMER_NAME_Q AMS_URL_Q AMS_EMAIL_Q AMS_PASSWORD_Q AMS_WORKSPACE_ID_Q
    local SLACK_WEBHOOK_URL_Q SLACK_BOT_TOKEN_Q SLACK_SIGNING_SECRET_Q
    local SLACK_APP_TOKEN_Q AUTHORIZED_SLACK_USER_IDS_Q
    local SCAN_INTERVAL_Q MG_DRY_RUN_Q
    local MG_INSTALL_RAM_TIER_Q MG_INSTALL_LLM_MODEL_Q
    CUSTOMER_NAME_Q="$(_shq "${CUSTOMER_NAME:-}")"
    AMS_URL_Q="$(_shq "${AMS_URL:-}")"
    AMS_EMAIL_Q="$(_shq "${AMS_EMAIL:-}")"
    AMS_PASSWORD_Q="$(_shq "${AMS_PASSWORD:-}")"
    AMS_WORKSPACE_ID_Q="$(_shq "${AMS_WORKSPACE_ID:-}")"
    SLACK_WEBHOOK_URL_Q="$(_shq "${SLACK_WEBHOOK_URL:-}")"
    SLACK_BOT_TOKEN_Q="$(_shq "${SLACK_BOT_TOKEN:-}")"
    SLACK_SIGNING_SECRET_Q="$(_shq "${SLACK_SIGNING_SECRET:-}")"
    SLACK_APP_TOKEN_Q="$(_shq "${SLACK_APP_TOKEN:-}")"
    AUTHORIZED_SLACK_USER_IDS_Q="$(_shq "${AUTHORIZED_SLACK_USER_IDS:-}")"
    SCAN_INTERVAL_Q="$(_shq "${SCAN_INTERVAL:-300}")"
    MG_DRY_RUN_Q="$(_shq "${MG_DRY_RUN:-true}")"
    _MG_PWD_Q="$(_shq "${MG_DB_PASSWORD}")"
    _CAT_KEY_Q="$(_shq "${CATALOG_API_KEY}")"
    _INT_SEC_Q="$(_shq "${INTERNAL_API_SECRET}")"
    MG_INSTALL_RAM_TIER_Q="$(_shq "${MG_INSTALL_RAM_TIER:-}")"
    MG_INSTALL_LLM_MODEL_Q="$(_shq "${MG_INSTALL_LLM_MODEL:-}")"

    local env_file="${MG_INSTALL_ROOT}/.env"
    # Subshell redirect — no secret value ever touches this script's
    # stdout. Heredoc body MUST stay aligned with setup.sh::phase_07_secrets
    # (any drift = launchd services crash on first start because the
    # Python code looks for keys this file did not write). P-029 — every
    # interpolated value is the *_Q (pre-quoted) twin; raw integer / URL
    # constants like `127.0.0.1`, `5432`, `mg` are safe as-is.
    cat > "$env_file" <<EOF
# /Library/Application Support/MiningGuardian/.env  mode=0600  owner=${MG_INSTALL_OPERATOR_USER}:staff
# Generated by Mining Guardian installer postinstall.sh
# Generated at $(date -u +%Y-%m-%dT%H:%M:%SZ)
# DO NOT COMMIT. DO NOT LOG. DO NOT SHARE.

# AMS — Bitcoin SHA-256 miners only (S-4: no creds in query strings)
AMS_BASE_URL=${AMS_URL_Q}
AMS_EMAIL=${AMS_EMAIL_Q}
AMS_PASSWORD=${AMS_PASSWORD_Q}
AMS_WORKSPACE_ID=${AMS_WORKSPACE_ID_Q}

# Postgres — 127.0.0.1 only (S-13: no Tailscale IPs anywhere)
# Integration bug 2: GUARDIAN_PG_USER + PGUSER both written with the
# same value until the Python-codebase dual-naming cleanup completes.
GUARDIAN_PG_HOST=127.0.0.1
GUARDIAN_PG_PORT=5432
GUARDIAN_PG_USER=mg
GUARDIAN_PG_PASSWORD=${_MG_PWD_Q}
GUARDIAN_PG_DBNAME=mining_guardian
GUARDIAN_PG_TEST_DBNAME=mining_guardian_test
GUARDIAN_PG_CATALOG_DBNAME=mining_guardian_catalog
PGHOST=127.0.0.1
PGPORT=5432
PGUSER=mg
PGDATABASE=mining_guardian
MG_DB_PASSWORD=${_MG_PWD_Q}

# Slack — all values customer-specific (do not copy from VPS; §6.3)
SLACK_WEBHOOK_URL=${SLACK_WEBHOOK_URL_Q}
SLACK_BOT_TOKEN=${SLACK_BOT_TOKEN_Q}
SLACK_SIGNING_SECRET=${SLACK_SIGNING_SECRET_Q}
SLACK_APP_TOKEN=${SLACK_APP_TOKEN_Q}
AUTHORIZED_SLACK_USER_IDS=${AUTHORIZED_SLACK_USER_IDS_Q}

# Catalog API key — S-6 fix: generated fresh; crash-on-startup if absent (PR #65/#66)
CATALOG_API_KEY=${_CAT_KEY_Q}

# Internal API secret — approval_api.py verify_internal() fail-closed
INTERNAL_API_SECRET=${_INT_SEC_Q}

# Ollama — local GPU inference on 127.0.0.1 (S-13 fix: no hardcoded Tailscale IPs)
OLLAMA_HOST=http://127.0.0.1:11434

# Runtime config (D-2: auto_approve=false — explicit opt-in required)
MG_DRY_RUN=${MG_DRY_RUN_Q}
MG_SCAN_INTERVAL=${SCAN_INTERVAL_Q}
MG_CUSTOMER_NAME=${CUSTOMER_NAME_Q}
AUTO_APPROVE_ENABLED=false

# Service ports — all 127.0.0.1 (S-13)
GUARDIAN_DASHBOARD_PORT=8585
GUARDIAN_APPROVAL_PORT=8686
GUARDIAN_INTELLIGENCE_PORT=8590

# Install metadata (sourced from preinstall.sh detect_ram.sh — D-13)
MG_INSTALL_RAM_TIER=${MG_INSTALL_RAM_TIER_Q}
MG_INSTALL_LLM_MODEL=${MG_INSTALL_LLM_MODEL_Q}
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

    # P-022 (2026-05-05) — re-export every key the downstream helper
    # libs read directly from the environment. The on-disk .env is
    # written for the launchd services (which source it on first
    # start), but the postinstall script itself NEVER re-sources the
    # file — it walks straight into `step_provision_postgres`, which
    # calls `provision_postgres` in lib/install_colima.sh, which reads
    # `MG_DB_PASSWORD` directly via `${MG_DB_PASSWORD:-}`. The legacy
    # code only re-exported MG_DB_PASSWORD here, but it was declared
    # `local` above so the export was a no-op once the function
    # returned. The fix is two-pronged: declare unscoped (above) AND
    # explicitly export every key the helpers consume so any future
    # helper that gains a new env-key dependency picks it up without a
    # second drop-dotenv rewrite.
    #
    # Logged: KEY NAMES ONLY. Never values. The .env file is the only
    # place any secret value should ever appear.
    GUARDIAN_PG_HOST=127.0.0.1
    GUARDIAN_PG_PORT=5432
    GUARDIAN_PG_USER=mg
    GUARDIAN_PG_PASSWORD="${MG_DB_PASSWORD}"
    GUARDIAN_PG_DBNAME=mining_guardian
    GUARDIAN_PG_TEST_DBNAME=mining_guardian_test
    GUARDIAN_PG_CATALOG_DBNAME=mining_guardian_catalog
    PGHOST=127.0.0.1
    PGPORT=5432
    PGUSER=mg
    PGDATABASE=mining_guardian
    export MG_DB_PASSWORD CATALOG_API_KEY INTERNAL_API_SECRET
    export GUARDIAN_PG_HOST GUARDIAN_PG_PORT GUARDIAN_PG_USER \
           GUARDIAN_PG_PASSWORD GUARDIAN_PG_DBNAME \
           GUARDIAN_PG_TEST_DBNAME GUARDIAN_PG_CATALOG_DBNAME
    export PGHOST PGPORT PGUSER PGDATABASE

    log "INFO loaded generated env keys into postinstall shell:" \
        "MG_DB_PASSWORD CATALOG_API_KEY INTERNAL_API_SECRET" \
        "GUARDIAN_PG_HOST GUARDIAN_PG_PORT GUARDIAN_PG_USER" \
        "GUARDIAN_PG_PASSWORD GUARDIAN_PG_DBNAME" \
        "GUARDIAN_PG_TEST_DBNAME GUARDIAN_PG_CATALOG_DBNAME" \
        "PGHOST PGPORT PGUSER PGDATABASE"
}

step_provision_postgres() {
    # P-022 (2026-05-05) — fail-fast sanity check. The helper
    # `provision_postgres` (lib/install_colima.sh) already refuses to
    # run when MG_DB_PASSWORD is missing, but its FATAL line buries
    # the root cause inside the colima/docker path. The e514c12 install
    # on the customer Mac mini exited 31 here AFTER colima had been
    # started and the postgres image had been loaded — meaning Rob now
    # has a half-installed system to clean up before retrying.
    #
    # Asserting the contract at the top of this step turns a 30-second
    # dance through colima into an immediate FATAL with a self-pointing
    # log line, BEFORE any system-state change made by
    # install_colima_runtime / load_postgres_image. Catches any future
    # regression in `step_drop_dotenv` (e.g., someone re-introduces
    # `local`, drops the export, or adds a new helper-required key).
    #
    # KEYS LOGGED, NEVER VALUES.
    local missing=()
    [[ -z "${MG_DB_PASSWORD:-}" ]] && missing+=("MG_DB_PASSWORD")
    [[ -z "${GUARDIAN_PG_USER:-}" ]] && missing+=("GUARDIAN_PG_USER")
    [[ -z "${PGUSER:-}" ]] && missing+=("PGUSER")
    [[ -z "${GUARDIAN_PG_DBNAME:-}" ]] && missing+=("GUARDIAN_PG_DBNAME")
    if (( ${#missing[@]} > 0 )); then
        fail 31 "step_drop_dotenv did not export required env keys: ${missing[*]} (P-022 regression — see step_drop_dotenv)"
    fi
    log "INFO step_provision_postgres preflight OK: required env keys present"

    install_colima_runtime || fail 31 "colima runtime install failed"
    load_postgres_image    || fail 31 "postgres image load failed"
    provision_postgres     || fail 31 "postgres container provisioning failed"
}

step_reconcile_postgres_password() {
    # P-029 (2026-05-06) — reconcile the `mg` Postgres role's password to
    # the value just written into .env, regardless of whether this is a
    # fresh initdb or a re-install over an existing pgdata volume.
    #
    # Why this is necessary: `provision_postgres` (lib/install_colima.sh
    # L355-369) always passes `-e POSTGRES_PASSWORD="$MG_DB_PASSWORD"` to
    # the postgres container, but the postgres image only honors that env
    # var on FIRST initdb of a fresh data directory. When the operator
    # re-runs the installer over an existing `${MG_INSTALL_ROOT}/postgres-data/`
    # volume (every retry round so far), Postgres reads the pre-existing
    # `pg_authid` / `pg_hba.conf` and silently keeps the prior install's
    # role passwords — so the new `mg` password in .env diverges from the
    # actual role. The customer Mini smoke (post-23a5af7) showed this:
    # dashboard `/` returned 500 with `password authentication failed for
    # user "mg"` against TCP 127.0.0.1:5432, even though .env carried a
    # freshly-generated value. (`docker exec psql -U mg` from inside the
    # container uses peer/trust on the unix socket and so worked — that
    # masked the bug through migrations and the catalog seed apply.)
    #
    # Fix: always issue `ALTER USER mg PASSWORD ...` against the running
    # container after provision_postgres returns ready. Idempotent: on a
    # fresh initdb the new password equals the env-supplied password
    # (no-op); on a re-install over existing pgdata it heals the role.
    #
    # Hardening:
    #   * Password sent to psql via stdin (-c '...' would expose it in
    #     the docker exec command line and `ps`). We use `\password`-
    #     equivalent via a single statement read from the parent shell's
    #     here-string into psql's stdin.
    #   * MG_DB_PASSWORD is openssl-rand-hex-32 — alnum only — so no
    #     SQL-quoting trap. Belt and suspenders: enforce that shape
    #     before issuing the statement (refuse to run if it ever gains a
    #     character that would need SQL escaping).
    #   * KEY NAMES LOGGED, NEVER VALUES.
    if [[ -z "${MG_DB_PASSWORD:-}" ]]; then
        fail 31 "step_reconcile_postgres_password: MG_DB_PASSWORD missing (P-029 — should have been exported by step_drop_dotenv)"
    fi
    if [[ ! "${MG_DB_PASSWORD}" =~ ^[A-Fa-f0-9]+$ ]]; then
        # openssl rand -hex 32 always emits 64 lowercase hex chars; if
        # this assertion fires, someone changed the generator and the
        # SQL-quoting story needs revisiting.
        fail 31 "step_reconcile_postgres_password: MG_DB_PASSWORD shape unexpected (P-029 — must be hex)"
    fi

    local container="mining-guardian-db"
    log "INFO reconciling Postgres role 'mg' password against .env (P-029)"
    # printf | docker exec -i  →  password reaches psql via stdin only.
    # ON_ERROR_STOP=1 so a failure here surfaces immediately.
    # shellcheck disable=SC2024  # log file is owned by root; redirect is opened by parent shell pre-sudo, intentional (matches step_apply_migrations / step_baseline_scan).
    if ! printf "ALTER USER mg WITH PASSWORD '%s';\n" "${MG_DB_PASSWORD}" \
            | sudo -u "${MG_INSTALL_OPERATOR_USER}" \
                /usr/bin/env PATH="$(_op_path)" \
                docker exec -i "$container" \
                psql -U mg -d postgres -v ON_ERROR_STOP=1 \
                >>"$MG_INSTALL_LOG" 2>&1; then
        fail 31 "step_reconcile_postgres_password: ALTER USER mg failed (P-029)"
    fi
    log "INFO Postgres role 'mg' password reconciled (P-029)"

    # Verify the reconciled password works for a TCP connection (the
    # path the host-side services actually use). docker exec on the
    # container's localhost is a strong proxy for what the launchd
    # services see; it forces the password code path (instead of unix-
    # socket peer/trust) by connecting to 127.0.0.1.
    # shellcheck disable=SC2024  # see SC2024 disable note above.
    if ! sudo -u "${MG_INSTALL_OPERATOR_USER}" \
            /usr/bin/env PATH="$(_op_path)" PGPASSWORD="${MG_DB_PASSWORD}" \
            docker exec -i \
                -e "PGPASSWORD=${MG_DB_PASSWORD}" \
                "$container" \
            psql -h 127.0.0.1 -U mg -d postgres \
                 -v ON_ERROR_STOP=1 -tAc 'SELECT 1;' \
            >>"$MG_INSTALL_LOG" 2>&1; then
        fail 31 "step_reconcile_postgres_password: TCP auth verification failed (P-029) — see ${MG_INSTALL_LOG}"
    fi
    log "INFO Postgres TCP auth verified for role 'mg' (P-029)"
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
        if ! sudo -u "${MG_INSTALL_OPERATOR_USER}" \
                /usr/bin/env PATH="$(_op_path)" \
                docker exec -i "$container" \
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
    exists="$(sudo -u "${MG_INSTALL_OPERATOR_USER}" \
                /usr/bin/env PATH="$(_op_path)" \
                docker exec -i "$container" \
        psql -U mg -d postgres -tAc \
        "SELECT 1 FROM pg_database WHERE datname='${catalog_db}';" \
        2>>"$MG_INSTALL_LOG" || true)"
    exists="$(echo "${exists:-}" | tr -d '[:space:]')"
    if [[ "${exists:-}" != "1" ]]; then
        log "INFO creating catalog database ${catalog_db}"
        # shellcheck disable=SC2024  # log file is owned by root; redirect is opened by parent shell pre-sudo, intentional (matches step_baseline_scan / step_create_venv).
        if ! sudo -u "${MG_INSTALL_OPERATOR_USER}" \
                /usr/bin/env PATH="$(_op_path)" \
                docker exec -i "$container" \
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
    if ! sudo -u "${MG_INSTALL_OPERATOR_USER}" \
            /usr/bin/env PATH="$(_op_path)" \
            docker exec "$container" \
            mkdir -p "$container_seed_dir" >>"$MG_INSTALL_LOG" 2>&1; then
        fail 39 "could not create staging dir inside container: ${container_seed_dir}"
    fi
    # shellcheck disable=SC2024
    if ! sudo -u "${MG_INSTALL_OPERATOR_USER}" \
            /usr/bin/env PATH="$(_op_path)" \
            docker cp \
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
    if ! sudo -u "${MG_INSTALL_OPERATOR_USER}" \
                /usr/bin/env PATH="$(_op_path)" \
                docker exec -i "$container" \
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
    row_count="$(sudo -u "${MG_INSTALL_OPERATOR_USER}" \
                /usr/bin/env PATH="$(_op_path)" \
                docker exec -i "$container" \
        psql -U mg -d "$catalog_db" -tAc \
        "SELECT count(*) FROM hardware.miner_models;" \
        2>>"$MG_INSTALL_LOG" || echo 0)"
    row_count="$(echo "${row_count:-0}" | tr -d '[:space:]')"
    if [[ "${row_count:-0}" -ge 320 ]]; then
        log "INFO catalog already seeded (${row_count} rows) — skipping seed apply"
    else
        log "INFO seeding 320 Bitcoin SHA-256 miner models into ${catalog_db}"
        # shellcheck disable=SC2024
        if ! sudo -u "${MG_INSTALL_OPERATOR_USER}" \
                /usr/bin/env PATH="$(_op_path)" \
                docker exec -i "$container" \
                psql -U mg -d "$catalog_db" -v ON_ERROR_STOP=1 \
                -f "${container_seed_dir}/seed_miner_models.sql" \
                >>"$MG_INSTALL_LOG" 2>&1; then
            fail 39 "seed_miner_models.sql apply failed against ${catalog_db}"
        fi
    fi

    # Verify final row count meets the v1.0.3 verification-gate floor.
    row_count="$(sudo -u "${MG_INSTALL_OPERATOR_USER}" \
                /usr/bin/env PATH="$(_op_path)" \
                docker exec -i "$container" \
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
    sudo -u "${MG_INSTALL_OPERATOR_USER}" \
            /usr/bin/env PATH="$(_op_path)" \
            docker exec "$container" \
        rm -rf "$container_seed_dir" >>"$MG_INSTALL_LOG" 2>&1 || true
}

step_apply_alias_seeds() {
    # P-018D (2026-05-06) — apply the two reference-data alias seeds the
    # importer's two-tier resolver (`mg_import_tool/resolver.py`) reads:
    #
    #   * intelligence-catalog/seed-data/aliases/001_hardware_model_aliases_tier1.sql
    #     → CATALOG DB `mining_guardian_catalog`, `hardware.model_aliases`
    #       (12,840 rows; unique aliases for ~317 known miner models;
    #        FK references `hardware.miner_models(id)` which only the
    #        catalog DB has populated).
    #
    #   * intelligence-catalog/seed-data/aliases/002_mg_family_aliases_tier2.sql
    #     → OPERATIONAL DB `mining_guardian`, `mg.model_family_aliases`
    #       (1,494 rows; ambiguous aliases with candidate-id arrays;
    #        resolver narrows by hashrate at lookup time).
    #
    # Both seeds are idempotent (`ON CONFLICT … DO NOTHING`); a re-install
    # against an already-seeded DB is a no-op. Failures here exit 42
    # (a fresh code reserved for alias-seed apply — disjoint from 39
    # which guards the catalog DB seed in the previous step, and from
    # 41 which is already used for the customer-info Desktop conf gate).
    #
    # Ordering: must run AFTER `step_apply_migrations` (creates
    # `mg.model_family_aliases` per migration 007) AND AFTER
    # `step_provision_catalog_db_and_seed` (creates the catalog DB and
    # `hardware.miner_models` rows the Tier-1 FKs target). It is fine to
    # run BEFORE `step_install_ollama_and_pull_model` and the LaunchDaemon
    # bootstrap below.
    #
    # D-20 note: these files live under `intelligence-catalog/seed-data/
    # aliases/` (NOT `mg_import_tool/sql/seed/`) because the `mg_import*`
    # path is forbidden in the customer payload by `build_pkg.sh::step 4h`.

    local seed_dir="${MG_PKG_PAYLOAD}/intelligence-catalog/seed-data/aliases"
    local tier1_file="${seed_dir}/001_hardware_model_aliases_tier1.sql"
    local tier2_file="${seed_dir}/002_mg_family_aliases_tier2.sql"
    # P-021 (2026-05-07) — Tier-1 supplement: short AMS names live-resolved
    # against `hardware.miner_models` at apply time. See file header for why.
    local tier1_supp_file="${seed_dir}/003_live_short_name_aliases.sql"
    local catalog_db="mining_guardian_catalog"
    local op_db="mining_guardian"
    local container="mining-guardian-db"

    if [[ ! -d "$seed_dir" ]]; then
        fail 42 "alias seed directory missing in payload: ${seed_dir} (build_pkg.sh step 4a should have rsync'd intelligence-catalog/***)"
    fi
    if [[ ! -r "$tier1_file" ]]; then
        fail 42 "Tier-1 alias seed missing: ${tier1_file}"
    fi
    if [[ ! -r "$tier2_file" ]]; then
        fail 42 "Tier-2 alias seed missing: ${tier2_file}"
    fi
    # P-021: the Tier-1 supplement is shipped alongside Tier-1/Tier-2.
    # Treat as required so a missing file is loud, not silently ignored.
    if [[ ! -r "$tier1_supp_file" ]]; then
        fail 42 "Tier-1 alias seed supplement missing: ${tier1_supp_file} (P-021)"
    fi

    # Stage the seeds inside the container so psql -f can find them on a
    # path the docker-exec'd psql can read. Mirror step_provision_catalog_*
    # exactly so the operator sees the same staging pattern in the log.
    local container_seed_dir="/tmp/mg-alias-seeds-$$"
    # shellcheck disable=SC2024
    if ! sudo -u "${MG_INSTALL_OPERATOR_USER}" \
            /usr/bin/env PATH="$(_op_path)" \
            docker exec "$container" \
            mkdir -p "$container_seed_dir" >>"$MG_INSTALL_LOG" 2>&1; then
        fail 42 "could not create staging dir inside container: ${container_seed_dir}"
    fi
    # shellcheck disable=SC2024
    if ! sudo -u "${MG_INSTALL_OPERATOR_USER}" \
            /usr/bin/env PATH="$(_op_path)" \
            docker cp \
            "${seed_dir}/." "${container}:${container_seed_dir}/" \
            >>"$MG_INSTALL_LOG" 2>&1; then
        fail 42 "docker cp of alias seed-data into container failed"
    fi

    # 1. Tier-1 → catalog DB.
    #
    # P-019B (2026-05-06) — defensive FK-safe staging apply.
    #
    # Background: the Tier-1 seed file references 317 specific
    # miner_model_id UUIDs that were frozen from the seed generator's
    # `db_catalog.tsv` snapshot. The catalog DB's `hardware.miner_models`
    # rows are seeded by `seed_miner_models.sql` whose every INSERT uses
    # `uuid_generate_v4()` — fresh random UUIDs at each install. So
    # almost none of the seed's 317 frozen UUIDs match the live DB's
    # randomly-generated UUIDs, and the seed's 12,840 INSERTs hit the
    # FK constraint `miner_model_id REFERENCES hardware.miner_models(id)`.
    # Applied as a single BEGIN/COMMIT block, the FIRST FK violation
    # aborts the whole transaction and zero rows land. Observed live on
    # 2026-05-06 against `MiningGuardian-1.0.3-511ed2768d76.pkg`:
    #   FATAL (42) Tier-1 alias seed apply failed against
    #     mining_guardian_catalog
    # with `hardware.model_aliases=29` (a partial pre-install state from
    # an older snapshot) and `hardware.miner_models=324` (the operational
    # seed plus 4 catalog_updater additions).
    #
    # Fix: stage the Tier-1 INSERTs into a `pg_temp` scratch table that
    # has no FK, then promote rows to `hardware.model_aliases` only
    # where `miner_model_id` exists in the live `hardware.miner_models`.
    # Rows whose UUIDs are stale are silently dropped — but a verify
    # step asserts a non-trivial count survived, so a future seed/
    # catalog-seed drift cannot silently apply zero rows.
    #
    # Implementation: a tiny `sed` rewrites the seed's
    # `INSERT INTO hardware.model_aliases` lines to target the scratch
    # table. The rewrite is idempotent (a re-apply against an
    # already-populated DB is still a no-op via ON CONFLICT). The
    # original seed file in the payload is unchanged on disk.
    log "INFO staging Tier-1 alias seed for FK-safe apply against ${catalog_db}"
    local staged_tier1="${container_seed_dir}/001_hardware_model_aliases_tier1.staged.sql"

    # 1a. Pre-flight wrapper that creates the scratch table at the start
    # of the transaction. The scratch is `LIKE hardware.model_aliases
    # INCLUDING DEFAULTS` minus EXCLUDING CONSTRAINTS so we keep column
    # types/defaults but lose the FK + UNIQUE so the bulk load never
    # aborts. Wrapper also pre-strips the seed's own BEGIN; / COMMIT;
    # via sed (see 1b) so the entire apply is one transaction wrapping
    # CREATE-stage + INSERT-stage + INSERT-real + DROP-stage.
    local wrap_pre="${container_seed_dir}/_tier1_wrap_pre.sql"
    local wrap_post="${container_seed_dir}/_tier1_wrap_post.sql"

    # shellcheck disable=SC2024
    sudo -u "${MG_INSTALL_OPERATOR_USER}" \
            /usr/bin/env PATH="$(_op_path)" \
            docker exec -i "$container" \
            bash -c "cat > '${wrap_pre}'" <<'__SQL_PRE__' >>"$MG_INSTALL_LOG" 2>&1 || \
        fail 42 "could not write Tier-1 staging pre-wrapper"
BEGIN;
CREATE TEMP TABLE _tier1_alias_seed_scratch (
    LIKE hardware.model_aliases INCLUDING DEFAULTS EXCLUDING CONSTRAINTS
) ON COMMIT DROP;
__SQL_PRE__

    # 1b. Sed-rewrite the seed in-container so its INSERTs target the
    # scratch table. Strip the seed's own BEGIN / COMMIT so the wrapper
    # owns the transaction. Drop the seed's `ON CONFLICT (...) DO NOTHING`
    # clauses too — the scratch table has no UNIQUE constraint to
    # conflict on, so the clause would error.
    # shellcheck disable=SC2024
    sudo -u "${MG_INSTALL_OPERATOR_USER}" \
            /usr/bin/env PATH="$(_op_path)" \
            docker exec -i "$container" \
            bash -c "
                sed -e 's/INSERT INTO hardware\\.model_aliases/INSERT INTO _tier1_alias_seed_scratch/g' \
                    -e '/^BEGIN;$/d' \
                    -e '/^COMMIT;$/d' \
                    -e 's/ ON CONFLICT (miner_model_id, alias) DO NOTHING//g' \
                    '${container_seed_dir}/001_hardware_model_aliases_tier1.sql' \
                    > '${staged_tier1}'
            " >>"$MG_INSTALL_LOG" 2>&1 || \
        fail 42 "could not stage-rewrite Tier-1 alias seed"

    # 1c. Post-wrapper: promote scratch rows to the real table, but only
    # those whose miner_model_id exists in hardware.miner_models. The
    # ON CONFLICT (miner_model_id, alias) DO NOTHING guards re-runs.
    # The DROP TABLE is implicit via ON COMMIT DROP on the scratch.
    # shellcheck disable=SC2024
    sudo -u "${MG_INSTALL_OPERATOR_USER}" \
            /usr/bin/env PATH="$(_op_path)" \
            docker exec -i "$container" \
            bash -c "cat > '${wrap_post}'" <<'__SQL_POST__' >>"$MG_INSTALL_LOG" 2>&1 || \
        fail 42 "could not write Tier-1 staging post-wrapper"
INSERT INTO hardware.model_aliases (
    miner_model_id, alias, alias_normalized, alias_source, is_common, notes
)
SELECT s.miner_model_id, s.alias, s.alias_normalized, s.alias_source, s.is_common, s.notes
FROM _tier1_alias_seed_scratch s
WHERE EXISTS (
    SELECT 1 FROM hardware.miner_models m WHERE m.id = s.miner_model_id
)
ON CONFLICT (miner_model_id, alias) DO NOTHING;
COMMIT;
__SQL_POST__

    # 1d. Apply the three SQL files as one psql session — psql streams
    # them in order under a single connection so the BEGIN; from the
    # pre-wrapper covers the scratch INSERT and the gated promote.
    # ON_ERROR_STOP=1 because the SHAPE of the apply (scratch table
    # creation, gated promote) is not allowed to fail; only individual
    # FK-stale rows are silently dropped, and that happens in the
    # WHERE-EXISTS filter, not as a row-level error.
    log "INFO applying Tier-1 alias seed (hardware.model_aliases) to ${catalog_db}"
    # shellcheck disable=SC2024
    if ! sudo -u "${MG_INSTALL_OPERATOR_USER}" \
                /usr/bin/env PATH="$(_op_path)" \
                docker exec -i "$container" \
            bash -c "cat '${wrap_pre}' '${staged_tier1}' '${wrap_post}' | psql -U mg -d '${catalog_db}' -v ON_ERROR_STOP=1" \
            >>"$MG_INSTALL_LOG" 2>&1; then
        fail 42 "Tier-1 alias seed apply failed against ${catalog_db}"
    fi

    # 2. Tier-2 → operational DB.
    log "INFO applying Tier-2 alias seed (mg.model_family_aliases) to ${op_db}"
    # shellcheck disable=SC2024
    if ! sudo -u "${MG_INSTALL_OPERATOR_USER}" \
                /usr/bin/env PATH="$(_op_path)" \
                docker exec -i "$container" \
            psql -U mg -d "$op_db" -v ON_ERROR_STOP=1 \
            -f "${container_seed_dir}/002_mg_family_aliases_tier2.sql" \
            >>"$MG_INSTALL_LOG" 2>&1; then
        fail 42 "Tier-2 alias seed apply failed against ${op_db}"
    fi

    # 2b. Tier-1 supplement → catalog DB.
    #
    # P-021 (2026-05-07) — fills the live AMS short-name gap regardless of
    # whether the frozen-UUID Tier-1 seed survived the FK gate. Resolves
    # IDs at apply time against the live `hardware.miner_models`, so it
    # cannot drift like 001_hardware_model_aliases_tier1.sql does. See
    # 003_live_short_name_aliases.sql header for the rationale.
    log "INFO applying Tier-1 alias seed supplement (P-021 short-name aliases) to ${catalog_db}"
    # shellcheck disable=SC2024
    if ! sudo -u "${MG_INSTALL_OPERATOR_USER}" \
                /usr/bin/env PATH="$(_op_path)" \
                docker exec -i "$container" \
            psql -U mg -d "$catalog_db" -v ON_ERROR_STOP=1 \
            -f "${container_seed_dir}/003_live_short_name_aliases.sql" \
            >>"$MG_INSTALL_LOG" 2>&1; then
        # Non-fatal: short-name supplement failure does not block install
        # (the four BiXBiT-USA names will fall through to Tier-2 + the
        # existing slug-derived contains-match in `_resolve_model_row`,
        # which is what's been happening pre-P-021). Log loudly so the
        # operator notices in install.log.
        log "ERROR Tier-1 alias seed supplement failed against ${catalog_db} (P-021) — install continues; AMS short names (S19JPro/S21EXPHyd/S21Imm/AH3880) will rely on slug-derived contains-match"
    fi

    # 3. Verify.
    #
    # Tier-2 floor stays at 1,000 (no FK; full seed always lands on a
    # healthy install).
    #
    # P-019B: Tier-1 floor is now THREE-tier:
    #   * == 0  → install ABORTS with FATAL (42). The staging+gate
    #             produced nothing, which means the catalog seed is
    #             empty, the catalog DB is wrong, or the staging logic
    #             itself broke. Don't proceed silently.
    #   * < 100 → install proceeds with a clear WARN. The seed and the
    #             catalog-seed UUID space have drifted to the point that
    #             essentially nothing matches; the importer's Tier-1
    #             resolver will return empty and almost every miner_type
    #             will fall through to Tier-2 / mg.unresolved_models.
    #             Operator must regenerate the alias seed against the
    #             current `seed_miner_models.sql` snapshot. Logged at
    #             ERROR level so it surfaces in the install log scan.
    #   * < 5000 → still proceeds, with INFO indicating partial coverage
    #             (some snapshots overlap, others don't).
    #   * >= 5000 → healthy install — the typical happy path.
    local tier1_count tier2_count
    tier1_count="$(sudo -u "${MG_INSTALL_OPERATOR_USER}" \
                /usr/bin/env PATH="$(_op_path)" \
                docker exec -i "$container" \
        psql -U mg -d "$catalog_db" -tAc \
        "SELECT count(*) FROM hardware.model_aliases;" \
        2>>"$MG_INSTALL_LOG" || echo 0)"
    tier1_count="$(echo "${tier1_count:-0}" | tr -d '[:space:]')"
    if [[ "${tier1_count:-0}" -eq 0 ]]; then
        fail 42 "Tier-1 alias seed verification failed: hardware.model_aliases has 0 rows after staging+gate apply — neither the seed nor the catalog seed is healthy"
    fi
    if [[ "${tier1_count:-0}" -lt 100 ]]; then
        log "ERROR Tier-1 alias seed coverage VERY LOW: hardware.model_aliases has ${tier1_count} rows (expected >= 5000). The alias seed's frozen miner_model_id UUIDs and seed_miner_models.sql's runtime UUIDs have drifted apart. Importer Tier-1 lookups will return empty; almost every miner_type will fall through to Tier-2 / mg.unresolved_models. Operator MUST regenerate the alias seed against the current seed_miner_models.sql snapshot and re-run install."
    elif [[ "${tier1_count:-0}" -lt 5000 ]]; then
        log "INFO Tier-1 alias seed partial coverage: hardware.model_aliases has ${tier1_count} rows (typical full coverage is ~12,840). Some seed UUIDs match the live catalog; others were dropped by the FK gate. Importer Tier-1 will work for the matched models; the rest will fall through to Tier-2."
    else
        log "INFO Tier-1 alias seed full coverage: hardware.model_aliases has ${tier1_count} rows."
    fi
    tier2_count="$(sudo -u "${MG_INSTALL_OPERATOR_USER}" \
                /usr/bin/env PATH="$(_op_path)" \
                docker exec -i "$container" \
        psql -U mg -d "$op_db" -tAc \
        "SELECT count(*) FROM mg.model_family_aliases;" \
        2>>"$MG_INSTALL_LOG" || echo 0)"
    tier2_count="$(echo "${tier2_count:-0}" | tr -d '[:space:]')"
    if [[ "${tier2_count:-0}" -lt 1000 ]]; then
        fail 42 "Tier-2 alias seed verification failed: mg.model_family_aliases has ${tier2_count} rows (expected >= 1000)"
    fi
    log "INFO alias seeds verified: hardware.model_aliases=${tier1_count}, mg.model_family_aliases=${tier2_count}"

    # Best-effort cleanup of in-container staging dir; not fatal.
    # shellcheck disable=SC2024
    sudo -u "${MG_INSTALL_OPERATOR_USER}" \
            /usr/bin/env PATH="$(_op_path)" \
            docker exec "$container" \
        rm -rf "$container_seed_dir" >>"$MG_INSTALL_LOG" 2>&1 || true
}

step_install_ollama_and_pull_model() {
    install_ollama_runtime || fail 33 "ollama runtime install failed"
    pull_llm_model         || fail 33 "ollama pull of ${MG_INSTALL_LLM_MODEL:-?} failed"
}

step_drop_config_json() {
    # P-029 (2026-05-06) — materialize ${MG_INSTALL_ROOT}/config.json so
    # every long-running service (scanner, approval_api, ams_alert_listener,
    # overnight_automation, ...) finds the runtime config it expects on
    # first start. Pre-P-029 the .pkg path NEVER wrote this file:
    # `core/mining_guardian.py::__main__` then fell into its
    # `write_example_config()` fallback, exited with `Create config.json
    # from config.example.json, then re-run.`, and every dependent service
    # crash-looped with the dashboard root returning 500.
    #
    # Source-of-truth template: <payload>/config/config_template.json.
    # That file ships in via build_pkg.sh `--include 'config/***'` (added
    # in this PR). It carries the structural pieces the operator tunes
    # between releases — profile_map, model_aliases, temp_thresholds,
    # miner_filters, scan_interval_seconds, slack_interval_seconds.
    #
    # Per-install pieces injected here:
    #   * ams_base_url / ams_email / ams_password / ams_workspace_id —
    #     written as `env:KEY` placeholders so GuardianConfig._resolve()
    #     looks them up from the .env every launcher already sources.
    #     Keeps the actual credentials out of config.json.
    #   * slack_webhook_url / slack_bot_token — same env: placeholder
    #     pattern, so a key rotation is a one-line .env edit.
    #   * dry_run from MG_DRY_RUN (operator decision per site).
    #   * approval_mode default "manual" (D-2 — explicit opt-in).
    #
    # Idempotent: if ${MG_INSTALL_ROOT}/config.json already exists we
    # do NOT overwrite. Operators tune profile_map between rounds and
    # wiping their edits silently is exactly the data-loss footgun the
    # 2-vs-10 rule warns against. A re-install that wants a clean
    # config.json must remove the file first.
    #
    # Owner: ${MG_INSTALL_OPERATOR_USER}:staff, mode 0640. The launcher
    # wrappers `cd "${INSTALL_ROOT}"` so consumers find it via the
    # `config_path = os.environ.get("GUARDIAN_CONFIG", "config.json")`
    # default in core/mining_guardian.py and `_ROOT / "config.json"`
    # in api/approval_api.py.
    local dest="${MG_INSTALL_ROOT}/config.json"
    if [[ -f "$dest" ]]; then
        log "INFO config.json already present at ${dest} — preserving operator edits (P-029)"
        return 0
    fi

    local tmpl="${MG_PKG_PAYLOAD}/config/config_template.json"
    if [[ ! -r "$tmpl" ]]; then
        fail 31 "step_drop_config_json: config template missing in payload: ${tmpl} (build_pkg.sh must include 'config/***' — P-029)"
    fi

    # Use the installer-owned Python interpreter to merge JSON. The venv
    # is not yet built at this point in main()'s ordering — but the same
    # packaged interpreter that step_create_venv resolves is available
    # under <payload>/runtime/python/. Repeats the resolver from
    # step_create_venv (kept inline rather than factored out so a future
    # refactor of step_create_venv does not silently change behavior here).
    local py312=""
    if [[ -x "${MG_PKG_PAYLOAD}/runtime/python/bin/python3.12" ]]; then
        py312="${MG_PKG_PAYLOAD}/runtime/python/bin/python3.12"
    elif [[ -x "${MG_PKG_PAYLOAD}/runtime/python/Python.framework/Versions/3.12/bin/python3.12" ]]; then
        py312="${MG_PKG_PAYLOAD}/runtime/python/Python.framework/Versions/3.12/bin/python3.12"
    elif [[ -x "/opt/homebrew/opt/python@3.12/bin/python3.12" ]]; then
        py312="/opt/homebrew/opt/python@3.12/bin/python3.12"
    elif [[ -x "/usr/local/opt/python@3.12/bin/python3.12" ]]; then
        py312="/usr/local/opt/python@3.12/bin/python3.12"
    else
        py312="$(command -v python3.12 2>/dev/null || command -v python3 2>/dev/null || true)"
    fi
    if [[ -z "$py312" || ! -x "$py312" ]]; then
        fail 31 "step_drop_config_json: no python3.12 to merge config template (P-029)"
    fi

    # Merge inline. dry_run is the only customer-tunable boolean; default
    # true if MG_DRY_RUN is unset or invalid (Vision Anchor 2 — safe by
    # default). We pass MG_DRY_RUN through the environment, NOT via argv,
    # so it does not appear in `ps`.
    log "INFO writing ${dest} (template=${tmpl#${MG_PKG_PAYLOAD}/}) — P-029"
    local tmp_out="${dest}.partial.$$"
    if ! MG_TMPL="$tmpl" MG_OUT="$tmp_out" MG_DRY_RUN="${MG_DRY_RUN:-true}" \
            "$py312" - <<'PYEOF' >>"$MG_INSTALL_LOG" 2>&1
import json, os, sys
src = os.environ["MG_TMPL"]
out = os.environ["MG_OUT"]
dry = os.environ.get("MG_DRY_RUN", "true").strip().lower() == "true"
with open(src, "r", encoding="utf-8") as f:
    cfg = json.load(f)
cfg["ams_base_url"]      = "env:AMS_BASE_URL"
cfg["ams_email"]         = "env:AMS_EMAIL"
cfg["ams_password"]      = "env:AMS_PASSWORD"
cfg["ams_workspace_id"]  = "env:AMS_WORKSPACE_ID"
cfg["slack_webhook_url"] = "env:SLACK_WEBHOOK_URL"
cfg["slack_bot_token"]   = "env:SLACK_BOT_TOKEN"
cfg["dry_run"]           = dry
cfg.setdefault("approval_mode", "manual")
cfg.setdefault("rules", [])
cfg.setdefault("miner_filters", {})
with open(out, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, sort_keys=False)
    f.write("\n")
print(f"OK wrote {out}")
PYEOF
    then
        rm -f "$tmp_out"
        fail 31 "step_drop_config_json: python merge failed (P-029) — see ${MG_INSTALL_LOG}"
    fi

    install -m 0640 -o "${MG_INSTALL_OPERATOR_USER}" -g staff \
        "$tmp_out" "$dest"
    rm -f "$tmp_out"
    log "INFO wrote config.json at ${dest} (P-029)"
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
    # P-019C (2026-05-06): launcher wrappers are now owned root:wheel,
    # mode 0755 — matching the canonical comment at the top of every
    # wrapper file. macOS launchd can refuse to bootstrap a LaunchDaemon
    # (no UserName key, runs as root) whose ProgramArguments[0] points
    # at a script writable by a non-root account — failure surfaces as
    # the famously-underspecified `Bootstrap failed: 5: Input/output
    # error` (B-25). All 10 LaunchDaemons run as root, so all 10
    # wrappers must be root-owned.
    local bin="${MG_INSTALL_ROOT}/bin"
    install -d -m 0755 -o root -g wheel "$bin"

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
        install -m 0755 -o root -g wheel "$src" "$dst"
        log "INFO installed launcher: ${f}"
    done

    # 10th wrapper — feedback_loop_daemon, copied from the deploy/ tree
    # (canonical D-14 PR 4b launcher; uses file path to dodge the
    # hyphenated-package import issue).
    local fbd_src="${MG_PKG_PAYLOAD}/deploy/feedback_loop_daemon_launcher.sh"
    local fbd_dst="${bin}/feedback_loop_daemon_launcher.sh"
    if [[ ! -r "$fbd_src" ]]; then
        fail 37 "feedback_loop_daemon launcher missing in payload: ${fbd_src}"
    fi
    install -m 0755 -o root -g wheel "$fbd_src" "$fbd_dst"
    log "INFO installed launcher: feedback_loop_daemon_launcher.sh (from deploy/)"

    # P-019D (2026-05-07) — install the shared preflight library next
    # to the launchers. The 5 service launchers (dashboard_api,
    # approval_api, intelligence_report, console, feedback_loop_daemon)
    # source this file at \${INSTALL_ROOT}/bin/_preflight.sh before
    # exec'ing Python. Without this file the launchers exit 1 on the
    # `source` line — which is exactly the silent rapid-exit pattern
    # that triggers errno 5. Mode 0644 is sufficient (sourced, not
    # exec'd); root:wheel matches the rest of bin/.
    local pf_src="${LAUNCHERS_SRC}/_preflight.sh"
    local pf_dst="${bin}/_preflight.sh"
    if [[ ! -r "$pf_src" ]]; then
        fail 37 "_preflight.sh missing in payload: ${pf_src} (P-019D)"
    fi
    install -m 0644 -o root -g wheel "$pf_src" "$pf_dst"
    log "INFO installed launcher preflight library: _preflight.sh (P-019D)"

    # P-019C: explicit re-chown to root:wheel covers any prior install
    # that left the bin/ tree miningguardian-owned. Without this a
    # re-install would inherit a non-root-owned bin and the new
    # `install` flags above would not flatten the existing dir's owner.
    chown -R root:wheel "$bin"
    chmod -R u=rwX,go=rX "$bin"
    log "INFO installed ${#LAUNCHER_FILES[@]} launcher wrappers in ${bin} (root:wheel, 0755)"
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
    #   * Python 3.12 is required. P-026 (2026-05-05) made Python 3.12
    #     installer-owned — the .pkg now vendors a relocatable Python
    #     3.12 interpreter under <payload>/runtime/python/, staged at
    #     build time by `build_pkg.sh::step_4i_stage_python_runtime`
    #     from `${HOME}/MiningGuardian-vendor/python-runtime/`. The
    #     resolver below prefers the packaged interpreter and only
    #     falls back to a system python@3.12 on dev / smoke-test runs.
    #     Customers are no longer required to have Homebrew or
    #     python@3.12 on the Mac mini.
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

    # P-026 (2026-05-05) — Python 3.12 is now installer-owned.
    #
    # Operator decision (Rob, 2026-05-05): "yes include it in the
    # installer and whatever else might pop up as the install keeps
    # going". Customers must NOT be required to install Homebrew or
    # python@3.12 ahead of running the .pkg; the .pkg owns its own
    # Python 3.12 runtime under <payload>/runtime/python/.
    #
    # Resolve a Python 3.12 interpreter. Order:
    #   1. ${MG_PKG_PAYLOAD}/runtime/python/bin/python3.12
    #      — the installer-owned, vendored runtime staged by
    #        build_pkg.sh::step_4i_stage_python_runtime from
    #        ${HOME}/MiningGuardian-vendor/python-runtime/. This is the
    #        ONLY path that runs on a customer Mac mini. The build-time
    #        guardrail in step 4i refuses to produce a .pkg whose payload
    #        does not carry this interpreter.
    #   2. ${MG_PKG_PAYLOAD}/runtime/python/Python.framework/Versions/3.12/bin/python3.12
    #      — alternate framework-shaped layout (relocatable
    #        Python.framework rather than a flat tree). Same vendor
    #        directory, different upstream tarball shape. We accept either.
    #   3. /opt/homebrew/opt/python@3.12/bin/python3.12 (Apple Silicon Homebrew default)
    #   4. /usr/local/opt/python@3.12/bin/python3.12 (Intel Homebrew fallback)
    #   5. `command -v python3.12`
    # Candidates 3-5 exist ONLY for source-tree dev / smoke-test runs of
    # postinstall.sh outside a real .pkg install (the test suites in
    # tests/installer/ exercise this path). On a real customer install
    # the packaged interpreter at #1 or #2 MUST be present, and a WARN
    # is logged when we fall through to a system Python. A future tighter
    # gate could refuse-to-fall-through entirely on production installs;
    # we keep the fallback for now to avoid breaking the dev test surface.
    #
    # We do NOT accept `python3` (the Apple-supplied one is 3.9 on
    # current macOS and many of the pinned wheels require ≥ 3.12 ABI).
    local py312=""
    local py312_source=""
    local candidate

    # Tier 1 — installer-owned runtime, the ONLY production path.
    local packaged_py_flat="${MG_PKG_PAYLOAD}/runtime/python/bin/python3.12"
    local packaged_py_framework="${MG_PKG_PAYLOAD}/runtime/python/Python.framework/Versions/3.12/bin/python3.12"
    if [[ -x "$packaged_py_flat" ]]; then
        py312="$packaged_py_flat"
        py312_source="packaged-flat"
    elif [[ -x "$packaged_py_framework" ]]; then
        py312="$packaged_py_framework"
        py312_source="packaged-framework"
    fi

    # Tier 2 — Homebrew / PATH fallback for dev / smoke-test runs only.
    if [[ -z "$py312" ]]; then
        for candidate in \
            "/opt/homebrew/opt/python@3.12/bin/python3.12" \
            "/usr/local/opt/python@3.12/bin/python3.12"; do
            if [[ -x "$candidate" ]]; then
                py312="$candidate"
                py312_source="homebrew-fallback"
                break
            fi
        done
    fi
    if [[ -z "$py312" ]]; then
        py312="$(command -v python3.12 2>/dev/null || true)"
        if [[ -n "$py312" ]]; then
            py312_source="path-fallback"
        fi
    fi

    if [[ -z "$py312" || ! -x "$py312" ]]; then
        fail 38 "python3.12 not found in payload (${packaged_py_flat} or ${packaged_py_framework}) and not on this Mac; build_pkg.sh step_4i_stage_python_runtime should have staged the installer-owned runtime — see docs/RUNBOOK_PKG_REBUILD.md 'Block Pre-B — populate the Python runtime' (P-026)"
    fi

    # P-027 (2026-05-06) — quote every interpreter invocation. The
    # packaged path lives under "/Library/Application Support/MiningGuardian/"
    # which contains a space; an unquoted `${py312} --version` splits on
    # whitespace and runs `/Library/Application` as the command, which
    # exits 127 with `No such file or directory` and silently leaves the
    # version probe empty so the next assertion fires
    # `reports version '', expected '3.12'`. Round 9 of the Mac mini
    # install hit this on 2026-05-05 (post-P-026, package
    # `MiningGuardian-1.0.3-d0ba6c40a323.pkg`).
    if [[ "$py312_source" == "packaged-flat" || "$py312_source" == "packaged-framework" ]]; then
        log "INFO using installer-owned Python interpreter (${py312_source}): ${py312} ($("$py312" --version 2>&1))"
    else
        log "WARN using FALLBACK Python interpreter (${py312_source}): ${py312} ($("$py312" --version 2>&1)) — this branch is only reachable on dev / smoke-test runs; a real customer .pkg install must carry the runtime in <payload>/runtime/python/ (P-026)"
    fi

    # Sanity-check the interpreter actually reports 3.12.x. We refuse to
    # build a venv from anything else — the vendored wheels are pinned to
    # the cp312 ABI and `pip install` would fail later in this same
    # function with a less-helpful error.
    local py_ver
    py_ver="$("$py312" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
    if [[ "$py_ver" != "3.12" ]]; then
        fail 38 "resolved Python interpreter ${py312} reports version '${py_ver}', expected '3.12'; vendored wheels are cp312 only (P-026/P-027)"
    fi

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

# P-019C (2026-05-06) — bootstrap one plist with the full safe sequence
# and rich post-failure diagnostics. Returns 0 on success and 1 on any
# failure (caller continues to the next plist; the main loop summarizes
# at the end and exits FATAL only after every failed label has had its
# diagnostic dump recorded). Used by both step_install_plists_and_bootstrap
# and step_install_scheduled_plists_and_bootstrap.
#
# Sequence per label:
#   1. bootout (always, ignore errors) — clears stale load even if
#      `launchctl print` claims unloaded. macOS occasionally has stale
#      state where `print` returns "could not find service" but
#      `bootstrap` returns errno 5 because internal domain bookkeeping
#      still holds the label (B-25 root cause #1).
#   2. enable — clears any persisted disable from a prior failed
#      install. `launchctl disable` state survives reboots in
#      /var/db/com.apple.xpc.launchd/disabled.plist; without an
#      explicit `enable` a re-install can hit `bootstrap` failures
#      that look like errno 5 but are really "service is disabled"
#      with no further detail (B-25 root cause #2).
#   3. bootstrap — the actual load. Output captured to install log.
#   4. On failure: dump diagnostics. Pre-P-019C the install aborted
#      with no further output and the operator had to start over.
#   5. On success: the service is loaded. We do NOT additionally
#      `kickstart -p` — RunAtLoad=true on every plist already triggers
#      a start; a service that bootstraps but immediately exits is
#      still successfully bootstrapped (its crash is a runtime issue
#      diagnosable from logs, not a bootstrap failure).
# P-019E (2026-05-07) — wait for `launchctl print system/<label>` to
# stop returning the label after a bootout, with a bounded timeout.
#
# Why: P-019D added preflight checks inside the launcher scripts, but the
# 2026-05-06 install on the Mini still failed with `Bootstrap failed: 5:
# Input/output error` for the 5 services that already had a running
# instance from a prior manual recovery (dashboard-api, approval-api,
# intelligence-report, console, feedback-loop-daemon).
#
# Forensic finding: `launchctl bootout` is asynchronous on macOS. It
# tells launchd to tear down the existing instance and returns
# immediately — the label remains in the system domain (`launchctl print
# system/<label>` still returns it) for several hundred milliseconds
# while launchd reaps the running PID + cleans up its bookkeeping.
# `launchctl bootstrap` issued during that window observes the label is
# still registered and refuses with errno 5 (`Bootstrap failed: 5: Input/
# output error`) — exactly the symptom seen on the Mini.
#
# Operator's manual recovery worked because they ran:
#     bootout → wait until `launchctl print system/<label>` exits non-zero → bootstrap
# which is the canonical sequence Apple's launchd team recommends. This
# helper bakes that wait into the postinstall path so every install
# performs it without operator intervention.
#
# Returns 0 the moment the label is absent, returns non-zero only after
# the timeout. The caller (`_bootstrap_one_plist`) treats both outcomes
# as "proceed to enable+bootstrap" — the timeout case still attempts
# bootstrap (it might succeed; if not, the diagnostic dump captures the
# state) but logs an explicit ERROR-level warning so the operator knows
# the wait did not converge.
#
# Tunables: 30s timeout, 0.5s probe interval — both round numbers chosen
# from the operator's manual recovery (which observed convergence within
# ~1s under normal load and ~5s when the service had open Postgres
# connections to flush). 30s budgets a 6× safety margin without
# meaningfully extending the install time on the happy path.
_wait_for_label_absent() {
    local label="$1"
    local timeout_s="${2:-30}"
    local interval_s="${3:-0.5}"

    local elapsed=0
    # Probe in tenths of a second using a busy loop tracker; macOS sleep
    # accepts fractional seconds but the integer timestamp arithmetic
    # below stays bash-3.2 + BSD safe.
    local start_ts
    start_ts="$(/bin/date +%s)"
    while :; do
        if ! /bin/launchctl print "system/${label}" >/dev/null 2>&1; then
            local end_ts
            end_ts="$(/bin/date +%s)"
            elapsed=$((end_ts - start_ts))
            log "INFO label absent after bootout: ${label} (waited ~${elapsed}s)"
            return 0
        fi
        local now_ts
        now_ts="$(/bin/date +%s)"
        elapsed=$((now_ts - start_ts))
        if [[ "$elapsed" -ge "$timeout_s" ]]; then
            log "ERROR label still present after bootout + ${timeout_s}s wait: ${label} (proceeding to bootstrap anyway; diagnostic dump will follow on failure)"
            return 1
        fi
        /bin/sleep "$interval_s"
    done
}

_bootstrap_one_plist() {
    local label="$1"
    local plist_path="$2"

    /bin/launchctl bootout "system/${label}" >>"$MG_INSTALL_LOG" 2>&1 || true
    # P-019E (2026-05-07) — wait for the label to actually disappear from
    # the system domain BEFORE issuing enable+bootstrap. `bootout` is
    # async; without this wait, `bootstrap` issued in the next ~100-500ms
    # observes the label still registered and refuses with errno 5
    # (Bootstrap failed: 5: Input/output error). Observed on the
    # 2026-05-06 install where 5 of 10 LaunchDaemons had a prior running
    # instance from manual recovery and every single one failed with
    # errno 5 in this exact pattern.
    _wait_for_label_absent "$label" || true
    /bin/launchctl enable  "system/${label}" >>"$MG_INSTALL_LOG" 2>&1 || true

    local bootstrap_out
    if bootstrap_out="$(/bin/launchctl bootstrap system "$plist_path" 2>&1)"; then
        log "INFO bootstrapped ${label}"
        if [[ -n "$bootstrap_out" ]]; then
            log "      bootstrap output: ${bootstrap_out}"
        fi
        return 0
    fi

    log "ERROR launchctl bootstrap failed for ${label}: ${bootstrap_out}"
    _dump_launchctl_diagnostics "$label" "$plist_path"
    return 1
}

# Forensic dump after a bootstrap failure. Goes to MG_INSTALL_LOG so
# the operator gets one self-contained record of what was wrong.
# Every command is wrapped in `|| true` — diagnostics never raise.
_dump_launchctl_diagnostics() {
    local label="$1"
    local plist_path="$2"
    {
        echo "===== launchctl diagnostics for ${label} ====="
        echo "--- plist on-disk:"
        /bin/ls -laO "$plist_path" 2>/dev/null || true
        echo "--- plutil -lint:"
        /usr/bin/plutil -lint "$plist_path" 2>&1 || true
        echo "--- launchctl print system/${label}:"
        /bin/launchctl print "system/${label}" 2>&1 || true
        echo "--- launchctl print-disabled system | grep ${label}:"
        /bin/launchctl print-disabled system 2>&1 | /usr/bin/grep -F "$label" || true
        echo "--- launcher script (ProgramArguments[1]):"
        local launcher
        launcher="$(/usr/bin/plutil -extract ProgramArguments.1 raw "$plist_path" 2>/dev/null || true)"
        if [[ -n "$launcher" && -e "$launcher" ]]; then
            /bin/ls -laO "$launcher" 2>/dev/null || true
        else
            echo "(could not resolve ProgramArguments.1 from plist)"
        fi
        echo "--- log dir (StandardOutPath parent):"
        /bin/ls -laO "${MG_INSTALL_ROOT}/logs" 2>/dev/null || true
        # P-019D (2026-05-07) — surface the launcher's StandardErrorPath
        # log content. Pre-P-019D this file existed but was never read
        # during postinstall; the operator had to know to look in
        # /Library/Application Support/MiningGuardian/logs/ after the
        # install aborted. With the P-019D preflight library writing
        # specific error codes + diagnostic messages to stderr, the
        # tail of these logs is the single most direct signal of WHY a
        # service refused to bootstrap.
        local err_path out_path
        err_path="$(/usr/bin/plutil -extract StandardErrorPath raw "$plist_path" 2>/dev/null || true)"
        out_path="$(/usr/bin/plutil -extract StandardOutPath  raw "$plist_path" 2>/dev/null || true)"
        if [[ -n "$err_path" && -f "$err_path" ]]; then
            echo "--- StandardErrorPath tail (${err_path}):"
            /usr/bin/tail -n 80 "$err_path" 2>/dev/null || true
        else
            echo "--- StandardErrorPath: (not present at ${err_path:-unknown})"
        fi
        if [[ -n "$out_path" && -f "$out_path" ]]; then
            echo "--- StandardOutPath tail (${out_path}):"
            /usr/bin/tail -n 40 "$out_path" 2>/dev/null || true
        fi
        echo "--- recent unified log entries for the label:"
        /usr/bin/log show --predicate "subsystem == 'com.apple.xpc.launchd' AND eventMessage CONTAINS '${label}'" \
            --last 5m --info 2>/dev/null \
            | /usr/bin/tail -n 50 || true
        echo "===== end diagnostics for ${label} ====="
    } >>"$MG_INSTALL_LOG" 2>&1 || true
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

    # P-019C: bootstrap each plist via _bootstrap_one_plist with rich
    # diagnostics on failure. CONTINUE PAST per-service failures.
    # Aggregate the failure list and report at the end.
    #
    # Pre-P-019C the loop aborted on the first per-service bootstrap
    # failure with no diagnostics, leaving the operator with installed-
    # but-not-loaded plists, no record of WHY, and the rest of the
    # install (uninstall script, install receipt, baseline scan)
    # skipped. Hit on 2026-05-06 against MiningGuardian-1.0.3-b44862c…
    # on the dashboard-api bootstrap — `Bootstrap failed: 5: Input/
    # output error` with no further detail (B-25).
    local failed_services=()
    for label in "${PLIST_LABELS[@]}"; do
        if ! _bootstrap_one_plist "$label" "${PLISTS_DEST}/${label}.plist"; then
            failed_services+=("$label")
        fi
    done

    local total="${#PLIST_LABELS[@]}"
    local failed="${#failed_services[@]}"
    local ok_count=$(( total - failed ))
    log "INFO LaunchDaemon bootstrap summary: ${ok_count}/${total} loaded; ${failed} failed"

    if [[ "$failed" -gt 0 ]]; then
        log "ERROR LaunchDaemons that failed to bootstrap (${failed}):"
        local svc
        for svc in "${failed_services[@]}"; do
            log "      - ${svc}"
        done
        fail 34 "${failed} of ${total} LaunchDaemons failed to bootstrap (${failed_services[*]}). See diagnostics above for each. Recover with: sudo launchctl bootstrap system /Library/LaunchDaemons/<label>.plist (after addressing the diagnostic root cause)."
    fi
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
    # P-019C: scheduled plists run as root (no UserName key); the log
    # parent dir must be root:wheel so launchd can open StdOut/Err
    # without the "writable by non-root" refusal that surfaces as
    # `Bootstrap failed: 5: Input/output error`.
    chown root:wheel "${MG_INSTALL_ROOT}/logs/scheduled"

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

    # P-019C: bootstrap each scheduled plist via _bootstrap_one_plist
    # (same robust helper used by the service plists above). bootout-
    # then-enable-then-bootstrap, rich diagnostics on failure, continue
    # past per-job failures, summarize at the end. Exit 40 is the
    # reserved code for any scheduled-job bootstrap failure.
    local failed_jobs=()
    for label in "${SCHEDULED_PLIST_LABELS[@]}"; do
        if ! _bootstrap_one_plist "$label" "${PLISTS_DEST}/${label}.plist"; then
            failed_jobs+=("$label")
        fi
    done

    local total="${#SCHEDULED_PLIST_LABELS[@]}"
    local failed="${#failed_jobs[@]}"
    local ok_count=$(( total - failed ))
    log "INFO scheduled-job bootstrap summary: ${ok_count}/${total} loaded; ${failed} failed"

    if [[ "$failed" -gt 0 ]]; then
        log "ERROR scheduled jobs that failed to bootstrap (${failed}):"
        local svc
        for svc in "${failed_jobs[@]}"; do
            log "      - ${svc}"
        done
        fail 40 "${failed} of ${total} scheduled jobs failed to bootstrap (${failed_jobs[*]}). See diagnostics above for each."
    fi
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
    #
    # P-028 (2026-05-06) — pass MG_INSTALL_ROOT explicitly and cd into
    # it so the scanner's _resolve_log_dir() lands on
    # ${MG_INSTALL_ROOT}/logs/ instead of a relative ./logs/. Round-9b
    # of the customer Mac mini install (`MiningGuardian-1.0.3-2a3de50c4af2`)
    # hit `PermissionError: [Errno 13] Permission denied: 'logs'`
    # because postinstall's CWD is the Installer.app scripts sandbox and
    # `sudo -u miningguardian` then tried to mkdir `/logs` (CWD inherited
    # from launchd as `/`). The env var is the contract; the cd is
    # belt-and-suspenders for any future caller that still uses
    # `Path("logs")`.
    ( cd "${MG_INSTALL_ROOT}" && \
      sudo -u "${MG_INSTALL_OPERATOR_USER}" \
          /usr/bin/env "MG_INSTALL_ROOT=${MG_INSTALL_ROOT}" \
          "${MG_INSTALL_ROOT}/venv/bin/python" \
          "${MG_INSTALL_ROOT}/core/mining_guardian.py" --once \
          >> "${MG_INSTALL_LOG}" 2>&1 ) &
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
    # P-028 first: quarantine stale pre-P-024 scripts BEFORE any
    # downstream step might exec one. Independent of P-027 (different
    # paths: scripts/ vs cron_tracking/scanner_discovery/).
    step_quarantine_stale_payload_scripts
    # P-027 second: pre-create + normalise the discovery sink dir so
    # the scanner's first append succeeds. Independent of P-028.
    step_normalize_discovery_sink_perms
    # P-029 (knowledge — 2026-05-08): install baseline knowledge.json on
    # fresh install, preserve existing runtime knowledge on upgrade
    # (stages packaged seed under knowledge/incoming/ for the monthly
    # merge workflow). Independent of P-027/P-028. Runs before .env /
    # postgres / migrations / launchd bootstrap so the scanner / AI tier
    # services see a valid knowledge.json on first fire and so a missing
    # payload seed surfaces an exit-43 BEFORE Colima or model-pull.
    step_install_knowledge_json
    step_drop_dotenv
    step_provision_postgres
    # P-029 — reconcile the `mg` Postgres role's password to .env
    # immediately after provision_postgres, so re-installs over an
    # existing pgdata volume (every retry round so far) do not leave a
    # stale role password that breaks TCP auth from the host-side
    # services. Migrations + catalog seed below use docker-exec peer
    # auth and so are insensitive to this fix; the LaunchDaemons
    # bootstrapped further down are the consumers that needed it.
    step_reconcile_postgres_password
    step_apply_migrations
    step_provision_catalog_db_and_seed
    # P-018D — apply the importer's two-tier alias reference data
    # (Tier-1 in catalog DB, Tier-2 in operational DB) so
    # `mg_import_tool/resolver.py` finds non-empty alias tables on the
    # very first import. Idempotent. Must run after migrations (creates
    # `mg.model_family_aliases`) and after the catalog seed (populates
    # `hardware.miner_models` for Tier-1 FK targets).
    step_apply_alias_seeds
    step_install_ollama_and_pull_model
    step_install_launcher_wrappers
    step_create_venv
    # P-029 — write ${MG_INSTALL_ROOT}/config.json so every service
    # that reads it (scanner, approval_api, ams_alert_listener, ...)
    # finds a valid file on first start. Idempotent: preserves an
    # operator-edited config.json on re-install. Ordering: must run
    # AFTER the .env drop (provides MG_DRY_RUN) and AFTER the payload
    # has been laid down (uses <payload>/config/config_template.json),
    # and BEFORE the launchd plist bootstrap so the services never
    # start without the file present.
    step_drop_config_json
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
