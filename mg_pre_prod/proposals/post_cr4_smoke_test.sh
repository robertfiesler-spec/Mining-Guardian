#!/bin/bash
# post_cr4_smoke_test.sh — Run on VPS AFTER CR-4 PR merges and services restart.
#
# Deterministic pass/fail check that:
#   1. All 8 services are active
#   2. The two HTTP APIs (dashboard, approval) respond
#   3. The mining-guardian scan loop completes one full cycle without AttributeError
#   4. The specific bug we fixed (_auto_create_missing_tickets line 1040) doesn't fire
#
# Exit code 0 = all green; non-zero = something failed; check stdout for which.
#
# Usage on VPS:
#   bash post_cr4_smoke_test.sh
#   echo "exit code: $?"

set -u

PASS=0
FAIL=0
FAIL_LINES=()

check() {
  local name="$1"
  local cond="$2"
  local detail="${3:-}"
  if [ "$cond" = "0" ]; then
    echo "  [PASS] $name"
    PASS=$((PASS + 1))
  else
    echo "  [FAIL] $name${detail:+ — $detail}"
    FAIL=$((FAIL + 1))
    FAIL_LINES+=("$name${detail:+ — $detail}")
  fi
}

echo "================================================================"
echo " MG POST-CR-4 SMOKE TEST  $(date -Iseconds)"
echo "================================================================"

# ── Section 1: service status ────────────────────────────────────────
echo ""
echo "── Services active ──"
SERVICES=(
  mining-guardian
  mining-guardian-alerts
  approval-api
  dashboard-api
  intelligence-report
  overnight-automation
  slack-commands
  slack-listener
)
for svc in "${SERVICES[@]}"; do
  if systemctl is-active --quiet "$svc"; then
    check "$svc active" 0
  else
    state=$(systemctl is-active "$svc" 2>/dev/null || echo "unknown")
    check "$svc active" 1 "state=$state"
  fi
done

# ── Section 2: HTTP API responsiveness ───────────────────────────────
echo ""
echo "── HTTP APIs respond ──"

# dashboard-api on :8585 — has /fleet/latest and /pending
if curl -sS --max-time 5 -o /dev/null -w "%{http_code}" http://127.0.0.1:8585/fleet/latest 2>/dev/null | grep -qE "^(200|204)$"; then
  check "dashboard-api /fleet/latest 2xx" 0
else
  code=$(curl -sS --max-time 5 -o /dev/null -w "%{http_code}" http://127.0.0.1:8585/fleet/latest 2>/dev/null || echo "unreachable")
  check "dashboard-api /fleet/latest 2xx" 1 "got $code"
fi

# approval-api on :8686 — has /pending
if curl -sS --max-time 5 -o /dev/null -w "%{http_code}" http://127.0.0.1:8686/pending 2>/dev/null | grep -qE "^(200|204)$"; then
  check "approval-api /pending 2xx" 0
else
  code=$(curl -sS --max-time 5 -o /dev/null -w "%{http_code}" http://127.0.0.1:8686/pending 2>/dev/null || echo "unreachable")
  check "approval-api /pending 2xx" 1 "got $code"
fi

# ── Section 3: scan loop healthy ─────────────────────────────────────
echo ""
echo "── mining-guardian scan loop ──"

# Look at the last 3 minutes of mining-guardian journal — at least one scan should
# have completed (loop runs every ~60s).
SINCE_RECENT="3 minutes ago"
recent_log=$(journalctl -u mining-guardian --since "$SINCE_RECENT" --no-pager 2>/dev/null)

# 3a. Some log activity (not silent / not crashed)
if [ -n "$recent_log" ]; then
  check "mining-guardian producing logs in last 3 min" 0
else
  check "mining-guardian producing logs in last 3 min" 1 "journal empty"
fi

# 3b. No new AttributeError in last 3 min
attr_err_count=$(echo "$recent_log" | grep -c "AttributeError" || true)
if [ "$attr_err_count" -eq 0 ]; then
  check "no AttributeError in last 3 min" 0
else
  check "no AttributeError in last 3 min" 1 "$attr_err_count occurrences"
fi

# 3c. The specific CR-4 bug (_auto_create_missing_tickets) didn't fire
auto_create_err=$(echo "$recent_log" | grep -c "_auto_create_missing_tickets" | head -1 || true)
recent_traceback_in_func=$(echo "$recent_log" | grep -B1 "Traceback" | grep -c "_auto_create_missing_tickets" || true)
if [ "$recent_traceback_in_func" -eq 0 ]; then
  check "no _auto_create_missing_tickets traceback in last 3 min" 0
else
  check "no _auto_create_missing_tickets traceback in last 3 min" 1 "$recent_traceback_in_func tracebacks"
fi

# 3d. No new psycopg2 errors
pg_err_count=$(echo "$recent_log" | grep -cE "psycopg2\.[A-Za-z]+Error" || true)
if [ "$pg_err_count" -eq 0 ]; then
  check "no psycopg2 errors in last 3 min" 0
else
  check "no psycopg2 errors in last 3 min" 1 "$pg_err_count occurrences"
fi

# 3e. Evidence of completed scan (look for typical end-of-scan log markers)
# Markers vary, but most loops emit "scan complete" or write a scan_id row.
scan_complete=$(echo "$recent_log" | grep -ciE "scan.*(complete|finished|done)|saved.*readings" || true)
if [ "$scan_complete" -gt 0 ]; then
  check "at least one scan completed in last 3 min" 0
else
  check "at least one scan completed in last 3 min" 1 "no completion markers found — may need longer window"
fi

# ── Section 4: dashboard-api / approval-api — no 500s in last 3 min ──
echo ""
echo "── HTTP services error-free ──"
for svc in dashboard-api approval-api; do
  log=$(journalctl -u "$svc" --since "$SINCE_RECENT" --no-pager 2>/dev/null)
  err=$(echo "$log" | grep -cE "AttributeError|psycopg2\.[A-Za-z]+Error|500 Internal" || true)
  if [ "$err" -eq 0 ]; then
    check "$svc — no errors in last 3 min" 0
  else
    check "$svc — no errors in last 3 min" 1 "$err error lines"
  fi
done

# ── Section 5: cross-check shim is in place ──────────────────────────
echo ""
echo "── CR-4 shim deployed ──"

# Locate the on-disk file (post-rename path)
GUARDIAN_DIR="/root/Mining-Guardian"
if [ ! -d "$GUARDIAN_DIR" ]; then
  GUARDIAN_DIR="/root/Mining-Gaurdian"
fi

if [ -f "$GUARDIAN_DIR/core/database_pg.py" ]; then
  if grep -q "_PgConnShim" "$GUARDIAN_DIR/core/database_pg.py"; then
    check "_PgConnShim class present in database_pg.py" 0
  else
    check "_PgConnShim class present in database_pg.py" 1 "shim missing — patch did not apply"
  fi
else
  check "_PgConnShim class present in database_pg.py" 1 "file not found at $GUARDIAN_DIR/core/database_pg.py"
fi

if [ -f "$GUARDIAN_DIR/core/mining_guardian.py" ]; then
  # Check one of CR-4's representative SQL conversions: line 1041 uses NOW() - INTERVAL
  if grep -q "NOW() - INTERVAL '30 minutes'" "$GUARDIAN_DIR/core/mining_guardian.py"; then
    check "CR-4 SQL conversions present in mining_guardian.py" 0
  else
    check "CR-4 SQL conversions present in mining_guardian.py" 1 "did not find NOW() - INTERVAL marker"
  fi
fi

# ── Final verdict ────────────────────────────────────────────────────
echo ""
echo "================================================================"
echo " RESULT: $PASS passed, $FAIL failed"
echo "================================================================"

if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "Failures:"
  for line in "${FAIL_LINES[@]}"; do
    echo "  • $line"
  done
  echo ""
  echo "Recommended next step: capture full journal for the failing service:"
  echo "  journalctl -u <service> --since \"5 minutes ago\" --no-pager > /tmp/mg_smoke_fail.txt"
  echo "Then paste /tmp/mg_smoke_fail.txt back to chat."
  exit 1
fi

echo ""
echo "All green. CR-4 looks healthy. Continue watching the journal for the next"
echo "30 minutes to be sure no rare code paths fire. Recommended:"
echo "  journalctl -u mining-guardian -f"
exit 0
