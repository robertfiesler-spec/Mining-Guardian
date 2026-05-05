#!/usr/bin/env bash
# tests/installer/test_postinstall_env_handoff.sh
#
# D-18 P-022 — postinstall.sh::step_drop_dotenv must export the keys
# the helper libs read directly from the environment, BEFORE
# step_provision_postgres calls them.
#
# Background: the e514c12 install on the customer Mac mini got past
# P-016 / P-017 / P-018 / P-019 / P-020 / P-021, successfully started
# Colima, loaded the postgres:16-bookworm image, dropped a correct
# /Library/Application Support/MiningGuardian/.env (mode 0600),
# then crashed inside provision_postgres() with
#
#     FATAL MG_DB_PASSWORD missing from environment; postinstall did
#     not source .env
#     [postinstall] FATAL (31) postgres container provisioning failed
#
# Root cause: step_drop_dotenv declared MG_DB_PASSWORD,
# CATALOG_API_KEY, INTERNAL_API_SECRET as `local`, then called
# `export MG_DB_PASSWORD` as the last line of the function. In bash,
# `export` on a `local` variable only marks the EXPORT attribute on
# that local — once the function returns, the local goes out of scope
# and the calling shell never sees the value. provision_postgres()
# then ran with MG_DB_PASSWORD unset and bailed.
#
# Fix shape (this test asserts it):
#   1. The unscoped (script-shell-scope) declaration of secrets in
#      step_drop_dotenv — no `local` line for MG_DB_PASSWORD,
#      CATALOG_API_KEY, INTERNAL_API_SECRET.
#   2. An `export` of every key the downstream helpers read
#      (MG_DB_PASSWORD plus the GUARDIAN_PG_* / PG* family that the
#      code base reads directly).
#   3. A `loaded generated env keys` log line emitted from
#      step_drop_dotenv that names the keys (NEVER values).
#   4. A defensive preflight check at the head of
#      step_provision_postgres that fails fast with a clear log line
#      if the env handoff regresses, BEFORE Colima is started or any
#      docker call is made.
#   5. No log line in postinstall.sh that interpolates a secret value
#      (no `log .*\${MG_DB_PASSWORD}.*`, etc.).
#   6. Runtime: invoking step_drop_dotenv in a stripped-env subshell
#      sets MG_DB_PASSWORD in the parent shell after the function
#      returns (the actual bug).
#   7. Runtime: the install-log file written by the function does NOT
#      contain the generated secret values.
#   8. The P-022 audit marker is present in postinstall.sh so future
#      sessions can find this fix from the script itself.
#   9. bash -n parse on postinstall.sh.
#
# Run from repo root:
#     bash tests/installer/test_postinstall_env_handoff.sh
#
# Exits 0 on success, non-zero with a fail count on regression.
# Requires: bash 4+, grep, awk, openssl.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

POSTINSTALL="installer/macos-pkg/scripts/postinstall.sh"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }

section() { echo; echo "## $*"; }

# ---------------------------------------------------------------------
section "1. step_drop_dotenv does NOT declare secrets as 'local'"
# ---------------------------------------------------------------------
# Extract the function body and assert the legacy `local
# MG_DB_PASSWORD ...` line is gone. A `local` here is the original
# bug — the trailing `export` only sets the EXPORT attribute on the
# local frame, the variable is dead by the time the function returns.
drop_body="$(/usr/bin/awk '/^step_drop_dotenv\(\)/,/^}$/' "$POSTINSTALL")"

if printf '%s\n' "$drop_body" \
        | /usr/bin/grep -E '^[[:space:]]*local[[:space:]]+MG_DB_PASSWORD' \
        >/dev/null 2>&1; then
    fail "step_drop_dotenv still declares MG_DB_PASSWORD as local — fix is incomplete"
else
    ok "step_drop_dotenv does not declare MG_DB_PASSWORD local"
fi

if printf '%s\n' "$drop_body" \
        | /usr/bin/grep -E '^[[:space:]]*local[[:space:]]+.*CATALOG_API_KEY' \
        >/dev/null 2>&1; then
    fail "step_drop_dotenv still declares CATALOG_API_KEY as local"
else
    ok "step_drop_dotenv does not declare CATALOG_API_KEY local"
fi

if printf '%s\n' "$drop_body" \
        | /usr/bin/grep -E '^[[:space:]]*local[[:space:]]+.*INTERNAL_API_SECRET' \
        >/dev/null 2>&1; then
    fail "step_drop_dotenv still declares INTERNAL_API_SECRET as local"
else
    ok "step_drop_dotenv does not declare INTERNAL_API_SECRET local"
fi

# ---------------------------------------------------------------------
section "2. step_drop_dotenv exports every helper-required env key"
# ---------------------------------------------------------------------
# The downstream consumers are:
#   * lib/install_colima.sh::provision_postgres → MG_DB_PASSWORD
#   * postinstall.sh::step_apply_migrations → uses `psql -U mg ...`
#     directly via docker exec (no env), but new helpers MAY read
#     PGUSER / PGDATABASE.
#   * postinstall.sh::step_provision_catalog_db_and_seed → same
#     contract.
# Asserting the explicit export list catches "I added a new key to
# the .env but forgot to export it" regressions immediately.
required_exports=(
    "MG_DB_PASSWORD"
    "CATALOG_API_KEY"
    "INTERNAL_API_SECRET"
    "GUARDIAN_PG_HOST"
    "GUARDIAN_PG_PORT"
    "GUARDIAN_PG_USER"
    "GUARDIAN_PG_PASSWORD"
    "GUARDIAN_PG_DBNAME"
    "GUARDIAN_PG_CATALOG_DBNAME"
    "PGHOST"
    "PGPORT"
    "PGUSER"
    "PGDATABASE"
)
# Collapse `export … \<NL>…` continuations into a single logical line
# so a single grep can verify each key appears on an export statement.
drop_exports="$(printf '%s\n' "$drop_body" \
    | /usr/bin/awk '
        /\\$/ { sub(/\\$/, ""); buf = buf $0; next }
        { print buf $0; buf = "" }')"
for key in "${required_exports[@]}"; do
    # Match: line begins with `export`, then anywhere in the (already
    # collapsed) line the key appears as a whole word — either the
    # first key on the line (`export ${key} …`) or after whitespace
    # (`export … ${key}`).
    if printf '%s\n' "$drop_exports" \
            | /usr/bin/grep -E "^[[:space:]]*export([[:space:]]|.*[[:space:]])${key}([[:space:]]|$)" \
            >/dev/null 2>&1; then
        ok "step_drop_dotenv exports ${key}"
    else
        fail "step_drop_dotenv does not export ${key}"
    fi
done

# ---------------------------------------------------------------------
section "3. step_drop_dotenv emits a 'loaded generated env keys' log"
# ---------------------------------------------------------------------
# Names of keys MUST appear, values MUST NOT. The function generates
# secrets via openssl rand -hex 32 — so any 64-hex-char run inside a
# log line in step_drop_dotenv would be a leak.
if printf '%s\n' "$drop_body" \
        | /usr/bin/grep -E 'loaded generated env keys' >/dev/null 2>&1; then
    ok "step_drop_dotenv logs 'loaded generated env keys' marker"
else
    fail "step_drop_dotenv missing 'loaded generated env keys' log line"
fi

# Check the log line names MG_DB_PASSWORD as a key (not a value).
if printf '%s\n' "$drop_body" \
        | /usr/bin/awk '/loaded generated env keys/,/^[[:space:]]*[a-zA-Z_][a-zA-Z0-9_]*[[:space:]]*[(=]|^}$/' \
        | /usr/bin/grep -q '"MG_DB_PASSWORD'; then
    ok "log line lists MG_DB_PASSWORD as a key name"
else
    fail "log line does not list MG_DB_PASSWORD"
fi

# ---------------------------------------------------------------------
section "4. step_provision_postgres has fail-fast preflight check"
# ---------------------------------------------------------------------
prov_body="$(/usr/bin/awk '/^step_provision_postgres\(\)/,/^}$/' "$POSTINSTALL")"
if printf '%s\n' "$prov_body" \
        | /usr/bin/grep -q 'MG_DB_PASSWORD'; then
    ok "step_provision_postgres references MG_DB_PASSWORD (preflight check)"
else
    fail "step_provision_postgres has no MG_DB_PASSWORD preflight"
fi
if printf '%s\n' "$prov_body" \
        | /usr/bin/grep -q 'fail 31'; then
    ok "step_provision_postgres exits 31 on missing keys"
else
    fail "step_provision_postgres has no fail 31 on missing keys"
fi

# Preflight must precede the actual install_colima_runtime invocation
# so we never touch system state. Strip comment lines (^[[:space:]]*#)
# before the ordering check so block-comment mentions of these symbols
# don't confuse it. Match the executable invocation specifically:
# `install_colima_runtime || fail 31 …`.
order_lines="$(printf '%s\n' "$prov_body" \
    | /usr/bin/grep -vE '^[[:space:]]*#' \
    | /usr/bin/grep -nE 'fail 31 "step_drop_dotenv|install_colima_runtime[[:space:]]*\|\|')"
preflight_line="$(printf '%s\n' "$order_lines" \
    | /usr/bin/grep -E 'fail 31 "step_drop_dotenv' \
    | /usr/bin/head -n1 \
    | /usr/bin/awk -F: '{ print $1 }')"
runtime_line="$(printf '%s\n' "$order_lines" \
    | /usr/bin/grep -E 'install_colima_runtime[[:space:]]*\|\|' \
    | /usr/bin/head -n1 \
    | /usr/bin/awk -F: '{ print $1 }')"
if [[ -n "${preflight_line}" && -n "${runtime_line}" \
        && "${preflight_line}" -lt "${runtime_line}" ]]; then
    ok "preflight 'fail 31' precedes install_colima_runtime invocation"
else
    fail "preflight ordering wrong: preflight=${preflight_line:-?} runtime=${runtime_line:-?}"
fi

# ---------------------------------------------------------------------
section "5. No secret-value log lines anywhere in postinstall.sh"
# ---------------------------------------------------------------------
# These would print the secret value into the install log:
#   log "...${MG_DB_PASSWORD}..."
#   log "...${CATALOG_API_KEY}..."
#   log "...${INTERNAL_API_SECRET}..."
# The grep pattern is a single ERE that matches any of the three.
leak_pattern='log[[:space:]]+.*\$\{(MG_DB_PASSWORD|CATALOG_API_KEY|INTERNAL_API_SECRET)'
n_leaks="$(/usr/bin/grep -cE "$leak_pattern" "$POSTINSTALL" || true)"
if [[ "${n_leaks:-0}" -eq 0 ]]; then
    ok "no log lines interpolate secret values"
else
    fail "${n_leaks} log line(s) interpolate secret values — leak risk"
fi

# Same check for the GUARDIAN_PG_PASSWORD alias.
n_leaks2="$(/usr/bin/grep -cE 'log[[:space:]]+.*\$\{GUARDIAN_PG_PASSWORD' "$POSTINSTALL" || true)"
if [[ "${n_leaks2:-0}" -eq 0 ]]; then
    ok "no log lines interpolate GUARDIAN_PG_PASSWORD"
else
    fail "${n_leaks2} log line(s) interpolate GUARDIAN_PG_PASSWORD — leak risk"
fi

# ---------------------------------------------------------------------
section "6. Runtime: step_drop_dotenv exports MG_DB_PASSWORD to caller"
# ---------------------------------------------------------------------
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Build an isolated MG_INSTALL_ROOT and install log so the function
# can run without touching real state.
FAKE_ROOT="${TMP}/mg_install_root"
mkdir -p "${FAKE_ROOT}"
FAKE_LOG="${TMP}/install.log"
: > "${FAKE_LOG}"

# Driver: source ONLY the helper bits we need from postinstall.sh +
# step_drop_dotenv, then fire it and report whether the export
# survived.
DRIVER="${TMP}/drive.sh"
{
    echo '#!/usr/bin/env bash'
    echo 'set -uo pipefail'
    echo "export MG_INSTALL_LOG='${FAKE_LOG}'"
    echo "export MG_INSTALL_ROOT='${FAKE_ROOT}'"
    echo "export MG_INSTALL_OPERATOR_USER='$(/usr/bin/id -un)'"
    echo "export MG_INSTALL_RAM_TIER=16"
    echo "export MG_INSTALL_LLM_MODEL='llama3.2:3b'"
    # Customer-info values that step_drop_dotenv expects.
    echo "export CUSTOMER_NAME='Test Site'"
    echo "export AMS_URL='https://api.bixbit.io/api/v1'"
    echo "export AMS_EMAIL='test@example.com'"
    echo "export AMS_PASSWORD='dummy'"
    echo "export AMS_WORKSPACE_ID='1'"
    echo "export SLACK_WEBHOOK_URL='https://hooks.slack.com/services/x/y/z'"
    echo "export SLACK_BOT_TOKEN='xoxb-dummy'"
    echo "export SLACK_SIGNING_SECRET='dummy'"
    echo "export SLACK_APP_TOKEN=''"
    echo "export AUTHORIZED_SLACK_USER_IDS='U123'"
    echo "export SCAN_INTERVAL='300'"
    echo "export MG_DRY_RUN='true'"
    # We need `chown` to be a no-op (the test user is not root and
    # cannot chown to ${MG_INSTALL_OPERATOR_USER}:staff). Override it
    # at the function level so the function body's invocation hits
    # the function, not /usr/bin/chown.
    echo 'chown() { return 0; }'
    echo 'export -f chown'
    # Stub log() so we collect output for inspection.
    echo "log() { echo \"\$*\" >> '${FAKE_LOG}'; }"
    # Stub fail() so a real failure surfaces as a clear test error.
    echo "fail() { echo \"FAIL_STUB_HIT(\$1): \${*:2}\" >&2; exit 99; }"
    # Extract step_drop_dotenv verbatim from postinstall.sh.
    /usr/bin/awk '/^step_drop_dotenv\(\)/,/^}$/' "$POSTINSTALL"
    # Invoke and report the post-call state.
    cat <<'POST'
unset MG_DB_PASSWORD CATALOG_API_KEY INTERNAL_API_SECRET
unset GUARDIAN_PG_USER GUARDIAN_PG_DBNAME PGUSER PGDATABASE
step_drop_dotenv
echo "POST_MG_DB_PASSWORD_LEN=${#MG_DB_PASSWORD}"
echo "POST_CATALOG_API_KEY_LEN=${#CATALOG_API_KEY}"
echo "POST_INTERNAL_API_SECRET_LEN=${#INTERNAL_API_SECRET}"
echo "POST_GUARDIAN_PG_USER=${GUARDIAN_PG_USER:-<unset>}"
echo "POST_PGUSER=${PGUSER:-<unset>}"
echo "POST_GUARDIAN_PG_DBNAME=${GUARDIAN_PG_DBNAME:-<unset>}"
POST
} > "$DRIVER"

if ! bash -n "$DRIVER" 2>/dev/null; then
    fail "extracted step_drop_dotenv driver has syntax errors"
else
    ok "extracted step_drop_dotenv driver parses"
fi

OUT="${TMP}/out.txt"
ERR="${TMP}/err.txt"
if bash "$DRIVER" >"$OUT" 2>"$ERR"; then
    ok "step_drop_dotenv ran cleanly under stripped-env driver"
else
    fail "step_drop_dotenv driver exited non-zero. stderr:"
    cat "$ERR" >&2
fi

# Asserts on captured post-call state.
mg_len="$(/usr/bin/grep '^POST_MG_DB_PASSWORD_LEN=' "$OUT" \
            | /usr/bin/awk -F= '{ print $2 }')"
if [[ "${mg_len:-0}" -ge 32 ]]; then
    ok "MG_DB_PASSWORD survived function return (length=${mg_len})"
else
    fail "MG_DB_PASSWORD did NOT survive function return (length=${mg_len:-0}) — fix is broken"
fi

cat_len="$(/usr/bin/grep '^POST_CATALOG_API_KEY_LEN=' "$OUT" \
            | /usr/bin/awk -F= '{ print $2 }')"
if [[ "${cat_len:-0}" -ge 32 ]]; then
    ok "CATALOG_API_KEY survived function return (length=${cat_len})"
else
    fail "CATALOG_API_KEY did NOT survive function return"
fi

int_len="$(/usr/bin/grep '^POST_INTERNAL_API_SECRET_LEN=' "$OUT" \
            | /usr/bin/awk -F= '{ print $2 }')"
if [[ "${int_len:-0}" -ge 32 ]]; then
    ok "INTERNAL_API_SECRET survived function return (length=${int_len})"
else
    fail "INTERNAL_API_SECRET did NOT survive function return"
fi

if /usr/bin/grep -q '^POST_GUARDIAN_PG_USER=mg$' "$OUT"; then
    ok "GUARDIAN_PG_USER=mg survived"
else
    fail "GUARDIAN_PG_USER lost or wrong value"
fi
if /usr/bin/grep -q '^POST_PGUSER=mg$' "$OUT"; then
    ok "PGUSER=mg survived"
else
    fail "PGUSER lost or wrong value"
fi
if /usr/bin/grep -q '^POST_GUARDIAN_PG_DBNAME=mining_guardian$' "$OUT"; then
    ok "GUARDIAN_PG_DBNAME=mining_guardian survived"
else
    fail "GUARDIAN_PG_DBNAME lost or wrong value"
fi

# ---------------------------------------------------------------------
section "7. Runtime: install log contains key names but NOT secret values"
# ---------------------------------------------------------------------
# The .env file is the only place the secret values should appear.
# Read it first so we have the actual generated values to scan for.
ENV_FILE="${FAKE_ROOT}/.env"
if [[ -r "${ENV_FILE}" ]]; then
    ok ".env file written at expected location"
else
    fail ".env file not written; cannot verify leak protection"
fi

# Extract the generated MG_DB_PASSWORD value from .env and grep for it
# in the install log. A non-zero match count means the secret leaked.
gen_pwd="$(/usr/bin/grep '^MG_DB_PASSWORD=' "${ENV_FILE}" 2>/dev/null \
            | /usr/bin/sed -E 's/^MG_DB_PASSWORD=//')"
if [[ -n "${gen_pwd}" ]]; then
    if /usr/bin/grep -q -- "${gen_pwd}" "${FAKE_LOG}"; then
        fail "install log CONTAINS the generated MG_DB_PASSWORD value (LEAK)"
    else
        ok "install log does not contain the generated MG_DB_PASSWORD value"
    fi
else
    fail "could not extract MG_DB_PASSWORD from .env to verify leak protection"
fi

gen_cat="$(/usr/bin/grep '^CATALOG_API_KEY=' "${ENV_FILE}" 2>/dev/null \
            | /usr/bin/sed -E 's/^CATALOG_API_KEY=//')"
if [[ -n "${gen_cat}" ]]; then
    if /usr/bin/grep -q -- "${gen_cat}" "${FAKE_LOG}"; then
        fail "install log CONTAINS the generated CATALOG_API_KEY value (LEAK)"
    else
        ok "install log does not contain the generated CATALOG_API_KEY value"
    fi
fi

gen_int="$(/usr/bin/grep '^INTERNAL_API_SECRET=' "${ENV_FILE}" 2>/dev/null \
            | /usr/bin/sed -E 's/^INTERNAL_API_SECRET=//')"
if [[ -n "${gen_int}" ]]; then
    if /usr/bin/grep -q -- "${gen_int}" "${FAKE_LOG}"; then
        fail "install log CONTAINS the generated INTERNAL_API_SECRET value (LEAK)"
    else
        ok "install log does not contain the generated INTERNAL_API_SECRET value"
    fi
fi

# Install log must contain the key-names log marker (positive control).
if /usr/bin/grep -q 'loaded generated env keys' "${FAKE_LOG}"; then
    ok "install log contains 'loaded generated env keys' marker"
else
    fail "install log missing 'loaded generated env keys' marker"
fi

# ---------------------------------------------------------------------
section "8. P-022 audit marker present in postinstall.sh"
# ---------------------------------------------------------------------
if /usr/bin/grep -q 'P-022' "$POSTINSTALL"; then
    ok "P-022 marker present"
else
    fail "P-022 marker missing"
fi

# ---------------------------------------------------------------------
section "9. bash -n parse on postinstall.sh"
# ---------------------------------------------------------------------
if bash -n "$POSTINSTALL" 2>/dev/null; then
    ok "postinstall.sh parses cleanly"
else
    fail "postinstall.sh has syntax errors"
fi

# ---------------------------------------------------------------------
echo
echo "================================================================"
echo "Summary: pass=${pass_count} fail=${fail_count}"
echo "================================================================"

if (( fail_count > 0 )); then
    exit 1
fi
exit 0
