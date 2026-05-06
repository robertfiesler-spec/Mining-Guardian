#!/usr/bin/env bash
# =============================================================================
# Tests for installer/macos-pkg/scripts/preinstall.sh gate_free_disk
# =============================================================================
# Regression tests for the v1.0.3 install-day false negative where `df -k /`
# reported ~19 GB free on the sealed APFS system volume and tripped the
# 20 GB disk-space gate even though the Mac mini had ~167 GB free in Finder.
#
# These tests source preinstall.sh and exercise gate_free_disk in isolation
# against stubbed `df` and `diskutil` binaries. No root, no real disk, no
# network — they run in any sandbox.
#
# Run with:
#   bash installer/macos-pkg/scripts/tests/test_preinstall_disk_gate.sh
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREINSTALL="$(cd "${SCRIPT_DIR}/.." && pwd)/preinstall.sh"

if [[ ! -r "$PREINSTALL" ]]; then
    echo "FATAL: cannot read $PREINSTALL" >&2
    exit 2
fi

PASS=0
FAIL=0

# Each test runs in its own subshell so `set -e`, exported vars, and stub
# directories never leak between tests.
run_test() {
    local name="$1"
    local fn="$2"
    if ( "$fn" ); then
        echo "  PASS: $name"
        PASS=$((PASS+1))
    else
        echo "  FAIL: $name"
        FAIL=$((FAIL+1))
    fi
}

# Build a temporary "bin" dir holding a fake `df` and `diskutil` whose
# output is controlled by environment variables. Sets MG_DF_BIN /
# MG_DISKUTIL_BIN to point at the fakes, and points MG_INSTALL_LOG at a
# disposable tempfile so log() doesn't try to write to /var/log.
_make_stub_env() {
    local stub_dir
    stub_dir="$(mktemp -d 2>/dev/null || mktemp -d -t mg_preinstall_test)"

    cat > "${stub_dir}/df" <<'EOF'
#!/bin/bash
# Fake df. Reads STUB_DF_HEADER and STUB_DF_<sanitized-path> envs and prints
# the matching row. Sanitization mirrors the test helper below.
set -u
path=""
# Skip flags ("-k", "--", etc.) and capture the last positional arg.
for arg in "$@"; do
    case "$arg" in
        -*) ;;
        *)  path="$arg" ;;
    esac
done
key="STUB_DF_$(printf '%s' "$path" | tr -c 'A-Za-z0-9' '_')"
row="${!key:-}"
echo "${STUB_DF_HEADER:-Filesystem 1024-blocks Used Available Capacity iused ifree %iused Mounted on}"
if [[ -n "$row" ]]; then
    echo "$row"
fi
EOF
    chmod +x "${stub_dir}/df"

    cat > "${stub_dir}/diskutil" <<'EOF'
#!/bin/bash
# Fake diskutil. Reads STUB_DISKUTIL_<sanitized-path> for the bytes value
# to embed in a "Container Free Space:" line. If the var is empty we print
# nothing matching, simulating a non-APFS path or a missing diskutil binary.
set -u
[[ "${1:-}" == "info" ]] || { echo "fake diskutil: only 'info' supported" >&2; exit 64; }
shift
# Skip "--"
[[ "${1:-}" == "--" ]] && shift
path="${1:-}"
key="STUB_DISKUTIL_$(printf '%s' "$path" | tr -c 'A-Za-z0-9' '_')"
bytes="${!key:-}"
if [[ -n "$bytes" ]]; then
    # Format must match what real diskutil emits — value between parens
    # in bytes is what _diskutil_container_free_gb parses.
    printf '   Container Free Space:      999.9 GB (%s Bytes)\n' "$bytes"
fi
EOF
    chmod +x "${stub_dir}/diskutil"

    export MG_DF_BIN="${stub_dir}/df"
    export MG_DISKUTIL_BIN="${stub_dir}/diskutil"
    export MG_INSTALL_LOG
    MG_INSTALL_LOG="${stub_dir}/preinstall.log"
    : > "$MG_INSTALL_LOG"

    echo "$stub_dir"
}

# Helper to set stub df row for a path. Mirrors the sanitization in the
# fake df above so the env var name matches.
_stub_df_row() {
    local path="$1" row="$2"
    local key="STUB_DF_$(printf '%s' "$path" | tr -c 'A-Za-z0-9' '_')"
    export "${key}=${row}"
}

# Helper to set stub diskutil container free bytes for a path.
_stub_diskutil_bytes() {
    local path="$1" bytes="$2"
    local key="STUB_DISKUTIL_$(printf '%s' "$path" | tr -c 'A-Za-z0-9' '_')"
    export "${key}=${bytes}"
}

# A row for `df -k <path>` with the given KB available. Filesystem name +
# other columns are filler that gate_free_disk does not parse.
_df_row_kb() {
    local kb="$1"
    printf '/dev/disk0s2  500000000  100000000  %s  20%%  100  100  50%%  /\n' "$kb"
}

# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------

# T1 — The v1.0.3 install-day regression. Sealed system volume on `/` reports
# ~19 GB free, but the writable install target has ~167 GB free.
# Pre-fix behavior: gate_free_disk fails 14. Post-fix: gate passes.
test_v1_0_3_regression_passes() {
    _make_stub_env >/dev/null
    # / shows the misleading 19 GB (~ 19 * 1024 * 1024 KB)
    _stub_df_row "/" "$(_df_row_kb 19922944)"
    # /Library/Application Support shows the truth via df fallback (~167 GB)
    _stub_df_row "/Library/Application Support" "$(_df_row_kb 175112192)"
    _stub_df_row "/System/Volumes/Data" "$(_df_row_kb 175112192)"
    # Authoritative APFS container free for the writable target.
    _stub_diskutil_bytes "/Library/Application Support" "$(( 167 * 1073741824 ))"

    # shellcheck disable=SC1090
    source "$PREINSTALL"
    gate_free_disk
}

# T2 — Same disk but APFS container reports ~10 GB free. Gate must fail
# regardless of what `df /` reports, because the writable target is the
# authoritative source.
test_low_apfs_container_free_fails() {
    _make_stub_env >/dev/null
    # `df /` lies in the OTHER direction here (claims plenty of room)
    _stub_df_row "/" "$(_df_row_kb $(( 200 * 1024 * 1024 )))"
    _stub_df_row "/Library/Application Support" "$(_df_row_kb $(( 10 * 1024 * 1024 )))"
    _stub_df_row "/System/Volumes/Data" "$(_df_row_kb $(( 10 * 1024 * 1024 )))"
    _stub_diskutil_bytes "/Library/Application Support" "$(( 10 * 1073741824 ))"

    # gate_free_disk calls `fail` which calls `exit 14`. Run it in a nested
    # subshell so we capture the exit code without aborting the test fn.
    local rc=0
    (
        # shellcheck disable=SC1090
        source "$PREINSTALL"
        gate_free_disk
    ) 2>/dev/null
    rc=$?
    [[ "$rc" -eq 14 ]] || return 1
    grep -q 'FATAL (14)' "$MG_INSTALL_LOG"
}

# T3 — diskutil unavailable (e.g., piped through a non-APFS path or the
# binary is missing). gate_free_disk falls back to `df -k <target>` and
# must NOT touch `df /`.
test_diskutil_unavailable_falls_back_to_df_target() {
    _make_stub_env >/dev/null
    _stub_df_row "/" "$(_df_row_kb $(( 5 * 1024 * 1024 )))"   # would fail if used
    _stub_df_row "/Library/Application Support" "$(_df_row_kb $(( 100 * 1024 * 1024 )))"
    _stub_df_row "/System/Volumes/Data" "$(_df_row_kb $(( 100 * 1024 * 1024 )))"
    # Intentionally NO _stub_diskutil_bytes call — fake diskutil emits no
    # "Container Free Space:" line, so _diskutil_container_free_gb returns "".

    # shellcheck disable=SC1090
    source "$PREINSTALL"
    gate_free_disk
}

# T4 — Defense in depth: the gate must NOT use `df /` even when it would
# pass. We confirm by setting `df /` to plenty AND making both APFS and
# `df <target>` fail to report — only /System/Volumes/Data has data.
# gate_free_disk should still succeed via the data-volume fallback.
test_data_volume_last_ditch_fallback() {
    _make_stub_env >/dev/null
    _stub_df_row "/" "$(_df_row_kb $(( 500 * 1024 * 1024 )))"   # ignored
    # Note: NOT setting /Library/Application Support. Fake df returns header
    # only, so _df_avail_gb echoes "".
    _stub_df_row "/System/Volumes/Data" "$(_df_row_kb $(( 80 * 1024 * 1024 )))"

    # shellcheck disable=SC1090
    source "$PREINSTALL"
    gate_free_disk
}

# T5 — All probes fail to read. gate must fail 14 with the diagnostic
# message naming the install target, NOT "/".
test_all_probes_fail() {
    _make_stub_env >/dev/null
    # No _stub_df_row, no _stub_diskutil_bytes for any path. Fake df returns
    # header only for every call.

    local rc=0
    (
        # shellcheck disable=SC1090
        source "$PREINSTALL"
        gate_free_disk
    ) 2>/dev/null
    rc=$?
    [[ "$rc" -eq 14 ]] || return 1
    grep -q 'FATAL (14)' "$MG_INSTALL_LOG" \
        && grep -q "could not read free disk for install target" "$MG_INSTALL_LOG"
}

# T6 — diagnostic log shape. gate_free_disk must log BOTH the misleading
# `df /` reading and the authoritative install-target reading on every run
# so future regressions are immediately obvious from the install log.
test_logs_both_root_and_target() {
    _make_stub_env >/dev/null
    _stub_df_row "/" "$(_df_row_kb $(( 19 * 1024 * 1024 )))"
    _stub_df_row "/Library/Application Support" "$(_df_row_kb $(( 167 * 1024 * 1024 )))"
    _stub_df_row "/System/Volumes/Data" "$(_df_row_kb $(( 167 * 1024 * 1024 )))"
    _stub_diskutil_bytes "/Library/Application Support" "$(( 167 * 1073741824 ))"

    # shellcheck disable=SC1090
    source "$PREINSTALL"
    gate_free_disk

    grep -q "df / = 19 GB" "$MG_INSTALL_LOG" \
        && grep -q "df /Library/Application Support = 167 GB" "$MG_INSTALL_LOG" \
        && grep -q "diskutil container free for /Library/Application Support = 167 GB" "$MG_INSTALL_LOG" \
        && grep -q "OK gate_free_disk: 167 GB free" "$MG_INSTALL_LOG"
}

# T7 — Regression guard: the source of truth must NEVER read `df -k /`
# alone for the gate decision. We grep the script itself to make sure no
# one reintroduces `df -k /` as a single-source-of-truth path inside
# gate_free_disk. Helpers may still call `_df_avail_gb /` for the
# diagnostic line, but the gate must never branch on `df /` value alone.
test_script_does_not_gate_on_df_root_alone() {
    # Extract just the gate_free_disk function body. The function ends at
    # the next top-level `}` after the opening `gate_free_disk()` line.
    awk '/^gate_free_disk\(\)/{flag=1} flag{print} /^\}/{if(flag){flag=0; exit}}' \
        "$PREINSTALL" > /tmp/_mg_gate_body.$$
    # The body must reference the writable target by name AND must not
    # branch on `_df_avail_gb /` as the gate value.
    grep -q "DISK_TARGET" /tmp/_mg_gate_body.$$ || {
        rm -f /tmp/_mg_gate_body.$$; return 1
    }
    # Allow `_df_avail_gb /` for diagnostics, but ensure we never assign it
    # to the variable that drives the comparison. Fail if we see
    # `avail_gb=$(_df_avail_gb /)` or similar anywhere in the function.
    if grep -E "avail_gb=.*_df_avail_gb[[:space:]]+/[^A-Za-z0-9]" /tmp/_mg_gate_body.$$; then
        rm -f /tmp/_mg_gate_body.$$; return 1
    fi
    rm -f /tmp/_mg_gate_body.$$
}

# -----------------------------------------------------------------------------
# Driver
# -----------------------------------------------------------------------------

echo "Running gate_free_disk tests against ${PREINSTALL}"
run_test "v1.0.3 regression: 19 GB on / + 167 GB on writable target → pass" test_v1_0_3_regression_passes
run_test "low APFS container free space → fail with FATAL (14)"             test_low_apfs_container_free_fails
run_test "diskutil unavailable → df fallback on writable target"            test_diskutil_unavailable_falls_back_to_df_target
run_test "/System/Volumes/Data last-ditch fallback when target df is empty" test_data_volume_last_ditch_fallback
run_test "all probes fail → FATAL (14) names the install target"            test_all_probes_fail
run_test "log captures df /, df target, diskutil container free, OK line"   test_logs_both_root_and_target
run_test "script does not gate on \`df /\` alone"                            test_script_does_not_gate_on_df_root_alone

echo
echo "Total: passed=${PASS} failed=${FAIL}"
[[ "$FAIL" -eq 0 ]]
