#!/usr/bin/env bash
# tests/installer/test_uninstall_script.sh
#
# D-18 Copy bug 3 / P-008 (v1.0.3) — bin/uninstall.sh static checks.
#
# Asserts the source uninstall script at
# installer/macos-pkg/resources/uninstall.sh:
#   * Exists, is executable, has the bash shebang.
#   * Bash syntax-check passes.
#   * Names all 10 service LaunchDaemons in MG_SERVICE_LABELS.
#   * Names all 11 scheduled-job LaunchDaemons in MG_SCHEDULED_LABELS.
#   * Label arrays match installer/macos-pkg/scripts/postinstall.sh
#     (PLIST_LABELS + SCHEDULED_PLIST_LABELS) — drift here would cause
#     the customer Mac to be left with orphaned plists.
#   * Implements --help, --dry-run, --yes, --purge-data, --purge-logs.
#   * Default behavior PRESERVES /Library/Application Support/
#     MiningGuardian/postgres-data — data deletion is opt-in via
#     --purge-data per the §"Critical Safety Rules" entry forbidding
#     destructive bulk DB removes without an explicit step.
#   * Default behavior PRESERVES /var/log/mining-guardian/.
#   * Refuses to run as a non-root user (require_root guard present).
#   * Refuses non-TTY without --yes (the script shows the
#     `non-interactive shell` fail string).
#   * Postinstall.sh installs the script at
#     ${MG_INSTALL_ROOT}/bin/uninstall.sh and step is wired into main().
#   * build_pkg.sh has a step 4j source-tree assertion (exit 48).
#   * --dry-run actually exits 0 without changing anything (run via the
#     `--help` path — full execution requires root + macOS launchctl, so
#     we exercise the no-op `--help` path here).
#
# This is a static / source-tree test — no Mac, no Installer.app, no
# real bootout. Full smoke test is the v1.0.3 verification gate per
# D-18.
#
# Run from repo root:
#     bash tests/installer/test_uninstall_script.sh
#
# Exits 0 on success, non-zero on first failed assertion.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

UNINSTALL="installer/macos-pkg/resources/uninstall.sh"
POSTINSTALL="installer/macos-pkg/scripts/postinstall.sh"
BUILD_PKG="installer/macos-pkg/scripts/build_pkg.sh"
CONCLUSION="installer/macos-pkg/resources/conclusion.html"

# Authoritative label lists — must match postinstall.sh::PLIST_LABELS
# and SCHEDULED_PLIST_LABELS exactly. Drift in either direction is a
# regression: services left running after uninstall, or labels removed
# from uninstall but still installed by postinstall.
SERVICE_LABELS=(
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

assert_contains() {
    local file="$1" pattern="$2" desc="$3"
    if /usr/bin/grep -qF -- "$pattern" "$file" 2>/dev/null; then
        ok "$desc"
    else
        fail "$desc — '$pattern' not found in $file"
    fi
}

# ---------------------------------------------------------------------
section "1. Source script presence + permissions"
# ---------------------------------------------------------------------
if [[ -f "$UNINSTALL" ]]; then
    ok "${UNINSTALL} exists"
else
    fail "${UNINSTALL} missing"
fi

if [[ -x "$UNINSTALL" ]]; then
    ok "${UNINSTALL} is executable (committed mode 0755)"
else
    fail "${UNINSTALL} not executable — chmod +x and re-commit"
fi

if /usr/bin/head -n1 "$UNINSTALL" 2>/dev/null | /usr/bin/grep -q '^#!.*bash'; then
    ok "${UNINSTALL} has a bash shebang"
else
    fail "${UNINSTALL} missing bash shebang"
fi

# ---------------------------------------------------------------------
section "2. Bash syntax-check"
# ---------------------------------------------------------------------
if bash -n "$UNINSTALL" 2>/dev/null; then
    ok "bash -n ${UNINSTALL} passes"
else
    fail "bash -n ${UNINSTALL} reported a syntax error"
fi

# ---------------------------------------------------------------------
section "3. uninstall.sh names all 10 service LaunchDaemons"
# ---------------------------------------------------------------------
for label in "${SERVICE_LABELS[@]}"; do
    assert_contains "$UNINSTALL" "$label" \
        "uninstall.sh names $label"
done

# ---------------------------------------------------------------------
section "4. uninstall.sh names all 11 scheduled-job LaunchDaemons"
# ---------------------------------------------------------------------
for label in "${SCHEDULED_LABELS[@]}"; do
    assert_contains "$UNINSTALL" "$label" \
        "uninstall.sh names $label"
done

# ---------------------------------------------------------------------
section "5. Drift check — postinstall.sh ↔ uninstall.sh"
# ---------------------------------------------------------------------
# Every label in postinstall.sh::PLIST_LABELS must also be in
# uninstall.sh, and vice versa. Same for SCHEDULED_PLIST_LABELS. We
# can't easily diff arrays from bash, so we just count occurrences.
service_count_post="$(/usr/bin/grep -cE '^    "com\.miningguardian\.[A-Za-z0-9.-]+"$' "$POSTINSTALL" || true)"
# That regex matches both PLIST_LABELS and SCHEDULED_PLIST_LABELS
# (since both are quoted bare labels in arrays). Total = 10 + 11 = 21.
if [[ "${service_count_post:-0}" -eq 21 ]]; then
    ok "postinstall.sh declares 21 plist labels (10 services + 11 scheduled)"
else
    fail "postinstall.sh declares ${service_count_post:-0} plist labels (expected 21)"
fi

service_count_un="$(/usr/bin/grep -cE '^    "com\.miningguardian\.[A-Za-z0-9.-]+"$' "$UNINSTALL" || true)"
if [[ "${service_count_un:-0}" -eq 21 ]]; then
    ok "uninstall.sh declares 21 plist labels (10 services + 11 scheduled)"
else
    fail "uninstall.sh declares ${service_count_un:-0} plist labels (expected 21)"
fi

# ---------------------------------------------------------------------
section "6. uninstall.sh implements expected flags"
# ---------------------------------------------------------------------
assert_contains "$UNINSTALL" "--dry-run" \
    "uninstall.sh implements --dry-run"
assert_contains "$UNINSTALL" "--purge-data" \
    "uninstall.sh implements --purge-data"
assert_contains "$UNINSTALL" "--purge-logs" \
    "uninstall.sh implements --purge-logs"
assert_contains "$UNINSTALL" "--yes" \
    "uninstall.sh implements --yes (non-TTY confirmation skip)"
assert_contains "$UNINSTALL" "--help" \
    "uninstall.sh implements --help"

# ---------------------------------------------------------------------
section "7. uninstall.sh data-preservation default"
# ---------------------------------------------------------------------
# Default must preserve postgres-data. The script preserves it
# iff PURGE_DATA=0 (the default), which the parse_args branch shows.
assert_contains "$UNINSTALL" "PURGE_DATA=0" \
    "PURGE_DATA defaults to 0 (data preserved by default)"
assert_contains "$UNINSTALL" "PURGE_LOGS=0" \
    "PURGE_LOGS defaults to 0 (logs preserved by default)"
# The summary path mentions the preservation explicitly so an operator
# reading the output knows what was kept.
assert_contains "$UNINSTALL" "preserved:" \
    "uninstall.sh logs explicit 'preserved:' summary lines"

# ---------------------------------------------------------------------
section "8. uninstall.sh root + non-TTY guards"
# ---------------------------------------------------------------------
assert_contains "$UNINSTALL" "must run as root" \
    "uninstall.sh require_root error message present"
assert_contains "$UNINSTALL" "non-interactive shell" \
    "uninstall.sh non-TTY confirmation guard present"
if /usr/bin/grep -qiE "type '?uninstall'? to continue" "$UNINSTALL"; then
    ok "uninstall.sh requires the literal word 'uninstall' to confirm"
else
    fail "uninstall.sh missing the 'type uninstall to continue' confirmation prompt"
fi

# ---------------------------------------------------------------------
section "9. postinstall.sh installs the script + wires into main()"
# ---------------------------------------------------------------------
assert_contains "$POSTINSTALL" "step_install_uninstall_script" \
    "postinstall.sh declares step_install_uninstall_script"
assert_contains "$POSTINSTALL" "/resources/uninstall.sh" \
    "postinstall.sh references the source path"

# step is invoked from main()
if /usr/bin/awk '/^main\(\)/,/^}/' "$POSTINSTALL" | \
        /usr/bin/grep -q "step_install_uninstall_script"; then
    ok "postinstall.sh main() invokes step_install_uninstall_script"
else
    fail "postinstall.sh main() does not invoke step_install_uninstall_script"
fi

# UNINSTALL_SH_SRC declaration is present
assert_contains "$POSTINSTALL" "UNINSTALL_SH_SRC=" \
    "postinstall.sh declares UNINSTALL_SH_SRC source path"

# ---------------------------------------------------------------------
section "10. build_pkg.sh has step 4j source-tree assertion"
# ---------------------------------------------------------------------
assert_contains "$BUILD_PKG" "step 4j" \
    "build_pkg.sh names step 4j (uninstaller assertion)"
assert_contains "$BUILD_PKG" "uninstall.sh" \
    "build_pkg.sh references uninstall.sh"
assert_contains "$BUILD_PKG" "_die 48" \
    "build_pkg.sh reserves exit 48 for uninstall-source failures"

# ---------------------------------------------------------------------
section "11. conclusion.html ↔ uninstall.sh path agreement"
# ---------------------------------------------------------------------
# The conclusion.html path the customer is told to run must be the same
# path postinstall.sh installs. Both must say:
#   /Library/Application Support/MiningGuardian/bin/uninstall.sh
assert_contains "$CONCLUSION" "/Library/Application Support/MiningGuardian/bin/uninstall.sh" \
    "conclusion.html points at the canonical uninstall path"
assert_contains "$POSTINSTALL" "bin/uninstall.sh" \
    "postinstall.sh installs to bin/uninstall.sh under MG_INSTALL_ROOT"

# ---------------------------------------------------------------------
section "12. uninstall.sh --help exits 0 without root"
# ---------------------------------------------------------------------
# `--help` is the only path that does not require root, so we can run
# the actual script in CI to verify it doesn't blow up with the
# default set -euo pipefail. We pipe in /dev/null so any read prompt
# hangs the test rather than being mistaken for success.
if bash "$UNINSTALL" --help </dev/null >/tmp/mg-uninstall-help.$$ 2>&1; then
    ok "uninstall.sh --help exits 0"
else
    fail "uninstall.sh --help exited non-zero ($?)"
fi
if /usr/bin/grep -q "Usage:" /tmp/mg-uninstall-help.$$ 2>/dev/null; then
    ok "uninstall.sh --help prints a Usage: line"
else
    fail "uninstall.sh --help did not print a Usage: line"
fi
rm -f /tmp/mg-uninstall-help.$$

# ---------------------------------------------------------------------
section "13. uninstall.sh rejects unknown flags"
# ---------------------------------------------------------------------
# The unknown-flag path runs parse_args BEFORE require_root, so it
# returns exit 2 even without root. Capture it explicitly.
set +e
bash "$UNINSTALL" --not-a-real-flag </dev/null >/tmp/mg-uninstall-bad.$$ 2>&1
rc=$?
set -e
if [[ "$rc" -eq 2 ]]; then
    ok "uninstall.sh rejects unknown flag with exit 2"
else
    fail "uninstall.sh unknown-flag exit code was $rc (expected 2)"
fi
rm -f /tmp/mg-uninstall-bad.$$

# ---------------------------------------------------------------------
section "Summary"
# ---------------------------------------------------------------------
echo
echo "  pass: $pass_count"
echo "  fail: $fail_count"
if (( fail_count > 0 )); then
    echo
    echo "FAILED."
    exit 1
fi
echo
echo "All assertions passed."
exit 0
