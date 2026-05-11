#!/usr/bin/env bash
# tests/installer/test_p038_db_maintenance_macos_portable.sh
#
# P-038 item #6 (2026-05-11) — `scripts/db_maintenance.sh` was written
# for a Linux host with a native `postgres` Unix user and a `psql` binary
# on PATH. On the Mac Mini deployment shape Postgres runs INSIDE a Docker
# container named `mining-guardian-db`, there is no `postgres` Unix user,
# and the script's `/var/log/db_maintenance.log` write path is a Linux
# holdover the launcher already supersedes by capturing stdout/stderr to
# `${MG_INSTALL_ROOT}/logs/scheduled/db_maintenance.{out,err}.log`.
#
# Live evidence captured from the Mini before writing the fix
# (`/Library/Application Support/MiningGuardian/logs/scheduled/`):
#   db_maintenance.last-run.json  → exit_code: 1 every 03:30 local.
#   db_maintenance.err.log        → empty (set -e aborts before the
#                                   launcher's stderr capture catches
#                                   anything; bash's exit-on-error does
#                                   not print to stderr).
#   db_maintenance.out.log        → empty (same reason).
#   /var/log/db_maintenance.log   → 5 consecutive days (May 7-11) of:
#                                       Starting database maintenance ...
#                                         Running VACUUM ANALYZE...
#                                       sudo: unknown user postgres
#                                       sudo: error initializing audit
#                                          plugin sudoers_audit
#                                   The /var/log/ file gets written
#                                   because the LaunchDaemon runs as
#                                   root (no UserName key in the plist
#                                   → launchd default), but every sudo
#                                   call fails because macOS has no
#                                   `postgres` user.
#
# Schema verified live on the Mini's Postgres (via Docker container):
#   - DB name `mining_guardian`, container name `mining-guardian-db`,
#     DB user `mg`, DB size 51 MB at the time of the audit.
#   - `docker exec mining-guardian-db psql -U mg -d mining_guardian -c
#     "ANALYZE scans"` returns `ANALYZE` (success). All 5 SQL commands
#     the script runs work cleanly inside the container.
#
# P-038 item #6 fix:
#   1. Replace all five `sudo -u postgres psql -d $PGDB ...` invocations
#      with `docker exec mining-guardian-db psql -U mg -d mining_guardian
#      ...`. Hardcode the container/user/db names — these are deployment
#      identities baked into the .pkg install, not env-configurable.
#   2. Drop `set -e`. With docker exec the first failure no longer
#      brings down the whole script silently; instead, explicit per-step
#      error handling logs the failure to stderr (caught by the launcher)
#      and the integrity check section continues so the operator still
#      sees the DB size and table report even if VACUUM ANALYZE hiccups.
#   3. Drop the `/var/log/db_maintenance.log` inline writes. Emit all
#      output to stdout/stderr; the launcher captures both to
#      `${MG_INSTALL_ROOT}/logs/scheduled/db_maintenance.{out,err}.log`,
#      which is the canonical Mac location every other scheduled job
#      uses.
#   4. Add `export PATH=/usr/local/bin:$PATH` at the top so `docker` is
#      reachable even if a future plist edit drops the EnvironmentVariables
#      PATH override. (The current plist already includes /usr/local/bin
#      in PATH, but defense-in-depth costs one line.)
#
# Out of scope (deliberate): no schema changes, no migration changes,
# no backup logic (the script never had `pg_dump` or `pg_repack`), no
# postinstall changes, no plist changes (already correct), no payload
# changes.
#
# This test asserts:
#   1. The script parses cleanly (`bash -n`).
#   2. No `sudo -u postgres` invocation survives anywhere in the script
#      (the exact bug shape must never reappear).
#   3. No `$LOG_FILE` writes to `/var/log/` survive (Linux holdover).
#   4. No `set -e` survives (silent-error trap).
#   5. The canonical `docker exec mining-guardian-db psql -U mg -d
#      mining_guardian` invocation appears at least once (proves the
#      docker-exec rewrite landed).
#   6. The script exports a PATH that includes `/usr/local/bin` so
#      `docker` is reachable.
#   7. Functional smoke — run the script with a mock `docker` binary on
#      PATH that records the args it was invoked with. The script must
#      exit 0 and invoke `docker exec mining-guardian-db psql -U mg -d
#      mining_guardian` for each of the 5 expected SQL commands
#      (VACUUM ANALYZE, ANALYZE, db size, top-10 tables, scans count).
#   8. Cohort-wide guard — no other `.sh` under `scripts/` re-introduces
#      `sudo -u postgres` (catches future regressions in sibling files).

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TARGET="${REPO_ROOT}/scripts/db_maintenance.sh"

PASS=0
FAIL=0

ok() {
    printf "  OK  %s\n" "$1"
    PASS=$((PASS + 1))
}

bad() {
    printf "  FAIL %s\n" "$1"
    FAIL=$((FAIL + 1))
}

# ----- §1 source presence + bash -n parses -----

echo "§1 source presence and bash -n"
if [[ -f "$TARGET" ]]; then
    ok "target present: ${TARGET#${REPO_ROOT}/}"
else
    bad "target missing: ${TARGET#${REPO_ROOT}/}"
    echo
    echo "Summary: ${PASS} passed, ${FAIL} failed"
    exit 1
fi

if bash -n "$TARGET" 2>/dev/null; then
    ok "bash -n parses"
else
    bad "bash -n failed; this means the script has a syntax error"
fi

# ----- §2 no `sudo -u postgres` survives -----

echo
echo "§2 no sudo -u postgres invocation survives in source code (comments OK)"
# Strip comment-only lines (lines starting with #) before searching, so
# docstring mentions of the OLD broken shape don't false-positive. The
# comment-stripping is intentionally loose because all the docstring
# context lives at the top of the file in #-prefixed comments.
if grep -vE '^[[:space:]]*#' "$TARGET" | grep -E 'sudo[[:space:]]+-u[[:space:]]+postgres' > /dev/null; then
    bad "sudo -u postgres invocation found in source code (the P-038 #6 bug):"
    grep -nE 'sudo[[:space:]]+-u[[:space:]]+postgres' "$TARGET" | head -5 | while IFS= read -r line; do
        printf "      %s\n" "$line"
    done
else
    ok "no sudo -u postgres invocation in source code"
fi

# ----- §3 no /var/log/ inline writes survive -----

echo
echo "§3 no /var/log/ inline log writes in source code (comments OK)"
# Detect writes to /var/log/ (>>) or assignment to a LOG_FILE that points
# at /var/log/. The launcher captures stdout/stderr to the canonical
# logs/scheduled/ location, so /var/log/ is dead weight. Strip comments.
if grep -vE '^[[:space:]]*#' "$TARGET" | grep -E '/var/log/' > /dev/null; then
    bad "/var/log/ path found in source code (Linux holdover):"
    grep -nE '/var/log/' "$TARGET" | head -3 | while IFS= read -r line; do
        printf "      %s\n" "$line"
    done
else
    ok "no /var/log/ path in source code"
fi

# ----- §4 no `set -e` survives -----

echo
echo "§4 no 'set -e' survives (silent-error trap removed)"
# Match `set -e` as a standalone option or as part of a combo like
# `set -eu`, `set -euo pipefail`. Allow comments mentioning set -e.
if grep -nE '^[[:space:]]*set[[:space:]]+-[a-z]*e' "$TARGET" > /dev/null; then
    bad "'set -e' found (will swallow docker exec failures silently):"
    grep -nE '^[[:space:]]*set[[:space:]]+-[a-z]*e' "$TARGET" | head -3 | while IFS= read -r line; do
        printf "      %s\n" "$line"
    done
else
    ok "no 'set -e' active (or it's only mentioned in comments)"
fi

# ----- §5 docker-exec rewrite present (inline or via helper) -----

echo
echo "§5 docker-exec rewrite present (inline invocation OR helper with constants)"
# Two valid shapes:
#   (a) Inline: `docker exec mining-guardian-db psql -U mg -d mining_guardian ...`
#   (b) Helper: a function that calls
#       `docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME"`
#       AND the same source defines CONTAINER="mining-guardian-db",
#       DB_USER="mg", DB_NAME="mining_guardian".
# Either is correct; the helper is cleaner DRY code. Accept both.
inline_count="$(grep -cE 'docker[[:space:]]+exec[[:space:]]+mining-guardian-db[[:space:]]+psql[[:space:]]+-U[[:space:]]+mg[[:space:]]+-d[[:space:]]+mining_guardian' "$TARGET" || true)"
helper_call="$(grep -cE 'docker[[:space:]]+exec[[:space:]]+"\$CONTAINER"[[:space:]]+psql[[:space:]]+-U[[:space:]]+"\$DB_USER"[[:space:]]+-d[[:space:]]+"\$DB_NAME"' "$TARGET" || true)"
has_container_const="$(grep -cE '^[[:space:]]*CONTAINER="mining-guardian-db"' "$TARGET" || true)"
has_user_const="$(grep -cE '^[[:space:]]*DB_USER="mg"' "$TARGET" || true)"
has_db_const="$(grep -cE '^[[:space:]]*DB_NAME="mining_guardian"' "$TARGET" || true)"

if [[ "$inline_count" -ge 1 ]]; then
    ok "inline docker-exec invocation appears (${inline_count} occurrences)"
elif [[ "$helper_call" -ge 1 && "$has_container_const" -ge 1 && "$has_user_const" -ge 1 && "$has_db_const" -ge 1 ]]; then
    ok "helper-function docker exec with correct CONTAINER/DB_USER/DB_NAME constants"
else
    bad "no recognized docker-exec invocation (neither inline nor helper-with-constants)"
    bad "  inline=${inline_count} helper=${helper_call} container_const=${has_container_const} user_const=${has_user_const} db_const=${has_db_const}"
fi

# ----- §6 PATH includes /usr/local/bin so docker is reachable -----

echo
echo "§6 PATH includes /usr/local/bin so docker is reachable"
# Note: `\b` is unreliable across grep dialects when next to `/`, so
# use a literal substring match (no word-boundary anchor).
if grep -nE '^[[:space:]]*export[[:space:]]+PATH=.*/usr/local/bin' "$TARGET" > /dev/null; then
    ok "PATH explicitly includes /usr/local/bin"
else
    bad "no 'export PATH=.../usr/local/bin...' line found (docker may not resolve)"
fi

# ----- §7 functional smoke with mock docker -----

echo
echo "§7 functional smoke — mock docker binary records invocations"
TMP="$(mktemp -d -t p038_db_maint.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

MOCK_BIN="${TMP}/mock-bin"
mkdir -p "$MOCK_BIN"

# Mock docker: log every arg-set to $MOCK_LOG, return canned output for
# the queries that the script reads via $(...).
MOCK_LOG="${TMP}/docker-calls.log"
cat > "${MOCK_BIN}/docker" <<MOCK
#!/usr/bin/env bash
echo "INVOCATION: \$*" >> "${MOCK_LOG}"
# Inspect args to decide what to print on stdout (for command substitution).
# The script does:
#   docker exec mining-guardian-db psql -U mg -d mining_guardian -tAc "SELECT pg_size_pretty(...)"
#   docker exec mining-guardian-db psql -U mg -d mining_guardian -tAc "SELECT COUNT(*) FROM scans"
# Other invocations are run for side effects only (VACUUM, ANALYZE,
# top-10 table report).
if [[ "\$*" == *"pg_size_pretty"* ]]; then
    echo "51 MB"
elif [[ "\$*" == *"SELECT COUNT(*) FROM scans"* ]]; then
    echo "12345"
else
    # Generic success stub.
    echo "OK"
fi
exit 0
MOCK
chmod +x "${MOCK_BIN}/docker"
ok "mock docker installed at ${MOCK_BIN}/docker"

# Run the script with PATH set so the mock docker wins. Capture
# stdout/stderr to mimic what the launcher sees.
script_out="${TMP}/script.out"
script_err="${TMP}/script.err"
if PATH="${MOCK_BIN}:/usr/bin:/bin" bash "$TARGET" > "$script_out" 2> "$script_err"; then
    ok "script exits 0 with mock docker"
else
    rc=$?
    bad "script exited non-zero (${rc}) with mock docker"
    printf "      stderr: %s\n" "$(head -5 "$script_err")"
fi

# Mock docker should have been invoked at least 5 times (5 SQL commands).
if [[ -f "$MOCK_LOG" ]]; then
    call_count="$(wc -l < "$MOCK_LOG" | tr -d ' ')"
    if [[ "$call_count" -ge 5 ]]; then
        ok "mock docker invoked ${call_count} times (≥ 5 expected)"
    else
        bad "mock docker invoked only ${call_count} times (expected ≥ 5)"
        printf "      log: %s\n" "$(cat "$MOCK_LOG")"
    fi
else
    bad "mock docker log file never created"
fi

# Each invocation line must contain `exec mining-guardian-db psql -U mg
# -d mining_guardian`. Some invocations include multi-line SQL (the
# top-10 tables query writes a multi-line string into a single argv
# slot), so multi-line shell `"$*"` capture appears as one logical
# invocation but several physical lines in the log. Count INVOCATION:
# header lines, then count how many of those headers are followed by
# the canonical shape.
if [[ -f "$MOCK_LOG" ]]; then
    inv_headers="$(grep -c '^INVOCATION:' "$MOCK_LOG" || true)"
    inv_with_shape="$(grep '^INVOCATION:' "$MOCK_LOG" | grep -c 'exec mining-guardian-db psql -U mg -d mining_guardian' || true)"
    if [[ "$inv_with_shape" -eq "$inv_headers" && "$inv_headers" -ge 1 ]]; then
        ok "all ${inv_headers} docker invocations target 'exec mining-guardian-db psql -U mg -d mining_guardian'"
    else
        bad "only ${inv_with_shape}/${inv_headers} invocations have the expected shape"
    fi
fi

# Each of the 5 expected SQL command shapes must be present in the calls.
if [[ -f "$MOCK_LOG" ]]; then
    for needle in "VACUUM ANALYZE" "ANALYZE;" "pg_size_pretty" "pg_total_relation_size" "FROM scans"; do
        if grep -q "$needle" "$MOCK_LOG"; then
            ok "docker call covers: $needle"
        else
            bad "no docker call covers: $needle"
        fi
    done
fi

# The script must NOT write to /var/log/. mktemp+stat the script_err
# already captures any sudo / permission noise — assert it stays empty
# or at least never mentions /var/log/.
if grep -q '/var/log/' "$script_err"; then
    bad "script stderr mentions /var/log/ (the Linux holdover is back):"
    printf "      %s\n" "$(grep '/var/log/' "$script_err" | head -3)"
else
    ok "script stderr does not mention /var/log/"
fi

# Exit-code propagation: re-run the script with a FAILING mock docker
# (always exits 1). The script should exit non-zero so the launcher's
# .last-run.json reflects the failure. This prevents silent regressions
# where ALL steps fail but exit_code=0 hides the problem.
echo
echo "   exit-code propagation: failing-mock-docker should produce non-zero exit"
FAIL_BIN="${TMP}/fail-bin"
mkdir -p "$FAIL_BIN"
cat > "${FAIL_BIN}/docker" <<'FAIL_MOCK'
#!/usr/bin/env bash
echo "mock docker says no" >&2
exit 1
FAIL_MOCK
chmod +x "${FAIL_BIN}/docker"
fail_out="${TMP}/fail.out"
fail_err="${TMP}/fail.err"
if PATH="${FAIL_BIN}:/usr/bin:/bin" bash "$TARGET" > "$fail_out" 2> "$fail_err"; then
    bad "script exited 0 with failing-mock-docker (should be non-zero so operator notices)"
else
    ok "script exits non-zero when all docker invocations fail"
fi
if grep -q 'FAIL: Running VACUUM ANALYZE' "$fail_err"; then
    ok "failing-mock stderr contains 'FAIL: Running VACUUM ANALYZE' line (operator sees the failed step)"
else
    bad "failing-mock stderr does not contain 'FAIL: Running VACUUM ANALYZE' line"
    printf "      stderr: %s\n" "$(head -5 "$fail_err")"
fi

# ----- §8 cohort-wide guard — no other scripts/*.sh has sudo -u postgres -----

echo
echo "§8 cohort-wide guard — no sibling shell script has sudo -u postgres in source code"
# Search every .sh under scripts/ (not just the target). If any sibling
# has the same broken pattern in actual code (not comments), this
# catches it now instead of later. bash-3.2-compatible (no mapfile).
sibling_hits=""
for f in "${REPO_ROOT}/scripts/"*.sh; do
    [[ -f "$f" ]] || continue
    if grep -vE '^[[:space:]]*#' "$f" | grep -qE 'sudo[[:space:]]+-u[[:space:]]+postgres'; then
        sibling_hits="${sibling_hits}${f}
SEP"
    fi
done
if [[ -z "$sibling_hits" ]]; then
    ok "no scripts/*.sh has sudo -u postgres in source code"
else
    bad "sibling scripts have sudo -u postgres in source code (cohort regression):"
    printf "%s" "$sibling_hits" | tr 'SEP' '\n' | while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        printf "      %s\n" "${f#${REPO_ROOT}/}"
    done
fi

# ----- summary -----

echo
echo "================================================="
echo "Summary: ${PASS} passed, ${FAIL} failed"
echo "================================================="
if [[ "$FAIL" -gt 0 ]]; then
    exit 1
fi
exit 0
