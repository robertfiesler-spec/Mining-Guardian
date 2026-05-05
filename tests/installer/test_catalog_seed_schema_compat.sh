#!/usr/bin/env bash
# tests/installer/test_catalog_seed_schema_compat.sh
#
# D-18 P-024 — static check that every column referenced by an
# INSERT INTO hardware.<table> (...) statement in
# intelligence-catalog/seed-data/seed_miner_models.sql actually exists in
# the catalog schema (intelligence_catalog_schema.sql + v2/v3/staging
# additions).
#
# Background: v1.0.3 Mac Mini install failed (postinstall exit 39) because
# the seed file inserted into hardware.manufacturers using columns
# `full_name, country, website, notes`, none of which exist in the schema
# — the schema uses legal_name / common_name / country_of_origin /
# website_url. The broken manufacturer block was removed in P-024
# (manufacturers are now seeded by deploy_schema.sql exclusively). This
# test prevents that class of drift from re-appearing.
#
# Also asserts:
#   - seed_miner_models.sql contains NO INSERT INTO hardware.manufacturers
#     statement (manufacturers are owned by deploy_schema.sql per P-024).
#   - deploy_schema.sql still seeds all brands referenced by the miner
#     INSERTs in seed_miner_models.sql.
#
# Run from repo root:
#     bash tests/installer/test_catalog_seed_schema_compat.sh
#
# Exits 0 on success, non-zero on first failed assertion.
# Requires: bash, awk, grep.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

SEED_FILE="intelligence-catalog/seed-data/seed_miner_models.sql"
SCHEMA_BUNDLE=(
    "intelligence-catalog/seed-data/intelligence_catalog_schema.sql"
    "intelligence-catalog/seed-data/intelligence_catalog_schema_v2_additions.sql"
    "intelligence-catalog/seed-data/intelligence_catalog_schema_v3_additions.sql"
    "intelligence-catalog/seed-data/staging_schema.sql"
)
DEPLOY_FILE="intelligence-catalog/seed-data/deploy_schema.sql"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }
section() { echo; echo "## $*"; }

# ---------------------------------------------------------------------
section "1. Source files exist"
# ---------------------------------------------------------------------
for f in "$SEED_FILE" "$DEPLOY_FILE" "${SCHEMA_BUNDLE[@]}"; do
    if [[ -r "$f" ]]; then
        ok "$f present"
    else
        fail "$f missing"
    fi
done

if (( fail_count > 0 )); then
    echo
    echo "Failed: $fail_count — aborting before column checks"
    exit 1
fi

# ---------------------------------------------------------------------
section "2. seed_miner_models.sql does NOT INSERT INTO hardware.manufacturers"
# ---------------------------------------------------------------------
# Manufacturers are owned by deploy_schema.sql (P-024). Re-introducing a
# manufacturer INSERT here re-creates the v1.0.3 install regression.
if /usr/bin/grep -qE '^[[:space:]]*INSERT[[:space:]]+INTO[[:space:]]+hardware\.manufacturers' "$SEED_FILE"; then
    fail "seed_miner_models.sql contains an INSERT INTO hardware.manufacturers — must live in deploy_schema.sql only (P-024 regression)"
else
    ok "seed_miner_models.sql has no INSERT INTO hardware.manufacturers (P-024 honored)"
fi

# ---------------------------------------------------------------------
section "3. Every column in seed INSERTs exists in the catalog schema"
# ---------------------------------------------------------------------
# Collect every CREATE TABLE column name across the schema bundle. We
# only care about columns inside CREATE TABLE blocks (ignore comments,
# CREATE INDEX, etc.). Awk extracts identifiers in column position 1.
SCHEMA_COLS_FILE="$(mktemp)"
trap 'rm -f "$SCHEMA_COLS_FILE"' EXIT

/usr/bin/awk '
    /^[[:space:]]*CREATE[[:space:]]+TABLE/ { in_table = 1; next }
    in_table && /^[[:space:]]*\)[[:space:]]*;?/ { in_table = 0; next }
    in_table {
        # skip blank, comment, constraint, trigger, check, index lines
        line = $0
        sub(/^[[:space:]]+/, "", line)
        if (line == "") next
        if (line ~ /^--/) next
        if (line ~ /^(PRIMARY|FOREIGN|UNIQUE|CHECK|CONSTRAINT|INDEX|EXCLUDE|LIKE)/) next
        # first whitespace-separated token is the column identifier
        col = line
        sub(/[[:space:]].*$/, "", col)
        sub(/,$/, "", col)
        if (col ~ /^[a-z_][a-z0-9_]*$/) print col
    }
' "${SCHEMA_BUNDLE[@]}" | sort -u > "$SCHEMA_COLS_FILE"

schema_col_count="$(/usr/bin/wc -l < "$SCHEMA_COLS_FILE" | tr -d '[:space:]')"
if (( schema_col_count < 50 )); then
    fail "schema column extraction yielded only ${schema_col_count} columns — awk parser likely broken"
else
    ok "extracted ${schema_col_count} unique column names from catalog schema bundle"
fi

# Pull every `INSERT INTO hardware.<table> (col, col, ...)` from the seed
# file and verify each col exists in the extracted column set. Multi-line
# column lists are flattened by awk before splitting.
seed_inserts_checked=0
seed_columns_checked=0
seed_columns_missing=0
missing_examples=""

while IFS= read -r insert_block; do
    # extract the parenthesised column list (between first '(' and its ')')
    col_list="$(/usr/bin/awk 'BEGIN{depth=0; out=""} {
        for (i = 1; i <= length($0); i++) {
            c = substr($0, i, 1)
            if (c == "(") { depth++; if (depth == 1) continue }
            if (c == ")") { depth--; if (depth == 0) { print out; exit } }
            if (depth >= 1) out = out c
        }
    }' <<<"$insert_block")"

    # split on commas; trim whitespace; ignore blanks
    while IFS= read -r col; do
        col_trimmed="$(echo "$col" | /usr/bin/tr -d '[:space:]')"
        [[ -z "$col_trimmed" ]] && continue
        seed_columns_checked=$((seed_columns_checked + 1))
        if ! /usr/bin/grep -qx "$col_trimmed" "$SCHEMA_COLS_FILE"; then
            seed_columns_missing=$((seed_columns_missing + 1))
            if [[ -z "$missing_examples" ]]; then
                missing_examples="$col_trimmed"
            else
                # cap example list length
                if [[ "$(echo "$missing_examples" | /usr/bin/awk -F, '{print NF}')" -lt 6 ]]; then
                    missing_examples="${missing_examples}, ${col_trimmed}"
                fi
            fi
        fi
    done < <(echo "$col_list" | /usr/bin/tr ',' '\n')

    seed_inserts_checked=$((seed_inserts_checked + 1))
done < <(/usr/bin/awk '
    /INSERT[[:space:]]+INTO[[:space:]]+hardware\./ {
        in_insert = 1; buf = ""
    }
    in_insert {
        buf = buf " " $0
        if (index($0, ")") > 0 && index(buf, "(") > 0) {
            # only the first () of the INSERT (the column list) matters
            print buf
            in_insert = 0
            buf = ""
        }
    }
' "$SEED_FILE")

if (( seed_inserts_checked < 1 )); then
    fail "no INSERT INTO hardware.* statements parsed from seed file — parser broken"
elif (( seed_columns_missing == 0 )); then
    ok "all ${seed_columns_checked} seed columns across ${seed_inserts_checked} INSERT blocks exist in schema"
else
    fail "${seed_columns_missing} seed column(s) not found in catalog schema (e.g., ${missing_examples}) — schema/seed drift, will fail psql apply"
fi

# Specific named checks for the P-024 regression columns. These assert
# the schema has the *correct* names (so deploy_schema.sql's INSERT
# remains valid), and that the seed file does NOT reference the *wrong*
# names that broke v1.0.3.
section "4. hardware.manufacturers schema columns (P-024 regression names)"

for canonical in legal_name common_name country_of_origin website_url; do
    if /usr/bin/grep -qx "$canonical" "$SCHEMA_COLS_FILE"; then
        ok "hardware.manufacturers schema column '$canonical' present"
    else
        fail "hardware.manufacturers schema column '$canonical' missing — deploy_schema.sql INSERT will fail"
    fi
done

for broken in full_name country website; do
    if /usr/bin/grep -q "(.*\b${broken}\b.*)" <(/usr/bin/grep -E '^[[:space:]]*INSERT[[:space:]]+INTO[[:space:]]+hardware\.manufacturers' "$SEED_FILE"); then
        fail "seed_miner_models.sql still references the broken column '$broken' on hardware.manufacturers (P-024 regression)"
    else
        ok "seed_miner_models.sql does not reference broken column '$broken' on hardware.manufacturers"
    fi
done

# ---------------------------------------------------------------------
section "5. deploy_schema.sql seeds every brand referenced by the seed file"
# ---------------------------------------------------------------------
SEED_BRANDS_FILE="$(mktemp)"
DEPLOY_BRANDS_FILE="$(mktemp)"
trap 'rm -f "$SCHEMA_COLS_FILE" "$SEED_BRANDS_FILE" "$DEPLOY_BRANDS_FILE"' EXIT

/usr/bin/grep -oE "brand[[:space:]]*=[[:space:]]*'[a-z_]+'" "$SEED_FILE" \
    | /usr/bin/grep -oE "'[a-z_]+'" \
    | /usr/bin/tr -d "'" \
    | /usr/bin/sort -u > "$SEED_BRANDS_FILE"

/usr/bin/grep -oE "^[[:space:]]+\('[a-z_]+'" "$DEPLOY_FILE" \
    | /usr/bin/grep -oE "'[a-z_]+'" \
    | /usr/bin/tr -d "'" \
    | /usr/bin/sort -u > "$DEPLOY_BRANDS_FILE"

missing_brands="$(/usr/bin/comm -23 "$SEED_BRANDS_FILE" "$DEPLOY_BRANDS_FILE" | /usr/bin/tr '\n' ',' | /usr/bin/sed 's/,$//')"
if [[ -z "$missing_brands" ]]; then
    seed_brand_count="$(/usr/bin/wc -l < "$SEED_BRANDS_FILE" | /usr/bin/tr -d '[:space:]')"
    ok "all ${seed_brand_count} brands referenced by seed_miner_models.sql are seeded by deploy_schema.sql"
else
    fail "deploy_schema.sql does not seed brand(s): ${missing_brands} — seed_miner_models.sql will fail FK lookup"
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
