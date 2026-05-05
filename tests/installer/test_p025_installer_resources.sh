#!/usr/bin/env bash
# tests/installer/test_p025_installer_resources.sh
#
# D-18 P-025 (2026-05-05) — installer-owned resources land in the payload
# at install time, NOT in the scripts sandbox.
#
# Background. With `pkgbuild --root ${PAYLOAD_DIR} --scripts ${SCRIPTS_DIR}`,
# Installer.app extracts ONLY the scripts archive (lib/ + preinstall +
# postinstall) into a private sandbox at
# `/tmp/PKInstallSandbox.<rand>/Scripts/com.miningguardian.installer.core.<rand>/`
# and runs the scripts from there. productbuild --resources content
# (Distribution.xml, branding, welcome/conclusion HTML, license text,
# resources/launchd/, resources/uninstall.sh) is metadata-only — it
# never lands on disk next to the scripts.
#
# The legacy postinstall.sh paths
#   ${SCRIPT_DIR}/../resources/launchd
#   ${SCRIPT_DIR}/../resources/launchd/launchers
#   ${SCRIPT_DIR}/../resources/launchd/scheduled
#   ${SCRIPT_DIR}/../resources/uninstall.sh
# all resolved to that nonexistent sandbox-relative path. Service
# bootstrap (exit 37), scheduled-job bootstrap (exit 40), and
# step_install_uninstall_script (exit 37) would have hit this on the
# next install attempt against the customer Mini.
#
# The P-025 fix:
#   * build_pkg.sh step 4k stages installer/macos-pkg/resources/launchd/
#     and installer/macos-pkg/resources/uninstall.sh into the customer
#     payload at <payload>/installer-resources/.
#   * postinstall.sh sets INSTALLER_RESOURCES_SRC to
#     ${MG_PKG_PAYLOAD}/installer-resources when present, falling back
#     to ${SCRIPT_DIR}/../resources for dev / smoke-test runs.
#   * The four readonly source-path constants (PLISTS_SRC, LAUNCHERS_SRC,
#     SCHEDULED_PLISTS_SRC, UNINSTALL_SH_SRC) all derive from
#     INSTALLER_RESOURCES_SRC, so no install-time consumer reads through
#     ${SCRIPT_DIR}/../resources any more.
#
# This test asserts:
#   1. postinstall.sh parses (bash -n).
#   2. INSTALLER_RESOURCES_SRC is declared and resolved through
#      ${MG_PKG_PAYLOAD}/installer-resources first, with the dev
#      fallback second.
#   3. PLISTS_SRC, LAUNCHERS_SRC, SCHEDULED_PLISTS_SRC, UNINSTALL_SH_SRC
#      derive from INSTALLER_RESOURCES_SRC (no remaining
#      ${SCRIPT_DIR}/../resources/... at the source-constant level).
#   4. No install-time SOURCE assignment in postinstall.sh still uses
#      ${SCRIPT_DIR}/../resources for plists / launchers / scheduled /
#      uninstall.sh. (Comments and dev-fallback are exempt.)
#   5. build_pkg.sh step 4k exists and stages the launchd/ tree +
#      uninstall.sh into <payload>/installer-resources/.
#   6. build_pkg.sh step 4b asserts <payload>/scripts/ is present after
#      the 4a rsync (A-4 fix).
#   7. The 4a rsync include list contains `--include 'scripts/***'`.
#   8. Every scheduled-job plist's ProgramArguments entrypoint either
#      lives in the source tree (so the 4a rsync would carry it into
#      the payload) or is a documented latent bug.
#
# Run from repo root:
#     bash tests/installer/test_p025_installer_resources.sh
#
# Exits 0 on success, non-zero on first failed assertion.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

POSTINSTALL="installer/macos-pkg/scripts/postinstall.sh"
BUILD_PKG="installer/macos-pkg/scripts/build_pkg.sh"
SCHEDULED_DIR="installer/macos-pkg/resources/launchd/scheduled"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }
section() { echo; echo "## $*"; }

# ---------------------------------------------------------------------
section "1. postinstall.sh + build_pkg.sh parse"
# ---------------------------------------------------------------------
if bash -n "$POSTINSTALL" 2>/dev/null; then
    ok "bash -n ${POSTINSTALL} passes"
else
    fail "bash -n ${POSTINSTALL} reported a syntax error"
fi
if bash -n "$BUILD_PKG" 2>/dev/null; then
    ok "bash -n ${BUILD_PKG} passes"
else
    fail "bash -n ${BUILD_PKG} reported a syntax error"
fi

# ---------------------------------------------------------------------
section "2. INSTALLER_RESOURCES_SRC resolves payload-first, dev-fallback"
# ---------------------------------------------------------------------
if /usr/bin/grep -q 'INSTALLER_RESOURCES_SRC="${MG_PKG_PAYLOAD}/installer-resources"' "$POSTINSTALL"; then
    ok "INSTALLER_RESOURCES_SRC primary branch points at \${MG_PKG_PAYLOAD}/installer-resources"
else
    fail "INSTALLER_RESOURCES_SRC primary branch missing or wrong"
fi
if /usr/bin/grep -q 'INSTALLER_RESOURCES_SRC="${SCRIPT_DIR}/../resources"' "$POSTINSTALL"; then
    ok "INSTALLER_RESOURCES_SRC dev fallback present"
else
    fail "INSTALLER_RESOURCES_SRC dev fallback missing"
fi
if /usr/bin/grep -q 'readonly INSTALLER_RESOURCES_SRC' "$POSTINSTALL"; then
    ok "INSTALLER_RESOURCES_SRC is readonly"
else
    fail "INSTALLER_RESOURCES_SRC not readonly"
fi

# ---------------------------------------------------------------------
section "3. Source-path constants derive from INSTALLER_RESOURCES_SRC"
# ---------------------------------------------------------------------
for var in \
    'PLISTS_SRC="${INSTALLER_RESOURCES_SRC}/launchd"' \
    'LAUNCHERS_SRC="${INSTALLER_RESOURCES_SRC}/launchd/launchers"' \
    'SCHEDULED_PLISTS_SRC="${INSTALLER_RESOURCES_SRC}/launchd/scheduled"' \
    'UNINSTALL_SH_SRC="${INSTALLER_RESOURCES_SRC}/uninstall.sh"'
do
    if /usr/bin/grep -qF -- "$var" "$POSTINSTALL"; then
        ok "constant present: ${var}"
    else
        fail "constant missing or not derived from INSTALLER_RESOURCES_SRC: ${var}"
    fi
done

# ---------------------------------------------------------------------
section "4. No install-time consumer reads \${SCRIPT_DIR}/../resources"
# ---------------------------------------------------------------------
# Strip comment lines, then assert no remaining match for the legacy
# pattern in any path-constant assignment. The dev-fallback assignment
# is exempt — it's the explicit second branch of the resolver.
legacy_hits="$(/usr/bin/grep -nE '^\s*[A-Z_]+="\$\{SCRIPT_DIR\}/\.\./resources' "$POSTINSTALL" \
    | /usr/bin/grep -v 'INSTALLER_RESOURCES_SRC' \
    || true)"
if [[ -z "$legacy_hits" ]]; then
    ok "no install-time path constant reads \${SCRIPT_DIR}/../resources"
else
    fail "legacy \${SCRIPT_DIR}/../resources path constants remain:"
    echo "$legacy_hits" >&2
fi

# ---------------------------------------------------------------------
section "5. build_pkg.sh step 4k stages installer-resources/"
# ---------------------------------------------------------------------
if /usr/bin/grep -q 'step 4k' "$BUILD_PKG"; then
    ok "build_pkg.sh names step 4k"
else
    fail "build_pkg.sh missing step 4k"
fi
if /usr/bin/grep -qF 'PAYLOAD_DIR}/installer-resources' "$BUILD_PKG"; then
    ok "step 4k targets <payload>/installer-resources/"
else
    fail "step 4k does not target <payload>/installer-resources/"
fi
if /usr/bin/grep -qF 'PKG_DIR}/resources/launchd/' "$BUILD_PKG" \
   && /usr/bin/grep -qF 'installer_resources_dst}/launchd/' "$BUILD_PKG"; then
    ok "step 4k rsyncs resources/launchd/ -> installer-resources/launchd/"
else
    fail "step 4k missing resources/launchd/ rsync"
fi
if /usr/bin/grep -qF 'installer-resources/uninstall.sh' "$BUILD_PKG"; then
    ok "step 4k installs uninstall.sh into installer-resources/"
else
    fail "step 4k does not install uninstall.sh into installer-resources/"
fi

# ---------------------------------------------------------------------
section "6. build_pkg.sh asserts <payload>/scripts/ after rsync (A-4)"
# ---------------------------------------------------------------------
if /usr/bin/grep -qF 'PAYLOAD_DIR}/scripts' "$BUILD_PKG"; then
    ok "build_pkg.sh asserts <payload>/scripts/"
else
    fail "build_pkg.sh missing <payload>/scripts/ assertion"
fi

# ---------------------------------------------------------------------
section "7. 4a rsync includes scripts/***"
# ---------------------------------------------------------------------
if /usr/bin/grep -qF -- "--include 'scripts/***'" "$BUILD_PKG"; then
    ok "build_pkg.sh 4a rsync includes scripts/***"
else
    fail "build_pkg.sh 4a rsync missing --include 'scripts/***'"
fi

# ---------------------------------------------------------------------
section "8. Every scheduled-plist entrypoint exists in the source tree"
# ---------------------------------------------------------------------
# Pull the third <string>...</string> entry out of each scheduled plist's
# ProgramArguments array — that's the entrypoint relative to
# ${INSTALL_ROOT}. Format:
#     <string>/bin/bash</string>
#     <string>/Library/.../scheduled_job_launcher.sh</string>
#     <string>scripts/foo.py</string>      <-- this one
#     <string>label</string>
#
# The 11th entrypoint (tests/run_benchmark.py) is a known pre-existing
# latent bug — see plist comment + docs/LATENT_BUGS.md. P-025 does not
# fix it. Whitelist it explicitly so this test does not regress when
# the bug is later resolved separately.
KNOWN_LATENT=(
    "tests/run_benchmark.py"
)

is_latent() {
    local needle="$1" w
    for w in "${KNOWN_LATENT[@]}"; do
        [[ "$w" == "$needle" ]] && return 0
    done
    return 1
}

extract_entrypoint() {
    /usr/bin/awk '
        /<key>ProgramArguments<\/key>/ { in_pa=1; next }
        in_pa && /<\/array>/ { in_pa=0; next }
        in_pa && /<string>/ {
            count++
            if (count == 3) {
                line=$0
                sub(/.*<string>/, "", line)
                sub(/<\/string>.*/, "", line)
                print line
                exit
            }
        }
    ' "$1"
}

for plist in "${SCHEDULED_DIR}"/*.plist; do
    label="$(basename "$plist" .plist)"
    entry="$(extract_entrypoint "$plist")"
    if [[ -z "$entry" ]]; then
        fail "could not extract entrypoint from ${label}.plist"
        continue
    fi
    if [[ -e "$entry" ]]; then
        ok "${label}: ${entry} exists in source tree"
    elif is_latent "$entry"; then
        ok "${label}: ${entry} is a known latent bug (whitelisted)"
    else
        fail "${label}: entrypoint ${entry} missing in source tree"
    fi
done

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
