#!/usr/bin/env bash
# tests/installer/test_postinstall_launchd_robust.sh
#
# P-019C — postinstall.sh static checks for the robust LaunchDaemon
# bootstrap. Asserts the install can survive (and diagnose) a per-
# service bootstrap failure rather than aborting the whole install
# the first time `launchctl bootstrap` returns "Bootstrap failed: 5:
# Input/output error".
#
# Background: 2026-05-06 install on `MiningGuardian-1.0.3-b44862c…`
# failed at the dashboard-api bootstrap with errno 5 and zero
# diagnostics. Postinstall aborted mid-loop, leaving the install in
# a half-laid-down state — uninstall script not written, install
# receipt not stamped, baseline scan not run.
#
# Source-tree static checks only — no live launchctl, no Mac.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

POSTINSTALL="installer/macos-pkg/scripts/postinstall.sh"
LAUNCHERS_DIR="installer/macos-pkg/resources/launchd/launchers"

pass_count=0
fail_count=0
ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }
section() { echo; echo "## $*"; }


section "1. Source files exist"
for f in "$POSTINSTALL"; do
    if [[ -r "$f" ]]; then
        ok "$f present"
    else
        fail "$f missing"
    fi
done


section "2. _bootstrap_one_plist + _dump_launchctl_diagnostics defined"
if grep -qE '^_bootstrap_one_plist\(\)' "$POSTINSTALL"; then
    ok "_bootstrap_one_plist() defined"
else
    fail "_bootstrap_one_plist() missing"
fi
if grep -qE '^_dump_launchctl_diagnostics\(\)' "$POSTINSTALL"; then
    ok "_dump_launchctl_diagnostics() defined"
else
    fail "_dump_launchctl_diagnostics() missing"
fi


section "3. Bootout / enable / bootstrap sequence inside the helper"
helper_body="$(awk '/^_bootstrap_one_plist\(\)/,/^\}/' "$POSTINSTALL")"

if echo "$helper_body" | grep -qE 'launchctl bootout'; then
    ok "helper invokes bootout"
else
    fail "helper missing bootout step"
fi
if echo "$helper_body" | grep -qE 'launchctl enable'; then
    ok "helper invokes enable (clears persisted disable)"
else
    fail "helper missing enable step"
fi
if echo "$helper_body" | grep -qE 'launchctl bootstrap system'; then
    ok "helper invokes bootstrap system <plist_path>"
else
    fail "helper missing bootstrap step"
fi
helper_lines="$(echo "$helper_body" | grep -nE 'bootout|enable|bootstrap system' || true)"
bootout_line="$(echo "$helper_lines" | grep -m1 bootout | cut -d: -f1)"
enable_line="$(echo "$helper_lines" | grep -m1 enable | cut -d: -f1)"
bootstrap_line="$(echo "$helper_lines" | grep -m1 'bootstrap system' | cut -d: -f1)"
if [[ -n "$bootout_line" ]] && [[ -n "$enable_line" ]] && [[ -n "$bootstrap_line" ]] \
        && [[ "$bootout_line" -lt "$enable_line" ]] \
        && [[ "$enable_line" -lt "$bootstrap_line" ]]; then
    ok "ordering: bootout ($bootout_line) < enable ($enable_line) < bootstrap ($bootstrap_line)"
else
    fail "ordering wrong: bootout=$bootout_line enable=$enable_line bootstrap=$bootstrap_line"
fi


section "4. Diagnostics helper covers the right surfaces"
diag_body="$(awk '/^_dump_launchctl_diagnostics\(\)/,/^\}/' "$POSTINSTALL")"

declare -a expected_surfaces=(
    "ls -laO"
    "plutil -lint"
    "launchctl print"
    "launchctl print-disabled"
    "log show"
)
for surface in "${expected_surfaces[@]}"; do
    if echo "$diag_body" | grep -F -q "$surface"; then
        ok "diagnostics include: ${surface}"
    else
        fail "diagnostics MISSING: ${surface}"
    fi
done

if echo "$diag_body" | grep -qE '\|\| true'; then
    ok "diagnostics are non-fatal (|| true wrapping)"
else
    fail "diagnostics command(s) lack || true"
fi


section "5. step_install_plists_and_bootstrap calls the helper"
plists_body="$(awk '/^step_install_plists_and_bootstrap\(\)/,/^step_install_scheduled_plists_and_bootstrap/' "$POSTINSTALL")"

if echo "$plists_body" | grep -qE '_bootstrap_one_plist'; then
    ok "step_install_plists_and_bootstrap delegates to _bootstrap_one_plist"
else
    fail "step_install_plists_and_bootstrap does NOT call _bootstrap_one_plist"
fi


section "6. Per-service failure aggregation + summary"
if echo "$plists_body" | grep -qE 'failed_services\+='; then
    ok "step_install_plists_and_bootstrap accumulates failures into failed_services"
else
    fail "step_install_plists_and_bootstrap missing failed_services accumulator"
fi
if echo "$plists_body" | grep -qE 'LaunchDaemon bootstrap summary'; then
    ok "step_install_plists_and_bootstrap emits a summary line"
else
    fail "step_install_plists_and_bootstrap missing summary line"
fi
if echo "$plists_body" | grep -qE 'fail 34.*LaunchDaemons'; then
    ok "step_install_plists_and_bootstrap fails 34 AT THE END (after diagnostics)"
else
    fail "step_install_plists_and_bootstrap final fail-34 not at end-of-loop"
fi


section "7. Scheduled bootstrap reuses the same helper"
sched_body="$(awk '/^step_install_scheduled_plists_and_bootstrap\(\)/,/^step_install_uninstall_script/' "$POSTINSTALL")"

if echo "$sched_body" | grep -qE '_bootstrap_one_plist'; then
    ok "step_install_scheduled_plists_and_bootstrap delegates to _bootstrap_one_plist"
else
    fail "step_install_scheduled_plists_and_bootstrap does NOT call _bootstrap_one_plist"
fi
if echo "$sched_body" | grep -qE 'failed_jobs\+='; then
    ok "step_install_scheduled_plists_and_bootstrap accumulates failures into failed_jobs"
else
    fail "step_install_scheduled_plists_and_bootstrap missing failed_jobs accumulator"
fi
if echo "$sched_body" | grep -qE 'scheduled-job bootstrap summary'; then
    ok "step_install_scheduled_plists_and_bootstrap emits a summary line"
else
    fail "step_install_scheduled_plists_and_bootstrap missing summary line"
fi
if echo "$sched_body" | grep -qE 'fail 40'; then
    ok "step_install_scheduled_plists_and_bootstrap reserves exit 40"
else
    fail "step_install_scheduled_plists_and_bootstrap missing fail 40"
fi


section "8. Launcher wrappers installed root:wheel"
launcher_body="$(awk '/^step_install_launcher_wrappers\(\)/,/^step_create_venv/' "$POSTINSTALL")"

if echo "$launcher_body" | grep -qE 'install -m 0755 -o "\$\{MG_INSTALL_OPERATOR_USER\}" -g staff'; then
    fail "launcher install still uses miningguardian:staff — pre-P-019C shape"
else
    ok "no launcher install lines use miningguardian:staff"
fi
if echo "$launcher_body" | grep -qE 'install -m 0755 -o root -g wheel'; then
    ok "launcher install lines use -o root -g wheel"
else
    fail "no launcher install line uses -o root -g wheel"
fi
if echo "$launcher_body" | grep -qE 'chown -R root:wheel'; then
    ok "final chown -R root:wheel covers re-install"
else
    fail "final chown -R is not root:wheel"
fi


section "9. Launcher comment ↔ install ownership consistency"
declare -a wrapper_files=(
    "${LAUNCHERS_DIR}/scanner_launcher.sh"
    "${LAUNCHERS_DIR}/dashboard_api_launcher.sh"
    "${LAUNCHERS_DIR}/approval_api_launcher.sh"
)
for w in "${wrapper_files[@]}"; do
    if [[ -r "$w" ]]; then
        if grep -q "owner root:wheel" "$w"; then
            ok "$(basename "$w"): header comment claims root:wheel ownership"
        else
            fail "$(basename "$w"): header comment does NOT claim root:wheel"
        fi
    else
        fail "wrapper missing: $w"
    fi
done


section "10. logs/ + bin/ are root:wheel after step_layout_install_root"
layout_body="$(awk '/^step_layout_install_root\(\)/,/^_cocoa_alert/' "$POSTINSTALL")"

if echo "$layout_body" | grep -qE 'chown root:wheel "\$\{MG_INSTALL_ROOT\}/bin"'; then
    ok "step_layout_install_root chowns bin/ to root:wheel"
else
    fail "step_layout_install_root does NOT chown bin/ to root:wheel"
fi
if echo "$layout_body" | grep -qE 'chown root:wheel "\$\{MG_INSTALL_ROOT\}/logs"'; then
    ok "step_layout_install_root chowns logs/ to root:wheel"
else
    fail "step_layout_install_root does NOT chown logs/ to root:wheel"
fi


section "11. logs/scheduled is root:wheel"
if echo "$sched_body" | grep -qE 'chown root:wheel "\$\{MG_INSTALL_ROOT\}/logs/scheduled"'; then
    ok "step_install_scheduled_plists_and_bootstrap chowns logs/scheduled to root:wheel"
else
    fail "step_install_scheduled_plists_and_bootstrap does NOT chown logs/scheduled to root:wheel"
fi


section "12. P-019C explanatory comments present"
if grep -qE 'P-019C' "$POSTINSTALL"; then
    ok "postinstall.sh references P-019C"
else
    fail "postinstall.sh missing P-019C marker"
fi
if grep -qE 'Input/output error|errno 5|Bootstrap failed: 5' "$POSTINSTALL"; then
    ok "postinstall.sh documents the errno-5 failure class"
else
    fail "postinstall.sh missing errno-5 explanation"
fi


section "Summary"
echo
echo "Passed: ${pass_count}"
echo "Failed: ${fail_count}"
if [[ "$fail_count" -gt 0 ]]; then
    exit 1
fi
echo "ALL OK"
