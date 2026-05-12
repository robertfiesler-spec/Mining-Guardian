#!/usr/bin/env bash
# scripts/disable_sleep.sh
#
# W01 (pmset portion) — disable Mac Mini sleep so launchd StartCalendarInterval
# jobs fire on schedule. macOS does NOT wake from sleep for
# StartCalendarInterval (only pmset repeat wake does that), so a sleeping Mini
# silently misses any scheduled job during the sleep window.
#
# See:
#   - docs/strategy/04_MASTER_EXECUTION_PLAN.md §W01
#   - docs/strategy/01_PERFORMANCE_AUDIT.md     §1.2
#
# Runs on the Mac Mini. Requires sudo.

set -euo pipefail

echo "================================================================"
echo "W01 — disable Mac Mini sleep so scheduled jobs don't miss fires"
echo "================================================================"
echo
echo "Before:"
pmset -g | head -25
echo

echo "Applying: sleep 0 disksleep 0"
echo "(needs sudo)"
sudo pmset -a sleep 0 disksleep 0

echo
echo "After:"
pmset -g | head -25
echo

# Verify
sleep_val=$(pmset -g | awk '/^[[:space:]]*sleep[[:space:]]/ {print $2}')
disk_val=$(pmset -g | awk '/^[[:space:]]*disksleep[[:space:]]/ {print $2}')

if [[ "$sleep_val" = "0" && "$disk_val" = "0" ]]; then
  echo "✅ Sleep disabled (sleep=0, disksleep=0)."
  echo
  echo "Note: if the Mini ever reboots and somehow comes back with sleep enabled,"
  echo "re-run this script. (Should not happen — pmset -a is persistent.)"
  exit 0
else
  echo "⚠️ Unexpected values: sleep=${sleep_val}, disksleep=${disk_val}"
  echo "   Investigate before relying on scheduled jobs."
  exit 1
fi
