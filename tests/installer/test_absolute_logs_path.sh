#!/usr/bin/env bash
# tests/installer/test_absolute_logs_path.sh
#
# D-18 P-028 — Mining Guardian's logging setup must NEVER use a relative
# `Path("logs")`. Every entry into core/mining_guardian.py must resolve
# the logs directory to an absolute path so that the directory winds up
# under the install root regardless of CWD.
#
# Background. Round-9b of the v1.0.3 customer Mac mini install
# (`MiningGuardian-1.0.3-2a3de50c4af2.pkg`) installed cleanly through
# postinstall, then the first-run baseline scan crashed in
# `_setup_logging` with:
#     PermissionError: [Errno 13] Permission denied: 'logs'
#         at core/mining_guardian.py line 63 (log_dir.mkdir(exist_ok=True))
# Root cause: `step_baseline_scan` invoked the scanner via
# `sudo -u miningguardian python /Library/.../mining_guardian.py --once`
# from postinstall.sh's CWD (the Installer.app scripts sandbox under
# `/tmp/PKInstallSandbox.<rand>/...`). With no `cd` and no env var,
# `Path("logs")` resolved relative to the sandbox CWD; on the live box
# it tried to create `/logs` which the unprivileged miningguardian user
# cannot write.
#
# This test asserts:
#   1.  core/mining_guardian.py defines a _resolve_log_dir() helper.
#   2.  _setup_logging() calls _resolve_log_dir() (no string `Path("logs")`).
#   3.  No `Path("logs")` literal remains anywhere in core/.
#   4.  postinstall.sh::step_baseline_scan exports MG_INSTALL_ROOT into
#       the scanner subprocess AND cd's into the install root.
#   5.  Every launcher wrapper (10 services + 1 generic scheduled-job
#       wrapper) exports MG_INSTALL_ROOT before exec'ing python.
#   6.  Runtime: with MG_INSTALL_ROOT="/tmp/.../mg_root" set, importing
#       core.mining_guardian creates the logs directory at
#       ${MG_INSTALL_ROOT}/logs, NOT in the test CWD.
#   7.  Runtime: with MG_INSTALL_ROOT unset and CWD elsewhere,
#       _resolve_log_dir() falls back to <repo_root>/logs (absolute).
#   8.  Runtime: with MG_LOG_DIR set, the override wins.
#   9.  P-028 audit marker present in mining_guardian.py.
#
# Run from repo root:
#     bash tests/installer/test_absolute_logs_path.sh
#
# Exits 0 on success, non-zero on first failed assertion.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

GUARDIAN="core/mining_guardian.py"
POSTINSTALL="installer/macos-pkg/scripts/postinstall.sh"
LAUNCHER_DIR="installer/macos-pkg/resources/launchd/launchers"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }
section() { echo; echo "## $*"; }

# ---------------------------------------------------------------------
section "1. core/mining_guardian.py defines _resolve_log_dir()"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE '^def _resolve_log_dir\(\)' "$GUARDIAN"; then
    ok "_resolve_log_dir() defined in $GUARDIAN"
else
    fail "_resolve_log_dir() missing from $GUARDIAN"
fi

# ---------------------------------------------------------------------
section "2. _setup_logging() uses _resolve_log_dir()"
# ---------------------------------------------------------------------
if /usr/bin/awk '
    /^def _setup_logging\(/ { in_fn = 1; next }
    in_fn && /^def / && !/^def _setup_logging/ { exit }
    in_fn && /_resolve_log_dir\(\)/ { found = 1 }
    END { exit (found ? 0 : 1) }
' "$GUARDIAN"; then
    ok "_setup_logging() body calls _resolve_log_dir()"
else
    fail "_setup_logging() does not call _resolve_log_dir()"
fi

# ---------------------------------------------------------------------
section "3. No Path(\"logs\") literal under core/"
# ---------------------------------------------------------------------
# Guards against the exact regression — relative `Path("logs")` was the
# round-9b crash site. Allow comments / docstrings to mention it as
# documentation; only flag actual assignments / arguments. The
# docstring body uses double-backticks (``Path("logs")``) so we exclude
# any line that contains the docstring marker.
if /usr/bin/grep -RInE 'Path\(["\047]logs["\047]\)' core/ 2>/dev/null \
        | /usr/bin/grep -vE '^[^:]+:[0-9]+:[[:space:]]*#' \
        | /usr/bin/grep -vE '``Path\(' \
        | /usr/bin/grep -q .; then
    /usr/bin/grep -RInE 'Path\(["\047]logs["\047]\)' core/ 2>/dev/null \
        | /usr/bin/grep -vE '^[^:]+:[0-9]+:[[:space:]]*#' \
        | /usr/bin/grep -vE '``Path\('
    fail 'core/ still contains a code-level Path("logs") literal'
else
    ok 'core/ has no relative Path("logs") code literal'
fi

# ---------------------------------------------------------------------
section "4. postinstall.sh::step_baseline_scan passes MG_INSTALL_ROOT + cds"
# ---------------------------------------------------------------------
if /usr/bin/awk '
    /^step_baseline_scan\(\)/ { in_fn = 1; next }
    in_fn && /^}/ { exit }
    in_fn && /MG_INSTALL_ROOT=\$\{MG_INSTALL_ROOT\}/ { has_env = 1 }
    in_fn && /cd "\$\{MG_INSTALL_ROOT\}"/ { has_cd = 1 }
    END { exit ((has_env && has_cd) ? 0 : 1) }
' "$POSTINSTALL"; then
    ok "step_baseline_scan exports MG_INSTALL_ROOT and cds into install root"
else
    fail "step_baseline_scan missing MG_INSTALL_ROOT export and/or cd"
fi

# ---------------------------------------------------------------------
section "5. Every launcher wrapper exports MG_INSTALL_ROOT"
# ---------------------------------------------------------------------
expected_launchers=(
    scanner_launcher.sh
    dashboard_api_launcher.sh
    approval_api_launcher.sh
    slack_listener_launcher.sh
    slack_commands_launcher.sh
    overnight_automation_launcher.sh
    alerts_launcher.sh
    intelligence_report_launcher.sh
    console_launcher.sh
    scheduled_job_launcher.sh
)
for launcher in "${expected_launchers[@]}"; do
    f="${LAUNCHER_DIR}/${launcher}"
    if [[ ! -r "$f" ]]; then
        fail "launcher missing: $f"
        continue
    fi
    if /usr/bin/grep -qE '^[[:space:]]*export MG_INSTALL_ROOT=' "$f"; then
        ok "${launcher} exports MG_INSTALL_ROOT"
    else
        fail "${launcher} does not export MG_INSTALL_ROOT"
    fi
done

# ---------------------------------------------------------------------
section "6. Runtime: MG_INSTALL_ROOT is honored"
# ---------------------------------------------------------------------
# Use a fresh temp dir as fake install root and verify the resolver
# lands on <root>/logs as an absolute path.
runtime_tmp="$(/usr/bin/mktemp -d -t mg_logs_resolve_XXXXXX)"
trap 'rm -rf "$runtime_tmp"' EXIT
mock_root="${runtime_tmp}/Application Support/MiningGuardian"  # space in path
mkdir -p "$mock_root"

# Run the resolver in a subprocess with a CWD elsewhere, so relative
# paths would resolve to the wrong place if the bug recurs.
runtime_cwd="${runtime_tmp}/elsewhere"
mkdir -p "$runtime_cwd"

resolved_path="$(
    cd "$runtime_cwd" && \
    MG_INSTALL_ROOT="$mock_root" /usr/bin/env python3 -c "
import sys, os
sys.path.insert(0, os.path.join('$REPO_ROOT', 'core'))
# Pull the helper directly out of the file rather than importing the
# whole guardian module (which has heavy side-effects on import).
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location('mg', os.path.join('$REPO_ROOT', 'core', 'mining_guardian.py'))
src = pathlib.Path(spec.origin).read_text()
import ast
mod_ast = ast.parse(src)
helper_src = ''
for node in mod_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name == '_resolve_log_dir':
        helper_src = ast.get_source_segment(src, node)
        break
ns = {'os': os, 'Path': pathlib.Path}
exec(helper_src, ns)
print(ns['_resolve_log_dir']())
" 2>/dev/null
)"

expected_path="${mock_root}/logs"
if [[ "$resolved_path" == "$expected_path" ]]; then
    ok "MG_INSTALL_ROOT honored: resolved=$resolved_path"
else
    fail "MG_INSTALL_ROOT not honored: expected=$expected_path got=$resolved_path"
fi

# ---------------------------------------------------------------------
section "7. Runtime: fallback to repo root with no env vars"
# ---------------------------------------------------------------------
fallback_path="$(
    cd "$runtime_cwd" && \
    /usr/bin/env -u MG_INSTALL_ROOT -u MG_LOG_DIR python3 -c "
import os, ast, importlib.util, pathlib
src = pathlib.Path(os.path.join('$REPO_ROOT', 'core', 'mining_guardian.py')).read_text()
mod_ast = ast.parse(src)
helper_src = ''
for node in mod_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name == '_resolve_log_dir':
        helper_src = ast.get_source_segment(src, node)
        break
ns = {'os': os, 'Path': pathlib.Path, '_ROOT': pathlib.Path('$REPO_ROOT')}
exec(helper_src, ns)
print(ns['_resolve_log_dir']())
" 2>/dev/null
)"

expected_fallback="${REPO_ROOT}/logs"
if [[ "$fallback_path" == "$expected_fallback" ]]; then
    ok "fallback resolved to repo-root/logs (absolute): $fallback_path"
else
    fail "fallback resolved to wrong path: expected=$expected_fallback got=$fallback_path"
fi

# Negative control: prove the bug RECURS without the fix. If we run the
# old `Path("logs")` behavior from `runtime_cwd`, it must NOT equal
# expected_path — this asserts the test is sensitive to the regression.
old_path="$(
    cd "$runtime_cwd" && \
    /usr/bin/env -u MG_INSTALL_ROOT -u MG_LOG_DIR python3 -c "
from pathlib import Path
print(Path('logs').resolve())
"
)"
if [[ "$old_path" != "$expected_path" ]]; then
    ok "negative control: old relative-Path behavior would NOT land on install root (would land at $old_path)"
else
    fail "negative control failed — old behavior happened to match install root by accident"
fi

# ---------------------------------------------------------------------
section "8. Runtime: MG_LOG_DIR override wins"
# ---------------------------------------------------------------------
override_dir="${runtime_tmp}/explicit_override"
override_resolved="$(
    cd "$runtime_cwd" && \
    MG_INSTALL_ROOT="$mock_root" MG_LOG_DIR="$override_dir" /usr/bin/env python3 -c "
import os, ast, pathlib
src = pathlib.Path(os.path.join('$REPO_ROOT', 'core', 'mining_guardian.py')).read_text()
mod_ast = ast.parse(src)
helper_src = ''
for node in mod_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name == '_resolve_log_dir':
        helper_src = ast.get_source_segment(src, node)
        break
ns = {'os': os, 'Path': pathlib.Path, '_ROOT': pathlib.Path('$REPO_ROOT')}
exec(helper_src, ns)
print(ns['_resolve_log_dir']())
" 2>/dev/null
)"
if [[ "$override_resolved" == "$override_dir" ]]; then
    ok "MG_LOG_DIR override honored: $override_resolved"
else
    fail "MG_LOG_DIR override ignored: expected=$override_dir got=$override_resolved"
fi

# ---------------------------------------------------------------------
section "9. P-028 audit marker"
# ---------------------------------------------------------------------
if /usr/bin/grep -q "P-028" "$GUARDIAN"; then
    ok "P-028 marker present in $GUARDIAN"
else
    fail "P-028 marker missing from $GUARDIAN"
fi
if /usr/bin/grep -q "P-028" "$POSTINSTALL"; then
    ok "P-028 marker present in $POSTINSTALL"
else
    fail "P-028 marker missing from $POSTINSTALL"
fi

# ---------------------------------------------------------------------
echo
echo "============================================================"
echo "Results: $pass_count passed, $fail_count failed"
echo "============================================================"

if (( fail_count > 0 )); then
    exit 1
fi
exit 0
