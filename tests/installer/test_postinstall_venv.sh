#!/usr/bin/env bash
# tests/installer/test_postinstall_venv.sh
#
# D-18 Gap 5 — postinstall.sh + build_pkg.sh static checks.
#
# This test asserts that the venv-create step is wired up correctly in
# the .pkg installer pipeline. It runs against the source tree only —
# no Mac, no Installer.app, no actual pip install. The full smoke test
# is the v1.0.3 verification gate per D-18 ("clean macOS 14 VM").
#
# Run from repo root:
#     bash tests/installer/test_postinstall_venv.sh
#
# Exits 0 on success, non-zero on first failed assertion.
# Requires: bash, shellcheck, grep.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

POSTINSTALL="installer/macos-pkg/scripts/postinstall.sh"
BUILD_PKG="installer/macos-pkg/scripts/build_pkg.sh"
PAYLOAD_REQ="installer/macos-pkg/payload-requirements.txt"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }

section() { echo; echo "## $*"; }

# ---------------------------------------------------------------------
section "1. Files exist"
# ---------------------------------------------------------------------
for f in "$POSTINSTALL" "$BUILD_PKG" "$PAYLOAD_REQ"; do
    if [[ -r "$f" ]]; then
        ok "$f present"
    else
        fail "$f missing"
    fi
done

# ---------------------------------------------------------------------
section "2. bash -n syntax check (no syntax errors)"
# ---------------------------------------------------------------------
if bash -n "$POSTINSTALL" 2>/dev/null; then
    ok "postinstall.sh parses"
else
    fail "postinstall.sh has bash syntax errors"
fi
if bash -n "$BUILD_PKG" 2>/dev/null; then
    ok "build_pkg.sh parses"
else
    fail "build_pkg.sh has bash syntax errors"
fi

# ---------------------------------------------------------------------
section "3. shellcheck regression baseline (no NEW warnings)"
# ---------------------------------------------------------------------
# The pre-existing baseline is documented in the PR that added Gap 5
# (count-based regression check; if a future PR introduces new
# warnings the count goes up and this assertion fires).
#
#   postinstall.sh baseline:  3 distinct warnings  (SC2034 line 98,
#                             SC2024 line 272 [info], SC2024 line 542 [warn])
#   build_pkg.sh   baseline:  5 distinct warnings  (SC2155 line 61,
#                             4× SC2295 in step_4b)
if command -v shellcheck >/dev/null 2>&1; then
    pi_count="$(shellcheck "$POSTINSTALL" 2>&1 | /usr/bin/grep -cE '^In .* line [0-9]+:' || true)"
    bp_count="$(shellcheck "$BUILD_PKG"   2>&1 | /usr/bin/grep -cE '^In .* line [0-9]+:' || true)"
    if [[ "$pi_count" -le 3 ]]; then
        ok "postinstall.sh shellcheck warnings: ${pi_count} (≤ 3 baseline)"
    else
        fail "postinstall.sh shellcheck warnings: ${pi_count} (> 3 baseline — new warning introduced)"
    fi
    if [[ "$bp_count" -le 5 ]]; then
        ok "build_pkg.sh shellcheck warnings: ${bp_count} (≤ 5 baseline)"
    else
        fail "build_pkg.sh shellcheck warnings: ${bp_count} (> 5 baseline — new warning introduced)"
    fi
else
    echo "  SKIP — shellcheck not installed (install: \`brew install shellcheck\` or \`apt-get install shellcheck\`)"
fi

# ---------------------------------------------------------------------
section "4. step_create_venv defined and wired in"
# ---------------------------------------------------------------------
if /usr/bin/grep -q '^step_create_venv()' "$POSTINSTALL"; then
    ok "step_create_venv() defined"
else
    fail "step_create_venv() missing — D-18 Gap 5 not implemented"
fi

# main() must call step_create_venv after step_install_launcher_wrappers
# and before step_install_plists_and_bootstrap so launchd services see
# the venv on first start.
if /usr/bin/grep -nE '^[[:space:]]+step_(create_venv|install_launcher_wrappers|install_plists_and_bootstrap)' "$POSTINSTALL" \
        | /usr/bin/awk -F: '/main/{n=NR} END{exit 0}' >/dev/null; then
    # Extract just the call order inside main()
    call_order="$(/usr/bin/awk '/^main\(\)/, /^}/' "$POSTINSTALL" \
        | /usr/bin/grep -oE 'step_(install_launcher_wrappers|create_venv|install_plists_and_bootstrap)' \
        | /usr/bin/paste -sd, -)"
    expected="step_install_launcher_wrappers,step_create_venv,step_install_plists_and_bootstrap"
    if [[ "$call_order" == "$expected" ]]; then
        ok "main() ordering: launchers → create_venv → plists_and_bootstrap"
    else
        fail "main() ordering wrong (got '$call_order', expected '$expected')"
    fi
fi

# ---------------------------------------------------------------------
section "5. Offline guarantees"
# ---------------------------------------------------------------------
# pip install must use --no-index AND --find-links, otherwise it can
# fall through to PyPI on networked hosts.
if /usr/bin/grep -q -- '--no-index' "$POSTINSTALL" \
        && /usr/bin/grep -q -- '--find-links' "$POSTINSTALL"; then
    ok "pip --no-index --find-links present (offline guarantee)"
else
    fail "pip install in postinstall is missing --no-index or --find-links — Vision Anchor 7 violated"
fi

# --only-binary=:all: prevents falling back to building from sdist
if /usr/bin/grep -q -- '--only-binary=:all:' "$POSTINSTALL"; then
    ok "--only-binary=:all: present (no source builds)"
else
    fail "--only-binary=:all: missing — pip could try to build from sdist (no compiler on Mini)"
fi

# Empty-wheels-dir guard
if /usr/bin/grep -q "no .whl files found" "$POSTINSTALL"; then
    ok "empty-wheels-dir guard present"
else
    fail "empty-wheels-dir guard missing — pip would silently fall through to PyPI"
fi

# ---------------------------------------------------------------------
section "6. Exit code 38 for venv failures"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE '^#[[:space:]]+38[[:space:]]+—' "$POSTINSTALL"; then
    ok "exit code 38 documented in header"
else
    fail "exit code 38 not documented in postinstall header"
fi
if /usr/bin/grep -qE 'fail 38 "' "$POSTINSTALL"; then
    ok "fail 38 used in step_create_venv"
else
    fail "fail 38 not used — Gap 5 errors will report wrong exit code"
fi

# ---------------------------------------------------------------------
section "7. build_pkg.sh stages wheels + requirements.txt into payload"
# ---------------------------------------------------------------------
if /usr/bin/grep -q 'python-wheels' "$BUILD_PKG"; then
    ok "build_pkg.sh references python-wheels/"
else
    fail "build_pkg.sh does not stage python-wheels/ — Gap 5 partial"
fi
if /usr/bin/grep -q 'payload-requirements.txt' "$BUILD_PKG"; then
    ok "build_pkg.sh references payload-requirements.txt"
else
    fail "build_pkg.sh does not copy payload-requirements.txt — Gap 5 partial"
fi

# ---------------------------------------------------------------------
section "8. payload-requirements.txt sanity"
# ---------------------------------------------------------------------
# Must contain a non-trivial set of pinned packages, no obvious typos.
non_comment_lines="$(/usr/bin/grep -cvE '^[[:space:]]*(#|$)' "$PAYLOAD_REQ" || true)"
if [[ "$non_comment_lines" -ge 30 ]]; then
    ok "payload-requirements.txt has $non_comment_lines requirement lines (≥ 30)"
else
    fail "payload-requirements.txt has only $non_comment_lines lines — too thin to be the full closure"
fi

# Spot-check key packages are present.
for pkg in fastapi psycopg2-binary slack-sdk anthropic ollama jinja2 prometheus-client; do
    if /usr/bin/grep -qE "^${pkg}([><=!~ ]|$)" "$PAYLOAD_REQ"; then
        ok "payload-requirements.txt pins '${pkg}'"
    else
        fail "payload-requirements.txt missing '${pkg}' — drift vs setup.sh phase_06_repo_venv"
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
