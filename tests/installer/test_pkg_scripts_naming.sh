#!/usr/bin/env bash
# tests/installer/test_pkg_scripts_naming.sh
#
# P-013 (2026-05-04) — macOS PackageKit script-naming regression guard.
#
# Background:
#   On 2026-05-04 Rob installed signed/notarized v1.0.3 build a35728d
#   on the customer Mac mini. The installer reported success and the
#   payload was laid down at /Library/Application Support/MiningGuardian
#   with the BUILD_STAMP.json showing version 1.0.3 + sha a35728dcfc8c.
#   But every postinstall artifact was MISSING:
#
#     /etc/mining-guardian/install-receipt.json     (missing)
#     /var/log/mining-guardian/install-postinstall.log (missing)
#     <install-root>/.env                           (missing)
#     <install-root>/venv/                          (missing)
#     <install-root>/logs/                          (missing)
#     <install-root>/postgres-data/                 (missing)
#     <install-root>/bin/                           (missing)
#
#   Root cause: build_pkg.sh step_4_assemble_payload step 4d staged the
#   scripts under their repo names `preinstall.sh` and `postinstall.sh`.
#   Apple's pkgbuild man page is explicit:
#     "If this directory contains scripts named preinstall and/or
#      postinstall, these will be run as the top-level scripts of the
#      package."
#   PackageKit silently ignores any other filename — including
#   `preinstall.sh` and `postinstall.sh`. So Installer.app extracted the
#   Scripts archive, never invoked anything inside it, wrote the BOM +
#   receipt, and reported success. The user-facing failure mode is a
#   payload-only install with no error in the install.log.
#
#   The fix in build_pkg.sh step 4d renames at staging time:
#     <staging>/preinstall.sh  -> <staging>/preinstall
#     <staging>/postinstall.sh -> <staging>/postinstall
#   Source files keep the .sh suffix so `bash -n`, shellcheck, and
#   editor highlighting still work.
#
# This test asserts:
#   1. The two source scripts exist with the .sh extension and are
#      executable in the source tree (committed mode).
#   2. build_pkg.sh step 4d performs the rename to extensionless names
#      (mv preinstall.sh -> preinstall; mv postinstall.sh -> postinstall).
#   3. build_pkg.sh refuses to leave any *.sh at the staging-dir top level
#      after the rename — the belt-and-suspenders find/_die guard exists.
#   4. build_pkg.sh chmod's the renamed files 0755 (executable) and
#      keeps the lib/*.sh chmod block.
#   5. build_pkg.sh parses with `bash -n` after the edit.
#   6. There is no remaining live (non-comment) reference inside
#      build_pkg.sh that hands `${SCRIPTS_DIR}/preinstall.sh` or
#      `${SCRIPTS_DIR}/postinstall.sh` to a downstream tool — a future
#      edit that re-introduced a chmod or pkgbuild flag pointing at the
#      old names would re-break the install.
#
# Static check only — no Mac, no Installer.app, no pkgbuild invocation.
# A future "smoke" test on macOS could pkgutil --expand a built pkg
# and assert "preinstall" + "postinstall" exist inside core.pkg/Scripts;
# we keep this static for portability with the rest of tests/installer/.
#
# Run from repo root:
#     bash tests/installer/test_pkg_scripts_naming.sh
#
# Exits 0 on success, non-zero on first failed assertion.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

BUILD_PKG="installer/macos-pkg/scripts/build_pkg.sh"
PRE_SRC="installer/macos-pkg/scripts/preinstall.sh"
POST_SRC="installer/macos-pkg/scripts/postinstall.sh"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }

section() { echo; echo "## $*"; }

# ---------------------------------------------------------------------
section "1. Source files exist and are executable"
# ---------------------------------------------------------------------
for f in "$BUILD_PKG" "$PRE_SRC" "$POST_SRC"; do
    if [[ -r "$f" ]]; then
        ok "$f present"
    else
        fail "$f missing"
    fi
done
# Mode 0755 in the source tree (preserved by .pkg-build at runtime).
for f in "$PRE_SRC" "$POST_SRC"; do
    if [[ -x "$f" ]]; then
        ok "$f is executable in source tree"
    else
        fail "$f is NOT executable in source tree (chmod +x and commit)"
    fi
done

# ---------------------------------------------------------------------
section "2. build_pkg.sh parses (bash -n)"
# ---------------------------------------------------------------------
if bash -n "$BUILD_PKG" 2>/dev/null; then
    ok "build_pkg.sh parses"
else
    fail "build_pkg.sh has bash syntax errors"
fi

# ---------------------------------------------------------------------
section "3. build_pkg.sh step 4d renames to extensionless names"
# ---------------------------------------------------------------------
# Live, non-comment lines only — comments documenting the historical
# violation are fine.
live_body="$(/usr/bin/grep -vE '^[[:space:]]*#' "$BUILD_PKG")"

if echo "$live_body" | /usr/bin/grep -qE 'mv -f[[:space:]]+"\$\{SCRIPTS_DIR\}/preinstall\.sh"[[:space:]]+"\$\{SCRIPTS_DIR\}/preinstall"'; then
    ok "build_pkg.sh renames preinstall.sh -> preinstall in staging"
else
    fail "build_pkg.sh missing rename: \${SCRIPTS_DIR}/preinstall.sh -> \${SCRIPTS_DIR}/preinstall (P-013)"
fi
if echo "$live_body" | /usr/bin/grep -qE 'mv -f[[:space:]]+"\$\{SCRIPTS_DIR\}/postinstall\.sh"[[:space:]]+"\$\{SCRIPTS_DIR\}/postinstall"'; then
    ok "build_pkg.sh renames postinstall.sh -> postinstall in staging"
else
    fail "build_pkg.sh missing rename: \${SCRIPTS_DIR}/postinstall.sh -> \${SCRIPTS_DIR}/postinstall (P-013)"
fi

# ---------------------------------------------------------------------
section "4. build_pkg.sh chmods the renamed (extensionless) files"
# ---------------------------------------------------------------------
if echo "$live_body" | /usr/bin/grep -qE 'chmod[[:space:]]+0755[[:space:]]+"\$\{SCRIPTS_DIR\}/preinstall"[[:space:]]+"\$\{SCRIPTS_DIR\}/postinstall"'; then
    ok "build_pkg.sh chmods 0755 on extensionless preinstall+postinstall"
else
    fail "build_pkg.sh missing chmod 0755 on \${SCRIPTS_DIR}/preinstall and \${SCRIPTS_DIR}/postinstall (P-013)"
fi

# ---------------------------------------------------------------------
section "5. build_pkg.sh refuses leftover top-level *.sh in staging"
# ---------------------------------------------------------------------
# After the mv, find -maxdepth 1 -type f -name '*.sh' should be empty;
# build_pkg.sh asserts this and aborts with exit 43 if not.
if echo "$live_body" | /usr/bin/grep -qE "find[[:space:]]+\"\\\$\{SCRIPTS_DIR\}\"[[:space:]]+-maxdepth[[:space:]]+1[[:space:]]+-type[[:space:]]+f[[:space:]]+-name[[:space:]]+'?\\*\.sh'?"; then
    ok "build_pkg.sh has find guard for leftover top-level *.sh"
else
    fail "build_pkg.sh missing find guard for top-level *.sh in \${SCRIPTS_DIR} (P-013)"
fi
# And asserts the renamed entries are executable post-rename.
if echo "$live_body" | /usr/bin/grep -qE '\[\[[[:space:]]+!\s+-x[[:space:]]+"\$\{SCRIPTS_DIR\}/preinstall"'; then
    ok "build_pkg.sh asserts \${SCRIPTS_DIR}/preinstall is executable after rename"
else
    fail "build_pkg.sh missing post-rename executable assertion for preinstall (P-013)"
fi
if echo "$live_body" | /usr/bin/grep -qE '\[\[[[:space:]]+!\s+-x[[:space:]]+"\$\{SCRIPTS_DIR\}/postinstall"'; then
    ok "build_pkg.sh asserts \${SCRIPTS_DIR}/postinstall is executable after rename"
else
    fail "build_pkg.sh missing post-rename executable assertion for postinstall (P-013)"
fi

# ---------------------------------------------------------------------
section "6. No live reference to *.sh entry points in staging dir"
# ---------------------------------------------------------------------
# A future edit that re-introduced
#     chmod +x "${SCRIPTS_DIR}/preinstall.sh"
# or some pkgbuild flag pointing at preinstall.sh would re-break the
# install. The only allowed live references to ${SCRIPTS_DIR}/preinstall.sh
# are the staging guard (`[[ ! -r ... ]]`), its `_die` error message,
# and the `mv -f ... -> preinstall` rename. We strip those three line
# shapes; anything that still mentions ${SCRIPTS_DIR}/(pre|post)install.sh
# is a violation that would re-break the install.
strict_body="$(echo "$live_body" \
    | /usr/bin/grep -vE 'mv -f[[:space:]]+"\$\{SCRIPTS_DIR\}/(preinstall|postinstall)\.sh"' \
    | /usr/bin/grep -vE '\[\[[[:space:]]+!\s+-r[[:space:]]+"\$\{SCRIPTS_DIR\}/(preinstall|postinstall)\.sh"' \
    | /usr/bin/grep -vE '_die[[:space:]]+43[[:space:]]+"step 4d:[^"]*\$\{SCRIPTS_DIR\}/(preinstall|postinstall)\.sh"' \
    || true)"

# strict_body now is the rest of the live (non-comment) script. It must
# NOT contain "${SCRIPTS_DIR}/preinstall.sh" or "${SCRIPTS_DIR}/postinstall.sh".
if echo "$strict_body" | /usr/bin/grep -qE '\$\{SCRIPTS_DIR\}/preinstall\.sh'; then
    fail "build_pkg.sh has stray live reference to \${SCRIPTS_DIR}/preinstall.sh outside the rename block (P-013)"
else
    ok "build_pkg.sh has no stray live reference to \${SCRIPTS_DIR}/preinstall.sh"
fi
if echo "$strict_body" | /usr/bin/grep -qE '\$\{SCRIPTS_DIR\}/postinstall\.sh'; then
    fail "build_pkg.sh has stray live reference to \${SCRIPTS_DIR}/postinstall.sh outside the rename block (P-013)"
else
    ok "build_pkg.sh has no stray live reference to \${SCRIPTS_DIR}/postinstall.sh"
fi

# ---------------------------------------------------------------------
section "7. P-013 marker present in build_pkg.sh"
# ---------------------------------------------------------------------
# Cheap forensics: future agents searching for "P-013" in the repo find
# the build-time rename block immediately.
if /usr/bin/grep -qE 'P-013' "$BUILD_PKG"; then
    ok "build_pkg.sh references P-013 (audit marker)"
else
    fail "build_pkg.sh has no P-013 reference — add a comment marker for future-grep"
fi

# ---------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------
echo
echo "================================================================"
echo "Passed:  ${pass_count}"
echo "Failed:  ${fail_count}"
echo "================================================================"

if (( fail_count > 0 )); then
    exit 1
fi
exit 0
