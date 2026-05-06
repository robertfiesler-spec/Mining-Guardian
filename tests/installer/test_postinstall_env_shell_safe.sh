#!/usr/bin/env bash
# tests/installer/test_postinstall_env_shell_safe.sh
#
# D-18 P-029 (2026-05-06) — postinstall.sh::step_drop_dotenv must write
# a .env file whose values round-trip exactly under the launcher
# wrappers' `set -a; source "${ENV_FILE}"; set +a` pattern, regardless
# of what shell-trap characters appear in the customer-supplied
# values.
#
# Background: round-9b smoke on the customer Mac mini (post-23a5af7
# install, the build that finally cleared P-028) hit
#     /Library/Application Support/MiningGuardian/.env: line 47:
#     D: command not found
# from every LaunchDaemon launcher. Root cause: customer name `R & D`
# was written into the heredoc as `MG_CUSTOMER_NAME=R & D`. With
# `set -a; source` bash interpreted the line as `MG_CUSTOMER_NAME=R`
# (assignment) followed by `&` (background) and `D` (a command). All
# 10 services exited 127 and crash-looped. Manually editing to
# `MG_CUSTOMER_NAME='R & D'` was confirmed to fix every wrapper.
#
# The fix introduces `_shq` — a shell-quoting helper that single-quotes
# every value and escapes embedded single quotes via the standard
# `'\''` close-reopen idiom — and pre-quotes every interpolated value
# (CUSTOMER_NAME, AMS_*, SLACK_*, MG_DB_PASSWORD, ...) into a *_Q
# variable BEFORE the heredoc. This test asserts the fix shape both
# statically (the source has the helper, the heredoc uses *_Q) and
# functionally (an extracted step_drop_dotenv invocation, fed a
# pathological customer name + every common shell-trap character,
# produces an .env that round-trips through `set -a; source`).
#
# Run from repo root:
#     bash tests/installer/test_postinstall_env_shell_safe.sh
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
section "1. postinstall.sh exists and parses"
# ---------------------------------------------------------------------
if [[ -r "$POSTINSTALL" ]]; then
    ok "$POSTINSTALL present"
else
    fail "$POSTINSTALL missing"
    echo "  Cannot continue." >&2
    exit 2
fi

if bash -n "$POSTINSTALL" 2>/dev/null; then
    ok "postinstall.sh parses cleanly"
else
    fail "postinstall.sh has bash syntax errors"
fi

# ---------------------------------------------------------------------
section "2. P-029 audit marker is present"
# ---------------------------------------------------------------------
if /usr/bin/grep -q 'P-029' "$POSTINSTALL"; then
    ok "P-029 marker present in postinstall.sh"
else
    fail "P-029 marker missing — future regressions will not be findable"
fi

# ---------------------------------------------------------------------
section "3. _shq helper is defined"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE '^_shq\(\)' "$POSTINSTALL"; then
    ok "_shq() defined"
else
    fail "_shq() helper not defined — P-029 fix is missing"
fi

# Helper must use the canonical close-reopen escape — the only POSIX-
# portable form bash will not interpret further.
if /usr/bin/grep -q "v//\\\\'/\\\\'\\\\\\\\'\\\\'" "$POSTINSTALL" \
        || /usr/bin/awk '/^_shq\(\)/,/^}$/' "$POSTINSTALL" \
            | /usr/bin/grep -qE "v//\\\\'/"; then
    ok "_shq uses single-quote close-reopen escape (\\'\\\\'\\')"
else
    fail "_shq does not use the canonical close-reopen escape"
fi

# ---------------------------------------------------------------------
section "4. step_drop_dotenv pre-quotes every customer-tunable value"
# ---------------------------------------------------------------------
drop_body="$(/usr/bin/awk '/^step_drop_dotenv\(\)/,/^}$/' "$POSTINSTALL")"

# Every key whose value comes from operator/customer input or openssl
# rand MUST appear on a `_Q="$(_shq "..."` line so the heredoc never
# sees the raw bytes.
required_quoted=(
    "CUSTOMER_NAME_Q"
    "AMS_URL_Q"
    "AMS_EMAIL_Q"
    "AMS_PASSWORD_Q"
    "AMS_WORKSPACE_ID_Q"
    "SLACK_WEBHOOK_URL_Q"
    "SLACK_BOT_TOKEN_Q"
    "SLACK_SIGNING_SECRET_Q"
    "SLACK_APP_TOKEN_Q"
    "AUTHORIZED_SLACK_USER_IDS_Q"
    "SCAN_INTERVAL_Q"
    "MG_DRY_RUN_Q"
    "_MG_PWD_Q"
    "_CAT_KEY_Q"
    "_INT_SEC_Q"
    "MG_INSTALL_RAM_TIER_Q"
    "MG_INSTALL_LLM_MODEL_Q"
)
for k in "${required_quoted[@]}"; do
    if printf '%s\n' "$drop_body" \
            | /usr/bin/grep -qE "${k}=\"\\\$\\(_shq "; then
        ok "step_drop_dotenv computes ${k} via _shq"
    else
        fail "step_drop_dotenv does not compute ${k} via _shq"
    fi
done

# ---------------------------------------------------------------------
section "5. .env heredoc references ONLY the *_Q twins for trap-prone keys"
# ---------------------------------------------------------------------
# Extract the heredoc body between `cat > "$env_file" <<EOF` and the
# closing `EOF` line. Any reference to a raw customer-supplied
# variable (without the _Q suffix) is a regression.
heredoc="$(printf '%s\n' "$drop_body" \
    | /usr/bin/awk '/cat > "\$env_file" <<EOF/{flag=1; next} /^EOF$/{flag=0} flag')"

# These are the keys that had the bug. Heredoc must reference *_Q only.
trap_prone_lines=(
    "CUSTOMER_NAME"
    "AMS_URL"
    "AMS_EMAIL"
    "AMS_PASSWORD"
    "AMS_WORKSPACE_ID"
    "SLACK_WEBHOOK_URL"
    "SLACK_BOT_TOKEN"
    "SLACK_SIGNING_SECRET"
    "SLACK_APP_TOKEN"
    "AUTHORIZED_SLACK_USER_IDS"
    "MG_DB_PASSWORD"
    "CATALOG_API_KEY"
    "INTERNAL_API_SECRET"
    "MG_DRY_RUN"
    "SCAN_INTERVAL"
)
for k in "${trap_prone_lines[@]}"; do
    # Heredoc lines look like e.g. `MG_CUSTOMER_NAME=${CUSTOMER_NAME_Q}`.
    # Find every line that uses ${KEY...} and verify it's the _Q form.
    raw_refs="$(printf '%s\n' "$heredoc" \
        | /usr/bin/grep -E "\\\$\\{${k}([^_A-Z]|$)" \
        | /usr/bin/grep -vE "\\\$\\{${k}_Q\\}" || true)"
    # `\\\$\\{${k}([^_A-Z]|$)` matches a `${KEY}` use that is not
    # `${KEY_<MORE>}` — i.e. a use of the raw variable. Filter out the
    # _Q form to find regressions.
    if [[ -z "${raw_refs}" ]]; then
        ok ".env heredoc only references ${k}_Q (no raw \${${k}})"
    else
        fail ".env heredoc still references raw \${${k}}: ${raw_refs}"
    fi
done

# ---------------------------------------------------------------------
section "6. Functional smoke — _shq round-trips arbitrary input under set -a; source"
# ---------------------------------------------------------------------
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Extract _shq verbatim from postinstall.sh into a tiny driver that
# round-trips a list of pathological inputs through .env and back.
DRIVER="${TMP}/shq_drive.sh"
{
    echo '#!/usr/bin/env bash'
    echo 'set -uo pipefail'
    /usr/bin/awk '/^_shq\(\)/,/^}$/' "$POSTINSTALL"
    cat <<'POST'
inputs=(
    "R & D"
    "ACME, Inc."
    "miner@home"
    'back`tick'
    'double"quote'
    "single'quote"
    'back\slash'
    "semi;colon"
    "pipe|char"
    " leading space"
    "trailing space "
    "  spaces  around  "
    'glob*?[abc]'
    'dollar$VAR'
    "(parens)"
    "<redirect>"
    "{braces}"
    "tab	here"
    "Plain"
    ""
    "double && amp; nest"
    "newline-free \\n literal"
)
ENVF="$1"
all_ok=1
i=0
for v in "${inputs[@]}"; do
    q="$(_shq "$v")"
    printf 'TESTKEY=%s\n' "$q" > "$ENVF"
    unset TESTKEY
    set -a
    # shellcheck disable=SC1090
    source "$ENVF" 2>/dev/null || { echo "SOURCE_FAIL idx=$i value=|$v| q=|$q|"; all_ok=0; set +a; i=$((i+1)); continue; }
    set +a
    if [[ "${TESTKEY-}" != "$v" ]]; then
        echo "ROUNDTRIP_FAIL idx=$i value=|$v| got=|${TESTKEY-<unset>}| q=|$q|"
        all_ok=0
    fi
    i=$((i+1))
done
if (( all_ok )); then
    echo "ALL_ROUNDTRIP_OK count=${#inputs[@]}"
else
    exit 1
fi
POST
} > "$DRIVER"

if bash -n "$DRIVER" 2>/dev/null; then
    ok "extracted _shq driver parses"
else
    fail "extracted _shq driver has bash syntax errors"
    cat "$DRIVER" >&2
fi

if out="$(bash "$DRIVER" "${TMP}/test.env" 2>&1)"; then
    if echo "$out" | /usr/bin/grep -q '^ALL_ROUNDTRIP_OK '; then
        ok "_shq round-trips every pathological input under set -a; source"
    else
        fail "_shq output unexpected: $out"
    fi
else
    fail "_shq round-trip driver exited non-zero. output:"
    echo "$out" >&2
fi

# ---------------------------------------------------------------------
section "7. Functional smoke — step_drop_dotenv with CUSTOMER_NAME='R & D'"
# ---------------------------------------------------------------------
# This is the actual customer-Mini failure repro, run end-to-end against
# an extracted step_drop_dotenv. Asserts the produced .env can be
# `set -a; source`d without error and round-trips MG_CUSTOMER_NAME.
FAKE_ROOT="${TMP}/install_root"
mkdir -p "$FAKE_ROOT"
FAKE_LOG="${TMP}/install.log"
: > "$FAKE_LOG"

DRIVER2="${TMP}/dotenv_drive.sh"
{
    echo '#!/usr/bin/env bash'
    echo 'set -uo pipefail'
    echo "export MG_INSTALL_LOG='${FAKE_LOG}'"
    echo "export MG_INSTALL_ROOT='${FAKE_ROOT}'"
    echo "export MG_INSTALL_OPERATOR_USER='$(/usr/bin/id -un)'"
    echo "export MG_INSTALL_RAM_TIER=24"
    echo "export MG_INSTALL_LLM_MODEL='qwen2.5:14b-instruct-q4_K_M'"
    # Pathological customer values — every documented trap character.
    echo 'export CUSTOMER_NAME="R & D"'
    echo "export AMS_URL='https://ams.example.com/api/v1'"
    echo "export AMS_EMAIL='ops+rd@example.com'"
    # Password may contain shell-traps; SLACK_BOT_TOKEN starts with xoxb-
    # but mid-string trap chars are still legal. Use single-quoted bash
    # string assembly so `$(rm)` in the test value stays literal — the
    # heredoc is fed to a subshell that should NOT execute it.
    echo "export AMS_PASSWORD='p@ss & word'\"'\"'\$(rm)'"
    echo "export AMS_WORKSPACE_ID='119'"
    echo "export SLACK_WEBHOOK_URL='https://hooks.slack.com/services/T/B/Z'"
    echo "export SLACK_BOT_TOKEN='xoxb-1-2-abc'"
    echo "export SLACK_SIGNING_SECRET='secret with & ampersand'"
    echo "export SLACK_APP_TOKEN=''"
    echo "export AUTHORIZED_SLACK_USER_IDS='U07AGTT8CLD,U0APQ4VDKGC'"
    echo "export SCAN_INTERVAL='300'"
    echo "export MG_DRY_RUN='true'"
    # chown is a no-op here — test user is not root and cannot chown
    # arbitrary owners. Mock log() so we collect output.
    echo 'chown() { return 0; }'
    echo 'export -f chown'
    echo "log() { echo \"\$*\" >> '${FAKE_LOG}'; }"
    echo "fail() { echo \"FAIL_STUB(\$1): \${*:2}\" >&2; exit 99; }"
    # Pull the helper + the function bodies we need.
    /usr/bin/awk '/^_shq\(\)/,/^}$/' "$POSTINSTALL"
    /usr/bin/awk '/^step_drop_dotenv\(\)/,/^}$/' "$POSTINSTALL"
    cat <<'POST'
step_drop_dotenv
echo "DOTENV_WROTE_OK"
POST
} > "$DRIVER2"

if bash -n "$DRIVER2" 2>/dev/null; then
    ok "extracted step_drop_dotenv driver parses"
else
    fail "extracted step_drop_dotenv driver has bash syntax errors"
fi

OUT2="${TMP}/dotenv_out.txt"
if bash "$DRIVER2" >"$OUT2" 2>&1; then
    if /usr/bin/grep -q '^DOTENV_WROTE_OK$' "$OUT2"; then
        ok "step_drop_dotenv ran cleanly under R & D customer name"
    else
        fail "step_drop_dotenv did not reach success marker. output:"
        cat "$OUT2" >&2
    fi
else
    fail "step_drop_dotenv driver exited non-zero with R & D input. output:"
    cat "$OUT2" >&2
fi

ENV_FILE="${FAKE_ROOT}/.env"
if [[ -r "$ENV_FILE" ]]; then
    ok ".env file written at expected location"
else
    fail ".env file was not written"
    echo "Cannot continue." >&2
    echo
    echo "================================================================"
    echo "Summary: pass=${pass_count} fail=${fail_count}"
    echo "================================================================"
    exit 1
fi

# Source the produced .env in a stripped subshell and verify every
# pathological value round-trips. This is the EXACT operation the
# launcher wrappers do (`set -a; source "${ENV_FILE}"; set +a`).
ROUND="${TMP}/round.sh"
{
    echo '#!/usr/bin/env bash'
    echo 'set -uo pipefail'
    echo "set -a"
    echo "# shellcheck disable=SC1090"
    echo "source '${ENV_FILE}' 2>'${TMP}/source.err'"
    echo "rc=\$?"
    echo "set +a"
    cat <<'POST'
if (( rc != 0 )); then
    echo "SOURCE_FAILED rc=$rc"
    cat "$1" >&2
    exit 2
fi
echo "MG_CUSTOMER_NAME=|${MG_CUSTOMER_NAME-<unset>}|"
echo "AMS_PASSWORD=|${AMS_PASSWORD-<unset>}|"
echo "SLACK_SIGNING_SECRET=|${SLACK_SIGNING_SECRET-<unset>}|"
echo "MG_DB_PASSWORD_LEN=${#MG_DB_PASSWORD}"
echo "AUTHORIZED_SLACK_USER_IDS=|${AUTHORIZED_SLACK_USER_IDS-<unset>}|"
echo "MG_DRY_RUN=|${MG_DRY_RUN-<unset>}|"
echo "SLACK_APP_TOKEN=|${SLACK_APP_TOKEN-<unset>}|"
POST
} > "$ROUND"
chmod +x "$ROUND"

ROUND_OUT="${TMP}/round.out"
if bash "$ROUND" "${TMP}/source.err" >"$ROUND_OUT" 2>&1; then
    ok "launcher-style \`set -a; source .env\` succeeded"
else
    fail "launcher-style source FAILED — this is the exact customer-Mini bug"
    cat "$ROUND_OUT" >&2
    [[ -r "${TMP}/source.err" ]] && cat "${TMP}/source.err" >&2
fi

# The big one: customer name round-trips exactly.
if /usr/bin/grep -q '^MG_CUSTOMER_NAME=|R & D|$' "$ROUND_OUT"; then
    ok "MG_CUSTOMER_NAME round-trips as 'R & D' through set -a; source"
else
    fail "MG_CUSTOMER_NAME did NOT round-trip:"
    /usr/bin/grep '^MG_CUSTOMER_NAME=' "$ROUND_OUT" >&2 || echo "  (no MG_CUSTOMER_NAME line)" >&2
fi

# AMS_PASSWORD with & ' $() round-trips. Expected literal: p@ss & word'$(rm)
expected_ams='AMS_PASSWORD=|p@ss & word'"'"'$(rm)|'
if /usr/bin/grep -qF "$expected_ams" "$ROUND_OUT"; then
    ok "AMS_PASSWORD round-trips with &, ', \$( ) chars"
else
    fail "AMS_PASSWORD did not round-trip:"
    /usr/bin/grep '^AMS_PASSWORD=' "$ROUND_OUT" >&2 || true
fi

if /usr/bin/grep -q '^SLACK_SIGNING_SECRET=|secret with & ampersand|$' "$ROUND_OUT"; then
    ok "SLACK_SIGNING_SECRET round-trips with embedded &"
else
    fail "SLACK_SIGNING_SECRET did not round-trip:"
    /usr/bin/grep '^SLACK_SIGNING_SECRET=' "$ROUND_OUT" >&2 || true
fi

if /usr/bin/grep -qE '^MG_DB_PASSWORD_LEN=(64|65)$' "$ROUND_OUT"; then
    ok "MG_DB_PASSWORD round-trips with hex shape (length 64)"
else
    fail "MG_DB_PASSWORD wrong length after round-trip:"
    /usr/bin/grep '^MG_DB_PASSWORD_LEN=' "$ROUND_OUT" >&2 || true
fi

if /usr/bin/grep -q '^MG_DRY_RUN=|true|$' "$ROUND_OUT"; then
    ok "MG_DRY_RUN round-trips"
else
    fail "MG_DRY_RUN missing or wrong"
fi

# Empty SLACK_APP_TOKEN renders as '' and round-trips to empty string,
# not the literal `''`.
if /usr/bin/grep -q '^SLACK_APP_TOKEN=||$' "$ROUND_OUT"; then
    ok "Empty SLACK_APP_TOKEN round-trips as empty string"
else
    fail "Empty SLACK_APP_TOKEN did not round-trip:"
    /usr/bin/grep '^SLACK_APP_TOKEN=' "$ROUND_OUT" >&2 || true
fi

# ---------------------------------------------------------------------
section "8. Counter-test — old unquoted heredoc style FAILS for 'R & D'"
# ---------------------------------------------------------------------
# Belt-and-suspenders: prove the test would catch the regression. Write
# an .env line in the OLD (broken) style and assert source fails
# (or at minimum mangles the value).
LEGACY="${TMP}/legacy.env"
printf 'MG_CUSTOMER_NAME=%s\n' "R & D" > "$LEGACY"
LEGACY_OUT="${TMP}/legacy.out"
if (
    set -uo pipefail
    set -a
    # shellcheck disable=SC1090
    source "$LEGACY" 2>"${TMP}/legacy.err"
    set +a
    echo "MG_CUSTOMER_NAME=|${MG_CUSTOMER_NAME-<unset>}|"
) >"$LEGACY_OUT" 2>&1; then
    # If source returned 0 but value is mangled, that is also a regression
    if /usr/bin/grep -q '^MG_CUSTOMER_NAME=|R & D|$' "$LEGACY_OUT"; then
        fail "counter-test broken: legacy unquoted form unexpectedly round-tripped 'R & D'"
    else
        ok "counter-test confirms: legacy unquoted form does NOT round-trip 'R & D'"
    fi
else
    ok "counter-test confirms: legacy unquoted form fails to source under set -e equivalent"
fi

# ---------------------------------------------------------------------
section "9. step_reconcile_postgres_password defined and ordered correctly"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE '^step_reconcile_postgres_password\(\)' "$POSTINSTALL"; then
    ok "step_reconcile_postgres_password() defined"
else
    fail "step_reconcile_postgres_password() missing — P-029 stale-password fix not in"
fi

# It must be invoked from main(), and AFTER step_provision_postgres but
# BEFORE step_apply_migrations (so migrations run against the correct
# password — they use unix-socket peer auth so are insensitive, but
# ordering still matters for any future migration that uses TCP).
main_body="$(/usr/bin/awk '/^main\(\)/,/^}$/' "$POSTINSTALL")"
prov_line="$(printf '%s\n' "$main_body" | /usr/bin/grep -nE '^[[:space:]]*step_provision_postgres[[:space:]]*$' | /usr/bin/awk -F: '{print $1}' | /usr/bin/head -n1)"
recon_line="$(printf '%s\n' "$main_body" | /usr/bin/grep -nE '^[[:space:]]*step_reconcile_postgres_password[[:space:]]*$' | /usr/bin/awk -F: '{print $1}' | /usr/bin/head -n1)"
mig_line="$(printf '%s\n' "$main_body" | /usr/bin/grep -nE '^[[:space:]]*step_apply_migrations[[:space:]]*$' | /usr/bin/awk -F: '{print $1}' | /usr/bin/head -n1)"
if [[ -n "$prov_line" && -n "$recon_line" && -n "$mig_line" \
        && "$prov_line" -lt "$recon_line" \
        && "$recon_line" -lt "$mig_line" ]]; then
    ok "main() order: provision_postgres → reconcile_postgres_password → apply_migrations"
else
    fail "main() ordering wrong: provision=$prov_line recon=$recon_line mig=$mig_line"
fi

# Reconcile must not interpolate the password value into the docker-exec
# argv (it must use stdin). A `psql -c "ALTER USER mg PASSWORD '...${MG_DB_PASSWORD}'"`
# would expose the password in `ps`.
recon_body="$(/usr/bin/awk '/^step_reconcile_postgres_password\(\)/,/^}$/' "$POSTINSTALL")"
if printf '%s\n' "$recon_body" | /usr/bin/grep -qE 'psql[[:space:]]+.*-c[[:space:]]+["'\''].*\$\{MG_DB_PASSWORD'; then
    fail "step_reconcile_postgres_password puts password on psql -c command line (visible in ps)"
else
    ok "step_reconcile_postgres_password does not put password on psql -c command line"
fi
if printf '%s\n' "$recon_body" | /usr/bin/grep -qE 'printf[[:space:]]+"ALTER USER mg WITH PASSWORD'; then
    ok "step_reconcile_postgres_password sends ALTER via stdin (printf | docker exec -i psql)"
else
    fail "step_reconcile_postgres_password does not use stdin for ALTER USER"
fi

# ---------------------------------------------------------------------
section "10. step_drop_config_json defined and ordered correctly"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE '^step_drop_config_json\(\)' "$POSTINSTALL"; then
    ok "step_drop_config_json() defined"
else
    fail "step_drop_config_json() missing — P-029 config materialization not in"
fi

cfg_line="$(printf '%s\n' "$main_body" | /usr/bin/grep -nE '^[[:space:]]*step_drop_config_json[[:space:]]*$' | /usr/bin/awk -F: '{print $1}' | /usr/bin/head -n1)"
plist_line="$(printf '%s\n' "$main_body" | /usr/bin/grep -nE '^[[:space:]]*step_install_plists_and_bootstrap[[:space:]]*$' | /usr/bin/awk -F: '{print $1}' | /usr/bin/head -n1)"
venv_line="$(printf '%s\n' "$main_body" | /usr/bin/grep -nE '^[[:space:]]*step_create_venv[[:space:]]*$' | /usr/bin/awk -F: '{print $1}' | /usr/bin/head -n1)"
if [[ -n "$cfg_line" && -n "$plist_line" \
        && "$cfg_line" -lt "$plist_line" ]]; then
    ok "main() order: step_drop_config_json runs BEFORE step_install_plists_and_bootstrap"
else
    fail "main() ordering wrong: drop_config=$cfg_line plists=$plist_line"
fi
if [[ -n "$cfg_line" && -n "$venv_line" \
        && "$venv_line" -lt "$cfg_line" ]]; then
    ok "main() order: step_create_venv runs BEFORE step_drop_config_json (venv is the python source if needed later)"
fi

# config_template.json must ship in the payload — build_pkg.sh include
# list controls this.
BUILD_PKG="installer/macos-pkg/scripts/build_pkg.sh"
if /usr/bin/grep -qE "^[[:space:]]*--include[[:space:]]+'config/\\*\\*\\*'" "$BUILD_PKG"; then
    ok "build_pkg.sh stages config/*** into payload"
else
    fail "build_pkg.sh does not stage config/*** — config template will be missing on customer Mini"
fi

# Source template must exist in the repo.
if [[ -r "${REPO_ROOT}/config/config_template.json" ]]; then
    ok "config/config_template.json present in repo"
else
    fail "config/config_template.json missing in repo"
fi

# step_drop_config_json must preserve operator-edited config.json on
# re-install (refuse to overwrite). Look for an early-return guard.
cfg_body="$(/usr/bin/awk '/^step_drop_config_json\(\)/,/^}$/' "$POSTINSTALL")"
if printf '%s\n' "$cfg_body" | /usr/bin/grep -qE 'if[[:space:]]*\[\[[[:space:]]*-f[[:space:]]+"\$dest"'; then
    ok "step_drop_config_json guards against overwriting an existing config.json"
else
    fail "step_drop_config_json has no overwrite guard — operator edits will be lost on re-install"
fi

# ---------------------------------------------------------------------
section "11. config.json materialization smoke (template + python merge)"
# ---------------------------------------------------------------------
PY3="$(command -v python3 2>/dev/null || true)"
if [[ -z "$PY3" ]]; then
    echo "  SKIP — no python3 available for config.json merge smoke"
else
    SMOKE_PAYLOAD="${TMP}/smoke_payload"
    SMOKE_ROOT="${TMP}/smoke_root"
    mkdir -p "${SMOKE_PAYLOAD}/config" "${SMOKE_ROOT}"
    cp "${REPO_ROOT}/config/config_template.json" "${SMOKE_PAYLOAD}/config/config_template.json"

    DRIVER3="${TMP}/cfg_drive.sh"
    {
        echo '#!/usr/bin/env bash'
        echo 'set -uo pipefail'
        echo "export MG_INSTALL_LOG='${FAKE_LOG}'"
        echo "export MG_INSTALL_ROOT='${SMOKE_ROOT}'"
        echo "export MG_PKG_PAYLOAD='${SMOKE_PAYLOAD}'"
        echo "export MG_INSTALL_OPERATOR_USER='$(/usr/bin/id -un)'"
        echo "export MG_DRY_RUN=true"
        echo 'install() { /usr/bin/install "$@"; }'
        echo "log() { echo \"\$*\" >> '${FAKE_LOG}'; }"
        echo "fail() { echo \"FAIL_STUB(\$1): \${*:2}\" >&2; exit 99; }"
        # Override the python resolver to use the host python3 we have.
        echo "shopt -s expand_aliases || true"
        # Patch step_drop_config_json's python resolver by exporting a
        # fake python3.12 path. Easiest: prepend a shim dir to PATH.
        SHIM_DIR="${TMP}/shim"
        mkdir -p "$SHIM_DIR"
        ln -sf "$PY3" "$SHIM_DIR/python3.12"
        echo "export PATH='${SHIM_DIR}:\$PATH'"
        /usr/bin/awk '/^step_drop_config_json\(\)/,/^}$/' "$POSTINSTALL"
        cat <<'POST'
step_drop_config_json
echo "CFG_DONE"
POST
    } > "$DRIVER3"

    CFG_OUT="${TMP}/cfg.out"
    if bash "$DRIVER3" >"$CFG_OUT" 2>&1; then
        if /usr/bin/grep -q '^CFG_DONE$' "$CFG_OUT"; then
            ok "step_drop_config_json ran cleanly"
        else
            fail "step_drop_config_json did not finish. output:"
            cat "$CFG_OUT" >&2
        fi
    else
        fail "step_drop_config_json driver exited non-zero. output:"
        cat "$CFG_OUT" >&2
    fi

    if [[ -r "${SMOKE_ROOT}/config.json" ]]; then
        ok "config.json materialized at \${MG_INSTALL_ROOT}/config.json"
    else
        fail "config.json was not written"
    fi

    # Validate JSON parses + has the expected env: placeholders.
    if "$PY3" -c "
import json, sys
cfg = json.load(open('${SMOKE_ROOT}/config.json'))
assert cfg['ams_email'] == 'env:AMS_EMAIL', cfg['ams_email']
assert cfg['ams_password'] == 'env:AMS_PASSWORD'
assert cfg['ams_workspace_id'] == 'env:AMS_WORKSPACE_ID'
assert cfg['slack_webhook_url'] == 'env:SLACK_WEBHOOK_URL'
assert cfg['slack_bot_token'] == 'env:SLACK_BOT_TOKEN'
assert cfg['dry_run'] is True
assert 'profile_map' in cfg
assert 'S19JPro' in cfg['profile_map']
assert cfg['approval_mode'] == 'manual'
print('OK')
" 2>"${TMP}/cfg.pyerr"; then
        ok "config.json has env: placeholders, profile_map, approval_mode=manual, dry_run=true"
    else
        fail "config.json shape wrong:"
        cat "${TMP}/cfg.pyerr" >&2
    fi

    # Idempotence — second run must NOT overwrite an operator-edited file.
    echo '{"operator_marker": true}' > "${SMOKE_ROOT}/config.json"
    if bash "$DRIVER3" >"$CFG_OUT" 2>&1; then
        if "$PY3" -c "
import json
cfg = json.load(open('${SMOKE_ROOT}/config.json'))
assert cfg.get('operator_marker') is True, cfg
print('OK')
" 2>/dev/null; then
            ok "step_drop_config_json preserves operator-edited config.json on re-install"
        else
            fail "step_drop_config_json clobbered operator-edited config.json"
        fi
    else
        fail "second-run driver exited non-zero"
    fi
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
