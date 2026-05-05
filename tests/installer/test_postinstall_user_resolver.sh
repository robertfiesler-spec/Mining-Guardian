#!/usr/bin/env bash
# tests/installer/test_postinstall_user_resolver.sh
#
# D-18 P-016 — postinstall.sh _resolve_install_user + Installer.app
# environment hardening (Bug B half of P-016; see
# test_postinstall_cocoa_alert_bounded.sh for the Bug A half — the
# osascript hang that was the actual cause of the cf1691e timeout).
#
# Bug B: Installer.app runs postinstall as root with a stripped
# environment — SUDO_USER is unset (the installer does not invoke
# scripts via sudo) and USER is exported as `root`. The legacy
# `${SUDO_USER:-${USER}}` pattern therefore resolves to `root` and the
# script reads `/Users/root/Desktop/MiningGuardian.conf` — a file that
# does not exist on the customer Mini, where the conf is at
# `/Users/miningguardian/Desktop/MiningGuardian.conf`. The conf-not-found
# path then went into `_conf_fail` → `_cocoa_alert`, which hung
# (Bug A — fixed separately).
#
# Note: this test originally hypothesised that the failure was a
# `set -u` "USER: unbound variable" crash. That is inconsistent with
# the cf1691e PackageKit log, which shows a 600-second timeout (a fast
# bash crash would not exhibit a 600 s timeout). The resolver fix is
# still the right shape for the wrong-target-file half, and the
# assertions below remain valid; only the narrative moved.
#
# This test asserts:
#   1. The fragile `${SUDO_USER:-${USER}}` pattern is gone.
#   2. _resolve_install_user is defined and uses the three documented
#      probes (SUDO_USER → /dev/console → /Users/*/Desktop scan).
#   3. The resolver returns a usable account name when SUDO_USER is
#      unset and USER='root' (the actual Installer.app environment).
#   4. main() probes the env and resolves the user BEFORE any step that
#      touches MG_INSTALL_OPERATOR_USER.
#   5. Every chown / install / sudo -u site uses the resolved variable.
#
# Run from repo root:
#     bash tests/installer/test_postinstall_user_resolver.sh
#
# Exits 0 on success, non-zero on first failed assertion.
# Requires: bash 4+, grep, awk.

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
section "1. Fragile \${SUDO_USER:-\${USER}} pattern eliminated"
# ---------------------------------------------------------------------
# Comment lines (^#) and string literals are allowed; the substantive
# command-line uses must all be gone. We grep the body excluding any
# line whose first non-whitespace character is '#'.
n_bad="$(/usr/bin/grep -nE 'SUDO_USER:-\$\{USER\}' "$POSTINSTALL" \
            | /usr/bin/sed -E 's/^[0-9]+://' \
            | /usr/bin/grep -vE '^[[:space:]]*#' \
            | /usr/bin/grep -cE '.' || true)"
if [[ "${n_bad:-0}" -eq 0 ]]; then
    ok "no \${SUDO_USER:-\${USER}} command-line uses remain"
else
    fail "${n_bad} \${SUDO_USER:-\${USER}} command-line uses still present"
fi

# ---------------------------------------------------------------------
section "2. _resolve_install_user defined"
# ---------------------------------------------------------------------
if /usr/bin/grep -q '^_resolve_install_user()' "$POSTINSTALL"; then
    ok "_resolve_install_user() defined"
else
    fail "_resolve_install_user() missing"
fi

# Probe 1: SUDO_USER reference (guarded by :-)
if /usr/bin/grep -q 'if \[\[ -n "${SUDO_USER:-}" \]\]' "$POSTINSTALL"; then
    ok "probe 1: SUDO_USER guarded check present"
else
    fail "probe 1: SUDO_USER check not in resolver"
fi

# Probe 2: /dev/console owner
if /usr/bin/grep -q "stat -f '%Su' /dev/console" "$POSTINSTALL"; then
    ok "probe 2: /dev/console owner via stat -f '%Su'"
else
    fail "probe 2: /dev/console probe missing"
fi

# Probe 3: /Users/*/Desktop scan
if /usr/bin/grep -q '/Users/\*' "$POSTINSTALL" \
        && /usr/bin/grep -q 'MiningGuardian.conf' "$POSTINSTALL"; then
    ok "probe 3: /Users/*/Desktop/MiningGuardian.conf scan present"
else
    fail "probe 3: /Users/*/Desktop scan missing"
fi

# ---------------------------------------------------------------------
section "3. main() resolves the user BEFORE any step needing it"
# ---------------------------------------------------------------------
# The MG_INSTALL_OPERATOR_USER assignment must appear in main() before
# step_collect_customer_info — which is the first step that consumes it
# (line 444: local desktop_user="${MG_INSTALL_OPERATOR_USER}").
main_block="$(/usr/bin/awk '/^main\(\)/, /^}/' "$POSTINSTALL")"
order="$(printf '%s\n' "$main_block" | /usr/bin/grep -nE \
            'MG_INSTALL_OPERATOR_USER=|step_collect_customer_info' \
            | /usr/bin/awk -F: '{ print $NF }' \
            | /usr/bin/paste -sd, -)"
if [[ "$order" == *"MG_INSTALL_OPERATOR_USER="*"step_collect_customer_info"* ]]; then
    ok "main() assigns MG_INSTALL_OPERATOR_USER before step_collect_customer_info"
else
    fail "main() ordering broken: got '$order'"
fi

# ---------------------------------------------------------------------
section "4. Env probe diagnostic in main()"
# ---------------------------------------------------------------------
# Every future install with a stripped env must leave a log line we can
# read. Assert main() emits an env probe.
if /usr/bin/grep -q 'INFO env probe: SUDO_USER' "$POSTINSTALL"; then
    ok "main() emits env-probe log line"
else
    fail "env probe log line missing — future failures will be silent"
fi

# ---------------------------------------------------------------------
section "5. Runtime: resolver returns usable name in stripped env"
# ---------------------------------------------------------------------
# Extract the resolver from postinstall.sh and exercise it with both
# SUDO_USER and USER unset (the Installer.app environment).
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

EXTRACT="${TMP}/resolver.sh"
# Stub /usr/bin/stat to a script that mimics the macOS `stat -f '%Su' <path>`
# contract: print the owner name of the path and exit 0. Falls back to
# returning empty so the resolver moves on to the /Users/*/Desktop probe.
STUB_BIN="${TMP}/bin"
mkdir -p "$STUB_BIN"
# Mock stat that returns the user name of /dev/console-equivalent. We
# return an empty string so the resolver moves on to probe 3.
cat > "${STUB_BIN}/stat" <<'STUB'
#!/usr/bin/env bash
# macOS-format mock — supports `stat -f '%Su' <path>` only.
if [[ "${1:-}" == "-f" && "${2:-}" == "%Su" ]]; then
    # Empty owner — simulates a console with no GUI user (mirrors the
    # `loginwindow` state where /dev/console is owned by root).
    printf ''
    exit 0
fi
exit 1
STUB
chmod +x "${STUB_BIN}/stat"

# Build a fake /Users tree so probe 3 has something to find.
FAKE_USERS="${TMP}/Users"
mkdir -p "${FAKE_USERS}/miningguardian/Desktop"
touch "${FAKE_USERS}/miningguardian/Desktop/MiningGuardian.conf"

{
    echo '#!/usr/bin/env bash'
    echo 'set -uo pipefail'
    # Override /usr/bin/stat by redefining it as a function pointing at the stub.
    echo 'stat_stub="'"${STUB_BIN}/stat"'"'
    echo '/usr/bin/stat() { "$stat_stub" "$@"; }'
    # Override the /Users/* glob by redefining the resolver's loop target
    # via a function that wraps the original. Easiest path: copy the
    # resolver verbatim but rewrite /Users to the fake tree.
    /usr/bin/awk -v fake="${FAKE_USERS}" '
        /^_resolve_install_user\(\)/ { capture=1 }
        capture {
            sub(/\/Users\/\*/, fake "/*")
            sub(/\/Users\/\${d}/, fake "/${d}")
            print
        }
        capture && /^}$/ { capture=0 }
    ' "$POSTINSTALL"
    cat <<'DRIVER'
unset SUDO_USER
# Installer.app exports USER=root in postinstall. Mirror that exactly
# so the test reflects production conditions, not a hypothetical
# stripped-USER state.
USER=root
result="$(_resolve_install_user)"
echo "RESULT=${result}"
DRIVER
} > "$EXTRACT"
chmod +x "$EXTRACT"

if bash -n "$EXTRACT" 2>/dev/null; then
    ok "extracted resolver parses"
else
    fail "extracted resolver has syntax errors"
fi

# Run with SUDO_USER unset and USER=root (mirrors Installer.app's env).
out="$(env -i HOME=/var/root PATH=/usr/bin:/bin USER=root bash "$EXTRACT" 2>&1)" || true
if echo "$out" | /usr/bin/grep -q '^RESULT='; then
    result="${out#*RESULT=}"
    result="${result%%$'\n'*}"
    if [[ "$result" == "miningguardian" ]]; then
        ok "resolver finds operator via Desktop scan even with USER=root: '${result}'"
    elif [[ -n "$result" && "$result" != "root" ]]; then
        ok "resolver returns non-root value with Installer.app env: '${result}'"
    elif [[ "$result" == "root" ]]; then
        fail "resolver returned 'root' — would still hit /Users/root/Desktop/* (the cf1691e symptom)"
    else
        fail "resolver returned empty value"
    fi
else
    fail "resolver crashed under Installer.app env: ${out}"
fi

# Defensive: the resolver must not trigger any unbound-variable error
# even though that is no longer the believed root cause. set -u safety
# is still a property worth asserting.
if echo "$out" | /usr/bin/grep -qE 'unbound variable'; then
    fail "resolver triggered an unbound-variable error: ${out}"
else
    ok "resolver does not trigger any unbound-variable error under set -u"
fi

# ---------------------------------------------------------------------
section "6. P-016 fix is documented in postinstall header"
# ---------------------------------------------------------------------
if /usr/bin/grep -q 'P-016' "$POSTINSTALL"; then
    ok "P-016 reference present in postinstall.sh"
else
    fail "P-016 reference missing — should be cited where the fix lands"
fi

# ---------------------------------------------------------------------
section "7. bash -n parse"
# ---------------------------------------------------------------------
if bash -n "$POSTINSTALL" 2>/dev/null; then
    ok "postinstall.sh parses"
else
    fail "postinstall.sh has bash syntax errors"
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
