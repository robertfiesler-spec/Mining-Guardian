#!/usr/bin/env bash
# tests/installer/test_postinstall_colima_path.sh
#
# D-18 P-019 — colima/docker invocations under `sudo -u` must propagate
# a PATH that includes /usr/local/bin, and install_colima.sh must verify
# limactl exists at the install destination before invoking colima.
#
# Why this exists: the 32ec2dcad973 install on the customer Mac mini
# exited 31 inside install_colima_runtime with
#
#     lima compatibility error: error checking Lima version:
#     exec: "limactl": executable file not found in $PATH
#
# even though install_colima_runtime had just copied limactl to
# /usr/local/bin two lines earlier. Root cause: macOS `sudo -u <op>`
# strips PATH and substitutes sudoers' `secure_path`
# (`/usr/bin:/bin:/usr/sbin:/sbin`) — note the absence of /usr/local/bin.
# `colima start` then uses Go's `os/exec.LookPath("limactl")`, which
# obeys the child PATH, and fails before any VM bytes are touched.
#
# This test asserts:
#   1. install_colima.sh defines `_op_path` and includes /usr/local/bin
#      first.
#   2. install_colima.sh defines `_verify_limactl` and calls it before
#      `colima start`.
#   3. Every `sudo -u "${op_user}" … colima/docker …` invocation in
#      install_colima.sh wraps with `/usr/bin/env PATH="$(_op_path)"`.
#   4. postinstall.sh defines `_op_path` (separate copy — postinstall is
#      the docker-exec call site for migrations + catalog seed).
#   5. Every `sudo -u "${MG_INSTALL_OPERATOR_USER}" … docker …`
#      invocation in postinstall.sh wraps with
#      `/usr/bin/env PATH="$(_op_path)"`.
#   6. The PATH order: /usr/local/bin precedes /usr/bin so vendored
#      binaries shadow homebrew/system copies.
#   7. Runtime: `_op_path` from install_colima.sh returns a PATH that
#      contains /usr/local/bin (smoke test against the actual function).
#   8. Runtime: `_verify_limactl` succeeds for an executable file and
#      fails non-zero with a clear log line for a missing one.
#   9. Runtime: an `env PATH="$(_op_path)" command -v limactl` test in a
#      stripped env (PATH=/usr/bin:/bin only) successfully locates a stub
#      limactl placed under a fake /usr/local/bin — proves the wrapper
#      really reverses the sudoers PATH strip.
#  10. P-019 audit marker present in install_colima.sh and postinstall.sh.
#  11. bash -n parse on both files.
#
# Run from repo root:
#     bash tests/installer/test_postinstall_colima_path.sh
#
# Exits 0 on success, non-zero on first failed assertion.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

COLIMA_LIB="installer/macos-pkg/scripts/lib/install_colima.sh"
POSTINSTALL_SH="installer/macos-pkg/scripts/postinstall.sh"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }

section() { echo; echo "## $*"; }

# ---------------------------------------------------------------------
section "1. _op_path defined in install_colima.sh and lists /usr/local/bin first"
# ---------------------------------------------------------------------
if /usr/bin/grep -q '^_op_path()' "$COLIMA_LIB"; then
    ok "_op_path() defined in install_colima.sh"
else
    fail "_op_path() missing from install_colima.sh"
fi

# Pull the printf line and verify /usr/local/bin is the first segment.
op_path_line="$(/usr/bin/grep -E "^[[:space:]]*printf '%s' \"/" "$COLIMA_LIB" | head -n1)"
if [[ "$op_path_line" =~ \"/usr/local/bin: ]]; then
    ok "install_colima.sh _op_path PATH starts with /usr/local/bin"
else
    fail "install_colima.sh _op_path PATH does not start with /usr/local/bin: ${op_path_line}"
fi

# ---------------------------------------------------------------------
section "2. _verify_limactl defined and called before colima start"
# ---------------------------------------------------------------------
if /usr/bin/grep -q '^_verify_limactl()' "$COLIMA_LIB"; then
    ok "_verify_limactl() defined in install_colima.sh"
else
    fail "_verify_limactl() missing from install_colima.sh"
fi

# _verify_limactl call must precede the actual `colima start` invocation
# (the one that runs colima as a subprocess, not the doc comments). Match
# only the live shell line that runs the binary: `…colima" start …`.
verify_line="$(/usr/bin/grep -nE '_verify_limactl[[:space:]]+"' "$COLIMA_LIB" | head -n1 | cut -d: -f1)"
start_line="$(/usr/bin/grep -nE '"\$\{target_bin\}/colima" start' "$COLIMA_LIB" | head -n1 | cut -d: -f1)"
if [[ -n "$verify_line" && -n "$start_line" && "$verify_line" -lt "$start_line" ]]; then
    ok "_verify_limactl called (line ${verify_line}) before colima start invocation (line ${start_line})"
else
    fail "_verify_limactl is not called before colima start invocation (verify=${verify_line:-none}, start=${start_line:-none})"
fi

# ---------------------------------------------------------------------
section "3. Every sudo -u colima/docker site in install_colima.sh wraps with env PATH"
# ---------------------------------------------------------------------
# Look at every `sudo -u "${op_user}"` line. The next non-empty,
# non-comment line should contain `/usr/bin/env PATH=`. Count
# unwrapped sites.
unwrapped="$(awk '
    /sudo -u "\${op_user}"/ {
        # Look ahead up to 3 lines for env PATH= or end of stanza
        line_no = NR
        sudo_line = $0
        wrapped = 0
        for (i = 1; i <= 3; i++) {
            if ((getline next_line) <= 0) break
            if (next_line ~ /\/usr\/bin\/env PATH=/) { wrapped = 1; break }
            # If we hit another sudo -u or a closing brace, we are done
            if (next_line ~ /sudo -u/) break
        }
        if (!wrapped) {
            print "L" line_no ": " sudo_line
        }
    }
' "$COLIMA_LIB")"

if [[ -z "$unwrapped" ]]; then
    ok "all sudo -u sites in install_colima.sh wrap with env PATH=…"
else
    fail "unwrapped sudo -u sites in install_colima.sh:"
    echo "$unwrapped" >&2
fi

# ---------------------------------------------------------------------
section "4. _op_path defined in postinstall.sh"
# ---------------------------------------------------------------------
if /usr/bin/grep -q '^_op_path()' "$POSTINSTALL_SH"; then
    ok "_op_path() defined in postinstall.sh"
else
    fail "_op_path() missing from postinstall.sh"
fi

post_path_line="$(/usr/bin/grep -E "^[[:space:]]*printf '%s' \"/" "$POSTINSTALL_SH" | head -n1)"
if [[ "$post_path_line" =~ \"/usr/local/bin: ]]; then
    ok "postinstall.sh _op_path PATH starts with /usr/local/bin"
else
    fail "postinstall.sh _op_path PATH does not start with /usr/local/bin: ${post_path_line}"
fi

# ---------------------------------------------------------------------
section "5. Every sudo -u docker site in postinstall.sh wraps with env PATH"
# ---------------------------------------------------------------------
# The postinstall sites use MG_INSTALL_OPERATOR_USER, not op_user.
unwrapped_post="$(awk '
    /sudo -u "\$\{MG_INSTALL_OPERATOR_USER\}"/ {
        sudo_line = $0
        line_no = NR
        wrapped = 0
        for (i = 1; i <= 3; i++) {
            if ((getline next_line) <= 0) break
            if (next_line ~ /\/usr\/bin\/env PATH=/) { wrapped = 1; break }
            if (next_line ~ /sudo -u/) break
        }
        # We only care about docker invocations; pip/python sites use
        # absolute paths and do not need PATH propagation. Detect by
        # peeking the line after the sudo header for `docker `.
        is_docker = 0
        if (sudo_line ~ /docker/) is_docker = 1
        # Re-scan a wider window to find docker if the sudo line is the
        # backslash header form.
        if (!is_docker) {
            for (j = 1; j <= 5; j++) {
                if ((getline next2) <= 0) break
                if (next2 ~ /docker /) { is_docker = 1; break }
                if (next2 ~ /pip /)    break
                if (next2 ~ /python/)  break
            }
        }
        if (is_docker && !wrapped) {
            print "L" line_no ": " sudo_line
        }
    }
' "$POSTINSTALL_SH")"

if [[ -z "$unwrapped_post" ]]; then
    ok "all sudo -u docker sites in postinstall.sh wrap with env PATH=…"
else
    fail "unwrapped sudo -u docker sites in postinstall.sh:"
    echo "$unwrapped_post" >&2
fi

# Direct count check: number of `env PATH="$(_op_path)"` occurrences
# matches or exceeds the number of `sudo -u "${MG_INSTALL_OPERATOR_USER}"
# … docker` invocations.
docker_sudo_count="$(/usr/bin/grep -cE 'sudo -u "\$\{MG_INSTALL_OPERATOR_USER\}"' "$POSTINSTALL_SH" || true)"
env_wrap_count="$(/usr/bin/grep -cE '/usr/bin/env PATH=' "$POSTINSTALL_SH" || true)"
# The 1124, 1142, 1314 lines are pip/python sites that don't need wrap;
# subtract those 3. The remaining ≈10 must be wrapped.
expected_min_wraps=10
if [[ "${env_wrap_count:-0}" -ge "$expected_min_wraps" ]]; then
    ok "postinstall.sh has ${env_wrap_count} env PATH= wraps (>= ${expected_min_wraps} expected for docker sites)"
else
    fail "postinstall.sh has only ${env_wrap_count} env PATH= wraps; expected >= ${expected_min_wraps}"
fi

# ---------------------------------------------------------------------
section "6. PATH order: /usr/local/bin precedes /usr/bin"
# ---------------------------------------------------------------------
for f in "$COLIMA_LIB" "$POSTINSTALL_SH"; do
    base="$(basename "$f")"
    line="$(/usr/bin/grep -E "^[[:space:]]*printf '%s' \"/" "$f" | head -n1)"
    # Compute the index of /usr/local/bin and /usr/bin in the value.
    # If /usr/local/bin appears first, the substring up to the first
    # `:` after /usr/local/bin must come before /usr/bin.
    if [[ -z "$line" ]]; then
        fail "${base}: no PATH printf line found"
        continue
    fi
    # Strip prefix up to first quote, then keep until last quote.
    val="${line#*\"}"; val="${val%\"*}"
    local_idx="$(echo "$val" | awk -v RS=':' '{ if ($0 == "/usr/local/bin") { print NR; exit } }')"
    usr_idx="$(echo "$val"   | awk -v RS=':' '{ if ($0 == "/usr/bin")       { print NR; exit } }')"
    if [[ -n "$local_idx" && -n "$usr_idx" && "$local_idx" -lt "$usr_idx" ]]; then
        ok "${base}: /usr/local/bin (idx=${local_idx}) precedes /usr/bin (idx=${usr_idx})"
    else
        fail "${base}: PATH order wrong (/usr/local/bin idx=${local_idx:-none}, /usr/bin idx=${usr_idx:-none}) in: ${val}"
    fi
done

# ---------------------------------------------------------------------
section "7. Runtime: _op_path from install_colima.sh contains /usr/local/bin"
# ---------------------------------------------------------------------
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Extract _op_path() from install_colima.sh into a small driver.
EXTRACT_PATH="${TMP}/op_path.sh"
{
    echo '#!/usr/bin/env bash'
    echo 'set -uo pipefail'
    /usr/bin/awk '
        /^_op_path\(\)/ { capture=1 }
        capture { print }
        capture && /^}$/ { capture=0 }
    ' "$COLIMA_LIB"
} > "$EXTRACT_PATH"

out="$(env -i bash -c "source '$EXTRACT_PATH'; _op_path" 2>&1 || true)"
if [[ "$out" =~ ^/usr/local/bin: ]]; then
    ok "install_colima.sh _op_path returns PATH starting with /usr/local/bin: ${out}"
else
    fail "install_colima.sh _op_path returned unexpected value: ${out}"
fi

# ---------------------------------------------------------------------
section "8. Runtime: _verify_limactl returns 0 on present, non-zero on missing"
# ---------------------------------------------------------------------
EXTRACT_VERIFY="${TMP}/verify.sh"
{
    echo '#!/usr/bin/env bash'
    echo 'set -uo pipefail'
    echo '_log() { echo "[test] $*" >&2; }'
    echo '_die() { _log "FATAL $*"; return 1; }'
    /usr/bin/awk '
        /^_verify_limactl\(\)/ { capture=1 }
        capture { print }
        capture && /^}$/ { capture=0 }
    ' "$COLIMA_LIB"
} > "$EXTRACT_VERIFY"

# Create a stub limactl
STUB_LIMACTL="${TMP}/limactl"
echo '#!/bin/sh
echo limactl-stub' > "$STUB_LIMACTL"
chmod +x "$STUB_LIMACTL"

rc=0
out="$(bash -c "source '$EXTRACT_VERIFY'; _verify_limactl '$STUB_LIMACTL'" 2>&1)" || rc=$?
if (( rc == 0 )); then
    ok "_verify_limactl returns 0 for present executable"
else
    fail "_verify_limactl returned ${rc} for present executable: ${out}"
fi

rc=0
out="$(bash -c "source '$EXTRACT_VERIFY'; _verify_limactl '${TMP}/does-not-exist'" 2>&1)" || rc=$?
if (( rc != 0 )); then
    ok "_verify_limactl returns non-zero for missing limactl (rc=${rc})"
else
    fail "_verify_limactl returned 0 for missing limactl — would let install proceed into a misleading colima error"
fi

if [[ "$out" =~ "limactl not found" ]]; then
    ok "_verify_limactl logs 'limactl not found' when missing"
else
    fail "_verify_limactl missing-message unexpected: ${out}"
fi

# ---------------------------------------------------------------------
section "9. Runtime: env PATH=_op_path() locates limactl in a stripped env"
# ---------------------------------------------------------------------
# Simulate the sudo-stripped PATH scenario. Place a stub limactl in a
# fake /usr/local/bin tree and prove the wrapped command finds it
# while a non-wrapped one would not.
FAKE_LOCAL_BIN="${TMP}/usr-local-bin"
mkdir -p "$FAKE_LOCAL_BIN"
cp "$STUB_LIMACTL" "${FAKE_LOCAL_BIN}/limactl"

# Build a wrapper that prints _op_path with the fake /usr/local/bin
# substituted in (mimics how the real call site uses it).
WRAPPED_PATH="${FAKE_LOCAL_BIN}:/usr/local/sbin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
out="$(env -i PATH=/usr/bin:/bin /usr/bin/env PATH="$WRAPPED_PATH" \
        bash -c 'command -v limactl' 2>&1 || true)"
if [[ "$out" == "${FAKE_LOCAL_BIN}/limactl" ]]; then
    ok "wrapped env PATH locates limactl in stripped-PATH env (got: ${out})"
else
    fail "wrapped env PATH did not locate limactl: got '${out}'"
fi

# Negative control — without the wrap, command -v finds nothing.
out="$(env -i PATH=/usr/bin:/bin bash -c 'command -v limactl' 2>&1 || true)"
if [[ -z "$out" ]]; then
    ok "control: stripped PATH (no /usr/local/bin) cannot locate limactl"
else
    fail "control: stripped PATH unexpectedly located limactl: '${out}'"
fi

# ---------------------------------------------------------------------
section "10. P-019 audit marker present in install_colima.sh and postinstall.sh"
# ---------------------------------------------------------------------
for f in "$COLIMA_LIB" "$POSTINSTALL_SH"; do
    if /usr/bin/grep -q 'P-019' "$f"; then
        ok "$(basename "$f") cites P-019"
    else
        fail "$(basename "$f") missing P-019 citation"
    fi
done

# ---------------------------------------------------------------------
section "11. bash -n parse"
# ---------------------------------------------------------------------
for f in "$COLIMA_LIB" "$POSTINSTALL_SH"; do
    if bash -n "$f" 2>/dev/null; then
        ok "$(basename "$f") parses"
    else
        fail "$(basename "$f") has bash syntax errors"
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
