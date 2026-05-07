#!/usr/bin/env bash
# tests/installer/test_postinstall_p021.sh
#
# P-021 (2026-05-07) — postinstall + payload static checks for the
# two-DB cooperative architecture batch:
#
#   1. Tier-1 alias seed supplement
#      (003_live_short_name_aliases.sql) is shipped, applied by
#      postinstall, and registered as required.
#   2. Daily catalog-import scheduled job is plumbed:
#      - run_daily_catalog_import.sh shipped + executable
#      - com.miningguardian.scheduled.catalog-import.plist shipped
#      - SCHEDULED_PLIST_LABELS array contains the new label
#      - service_count and scheduled_job_count derive from arrays
#        (so the new job auto-bumps install-receipt count to 12).
#   3. The three SQL-schema fixes are present in source (catalog_api.py
#      + catalog_context.py reference miner_model_id / primary_model_id
#      / firmware_compatibility joins, NOT the broken model_id pattern).
#
# Source-tree static checks only — no live launchctl, no Mac, no
# Postgres. Runs on macOS BSD bash 3.2 + GNU bash 4+. Mirrors the
# portability guards in tests/installer/test_postinstall_service_startup_robust.sh.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

POSTINSTALL="installer/macos-pkg/scripts/postinstall.sh"
ALIASES_DIR="intelligence-catalog/seed-data/aliases"
TIER1_SUPP="${ALIASES_DIR}/003_live_short_name_aliases.sql"
WRAPPER="intelligence-catalog/tools/run_daily_catalog_import.sh"
PLIST="installer/macos-pkg/resources/launchd/scheduled/com.miningguardian.scheduled.catalog-import.plist"
CATALOG_API="intelligence-catalog/catalog-api/catalog_api.py"
CATALOG_CTX="ai/catalog_context.py"

pass_count=0
fail_count=0
ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }
section() { echo; echo "## $*"; }


section "1. Tier-1 alias seed supplement file"
if [[ -r "$TIER1_SUPP" ]]; then
    ok "${TIER1_SUPP} present"
else
    fail "${TIER1_SUPP} missing"
fi
for name in S19JPro S21EXPHyd S21Imm AH3880; do
    if /usr/bin/grep -q "'${name}'" "$TIER1_SUPP"; then
        ok "supplement covers ${name}"
    else
        fail "supplement missing alias for ${name}"
    fi
done
if /usr/bin/grep -q "ON CONFLICT (miner_model_id, alias) DO NOTHING" "$TIER1_SUPP"; then
    ok "supplement is idempotent (ON CONFLICT DO NOTHING)"
else
    fail "supplement missing ON CONFLICT clause"
fi
# UUIDs must NOT appear — supplement resolves IDs at apply time.
if /usr/bin/grep -qE '\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b' "$TIER1_SUPP"; then
    fail "supplement contains hard-coded UUIDs (would re-introduce B-24 drift)"
else
    ok "supplement contains no hard-coded UUIDs"
fi


section "2. postinstall wires the supplement"
postinstall_body="$(/usr/bin/awk '/^step_apply_alias_seeds\(\)/,/^}$/' "$POSTINSTALL")"
if echo "$postinstall_body" | /usr/bin/grep -q '003_live_short_name_aliases.sql'; then
    ok "step_apply_alias_seeds references 003_live_short_name_aliases.sql"
else
    fail "step_apply_alias_seeds does NOT reference the supplement"
fi
if echo "$postinstall_body" | /usr/bin/grep -q 'tier1_supp_file'; then
    ok "step_apply_alias_seeds defines tier1_supp_file local"
else
    fail "step_apply_alias_seeds missing tier1_supp_file local"
fi
# Must be applied AFTER tier-2 (and BEFORE verify) so the verify counts
# include the supplement.
tier2_apply_line="$(echo "$postinstall_body" | /usr/bin/grep -n '002_mg_family_aliases_tier2.sql' | /usr/bin/tail -n 1 | /usr/bin/cut -d: -f1)"
supp_apply_line="$(echo "$postinstall_body" | /usr/bin/grep -n '003_live_short_name_aliases.sql' | /usr/bin/tail -n 1 | /usr/bin/cut -d: -f1)"
verify_line="$(echo "$postinstall_body" | /usr/bin/grep -n '# 3. Verify' | /usr/bin/head -n 1 | /usr/bin/cut -d: -f1)"
if [[ -n "$tier2_apply_line" ]] && [[ -n "$supp_apply_line" ]] && [[ -n "$verify_line" ]] \
        && [[ "$tier2_apply_line" -lt "$supp_apply_line" ]] \
        && [[ "$supp_apply_line" -lt "$verify_line" ]]; then
    ok "ordering: tier-2 apply ($tier2_apply_line) < supplement apply ($supp_apply_line) < verify ($verify_line)"
else
    fail "ordering wrong: tier-2=$tier2_apply_line supp=$supp_apply_line verify=$verify_line"
fi


section "3. Daily catalog-import wrapper"
if [[ -r "$WRAPPER" ]]; then
    ok "$WRAPPER present"
else
    fail "$WRAPPER missing"
fi
if [[ -x "$WRAPPER" ]]; then
    ok "$WRAPPER is executable (mode bit set in repo)"
else
    fail "$WRAPPER NOT executable"
fi
if /usr/bin/grep -q 'catalog_updater.py --add-from-csv\|catalog_updater.py" --add-from-csv\|catalog_updater.py" "--add-from-csv"' "$WRAPPER" \
   || /usr/bin/grep -q -- '--add-from-csv' "$WRAPPER"; then
    ok "wrapper invokes catalog_updater.py --add-from-csv"
else
    fail "wrapper does NOT invoke catalog_updater.py --add-from-csv"
fi
if /usr/bin/grep -q 'cron_tracking/enrichment_sweep' "$WRAPPER"; then
    ok "wrapper reads from cron_tracking/enrichment_sweep/"
else
    fail "wrapper does NOT reference cron_tracking/enrichment_sweep/"
fi
if bash -n "$WRAPPER" 2>/dev/null; then
    ok "wrapper passes bash -n"
else
    fail "wrapper has bash syntax errors"
fi


section "4. Daily catalog-import plist"
if [[ -r "$PLIST" ]]; then
    ok "$PLIST present"
else
    fail "$PLIST missing"
fi
if /usr/bin/grep -q 'scheduled_job_launcher.sh' "$PLIST"; then
    ok "plist dispatches via scheduled_job_launcher.sh"
else
    fail "plist does NOT dispatch via scheduled_job_launcher.sh"
fi
if /usr/bin/grep -q 'intelligence-catalog/tools/run_daily_catalog_import.sh' "$PLIST"; then
    ok "plist points at the wrapper"
else
    fail "plist does NOT point at the wrapper"
fi
if /usr/bin/grep -q '<string>catalog_import</string>' "$PLIST"; then
    ok "plist passes the canonical 'catalog_import' label"
else
    fail "plist missing canonical label"
fi


section "5. SCHEDULED_PLIST_LABELS contains catalog-import"
if /usr/bin/grep -q '"com.miningguardian.scheduled.catalog-import"' "$POSTINSTALL"; then
    ok "postinstall registers com.miningguardian.scheduled.catalog-import"
else
    fail "postinstall does NOT register catalog-import label"
fi


section "6. install-receipt count derives from arrays"
# service_count = ${#PLIST_LABELS[@]}, scheduled_job_count = ${#SCHEDULED_PLIST_LABELS[@]}
if /usr/bin/grep -q '"service_count": \${#PLIST_LABELS\[@\]}' "$POSTINSTALL"; then
    ok "service_count derives from PLIST_LABELS"
else
    fail "service_count is NOT array-derived (would not auto-bump)"
fi
if /usr/bin/grep -q '"scheduled_job_count": \${#SCHEDULED_PLIST_LABELS\[@\]}' "$POSTINSTALL"; then
    ok "scheduled_job_count derives from SCHEDULED_PLIST_LABELS"
else
    fail "scheduled_job_count is NOT array-derived (would not auto-bump)"
fi


section "7. catalog_api.py: schema-correct columns"
api_body="$(/bin/cat "$CATALOG_API")"
# These MUST be present (the fix):
for needle in 'primary_model_id' 'firmware.firmware_compatibility' 'affected_model_id' 'hardware.psu_compatibility'; do
    if echo "$api_body" | /usr/bin/grep -q "$needle"; then
        ok "catalog_api.py references ${needle}"
    else
        fail "catalog_api.py missing ${needle}"
    fi
done


section "8. catalog_context.py: schema-correct columns"
ctx_body="$(/bin/cat "$CATALOG_CTX")"
for needle in 'firmware.firmware_compatibility' 'miner_model_id'; do
    if echo "$ctx_body" | /usr/bin/grep -q "$needle"; then
        ok "catalog_context.py references ${needle}"
    else
        fail "catalog_context.py missing ${needle}"
    fi
done


# ---------------------------------------------------------------------------
echo
echo "================================================================"
echo "PASS: ${pass_count}    FAIL: ${fail_count}"
echo "================================================================"
if [[ "$fail_count" -gt 0 ]]; then
    exit 1
fi
exit 0
