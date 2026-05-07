#!/bin/bash
# installer/macos-pkg/resources/launchd/launchers/_preflight.sh
# P-019D (2026-05-07) — shared launcher preflight library.
#
# Why this exists
# ---------------
# After P-019C made the launchctl bootstrap loop robust + diagnostic, the
# 2026-05-06 install on the Mini still surfaced 5 of 10 LaunchDaemons
# failing with `Bootstrap failed: 5: Input/output error`:
#
#     com.miningguardian.dashboard-api          (binds 127.0.0.1:8585)
#     com.miningguardian.approval-api           (binds 127.0.0.1:8686)
#     com.miningguardian.intelligence-report    (binds 127.0.0.1:8590)
#     com.miningguardian.console                (binds 127.0.0.1:8787)
#     com.miningguardian.feedback-loop-daemon   (opens psycopg2 LISTEN)
#
# All five share one trait: their entry points open a NETWORK/DB resource
# at module scope (uvicorn.run() or psycopg2.connect() before any HTTP
# request). The 5 services that loaded successfully (scanner,
# slack-listener, slack-commands, overnight-automation, alerts) defer
# their first network/DB call until inside the run loop.
#
# Two failure modes plausibly cause the 5-of-10 split:
#
#   (a) Port already bound by a stale uvicorn process from a prior install
#       attempt or from the old systemd-on-ROBS-PC era. uvicorn raises
#       OSError immediately, the process exits in <0.5s, launchd's
#       ThrottleInterval=10 + RunAtLoad=true loop hits the rapid-respawn
#       refusal that surfaces as bootstrap errno 5.
#
#   (b) Postgres password drift / .env-vs-actual mismatch. P-029
#       reconciles `mg`'s Postgres password during postinstall, but on a
#       fresh re-install the new password is only effective AFTER the
#       reconcile step runs. If a launchd job races the reconcile, or if
#       an env key is missing, psycopg2.connect() raises
#       OperationalError, the process exits, and launchd refuses on
#       respawn-throttle.
#
# This library covers both classes BEFORE the Python entry point is
# exec'd, with explicit error codes and diagnostic output written to
# stderr (which launchd routes to StandardErrorPath, captured by the
# postinstall diagnostic dumper in P-019D step 3).
#
# Idempotent + safe to source multiple times. No globals leak. Each
# function is independently callable; launchers source this library and
# decide which checks apply.
#
# Conventions
# -----------
# - Functions return non-zero on failure; callers decide whether to
#   abort or continue.
# - All diagnostic output goes to stderr so launchd's StandardErrorPath
#   captures it (postinstall.sh's _dump_launchctl_diagnostics tails
#   that file).
# - No `set -e` here — this library is sourced into launcher scripts
#   that already have `set -euo pipefail`, and we want function returns
#   to be testable by callers without aborting the launcher prematurely.

# Guard against double-source.
if [[ -n "${_MG_PREFLIGHT_LOADED:-}" ]]; then
    return 0 2>/dev/null || exit 0
fi
_MG_PREFLIGHT_LOADED=1

# -----------------------------------------------------------------------
# _preflight_log <component> <message...>
#
# All preflight messages prefix the component name (e.g. dashboard_api)
# so a multi-launcher diagnostic dump is greppable.
# -----------------------------------------------------------------------
_preflight_log() {
    local component="$1"; shift
    local ts
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "[${ts}] [${component}] [preflight] $*" >&2
}

# -----------------------------------------------------------------------
# _preflight_env_keys <component> <env_file> <key1> [key2 ...]
#
# Verify each named key exists in the env file as a KEY=VALUE line with a
# non-empty VALUE. Returns 0 if all present, non-zero on first missing
# or empty key.
#
# Why parse the file rather than rely on ${KEY:-} after sourcing? Because
# this is a LOAD-time guard: we want to point at the literal source of
# truth (the .env on disk) so the operator's recovery action is "edit
# /Library/Application Support/MiningGuardian/.env". Sourcing first then
# checking would obscure whether the value is missing, blank, or just
# overridden by a later line.
# -----------------------------------------------------------------------
_preflight_env_keys() {
    local component="$1"; shift
    local env_file="$1"; shift

    if [[ ! -f "$env_file" ]]; then
        _preflight_log "$component" "FATAL env file not found: ${env_file}"
        return 11
    fi

    local key value
    for key in "$@"; do
        value="$(/usr/bin/grep -E "^${key}=" "$env_file" 2>/dev/null \
                  | /usr/bin/tail -n 1 \
                  | /usr/bin/sed -E "s/^${key}=//; s/^[\"']//; s/[\"']$//")"
        if [[ -z "$value" ]]; then
            _preflight_log "$component" "FATAL required env key missing or empty: ${key} (edit ${env_file})"
            return 12
        fi
    done

    _preflight_log "$component" "env keys ok ($#)"
    return 0
}

# -----------------------------------------------------------------------
# _preflight_db_ping <component> <venv_python> [retries=5] [delay_s=2]
#
# Bounded-retry Postgres connection check. Uses the venv's psycopg2 (so
# we get the same client as the entry point) with the connection params
# already in the environment (the launcher will have sourced .env before
# calling us, so MG_DB_PASSWORD / PG* / GUARDIAN_PG_* are visible).
#
# Return codes:
#   0   — connected within budget
#   21  — psycopg2 import failed (venv broken)
#   22  — connection refused / timeout for entire retry budget
#   23  — auth failed (password mismatch, role missing) — does not retry
#         beyond the first attempt; an auth failure is not a transient
#         bootstrap race and re-trying just delays the inevitable
#         diagnostic.
# -----------------------------------------------------------------------
_preflight_db_ping() {
    local component="$1"; shift
    local venv_python="$1"; shift
    local retries="${1:-5}"
    local delay_s="${2:-2}"

    if [[ ! -x "$venv_python" ]]; then
        _preflight_log "$component" "FATAL venv python missing or not executable: ${venv_python}"
        return 21
    fi

    local attempt=1
    local rc=0
    while (( attempt <= retries )); do
        # Run the connect probe in the venv. Exit 0 = connected, 23 =
        # auth, 22 = transient. Pull the dsn from env vars (psycopg2
        # picks up PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE
        # automatically when no dsn is passed).
        if "$venv_python" - <<'PYEOF' 2>&1
import os, sys
try:
    import psycopg2
    from psycopg2 import OperationalError
except Exception as exc:
    print(f"psycopg2 import failed: {exc}", file=sys.stderr)
    sys.exit(21)

# Prefer the operational MG_DB_* vars if present; fall back to PG* (which
# psycopg2 picks up natively). Either set is enough — the launcher
# sourced .env before this script runs.
dsn_kwargs = {}
host = os.environ.get("MG_DB_HOST") or os.environ.get("PGHOST", "127.0.0.1")
port = os.environ.get("MG_DB_PORT") or os.environ.get("PGPORT", "5432")
user = os.environ.get("MG_DB_USER") or os.environ.get("PGUSER", "mg")
db   = os.environ.get("MG_DB_NAME") or os.environ.get("PGDATABASE", "mining_guardian")
pwd  = os.environ.get("MG_DB_PASSWORD") or os.environ.get("PGPASSWORD")
dsn_kwargs.update(host=host, port=port, user=user, dbname=db,
                  connect_timeout=5)
if pwd:
    dsn_kwargs["password"] = pwd

try:
    conn = psycopg2.connect(**dsn_kwargs)
    conn.close()
    print(f"db ok: host={host} port={port} user={user} db={db}",
          file=sys.stderr)
    sys.exit(0)
except OperationalError as exc:
    msg = str(exc).lower()
    if "authentication failed" in msg or "role " in msg and "does not exist" in msg:
        print(f"db auth failed: {exc}".rstrip(), file=sys.stderr)
        sys.exit(23)
    print(f"db connect failed: {exc}".rstrip(), file=sys.stderr)
    sys.exit(22)
except Exception as exc:
    print(f"db unexpected error: {exc}".rstrip(), file=sys.stderr)
    sys.exit(22)
PYEOF
        then
            _preflight_log "$component" "db ping ok (attempt ${attempt}/${retries})"
            return 0
        fi
        rc=$?
        if [[ "$rc" -eq 21 ]]; then
            _preflight_log "$component" "FATAL psycopg2 unavailable in venv (rc=21)"
            return 21
        fi
        if [[ "$rc" -eq 23 ]]; then
            _preflight_log "$component" "FATAL Postgres auth failed (rc=23) — check MG_DB_PASSWORD in .env vs ALTER USER mg PASSWORD"
            return 23
        fi
        _preflight_log "$component" "db transient failure (rc=${rc}) attempt ${attempt}/${retries}, retrying in ${delay_s}s"
        sleep "$delay_s"
        attempt=$((attempt + 1))
    done

    _preflight_log "$component" "FATAL Postgres unreachable after ${retries} attempts (rc=22)"
    return 22
}

# -----------------------------------------------------------------------
# _preflight_port_free <component> <port> [retries=3]
#
# Verify that the given TCP port is not held by another process. If it
# is, identify the holder via `lsof`, log the holder PID + command, send
# SIGTERM, wait briefly, then re-check. Repeat up to `retries`. If still
# held after the budget, return non-zero with the lsof output captured
# in the launcher's stderr.
#
# Why try to terminate a holder rather than just refusing? The dominant
# observed failure mode is a stale uvicorn from the previous install
# attempt — exactly the same Python bound to exactly the same port.
# Killing it is safe (the upgrade is replacing it). For the rare case
# where an UNRELATED process holds the port, we abort after the budget
# rather than escalate to SIGKILL on something we don't own.
#
# Return codes:
#   0   — port free
#   31  — lsof not available (don't fail-open; treat as preflight error)
#   32  — port held; could not free within retry budget
# -----------------------------------------------------------------------
_preflight_port_free() {
    local component="$1"; shift
    local port="$1"; shift
    local retries="${1:-3}"

    if ! command -v /usr/sbin/lsof >/dev/null 2>&1 && ! command -v lsof >/dev/null 2>&1; then
        _preflight_log "$component" "FATAL lsof not available — cannot probe port ${port}"
        return 31
    fi
    local lsof_bin
    if [[ -x /usr/sbin/lsof ]]; then
        lsof_bin=/usr/sbin/lsof
    else
        lsof_bin="$(command -v lsof)"
    fi

    local attempt=1
    local holder_pid holder_cmd
    while (( attempt <= retries )); do
        # -i:PORT lists IPv4 + IPv6 sockets on the port; -sTCP:LISTEN
        # narrows to listeners (avoids matching transient client connects).
        # -t prints just the PID list.
        holder_pid="$("$lsof_bin" -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | /usr/bin/head -n 1 || true)"
        if [[ -z "$holder_pid" ]]; then
            _preflight_log "$component" "port ${port} free (attempt ${attempt}/${retries})"
            return 0
        fi
        holder_cmd="$(/bin/ps -o command= -p "$holder_pid" 2>/dev/null | /usr/bin/head -c 200 || true)"
        _preflight_log "$component" "port ${port} held by pid=${holder_pid} cmd=${holder_cmd}; sending SIGTERM (attempt ${attempt}/${retries})"
        /bin/kill -TERM "$holder_pid" 2>/dev/null || true
        # Brief wait for graceful exit; do NOT escalate to SIGKILL on a
        # process we do not own. If it does not release the port within
        # 2s, the next loop iteration will probe again.
        sleep 2
        attempt=$((attempt + 1))
    done

    # Final probe + diagnostic dump on hard failure.
    holder_pid="$("$lsof_bin" -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | /usr/bin/head -n 1 || true)"
    if [[ -z "$holder_pid" ]]; then
        _preflight_log "$component" "port ${port} free after final probe"
        return 0
    fi
    _preflight_log "$component" "FATAL port ${port} still held after ${retries} attempts; full lsof:"
    "$lsof_bin" -nP -iTCP:"$port" -sTCP:LISTEN >&2 2>&1 || true
    return 32
}
