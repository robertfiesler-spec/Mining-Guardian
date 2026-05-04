#!/usr/bin/env bash
# tests/installer/test_preinstall_arch_gate.sh
#
# P-015 (2026-05-04) — Apple Silicon arch-gate Rosetta-safe regression guard.
#
# Background:
#   On 2026-05-04 Rob installed signed/notarized v1.0.3 build 2b48f98 on
#   the customer Mac mini (a documented M-series machine). The corrected
#   .pkg now stages preinstall/postinstall under the extensionless names
#   PackageKit honors (P-013/P-014), so the preinstall script DID fire for
#   the first time. /var/log/mining-guardian/install-preinstall.log
#   showed:
#     OK gate_root: running as root
#     OK gate_macos_version: 26.4.1 >= 13.0
#     FATAL (12) this build supports Apple Silicon (arm64) only;
#         detected 'x86_64'
#
#   Root cause: gate_apple_silicon called `/usr/bin/uname -m` and
#   compared the result to "arm64". `uname -m` reports the architecture
#   of the CURRENT PROCESS, not the hardware. On Apple Silicon, if
#   Installer.app spawns the preinstall under a Rosetta-translated
#   /bin/bash (Terminal.app set to "Open using Rosetta", or the operator
#   invoked `arch -x86_64 sudo installer ...`), `uname -m` returns
#   `x86_64` even though the Mac is M-series. The gate hard-failed on a
#   perfectly valid host.
#
#   The fix in installer/macos-pkg/scripts/preinstall.sh::gate_apple_silicon
#   reads `sysctl -n hw.optional.arm64`, which is set by the kernel based
#   on the SoC and does NOT change under Rosetta translation:
#     hw.optional.arm64 == 1   → Apple Silicon hardware → pass
#     hw.optional.arm64 == 0   → Intel hardware → fail (12)
#     sysctl missing/unreadable → fall back to uname -m, accepting only
#                                if uname agrees with arm64
#   `sysctl.proc_translated` is logged for diagnostics but does NOT gate.
#
#   Intel-only support remains explicitly out of scope (CLAUDE.md / D-18 /
#   Vision Anchor 2). This test guards both directions: false-negative
#   (Apple Silicon under Rosetta) MUST pass; Intel hardware MUST still
#   fail.
#
# This test asserts:
#   STATIC (source-tree drift guards):
#     1. preinstall.sh parses (bash -n).
#     2. gate_apple_silicon reads `sysctl -n hw.optional.arm64`.
#     3. gate_apple_silicon reads `sysctl -n sysctl.proc_translated`
#        (used for diagnostic logging only).
#     4. gate_apple_silicon does NOT use the original
#        `/usr/bin/uname -m` == arm64 short-circuit as the sole
#        decision (live body must reference hw.optional.arm64).
#     5. The function still exits with code 12 on the rejection path
#        (Intel hardware).
#     6. The P-015 audit marker is present in a comment so future
#        sessions can grep for it.
#
#   FUNCTIONAL (extracted-function harness, mocked sysctl/uname):
#     7. Native Apple Silicon (sysctl arm64=1, proc_translated=0,
#        uname=arm64) → exit 0.
#     8. Apple Silicon under Rosetta (sysctl arm64=1, proc_translated=1,
#        uname=x86_64) → exit 0 (the bug we're fixing).
#     9. Intel hardware (sysctl arm64=0, proc_translated missing,
#        uname=x86_64) → exit 12.
#    10. Hardware indeterminate + uname says x86_64 (sysctl missing
#        entirely, uname=x86_64) → exit 12 (defensive fallback).
#    11. Hardware indeterminate + uname says arm64 (sysctl missing
#        entirely, uname=arm64) → exit 0 (defensive fallback accepts
#        only when uname agrees).
#
# Static checks have no Mac/installer dependency. Functional checks run
# the actual gate function with `sysctl` + `uname` shadowed on PATH so
# behavior is verified end-to-end without a real macOS host.
#
# Run from repo root:
#     bash tests/installer/test_preinstall_arch_gate.sh
#
# Exits 0 on success, non-zero on first failed assertion.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PRE_SRC="installer/macos-pkg/scripts/preinstall.sh"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }

section() { echo; echo "## $*"; }

# ---------------------------------------------------------------------
section "1. preinstall.sh parses (bash -n)"
# ---------------------------------------------------------------------
if bash -n "$PRE_SRC" 2>/dev/null; then
    ok "preinstall.sh parses"
else
    fail "preinstall.sh has bash syntax errors"
fi

# Live (non-comment) body of gate_apple_silicon for substring checks.
gate_body="$(/usr/bin/awk '/^gate_apple_silicon\(\)/,/^}$/' "$PRE_SRC")"
gate_live="$(echo "$gate_body" | /usr/bin/grep -vE '^[[:space:]]*#')"

# ---------------------------------------------------------------------
section "2. gate reads hw.optional.arm64 (kernel-authoritative)"
# ---------------------------------------------------------------------
if echo "$gate_live" | /usr/bin/grep -qE 'sysctl[[:space:]]+-n[[:space:]]+hw\.optional\.arm64'; then
    ok "gate_apple_silicon calls sysctl -n hw.optional.arm64"
else
    fail "gate_apple_silicon must read sysctl -n hw.optional.arm64 (P-015)"
fi

# ---------------------------------------------------------------------
section "3. gate reads sysctl.proc_translated for diagnostics"
# ---------------------------------------------------------------------
if echo "$gate_live" | /usr/bin/grep -qE 'sysctl[[:space:]]+-n[[:space:]]+sysctl\.proc_translated'; then
    ok "gate_apple_silicon calls sysctl -n sysctl.proc_translated"
else
    fail "gate_apple_silicon should read sysctl.proc_translated for Rosetta diagnostics (P-015)"
fi

# ---------------------------------------------------------------------
section "4. gate is not a uname-only short-circuit"
# ---------------------------------------------------------------------
# The pre-P-015 implementation was a single `[[ "$arch" != "$EXPECTED_ARCH" ]] && fail 12`.
# Guard against a future rewrite that drops the sysctl path.
if echo "$gate_live" | /usr/bin/grep -qE 'hw_arm64'; then
    ok "gate_apple_silicon retains the hw_arm64 decision branch"
else
    fail "gate_apple_silicon dropped the hw.optional.arm64 branch — re-introduces the Rosetta false-negative"
fi

# ---------------------------------------------------------------------
section "5. gate still rejects with exit code 12"
# ---------------------------------------------------------------------
if echo "$gate_live" | /usr/bin/grep -qE 'fail[[:space:]]+12'; then
    ok "gate_apple_silicon still calls fail 12 on the rejection path"
else
    fail "gate_apple_silicon must keep fail 12 for Intel rejection (CLAUDE.md / Vision Anchor 2)"
fi

# ---------------------------------------------------------------------
section "6. P-015 audit marker present"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE 'P-015' "$PRE_SRC"; then
    ok "preinstall.sh contains a P-015 audit marker"
else
    fail "preinstall.sh missing P-015 audit marker (drift guard)"
fi

# ---------------------------------------------------------------------
section "7..11. Functional: extracted-function harness"
# ---------------------------------------------------------------------
# We can't simply `source preinstall.sh` because it ends with `main "$@"`.
# Build a sourceable harness on the fly:
#   - extract gate_apple_silicon and the constants it needs
#   - replace absolute paths /usr/sbin/sysctl + /usr/bin/uname with the
#     unqualified names so a PATH-shadowed mock takes effect
#   - inject minimal log()/fail() shims that capture exit code

HARNESS_DIR="$(mktemp -d)"
trap 'rm -rf "$HARNESS_DIR"' EXIT

HARNESS="${HARNESS_DIR}/harness.sh"

cat > "$HARNESS" <<'HARNESS_HEAD'
#!/usr/bin/env bash
set -uo pipefail

readonly EXPECTED_ARCH="arm64"

log() { echo "[log] $*" >&2; }
fail() {
    local code="$1"; shift
    echo "[fail $code] $*" >&2
    exit "$code"
}
HARNESS_HEAD

# Extract the function definition body and rewrite absolute tool paths so
# PATH-shadowed mocks take effect.
/usr/bin/awk '/^gate_apple_silicon\(\)/,/^}$/' "$PRE_SRC" \
    | /usr/bin/sed -e 's#/usr/sbin/sysctl#sysctl#g' \
                   -e 's#/usr/bin/uname#uname#g' \
    >> "$HARNESS"

cat >> "$HARNESS" <<'HARNESS_TAIL'

gate_apple_silicon
HARNESS_TAIL

# Build mock sysctl + uname binaries that read scenario from env vars.
MOCKS_DIR="${HARNESS_DIR}/mocks"
mkdir -p "$MOCKS_DIR"

cat > "${MOCKS_DIR}/sysctl" <<'MOCK_SYSCTL'
#!/usr/bin/env bash
# Mock sysctl. Honors:
#   sysctl -n hw.optional.arm64
#   sysctl -n sysctl.proc_translated
# Driven by env:
#   MOCK_HW_ARM64        — value to print, or "MISSING" to exit 1
#   MOCK_PROC_TRANSLATED — value to print, or "MISSING" to exit 1
key="$2"
case "$key" in
    hw.optional.arm64)
        if [[ "${MOCK_HW_ARM64:-MISSING}" == "MISSING" ]]; then
            echo "sysctl: unknown oid 'hw.optional.arm64'" >&2
            exit 1
        fi
        printf '%s\n' "$MOCK_HW_ARM64"
        ;;
    sysctl.proc_translated)
        if [[ "${MOCK_PROC_TRANSLATED:-MISSING}" == "MISSING" ]]; then
            echo "sysctl: unknown oid 'sysctl.proc_translated'" >&2
            exit 1
        fi
        printf '%s\n' "$MOCK_PROC_TRANSLATED"
        ;;
    *)
        echo "mock sysctl: unhandled key '$key'" >&2
        exit 1
        ;;
esac
MOCK_SYSCTL
chmod +x "${MOCKS_DIR}/sysctl"

cat > "${MOCKS_DIR}/uname" <<'MOCK_UNAME'
#!/usr/bin/env bash
# Mock uname. Only -m is exercised by gate_apple_silicon.
# Driven by env:
#   MOCK_UNAME_M — value to print for `uname -m`
if [[ "${1:-}" == "-m" ]]; then
    printf '%s\n' "${MOCK_UNAME_M:-arm64}"
    exit 0
fi
echo "mock uname: unhandled flags: $*" >&2
exit 1
MOCK_UNAME
chmod +x "${MOCKS_DIR}/uname"

run_scenario() {
    local label="$1"; shift
    local expected_rc="$1"; shift
    # Remaining args are KEY=VALUE env overrides.
    local rc
    (
        export PATH="${MOCKS_DIR}:${PATH}"
        for kv in "$@"; do
            export "${kv?}"
        done
        bash "$HARNESS" >/dev/null 2>&1
    )
    rc=$?
    if [[ "$rc" -eq "$expected_rc" ]]; then
        ok "scenario '${label}' → rc=${rc} (expected ${expected_rc})"
    else
        fail "scenario '${label}' → rc=${rc} (expected ${expected_rc})"
    fi
}

# 7. Native Apple Silicon
run_scenario "native Apple Silicon" 0 \
    MOCK_HW_ARM64=1 MOCK_PROC_TRANSLATED=0 MOCK_UNAME_M=arm64

# 8. Apple Silicon under Rosetta — the bug being fixed
run_scenario "Apple Silicon under Rosetta (uname lies)" 0 \
    MOCK_HW_ARM64=1 MOCK_PROC_TRANSLATED=1 MOCK_UNAME_M=x86_64

# 9. Intel hardware — must still reject
run_scenario "Intel hardware (hw.optional.arm64=0)" 12 \
    MOCK_HW_ARM64=0 MOCK_PROC_TRANSLATED=MISSING MOCK_UNAME_M=x86_64

# 10. sysctl indeterminate + uname=x86_64 — defensive reject
run_scenario "sysctl missing + uname x86_64 (defensive reject)" 12 \
    MOCK_HW_ARM64=MISSING MOCK_PROC_TRANSLATED=MISSING MOCK_UNAME_M=x86_64

# 11. sysctl indeterminate + uname=arm64 — defensive accept
run_scenario "sysctl missing + uname arm64 (defensive accept)" 0 \
    MOCK_HW_ARM64=MISSING MOCK_PROC_TRANSLATED=MISSING MOCK_UNAME_M=arm64

# ---------------------------------------------------------------------
echo
echo "==============================================="
echo "Results: ${pass_count} passed, ${fail_count} failed"
echo "==============================================="

if [[ "$fail_count" -gt 0 ]]; then
    exit 1
fi
exit 0
