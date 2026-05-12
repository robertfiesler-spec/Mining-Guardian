#!/usr/bin/env bash
# scripts/run_reconciliation_greps.sh
# Re-runnable reconciliation against the Master Execution Plan.
# Run from repo root: `bash scripts/run_reconciliation_greps.sh`
# Update docs/strategy/RECONCILIATION_<DATE>.md if numbers change.

set -u

echo "===================================================="
echo "Reconciliation against: $(git log -1 --oneline 2>/dev/null || echo 'not a git repo')"
echo "Date: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "===================================================="
echo

echo "--- W16: production TO_CHAR (expect 0) ---"
w16=$(grep -rn 'TO_CHAR(NOW(' ai/ core/ api/ scripts/ --include='*.py' 2>/dev/null | wc -l)
echo "  count: $w16"
[ "$w16" = "0" ] && echo "  status: ✅ PASS" || echo "  status: ❌ REGRESSION"
echo

echo "--- W16: test guard count (expect 7) ---"
w16t=$(grep -rn 'TO_CHAR(NOW(' tests/ --include='*.py' 2>/dev/null | wc -l)
echo "  count: $w16t"
echo

echo "--- W17: naive datetime.now() (expect ~151, ideally trending down) ---"
w17n=$(grep -rnE 'datetime\.now\(\)' ai/ core/ api/ scripts/ --include='*.py' 2>/dev/null | wc -l)
echo "  count: $w17n"
echo

echo "--- W17: tz-aware datetime.now(timezone... (baseline 18, ideally trending up) ---"
w17t=$(grep -rnE 'datetime\.now\(timezone' ai/ core/ api/ scripts/ --include='*.py' 2>/dev/null | wc -l)
echo "  count: $w17t"
echo

echo "--- W05: ProcessType in always-on plists (9 lines expected) ---"
for f in installer/macos-pkg/resources/launchd/com.miningguardian.*.plist; do
  name=$(basename "$f" .plist | sed 's/com.miningguardian.//')
  pt=$(grep -A1 '<key>ProcessType</key>' "$f" 2>/dev/null | tail -1 | tr -d '[:space:]')
  echo "  $name : $pt"
done
echo

echo "--- W03: ThreadedConnectionPool usage in repo ---"
grep -rln "ThreadedConnectionPool\|psycopg2.pool" --include='*.py' 2>/dev/null | sed 's/^/  /'
echo

echo "--- W03: confirm core/database_pg.py still per-call (expect TODO comment present) ---"
if grep -q 'no pool today — simple for correctness' core/database_pg.py 2>/dev/null; then
  echo "  status: ⚠️ Operational adapter still per-call (W03 not done)"
else
  echo "  status: ✅ TODO comment removed — re-check that pool is in place"
fi
echo

echo "--- W02: pg_stat_statements references (expect empty until done) ---"
w02=$(grep -rln "pg_stat_statements\|shared_preload_libraries" \
      --include='*.py' --include='*.sql' --include='*.md' --include='*.sh' 2>/dev/null | wc -l)
echo "  files referencing: $w02"
echo

echo "===================================================="
echo "Done. Update docs/EXECUTION_PLAN_STATUS.md and"
echo "docs/strategy/RECONCILIATION_<DATE>.md if anything changed."
echo "===================================================="
