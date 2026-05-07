#!/usr/bin/env bash
# tests/installer/test_p024_payload_scripts_allowlist.sh
#
# P-024 — installer/macos-pkg/scripts/build_pkg.sh step 4a rsync filter
# must ship ONLY the scripts the customer Mac Mini actually invokes.
#
# Background. Pre-P-024 the rsync filter used `--include 'scripts/***'`,
# which copied the entire `scripts/` tree into the customer payload. That
# included operator-only / dead-code files that referenced Bobby's Mac
# (BigBobby username, /Volumes/Big-Bobby-T9, 100.103.185.53 tailscale IP)
# and the retired Hostinger VPS (187.124.247.182). None are reachable
# from any plist or launcher; they would never run on the Mini, but they
# would land in the payload and be visible to anyone who unpacked the
# .pkg. P-024 narrowed the rsync to a per-file allowlist matching exactly
# the entrypoints invoked by scheduled-job plists / launchers. This test
# locks that allowlist in.
#
# This test:
#   1. Verifies build_pkg.sh parses (bash -n).
#   2. Statically asserts that build_pkg.sh's filter block contains the
#      7 allowed scripts AND the four `--exclude` markers that must be
#      absent (per-file include-then-catch-all-exclude pattern).
#   3. Runtime: replays the same filter against the working tree into a
#      temporary directory and asserts:
#        * the 7 allowed files (6 scheduled scripts + __init__.py) ARE
#          present under <tmp>/scripts/
#        * the four forbidden operator/dead scripts (backup_db.sh,
#          backup_mining_guardian.sh, start_guardian.sh, setup.sh) are
#          NOT present
#        * no shipped scripts/* file contains a Bobby-Mac contamination
#          string (BigBobby, MAC_USER, MAC_HOST, 100.103.185.53, scp )
#
# Run from repo root:
#     bash tests/installer/test_p024_payload_scripts_allowlist.sh
#
# Exits 0 on success, non-zero on first failed assertion.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

BUILD_PKG="installer/macos-pkg/scripts/build_pkg.sh"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }

section() { echo; echo "## $*"; }

# ---------------------------------------------------------------------
section "1. build_pkg.sh parses"
# ---------------------------------------------------------------------
if bash -n "$BUILD_PKG" 2>/dev/null; then
    ok "build_pkg.sh parses (bash -n)"
else
    fail "build_pkg.sh has bash syntax errors"
fi

# ---------------------------------------------------------------------
section "2. Filter block contains the per-file allowlist"
# ---------------------------------------------------------------------
ALLOWED_SCRIPTS=(
    "scripts/__init__.py"
    "scripts/cleanup_ams_logs.py"
    "scripts/db_maintenance.sh"
    "scripts/direct_collect_logs.py"
    "scripts/daily_log_failure_report.py"
    "scripts/morning_briefing.py"
    "scripts/daily_operator_review.py"
)
for s in "${ALLOWED_SCRIPTS[@]}"; do
    if /usr/bin/grep -qF -- "--include '${s}'" "$BUILD_PKG"; then
        ok "build_pkg.sh includes '${s}'"
    else
        fail "build_pkg.sh missing --include for '${s}'"
    fi
done

# The catch-all `--exclude 'scripts/*'` must follow the includes so
# anything not on the allowlist drops out of the payload.
if /usr/bin/grep -qF -- "--exclude 'scripts/*'" "$BUILD_PKG"; then
    ok "build_pkg.sh has catch-all --exclude 'scripts/*'"
else
    fail "build_pkg.sh missing catch-all --exclude 'scripts/*'"
fi

# The pre-P-024 broad include would re-allow everything in scripts/.
# Make sure it is gone.
if /usr/bin/grep -qF -- "--include 'scripts/***'" "$BUILD_PKG"; then
    fail "build_pkg.sh still has the pre-P-024 broad --include 'scripts/***' (this re-ships operator-only / dead scripts)"
else
    ok "build_pkg.sh no longer has --include 'scripts/***'"
fi

# `branding/***` must be anchored so it cannot match `scripts/branding/`.
if /usr/bin/grep -qF -- "--include '/branding/***'" "$BUILD_PKG"; then
    ok "build_pkg.sh anchors top-level branding include"
else
    fail "build_pkg.sh has unanchored 'branding/***' — this lets scripts/branding/ slip into the payload"
fi

# ---------------------------------------------------------------------
section "3. Runtime: replay rsync filter and assert payload shape"
# ---------------------------------------------------------------------
# Mirror the exact rsync filter from build_pkg.sh step 4a. Keep this
# block in sync with the build script — the assertions below only catch
# regressions if the filter under test is the one that actually ships.
TMPDIR_PAYLOAD="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_PAYLOAD"' EXIT

if /usr/bin/rsync -a --delete \
    --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
    --exclude 'build' --exclude 'venv' --exclude '.venv' \
    --include 'pyproject.toml' \
    --include 'predictor.py' \
    --include 'requirements.txt' \
    --include 'core/***' \
    --include 'clients/***' \
    --include 'notifiers/***' \
    --include 'monitoring/***' \
    --include 'api/***' \
    --include 'ai/***' \
    --include 'console/***' \
    --include 'intelligence-catalog/***' \
    --include 'docs/***' \
    --include '/branding/***' \
    --include 'deploy/***' \
    --include 'migrations/***' \
    --include 'scripts/' \
    --include 'scripts/__init__.py' \
    --include 'scripts/cleanup_ams_logs.py' \
    --include 'scripts/db_maintenance.sh' \
    --include 'scripts/direct_collect_logs.py' \
    --include 'scripts/daily_log_failure_report.py' \
    --include 'scripts/morning_briefing.py' \
    --include 'scripts/daily_operator_review.py' \
    --exclude 'scripts/*' \
    --include 'config/***' \
    --exclude '*' \
    "${REPO_ROOT}/" "${TMPDIR_PAYLOAD}/" >/dev/null 2>&1; then
    ok "rsync replay produced a payload"
else
    fail "rsync replay failed (rsync not present, or filter syntax broke)"
fi

# 3a. Each allowed script must be present in the replayed payload.
for s in "${ALLOWED_SCRIPTS[@]}"; do
    if [[ -f "${TMPDIR_PAYLOAD}/${s}" ]]; then
        ok "payload contains '${s}'"
    else
        fail "payload missing '${s}' — scheduled jobs would fail"
    fi
done

# 3b. Each forbidden script must NOT be in the replayed payload.
FORBIDDEN_SCRIPTS=(
    "scripts/backup_db.sh"
    "scripts/backup_mining_guardian.sh"
    "scripts/start_guardian.sh"
    "scripts/setup.sh"
)
for s in "${FORBIDDEN_SCRIPTS[@]}"; do
    if [[ -e "${TMPDIR_PAYLOAD}/${s}" ]]; then
        fail "payload contains operator-only / dead script '${s}' — must not ship"
    else
        ok "payload excludes '${s}'"
    fi
done

# 3c. Operator-only subdirectories must NOT be in the replayed payload.
FORBIDDEN_SUBDIRS=(
    "scripts/branding"
    "scripts/diagnostics"
)
for d in "${FORBIDDEN_SUBDIRS[@]}"; do
    if [[ -e "${TMPDIR_PAYLOAD}/${d}" ]]; then
        fail "payload contains operator-only subdir '${d}/' — must not ship"
    else
        ok "payload excludes '${d}/'"
    fi
done

# 3d. No shipped scripts/* file may contain Bobby-Mac contamination.
# The retired-host hardening (P-018E + P-019A + P-023) handles the IPs
# 100.110.87.1 / 187.124.247.182. P-024 adds Bobby-Mac strings that the
# previous shipped operator scripts contained.
CONTAM_PATTERNS=(
    'BigBobby'
    'MAC_USER='
    'MAC_HOST='
    '100\.103\.185\.53'
    '\bscp '
)
contam_failures=0
for pat in "${CONTAM_PATTERNS[@]}"; do
    hits=$(/usr/bin/grep -rEn "${pat}" "${TMPDIR_PAYLOAD}/scripts/" 2>/dev/null || true)
    if [[ -n "${hits}" ]]; then
        fail "payload scripts contain forbidden pattern /${pat}/:"
        echo "${hits}" | sed 's|^|      |'
        contam_failures=$((contam_failures + 1))
    fi
done
if (( contam_failures == 0 )); then
    ok "payload scripts/ has no Bobby-Mac contamination"
fi

# ---------------------------------------------------------------------
section "Summary"
# ---------------------------------------------------------------------
echo "  passed: ${pass_count}"
echo "  failed: ${fail_count}"

if (( fail_count > 0 )); then
    exit 1
fi
exit 0
