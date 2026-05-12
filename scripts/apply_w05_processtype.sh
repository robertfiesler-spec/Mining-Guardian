#!/usr/bin/env bash
# scripts/apply_w05_processtype.sh
#
# W05 — flip ProcessType from Background to Standard for the 9 always-on
# Mining Guardian services on the Mac Mini. See:
#   - docs/strategy/04_MASTER_EXECUTION_PLAN.md  §W05  (original Plan, 6 plists)
#   - docs/strategy/AMENDMENTS_2026-05-12.md     §A02  (expansion to 9 plists)
#
# This script runs ON the Mac Mini, AFTER the patch has been applied to
# /Library/Application Support/MiningGuardian/ via either an installer
# refresh or manual scp. It assumes the 9 plist files at
# /Library/LaunchDaemons/com.miningguardian.<service>.plist already
# contain <string>Standard</string> for ProcessType.
#
# What it does:
#   - bootout each affected service
#   - bootstrap each affected service
#   - verify each has a numeric PID and ProcessType=Standard
#
# Rollback:
#   - flip the plists back to Background and re-run this script

set -euo pipefail

SERVICES=(
  scanner
  alerts
  approval-api
  console
  dashboard-api
  intelligence-report
  overnight-automation
  slack-commands
  slack-listener
)

LAUNCHD_DIR="/Library/LaunchDaemons"

echo "================================================================"
echo "W05 — flip ProcessType to Standard on ${#SERVICES[@]} always-on services"
echo "================================================================"
echo

# Pre-check: confirm the plists on disk already say Standard.
echo "--- pre-check: plist contents on disk ---"
all_ready=true
for svc in "${SERVICES[@]}"; do
  plist="${LAUNCHD_DIR}/com.miningguardian.${svc}.plist"
  if [[ ! -f "$plist" ]]; then
    echo "  ❌ ${svc}: ${plist} not found"
    all_ready=false
    continue
  fi
  pt=$(grep -A1 '<key>ProcessType</key>' "$plist" | tail -1 | tr -d '[:space:]')
  case "$pt" in
    "<string>Standard</string>")
      echo "  ✅ ${svc}: $pt"
      ;;
    "<string>Background</string>")
      echo "  ⚠️ ${svc}: still Background — patch not yet applied to disk"
      all_ready=false
      ;;
    *)
      echo "  ❓ ${svc}: unexpected value: $pt"
      all_ready=false
      ;;
  esac
done

if ! $all_ready; then
  echo
  echo "Pre-check failed. The plist files on disk must contain"
  echo "<string>Standard</string> before this script can apply the change."
  echo "Apply the W05 patch first, then re-run this script."
  exit 1
fi

echo
echo "--- bootout + bootstrap each service ---"
echo "(needs sudo)"
echo

for svc in "${SERVICES[@]}"; do
  plist="${LAUNCHD_DIR}/com.miningguardian.${svc}.plist"
  echo "  → ${svc}"
  if ! sudo launchctl bootout system "$plist" 2>&1 | grep -v "Boot-out failed: 5: Input/output error" || true; then
    : # bootout reports an error if the service isn't currently loaded — tolerate
  fi
  sudo launchctl bootstrap system "$plist"
done

echo
echo "--- post-check: verify all 9 services have numeric PIDs ---"
echo
launchctl list | grep com.miningguardian | head -30
echo

count=$(launchctl list | grep -c com.miningguardian || true)
no_pid=$(launchctl list | grep com.miningguardian | awk '{print $1}' | grep -c '^-' || true)
echo "Total Mining Guardian services loaded: ${count}"
echo "Services without a PID (dash PIDs):    ${no_pid}"

if (( no_pid > 0 )); then
  echo
  echo "⚠️ Some services failed to start. Check log files:"
  echo "   /Library/Application Support/MiningGuardian/logs/*.err.log"
  exit 2
fi

echo
echo "================================================================"
echo "✅ W05 applied. All 9 always-on services running as Standard."
echo "================================================================"
echo
echo "Next: watch latency on Slack approval round-trip — should be"
echo "noticeably faster. If anything regresses, rollback is:"
echo "  1. Edit each plist: <string>Standard</string> → <string>Background</string>"
echo "  2. Re-run this script"
