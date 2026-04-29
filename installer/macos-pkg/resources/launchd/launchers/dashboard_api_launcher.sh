#!/bin/bash
# installer/macos-pkg/resources/launchd/launchers/dashboard_api_launcher.sh
# Bucket 6 — installer rebuild.
#
# Wrapper invoked by com.miningguardian.dashboard-api.plist.
#
# launchd has no EnvironmentFile= equivalent, so this wrapper sources
# /usr/local/MiningGuardian/.env and execs the Python entry point.
#
# Drop at /usr/local/MiningGuardian/bin/dashboard_api_launcher.sh, mode 0755, owner root:wheel.

set -euo pipefail

INSTALL_ROOT="/usr/local/MiningGuardian"
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

cd "${INSTALL_ROOT}"
exec "${VENV_PYTHON}" -u "${ENTRY_POINT}"
