#!/usr/bin/env bash
# tests/installer/test_postinstall_python_runtime.sh
#
# P-026 (2026-05-05) — installer-owned Python 3.12 runtime regression
# tests.
#
# Background: Round 9 of the Mac mini install (2026-05-05, package
# `MiningGuardian-1.0.3-00720ab71cc4.pkg`) hard-failed in
# postinstall.sh::step_create_venv with `FATAL (38) python3.12 not
# found on this Mac; install Homebrew + python@3.12 before running
# the .pkg`. Operator decision (Rob, 2026-05-05): the .pkg owns its
# own Python 3.12 runtime — customers must not be required to
# install Homebrew or python@3.12 ahead of running the installer.
#
# This test asserts:
#   * `postinstall.sh::step_create_venv` resolves an installer-owned
#     Python 3.12 interpreter at <payload>/runtime/python/ BEFORE any
#     Homebrew / system fallback.
#   * `postinstall.sh` no longer emits the bare-Mac "install Homebrew
#     + python@3.12 before running the .pkg" error string (the legacy
#     hidden-prerequisite path).
#   * `postinstall.sh` validates the resolved interpreter is exactly
#     Python 3.12.x (rejects 3.11/3.13/etc., which the cp312-pinned
#     wheelhouse would not match anyway).
#   * `build_pkg.sh::step_4i_stage_python_runtime` exists, is wired
#     into the build pipeline, and refuses to produce a .pkg whose
#     payload does not carry the runtime.
#   * `build_pkg.sh` exit-code header documents the new step-4i
#     hard-fail path under exit 43.
#   * `docs/RUNBOOK_PKG_REBUILD.md` contains the new "Block Pre-B —
#     populate the Python runtime" section.
#   * `installer/macos-pkg/scripts/postinstall.sh` step_create_venv
#     header docstring no longer references "Homebrew python@3.12"
#     as a customer prerequisite.
#
# Run from repo root:
#     bash tests/installer/test_postinstall_python_runtime.sh
#
# Exits 0 on success, non-zero on first failed assertion.
# Requires: bash, grep.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

POSTINSTALL="installer/macos-pkg/scripts/postinstall.sh"
BUILD_PKG="installer/macos-pkg/scripts/build_pkg.sh"
RUNBOOK="docs/RUNBOOK_PKG_REBUILD.md"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }

section() { echo; echo "## $*"; }

# ---------------------------------------------------------------------
section "1. Files exist"
# ---------------------------------------------------------------------
for f in "$POSTINSTALL" "$BUILD_PKG" "$RUNBOOK"; do
    if [[ -r "$f" ]]; then
        ok "$f present"
    else
        fail "$f missing"
    fi
done

# ---------------------------------------------------------------------
section "2. bash -n syntax"
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
section "3. postinstall — packaged interpreter resolved first"
# ---------------------------------------------------------------------
if /usr/bin/grep -q 'packaged_py_flat=' "$POSTINSTALL"; then
    ok "packaged_py_flat resolver variable present"
else
    fail "packaged_py_flat resolver missing — P-026 regression"
fi
if /usr/bin/grep -q 'packaged_py_framework=' "$POSTINSTALL"; then
    ok "packaged_py_framework resolver variable present"
else
    fail "packaged_py_framework resolver missing — P-026 regression"
fi
if /usr/bin/grep -q '${MG_PKG_PAYLOAD}/runtime/python/bin/python3.12' "$POSTINSTALL"; then
    ok "packaged flat path references \${MG_PKG_PAYLOAD}/runtime/python/bin/python3.12"
else
    fail "packaged flat path does not reference \${MG_PKG_PAYLOAD}/runtime/python/bin/python3.12"
fi

# Tier-1 packaged resolver MUST appear before Tier-2 Homebrew fallback.
# We compare the code-level Homebrew reference (the bash assignment
# inside the for-loop), not docstring mentions in the file header —
# the docstring legitimately mentions `/opt/homebrew/...` while
# explaining what the legacy code did before P-026.
packaged_first_line="$(/usr/bin/grep -n 'packaged_py_flat=' "$POSTINSTALL" | /usr/bin/head -n1 | /usr/bin/cut -d: -f1 || true)"
homebrew_code_line="$(/usr/bin/grep -nE '^[[:space:]]+"/opt/homebrew/opt/python@3.12/bin/python3.12" \\$' "$POSTINSTALL" | /usr/bin/head -n1 | /usr/bin/cut -d: -f1 || true)"
if [[ -n "$packaged_first_line" && -n "$homebrew_code_line" && "$packaged_first_line" -lt "$homebrew_code_line" ]]; then
    ok "packaged resolver precedes Homebrew fallback (packaged @${packaged_first_line} < homebrew @${homebrew_code_line})"
else
    fail "packaged resolver MUST precede Homebrew fallback (packaged='${packaged_first_line}', homebrew='${homebrew_code_line}')"
fi

# ---------------------------------------------------------------------
section "4. postinstall — legacy 'install Homebrew + python@3.12' error string is gone"
# ---------------------------------------------------------------------
# Before P-026 the error told the operator to install Homebrew +
# python@3.12 — that's the hidden-prerequisite path Rob explicitly
# rejected. The new error points at build_pkg.sh step_4i and the
# runbook.
if /usr/bin/grep -qE 'install Homebrew \+ python@3.12 before running the .pkg' "$POSTINSTALL"; then
    fail "postinstall still emits the legacy 'install Homebrew + python@3.12' error — P-026 regression"
else
    ok "postinstall no longer tells customer to install Homebrew + python@3.12"
fi
# The new error string MUST point at build_pkg.sh step_4i and the runbook.
if /usr/bin/grep -qE 'step_4i_stage_python_runtime' "$POSTINSTALL"; then
    ok "new error string points at build_pkg.sh::step_4i_stage_python_runtime"
else
    fail "new error string does not point at step_4i_stage_python_runtime — P-026 incomplete"
fi
if /usr/bin/grep -qE 'RUNBOOK_PKG_REBUILD\.md.*Block Pre-B' "$POSTINSTALL"; then
    ok "new error string points at runbook 'Block Pre-B'"
else
    fail "new error string does not point at runbook 'Block Pre-B' — P-026 incomplete"
fi

# ---------------------------------------------------------------------
section "5. postinstall — Python 3.12 version sanity check"
# ---------------------------------------------------------------------
# A 3.11 or 3.13 interpreter would silently build a venv that pip
# cannot populate from the cp312 wheelhouse. We refuse-to-proceed
# with a clearer error than pip's downstream complaint.
if /usr/bin/grep -qE "import sys; print\(\"%d\.%d\" % sys\.version_info\[:2\]\)" "$POSTINSTALL"; then
    ok "version probe present in postinstall"
else
    fail "version probe missing — postinstall would silently accept 3.11 or 3.13"
fi
if /usr/bin/grep -qE "reports version '\\\$" "$POSTINSTALL" \
        || /usr/bin/grep -qE "reports version '\$\{py_ver\}'" "$POSTINSTALL"; then
    ok "version mismatch error message present"
else
    fail "version mismatch error message missing — P-026 regression"
fi

# ---------------------------------------------------------------------
section "6. build_pkg — step_4i_stage_python_runtime exists and is invoked"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE '^[[:space:]]*# 4i\. Installer-owned Python 3\.12 runtime' "$BUILD_PKG"; then
    ok "step 4i comment block present"
else
    fail "step 4i comment block missing — P-026 regression"
fi
if /usr/bin/grep -qE '_die 43 "step 4i:' "$BUILD_PKG"; then
    ok "step 4i hard-fail (_die 43) present"
else
    fail "step 4i hard-fail missing — P-026 regression"
fi

# Vendor directory contract.
if /usr/bin/grep -q '\${HOME}/MiningGuardian-vendor/python-runtime' "$BUILD_PKG"; then
    ok "step 4i references \${HOME}/MiningGuardian-vendor/python-runtime"
else
    fail "step 4i does not reference \${HOME}/MiningGuardian-vendor/python-runtime — P-026 regression"
fi

# Both accepted layouts (flat + framework) MUST be enumerated.
if /usr/bin/grep -qE 'bin/python3\.12' "$BUILD_PKG" \
        && /usr/bin/grep -qE 'Python\.framework/Versions/3\.12/bin/python3\.12' "$BUILD_PKG"; then
    ok "step 4i accepts both flat and framework layouts"
else
    fail "step 4i does not accept both flat and framework python layouts — P-026 incomplete"
fi

# Mach-O check.
if /usr/bin/grep -qE 'is not a Mach-O binary' "$BUILD_PKG"; then
    ok "step 4i refuses non-Mach-O python (wrong tarball flavor)"
else
    fail "step 4i missing non-Mach-O check — P-026 regression"
fi

# Version check at build time.
if /usr/bin/grep -qE "expected 3\.12 \(vendored wheels are cp312" "$BUILD_PKG"; then
    ok "step 4i refuses non-3.12 python interpreter"
else
    fail "step 4i missing 3.12 version check — P-026 regression"
fi

# venv module check (catches python-build-standalone build/ variant).
if /usr/bin/grep -qE "cannot import the 'venv' module" "$BUILD_PKG"; then
    ok "step 4i refuses python without venv module"
else
    fail "step 4i missing venv module check — P-026 regression"
fi

# Post-rsync sanity check.
if /usr/bin/grep -qE 'staged Python interpreter' "$BUILD_PKG"; then
    ok "step 4i post-rsync sanity check present"
else
    fail "step 4i missing post-rsync sanity check — P-026 regression"
fi

# Runtime / vendor rsync excludes python-runtime/ so step 4i owns it.
if /usr/bin/grep -qE "exclude 'python-runtime/'" "$BUILD_PKG"; then
    ok "bulk runtime rsync excludes python-runtime/"
else
    fail "bulk runtime rsync does NOT exclude python-runtime/ — P-026 regression"
fi

# ---------------------------------------------------------------------
section "7. build_pkg — exit code 43 documentation extended for step 4i"
# ---------------------------------------------------------------------
# The header comment block lists exit codes; step 4i's _die 43 must
# be referenced so future maintainers don't think 43 is only step 4h.
if /usr/bin/awk '
    /^# +Exit codes:/ { in_block=1 }
    in_block && /^# +43/,/^# +4[4-9]/ { print }
    /^set -euo pipefail/ { exit }
' "$BUILD_PKG" | /usr/bin/grep -qE 'P-026|step 4i|installer-owned Python'; then
    ok "exit code 43 documentation references P-026 / step 4i"
else
    fail "exit code 43 docstring not extended for step 4i — P-026 regression"
fi

# ---------------------------------------------------------------------
section "8. RUNBOOK has 'Block Pre-B — populate the Python runtime'"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE 'Block Pre-B' "$RUNBOOK"; then
    ok "RUNBOOK section 'Block Pre-B' present"
else
    fail "RUNBOOK missing 'Block Pre-B' — P-026 docs incomplete"
fi
if /usr/bin/grep -qE 'python-build-standalone' "$RUNBOOK"; then
    ok "RUNBOOK names python-build-standalone as the recommended source"
else
    fail "RUNBOOK does not name python-build-standalone — P-026 docs incomplete"
fi
if /usr/bin/grep -qE '\${HOME}/MiningGuardian-vendor/python-runtime' "$RUNBOOK"; then
    ok "RUNBOOK names the vendor directory"
else
    fail "RUNBOOK does not name the vendor directory — P-026 docs incomplete"
fi

# ---------------------------------------------------------------------
section "9. postinstall step_create_venv header no longer requires Homebrew prereq"
# ---------------------------------------------------------------------
# The "Hard rules" comment block inside step_create_venv must reflect
# the P-026 reality: .pkg now vendors its own Python interpreter.
if /usr/bin/awk '
    /step_create_venv\(\)/      { in_func=1 }
    in_func && /Hard rules:/    { in_rules=1; next }
    in_rules                    { print }
    in_rules && /^[[:space:]]*$/ { exit }
' "$POSTINSTALL" | /usr/bin/grep -qE 'P-026'; then
    ok "step_create_venv 'Hard rules' block updated for P-026"
else
    fail "step_create_venv 'Hard rules' block does not mention P-026 — docstring drift"
fi
# The legacy "Apple-supplied python3 is 3.9 ... assumes Homebrew
# python@3.12" wording explicitly told future maintainers to keep
# the prerequisite as-is; that wording must not survive P-026.
if /usr/bin/grep -qE 'docs the python@3.12 prerequisite' "$POSTINSTALL"; then
    fail "legacy 'docs the python@3.12 prerequisite' comment still in step_create_venv — P-026 regression"
else
    ok "legacy 'docs the python@3.12 prerequisite' comment removed"
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
