#!/bin/bash
# installer/macos-pkg/resources/launchd/launchers/slack_commands_launcher.sh
# Bucket 6 — installer rebuild.
#
# Wrapper invoked by com.miningguardian.slack-commands.plist.
#
# launchd has no EnvironmentFile= equivalent, so this wrapper sources
# /Library/Application Support/MiningGuardian/.env and execs the Python entry point.
#
# Drop at /Library/Application Support/MiningGuardian/bin/slack_commands_launcher.sh, mode 0755, owner root:wheel.

set -euo pipefail

INSTALL_ROOT="/Library/Application Support/MiningGuardian"
ENV_FILE="${INSTALL_ROOT}/.env"
VENV_PYTHON="${INSTALL_ROOT}/venv/bin/python"
ENTRY_POINT="${INSTALL_ROOT}/api/slack_command_handler.py"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "[slack_commands_launcher] FATAL: ${ENV_FILE} not found" >&2
    exit 1
fi

if [[ ! -x "${VENV_PYTHON}" ]]; then
    echo "[slack_commands_launcher] FATAL: ${VENV_PYTHON} missing or not executable" >&2
    exit 1
fi

if [[ ! -f "${ENTRY_POINT}" ]]; then
    echo "[slack_commands_launcher] FATAL: ${ENTRY_POINT} not found" >&2
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

cd "${INSTALL_ROOT}"
exec "${VENV_PYTHON}" -u "${ENTRY_POINT}"
