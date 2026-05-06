#!/bin/bash
# installer/macos-pkg/resources/launchd/launchers/console_launcher.sh
# D-19 / P-006 — v1.0.3 (10th LaunchDaemon)
#
# Wrapper invoked by com.miningguardian.console.plist.
#
# launchd has no EnvironmentFile= equivalent, so this wrapper sources
# /Library/Application Support/MiningGuardian/.env and execs the Python
# entrypoint via `python -m console.main`. The console binds to
# 127.0.0.1:8787 (D-19 originally requested 8686 but that port is owned
# by the approval API — see docs/CONSOLE_OPERATIONS_GUIDE.md).
#
# Drop at /Library/Application Support/MiningGuardian/bin/console_launcher.sh,
# mode 0755, owner root:wheel.

set -euo pipefail

INSTALL_ROOT="/Library/Application Support/MiningGuardian"
ENV_FILE="${INSTALL_ROOT}/.env"
VENV_PYTHON="${INSTALL_ROOT}/venv/bin/python"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "[console_launcher] FATAL: ${ENV_FILE} not found" >&2
    exit 1
fi

if [[ ! -x "${VENV_PYTHON}" ]]; then
    echo "[console_launcher] FATAL: ${VENV_PYTHON} missing or not executable" >&2
    exit 1
fi

if [[ ! -d "${INSTALL_ROOT}/console" ]]; then
    echo "[console_launcher] FATAL: ${INSTALL_ROOT}/console not found" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

# Hard-bind to 127.0.0.1:8787; main.py reads MG_CONSOLE_PORT only.
export MG_CONSOLE_PORT="${MG_CONSOLE_PORT:-8787}"
export PYTHONPATH="${INSTALL_ROOT}:${PYTHONPATH:-}"
# P-028 (2026-05-06) — see scanner_launcher.sh for rationale.
export MG_INSTALL_ROOT="${INSTALL_ROOT}"

cd "${INSTALL_ROOT}"
exec "${VENV_PYTHON}" -u -m console.main
