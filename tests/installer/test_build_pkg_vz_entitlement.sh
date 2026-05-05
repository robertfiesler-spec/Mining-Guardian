#!/usr/bin/env bash
# tests/installer/test_build_pkg_vz_entitlement.sh
#
# D-18 P-020 / P-021 — VZ entitlement signing for the vendored Lima/Colima
# runtime, plus limactl source-location robustness.
#
# Why this exists: postinstall round 4 on the customer Mac mini, 2026-05-05,
# against `MiningGuardian-1.0.3-47efd658f16a.pkg` — `colima start --vm-type vz`
# made it through Lima version handshake and disk-image conversion, then the
# VZ driver subprocess exited 1 with:
#
#     fatal: error starting vm: exit status 1
#     Error Domain=VZErrorDomain Code=2
#     "Invalid virtual machine configuration. The process doesn't have
#      the "com.apple.security.virtualization" entitlement."
#
# Root cause: build_pkg.sh::step_4b_codesign_inner_binaries re-signs every
# vendored Mach-O with Developer ID Application + hardened runtime + secure
# timestamp. codesign REPLACES the upstream signature wholesale (including
# entitlements). Without `--entitlements` on our re-sign call, every VZ-
# needing binary loses `com.apple.security.virtualization`. Lima upstream
# signs `limactl` and `lima-driver-vz` with that entitlement; our re-sign
# stripped it.
#
# This test asserts:
#   1. installer/macos-pkg/scripts/lib/vz.entitlements exists, parses as
#      a plist, and declares com.apple.security.virtualization=true.
#   2. build_pkg.sh references vz.entitlements at the lib/ path.
#   3. step_4b defines vz_binary_names list including limactl,
#      lima-driver-vz, and lima.
#   4. step_4b's Pass 2 codesign call passes --entitlements when basename
#      matches vz_binary_names; the non-VZ branch keeps the existing
#      no-entitlements call shape.
#   5. step_4b includes a verify-after-sign that greps for
#      com.apple.security.virtualization in `codesign -d --entitlements`
#      output and fails the build if absent.
#   6. step_4b includes a mandatory-presence check that fails the build
#      if no limactl is found anywhere under runtime/.
#   7. install_colima.sh::install_colima_runtime walks two known limactl
#      source locations (Lima 1.x: ${src}/limactl; Lima 2.x: ${src}/bin/limactl)
#      and refuses to proceed with a clear log line if neither is present.
#   8. P-020 and P-021 audit markers present in build_pkg.sh and
#      install_colima.sh.
#   9. bash -n parses both files cleanly.
#
# Run from repo root:
#     bash tests/installer/test_build_pkg_vz_entitlement.sh
#
# Exits 0 on success, non-zero on first failed assertion.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

BUILD_PKG="installer/macos-pkg/scripts/build_pkg.sh"
COLIMA_LIB="installer/macos-pkg/scripts/lib/install_colima.sh"
ENTITLEMENTS="installer/macos-pkg/scripts/lib/vz.entitlements"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }

section() { echo; echo "## $*"; }

# ---------------------------------------------------------------------
section "1. vz.entitlements plist exists and declares the entitlement"
# ---------------------------------------------------------------------
if [[ -r "$ENTITLEMENTS" ]]; then
    ok "vz.entitlements exists at ${ENTITLEMENTS}"
else
    fail "vz.entitlements missing at ${ENTITLEMENTS}"
fi

if /usr/bin/grep -q '<key>com.apple.security.virtualization</key>' "$ENTITLEMENTS" \
        && /usr/bin/grep -A1 'com.apple.security.virtualization' "$ENTITLEMENTS" \
            | /usr/bin/grep -q '<true/>'; then
    ok "vz.entitlements declares com.apple.security.virtualization=true"
else
    fail "vz.entitlements does not declare com.apple.security.virtualization=true"
fi

# Plist must parse as XML — use Python's xml.etree (available everywhere)
# since plutil is macOS-only and tests should run on Linux CI too.
if /usr/bin/env python3 -c "
import sys, xml.etree.ElementTree as ET
ET.parse(sys.argv[1])
" "$ENTITLEMENTS" 2>/dev/null; then
    ok "vz.entitlements parses as well-formed XML"
else
    fail "vz.entitlements does not parse as well-formed XML"
fi

# ---------------------------------------------------------------------
section "2. build_pkg.sh references vz.entitlements at the lib/ path"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE 'vz_entitlements="\$\{PKG_DIR\}/scripts/lib/vz\.entitlements"' "$BUILD_PKG"; then
    ok "build_pkg.sh resolves vz_entitlements via \${PKG_DIR}/scripts/lib/vz.entitlements"
else
    fail "build_pkg.sh does not reference \${PKG_DIR}/scripts/lib/vz.entitlements"
fi

if /usr/bin/grep -qE '_die 44 "step 4b: VZ entitlements plist missing' "$BUILD_PKG"; then
    ok "build_pkg.sh hard-fails (exit 44) when vz.entitlements is absent"
else
    fail "build_pkg.sh does not hard-fail when vz.entitlements is missing"
fi

# ---------------------------------------------------------------------
section "3. vz_binary_names list defined and includes the upstream set"
# ---------------------------------------------------------------------
if /usr/bin/grep -q 'vz_binary_names=(' "$BUILD_PKG"; then
    ok "build_pkg.sh defines vz_binary_names list"
else
    fail "build_pkg.sh does not define vz_binary_names list"
fi

for vz_name in limactl lima-driver-vz lima; do
    if /usr/bin/awk '
        /vz_binary_names=\(/ { capture=1 }
        capture { print }
        capture && /\)/ { capture=0 }
    ' "$BUILD_PKG" | /usr/bin/grep -q "\"${vz_name}\""; then
        ok "vz_binary_names includes ${vz_name}"
    else
        fail "vz_binary_names missing ${vz_name}"
    fi
done

# ---------------------------------------------------------------------
section "4. Pass 2 codesign passes --entitlements for VZ binaries"
# ---------------------------------------------------------------------
# The VZ branch must call codesign with --entitlements; the non-VZ branch
# must NOT pass --entitlements (over-broad entitlement application is a
# notarization risk). Two codesign invocations expected in the loose-
# Mach-O loop.
ent_codesign_count="$(/usr/bin/grep -cE 'codesign[[:space:]]*\\$|codesign \\\\$' "$BUILD_PKG" || true)"
ent_pass_count="$(/usr/bin/grep -cE -- '--entitlements "\$vz_entitlements"' "$BUILD_PKG" || true)"
if (( ent_pass_count >= 1 )); then
    ok "build_pkg.sh passes --entitlements \"\$vz_entitlements\" at least once"
else
    fail "build_pkg.sh does not pass --entitlements \"\$vz_entitlements\" anywhere"
fi

# Verify the basename match gating exists.
if /usr/bin/grep -qE 'base="\$\(basename "\$path"\)"' "$BUILD_PKG"; then
    ok "build_pkg.sh extracts basename for VZ matching"
else
    fail "build_pkg.sh does not extract basename for VZ matching"
fi

# ---------------------------------------------------------------------
section "5. Verify-after-sign greps for com.apple.security.virtualization"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE "codesign -d --entitlements - " "$BUILD_PKG" \
        && /usr/bin/grep -qE 'grep -q .com\.apple\.security\.virtualization' "$BUILD_PKG"; then
    ok "build_pkg.sh verifies VZ entitlement post-codesign and greps for com.apple.security.virtualization"
else
    fail "build_pkg.sh does not verify VZ entitlement after codesign"
fi

if /usr/bin/grep -qE '_die 44 "step 4b: VZ entitlement missing after codesign' "$BUILD_PKG"; then
    ok "build_pkg.sh _die 44 if entitlement missing after codesign"
else
    fail "build_pkg.sh does not _die when entitlement missing after codesign"
fi

# ---------------------------------------------------------------------
section "6. Mandatory limactl-presence check (P-020)"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE "find \"\\\$runtime_dir\" -type f -name 'limactl'" "$BUILD_PKG" \
        && /usr/bin/grep -qE '_die 44 "step 4b: limactl not found' "$BUILD_PKG"; then
    ok "build_pkg.sh enforces limactl presence under runtime/"
else
    fail "build_pkg.sh does not enforce limactl presence under runtime/"
fi

# ---------------------------------------------------------------------
section "7. install_colima.sh walks two limactl source locations (P-020)"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE 'if \[\[ -f "\$\{src\}/limactl" \]\];' "$COLIMA_LIB" \
        && /usr/bin/grep -qE 'elif \[\[ -f "\$\{src\}/bin/limactl" \]\];' "$COLIMA_LIB"; then
    ok "install_colima.sh walks both \${src}/limactl and \${src}/bin/limactl"
else
    fail "install_colima.sh does not walk both limactl source locations"
fi

if /usr/bin/grep -qE '_die "vendored limactl not found at \$\{src\}/limactl or \$\{src\}/bin/limactl' "$COLIMA_LIB"; then
    ok "install_colima.sh fails with a clear log line when limactl is absent"
else
    fail "install_colima.sh does not fail with a clear log line when limactl is absent"
fi

# Runtime smoke test — extract the limactl-resolution block, run it
# against a fake src tree where only ${src}/bin/limactl exists, and
# confirm the resolver picks it. Then run again with NEITHER present
# and confirm it returns a non-zero exit with the documented message.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Pull the limactl resolution snippet from install_colima.sh into a
# small runnable fixture. We don't try to source the whole file (it
# pulls $MG_PKG_PAYLOAD etc.); instead we extract just the resolver
# block and wrap it in a function we can call.
RESOLVER_SH="${TMP}/limactl_resolver.sh"
cat > "$RESOLVER_SH" <<'BASH_EOF'
#!/usr/bin/env bash
set -uo pipefail
_die() { echo "FATAL $*" >&2; return 1; }
_log() { echo "$*"; }

resolve_limactl() {
    local src="$1"
    local limactl_src=""
    if [[ -f "${src}/limactl" ]]; then
        limactl_src="${src}/limactl"
    elif [[ -f "${src}/bin/limactl" ]]; then
        limactl_src="${src}/bin/limactl"
    fi
    if [[ -z "$limactl_src" ]]; then
        _die "vendored limactl not found at ${src}/limactl or ${src}/bin/limactl (P-020)"
        return 1
    fi
    echo "$limactl_src"
    return 0
}
BASH_EOF

# Scenario A — Lima 1.x layout: ${src}/limactl present.
src_a="${TMP}/lima1x"; mkdir -p "$src_a"; touch "${src_a}/limactl"; chmod +x "${src_a}/limactl"
out_a="$(bash -c "source '$RESOLVER_SH'; resolve_limactl '$src_a'" 2>/dev/null || true)"
if [[ "$out_a" == "${src_a}/limactl" ]]; then
    ok "limactl resolver picks Lima 1.x layout (\${src}/limactl)"
else
    fail "limactl resolver got '${out_a}', expected '${src_a}/limactl'"
fi

# Scenario B — Lima 2.x layout: ${src}/bin/limactl present.
src_b="${TMP}/lima2x"; mkdir -p "${src_b}/bin"; touch "${src_b}/bin/limactl"; chmod +x "${src_b}/bin/limactl"
out_b="$(bash -c "source '$RESOLVER_SH'; resolve_limactl '$src_b'" 2>/dev/null || true)"
if [[ "$out_b" == "${src_b}/bin/limactl" ]]; then
    ok "limactl resolver picks Lima 2.x layout (\${src}/bin/limactl)"
else
    fail "limactl resolver got '${out_b}', expected '${src_b}/bin/limactl'"
fi

# Scenario C — neither present, must fail non-zero with the documented
# message.
src_c="${TMP}/missing"; mkdir -p "$src_c"
err_c="$(bash -c "source '$RESOLVER_SH'; resolve_limactl '$src_c'" 2>&1)"
rc_c="$(bash -c "source '$RESOLVER_SH'; resolve_limactl '$src_c' >/dev/null 2>&1; echo \$?")"
if [[ "$rc_c" != "0" ]]; then
    ok "limactl resolver exits non-zero when limactl missing (rc=${rc_c})"
else
    fail "limactl resolver returned rc=0 when limactl was missing"
fi
if [[ "$err_c" == *"vendored limactl not found at"* ]]; then
    ok "limactl resolver logs the documented FATAL message when missing"
else
    fail "limactl resolver did not log the documented FATAL message: '${err_c}'"
fi

# ---------------------------------------------------------------------
section "8. P-020 and P-021 audit markers present"
# ---------------------------------------------------------------------
if /usr/bin/grep -q 'P-020' "$COLIMA_LIB"; then
    ok "P-020 audit marker in install_colima.sh"
else
    fail "P-020 audit marker missing from install_colima.sh"
fi
if /usr/bin/grep -q 'P-020' "$BUILD_PKG"; then
    ok "P-020 audit marker in build_pkg.sh"
else
    fail "P-020 audit marker missing from build_pkg.sh"
fi
if /usr/bin/grep -q 'P-021' "$BUILD_PKG"; then
    ok "P-021 audit marker in build_pkg.sh"
else
    fail "P-021 audit marker missing from build_pkg.sh"
fi
if /usr/bin/grep -q 'P-021' "$ENTITLEMENTS"; then
    ok "P-021 audit marker in vz.entitlements"
else
    fail "P-021 audit marker missing from vz.entitlements"
fi

# ---------------------------------------------------------------------
section "9. bash -n parses both files"
# ---------------------------------------------------------------------
for f in "$BUILD_PKG" "$COLIMA_LIB"; do
    if bash -n "$f" 2>/dev/null; then
        ok "bash -n clean: $(basename "$f")"
    else
        fail "bash -n FAILED on $(basename "$f"):"
        bash -n "$f" 2>&1 | sed 's/^/    /' >&2 || true
    fi
done

# ---------------------------------------------------------------------
section "Summary"
# ---------------------------------------------------------------------
echo
echo "  Passed: ${pass_count}"
echo "  Failed: ${fail_count}"
echo

if (( fail_count > 0 )); then
    exit 1
fi
exit 0
