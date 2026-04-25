#!/bin/bash
# vps_journal_audit.sh — Run on VPS to inventory error signatures across all 8 services.
# Goal: confirm CR-4 covers all real production errors, and surface anything we missed.
#
# Usage on VPS:
#   bash vps_journal_audit.sh > /tmp/mg_journal_audit_$(date +%Y%m%d).txt
#   cat /tmp/mg_journal_audit_*.txt   # paste back to chat
#
# Safe: read-only. journalctl --since "7 days ago".

set -u

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

SINCE="7 days ago"

echo "================================================================"
echo " MG JOURNAL AUDIT  $(date -Iseconds)"
echo " Window: --since \"$SINCE\""
echo "================================================================"

for svc in "${SERVICES[@]}"; do
  echo ""
  echo "================================================================"
  echo " SERVICE: $svc"
  echo "================================================================"

  # Total error volume
  err_total=$(journalctl -u "$svc" --since "$SINCE" --no-pager 2>/dev/null \
              | grep -cE "ERROR|Traceback|AttributeError|psycopg2|OperationalError|ProgrammingError|SyntaxError" || true)
  echo "Total error/traceback lines (7d): $err_total"
  if [ "$err_total" -eq 0 ]; then
    echo "  (no errors — skipping detail breakdown)"
    continue
  fi

  echo ""
  echo "--- AttributeError signatures (top 15 unique) ---"
  journalctl -u "$svc" --since "$SINCE" --no-pager 2>/dev/null \
    | grep -oE "AttributeError: [^\"']*" \
    | sort | uniq -c | sort -rn | head -15

  echo ""
  echo "--- psycopg2 errors (top 15 unique) ---"
  journalctl -u "$svc" --since "$SINCE" --no-pager 2>/dev/null \
    | grep -oE "psycopg2\.[A-Za-z]+Error: [^\"']*" \
    | sort | uniq -c | sort -rn | head -15

  echo ""
  echo "--- 'syntax error at or near' (Postgres rejecting SQLite SQL) ---"
  journalctl -u "$svc" --since "$SINCE" --no-pager 2>/dev/null \
    | grep -iE "syntax error at or near" \
    | sed -E "s/.*(syntax error at or near \"[^\"]+\").*/\1/" \
    | sort | uniq -c | sort -rn | head -10

  echo ""
  echo "--- Traceback originating files (top 10) ---"
  journalctl -u "$svc" --since "$SINCE" --no-pager 2>/dev/null \
    | grep -oE 'File "[^"]+", line [0-9]+, in [^ ]+' \
    | sort | uniq -c | sort -rn | head -10

  echo ""
  echo "--- 'function ... does not exist' (Postgres rejecting SQLite functions) ---"
  journalctl -u "$svc" --since "$SINCE" --no-pager 2>/dev/null \
    | grep -iE "function.*does not exist|datetime\(.*now" \
    | sed -E "s/^.{0,80}(function [^ ]+ does not exist).*/\1/" \
    | sort | uniq -c | sort -rn | head -10
done

echo ""
echo "================================================================"
echo " SUMMARY: cross-service unique AttributeError signatures (top 20)"
echo "================================================================"
for svc in "${SERVICES[@]}"; do
  journalctl -u "$svc" --since "$SINCE" --no-pager 2>/dev/null \
    | grep -oE "AttributeError: [^\"']*"
done | sort | uniq -c | sort -rn | head -20

echo ""
echo "================================================================"
echo " SUMMARY: cross-service unique psycopg2 errors (top 20)"
echo "================================================================"
for svc in "${SERVICES[@]}"; do
  journalctl -u "$svc" --since "$SINCE" --no-pager 2>/dev/null \
    | grep -oE "psycopg2\.[A-Za-z]+Error: [^\"']*"
done | sort | uniq -c | sort -rn | head -20

echo ""
echo "================================================================"
echo " DONE  $(date -Iseconds)"
echo "================================================================"
