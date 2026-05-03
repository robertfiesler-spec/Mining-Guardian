#!/usr/bin/env bash
# tests/installer/test_d20_importer_payload_reconciliation.sh
#
# D-20 importer-payload reconciliation — static checks against the source
# tree only (no Mac, no Installer.app, no actual rsync, no actual psql
# apply). The full smoke test is the v1.0.3 D-18 verification gate
# ("clean macOS 14 VM"); this static suite asserts the build_pkg.sh and
# canonical-migrations layout are consistent with D-20 BEFORE the v1.0.3
# build is fired.
#
# What this guards:
#   1. build_pkg.sh step 4a NO LONGER includes `mg_import_tool/***` in
#      the payload rsync.
#   2. build_pkg.sh step 4b NO LONGER rsyncs `mg_import_tool/sql/migrations/`
#      into the payload.
#   3. build_pkg.sh step 4h is wired in: a `find ... -name 'mg_import*'`
#      assertion runs post-assembly and aborts with exit 43 if any match.
#   4. The runtime-relevant importer migrations have been relocated into
#      canonical `migrations/` under the next free numeric prefixes
#      (006_field_log_bootstrap.sql, 007_layer2_resolver.sql), and their
#      bodies are byte-identical to the operator-side originals at
#      `mg_import_tool/sql/migrations/*.sql` (preserves idempotency).
#   5. The operator-side originals at `mg_import_tool/sql/migrations/` are
#      INTENTIONALLY retained (D-20 footnote — importer is operator-only
#      forever; the operator workstation needs them for its own importer
#      bootstrap path).
#   6. postinstall.sh `step_apply_migrations` still globs `<payload>/migrations/*.sql`
#      lexically — no hand-picked subset — so the new 006/007 files are
#      applied in order.
#
# Run from repo root:
#     bash tests/installer/test_d20_importer_payload_reconciliation.sh
#
# Exits 0 on success, non-zero on first failed assertion.
# Requires: bash, grep, diff, find, awk. shellcheck optional.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

POSTINSTALL="installer/macos-pkg/scripts/postinstall.sh"
BUILD_PKG="installer/macos-pkg/scripts/build_pkg.sh"

CANONICAL_006="migrations/006_field_log_bootstrap.sql"
CANONICAL_007="migrations/007_layer2_resolver.sql"
IMPORTER_000="mg_import_tool/sql/migrations/000_bootstrap_field_log_tables.sql"
IMPORTER_002="mg_import_tool/sql/migrations/002_layer2_and_learning_foundation.sql"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }

section() { echo; echo "## $*"; }

# ---------------------------------------------------------------------
section "1. Source files exist"
# ---------------------------------------------------------------------
for f in "$POSTINSTALL" "$BUILD_PKG" "$CANONICAL_006" "$CANONICAL_007" \
         "$IMPORTER_000" "$IMPORTER_002"; do
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
if bash -n "$BUILD_PKG" 2>/dev/null; then
    ok "build_pkg.sh parses"
else
    fail "build_pkg.sh has bash syntax errors"
fi

# ---------------------------------------------------------------------
section "3. build_pkg.sh step 4a does NOT include mg_import_tool"
# ---------------------------------------------------------------------
# The 4a rsync include block is the curated repo-subset list. After D-20
# reconciliation it must NOT contain `mg_import_tool/***`. We grep for
# the literal include line; presence is an unconditional FAIL.
if /usr/bin/grep -qE "^[[:space:]]*--include[[:space:]]+'mg_import_tool/\*\*\*'" "$BUILD_PKG"; then
    fail "build_pkg.sh still includes mg_import_tool/*** in 4a rsync — D-20 violation"
else
    ok "build_pkg.sh 4a rsync does not include mg_import_tool/***"
fi

# Spot-check the surrounding includes are intact (intelligence-catalog +
# migrations + docs); a botched edit could have removed more than we
# meant to.
for inc in 'core/\*\*\*' 'intelligence-catalog/\*\*\*' 'migrations/\*\*\*' 'docs/\*\*\*' 'deploy/\*\*\*'; do
    if /usr/bin/grep -qE "^[[:space:]]*--include[[:space:]]+'${inc}'" "$BUILD_PKG"; then
        ok "build_pkg.sh 4a still includes ${inc}"
    else
        fail "build_pkg.sh 4a no longer includes ${inc} — over-pruned"
    fi
done

# ---------------------------------------------------------------------
section "4. build_pkg.sh step 4b does NOT rsync from mg_import_tool/sql/migrations/"
# ---------------------------------------------------------------------
# Strip shell comment lines, then look for an actual rsync/cp/install
# operation that would copy from mg_import_tool/sql/migrations/. The
# updated 4b block now explains the historical violation in a comment;
# that's documentation, not behavior.
if /usr/bin/grep -vE '^[[:space:]]*#' "$BUILD_PKG" \
        | /usr/bin/grep -qE 'mg_import_tool/sql/migrations'; then
    fail "build_pkg.sh still has live (non-comment) reference to mg_import_tool/sql/migrations/ — D-20 violation"
else
    ok "build_pkg.sh has no live reference to mg_import_tool/sql/migrations/ (comments allowed)"
fi

# ---------------------------------------------------------------------
section "5. build_pkg.sh step 4h post-assembly D-20 assertion is wired in"
# ---------------------------------------------------------------------
if /usr/bin/grep -q '^[[:space:]]*# 4h\.' "$BUILD_PKG"; then
    ok "build_pkg.sh has step 4h block comment"
else
    fail "build_pkg.sh missing step 4h block comment"
fi

# Extract step_4_assemble_payload body and assert the find-based
# assertion + exit 43 are both present inside it.
assemble_body="$(/usr/bin/awk '/^step_4_assemble_payload\(\)/,/^}/' "$BUILD_PKG")"
if /usr/bin/grep -qE "find[[:space:]]+\"\\\$PAYLOAD_DIR\"[[:space:]]+-name[[:space:]]+'mg_import\*'" <<<"$assemble_body"; then
    ok "step_4_assemble_payload runs find -name 'mg_import*' on PAYLOAD_DIR"
else
    fail "step_4_assemble_payload missing find -name 'mg_import*' assertion"
fi
if /usr/bin/grep -q '_die 43' <<<"$assemble_body"; then
    ok "step_4_assemble_payload uses _die 43 for D-20 violation"
else
    fail "step_4_assemble_payload missing _die 43 (D-20 regression exit code)"
fi
if /usr/bin/grep -qE 'D-20' <<<"$assemble_body"; then
    ok "step_4_assemble_payload references D-20 in its log/_die message"
else
    fail "step_4_assemble_payload does not reference D-20 in its messages"
fi

# ---------------------------------------------------------------------
section "6. Header documents exit 43 as the D-20 violation code"
# ---------------------------------------------------------------------
header_block="$(/usr/bin/awk '/^# Exit codes:/,/^[^#]|^$/' "$BUILD_PKG")"
if /usr/bin/grep -qE '43.*D-20|D-20.*43' <<<"$header_block"; then
    ok "header maps exit 43 to the D-20 importer-payload violation"
else
    fail "header does not connect exit 43 to D-20 — future readers will be confused"
fi

# ---------------------------------------------------------------------
section "7. Canonical migrations 006 and 007 exist under repo migrations/"
# ---------------------------------------------------------------------
if [[ -r "$CANONICAL_006" ]]; then
    ok "$CANONICAL_006 exists"
else
    fail "$CANONICAL_006 missing — migration was not relocated"
fi
if [[ -r "$CANONICAL_007" ]]; then
    ok "$CANONICAL_007 exists"
else
    fail "$CANONICAL_007 missing — migration was not relocated"
fi

# ---------------------------------------------------------------------
section "8. Canonical 006/007 bodies are byte-identical to the importer-side originals"
# ---------------------------------------------------------------------
# The contract: the SQL content of the canonical-side copies must match
# the operator-side originals exactly so idempotency is preserved on a
# customer Mini that already has the importer-side numbering applied
# (e.g., the upgrade-from-v1.0.2 path, where 000+002 were applied via
# the v1.0.2 .pkg and 006+007 will be applied via v1.0.3+; both must
# be no-ops because every CREATE/ALTER uses IF NOT EXISTS).
#
# Canonical file = prepended introductory header + verbatim importer
# body. The introductory header on each canonical file ends with a
# closing-paren-colon BODY marker line; everything after is the
# byte-identical importer body. We grep for the LAST line of the new
# header (it contains "byte-identical" which the importer originals do
# NOT contain) and diff what follows against the importer file body.
#
# For the importer-side files we strip their own file-level header by
# locating the LAST `-- ===...===` divider line (the original header's
# closing rule).

# canonical 006 body offset: line after "byte-identical to preserve idempotency):"
c006_skip=$(/usr/bin/grep -nE '^-- byte-identical with the importer-side original to preserve idempotency\):' "$CANONICAL_006" | /usr/bin/head -1 | /usr/bin/cut -d: -f1)
# importer 000 body offset: the file-level header's CLOSING `===` rule
# is the LAST `===` rule before the first non-comment SQL line. We
# locate the line just BEFORE the first `-- Schemas` block header, which
# is the canonical first body comment in both 000 and 006.
i000_body_anchor=$(/usr/bin/grep -nE '^-- Schemas$' "$IMPORTER_000" | /usr/bin/head -1 | /usr/bin/cut -d: -f1)
if [[ -n "$c006_skip" && -n "$i000_body_anchor" ]]; then
    # Importer body starts 2 lines before "-- Schemas" (the dashed
    # underline rule above it). Same in canonical.
    i000_skip=$((i000_body_anchor - 2))
    if /usr/bin/diff <(/usr/bin/tail -n +$((c006_skip + 1)) "$CANONICAL_006") \
                    <(/usr/bin/tail -n +"$i000_skip" "$IMPORTER_000") \
                    >/dev/null; then
        ok "$CANONICAL_006 body byte-identical to $IMPORTER_000 body"
    else
        fail "$CANONICAL_006 body DIFFERS from $IMPORTER_000 — idempotency contract broken"
    fi
else
    fail "could not locate body offsets (c006_skip='${c006_skip}', i000_body_anchor='${i000_body_anchor}')"
fi

# canonical 007 body offset: line after "byte-identical to the importer-side original to preserve idempotency):"
c007_skip=$(/usr/bin/grep -nE '^-- byte-identical to the importer-side original to preserve idempotency\):' "$CANONICAL_007" | /usr/bin/head -1 | /usr/bin/cut -d: -f1)
# importer 002 has no file-level header to strip (its first line IS the body).
if [[ -n "$c007_skip" ]]; then
    if /usr/bin/diff <(/usr/bin/tail -n +$((c007_skip + 1)) "$CANONICAL_007") \
                    "$IMPORTER_002" \
                    >/dev/null; then
        ok "$CANONICAL_007 body byte-identical to $IMPORTER_002 body"
    else
        fail "$CANONICAL_007 body DIFFERS from $IMPORTER_002 — idempotency contract broken"
    fi
else
    fail "could not locate canonical_007 body offset (c007_skip='${c007_skip}')"
fi

# ---------------------------------------------------------------------
section "9. Operator-side importer originals are INTENTIONALLY retained"
# ---------------------------------------------------------------------
# D-20 footnote — the importer keeps its own copy of these migrations so
# its bootstrap path on the operator workstation continues to work. If a
# future PR deletes them, this assertion catches it.
if [[ -r "$IMPORTER_000" ]]; then
    ok "$IMPORTER_000 retained (D-20 footnote — importer-side source of truth)"
else
    fail "$IMPORTER_000 was deleted — importer's own bootstrap path now broken"
fi
if [[ -r "$IMPORTER_002" ]]; then
    ok "$IMPORTER_002 retained (D-20 footnote — importer-side source of truth)"
else
    fail "$IMPORTER_002 was deleted — importer's own bootstrap path now broken"
fi

# ---------------------------------------------------------------------
section "10. postinstall.sh step_apply_migrations applies all <payload>/migrations/*.sql lexically"
# ---------------------------------------------------------------------
apply_body="$(/usr/bin/awk '/^step_apply_migrations\(\)/,/^}/' "$POSTINSTALL")"
if /usr/bin/grep -qE 'for[[:space:]]+\w+[[:space:]]+in[[:space:]]+"\$\{?mig_dir' <<<"$apply_body"; then
    ok "step_apply_migrations iterates over <payload>/migrations/*.sql"
else
    fail "step_apply_migrations no longer loops the migrations dir — hand-picked subset?"
fi
if /usr/bin/grep -qE '\*\.sql' <<<"$apply_body"; then
    ok "step_apply_migrations glob is *.sql (no hand-picked subset)"
else
    fail "step_apply_migrations does not use *.sql glob — D-18 §4 item 6 violation"
fi

# ---------------------------------------------------------------------
section "11. Canonical migrations directory has no numeric collision at 006/007"
# ---------------------------------------------------------------------
if [[ "$(/usr/bin/find migrations -maxdepth 1 -name '006_*.sql' -type f | /usr/bin/wc -l | /usr/bin/tr -d ' ')" == "1" ]]; then
    ok "exactly one migrations/006_*.sql file"
else
    fail "migrations/006_*.sql collision (or missing)"
fi
if [[ "$(/usr/bin/find migrations -maxdepth 1 -name '007_*.sql' -type f | /usr/bin/wc -l | /usr/bin/tr -d ' ')" == "1" ]]; then
    ok "exactly one migrations/007_*.sql file"
else
    fail "migrations/007_*.sql collision (or missing)"
fi

# ---------------------------------------------------------------------
section "12. shellcheck regression baseline (no NEW warnings)"
# ---------------------------------------------------------------------
# Same baseline policy as test_postinstall_catalog_seed.sh §11 and
# test_postinstall_venv.sh §3. This PR adds one new step body
# (step 4h) to build_pkg.sh; if shellcheck flags the new code, we
# catch it here. Existing baselines: postinstall.sh ≤ 3, build_pkg.sh ≤ 5.
if command -v shellcheck >/dev/null 2>&1; then
    pi_count="$(shellcheck "$POSTINSTALL" 2>&1 | /usr/bin/grep -cE '^In .* line [0-9]+:' || true)"
    bp_count="$(shellcheck "$BUILD_PKG"   2>&1 | /usr/bin/grep -cE '^In .* line [0-9]+:' || true)"
    if [[ "$pi_count" -le 3 ]]; then
        ok "postinstall.sh shellcheck warnings: ${pi_count} (≤ 3 baseline)"
    else
        fail "postinstall.sh shellcheck warnings: ${pi_count} (> 3 baseline — new warning introduced)"
    fi
    if [[ "$bp_count" -le 5 ]]; then
        ok "build_pkg.sh shellcheck warnings: ${bp_count} (≤ 5 baseline)"
    else
        fail "build_pkg.sh shellcheck warnings: ${bp_count} (> 5 baseline — new warning introduced)"
    fi
else
    echo "  SKIP — shellcheck not installed (install: \`brew install shellcheck\` or \`apt-get install shellcheck\`)"
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
