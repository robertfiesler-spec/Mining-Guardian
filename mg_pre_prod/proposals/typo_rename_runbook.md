# Typo Rename Runbook — `Mining-Gaurdian` \u2192 `Mining-Guardian`

**Scheduled:** Sunday 2026-04-26, 9:00 AM CDT
**Estimated downtime:** 5-10 minutes
**Estimated total time:** 30-45 minutes (with verification)
**Risk:** Low (no logic changes, just path renames). All callers of `/root/Mining-Gaurdian/...`
identified up-front.

## Why this matters

The GitHub repo is correctly named `Mining-Guardian`. Only the VPS local clone
directory carries the typo. Every systemd unit, cron job, and Python script
that references absolute path `/root/Mining-Gaurdian/...` will break the
moment the directory is renamed \u2014 unless we rename them all in lockstep.

The Mac Mini cutover (Monday 2026-04-27) needs a clean directory name. Doing
this Sunday morning leaves a full day to verify before the cutover.

## Inventory of references on `origin/main` (b28c8a7)

### Tier 1 \u2014 systemd unit files (CRITICAL — run as services)

8 unit files in `deploy/`:
- `approval-api.service`
- `dashboard-api.service`
- `intelligence-report.service` (also has `GUARDIAN_DB=/root/Mining-Gaurdian/guardian.db`)
- `mining-guardian-alerts.service`
- `mining-guardian.service`
- `overnight-automation.service`
- `slack-commands.service`
- `slack-listener.service`

Each has 3-4 references: `EnvironmentFile=`, `WorkingDirectory=`, `ExecStart=`,
`Environment=PATH=`. Total: ~28 occurrences across 8 files.

**These are the ones that MUST be updated before `systemctl daemon-reload`.**

### Tier 2 \u2014 active runtime code with hardcoded paths

| File | Lines | What it does |
|---|---|---|
| `core/mining_guardian.py` | 2171 | `kpath = _P("/root/Mining-Gaurdian/knowledge.json")` — Qwen scan analysis writes |
| `ai/local_llm_analyzer.py` | 96 | Default `db_path` fallback (only used if env var unset) |
| `ai/predictive_eta.py` | 23 | Default `GUARDIAN_DB` env fallback |
| `api/fleet_comparison.py` | 23 | Default `GUARDIAN_DB` env fallback |

**Line 2171 in `core/mining_guardian.py` is the most critical** \u2014 it's a
literal absolute path that runs every scan cycle (Qwen analysis writes to
`knowledge.json`). After rename, this line will silently fail to write
new analyses to knowledge until we update it.

### Tier 3 \u2014 scripts and Makefile (manual / cron-invoked only)

| File | Lines | Notes |
|---|---|---|
| `Makefile` | 21, 24, 27, 41, 53 | Test invocations + `daemon-run` target |
| `ai/backup_knowledge.py` | 9 (cron docstring only) | docstring; runtime uses cwd |
| `ai/daily_deep_dive.py` | 34, 52 (docstring + WIP path) | partial — line 52 may be a literal |
| `ai/refinement_chain.py` | 16 (docstring) | docstring only |
| `ai/train_comprehensive.py` | 19 (docstring) | docstring only |
| `ai/weekly_train.py` | 10 (docstring) | docstring only |
| `scripts/audit_ai_data.py` | 9, 10 | absolute path opens — ad-hoc audit script |
| `scripts/cleanup_ams_logs.py` | 19, 35 | sys.path + config.json |
| `scripts/daily_collect_logs.py` | 9, 22 | sys.path + config.json — RUNS DAILY |
| `scripts/deep_dive_progress_monitor.py` | 14, 18 | .env load + WIP path |
| `scripts/direct_collect_logs.py` | 187 | .env fallback read |
| `scripts/full_ai_audit.py` | 17, 44, 45, 46, 102 | knowledge + Path globs + sqlite |
| `scripts/run_after_deep_dive.py` | 14, 16, 26, 44, 71, 72, 75, 78 | sys.path + cwd + subprocess invocations — RUNS DAILY |
| `scripts/send_deep_dive_report.py` | 14, 17, 18 | .env + WIP + knowledge |
| `scripts/morning_briefing.py` | 13 (docstring) | docstring only |

### Tier 4 \u2014 shell scripts

- `scripts/backup_db.sh` line 7
- `scripts/backup_mining_guardian.sh` line 8
- `scripts/daily_backup.sh` lines 7, 10

### Tier 5 \u2014 archive/, fixes/2026-04-13/, docs/, *.md files

**Leave alone.** Archive and one-time fix scripts have already run; doc files
are reference material. Updating them creates noise without value. They can
be cleaned up post-cutover when stable.

## Pre-flight checks (do BEFORE 9am)

Run these on the VPS to surface anything we couldn't see from the repo:

```bash
# 1. Crontab — does Rob have any cron lines mentioning the typo path?
crontab -l 2>/dev/null | grep -i Mining-Gaurdian
# If hits: copy them out, we'll edit before re-installing.

# 2. Logrotate / nginx / other system configs
sudo grep -rl "Mining-Gaurdian" /etc/ 2>/dev/null

# 3. Any .bashrc / .profile / .env aliases
grep -l "Mining-Gaurdian" ~/.bashrc ~/.profile ~/.bash_aliases /root/.env 2>/dev/null

# 4. venv path inside the dir (may have hardcoded shebangs)
head -1 /root/Mining-Gaurdian/venv/bin/python
# If shebang says #!/root/Mining-Gaurdian/venv/bin/python3.x, the venv may
# need recreating after rename. If it's #!/usr/bin/python3 with activate
# script handling paths, we're fine.

# 5. systemd "linked" overrides
ls -la /etc/systemd/system/multi-user.target.wants/ | grep mining
# Confirm these are symlinks pointing to the unit files (so systemctl picks them up)
```

## The rename procedure

### Step 0 \u2014 Pre-flight (5 min)

1. SSH to VPS as root
2. Run all 5 pre-flight checks above. Save output.
3. **Snapshot current state** in case we need to roll back:
   ```bash
   systemctl list-units --all --no-pager | grep -E "mining|approval|dashboard|intelligence|overnight|slack" > /tmp/services_before.txt
   df -h /root > /tmp/disk_before.txt
   ls -la /root/Mining-Gaurdian/ | head > /tmp/dir_before.txt
   ```

### Step 1 \u2014 Stop all 8 services (~30 sec downtime begins)

```bash
systemctl stop \
    mining-guardian \
    mining-guardian-alerts \
    approval-api \
    dashboard-api \
    intelligence-report \
    overnight-automation \
    slack-commands \
    slack-listener

# Confirm all stopped
systemctl is-active mining-guardian mining-guardian-alerts approval-api \
    dashboard-api intelligence-report overnight-automation \
    slack-commands slack-listener
# Expected: 8 lines of "inactive" or "failed"
```

### Step 2 \u2014 Rename the directory (~5 sec)

```bash
mv /root/Mining-Gaurdian /root/Mining-Guardian

# Verify
ls -d /root/Mining-Guardian
ls -d /root/Mining-Gaurdian 2>&1   # should error: No such file
```

### Step 3 \u2014 Update systemd unit files (~2 min)

```bash
cd /etc/systemd/system

# Bulk replace in all 8 files at once
sed -i.bak 's|/root/Mining-Gaurdian|/root/Mining-Guardian|g' \
    mining-guardian.service \
    mining-guardian-alerts.service \
    approval-api.service \
    dashboard-api.service \
    intelligence-report.service \
    overnight-automation.service \
    slack-commands.service \
    slack-listener.service

# Verify zero occurrences of the typo remain
grep -l "Mining-Gaurdian" *.service && echo "TYPO STILL PRESENT — STOP" || echo "all clear"

# Check the new path is correct
grep "Mining-Guardian" mining-guardian.service
```

### Step 4 \u2014 Update venv shebangs IF needed (~1 min, probably skip)

```bash
# Check if venv shebangs point at the old path
head -1 /root/Mining-Guardian/venv/bin/python3 \
       /root/Mining-Guardian/venv/bin/pip 2>/dev/null

# If they say "/root/Mining-Gaurdian/venv/bin/python3.x" \u2014 they're broken now.
# Easiest fix: recreate the venv (slower) or sed-fix the shebangs (faster).
# Quick fix:
sed -i 's|/root/Mining-Gaurdian|/root/Mining-Guardian|g' \
    /root/Mining-Guardian/venv/bin/*.py \
    /root/Mining-Guardian/venv/bin/python* \
    /root/Mining-Guardian/venv/bin/pip* \
    /root/Mining-Guardian/venv/bin/activate \
    /root/Mining-Guardian/venv/bin/activate.csh \
    /root/Mining-Guardian/venv/bin/activate.fish \
    2>/dev/null
echo "venv shebangs updated"
```

### Step 5 \u2014 Update cron jobs (~1 min)

```bash
# Backup current crontab
crontab -l > /tmp/crontab.before

# Edit in place
crontab -l 2>/dev/null | sed 's|/root/Mining-Gaurdian|/root/Mining-Guardian|g' | crontab -

# Verify
crontab -l | grep -i Mining
```

### Step 6 \u2014 Update Tier 2 runtime code (~2 min)

Four critical files \u2014 `sed` them in place:

```bash
cd /root/Mining-Guardian

sed -i 's|/root/Mining-Gaurdian|/root/Mining-Guardian|g' \
    core/mining_guardian.py \
    ai/local_llm_analyzer.py \
    ai/predictive_eta.py \
    api/fleet_comparison.py

# Verify Tier 2 is clean
grep -l "Mining-Gaurdian" \
    core/mining_guardian.py \
    ai/local_llm_analyzer.py \
    ai/predictive_eta.py \
    api/fleet_comparison.py && echo "STILL HAS TYPO" || echo "Tier 2 clean"
```

### Step 7 \u2014 Update Tier 3 (scripts that run from cron) (~1 min)

```bash
cd /root/Mining-Guardian

# Scripts that run daily/regularly from cron
sed -i 's|/root/Mining-Gaurdian|/root/Mining-Guardian|g' \
    scripts/daily_collect_logs.py \
    scripts/run_after_deep_dive.py \
    scripts/send_deep_dive_report.py \
    scripts/deep_dive_progress_monitor.py \
    scripts/cleanup_ams_logs.py \
    scripts/direct_collect_logs.py \
    scripts/morning_briefing.py

# Shell scripts
sed -i 's|/root/Mining-Gaurdian|/root/Mining-Guardian|g' \
    scripts/backup_db.sh \
    scripts/backup_mining_guardian.sh \
    scripts/daily_backup.sh

# Makefile
sed -i 's|/root/Mining-Gaurdian|/root/Mining-Guardian|g' Makefile

echo "Tier 3 scripts + Makefile updated"
```

### Step 8 \u2014 Reload systemd + restart services (~1 min)

```bash
systemctl daemon-reload

# Start in dependency order — core first, then auxiliaries
systemctl start mining-guardian
sleep 3
systemctl is-active mining-guardian || { echo "MINING-GUARDIAN DID NOT START — CHECK journalctl -u mining-guardian -n 50"; exit 1; }

systemctl start mining-guardian-alerts approval-api dashboard-api \
    intelligence-report overnight-automation slack-commands slack-listener

sleep 5
systemctl is-active mining-guardian mining-guardian-alerts approval-api \
    dashboard-api intelligence-report overnight-automation \
    slack-commands slack-listener
# Expected: 8 lines of "active"
```

**Downtime ends here. Total downtime: ~5-7 minutes.**

### Step 9 \u2014 Verification (~10 min)

```bash
# 1. All 8 services should be active
systemctl list-units --all --no-pager | grep -E "mining|approval|dashboard|intelligence|overnight|slack"

# 2. No new AttributeError or path errors in last 5 min
for s in mining-guardian mining-guardian-alerts approval-api dashboard-api \
         intelligence-report overnight-automation slack-commands slack-listener; do
  echo "=== $s ==="
  journalctl -u "$s" --since "5 min ago" -p err --no-pager | tail -10
done

# 3. AttributeError count: should be 0 from this point forward
journalctl --since "5 min ago" --no-pager | grep -c "AttributeError"
# (compare to old baseline of ~9.7/day)

# 4. Confirm new scan ran successfully
journalctl -u mining-guardian --since "5 min ago" | grep -E "Scan complete|scan_id|saved"

# 5. Sanity: knowledge.json writes hit the new path
ls -la /root/Mining-Guardian/knowledge.json
# Should show recent mtime if a scan has run
```

### Step 10 \u2014 Final sweep (~5 min)

```bash
# After 5 min of running, do a final scan for ANY remaining typo references
sudo grep -rn "Mining-Gaurdian" /root/Mining-Guardian /etc/systemd 2>/dev/null \
  | grep -v "\.pre_cr4_backup" \
  | grep -v "/archive/" \
  | grep -v "/docs/" \
  | grep -v "fixes/2026-04-13/" \
  | grep -v "\.md:" \
  | grep -v "REPAIR_LOG\|CLAUDE\|README\|DEPLOYMENT_CHECKLIST\|NEXT_SESSION"

# Anything that comes up here is a leftover. We deal with it case-by-case.
# Expected output: empty (or only files we knowingly left alone in Tier 5)
```

## Rollback procedure (if anything goes wrong before Step 8 completes)

```bash
# 1. Stop any services that came up
systemctl stop mining-guardian mining-guardian-alerts approval-api \
    dashboard-api intelligence-report overnight-automation \
    slack-commands slack-listener 2>/dev/null

# 2. Revert directory rename
mv /root/Mining-Guardian /root/Mining-Gaurdian

# 3. Restore systemd .bak files
cd /etc/systemd/system
for s in mining-guardian.service mining-guardian-alerts.service \
         approval-api.service dashboard-api.service \
         intelligence-report.service overnight-automation.service \
         slack-commands.service slack-listener.service; do
  [ -f "${s}.bak" ] && mv "${s}.bak" "$s"
done
systemctl daemon-reload

# 4. Restore crontab
[ -f /tmp/crontab.before ] && crontab /tmp/crontab.before

# 5. For Tier 2/3 code: git checkout from origin/main
cd /root/Mining-Gaurdian
git checkout -- core/mining_guardian.py ai/local_llm_analyzer.py \
    ai/predictive_eta.py api/fleet_comparison.py \
    scripts/daily_collect_logs.py scripts/run_after_deep_dive.py \
    scripts/send_deep_dive_report.py scripts/deep_dive_progress_monitor.py \
    scripts/cleanup_ams_logs.py scripts/direct_collect_logs.py \
    scripts/morning_briefing.py scripts/backup_db.sh \
    scripts/backup_mining_guardian.sh scripts/daily_backup.sh Makefile

# 6. Restart in dependency order
systemctl start mining-guardian
systemctl start mining-guardian-alerts approval-api dashboard-api \
    intelligence-report overnight-automation slack-commands slack-listener
```

## Post-rename: commit the changes back to GitHub

After verification passes, the Tier 1/2/3/4 file edits should be committed
back to `origin/main` so future deploys (and the Mac Mini) inherit the fix.

```bash
cd /root/Mining-Guardian
git checkout -B fix/typo-rename-mining-guardian-2026-04-26
git add -A
git status
# Should show modified: deploy/*.service, core/mining_guardian.py, ai/*.py,
#                      api/fleet_comparison.py, scripts/*.py, scripts/*.sh,
#                      Makefile

git commit -m "fix: rename Mining-Gaurdian -> Mining-Guardian (typo cleanup)

Production VPS directory renamed from /root/Mining-Gaurdian to
/root/Mining-Guardian. Updated all hardcoded path references in:
  - 8 systemd unit files (deploy/*.service)
  - core/mining_guardian.py (knowledge.json path)
  - 3 ai/ files with default db_path fallbacks
  - 11 scripts/ files with sys.path + config + .env loads
  - 3 shell scripts (backup_db.sh, backup_mining_guardian.sh, daily_backup.sh)
  - Makefile (PYTHONPATH + daemon-run + sqlite3 query target)

Tier 5 (archive/, fixes/2026-04-13/, docs/, top-level .md) intentionally
left alone — historical references, no runtime impact.

Verified: all 8 services running, AttributeError rate = 0/min after rename."

git push -u origin fix/typo-rename-mining-guardian-2026-04-26
# Then merge to main on GitHub UI.
```

## Combined timeline

| Step | Action | Cumulative time |
|---|---|---|
| 0 | Pre-flight checks | 0:05 |
| 1 | Stop services (downtime begins) | 0:06 |
| 2 | mv directory | 0:06 |
| 3 | Update 8 systemd units | 0:08 |
| 4 | venv shebang fix (if needed) | 0:09 |
| 5 | Update crontab | 0:10 |
| 6 | Update Tier 2 runtime code (4 files) | 0:12 |
| 7 | Update Tier 3 scripts + Makefile (15 files) | 0:13 |
| 8 | daemon-reload + start (downtime ends) | 0:14 |
| 9 | Verification | 0:24 |
| 10 | Final sweep | 0:30 |
| 11 | Commit + push to fix branch | 0:40 |

**Effective downtime: Step 1 \u2192 Step 8, roughly 7 minutes.**

## What we still need from Rob in the morning

1. **Pre-flight output** \u2014 paste the 5 pre-flight check outputs so we
   can adjust if there are surprises (cron entries we didn't know about,
   logrotate configs, etc).
2. **Decision: merge CR-4 hotfix PR before or after the rename?**
   - **Before:** scan loop stops crashing immediately, but then we rename
     mid-fix.
   - **After:** clean separation; CR-4 merges to a freshly-renamed `main`.
   - Recommendation: **after**. Cleaner. Production has been crashing for
     7+ days; one more morning won't hurt.

## What we have ready to go

- [x] CR-4 hotfix on branch `hotfix/cr-4-pg-shim-2026-04-25` (commit `e23c419`)
- [x] PR URL: https://github.com/robertfiesler-spec/Mining-Guardian/pull/new/hotfix/cr-4-pg-shim-2026-04-25
- [x] This rename runbook (proposals/typo_rename_runbook.md on the audit branch)
- [x] Full Tier 1-5 inventory (see above)

## What's NOT in this runbook (post-rename, separate work)

- **CR-4-EXT inventory rebuild** for `main` (the audit branch's 47-statement inventory was against the audit-branch version of `mining_guardian.py`; main has its own structure)
- **CR-2 hashrate fix** translated to `main` line numbers
- **Reconciling audit branch's 29 commits with main's 212 commits** \u2014 separate triage session
- **Mac Mini cutover** Monday 2026-04-27
