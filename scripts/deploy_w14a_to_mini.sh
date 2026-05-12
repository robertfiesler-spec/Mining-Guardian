#!/usr/bin/env bash
# scripts/deploy_w14a_to_mini.sh
#
# W14a deployment to the Mac Mini (2026-05-12).
#
# Copies the 28 .py files modified by PR #186 from the laptop repo into
# /Library/Application Support/MiningGuardian/ on the Mini, preserving
# directory structure. Then runs a bootout/bootstrap cycle on the 10
# always-on launchd services so they pick up the new Python code.
#
# Files deployed (28):
#   scripts/        (3 files)
#   console/        (1 file)
#   core/           (4 files — db_targets, database_pg, hashrate_evaluation,
#                    llm_analyzer, overnight_automation)
#   api/            (8 files)
#   ai/             (9 files including catalog_context)
#   intelligence-catalog/ (2 files in subdirs)
#
# Not deployed: tests/test_w14a_no_direct_pg_env_reads.py
#   (Mini install tree has no tests/ dir; the test is laptop-side only.)
#
# This script runs ON THE LAPTOP. It scp's to the Mini via Tailscale.
# The Mini-side bootout/bootstrap requires sudo and is documented in
# the comments below — operator runs that step manually with their
# sudo SSH session.

set -euo pipefail

REPO_ROOT="/Users/BigBobby/Documents/GitHub/Mining-Guardian"
MINI_USER="miningguardian"
MINI_HOST="100.69.66.32"
MINI_ROOT="/Library/Application Support/MiningGuardian"

# Files to deploy. Paths are relative to REPO_ROOT and to MINI_ROOT.
# Keep this list in sync with the W14a PR file list.
FILES=(
  # scripts/
  "scripts/daily_log_failure_report.py"
  "scripts/direct_collect_logs.py"
  "scripts/morning_briefing.py"
  # console/
  "console/system_state.py"
  # core/
  "core/db_targets.py"
  "core/database_pg.py"
  "core/hashrate_evaluation.py"
  "core/llm_analyzer.py"
  "core/overnight_automation.py"
  # api/
  "api/ai_dashboard_api.py"
  "api/ams_alert_listener.py"
  "api/approval_api.py"
  "api/dashboard_api.py"
  "api/intelligence_report_api.py"
  "api/slack_approval_listener.py"
  "api/slack_command_handler.py"
  "api/system_settings.py"
  # ai/
  "ai/ai_score.py"
  "ai/catalog_context.py"
  "ai/confidence_scorer.py"
  "ai/daily_deep_dive.py"
  "ai/fingerprint_builder.py"
  "ai/hvac_correlator.py"
  "ai/local_llm_analyzer.py"
  "ai/predictor.py"
  "ai/train_cohort.py"
  # intelligence-catalog/
  "intelligence-catalog/catalog-api/catalog_api.py"
  "intelligence-catalog/db/dual_writer.py"
)

# Pre-flight: confirm all source files exist on the laptop.
echo "================================================================"
echo "W14a Mini deployment — pre-flight check"
echo "================================================================"
missing=0
for f in "${FILES[@]}"; do
  if [[ ! -f "${REPO_ROOT}/${f}" ]]; then
    echo "  ❌ MISSING ON LAPTOP: ${f}"
    missing=$((missing + 1))
  fi
done
if (( missing > 0 )); then
  echo "❌ ${missing} file(s) missing on laptop. Aborting."
  exit 1
fi
echo "✅ All ${#FILES[@]} source files present on laptop."
echo

# Stage on Mini in /tmp/w14a-staging/ first (mirrors W05 deploy pattern).
# Safer than scp-direct-to-install-tree because it lets us diff before
# overwriting and it keeps the install tree untouched if scp fails midway.
echo "================================================================"
echo "Stage files to Mini at /tmp/w14a-staging/"
echo "================================================================"
ssh "${MINI_USER}@${MINI_HOST}" 'rm -rf /tmp/w14a-staging && mkdir -p /tmp/w14a-staging'

for f in "${FILES[@]}"; do
  dest_dir="/tmp/w14a-staging/$(dirname "$f")"
  ssh "${MINI_USER}@${MINI_HOST}" "mkdir -p '${dest_dir}'"
  scp -q "${REPO_ROOT}/${f}" "${MINI_USER}@${MINI_HOST}:${dest_dir}/$(basename "$f")"
  echo "  staged: ${f}"
done
echo "✅ All ${#FILES[@]} files staged."
echo

# Diff staged vs current install tree — confirms our changes are real
# and nothing else has drifted.
echo "================================================================"
echo "Diff staged vs current install tree"
echo "================================================================"
for f in "${FILES[@]}"; do
  staged="/tmp/w14a-staging/${f}"
  current="${MINI_ROOT}/${f}"
  diff_lines=$(ssh "${MINI_USER}@${MINI_HOST}" "diff -q '${staged}' '${current}' 2>/dev/null | wc -l | tr -d ' '")
  if [[ "${diff_lines}" == "0" ]]; then
    echo "  ≡ identical: ${f}  (no change — file may not have shipped to Mini yet, or already up to date)"
  else
    # Files differ — count the diff lines for a quick sanity check.
    line_count=$(ssh "${MINI_USER}@${MINI_HOST}" "diff '${staged}' '${current}' 2>/dev/null | wc -l | tr -d ' '")
    echo "  Δ change:     ${f}  (${line_count} diff lines)"
  fi
done
echo

echo "================================================================"
echo "Pre-deploy backup of current install tree (.pre-w14a-backup/)"
echo "================================================================"
ssh "${MINI_USER}@${MINI_HOST}" "mkdir -p '${MINI_ROOT}/.pre-w14a-backup'"
for f in "${FILES[@]}"; do
  dest_dir="${MINI_ROOT}/.pre-w14a-backup/$(dirname "$f")"
  ssh "${MINI_USER}@${MINI_HOST}" "mkdir -p '${dest_dir}' && cp '${MINI_ROOT}/${f}' '${dest_dir}/$(basename "$f")' 2>/dev/null || echo '  (skipped missing: ${f})'"
done
echo "✅ Backup taken at ${MINI_ROOT}/.pre-w14a-backup/"
echo "   Rollback: cp -R '${MINI_ROOT}/.pre-w14a-backup/'* '${MINI_ROOT}/'"
echo

echo "================================================================"
echo "Install: copy staged files into install tree"
echo "================================================================"
# The install tree is owned by miningguardian:staff per the May 12
# `ls -la` we ran. No sudo needed for the cp itself.
for f in "${FILES[@]}"; do
  staged="/tmp/w14a-staging/${f}"
  dest="${MINI_ROOT}/${f}"
  dest_dir="$(dirname "${dest}")"
  ssh "${MINI_USER}@${MINI_HOST}" "mkdir -p '${dest_dir}' && cp '${staged}' '${dest}'"
done
echo "✅ All ${#FILES[@]} files installed."
echo

echo "================================================================"
echo "Verify: spot-check 3 representative files for the new pattern"
echo "================================================================"
# Probe one file from each pattern variant to confirm the install
# actually shipped W14a code (not some half-applied state).
for f in "scripts/daily_log_failure_report.py" "core/database_pg.py" "ai/catalog_context.py"; do
  has_import=$(ssh "${MINI_USER}@${MINI_HOST}" "grep -c 'from core.db_targets import' '${MINI_ROOT}/${f}' 2>/dev/null || echo 0")
  if [[ "${has_import}" -gt 0 ]]; then
    echo "  ✅ ${f}: W14a import present"
  else
    echo "  ❌ ${f}: W14a import MISSING — install failed"
  fi
done
echo

echo "================================================================"
echo "✅ Deploy complete. NEXT STEP: bootout/bootstrap the 10 services."
echo "================================================================"
echo
echo "  ⚠️  REQUIRES SUDO — operator runs this step manually."
echo
echo "  In your sudo SSH session on the Mini:"
echo
echo "    for svc in scanner alerts approval-api console dashboard-api \\"
echo "               feedback-loop-daemon intelligence-report \\"
echo "               overnight-automation slack-commands slack-listener; do"
echo "      echo \"  → \${svc}\""
echo "      sudo launchctl bootout system \"/Library/LaunchDaemons/com.miningguardian.\${svc}.plist\" 2>/dev/null"
echo "      sudo launchctl bootstrap system \"/Library/LaunchDaemons/com.miningguardian.\${svc}.plist\""
echo "    done"
echo
echo "    # Then verify all 10 came back with fresh PIDs:"
echo "    sudo launchctl list | grep -E 'com\\.miningguardian\\.(scanner|alerts|approval-api|console|dashboard-api|feedback-loop-daemon|intelligence-report|overnight-automation|slack-commands|slack-listener)\$' | sort -k3"
echo
echo "  Expected: 10 services with new sequential PIDs (probably 87xxx range)."
echo "  Current baseline (pre-W14a) is 865xx range from this morning's W05/W05b."
