#!/bin/bash
# installer/macos-pkg/resources/launchd/launchers/scheduled_job_launcher.sh
# D-18 Gap 4 / P-007 — v1.0.3.
#
# Generic wrapper invoked by the 11 com.miningguardian.scheduled.* plists
# that replace setup.sh::phase_10_cron. Each scheduled plist passes:
#   $1  the entrypoint, relative to ${INSTALL_ROOT}
#         e.g. ai/daily_deep_dive.py
#         e.g. scripts/db_maintenance.sh
#         e.g. tests/run_benchmark.py
#   $2  a stable label (used for stamp / lock file naming)
#         e.g. daily_deep_dive
#
# Why this wrapper exists:
#   * launchd has no EnvironmentFile= equivalent — we must source .env
#     before exec'ing the entrypoint. Mirrors the per-service launchers.
#   * Eleven nearly-identical wrappers would be more maintenance than one
#     parameterized wrapper. The plists encode the per-job knobs
#     (StartCalendarInterval, log paths, ProgramArguments).
#   * Last-run stamping for the operator console (D-19): every successful
#     run writes a JSON line to
#       ${INSTALL_ROOT}/logs/scheduled/<label>.last-run.json
#     The console reads this in console/system_state.py to render the
#     "last run" column on /tasks. No DB write at job-fire time keeps the
#     wrapper independent of Postgres availability.
#
# Install:
#   * Dropped at ${INSTALL_ROOT}/bin/scheduled_job_launcher.sh by
#     postinstall.sh::step_install_launcher_wrappers (mode 0755 root:wheel).
#   * Each scheduled plist invokes:
#       /bin/bash <bin>/scheduled_job_launcher.sh <entrypoint> <label>
#
# Exit codes propagate from the entrypoint so launchd's
# ExitTimeOut / KeepAlive=Crashed semantics behave correctly.

set -euo pipefail

INSTALL_ROOT="/Library/Application Support/MiningGuardian"
ENV_FILE="${INSTALL_ROOT}/.env"
VENV_PYTHON="${INSTALL_ROOT}/venv/bin/python"
STAMP_DIR="${INSTALL_ROOT}/logs/scheduled"

if [[ $# -lt 2 ]]; then
    echo "[scheduled_job_launcher] FATAL: usage: $0 <entrypoint-relative-to-install-root> <label>" >&2
    exit 2
fi

ENTRY="$1"
LABEL="$2"
ENTRY_FULL="${INSTALL_ROOT}/${ENTRY}"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "[scheduled_job_launcher][${LABEL}] FATAL: ${ENV_FILE} not found" >&2
    exit 1
fi

if [[ ! -f "${ENTRY_FULL}" ]]; then
    echo "[scheduled_job_launcher][${LABEL}] FATAL: entrypoint not found: ${ENTRY_FULL}" >&2
    exit 1
fi

# Source .env so AMS_*, SLACK_*, GUARDIAN_PG_*, MG_DB_*, OLLAMA_HOST etc.
# are exported into the child process environment.
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

export PYTHONPATH="${INSTALL_ROOT}:${PYTHONPATH:-}"
# P-028 (2026-05-06) — see scanner_launcher.sh for rationale.
export MG_INSTALL_ROOT="${INSTALL_ROOT}"
mkdir -p "${STAMP_DIR}"

cd "${INSTALL_ROOT}"

started_at_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Pick interpreter by file extension. .py -> venv python; .sh -> bash.
# Anything else fails loudly so a future entrypoint that changes shape
# does not silently no-op.
rc=0
case "${ENTRY}" in
    *.py)
        if [[ ! -x "${VENV_PYTHON}" ]]; then
            echo "[scheduled_job_launcher][${LABEL}] FATAL: ${VENV_PYTHON} missing or not executable" >&2
            exit 1
        fi
        "${VENV_PYTHON}" -u "${ENTRY_FULL}" || rc=$?
        ;;
    *.sh)
        /bin/bash "${ENTRY_FULL}" || rc=$?
        ;;
    *)
        echo "[scheduled_job_launcher][${LABEL}] FATAL: unsupported entrypoint extension: ${ENTRY}" >&2
        exit 1
        ;;
esac

finished_at_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Stamp regardless of exit code so the console can show "last failed at"
# vs "last succeeded at". Best-effort — never fail the run because we
# could not write the stamp.
{
    printf '{"label":"%s","entrypoint":"%s","started_at_utc":"%s","finished_at_utc":"%s","exit_code":%d}\n' \
        "${LABEL}" "${ENTRY}" "${started_at_utc}" "${finished_at_utc}" "${rc}" \
        > "${STAMP_DIR}/${LABEL}.last-run.json"
} || true

exit "${rc}"
