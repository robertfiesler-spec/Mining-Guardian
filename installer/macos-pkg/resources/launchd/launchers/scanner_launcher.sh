#!/bin/bash
# installer/macos-pkg/resources/launchd/launchers/scanner_launcher.sh
# Bucket 6 — installer rebuild.
#
# Wrapper invoked by com.miningguardian.scanner.plist.
#
# Why this wrapper exists
# -----------------------
# launchd does NOT read .env files natively (unlike systemd's
# EnvironmentFile= directive). The scanner needs AMS_*, SLACK_*, MG_DB_*
# in its environment. Rather than hard-code secrets into the plist
# (which sits in /Library/LaunchDaemons/ world-readable), we source the
# .env file here and exec python with the inherited env.
#
# Installer responsibilities (installer/macos-pkg/scripts/postinstall.sh):
#   1. Drop this script at /Library/Application Support/MiningGuardian/bin/scanner_launcher.sh
#      with mode 0755, owner root:wheel.
#   2. Drop /Library/Application Support/MiningGuardian/.env with mode 0600, owner root:wheel.
#   3. Drop the plist at /Library/LaunchDaemons/com.miningguardian.scanner.plist
#      with mode 0644, owner root:wheel.
#   4. mkdir -p /Library/Application Support/MiningGuardian/logs
#   5. launchctl bootstrap system /Library/LaunchDaemons/com.miningguardian.scanner.plist

set -euo pipefail

INSTALL_ROOT="/Library/Application Support/MiningGuardian"
ENV_FILE="${INSTALL_ROOT}/.env"
VENV_PYTHON="${INSTALL_ROOT}/venv/bin/python"
ENTRY_POINT="${INSTALL_ROOT}/core/mining_guardian.py"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "[scanner_launcher] FATAL: ${ENV_FILE} not found" >&2
    exit 1
fi

if [[ ! -x "${VENV_PYTHON}" ]]; then
    echo "[scanner_launcher] FATAL: ${VENV_PYTHON} missing or not executable" >&2
    exit 1
fi

if [[ ! -f "${ENTRY_POINT}" ]]; then
    echo "[scanner_launcher] FATAL: ${ENTRY_POINT} not found" >&2
    exit 1
fi

# Source .env. We want every KEY=VALUE in there exported into the env.
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

# P-028 (2026-05-06) — export MG_INSTALL_ROOT so the scanner's
# _resolve_log_dir() lands on ${INSTALL_ROOT}/logs/ regardless of what
# CWD launchd hands us. The cd below is the belt; this env var is the
# suspenders for any future caller that does not cd first.
export MG_INSTALL_ROOT="${INSTALL_ROOT}"

cd "${INSTALL_ROOT}"
exec "${VENV_PYTHON}" -u "${ENTRY_POINT}"
