#!/usr/bin/env bash
# tests/installer/test_postinstall_service_startup_robust.sh
#
# P-019D — postinstall.sh + launcher static checks for the
# defensive-preflight pass added on 2026-05-07.
#
# Background: P-019C made the bootstrap loop robust + diagnostic. The
# 2026-05-06 install on the Mini still surfaced 5 of 10 LaunchDaemons
# exiting silently with errno 5. The 5 failing services (dashboard-api,
# approval-api, intelligence-report, console, feedback-loop-daemon) all
# share one trait: their entry points open a network/DB resource at
# module scope. P-019D adds a shared `_preflight.sh` library that those
# 5 launchers source before exec'ing Python; postinstall installs the
# library into ${INSTALL_ROOT}/bin and tails the failing service's
# StandardErrorPath inside the launchctl diagnostic dump.
#
# Source-tree static checks only — no live launchctl, no Mac.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

POSTINSTALL="installer/macos-pkg/scripts/postinstall.sh"
LAUNCHERS_DIR="installer/macos-pkg/resources/launchd/launchers"
PREFLIGHT="${LAUNCHERS_DIR}/_preflight.sh"
DEPLOY_LAUNCHER="deploy/feedback_loop_daemon_launcher.sh"

pass_count=0
fail_count=0
ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }
section() { echo; echo "## $*"; }


section "1. Preflight library file present"
if [[ -r "$PREFLIGHT" ]]; then
    ok "${PREFLIGHT} present"
else
    fail "${PREFLIGHT} missing"
fi
if bash -n "$PREFLIGHT" 2>/dev/null; then
    ok "preflight library is syntactically valid bash"
else
    fail "preflight library has syntax errors"
fi


section "2. Preflight library exposes the three required functions"
for fn in _preflight_env_keys _preflight_db_ping _preflight_port_free; do
    if grep -qE "^${fn}\(\)" "$PREFLIGHT"; then
        ok "${fn}() defined"
    else
        fail "${fn}() missing"
    fi
done


section "3. Preflight library is double-source-safe"
if grep -qE '_MG_PREFLIGHT_LOADED' "$PREFLIGHT"; then
    ok "double-source guard variable present"
else
    fail "missing _MG_PREFLIGHT_LOADED double-source guard"
fi


section "4. Preflight functions write diagnostics to STDERR"
# Each function must emit messages to stderr so launchd's
# StandardErrorPath picks them up. Heuristic: the helper _preflight_log
# does the redirect; verify it.
log_body="$(awk '/^_preflight_log\(\)/,/^\}/' "$PREFLIGHT")"
if echo "$log_body" | grep -qE '>&2'; then
    ok "_preflight_log() routes to stderr"
else
    fail "_preflight_log() does not route to stderr"
fi


section "5. _preflight_db_ping has a fast-fail on auth (rc=23)"
db_body="$(awk '/^_preflight_db_ping\(\)/,/^\}/' "$PREFLIGHT")"
if echo "$db_body" | grep -qE 'authentication failed'; then
    ok "db ping detects 'authentication failed' substring"
else
    fail "db ping does not detect auth-failed message"
fi
if echo "$db_body" | grep -qE 'sys.exit\(23\)'; then
    ok "db ping exits 23 on auth failure (no retry)"
else
    fail "db ping missing sys.exit(23) on auth failure"
fi
if echo "$db_body" | grep -qE 'rc.*-eq 23'; then
    ok "db ping wrapper short-circuits on rc=23 (no further retries)"
else
    fail "db ping wrapper does not short-circuit on rc=23"
fi


section "6. _preflight_port_free uses lsof + tries SIGTERM before failing"
port_body="$(awk '/^_preflight_port_free\(\)/,/^\}/' "$PREFLIGHT")"
if echo "$port_body" | grep -qE 'lsof'; then
    ok "port check uses lsof"
else
    fail "port check missing lsof"
fi
if echo "$port_body" | grep -qE 'kill.*-TERM'; then
    ok "port check sends SIGTERM to free a stale holder"
else
    fail "port check does not send SIGTERM"
fi
# Refusal-to-escalate to SIGKILL is intentional; verify by absence of an
# ACTUAL kill command (not a code comment that mentions SIGKILL by name).
# Strip comments first, then look for a kill -9 / kill -KILL / kill -SIGKILL
# invocation.
port_code_only="$(echo "$port_body" | sed -E 's/[[:space:]]*#.*$//')"
if echo "$port_code_only" | grep -qE '/bin/kill[[:space:]]+-(9|KILL|SIGKILL)|[[:space:]]kill[[:space:]]+-(9|KILL|SIGKILL)'; then
    fail "port check escalates to SIGKILL — must NOT (we don't own the process)"
else
    ok "port check does NOT escalate to SIGKILL on unowned process"
fi


section "7. The 5 failing-class launchers source the preflight library"
declare -a service_launchers=(
    "${LAUNCHERS_DIR}/dashboard_api_launcher.sh"
    "${LAUNCHERS_DIR}/approval_api_launcher.sh"
    "${LAUNCHERS_DIR}/intelligence_report_launcher.sh"
    "${LAUNCHERS_DIR}/console_launcher.sh"
    "${DEPLOY_LAUNCHER}"
)
for w in "${service_launchers[@]}"; do
    name="$(basename "$w")"
    if [[ ! -r "$w" ]]; then
        fail "launcher missing: $w"
        continue
    fi
    if grep -qE 'source[[:space:]]+"\$\{INSTALL_ROOT\}/bin/_preflight\.sh"' "$w"; then
        ok "${name}: sources \${INSTALL_ROOT}/bin/_preflight.sh"
    else
        fail "${name}: does NOT source \${INSTALL_ROOT}/bin/_preflight.sh"
    fi
done


section "8. Each failing-class launcher calls the right preflight checks"
# Port-binding services must call _preflight_port_free.
# Use a flattened-line view (line continuations collapsed) so multi-line
# preflight invocations match the same as single-line ones.
flatten_launcher() {
    local p="$1"
    /usr/bin/sed -E ':a;N;$!ba; s/\\\n[[:space:]]*/ /g' "$p"
}
declare -A expected_port=(
    ["${LAUNCHERS_DIR}/dashboard_api_launcher.sh"]="8585"
    ["${LAUNCHERS_DIR}/approval_api_launcher.sh"]="8686"
    ["${LAUNCHERS_DIR}/intelligence_report_launcher.sh"]="INTEL_PORT"
    ["${LAUNCHERS_DIR}/console_launcher.sh"]="MG_CONSOLE_PORT"
)
for w in "${!expected_port[@]}"; do
    name="$(basename "$w")"
    pat="${expected_port[$w]}"
    flat="$(flatten_launcher "$w")"
    if echo "$flat" | grep -qE "_preflight_port_free [^|&;]*${pat}"; then
        ok "${name}: calls _preflight_port_free for ${pat}"
    else
        fail "${name}: does NOT call _preflight_port_free for ${pat}"
    fi
done

# DB-touching services (4 of 5; console is db-tolerant) call db_ping.
declare -a db_ping_launchers=(
    "${LAUNCHERS_DIR}/dashboard_api_launcher.sh"
    "${LAUNCHERS_DIR}/approval_api_launcher.sh"
    "${LAUNCHERS_DIR}/intelligence_report_launcher.sh"
    "${DEPLOY_LAUNCHER}"
)
for w in "${db_ping_launchers[@]}"; do
    name="$(basename "$w")"
    flat="$(flatten_launcher "$w")"
    if echo "$flat" | grep -qE '_preflight_db_ping '; then
        ok "${name}: calls _preflight_db_ping"
    else
        fail "${name}: does NOT call _preflight_db_ping"
    fi
done

# Console is intentionally DB-tolerant; verify it does NOT call db_ping.
if grep -qE '_preflight_db_ping' "${LAUNCHERS_DIR}/console_launcher.sh"; then
    fail "console_launcher.sh: calls _preflight_db_ping (should be db-tolerant)"
else
    ok "console_launcher.sh: does NOT call _preflight_db_ping (intentional)"
fi


section "9. Each failing-class launcher validates required env keys"
# Every launcher except console (which has no DB requirement) must call
# _preflight_env_keys with at least MG_DB_PASSWORD.
declare -a env_keys_launchers=(
    "${LAUNCHERS_DIR}/dashboard_api_launcher.sh"
    "${LAUNCHERS_DIR}/approval_api_launcher.sh"
    "${LAUNCHERS_DIR}/intelligence_report_launcher.sh"
    "${DEPLOY_LAUNCHER}"
)
for w in "${env_keys_launchers[@]}"; do
    name="$(basename "$w")"
    flat="$(flatten_launcher "$w")"
    if echo "$flat" | grep -qE '_preflight_env_keys [^|&;]*MG_DB_PASSWORD'; then
        ok "${name}: validates MG_DB_PASSWORD"
    else
        fail "${name}: does NOT validate MG_DB_PASSWORD"
    fi
done


section "10. Every preflight call short-circuits with || exit \$?"
for w in "${service_launchers[@]}"; do
    name="$(basename "$w")"
    if [[ ! -r "$w" ]]; then
        continue
    fi
    flat="$(flatten_launcher "$w")"
    pf_calls=0
    pf_exits=0
    while IFS= read -r line; do
        pf_calls=$((pf_calls + 1))
        if [[ "$line" == *"|| exit \$?"* ]]; then
            pf_exits=$((pf_exits + 1))
        fi
    done < <(echo "$flat" | /usr/bin/grep -E '_preflight_(env_keys|db_ping|port_free)[[:space:]]')
    if [[ "$pf_calls" -eq 0 ]]; then
        fail "${name}: no preflight calls found"
    elif [[ "$pf_calls" -eq "$pf_exits" ]]; then
        ok "${name}: ${pf_calls} preflight call(s), all short-circuit on failure"
    else
        fail "${name}: ${pf_calls} preflight call(s) but only ${pf_exits} short-circuit"
    fi
done


section "11. postinstall installs _preflight.sh into bin/"
launcher_install_body="$(awk '/^step_install_launcher_wrappers\(\)/,/^step_create_venv/' "$POSTINSTALL")"
if echo "$launcher_install_body" | grep -qE '_preflight\.sh'; then
    ok "step_install_launcher_wrappers references _preflight.sh"
else
    fail "step_install_launcher_wrappers does NOT install _preflight.sh"
fi
if echo "$launcher_install_body" | grep -qE 'install -m 0644 -o root -g wheel.*_preflight\.sh|install -m 0644.*-o root -g wheel.*pf_src'; then
    ok "_preflight.sh installed with mode 0644 root:wheel"
else
    # Looser fallback: any 0644 install line in the same step that
    # mentions the preflight payload.
    if echo "$launcher_install_body" | grep -qE 'pf_src|_preflight\.sh' \
       && echo "$launcher_install_body" | grep -qE 'install -m 0644'; then
        ok "_preflight.sh has an install -m 0644 line in the same step"
    else
        fail "_preflight.sh install line missing 0644 root:wheel ownership"
    fi
fi


section "12. _dump_launchctl_diagnostics tails StandardErrorPath"
diag_body="$(awk '/^_dump_launchctl_diagnostics\(\)/,/^\}/' "$POSTINSTALL")"
if echo "$diag_body" | grep -qE 'StandardErrorPath'; then
    ok "diagnostics extract StandardErrorPath"
else
    fail "diagnostics do NOT extract StandardErrorPath"
fi
if echo "$diag_body" | grep -qE 'plutil -extract StandardErrorPath'; then
    ok "diagnostics use plutil -extract to find the path"
else
    fail "diagnostics missing plutil -extract for StandardErrorPath"
fi
if echo "$diag_body" | grep -qE 'tail -n [0-9]+ "\$err_path"'; then
    ok "diagnostics tail the err log content"
else
    fail "diagnostics do NOT tail the err log content"
fi


section "13. Idempotency: re-source of preflight library is a no-op"
# Sourcing _preflight.sh twice in the same shell must not duplicate
# function definitions or side-effects.
tmp_log="$(mktemp -t mg-preflight-double-source.XXXXXX)"
trap 'rm -f "$tmp_log"' EXIT
bash -c "
set -e
source '${PREFLIGHT}'
source '${PREFLIGHT}'
type _preflight_env_keys >/dev/null
type _preflight_db_ping  >/dev/null
type _preflight_port_free >/dev/null
" >"$tmp_log" 2>&1 && rc=0 || rc=$?
if [[ "$rc" -eq 0 ]]; then
    ok "preflight library is double-source safe"
else
    fail "preflight double-source failed (rc=${rc}): $(cat "$tmp_log")"
fi


section "14. Preflight env-key check rejects an empty value"
# Build a tiny .env with one empty value and verify the function returns
# a non-zero code.
tmp_env="$(mktemp -t mg-preflight-empty-env.XXXXXX)"
trap 'rm -f "$tmp_log" "$tmp_env"' EXIT
cat >"$tmp_env" <<EOF
MG_DB_PASSWORD=
OTHER_KEY=value
EOF
rc=0
bash -c "
source '${PREFLIGHT}'
_preflight_env_keys 'test' '${tmp_env}' MG_DB_PASSWORD
" >/dev/null 2>&1 || rc=$?
if [[ "$rc" -ne 0 ]]; then
    ok "preflight env-key check rejects empty MG_DB_PASSWORD (rc=${rc})"
else
    fail "preflight env-key check accepted empty MG_DB_PASSWORD"
fi

rc=0
bash -c "
source '${PREFLIGHT}'
_preflight_env_keys 'test' '${tmp_env}' OTHER_KEY
" >/dev/null 2>&1 || rc=$?
if [[ "$rc" -eq 0 ]]; then
    ok "preflight env-key check accepts non-empty OTHER_KEY"
else
    fail "preflight env-key check rejected a non-empty value (rc=${rc})"
fi

rc=0
bash -c "
source '${PREFLIGHT}'
_preflight_env_keys 'test' '${tmp_env}' UNDEFINED_KEY
" >/dev/null 2>&1 || rc=$?
if [[ "$rc" -ne 0 ]]; then
    ok "preflight env-key check rejects an absent key (rc=${rc})"
else
    fail "preflight env-key check accepted an absent key"
fi


# ---------------------------------------------------------------------------
echo
echo "================================================================"
echo "PASS: ${pass_count}    FAIL: ${fail_count}"
echo "================================================================"
if [[ "$fail_count" -gt 0 ]]; then
    exit 1
fi
exit 0
