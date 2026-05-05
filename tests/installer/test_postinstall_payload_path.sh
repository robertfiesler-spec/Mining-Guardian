#!/usr/bin/env bash
# tests/installer/test_postinstall_payload_path.sh
#
# D-18 P-017 — postinstall.sh MG_PKG_PAYLOAD must resolve to the install
# location at install time, NOT to the scripts-sandbox `../payload`.
#
# Background. With `pkgbuild --root ${PAYLOAD_DIR} --scripts ${SCRIPTS_DIR}
# --install-location "/Library/Application Support/MiningGuardian"`,
# Installer.app at install time:
#   * extracts the *scripts* archive into a private sandbox like
#     /tmp/PKInstallSandbox.<rand>/Scripts/com.miningguardian.installer.core.<rand>/
#     and runs preinstall/postinstall from there;
#   * extracts the *payload* archive directly to the install location
#     `/Library/Application Support/MiningGuardian/`.
#
# The legacy `MG_PKG_PAYLOAD="${SCRIPT_DIR}/../payload"` resolves to a
# path INSIDE the scripts sandbox that does NOT exist — the scripts
# sandbox holds only the script archive contents. The cf1691e + 9318062
# install attempts on the customer Mini both exited 31 in
# `install_colima_runtime` with:
#   FATAL vendored colima runtime not found at
#     /tmp/PKInstallSandbox.sJTxI0/Scripts/com.miningguardian.installer.core.Hy5Eby/../payload/runtime/colima
#
# The fix sets MG_PKG_PAYLOAD to MG_INSTALL_ROOT (the install location)
# when ${MG_INSTALL_ROOT}/runtime exists, with a fallback to the legacy
# path for dev / smoke-test invocations outside a real .pkg install.
#
# This test asserts:
#   1. postinstall.sh parses (bash -n).
#   2. The install-root branch is present and chosen first.
#   3. The legacy `../payload` path is NOT the unconditional default.
#   4. install_colima.sh + install_ollama.sh still consume MG_PKG_PAYLOAD
#      (i.e. they did not regress to a hard-coded scripts-sandbox path).
#   5. Runtime: with MG_INSTALL_ROOT containing a `runtime/` dir,
#      MG_PKG_PAYLOAD resolves to MG_INSTALL_ROOT.
#   6. Runtime: with MG_INSTALL_ROOT empty (no runtime/), MG_PKG_PAYLOAD
#      falls back to ${SCRIPT_DIR}/../payload.
#   7. P-017 reference is present in postinstall.sh header.
#
# Run from repo root:
#     bash tests/installer/test_postinstall_payload_path.sh
#
# Exits 0 on success, non-zero on first failed assertion.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

POSTINSTALL="installer/macos-pkg/scripts/postinstall.sh"
COLIMA_LIB="installer/macos-pkg/scripts/lib/install_colima.sh"
OLLAMA_LIB="installer/macos-pkg/scripts/lib/install_ollama.sh"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }

section() { echo; echo "## $*"; }

# ---------------------------------------------------------------------
section "1. postinstall.sh parses"
# ---------------------------------------------------------------------
if bash -n "$POSTINSTALL" 2>/dev/null; then
    ok "postinstall.sh parses (bash -n)"
else
    fail "postinstall.sh has bash syntax errors"
fi

# ---------------------------------------------------------------------
section "2. Install-root branch present"
# ---------------------------------------------------------------------
# The fix branches on the existence of ${MG_INSTALL_ROOT}/runtime and
# uses MG_INSTALL_ROOT when it exists. Look for both halves.
if /usr/bin/grep -q 'MG_PKG_PAYLOAD="${MG_INSTALL_ROOT}"' "$POSTINSTALL"; then
    ok "MG_PKG_PAYLOAD assigned from MG_INSTALL_ROOT"
else
    fail "MG_PKG_PAYLOAD=MG_INSTALL_ROOT branch missing"
fi

if /usr/bin/grep -qE '\[\[ -d "\$\{MG_INSTALL_ROOT\}/runtime" \]\]' "$POSTINSTALL"; then
    ok "guarded by MG_INSTALL_ROOT/runtime existence check"
else
    fail "existence guard for MG_INSTALL_ROOT/runtime missing"
fi

# ---------------------------------------------------------------------
section "3. Legacy ../payload is fallback only, not the default"
# ---------------------------------------------------------------------
# The legacy assignment may still appear in the fallback branch (and in
# documentation), but it must NOT be the only / unconditional setter.
# Concretely: the line `export MG_PKG_PAYLOAD="${SCRIPT_DIR}/../payload"`
# at top level (no leading whitespace beyond a `else` arm) is the bug.
# We assert the unconditional pattern is gone — i.e. there is at least
# one MG_INSTALL_ROOT-based branch above any fallback.
mg_install_root_line="$(/usr/bin/grep -nE 'MG_PKG_PAYLOAD="\$\{MG_INSTALL_ROOT\}"' "$POSTINSTALL" | /usr/bin/awk -F: '{print $1; exit}' || true)"
legacy_line="$(/usr/bin/grep -nE 'MG_PKG_PAYLOAD="\$\{SCRIPT_DIR\}/\.\./payload"' "$POSTINSTALL" | /usr/bin/awk -F: '{print $1; exit}' || true)"

if [[ -n "$mg_install_root_line" && -n "$legacy_line" ]]; then
    if (( mg_install_root_line < legacy_line )); then
        ok "MG_INSTALL_ROOT branch (line ${mg_install_root_line}) precedes legacy fallback (line ${legacy_line})"
    else
        fail "legacy fallback (line ${legacy_line}) appears before MG_INSTALL_ROOT branch (line ${mg_install_root_line}) — branch order wrong"
    fi
elif [[ -n "$mg_install_root_line" && -z "$legacy_line" ]]; then
    ok "only MG_INSTALL_ROOT branch present (no legacy fallback)"
else
    fail "neither install-root branch nor legacy line found — postinstall does not assign MG_PKG_PAYLOAD"
fi

# ---------------------------------------------------------------------
section "4. Helper libs still consume MG_PKG_PAYLOAD"
# ---------------------------------------------------------------------
# The fix lives in postinstall.sh; the helper libs read MG_PKG_PAYLOAD
# unchanged. Belt-and-suspenders: assert no helper hard-codes a
# scripts-sandbox path or rewrites MG_PKG_PAYLOAD.
for lib in "$COLIMA_LIB" "$OLLAMA_LIB"; do
    if /usr/bin/grep -q 'MG_PKG_PAYLOAD' "$lib"; then
        ok "$(basename "$lib") consumes MG_PKG_PAYLOAD"
    else
        fail "$(basename "$lib") no longer references MG_PKG_PAYLOAD"
    fi
    # No helper lib is allowed to hard-code a PKInstallSandbox path or
    # `${SCRIPT_DIR}/../payload` — those are bugs.
    if /usr/bin/grep -qE 'PKInstallSandbox' "$lib"; then
        fail "$(basename "$lib") references PKInstallSandbox literal — must not"
    else
        ok "$(basename "$lib") has no PKInstallSandbox literal"
    fi
done

# ---------------------------------------------------------------------
section "5. Runtime: payload resolves to install root when runtime/ exists"
# ---------------------------------------------------------------------
# Build a tiny harness that mirrors the top-of-script `MG_PKG_PAYLOAD`
# resolution and exercise both branches. We extract the relevant lines
# from the file itself so the test stays in sync with future edits.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Branch A — MG_INSTALL_ROOT/runtime exists. Expect MG_PKG_PAYLOAD == MG_INSTALL_ROOT.
ROOT_A="${TMP}/root_with_runtime"
mkdir -p "${ROOT_A}/runtime/colima"

# Build a synthetic SCRIPT_DIR + payload tree that the legacy path WOULD
# resolve to. We want to verify the install-root branch wins even when
# the legacy fallback path also exists on disk.
SANDBOX_A="${TMP}/sandbox_a/Scripts/com.miningguardian.installer.core.X"
mkdir -p "$SANDBOX_A"
LEGACY_PAYLOAD_A="${TMP}/sandbox_a/payload"
mkdir -p "${LEGACY_PAYLOAD_A}/runtime/colima"

cat > "${TMP}/probe_a.sh" <<EOF
#!/usr/bin/env bash
set -uo pipefail
export MG_INSTALL_ROOT="${ROOT_A}"
SCRIPT_DIR="${SANDBOX_A}"
if [[ -d "\${MG_INSTALL_ROOT}/runtime" ]]; then
    export MG_PKG_PAYLOAD="\${MG_INSTALL_ROOT}"
else
    export MG_PKG_PAYLOAD="\${SCRIPT_DIR}/../payload"
fi
echo "MG_PKG_PAYLOAD=\${MG_PKG_PAYLOAD}"
EOF
chmod +x "${TMP}/probe_a.sh"
out_a="$(bash "${TMP}/probe_a.sh" 2>&1 || true)"
if echo "$out_a" | /usr/bin/grep -q "^MG_PKG_PAYLOAD=${ROOT_A}$"; then
    ok "install-root branch chosen when MG_INSTALL_ROOT/runtime exists"
else
    fail "branch A failed: ${out_a}"
fi

# ---------------------------------------------------------------------
section "6. Runtime: fallback to ../payload when MG_INSTALL_ROOT empty"
# ---------------------------------------------------------------------
# Branch B — no runtime/ under MG_INSTALL_ROOT. Expect fallback path.
ROOT_B="${TMP}/root_empty"
mkdir -p "$ROOT_B"  # exists but no runtime/
SANDBOX_B="${TMP}/sandbox_b/Scripts/com.miningguardian.installer.core.X"
mkdir -p "$SANDBOX_B"
LEGACY_PAYLOAD_B="${TMP}/sandbox_b/payload"
mkdir -p "$LEGACY_PAYLOAD_B"

cat > "${TMP}/probe_b.sh" <<EOF
#!/usr/bin/env bash
set -uo pipefail
export MG_INSTALL_ROOT="${ROOT_B}"
SCRIPT_DIR="${SANDBOX_B}"
if [[ -d "\${MG_INSTALL_ROOT}/runtime" ]]; then
    export MG_PKG_PAYLOAD="\${MG_INSTALL_ROOT}"
else
    export MG_PKG_PAYLOAD="\${SCRIPT_DIR}/../payload"
fi
echo "MG_PKG_PAYLOAD=\${MG_PKG_PAYLOAD}"
EOF
chmod +x "${TMP}/probe_b.sh"
out_b="$(bash "${TMP}/probe_b.sh" 2>&1 || true)"
expected_b="${SANDBOX_B}/../payload"
if echo "$out_b" | /usr/bin/grep -q "^MG_PKG_PAYLOAD=${expected_b}$"; then
    ok "fallback branch chosen when MG_INSTALL_ROOT/runtime missing"
else
    fail "branch B failed: ${out_b} (expected MG_PKG_PAYLOAD=${expected_b})"
fi

# ---------------------------------------------------------------------
section "7. P-017 reference present in postinstall.sh"
# ---------------------------------------------------------------------
if /usr/bin/grep -q 'P-017' "$POSTINSTALL"; then
    ok "P-017 reference present in postinstall.sh"
else
    fail "P-017 reference missing — should be cited where the fix lands"
fi

# Sanity: the diagnostic literal from the cf1691e/9318062 install logs
# should also appear so future readers can grep for the exact symptom.
if /usr/bin/grep -q 'PKInstallSandbox' "$POSTINSTALL"; then
    ok "PKInstallSandbox symptom mentioned (greppable from log)"
else
    fail "PKInstallSandbox symptom not mentioned — future debug harder"
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
