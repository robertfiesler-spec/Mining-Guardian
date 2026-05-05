#!/usr/bin/env bash
# tests/installer/test_postinstall_customer_info.sh
#
# D-18 Gap 1 — postinstall.sh customer-info Desktop conf flow + full
# .env generation (plus Integration bugs 1, 2, 4).
#
# Static checks that the conf-reading + validation + .env-shape wiring
# is correct, plus runtime checks against extracted helpers. Runs
# against the source tree only — no Mac, no Installer.app, no actual
# Postgres/Cocoa interaction. The full smoke test is the v1.0.3
# verification gate per D-18 ("clean macOS 14 VM").
#
# Run from repo root:
#     bash tests/installer/test_postinstall_customer_info.sh
#
# Exits 0 on success, non-zero on first failed assertion.
# Requires: bash 4+, shellcheck (optional), grep, awk.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

POSTINSTALL="installer/macos-pkg/scripts/postinstall.sh"
CONF_TEMPLATE="installer/macos-pkg/resources/MiningGuardian.conf.template"
SETUP="scripts/setup.sh"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }

section() { echo; echo "## $*"; }

# ---------------------------------------------------------------------
section "1. Files exist"
# ---------------------------------------------------------------------
for f in "$POSTINSTALL" "$CONF_TEMPLATE" "$SETUP"; do
    if [[ -r "$f" ]]; then
        ok "$f present"
    else
        fail "$f missing"
    fi
done

# ---------------------------------------------------------------------
section "2. bash -n syntax check"
# ---------------------------------------------------------------------
if bash -n "$POSTINSTALL" 2>/dev/null; then
    ok "postinstall.sh parses"
else
    fail "postinstall.sh has bash syntax errors"
fi

# ---------------------------------------------------------------------
section "3. shellcheck regression baseline (no NEW warnings)"
# ---------------------------------------------------------------------
# Pre-existing baseline = 3 distinct warnings:
#   SC2034 (INSTALL_KIND unused), 2× SC2024 (sudo redirect notes).
# This PR (D-18 Gap 1) MUST NOT raise the count.
if command -v shellcheck >/dev/null 2>&1; then
    pi_count="$(shellcheck "$POSTINSTALL" 2>&1 | /usr/bin/grep -cE '^In .* line [0-9]+:' || true)"
    if [[ "${pi_count:-0}" -le 3 ]]; then
        ok "postinstall.sh shellcheck warnings: ${pi_count} (≤ 3 baseline)"
    else
        fail "postinstall.sh shellcheck warnings: ${pi_count} (> 3 baseline — new warning introduced)"
    fi
else
    echo "  SKIP — shellcheck not installed"
fi

# ---------------------------------------------------------------------
section "4. step_collect_customer_info defined and ordered correctly"
# ---------------------------------------------------------------------
if /usr/bin/grep -q '^step_collect_customer_info()' "$POSTINSTALL"; then
    ok "step_collect_customer_info() defined"
else
    fail "step_collect_customer_info() missing — D-18 Gap 1 not implemented"
fi

# Must run BEFORE step_layout_install_root so a bad config aborts before
# any system-state change.
call_order="$(/usr/bin/awk '/^main\(\)/, /^}/' "$POSTINSTALL" \
    | /usr/bin/grep -oE 'step_(collect_customer_info|layout_install_root|drop_dotenv|provision_postgres)' \
    | /usr/bin/paste -sd, -)"
expected_prefix="step_collect_customer_info,step_layout_install_root,step_drop_dotenv,step_provision_postgres"
if [[ "$call_order" == "$expected_prefix" ]]; then
    ok "main() ordering: collect_customer_info → layout → drop_dotenv → provision_postgres"
else
    fail "main() ordering wrong (got '$call_order', expected '$expected_prefix')"
fi

# ---------------------------------------------------------------------
section "5. Desktop conf path is /Users/\${SUDO_USER}/Desktop/MiningGuardian.conf"
# ---------------------------------------------------------------------
if /usr/bin/grep -q 'Users/\${desktop_user}/Desktop/MiningGuardian.conf\|Users/${SUDO_USER}/Desktop/MiningGuardian.conf' "$POSTINSTALL"; then
    ok "Desktop conf path matches D-18 Gap 1 spec"
else
    fail "Desktop conf path missing or wrong"
fi

# ---------------------------------------------------------------------
section "6. Cocoa dialog on missing/invalid conf"
# ---------------------------------------------------------------------
if /usr/bin/grep -q 'osascript' "$POSTINSTALL" \
        && /usr/bin/grep -q 'display dialog' "$POSTINSTALL"; then
    ok "Cocoa dialog (osascript display dialog) present"
else
    fail "Cocoa dialog missing — D-18 Gap 1 requires Cocoa-style alert"
fi
if /usr/bin/grep -q 'fail 41 ' "$POSTINSTALL"; then
    ok "exit code 41 used for customer-info failures"
else
    fail "exit code 41 not used — D-18 Gap 1 reserves 41"
fi
if /usr/bin/grep -qE '^#[[:space:]]+41[[:space:]]+—' "$POSTINSTALL"; then
    ok "exit code 41 documented in postinstall header"
else
    fail "exit code 41 not documented in postinstall header"
fi

# ---------------------------------------------------------------------
section "7. Integration bug 1 — MG_DB_PASSWORD generated in-process"
# ---------------------------------------------------------------------
# v1.0.3 fix: postinstall calls openssl rand directly. The /tmp staging
# file is NOT consumed (the audit's old flow); v1.0.3 only scrubs it
# defensively in case a stale v1.0.2 secret remains.
if /usr/bin/grep -q 'MG_DB_PASSWORD="\$(openssl rand -hex 32)"\|MG_DB_PASSWORD="$(openssl rand -hex 32)"' "$POSTINSTALL"; then
    ok "MG_DB_PASSWORD generated via openssl rand -hex 32"
else
    fail "MG_DB_PASSWORD not generated in-process — Integration bug 1 NOT closed"
fi
if /usr/bin/grep -q 'CATALOG_API_KEY="\$(openssl rand -hex 32)"\|CATALOG_API_KEY="$(openssl rand -hex 32)"' "$POSTINSTALL"; then
    ok "CATALOG_API_KEY generated via openssl rand -hex 32"
else
    fail "CATALOG_API_KEY not generated in-process"
fi
if /usr/bin/grep -q 'INTERNAL_API_SECRET="\$(openssl rand -hex 32)"\|INTERNAL_API_SECRET="$(openssl rand -hex 32)"' "$POSTINSTALL"; then
    ok "INTERNAL_API_SECRET generated via openssl rand -hex 32"
else
    fail "INTERNAL_API_SECRET not generated in-process"
fi
# The /tmp/mg_install_env_secret consumption MUST be gone (defensive
# scrub-only is acceptable; the old `source` of it must NOT be present).
if /usr/bin/grep -q 'source "/tmp/mg_install_env_secret"\|source "$secret_file"' "$POSTINSTALL"; then
    fail "postinstall still sources /tmp/mg_install_env_secret — Integration bug 1 NOT closed"
else
    ok "no /tmp/mg_install_env_secret source — Integration bug 1 closed"
fi

# ---------------------------------------------------------------------
section "8. Integration bug 2 — both GUARDIAN_PG_USER and PGUSER present in .env"
# ---------------------------------------------------------------------
# We check the heredoc body in step_drop_dotenv writes both keys.
if /usr/bin/grep -q '^GUARDIAN_PG_USER=mg' "$POSTINSTALL"; then
    ok "GUARDIAN_PG_USER=mg in .env heredoc"
else
    fail "GUARDIAN_PG_USER not written to .env"
fi
if /usr/bin/grep -q '^PGUSER=mg' "$POSTINSTALL"; then
    ok "PGUSER=mg in .env heredoc"
else
    fail "PGUSER not written to .env — Integration bug 2 NOT closed"
fi

# ---------------------------------------------------------------------
section "9. Integration bug 4 — full .env shape matches setup.sh phase_07_secrets"
# ---------------------------------------------------------------------
# The keys below MUST appear in postinstall .env, matching phase_07_secrets.
# These are the exact LHS keys from scripts/setup.sh::phase_07_secrets that
# Python code reads at runtime.
required_env_keys=(
    "AMS_BASE_URL"
    "AMS_EMAIL"
    "AMS_PASSWORD"
    "AMS_WORKSPACE_ID"
    "GUARDIAN_PG_HOST"
    "GUARDIAN_PG_PORT"
    "GUARDIAN_PG_USER"
    "GUARDIAN_PG_PASSWORD"
    "GUARDIAN_PG_DBNAME"
    "GUARDIAN_PG_TEST_DBNAME"
    "GUARDIAN_PG_CATALOG_DBNAME"
    "SLACK_WEBHOOK_URL"
    "SLACK_BOT_TOKEN"
    "SLACK_SIGNING_SECRET"
    "SLACK_APP_TOKEN"
    "AUTHORIZED_SLACK_USER_IDS"
    "CATALOG_API_KEY"
    "INTERNAL_API_SECRET"
    "OLLAMA_HOST"
    "MG_DRY_RUN"
    "MG_SCAN_INTERVAL"
    "MG_CUSTOMER_NAME"
    "AUTO_APPROVE_ENABLED"
    "GUARDIAN_DASHBOARD_PORT"
    "GUARDIAN_APPROVAL_PORT"
    "GUARDIAN_INTELLIGENCE_PORT"
)
for key in "${required_env_keys[@]}"; do
    if /usr/bin/grep -qE "^${key}=" "$POSTINSTALL"; then
        ok "postinstall .env writes ${key}"
    else
        fail "postinstall .env missing ${key} — Integration bug 4 partial"
    fi
done

# AUTO_APPROVE_ENABLED must default to false (D-2).
if /usr/bin/grep -q '^AUTO_APPROVE_ENABLED=false' "$POSTINSTALL"; then
    ok "AUTO_APPROVE_ENABLED=false (D-2 default)"
else
    fail "AUTO_APPROVE_ENABLED is not false — D-2 violated"
fi

# ---------------------------------------------------------------------
section "10. .env file mode 0600 + ownership"
# ---------------------------------------------------------------------
if /usr/bin/grep -q 'chmod 0600 "\$env_file"' "$POSTINSTALL"; then
    ok ".env chmod 0600 (S-13 secret hygiene)"
else
    fail ".env chmod 0600 missing"
fi
# P-016: .env chown now uses the resolved $MG_INSTALL_OPERATOR_USER (from
# _resolve_install_user) instead of the brittle `${SUDO_USER:-${USER}}`
# expansion that crashed under set -u when Installer.app stripped USER.
if /usr/bin/grep -qE 'chown "\$\{MG_INSTALL_OPERATOR_USER\}:staff" "\$env_file"|chown "\$\{SUDO_USER:-\$\{USER\}\}:staff" "\$env_file"' "$POSTINSTALL"; then
    ok ".env chown to operator:staff"
else
    fail ".env chown missing"
fi

# ---------------------------------------------------------------------
section "11. Conf-template has every key validate() requires"
# ---------------------------------------------------------------------
template_required_keys=(
    "CUSTOMER_NAME"
    "AMS_URL"
    "AMS_EMAIL"
    "AMS_PASSWORD"
    "AMS_WORKSPACE_ID"
    "SLACK_WEBHOOK_URL"
    "SLACK_BOT_TOKEN"
    "SLACK_SIGNING_SECRET"
    "AUTHORIZED_SLACK_USER_IDS"
    "SLACK_APP_TOKEN"
    "SCAN_INTERVAL"
    "MG_DRY_RUN"
)
for key in "${template_required_keys[@]}"; do
    if /usr/bin/grep -qE "^${key}=" "$CONF_TEMPLATE"; then
        ok "conf template has ${key}"
    else
        fail "conf template missing ${key}"
    fi
done

# ---------------------------------------------------------------------
section "12. Validation rules match setup.sh::mg_validate_site_config (B-2)"
# ---------------------------------------------------------------------
# Spot-check that the same regex anchors live in postinstall.sh — these
# are the customer-facing rules the operator pre-trains the customer on.
expected_patterns=(
    "CUSTOMER_NAME is required."
    "AMS_URL must start with http:// or https://"
    "AMS_EMAIL must contain '@'"
    "AMS_WORKSPACE_ID must be an integer"
    "SLACK_WEBHOOK_URL must start with https://hooks.slack.com/"
    "SLACK_BOT_TOKEN must start with 'xoxb-'"
    "AUTHORIZED_SLACK_USER_IDS is required"
    "SCAN_INTERVAL must be an integer"
    "MG_DRY_RUN must be 'true' or 'false'"
)
for pat in "${expected_patterns[@]}"; do
    if /usr/bin/grep -qF "$pat" "$POSTINSTALL"; then
        ok "validation message present: ${pat:0:60}..."
    else
        fail "validation message missing: ${pat}"
    fi
done

# ---------------------------------------------------------------------
section "13. Runtime: extracted helpers _conf_source + _conf_validate"
# ---------------------------------------------------------------------
# Smoke-test the validation logic by extracting the helpers + running
# them against synthetic conf files. We extract _conf_source + _conf_validate
# from postinstall.sh, stub fail() and _conf_fail()/_cocoa_alert/log into
# something we can observe, then run a battery of cases.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

EXTRACT="${TMP}/extract.sh"
{
    echo '#!/usr/bin/env bash'
    echo 'set -uo pipefail'
    echo 'log() { :; }'
    echo '_cocoa_alert() { :; }'
    echo 'fail() { echo "FAIL_CODE=$1" >&2; echo "FAIL_MSG=$2" >&2; exit "$1"; }'
    echo '_conf_fail() { fail 41 "$1"; }'
    # Extract _conf_source and _conf_validate function bodies from postinstall.
    /usr/bin/awk '
        /^_conf_source\(\)/        { capture=1 }
        capture                    { print }
        capture && /^}$/           { capture=0 }
    ' "$POSTINSTALL"
    /usr/bin/awk '
        /^_conf_validate\(\)/      { capture=1 }
        capture                    { print }
        capture && /^}$/           { capture=0 }
    ' "$POSTINSTALL"
    # Driver — read conf path from $1, run source + validate, exit 0 if both pass.
    cat <<'DRIVER'
_main() {
    _conf_source "$1"
    _conf_validate
    echo "OK"
}
_main "$@"
DRIVER
} > "$EXTRACT"
chmod +x "$EXTRACT"

# Sanity: extracted file parses.
if bash -n "$EXTRACT" 2>/dev/null; then
    ok "extracted helpers parse"
else
    fail "extracted helpers have syntax errors"
fi

# 13a. Valid conf passes validation.
GOOD_CONF="${TMP}/good.conf"
cat > "$GOOD_CONF" <<EOF
CUSTOMER_NAME="Acme Mine I"
AMS_URL="https://api.bixbit.io/api/v1"
AMS_EMAIL="ops@acme.example"
AMS_PASSWORD="secretpass"
AMS_WORKSPACE_ID="119"
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T0/B0/abc"
SLACK_BOT_TOKEN="xoxb-1-2-3"
SLACK_SIGNING_SECRET="abcdef"
AUTHORIZED_SLACK_USER_IDS="U07AGTT8CLD"
SLACK_APP_TOKEN=""
SCAN_INTERVAL="300"
MG_DRY_RUN="true"
EOF
if out="$(bash "$EXTRACT" "$GOOD_CONF" 2>&1)" && [[ "$out" == "OK" ]]; then
    ok "valid conf passes _conf_source + _conf_validate"
else
    fail "valid conf rejected: $out"
fi

# 13b. Missing CUSTOMER_NAME aborts.
BAD_CONF="${TMP}/bad_no_customer.conf"
cat > "$BAD_CONF" <<EOF
CUSTOMER_NAME=""
AMS_EMAIL="ops@acme.example"
AMS_PASSWORD="secretpass"
AMS_WORKSPACE_ID="119"
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T0/B0/abc"
SLACK_BOT_TOKEN="xoxb-1"
SLACK_SIGNING_SECRET="abcdef"
AUTHORIZED_SLACK_USER_IDS="U07AGTT8CLD"
EOF
out="$(bash "$EXTRACT" "$BAD_CONF" 2>&1)"
rc=$?
if [[ "$rc" == "41" ]] && echo "$out" | /usr/bin/grep -q "CUSTOMER_NAME is required"; then
    ok "missing CUSTOMER_NAME → exit 41 with correct reason"
else
    fail "missing CUSTOMER_NAME did not abort with exit 41 (rc=$rc, out=$out)"
fi

# 13c. Bad SLACK_WEBHOOK_URL aborts.
BAD_CONF="${TMP}/bad_slack.conf"
cat > "$BAD_CONF" <<EOF
CUSTOMER_NAME="Acme"
AMS_EMAIL="ops@acme.example"
AMS_PASSWORD="secretpass"
AMS_WORKSPACE_ID="119"
SLACK_WEBHOOK_URL="https://example.com/not-slack"
SLACK_BOT_TOKEN="xoxb-1"
SLACK_SIGNING_SECRET="abcdef"
AUTHORIZED_SLACK_USER_IDS="U07AGTT8CLD"
EOF
out="$(bash "$EXTRACT" "$BAD_CONF" 2>&1)"
rc=$?
if [[ "$rc" == "41" ]] && echo "$out" | /usr/bin/grep -q "hooks.slack.com"; then
    ok "bad SLACK_WEBHOOK_URL → exit 41 with hooks.slack.com message"
else
    fail "bad SLACK_WEBHOOK_URL did not abort with exit 41 (rc=$rc, out=$out)"
fi

# 13d. Bad SLACK_BOT_TOKEN prefix aborts.
BAD_CONF="${TMP}/bad_bot.conf"
cat > "$BAD_CONF" <<EOF
CUSTOMER_NAME="Acme"
AMS_EMAIL="ops@acme.example"
AMS_PASSWORD="secretpass"
AMS_WORKSPACE_ID="119"
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T0/B0/abc"
SLACK_BOT_TOKEN="not-a-real-token"
SLACK_SIGNING_SECRET="abcdef"
AUTHORIZED_SLACK_USER_IDS="U07AGTT8CLD"
EOF
out="$(bash "$EXTRACT" "$BAD_CONF" 2>&1)"
rc=$?
if [[ "$rc" == "41" ]] && echo "$out" | /usr/bin/grep -q "xoxb-"; then
    ok "bad SLACK_BOT_TOKEN → exit 41 with xoxb- message"
else
    fail "bad SLACK_BOT_TOKEN did not abort with exit 41 (rc=$rc, out=$out)"
fi

# 13e. Non-integer AMS_WORKSPACE_ID aborts.
BAD_CONF="${TMP}/bad_ws.conf"
cat > "$BAD_CONF" <<EOF
CUSTOMER_NAME="Acme"
AMS_EMAIL="ops@acme.example"
AMS_PASSWORD="secretpass"
AMS_WORKSPACE_ID="not-an-int"
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T0/B0/abc"
SLACK_BOT_TOKEN="xoxb-1"
SLACK_SIGNING_SECRET="abcdef"
AUTHORIZED_SLACK_USER_IDS="U07AGTT8CLD"
EOF
out="$(bash "$EXTRACT" "$BAD_CONF" 2>&1)"
rc=$?
if [[ "$rc" == "41" ]] && echo "$out" | /usr/bin/grep -q "AMS_WORKSPACE_ID must be an integer"; then
    ok "non-integer AMS_WORKSPACE_ID → exit 41 with integer message"
else
    fail "non-integer AMS_WORKSPACE_ID did not abort with exit 41 (rc=$rc, out=$out)"
fi

# 13f. Bad MG_DRY_RUN aborts.
BAD_CONF="${TMP}/bad_dryrun.conf"
cat > "$BAD_CONF" <<EOF
CUSTOMER_NAME="Acme"
AMS_EMAIL="ops@acme.example"
AMS_PASSWORD="secretpass"
AMS_WORKSPACE_ID="119"
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T0/B0/abc"
SLACK_BOT_TOKEN="xoxb-1"
SLACK_SIGNING_SECRET="abcdef"
AUTHORIZED_SLACK_USER_IDS="U07AGTT8CLD"
MG_DRY_RUN="maybe"
EOF
out="$(bash "$EXTRACT" "$BAD_CONF" 2>&1)"
rc=$?
if [[ "$rc" == "41" ]] && echo "$out" | /usr/bin/grep -q "MG_DRY_RUN must be"; then
    ok "bad MG_DRY_RUN → exit 41 with true/false message"
else
    fail "bad MG_DRY_RUN did not abort with exit 41 (rc=$rc, out=$out)"
fi

# 13g. AMS_URL defaults when empty.
DEFAULT_CONF="${TMP}/default_ams.conf"
cat > "$DEFAULT_CONF" <<EOF
CUSTOMER_NAME="Acme"
AMS_URL=""
AMS_EMAIL="ops@acme.example"
AMS_PASSWORD="secretpass"
AMS_WORKSPACE_ID="119"
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T0/B0/abc"
SLACK_BOT_TOKEN="xoxb-1"
SLACK_SIGNING_SECRET="abcdef"
AUTHORIZED_SLACK_USER_IDS="U07AGTT8CLD"
EOF
if out="$(bash "$EXTRACT" "$DEFAULT_CONF" 2>&1)" && [[ "$out" == "OK" ]]; then
    ok "empty AMS_URL defaults to https://api.bixbit.io/api/v1"
else
    fail "empty AMS_URL did not default cleanly: $out"
fi

# 13h. SLACK_APP_TOKEN with wrong prefix aborts.
BAD_CONF="${TMP}/bad_app_token.conf"
cat > "$BAD_CONF" <<EOF
CUSTOMER_NAME="Acme"
AMS_EMAIL="ops@acme.example"
AMS_PASSWORD="secretpass"
AMS_WORKSPACE_ID="119"
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T0/B0/abc"
SLACK_BOT_TOKEN="xoxb-1"
SLACK_SIGNING_SECRET="abcdef"
AUTHORIZED_SLACK_USER_IDS="U07AGTT8CLD"
SLACK_APP_TOKEN="xbad-prefix-token"
EOF
out="$(bash "$EXTRACT" "$BAD_CONF" 2>&1)"
rc=$?
if [[ "$rc" == "41" ]] && echo "$out" | /usr/bin/grep -q "xapp-"; then
    ok "wrong-prefix SLACK_APP_TOKEN → exit 41 with xapp- message"
else
    fail "wrong-prefix SLACK_APP_TOKEN did not abort with exit 41 (rc=$rc, out=$out)"
fi

# ---------------------------------------------------------------------
section "Summary"
# ---------------------------------------------------------------------
echo
echo "Passed: $pass_count"
echo "Failed: $fail_count"
if (( fail_count > 0 )); then
    exit 1
fi
exit 0
