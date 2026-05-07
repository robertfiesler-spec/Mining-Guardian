#!/bin/bash
# installer/macos-pkg/resources/launchd/launchers/intelligence_report_launcher.sh
# Bucket 6 — installer rebuild.
#
# Wrapper invoked by com.miningguardian.intelligence-report.plist.
#
# launchd has no EnvironmentFile= equivalent, so this wrapper sources
# /Library/Application Support/MiningGuardian/.env and execs the Python entry point.
#
# Drop at /Library/Application Support/MiningGuardian/bin/intelligence_report_launcher.sh, mode 0755, owner root:wheel.

set -euo pipefail

INSTALL_ROOT="/Library/Application Support/MiningGuardian"
ENV_FILE="${INSTALL_ROOT}/.env"
VENV_PYTHON="${INSTALL_ROOT}/venv/bin/python"
ENTRY_POINT="${INSTALL_ROOT}/api/intelligence_report_api.py"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "[intelligence_report_launcher] FATAL: ${ENV_FILE} not found" >&2
    exit 1
fi

if [[ ! -x "${VENV_PYTHON}" ]]; then
    echo "[intelligence_report_launcher] FATAL: ${VENV_PYTHON} missing or not executable" >&2
    exit 1
fi

if [[ ! -f "${ENTRY_POINT}" ]]; then
    echo "[intelligence_report_launcher] FATAL: ${ENTRY_POINT} not found" >&2
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

# P-019D (2026-05-07) — preflight before exec. Intelligence report API
# binds INTEL_REPORT_API_BIND:INTEL_REPORT_API_PORT (default
# 127.0.0.1:8590) and reads the catalog DB. Same shape as
# dashboard_api_launcher.
INTEL_PORT="${INTEL_REPORT_API_PORT:-8590}"
# shellcheck source=_preflight.sh
source "${INSTALL_ROOT}/bin/_preflight.sh"
_preflight_env_keys "intelligence_report" "${ENV_FILE}" \
    MG_DB_PASSWORD || exit $?
_preflight_port_free "intelligence_report" "${INTEL_PORT}" || exit $?
_preflight_db_ping "intelligence_report" "${VENV_PYTHON}" || exit $?

cd "${INSTALL_ROOT}"
exec "${VENV_PYTHON}" -u "${ENTRY_POINT}"
