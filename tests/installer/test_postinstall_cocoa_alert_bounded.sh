#!/usr/bin/env bash
# tests/installer/test_postinstall_cocoa_alert_bounded.sh
#
# D-18 P-016 — postinstall.sh _cocoa_alert wall-clock bound (Bug A half
# of P-016). See test_postinstall_user_resolver.sh for the Bug B half.
#
# Why this exists. The cf1691e Mac mini install showed only:
#
#   2026-05-04T23:48:44Z [postinstall] Mining Guardian postinstall starting
#   2026-05-04T23:48:44Z [postinstall] PKG_PATH=... TARGET=/ ...
#   2026-05-04T23:48:44Z [postinstall] INFO sourced env: ...
#   2026-05-04T23:48:44Z [postinstall] INFO loaded helper libs
#
# …then 600 s of silence, then PackageKit's "exceeded 600 seconds of
# runtime" kill in /var/log/install.log. No FATAL line was emitted.
#
# A 600 s timeout rules out a fast `set -u` crash (bash would have
# exited within milliseconds). The script was alive but blocked. The
# only synchronous external call between `INFO loaded helper libs` and
# the never-emitted next log line was `_cocoa_alert` calling
# `osascript display dialog` from inside `_conf_fail`. macOS osascript
# `display dialog` blocks indefinitely waiting for a click — and when
# the parent process is root in an Installer.app postinstall context,
# there is no Window Server connection and no way for a click to reach
# it. The dialog hangs until PackageKit's 600 s watchdog kills the
# whole script.
#
# This test asserts that `_cocoa_alert` is now hard-bounded so the
# postinstall can NEVER hang in this code path again, regardless of
# whether the dialog is delivered.
#
# Asserts:
#   1. _cocoa_alert is defined.
#   2. The AppleScript carries `giving up after <N>` (dialog auto-dismiss).
#   3. There is a wall-clock watchdog around the osascript subprocess
#      (kill -KILL after a bounded sleep loop). macOS does NOT ship
#      coreutils `timeout(1)` so the wrapper must be pure-bash — we
#      assert the watchdog idiom rather than a `timeout(1)` invocation.
#   4. _cocoa_alert routes through the GUI console user via
#      `launchctl asuser` so the dialog can actually render.
#   5. RUNTIME: with osascript stubbed to sleep forever, _cocoa_alert
#      returns within 15 wall-clock seconds (10 s budget + 5 s slack).
#
# Run from repo root:
#     bash tests/installer/test_postinstall_cocoa_alert_bounded.sh
#
# Exits 0 on success, non-zero on first failed assertion.
# Requires: bash 4+, grep, awk, /bin/sleep, /usr/bin/time-equivalent.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

POSTINSTALL="installer/macos-pkg/scripts/postinstall.sh"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }

section() { echo; echo "## $*"; }

# ---------------------------------------------------------------------
section "1. _cocoa_alert defined"
# ---------------------------------------------------------------------
if /usr/bin/grep -q '^_cocoa_alert()' "$POSTINSTALL"; then
    ok "_cocoa_alert() defined"
else
    fail "_cocoa_alert() missing"
fi

# ---------------------------------------------------------------------
section "2. AppleScript dialog has 'giving up after' clause"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE 'giving up after [0-9]+' "$POSTINSTALL"; then
    ok "AppleScript dialog auto-dismisses ('giving up after N')"
else
    fail "AppleScript missing 'giving up after N' — dialog can hang waiting for a click"
fi

# ---------------------------------------------------------------------
section "3. Wall-clock watchdog wraps the osascript subprocess"
# ---------------------------------------------------------------------
# macOS does not ship coreutils timeout(1). The wrapper must be pure
# bash. Look for the kill -KILL idiom inside _cocoa_alert.
alert_block="$(/usr/bin/awk '/^_cocoa_alert\(\)/,/^}/' "$POSTINSTALL")"

if printf '%s\n' "$alert_block" | /usr/bin/grep -q 'kill -KILL'; then
    ok "watchdog uses kill -KILL to bound wall-clock"
else
    fail "watchdog missing kill -KILL — osascript can hang the install"
fi

if printf '%s\n' "$alert_block" | /usr/bin/grep -qE 'while \(\( i < [0-9]+ \)\)'; then
    ok "watchdog uses bounded poll loop"
else
    fail "watchdog poll loop missing or unbounded"
fi

# Belt+suspenders: NEVER call /usr/bin/timeout (not on macOS by default).
if printf '%s\n' "$alert_block" | /usr/bin/grep -qE '/usr/bin/timeout|^[[:space:]]*timeout '; then
    fail "_cocoa_alert depends on /usr/bin/timeout — that binary does not ship on macOS"
else
    ok "_cocoa_alert avoids /usr/bin/timeout (pure-bash watchdog)"
fi

# ---------------------------------------------------------------------
section "4. Dialog delivery routed through GUI console user"
# ---------------------------------------------------------------------
if printf '%s\n' "$alert_block" | /usr/bin/grep -q 'launchctl asuser'; then
    ok "dialog routed via launchctl asuser when console user is present"
else
    fail "dialog not routed via launchctl asuser — root has no Window Server"
fi

# Console probe must guard against console_user='root' (no GUI session).
if printf '%s\n' "$alert_block" \
        | /usr/bin/grep -qE 'console_user.*!=.*"root"|"\$\{console_user\}".*!=.*"root"'; then
    ok "console-user check skips when /dev/console owner is root"
else
    fail "console-user check missing — would route asuser to root and re-hang"
fi

# ---------------------------------------------------------------------
section "5. RUNTIME: _cocoa_alert returns within 15s when osascript hangs"
# ---------------------------------------------------------------------
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Stub osascript to hang forever. Place at /usr/bin/osascript priority
# via a shim shell that defines osascript as a function pointing at the
# stub.
STUB="${TMP}/osascript_hang"
cat > "$STUB" <<'STUB'
#!/usr/bin/env bash
# Mock osascript: sleep forever to simulate the cf1691e dialog hang.
exec sleep 600
STUB
chmod +x "$STUB"

# Build a driver that loads _cocoa_alert (and its deps) from
# postinstall.sh and exercises it with the hang-stub.
DRIVER="${TMP}/driver.sh"
{
    echo '#!/usr/bin/env bash'
    echo 'set -uo pipefail'
    echo "MG_INSTALL_LOG=${TMP}/mg.log"
    echo "stub=${STUB}"
    # Override /usr/bin/osascript and the "command -v /usr/bin/osascript"
    # check by routing through /usr/bin/env with a synthetic PATH. Easier:
    # define a function that intercepts /usr/bin/osascript.
    cat <<'SHIM'
/usr/bin/osascript() { "$stub" "$@"; }
command() {
    if [[ "${1:-}" == "-v" && "${2:-}" == "/usr/bin/osascript" ]]; then
        echo "/usr/bin/osascript"
        return 0
    fi
    builtin command "$@"
}
# Ensure no console GUI user is found, so the fallback osascript path
# is exercised — that path is the one most at risk of hanging in prod.
/usr/bin/stat() { printf 'root'; }
/usr/bin/id()   { printf '0'; }
SHIM
    # Pull in just the _cocoa_alert function from postinstall.sh.
    /usr/bin/awk '/^_cocoa_alert\(\)/,/^}/' "$POSTINSTALL"
    cat <<'TAIL'
# Run _cocoa_alert and time it.
start=$(date +%s)
_cocoa_alert "test title" "test body"
end=$(date +%s)
elapsed=$(( end - start ))
echo "ELAPSED=${elapsed}"
TAIL
} > "$DRIVER"
chmod +x "$DRIVER"

if ! bash -n "$DRIVER" 2>/dev/null; then
    fail "test driver has syntax errors"
else
    out="$(bash "$DRIVER" 2>&1)" || true
    elapsed_line="$(printf '%s\n' "$out" | /usr/bin/grep '^ELAPSED=' || true)"
    if [[ -z "$elapsed_line" ]]; then
        fail "_cocoa_alert did not return — output: ${out}"
    else
        elapsed="${elapsed_line#ELAPSED=}"
        if [[ "$elapsed" -le 15 ]]; then
            ok "_cocoa_alert returned in ${elapsed}s (≤ 15 s budget) despite osascript hang"
        else
            fail "_cocoa_alert took ${elapsed}s — watchdog not bounding wall-clock"
        fi
    fi
fi

# ---------------------------------------------------------------------
section "6. P-016 Bug A reference present in postinstall header"
# ---------------------------------------------------------------------
if /usr/bin/grep -q 'Bug A' "$POSTINSTALL"; then
    ok "Bug A (osascript hang) called out in postinstall.sh"
else
    fail "postinstall.sh does not document Bug A (osascript hang)"
fi

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
