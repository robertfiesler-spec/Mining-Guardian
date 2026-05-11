#!/usr/bin/env bash
# tests/installer/test_p039_scanner_recurrence.sh
#
# P-039 (2026-05-11) — scanner LaunchDaemon recurrence and --loop invocation.
#
# Background. During the 2026-05-10 Sunday VPS + ROBS-PC isolation crossover
# the Mac Mini's scanner LaunchDaemon was observed to be green only after
# manual `launchctl kickstart`. It did not run naturally overnight on
# 2026-05-10 → 2026-05-11. Inspection of the live plist
# `/Library/LaunchDaemons/com.miningguardian.scanner.plist` showed:
#   - RunAtLoad=true
#   - KeepAlive only on Crashed=true
#   - NO StartInterval / StartCalendarInterval
# and the launcher (`scanner_launcher.sh`) exec'd
# `${VENV_PYTHON} -u ${ENTRY_POINT}` with NO `--loop`. Because
# core/mining_guardian.py's `if __name__ == "__main__"` block calls
# `run_once()` when `--loop` is absent and then exits cleanly,
# KeepAlive=Crashed-only never re-launched the daemon. With no
# StartInterval, launchd had no clock to re-fire the job. Result:
# one scan per manual kickstart, then silence.
#
# Manual proof on 2026-05-11 04:41: Mini scanner kickstart succeeded,
# scan #26 saved to Postgres, Qwen analysis succeeded, `llm_scan_analyses`
# advanced to 184, knowledge.json saved, NO_OLD_HOST_TCP to all retired
# host IPs. Recurring scans without manual kickstart still required.
#
# P-039 fix (this PR):
#   1. installer/macos-pkg/resources/launchd/launchers/scanner_launcher.sh
#      now `exec`s python WITH `--loop`. The daemon stays alive and runs
#      the 8 in-process AI features after each scan per CLAUDE.md project
#      intent (`runs all 8 AI features in loop() after each scan`).
#   2. installer/macos-pkg/resources/launchd/com.miningguardian.scanner.plist
#      adds `StartInterval=3600` as a belt-and-suspenders safety net. If
#      the daemon ever exits cleanly (which should not happen under
#      --loop), launchd re-launches within one hour. Documented in the
#      plist comments why launchd cannot read scan_interval_seconds from
#      .env directly (no EnvironmentFile= equivalent on launchd).
#   3. RunAtLoad=true and KeepAlive.Crashed=true are preserved.
#
# This test asserts:
#   1. The packaged plist parses (xmllint or `plutil -lint` if present)
#      and is well-formed XML.
#   2. The packaged plist declares Label=com.miningguardian.scanner.
#   3. The packaged plist has RunAtLoad=true.
#   4. The packaged plist has KeepAlive.Crashed=true and
#      KeepAlive.SuccessfulExit=false.
#   5. The packaged plist has StartInterval=3600 (P-039 safety net).
#   6. The packaged plist's ProgramArguments invoke
#      /Library/Application Support/MiningGuardian/bin/scanner_launcher.sh
#      under /bin/bash.
#   7. The launcher passes `--loop` to the python entry point
#      (`core/mining_guardian.py`).
#   8. The launcher still sources .env, exports MG_INSTALL_ROOT, and
#      cd's into INSTALL_ROOT before exec (preserves P-028 fix).
#   9. postinstall.sh still names com.miningguardian.scanner in its
#      service-label list and still copies scanner_launcher.sh from
#      LAUNCHERS_SRC, so the plist + launcher both land in the
#      customer payload.
#  10. The pkg-build path that stages launchd resources is unchanged
#      (P-025 step 4k still includes the scanner plist + launcher).
#
# Run from repo root:
#     bash tests/installer/test_p039_scanner_recurrence.sh
#
# Exits 0 on success, non-zero on first failed assertion.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PLIST="installer/macos-pkg/resources/launchd/com.miningguardian.scanner.plist"
LAUNCHER="installer/macos-pkg/resources/launchd/launchers/scanner_launcher.sh"
POSTINSTALL="installer/macos-pkg/scripts/postinstall.sh"
BUILD_PKG="installer/macos-pkg/scripts/build_pkg.sh"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }
section() { echo; echo "## $*"; }


# ---------------------------------------------------------------------
section "1. Scanner plist is present and well-formed"
# ---------------------------------------------------------------------
if [[ -r "$PLIST" ]]; then
    ok "${PLIST} present"
else
    fail "${PLIST} missing"
    echo "  passed: ${pass_count}"
    echo "  failed: ${fail_count}"
    exit 1
fi

if command -v plutil >/dev/null 2>&1; then
    if plutil -lint "$PLIST" >/dev/null 2>&1; then
        ok "plutil -lint passes"
    else
        fail "plutil -lint failed: $(plutil -lint "$PLIST" 2>&1)"
    fi
elif command -v xmllint >/dev/null 2>&1; then
    if xmllint --noout "$PLIST" 2>/dev/null; then
        ok "xmllint passes (plutil unavailable on this host)"
    else
        fail "xmllint reports the plist is not well-formed XML"
    fi
else
    # Last-resort: python's plistlib.
    if python3 -c "import plistlib,sys; plistlib.load(open(sys.argv[1],'rb'))" "$PLIST" 2>/dev/null; then
        ok "python3 plistlib parses the plist (plutil + xmllint both unavailable)"
    else
        fail "no XML validator available, and python3 plistlib could not parse the plist"
    fi
fi


# ---------------------------------------------------------------------
section "2. Plist declares Label=com.miningguardian.scanner"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE '<string>com\.miningguardian\.scanner</string>' "$PLIST"; then
    ok "Label value present"
else
    fail "Label value 'com.miningguardian.scanner' missing"
fi


# ---------------------------------------------------------------------
section "3. RunAtLoad=true preserved"
# ---------------------------------------------------------------------
# Look for the <key>RunAtLoad</key> followed by <true/> on the next non-blank line.
run_at_load_value="$(awk '
    /<key>RunAtLoad<\/key>/ {flag=1; next}
    flag && /<true\/>/ {print "true"; exit}
    flag && /<false\/>/ {print "false"; exit}
' "$PLIST")"
if [[ "$run_at_load_value" == "true" ]]; then
    ok "RunAtLoad=true"
else
    fail "RunAtLoad is not true (got: '${run_at_load_value:-MISSING}')"
fi


# ---------------------------------------------------------------------
section "4. KeepAlive.Crashed=true and KeepAlive.SuccessfulExit=false preserved"
# ---------------------------------------------------------------------
keepalive_block="$(awk '
    /<key>KeepAlive<\/key>/ {flag=1}
    flag {print}
    flag && /<\/dict>/ {exit}
' "$PLIST")"

# Match the Crashed key's immediately-following <true/> line.
if echo "$keepalive_block" | awk '
    /<key>Crashed<\/key>/ {flag=1; next}
    flag && /<true\/>/ {found=1; exit}
    flag && /<false\/>/ {flag=0}
    END {exit !found}
'; then
    ok "KeepAlive.Crashed=true"
else
    fail "KeepAlive.Crashed is not true"
fi

if echo "$keepalive_block" | awk '
    /<key>SuccessfulExit<\/key>/ {flag=1; next}
    flag && /<false\/>/ {found=1; exit}
    flag && /<true\/>/ {flag=0}
    END {exit !found}
'; then
    ok "KeepAlive.SuccessfulExit=false"
else
    fail "KeepAlive.SuccessfulExit is not false"
fi


# ---------------------------------------------------------------------
section "5. StartInterval=3600 present (P-039 safety net)"
# ---------------------------------------------------------------------
# Prefer python3 plistlib for a structured lookup; fall back to a
# portable awk-then-sed scrape if python3 is missing.
start_interval_value=""
if command -v python3 >/dev/null 2>&1; then
    start_interval_value="$(python3 -c "
import plistlib, sys
p = plistlib.load(open(sys.argv[1], 'rb'))
v = p.get('StartInterval')
print('' if v is None else int(v))
" "$PLIST" 2>/dev/null)"
fi
if [[ -z "$start_interval_value" ]]; then
    start_interval_value="$(awk '
        /<key>StartInterval<\/key>/ {flag=1; next}
        flag && /<integer>/ {print; exit}
    ' "$PLIST" | /usr/bin/sed -E 's/.*<integer>([0-9]+)<\/integer>.*/\1/' | tr -cd '0-9')"
fi
if [[ "$start_interval_value" == "3600" ]]; then
    ok "StartInterval=3600 (hourly)"
elif [[ -z "$start_interval_value" ]]; then
    fail "StartInterval missing — P-039 safety net not packaged"
else
    fail "StartInterval is not 3600 (got: ${start_interval_value})"
fi


# ---------------------------------------------------------------------
section "6. ProgramArguments invoke scanner_launcher.sh via /bin/bash"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE '<string>/bin/bash</string>' "$PLIST"; then
    ok "ProgramArguments uses /bin/bash"
else
    fail "ProgramArguments does not use /bin/bash"
fi
if /usr/bin/grep -qE '<string>/Library/Application Support/MiningGuardian/bin/scanner_launcher\.sh</string>' "$PLIST"; then
    ok "ProgramArguments invokes scanner_launcher.sh from the install root"
else
    fail "ProgramArguments does not invoke scanner_launcher.sh from the install root"
fi


# ---------------------------------------------------------------------
section "7. Launcher passes --loop to the python entry point"
# ---------------------------------------------------------------------
if [[ -r "$LAUNCHER" ]]; then
    ok "${LAUNCHER} present"
else
    fail "${LAUNCHER} missing"
    echo "  passed: ${pass_count}"
    echo "  failed: ${fail_count}"
    exit 1
fi

if bash -n "$LAUNCHER" 2>/dev/null; then
    ok "launcher is syntactically valid bash"
else
    fail "launcher has shell syntax errors"
fi

# The launcher's final exec line must include both ${ENTRY_POINT} and --loop.
exec_line="$(/usr/bin/grep -E '^exec[[:space:]]' "$LAUNCHER" | tail -1)"
if [[ -z "$exec_line" ]]; then
    fail "could not find a final 'exec' line in ${LAUNCHER}"
else
    ok "found final exec line: ${exec_line}"
    if echo "$exec_line" | /usr/bin/grep -qF '${ENTRY_POINT}'; then
        ok "exec line references \${ENTRY_POINT}"
    else
        fail "exec line does not reference \${ENTRY_POINT}"
    fi
    if echo "$exec_line" | /usr/bin/grep -qE '(^|[[:space:]])--loop([[:space:]]|$)'; then
        ok "exec line passes --loop (P-039 fix)"
    else
        fail "exec line does NOT pass --loop — P-039 regression"
    fi
fi


# ---------------------------------------------------------------------
section "8. Launcher preserves env handling (sources .env, exports MG_INSTALL_ROOT, cd's into INSTALL_ROOT)"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE '^source[[:space:]]+"\$\{ENV_FILE\}"' "$LAUNCHER" || \
   /usr/bin/grep -qE 'source[[:space:]]+"\$\{ENV_FILE\}"' "$LAUNCHER"; then
    ok "launcher still sources \${ENV_FILE}"
else
    fail "launcher no longer sources \${ENV_FILE}"
fi

if /usr/bin/grep -qE '^export[[:space:]]+MG_INSTALL_ROOT=' "$LAUNCHER"; then
    ok "launcher still exports MG_INSTALL_ROOT (P-028 preserved)"
else
    fail "launcher no longer exports MG_INSTALL_ROOT — P-028 regression"
fi

if /usr/bin/grep -qE '^cd[[:space:]]+"\$\{INSTALL_ROOT\}"' "$LAUNCHER"; then
    ok "launcher still cd's into INSTALL_ROOT"
else
    fail "launcher no longer cd's into INSTALL_ROOT"
fi


# ---------------------------------------------------------------------
section "9. postinstall.sh still installs the scanner plist and launcher"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE '"com\.miningguardian\.scanner"' "$POSTINSTALL"; then
    ok "postinstall.sh lists com.miningguardian.scanner in its service-label list"
else
    fail "postinstall.sh no longer lists com.miningguardian.scanner"
fi

if /usr/bin/grep -qE '"scanner_launcher\.sh"' "$POSTINSTALL"; then
    ok "postinstall.sh lists scanner_launcher.sh among the launchers to install"
else
    fail "postinstall.sh no longer lists scanner_launcher.sh"
fi


# ---------------------------------------------------------------------
section "10. build_pkg.sh step 4k still stages launchd/ into the payload"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE 'installer-resources' "$BUILD_PKG" && \
   /usr/bin/grep -qE 'launchd' "$BUILD_PKG"; then
    ok "build_pkg.sh still references the installer-resources/launchd staging path (P-025)"
else
    fail "build_pkg.sh appears to have lost the installer-resources/launchd staging — P-025 regression"
fi


# ---------------------------------------------------------------------
section "Summary"
# ---------------------------------------------------------------------
echo "  passed: ${pass_count}"
echo "  failed: ${fail_count}"

if (( fail_count > 0 )); then
    exit 1
fi
exit 0
