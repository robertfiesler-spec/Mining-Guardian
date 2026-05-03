#!/usr/bin/env bash
# tests/installer/test_installer_copy.sh
#
# D-18 Copy bugs 1, 2, 4 / P-008 (v1.0.3) — installer welcome/conclusion
# copy static checks.
#
# Asserts that installer/macos-pkg/resources/welcome.html and
# conclusion.html reflect v1.0.3 install reality:
#   * 10 service LaunchDaemons (NOT four)
#   * 11 scheduled-job LaunchDaemons (mentioned, with launchd wording)
#   * No `cron` / `crontab` wording (Mining Guardian uses launchd, never
#     cron, on the v1.0.3 install path — Failure mode: silent regression
#     to crontab on a future copy edit).
#   * Console URL :8787 present (NOT :8686 — D-19 / P-006 port conflict)
#   * Dashboard URL :8585 present (NOT :8080 — stale v1.0.2 placeholder)
#   * Approval API URL :8686 present
#   * No misleading "Grafana control" wording — Grafana is the visibility
#     surface only, the operator console (:8787) is the control surface
#     (D-19 tech-stack split). A `:3000` Grafana URL reference is
#     allowed if it appears, but no copy claiming Grafana toggles services.
#   * The uninstall path mentioned matches the installed path:
#     /Library/Application Support/MiningGuardian/bin/uninstall.sh
#   * The Desktop MiningGuardian.conf hand-off is mentioned in welcome
#     (so the customer knows to look for the file) — D-18 Gap 1 customer
#     experience.
#   * "Mining Guardian" branding renders in HTML, not the legacy typo.
#
# Static check only — no Mac, no Installer.app, no WebKit render.
#
# Run from repo root:
#     bash tests/installer/test_installer_copy.sh
#
# Exits 0 on success, non-zero on first failed assertion.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

WELCOME="installer/macos-pkg/resources/welcome.html"
CONCLUSION="installer/macos-pkg/resources/conclusion.html"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }

section() { echo; echo "## $*"; }

# Assert that `pattern` appears in `file` (literal grep).
assert_contains() {
    local file="$1" pattern="$2" desc="$3"
    if /usr/bin/grep -qF -- "$pattern" "$file" 2>/dev/null; then
        ok "$desc"
    else
        fail "$desc — '$pattern' not found in $file"
    fi
}

# Assert that `pattern` does NOT appear in `file`.
assert_not_contains() {
    local file="$1" pattern="$2" desc="$3"
    if /usr/bin/grep -qF -- "$pattern" "$file" 2>/dev/null; then
        fail "$desc — '$pattern' must NOT appear in $file"
    else
        ok "$desc"
    fi
}

assert_not_contains_re() {
    local file="$1" pattern="$2" desc="$3"
    if /usr/bin/grep -qE -- "$pattern" "$file" 2>/dev/null; then
        fail "$desc — pattern /$pattern/ must NOT appear in $file"
    else
        ok "$desc"
    fi
}

# ---------------------------------------------------------------------
section "1. Files exist"
# ---------------------------------------------------------------------
for f in "$WELCOME" "$CONCLUSION"; do
    if [[ -r "$f" ]]; then
        ok "$f present"
    else
        fail "$f missing"
    fi
done

# ---------------------------------------------------------------------
section "2. welcome.html — service / scheduled-job counts"
# ---------------------------------------------------------------------
assert_contains "$WELCOME" "ten background services" \
    "welcome mentions ten background services"
assert_contains "$WELCOME" "eleven scheduled jobs" \
    "welcome mentions eleven scheduled jobs"
assert_not_contains "$WELCOME" "four background services" \
    "welcome no longer says 'four background services'"
assert_not_contains "$WELCOME" "nine background services" \
    "welcome no longer says 'nine background services' (pre-console count)"
assert_contains "$WELCOME" "launchd" \
    "welcome mentions launchd (the macOS-native scheduler)"

# ---------------------------------------------------------------------
section "3. welcome.html — no cron/crontab wording"
# ---------------------------------------------------------------------
# Customer copy must not reference cron or crontab — Mining Guardian
# v1.0.3 ships scheduled jobs as launchd plists per D-18 Gap 4.
assert_not_contains_re "$WELCOME" "(crontab|[Cc]ron job|[Cc]ron entries)" \
    "welcome contains no crontab / cron-job wording"

# ---------------------------------------------------------------------
section "4. welcome.html — ports + Desktop conf hand-off"
# ---------------------------------------------------------------------
assert_contains "$WELCOME" "127.0.0.1:8585" \
    "welcome dashboard URL is :8585"
assert_contains "$WELCOME" "127.0.0.1:8787" \
    "welcome operator console URL is :8787"
assert_not_contains "$WELCOME" "127.0.0.1:8080" \
    "welcome no longer references the stale :8080 dashboard URL"
assert_not_contains "$WELCOME" "127.0.0.1:8081" \
    "welcome no longer references the stale :8081 approval URL"
assert_contains "$WELCOME" "MiningGuardian.conf" \
    "welcome mentions the Desktop MiningGuardian.conf hand-off (D-18 Gap 1)"

# ---------------------------------------------------------------------
section "5. welcome.html — no Grafana-control claim"
# ---------------------------------------------------------------------
# Grafana is read-only visibility per D-19. Customer copy must not
# imply the customer toggles services from Grafana.
assert_not_contains_re "$WELCOME" "[Gg]rafana[^.]*(toggle|control|enable|disable|approve)" \
    "welcome contains no Grafana-control claim"

# ---------------------------------------------------------------------
section "6. conclusion.html — service / scheduled-job counts"
# ---------------------------------------------------------------------
assert_contains "$CONCLUSION" "ten background services" \
    "conclusion mentions ten background services"
assert_contains "$CONCLUSION" "eleven scheduled jobs" \
    "conclusion mentions eleven scheduled jobs"
assert_not_contains "$CONCLUSION" "four background services" \
    "conclusion no longer says 'four background services'"
assert_not_contains "$CONCLUSION" "All four" \
    "conclusion no longer says 'All four' services"
assert_contains "$CONCLUSION" "Verifying the ten services" \
    "conclusion verify section heading uses 'ten'"

# ---------------------------------------------------------------------
section "7. conclusion.html — verify code block enumerates all 10 services"
# ---------------------------------------------------------------------
# Each of the 10 service labels must appear at least once inside the
# conclusion (the verify code block enumerates them).
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
for label in "${SERVICE_LABELS[@]}"; do
    assert_contains "$CONCLUSION" "$label" \
        "conclusion verify block names $label"
done

# ---------------------------------------------------------------------
section "8. conclusion.html — scheduled-jobs verify hint present"
# ---------------------------------------------------------------------
assert_contains "$CONCLUSION" "com.miningguardian.scheduled." \
    "conclusion shows scheduled-job listing command (grep prefix)"

# ---------------------------------------------------------------------
section "9. conclusion.html — quick-link ports correct"
# ---------------------------------------------------------------------
assert_contains "$CONCLUSION" "127.0.0.1:8585" \
    "conclusion dashboard URL is :8585"
assert_contains "$CONCLUSION" "127.0.0.1:8686" \
    "conclusion approval API URL is :8686"
assert_contains "$CONCLUSION" "127.0.0.1:8787" \
    "conclusion operator console URL is :8787"
assert_not_contains "$CONCLUSION" "127.0.0.1:8080" \
    "conclusion no longer references the stale :8080 dashboard URL"
assert_not_contains "$CONCLUSION" "127.0.0.1:8081" \
    "conclusion no longer references the stale :8081 approval URL"

# ---------------------------------------------------------------------
section "10. conclusion.html — uninstall path matches install reality"
# ---------------------------------------------------------------------
assert_contains "$CONCLUSION" "/Library/Application Support/MiningGuardian/bin/uninstall.sh" \
    "conclusion points at the same uninstall path postinstall installs"
assert_contains "$CONCLUSION" "ten services and eleven scheduled jobs" \
    "conclusion uninstall blurb names both service classes"
assert_contains "$CONCLUSION" "--purge-data" \
    "conclusion mentions --purge-data opt-in"
assert_contains "$CONCLUSION" "--dry-run" \
    "conclusion mentions --dry-run preview"

# ---------------------------------------------------------------------
section "11. conclusion.html — no cron/crontab wording"
# ---------------------------------------------------------------------
assert_not_contains_re "$CONCLUSION" "(crontab|[Cc]ron job|[Cc]ron entries)" \
    "conclusion contains no crontab / cron-job wording"

# ---------------------------------------------------------------------
section "12. conclusion.html — no Grafana-control claim"
# ---------------------------------------------------------------------
assert_not_contains_re "$CONCLUSION" "[Gg]rafana[^.]*(toggle|control|enable|disable|approve)" \
    "conclusion contains no Grafana-control claim"

# ---------------------------------------------------------------------
section "13. Branding"
# ---------------------------------------------------------------------
assert_not_contains "$WELCOME" "Mining Gaurdian" \
    "welcome uses correct 'Mining Guardian' spelling"
assert_not_contains "$CONCLUSION" "Mining Gaurdian" \
    "conclusion uses correct 'Mining Guardian' spelling"

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
