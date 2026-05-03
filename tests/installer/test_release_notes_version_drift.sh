#!/usr/bin/env bash
# tests/installer/test_release_notes_version_drift.sh
#
# P-009 — pyproject.toml ↔ docs/RELEASE_NOTES_v<VERSION>.md drift guard.
#
# Asserts:
#   1. pyproject.toml parses to a semver string vX.Y.Z
#   2. docs/RELEASE_NOTES_v${VERSION}.md exists for that exact version
#   3. The first heading line in the release notes matches the version
#      (e.g. "# Mining Guardian v1.0.3")
#   4. No older RELEASE_NOTES_v*.md file claims a version >= ${VERSION}
#      that would shadow the current release
#   5. installer/macos-pkg/scripts/build_pkg.sh still reads pyproject.toml
#      via the inline python3 snippet that has been the source of truth
#      since PR #110 (v1.0.2 release bump)
#
# This protects against the failure mode where a release-bump PR ships
# pyproject without notes (or notes without a pyproject bump), or a
# stale notes file outranks the current release.
#
# Run from repo root:
#     bash tests/installer/test_release_notes_version_drift.sh
#
# Exits 0 on success, non-zero on first failed assertion.
# Requires: bash, grep, awk. No network, no Mac.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PYPROJECT="pyproject.toml"
NOTES_DIR="docs"
BUILD_PKG="installer/macos-pkg/scripts/build_pkg.sh"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }
section() { echo; echo "## $*"; }

# Parse vX.Y.Z out of `version = "X.Y.Z"` in pyproject.toml.
# Tolerant of single or double quotes and extra whitespace.
# Refuses anything that is not strictly major.minor.patch (no pre-release
# suffixes — those are out of scope for this repo's release pattern).
parse_pyproject_version() {
    awk '
        /^version[[:space:]]*=/ {
            # strip everything up to the first quote
            sub(/^[^"\047]*["\047]/, "")
            # strip trailing quote and anything after
            sub(/["\047].*$/, "")
            print
            exit
        }
    ' "$PYPROJECT"
}

# Compare two semver strings X.Y.Z. Echoes -1 / 0 / 1.
semver_cmp() {
    local a="$1" b="$2"
    local IFS=.
    # shellcheck disable=SC2206
    local aa=( $a ) bb=( $b )
    for i in 0 1 2; do
        local x="${aa[$i]:-0}" y="${bb[$i]:-0}"
        if (( x < y )); then echo "-1"; return; fi
        if (( x > y )); then echo "1"; return; fi
    done
    echo "0"
}

# ---------------------------------------------------------------------
section "1. pyproject.toml parses to a semver"
# ---------------------------------------------------------------------

if [[ ! -r "$PYPROJECT" ]]; then
    fail "$PYPROJECT not readable"
    exit 1
fi
ok "$PYPROJECT readable"

VERSION="$(parse_pyproject_version)"
if [[ -z "$VERSION" ]]; then
    fail "could not parse version from $PYPROJECT"
    exit 1
fi
ok "parsed version=${VERSION}"

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    fail "version=${VERSION} is not strict semver X.Y.Z"
    exit 1
fi
ok "version=${VERSION} is strict semver"

# ---------------------------------------------------------------------
section "2. RELEASE_NOTES_v${VERSION}.md exists"
# ---------------------------------------------------------------------

NOTES_FILE="${NOTES_DIR}/RELEASE_NOTES_v${VERSION}.md"
if [[ ! -r "$NOTES_FILE" ]]; then
    fail "release notes file missing: ${NOTES_FILE}"
    exit 1
fi
ok "${NOTES_FILE} present"

# ---------------------------------------------------------------------
section "3. First heading matches the version"
# ---------------------------------------------------------------------

FIRST_HEADING="$(awk '/^# / { print; exit }' "$NOTES_FILE")"
EXPECTED_HEADING="# Mining Guardian v${VERSION}"
if [[ "$FIRST_HEADING" != "$EXPECTED_HEADING" ]]; then
    fail "first heading mismatch: got '${FIRST_HEADING}', expected '${EXPECTED_HEADING}'"
else
    ok "first heading matches: ${EXPECTED_HEADING}"
fi

# ---------------------------------------------------------------------
section "4. No newer RELEASE_NOTES_v*.md exists that would shadow this release"
# ---------------------------------------------------------------------

found_newer=0
for f in "${NOTES_DIR}"/RELEASE_NOTES_v*.md; do
    [[ -r "$f" ]] || continue
    base="$(basename "$f")"
    other_v="${base#RELEASE_NOTES_v}"
    other_v="${other_v%.md}"
    if [[ ! "$other_v" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        # ignore non-strict-semver release notes (none today, but tolerant)
        continue
    fi
    cmp="$(semver_cmp "$other_v" "$VERSION")"
    if [[ "$cmp" == "1" ]]; then
        fail "newer release notes file exists: ${f} (v${other_v} > v${VERSION})"
        found_newer=1
    fi
done
if [[ "$found_newer" -eq 0 ]]; then
    ok "no RELEASE_NOTES_v*.md outranks v${VERSION}"
fi

# ---------------------------------------------------------------------
section "5. build_pkg.sh still reads pyproject.toml as the version source of truth"
# ---------------------------------------------------------------------

if [[ ! -r "$BUILD_PKG" ]]; then
    fail "$BUILD_PKG not readable"
else
    ok "$BUILD_PKG readable"
fi

# Look for the inline python3 snippet that has been the SSOT reader since
# PR #110 (v1.0.2). The exact phrase to anchor on is `BUILD_VERSION=`
# combined with `pyproject.toml` on the same step.
if grep -nE 'BUILD_VERSION=' "$BUILD_PKG" >/dev/null; then
    ok "BUILD_VERSION assignment present in $BUILD_PKG"
else
    fail "BUILD_VERSION assignment missing from $BUILD_PKG (regression)"
fi

if grep -nE "open\(['\"]pyproject\.toml['\"]\)" "$BUILD_PKG" >/dev/null; then
    ok "pyproject.toml read present in $BUILD_PKG"
else
    fail "pyproject.toml read missing from $BUILD_PKG (regression — would unstamp the version)"
fi

# ---------------------------------------------------------------------
echo
echo "Summary: pass=${pass_count} fail=${fail_count}"
if [[ "$fail_count" -gt 0 ]]; then
    exit 1
fi
exit 0
