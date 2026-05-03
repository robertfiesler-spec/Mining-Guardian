#!/usr/bin/env bash
# tests/installer/test_postinstall_scheduled_jobs.sh
#
# D-18 Gap 4 / P-007 — scheduled-jobs launchd plists static checks.
#
# Asserts that the launchd plists that replace setup.sh::phase_10_cron
# are correctly authored and wired into the .pkg installer pipeline,
# AND that the legacy cron path is genuinely gone (no silent regression
# back to crontab behavior on a future setup.sh edit).
#
# This test runs against the source tree only — no Mac, no Installer.app,
# no actual launchctl bootstrap. The full smoke test is the v1.0.3
# verification gate per D-18 ("clean macOS 14 VM"). Static checks only.
#
# Run from repo root:
#     bash tests/installer/test_postinstall_scheduled_jobs.sh
#
# Exits 0 on success, non-zero on first failed assertion.
# Requires: bash, grep, find, python3.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

POSTINSTALL="installer/macos-pkg/scripts/postinstall.sh"
BUILD_PKG="installer/macos-pkg/scripts/build_pkg.sh"
SETUP_SH="scripts/setup.sh"
SCHED_DIR="installer/macos-pkg/resources/launchd/scheduled"
LAUNCHER="installer/macos-pkg/resources/launchd/launchers/scheduled_job_launcher.sh"
TASK_REGISTRY="console/task_registry.py"

# 11 scheduled-job labels — must match across:
#   * SCHED_DIR/<label>.plist files
#   * postinstall.sh SCHEDULED_PLIST_LABELS
#   * setup.sh phase_10_scheduled labels list
#   * console/task_registry.py plist_label values
SCHEDULED_LABELS=(
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

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }

section() { echo; echo "## $*"; }

# ---------------------------------------------------------------------
section "1. Files exist"
# ---------------------------------------------------------------------
for f in "$POSTINSTALL" "$BUILD_PKG" "$SETUP_SH" "$LAUNCHER" "$TASK_REGISTRY"; do
    if [[ -r "$f" ]]; then
        ok "$f present"
    else
        fail "$f missing"
    fi
done

if [[ -d "$SCHED_DIR" ]]; then
    ok "${SCHED_DIR}/ directory exists"
else
    fail "${SCHED_DIR}/ directory missing"
fi

# ---------------------------------------------------------------------
section "2. All 11 scheduled-job plists present"
# ---------------------------------------------------------------------
for lbl in "${SCHEDULED_LABELS[@]}"; do
    p="${SCHED_DIR}/${lbl}.plist"
    if [[ -r "$p" ]]; then
        ok "plist present: ${lbl}.plist"
    else
        fail "plist missing: ${p}"
    fi
done

# Exactly 11 — guard against an accidental 12th plist landing without
# the corresponding postinstall / setup.sh / console registry update.
plist_count="$(/usr/bin/find "$SCHED_DIR" -maxdepth 1 -type f -name '*.plist' | /usr/bin/wc -l | /usr/bin/tr -d ' ')"
if [[ "$plist_count" -eq 11 ]]; then
    ok "exactly 11 .plist files in ${SCHED_DIR}/"
else
    fail "expected 11 plist files in ${SCHED_DIR}/, found ${plist_count}"
fi

# ---------------------------------------------------------------------
section "3. Every plist parses as valid plist XML"
# ---------------------------------------------------------------------
for lbl in "${SCHEDULED_LABELS[@]}"; do
    p="${SCHED_DIR}/${lbl}.plist"
    if python3 -c "import plistlib; plistlib.load(open('${p}','rb'))" 2>/dev/null; then
        ok "plist parses: ${lbl}.plist"
    else
        fail "plist does not parse: ${p}"
    fi
done

# ---------------------------------------------------------------------
section "4. Every plist has the expected scheduling primitive"
# ---------------------------------------------------------------------
# 10 plists use StartCalendarInterval; the benchmark plist uses
# StartInterval=3600 (hourly).
for lbl in "${SCHEDULED_LABELS[@]}"; do
    p="${SCHED_DIR}/${lbl}.plist"
    if [[ "$lbl" == "com.miningguardian.scheduled.benchmark" ]]; then
        if /usr/bin/grep -q '<key>StartInterval</key>' "$p" \
                && /usr/bin/grep -q '<integer>3600</integer>' "$p"; then
            ok "${lbl}: StartInterval=3600 present (hourly)"
        else
            fail "${lbl}: missing StartInterval=3600"
        fi
    else
        if /usr/bin/grep -q '<key>StartCalendarInterval</key>' "$p"; then
            ok "${lbl}: StartCalendarInterval present"
        else
            fail "${lbl}: missing StartCalendarInterval"
        fi
    fi
done

# ---------------------------------------------------------------------
section "5. Every plist invokes scheduled_job_launcher.sh"
# ---------------------------------------------------------------------
for lbl in "${SCHEDULED_LABELS[@]}"; do
    p="${SCHED_DIR}/${lbl}.plist"
    if /usr/bin/grep -q 'scheduled_job_launcher.sh' "$p"; then
        ok "${lbl}: invokes scheduled_job_launcher.sh"
    else
        fail "${lbl}: does not invoke scheduled_job_launcher.sh"
    fi
done

# ---------------------------------------------------------------------
section "6. Launcher syntax + offline guarantees"
# ---------------------------------------------------------------------
if bash -n "$LAUNCHER" 2>/dev/null; then
    ok "scheduled_job_launcher.sh parses"
else
    fail "scheduled_job_launcher.sh has bash syntax errors"
fi

# Launcher must source .env, refuse to run without it, and dispatch by
# extension — these are the contract callers depend on.
if /usr/bin/grep -q 'source "${ENV_FILE}"' "$LAUNCHER"; then
    ok "launcher sources .env"
else
    fail "launcher does not source .env — secrets not propagated"
fi
if /usr/bin/grep -q '${VENV_PYTHON}' "$LAUNCHER" \
        && /usr/bin/grep -q '/bin/bash' "$LAUNCHER"; then
    ok "launcher dispatches python (.py) AND bash (.sh) entrypoints"
else
    fail "launcher does not dispatch both .py and .sh entrypoints"
fi
if /usr/bin/grep -q 'last-run.json' "$LAUNCHER"; then
    ok "launcher writes per-run stamp file (console /tasks dependency)"
else
    fail "launcher does not write last-run.json — operator console will show no last-run data"
fi

# ---------------------------------------------------------------------
section "7. postinstall.sh wires SCHEDULED_PLIST_LABELS + new step"
# ---------------------------------------------------------------------
if bash -n "$POSTINSTALL" 2>/dev/null; then
    ok "postinstall.sh parses"
else
    fail "postinstall.sh has bash syntax errors"
fi

if /usr/bin/grep -q '^readonly SCHEDULED_PLIST_LABELS=' "$POSTINSTALL"; then
    ok "SCHEDULED_PLIST_LABELS array declared"
else
    fail "SCHEDULED_PLIST_LABELS array missing"
fi

# Every label must appear inside the SCHEDULED_PLIST_LABELS block.
for lbl in "${SCHEDULED_LABELS[@]}"; do
    if /usr/bin/grep -q "\"${lbl}\"" "$POSTINSTALL"; then
        ok "postinstall.sh references ${lbl}"
    else
        fail "postinstall.sh missing ${lbl}"
    fi
done

if /usr/bin/grep -q '^step_install_scheduled_plists_and_bootstrap()' "$POSTINSTALL"; then
    ok "step_install_scheduled_plists_and_bootstrap() defined"
else
    fail "step_install_scheduled_plists_and_bootstrap() missing"
fi

# Must be called inside main() — and AFTER step_install_plists_and_bootstrap
# (services first, scheduled after).
call_order="$(/usr/bin/awk '/^main\(\)/, /^}/' "$POSTINSTALL" \
    | /usr/bin/grep -oE 'step_(install_plists_and_bootstrap|install_scheduled_plists_and_bootstrap|write_install_receipt)' \
    | /usr/bin/paste -sd, -)"
expected="step_install_plists_and_bootstrap,step_install_scheduled_plists_and_bootstrap,step_write_install_receipt"
if [[ "$call_order" == "$expected" ]]; then
    ok "main() ordering: services → scheduled → receipt"
else
    fail "main() ordering wrong (got '${call_order}', expected '${expected}')"
fi

# Exit code 40 reserved for scheduled-job failures.
if /usr/bin/grep -qE '^#[[:space:]]+40[[:space:]]+—' "$POSTINSTALL"; then
    ok "exit code 40 documented in postinstall header"
else
    fail "exit code 40 not documented in postinstall header"
fi
if /usr/bin/grep -qE 'fail 40 "' "$POSTINSTALL"; then
    ok "fail 40 used in step_install_scheduled_plists_and_bootstrap"
else
    fail "fail 40 not used — scheduled-bootstrap errors will report wrong exit code"
fi

# scheduled_job_launcher.sh must be in LAUNCHER_FILES so the existing
# step_install_launcher_wrappers copies it to ${INSTALL_ROOT}/bin/.
if /usr/bin/grep -q '"scheduled_job_launcher.sh"' "$POSTINSTALL"; then
    ok "scheduled_job_launcher.sh listed in LAUNCHER_FILES"
else
    fail "scheduled_job_launcher.sh not in LAUNCHER_FILES — wrapper would not ship to ${INSTALL_ROOT}/bin/"
fi

# scheduled_job_count must appear in the install-receipt JSON so the
# console / verification gate can read it back.
if /usr/bin/grep -q '"scheduled_job_count":' "$POSTINSTALL"; then
    ok "install-receipt includes scheduled_job_count"
else
    fail "install-receipt missing scheduled_job_count field"
fi

# ---------------------------------------------------------------------
section "8. build_pkg.sh step 4i assertion"
# ---------------------------------------------------------------------
if bash -n "$BUILD_PKG" 2>/dev/null; then
    ok "build_pkg.sh parses"
else
    fail "build_pkg.sh has bash syntax errors"
fi
if /usr/bin/grep -q 'step 4i' "$BUILD_PKG"; then
    ok "build_pkg.sh has step 4i (scheduled-plists assertion)"
else
    fail "build_pkg.sh step 4i missing — scheduled plists could silently drop out of payload"
fi
if /usr/bin/grep -q '_die 47' "$BUILD_PKG"; then
    ok "build_pkg.sh reserves exit 47 for D-18 Gap 4 build assertions"
else
    fail "build_pkg.sh exit code 47 missing"
fi

# ---------------------------------------------------------------------
section "9. setup.sh phase_10 — cron is gone, launchd is in"
# ---------------------------------------------------------------------
if bash -n "$SETUP_SH" 2>/dev/null; then
    ok "setup.sh parses"
else
    fail "setup.sh has bash syntax errors"
fi

# phase_10 must call the new launchd-based function from main().
if /usr/bin/grep -qE '\bphase_10_scheduled\b' "$SETUP_SH"; then
    ok "phase_10_scheduled defined and called"
else
    fail "phase_10_scheduled missing"
fi

# Active code path must NOT install crontab entries. The legacy
# `crontab -` invocation is a smoking gun; if it ever returns, the
# operator path silently regresses to the FDA-blocked cron behavior.
# We allow `crontab` to appear in the deprecation shim or comments, but
# `(...) | crontab -` (the install line) MUST be gone.
if /usr/bin/grep -qE '\| crontab -[[:space:]]*$' "$SETUP_SH"; then
    fail "setup.sh still pipes into 'crontab -' — D-18 Gap 4 regressed"
else
    ok "setup.sh does not pipe into 'crontab -' (crontab install path removed)"
fi

# Heredoc constants should be gone too.
if /usr/bin/grep -q 'Mining Guardian cron schedule' "$SETUP_SH"; then
    fail "setup.sh still contains 'Mining Guardian cron schedule' header — leftover from cron block"
else
    ok "setup.sh no longer contains the cron block header"
fi

# StartCalendarInterval is the new primitive — phase_10_scheduled should
# reference it (or the plist files it installs).
if /usr/bin/grep -q 'launchctl bootstrap' "$SETUP_SH"; then
    ok "setup.sh invokes launchctl bootstrap (launchd path in use)"
else
    fail "setup.sh missing launchctl bootstrap call"
fi

# Same 11 labels must appear inside setup.sh too.
for lbl in "${SCHEDULED_LABELS[@]}"; do
    if /usr/bin/grep -q "\"${lbl}\"" "$SETUP_SH"; then
        ok "setup.sh references ${lbl}"
    else
        fail "setup.sh missing ${lbl}"
    fi
done

# ---------------------------------------------------------------------
section "10. console/task_registry.py label drift check"
# ---------------------------------------------------------------------
# Every label declared in the scheduled plists must be the plist_label
# the operator console reads from. Drift here breaks the /tasks page.
for lbl in "${SCHEDULED_LABELS[@]}"; do
    if /usr/bin/grep -q "\"${lbl}\"" "$TASK_REGISTRY"; then
        ok "task_registry references ${lbl}"
    else
        fail "task_registry missing ${lbl} — console /tasks would not find this plist"
    fi
done

# ---------------------------------------------------------------------
section "11. Each plist routes its own log files (per task_key)"
# ---------------------------------------------------------------------
# StandardOutPath / StandardErrorPath should land under
# /Library/Application Support/MiningGuardian/logs/scheduled/<task_key>.{out,err}.log
# so the operator console (D-19) can surface them without a per-job lookup table.
for lbl in "${SCHEDULED_LABELS[@]}"; do
    p="${SCHED_DIR}/${lbl}.plist"
    if /usr/bin/grep -q '/logs/scheduled/' "$p"; then
        ok "${lbl}: log paths under logs/scheduled/"
    else
        fail "${lbl}: log paths NOT under logs/scheduled/"
    fi
done

# ---------------------------------------------------------------------
section "Summary"
# ---------------------------------------------------------------------
echo
echo "Passed: $pass_count"
echo "Failed: $fail_count"
if (( fail_count > 0 )); then
    exit 1
fi
exit 0
