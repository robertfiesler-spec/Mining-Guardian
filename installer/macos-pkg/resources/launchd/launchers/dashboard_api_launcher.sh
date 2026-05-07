#!/bin/bash
# installer/macos-pkg/resources/launchd/launchers/dashboard_api_launcher.sh
# Bucket 6 — installer rebuild.
#
# Wrapper invoked by com.miningguardian.dashboard-api.plist.
#
# launchd has no EnvironmentFile= equivalent, so this wrapper sources
# /Library/Application Support/MiningGuardian/.env and execs the Python entry point.
#
# Drop at /Library/Application Support/MiningGuardian/bin/dashboard_api_launcher.sh, mode 0755, owner root:wheel.

set -euo pipefail

INSTALL_ROOT="/Library/Application Support/MiningGuardian"
ENV_FILE="${INSTALL_ROOT}/.env"
VENV_PYTHON="${INSTALL_ROOT}/venv/bin/python"
ENTRY_POINT="${INSTALL_ROOT}/api/dashboard_api.py"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "[dashboard_api_launcher] FATAL: ${ENV_FILE} not found" >&2
    exit 1
fi

if [[ ! -x "${VENV_PYTHON}" ]]; then
    echo "[dashboard_api_launcher] FATAL: ${VENV_PYTHON} missing or not executable" >&2
    exit 1
fi

if [[ ! -f "${ENTRY_POINT}" ]]; then
    echo "[dashboard_api_launcher] FATAL: ${ENTRY_POINT} not found" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

# P-028 (2026-05-06) — export MG_INSTALL_ROOT so any module that uses
# core.mining_guardian._resolve_log_dir() picks the correct absolute
# logs path. See scanner_launcher.sh for the canonical comment.
export MG_INSTALL_ROOT="${INSTALL_ROOT}"

# P-019D (2026-05-07) — preflight before exec.
# This service binds 127.0.0.1:8585 and opens psycopg2 in /health and
# /query/* handlers. Both are common silent-exit failure modes under
# launchd: a stale uvicorn from a prior install holds 8585 (uvicorn
# exits ~immediately on OSError, launchd refuses respawn with errno 5),
# or MG_DB_PASSWORD drifts from the actual mg role and psycopg2 raises
# OperationalError on first request. We check both before exec and emit
# loud, codeable diagnostics to stderr (captured by launchd's
# StandardErrorPath, dumped by postinstall in P-019D step 3).
# shellcheck source=_preflight.sh
source "${INSTALL_ROOT}/bin/_preflight.sh"
_preflight_env_keys "dashboard_api" "${ENV_FILE}" \
    MG_DB_PASSWORD || exit $?
_preflight_port_free "dashboard_api" 8585 || exit $?
_preflight_db_ping "dashboard_api" "${VENV_PYTHON}" || exit $?

cd "${INSTALL_ROOT}"
exec "${VENV_PYTHON}" -u "${ENTRY_POINT}"
