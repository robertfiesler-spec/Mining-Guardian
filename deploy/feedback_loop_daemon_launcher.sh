#!/bin/bash
# deploy/feedback_loop_daemon_launcher.sh — D-14 PR 4b
#
# Wrapper invoked by com.miningguardian.feedback-loop-daemon.plist.
#
# Why this wrapper exists
# -----------------------
# launchd does NOT read .env files natively (unlike systemd's
# EnvironmentFile= directive). The C5 daemon needs MG_DB_PASSWORD and the
# PG* connection vars in its environment. Rather than hard-code secrets
# into the plist (which sits in /Library/LaunchDaemons/ world-readable),
# we source the .env file here and exec python with the inherited env.
#
# Installer responsibilities (installer/macos-pkg/postinstall.sh):
#   1. Drop this script at /Library/Application Support/MiningGuardian/bin/feedback_loop_daemon_launcher.sh
#      with mode 0755, owner root:wheel.
#   2. Drop /Library/Application Support/MiningGuardian/.env with mode 0600, owner root:wheel
#      containing MG_DB_PASSWORD, PGHOST, PGPORT, PGUSER, PGDATABASE.
#   3. Drop the plist at /Library/LaunchDaemons/com.miningguardian.feedback-loop-daemon.plist
#      with mode 0644, owner root:wheel.
#   4. mkdir -p /Library/Application Support/MiningGuardian/logs
#   5. launchctl bootstrap system /Library/LaunchDaemons/com.miningguardian.feedback-loop-daemon.plist
#
# This script is identical in shape to whatever wrapper the systemd unit
# would need on Linux (where systemd's EnvironmentFile= handles it for us).

set -euo pipefail

INSTALL_ROOT="/Library/Application Support/MiningGuardian"
ENV_FILE="${INSTALL_ROOT}/.env"
VENV_PYTHON="${INSTALL_ROOT}/venv/bin/python"
DAEMON_PATH="${INSTALL_ROOT}/intelligence-catalog/db/feedback_loop_daemon.py"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "[feedback_loop_daemon_launcher] FATAL: ${ENV_FILE} not found" >&2
    exit 1
fi

if [[ ! -x "${VENV_PYTHON}" ]]; then
    echo "[feedback_loop_daemon_launcher] FATAL: ${VENV_PYTHON} missing or not executable" >&2
    exit 1
fi

if [[ ! -f "${DAEMON_PATH}" ]]; then
    echo "[feedback_loop_daemon_launcher] FATAL: ${DAEMON_PATH} not found" >&2
    exit 1
fi

# Source .env in a subshell-safe way: only KEY=VALUE lines, no commands.
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

# P-019D (2026-05-07) — preflight before exec. The C5 daemon opens
# psycopg2 in autocommit and runs `LISTEN catalog_feedback` at module
# scope; if MG_DB_PASSWORD does not match the actual mg role (P-029
# reconcile race or .env drift) the daemon raises OperationalError and
# exits in <0.5s — under launchd ThrottleInterval=10 + RunAtLoad=true
# this surfaces as `Bootstrap failed: 5: Input/output error` with no
# further detail (the same B-25 class as the FastAPI services). Bound
# the auth class behind a loud preflight that writes to stderr (which
# launchd's StandardErrorPath captures, dumped by postinstall in P-019D
# step 3). This daemon does not bind a TCP port, so no port check.
# shellcheck source=_preflight.sh
source "${INSTALL_ROOT}/bin/_preflight.sh"
_preflight_env_keys "feedback_loop_daemon" "${ENV_FILE}" \
    MG_DB_PASSWORD || exit $?
_preflight_db_ping "feedback_loop_daemon" "${VENV_PYTHON}" || exit $?

exec "${VENV_PYTHON}" -u "${DAEMON_PATH}"
