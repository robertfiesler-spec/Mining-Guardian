# Mining Guardian — Deployment Checklist

**Target:** customer Mac Mini (macOS 14+, Apple Silicon, 16 GB RAM, ≥50 GB free)
**Installer:** signed/notarized `MiningGuardian-1.0.0-<sha>.pkg`
**Last updated:** 2026-04-29 (repo doc sweep — supersedes Bucket 6f)

> **The Mac Mini install is a fresh, standalone deployment.** The customer Mini stands up its own Postgres operational DB and catalog DB during `scripts/setup.sh`; there is no migration step. The historical VPS / systemd-era checklist (April 15 2026 baseline) is preserved in **Appendix A** at the bottom of this file for reference only — do not follow it on a Mac Mini install.

---

## 0. Prerequisites (operator side, before touching the Mac)

- [ ] All four installer PRs merged to `main`:
  - PR #74 — Bucket 6a: 5 LaunchDaemon plists + 8 launcher wrappers
  - PR #75 — Bucket 6b: `scripts/setup.sh` v2 (15 phases)
  - PR #76 — Bucket 6c: `scripts/restore_from_snapshot.sh` (8 phases — kept for historical / lab use only; not part of the customer fresh-install path)
  - PR #77 — Bucket 6d: Grafana provisioning bundle + `scripts/install_grafana_provisioning.sh`
- [ ] Migrations 001–005 present in `migrations/` and applied automatically by `setup.sh` Phase 5 (operational + catalog schemas, including the 320-row miner_models seed (313 baseline + 7 Bitaxe added in PR #102))
- [ ] `MG_DB_PASSWORD` generated for this Mac (32-char): `openssl rand -base64 24`
- [ ] `CATALOG_API_KEY` generated: `openssl rand -hex 32`
- [ ] AMS API username + password handed to operator
- [ ] Slack bot token + signing secret + target channel ID available
- [ ] Site name decided (lowercase-with-hyphens, e.g. `bixbit-fairfax-1`)
- [ ] USB stick "MG Install" available with `MiningGuardian-1.0.0-<sha>.pkg` (do not erase the stick — replace files only)

---

## 1. Install the .pkg

### 1.1. macOS preconditions

- [ ] macOS Sonoma 14.5 or newer (`sw_vers -productVersion`)
- [ ] Apple Silicon (`uname -m` → `arm64`)
- [ ] Logged in as the operator user that will own Mining Guardian (NOT a separate `mg` daemon user — the agents need keychain access for AMS / Slack creds)
- [ ] FileVault either off, or operator knows the recovery key

### 1.2. Run the installer

- [ ] Insert USB stick "MG Install"
- [ ] Double-click `MiningGuardian-1.0.0-<sha>.pkg` → walk through the welcome screen (navy / BTC orange / electric blue branding from PR #54 / `installer/macos-pkg/resources/welcome.html`)
- [ ] Enter admin password when prompted
- [ ] Wait for "Installing Mining Guardian" screen (typically 5–8 minutes for the binary install — `setup.sh` runs separately afterward)
- [ ] Confirm "Mining Guardian installed successfully" screen

### 1.3. Run `scripts/setup.sh`

- [ ] Open Terminal natively (right-click Terminal in `/Applications/Utilities` → Get Info → uncheck "Open using Rosetta" — applies to Apple Silicon Macs only)
- [ ] `cd /Library/Application Support/MiningGuardian` (the install root from `installer/macos-pkg/Distribution.xml`)
- [ ] `zsh scripts/setup.sh` (or `--dry-run-install` first to see the plan)
- [ ] Walk through Phase 2 prompts; **secrets are read with `read -s` so nothing echoes to the terminal scrollback** (S-14 mitigation)

---

## 2. Post-install state checks

> Each check below is a **specific command**. If you're filling this checklist for a real Mac Mini ship, paste the actual output beside the command — that's what makes this checklist descriptive of observed reality (per Bucket 6e runbook §"Bucket 6e exit criteria → Bucket 6f").

### 2.1. LaunchDaemons

```bash
launchctl list | grep com.miningguardian | wc -l
# expected: 9
```

- [ ] All 9 services loaded
- [ ] No service shows PID `-` (which means crashed at first launch — check `~/Library/Logs/MiningGuardian/<service>_stderr.log`)
- [ ] `launchctl error <last_exit>` returns `0` for each service

```bash
launchctl list | grep com.miningguardian
# example expected output (Mac-Mini ship will paste real output here):
# PID    Status  Label
# 12345  0       com.miningguardian.scanner
# 12346  0       com.miningguardian.dashboard-api
# 12347  0       com.miningguardian.approval-api
# 12348  0       com.miningguardian.alerts
# 12349  0       com.miningguardian.intelligence-report
# 12350  0       com.miningguardian.overnight-automation
# 12351  0       com.miningguardian.slack-listener
# 12352  0       com.miningguardian.slack-commands
# 12353  0       com.miningguardian.cleanup
```

### 2.2. Cron (parallel to launchd during the v1→v2 transition)

```bash
crontab -l | grep -c MiningGuardian
# expected: 9
```

- [ ] All 9 cron jobs installed
- [ ] Operator granted Full Disk Access to `/usr/sbin/cron` (System Settings → Privacy & Security → Full Disk Access)

### 2.3. Postgres

```bash
brew services list | grep postgresql@16
# expected: started
psql -U guardian_app -d mining_guardian -c '\dt' | wc -l
# expected: ≥ 24 tables
psql -U guardian_app -d mining_guardian_catalog -c "\dn" | grep -E 'hardware|firmware|ops|knowledge'
# expected: 4 schemas
psql -U guardian_app -d mining_guardian_catalog -c "SELECT COUNT(*) FROM hardware.miner_models;"
# expected: 320 (or current seed count — match against intelligence-catalog/seed-data/seed_miner_models.sql)
```

- [ ] `mining_guardian` operational DB has all expected tables
- [ ] `mining_guardian_catalog` has 4 schemas + 320 miner models
- [ ] `~/Mining-Guardian/.env` mode `600`, contains non-default `MG_DB_PASSWORD` and `CATALOG_API_KEY`

### 2.4. Ollama

```bash
ollama list | grep qwen2.5:14b-instruct-q4_K_M
ollama run qwen2.5:14b-instruct-q4_K_M 'Say "OK"' --hidethinking 2>/dev/null
# expected: model line in `ollama list`, prompt returns "OK"
```

- [ ] `qwen2.5:14b-instruct-q4_K_M` model pulled (~9 GB)
- [ ] Smoke prompt returns expected string

### 2.5. Grafana

```bash
brew services list | grep grafana                                         # started
ls /opt/homebrew/var/lib/grafana/provisioning/datasources/mining_guardian.yml
ls /opt/homebrew/var/lib/grafana/provisioning/dashboards/mining_guardian.yml
ls /Library/Application Support/MiningGuardian/grafana/dashboards/*.json | wc -l            # 3
open http://localhost:3000                                                # admin / admin (change on first login)
```

In the browser at `http://localhost:3000`:
- [ ] 2 datasources visible: **Mining Guardian (operational)** + **Mining Guardian Catalog**
- [ ] Both datasources test green (Postgres reachable, password works)
- [ ] Folder **"Mining Guardian"** contains 3 dashboards:
  - Mining Guardian — Fleet Overview
  - Mining Guardian — Scans & Collection Health
  - Mining Guardian — Miner Models Catalog
- [ ] All 3 dashboards render their navy + BTC orange header strip
- [ ] Dashboards either show data (if scans have run) or "No data" cleanly (no SQL errors)

### 2.6. Tailscale (if `--tailscale` flag was used during setup)

```bash
tailscale status
tailscale ip -4
# expected: 100.x.y.z address, machine joined to operator mesh
```

- [ ] Tailscale up, machine has 100.x.y.z IP
- [ ] Mac is reachable via Tailscale from operator's primary device

### 2.7. Secrets / `.env`

```bash
ls -la ~/Mining-Guardian/.env
# expected: -rw-------  …  ~/Mining-Guardian/.env  (mode 600)
grep -c '^MG_DB_PASSWORD=' ~/Mining-Guardian/.env                         # 1
grep -c '^CATALOG_API_KEY=' ~/Mining-Guardian/.env                        # 1
grep '^MG_DB_PASSWORD=CHANGE_ME' ~/Mining-Guardian/.env || echo "OK no default"
grep '^CATALOG_API_KEY=changeme' ~/Mining-Guardian/.env || echo "OK no default"
```

- [ ] `.env` exists, mode `600`
- [ ] No default sentinel passwords (S-1 / S-6 mitigations engaged)
- [ ] `dry_run=true` set initially (operator flips to `false` after smoke test passes)

### 2.8. Smoke test — first scan

```bash
cd /Library/Application Support/MiningGuardian
.venv/bin/python core/scanner.py --once 2>&1 | tail -30
```

- [ ] Scanner runs without crashing
- [ ] Either reports miners scanned (if on lab LAN) or "no miners reachable" cleanly (if not)
- [ ] Row appears in `scans` table: `psql -U guardian_app -d mining_guardian -c 'SELECT * FROM scans ORDER BY scanned_at DESC LIMIT 1;'`

### 2.9. Slack ping

- [ ] `setup.sh` Phase 14 posted `Mining Guardian v1.0 setup complete on <hostname>` to the configured Slack channel
- [ ] Bot user in Slack channel responds to `/mg-status` (basic Slack-command roundtrip)

---

## 3. Restore-from-snapshot path (lab / historical only)

The customer Mac Mini install is **fresh** — `setup.sh` provisions empty operational and catalog Postgres databases, applies migrations 001–005, and seeds the catalog from `intelligence-catalog/seed-data/` during Phase 5. No snapshot restore is required.

`scripts/restore_from_snapshot.sh` is preserved for lab use (e.g., re-deploying the proof-of-concept site against an existing operational dataset) and is documented in the script header. It is **not** part of the customer install path. If you find yourself reading this section on a customer install, skip ahead — you do not need it.

---

## 4. Operator sign-off

| Check | Status | Notes |
|---|---|---|
| All 9 LaunchDaemons running | ☐ | |
| All 9 cron jobs installed (FDA granted) | ☐ | |
| 2 Grafana datasources test green | ☐ | |
| 3 Grafana dashboards render | ☐ | |
| First scan recorded in `scans` table | ☐ | |
| Slack ping received | ☐ | |
| `.env` mode 600, no default secrets | ☐ | |
| Tailscale up (if applicable) | ☐ | |


**Operator name:** ________________________
**Mac Mini hostname:** ________________________
**Date:** ________________________
**Site name:** ________________________
**`MiningGuardian-1.0.0-<sha>.pkg` SHA:** ________________________
**Notarization ID:** ________________________

---

## 5. Common failure modes

See `docs/RUNBOOK_BUCKET_6E_SANDBOX_TEST.md` §"Failure-mode catalog" for the full Phase × symptom × fix table. The most-frequent issues during fresh installs:

| Symptom | Quick fix |
|---|---|
| Brew install fails on Apple Silicon | Reopen Terminal natively (uncheck Rosetta in Get Info), rerun |
| `launchctl load` exit 5 on a plist | `plutil -lint ~/Library/LaunchAgents/com.miningguardian.<name>.plist` |
| Grafana shows "No data" but rows exist in Postgres | Datasource yaml password expansion failed — confirm `${GUARDIAN_PG_PASSWORD}` is set in user shell env so brew-services-managed Grafana inherits it |
| Cron jobs fire but jobs that read `~/Documents` silently fail | Operator skipped Full Disk Access prompt; grant in System Settings → Privacy & Security |
| `pg_restore` complains about role `guardian_app` | `setup.sh` Phase 4 must run before `restore_from_snapshot.sh` — order matters |

---

## 6. Rollback plan (if a restore goes wrong)

```bash
# On the Mac:
cd /Library/Application Support/MiningGuardian
brew services stop grafana

# .env
ls -la .env.bak.*
cp .env.bak.<latest_ts> .env
chmod 600 .env

# grafana.db
ls /opt/homebrew/var/lib/grafana/grafana.db.bak.*
cp /opt/homebrew/var/lib/grafana/grafana.db.bak.<latest_ts> /opt/homebrew/var/lib/grafana/grafana.db

# Postgres — drop and recreate from a known-good dump (operator must have one)
brew services restart postgresql@16
sudo -u $(whoami) dropdb mining_guardian
sudo -u $(whoami) createdb -O guardian_app mining_guardian
psql -U guardian_app -d mining_guardian -f migrations/001_initial_schema.sql
# … plus 002 / 003 / 004 once Bucket 5.7 lands

brew services restart grafana
launchctl kickstart -k gui/$UID/com.miningguardian.scanner
# (repeat for each service)
```

---

## 7. Reference — What was deprecated

The previous Mining Guardian deployment lived on a Debian VPS (`srv1549463`) running 7 systemd units behind Caddy + Cloudflare Tunnel. That model is **deprecated as of 2026-04-23** with the migration to per-customer Mac Minis. The VPS still runs as the catalog Postgres host (`mining_guardian_catalog` schemas `hardware.*` / `firmware.*` / `ops.*` / `knowledge.*` are sourced there) and as the Grafana frontend during the transition window, but no new operational telemetry routes through it.

The original 21-fix VPS deployment checklist (April 15 2026) is preserved verbatim in **Appendix A** below for historical reference. **Do not follow Appendix A on a Mac Mini install** — it describes a different OS, a different service manager, and a different network topology.

---

# Appendix A — Historical: VPS / systemd Deployment Checklist (April 15 2026)

> **DEPRECATED.** Preserved for reference. This describes the previous Debian VPS deployment that was migrated away from on 2026-04-23. Do not follow on a Mac Mini.

## 21 HIGH PRIORITY FIXES READY FOR DEPLOYMENT

### Pre-Deployment Steps

**1. Environment Variables - Add to .env:**
```bash
# Local Mac Mini Ollama (D-9 / S-13). Postinstall already writes
# OLLAMA_HOST=http://127.0.0.1:11434 to .env at install time; OLLAMA_URL
# is the legacy generate-endpoint variable that some code paths still
# read. Setting both is safe.
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_URL=http://127.0.0.1:11434/api/generate

# Need to add:
DASHBOARD_URL=http://127.0.0.1:8585
AURADINE_USER=admin
AURADINE_PASS=admin
AUTHORIZED_SLACK_USER_IDS=U07AGTT8CLD
```

**2. Systemd Service Reload:**
```bash
systemctl daemon-reload
```

**3. Service Restarts (in order):**
```bash
systemctl restart mining-guardian
systemctl restart approval-api
systemctl restart dashboard-api
systemctl restart slack-listener
systemctl restart slack-commands
systemctl restart overnight-automation
systemctl restart mining-guardian-alerts
```

### Post-Deployment Verification (VPS-era)

**1. Check Services Running:**
```bash
systemctl status mining-guardian approval-api dashboard-api slack-listener slack-commands overnight-automation
```

**2. Verify Environment Variables Loaded:**
```bash
journalctl -u mining-guardian -n 50 | grep -i ollama
tail -f /root/Mining-Guardian/mining_guardian.log | grep -i "knowledge\|operator_rules"
```

**3. Test Log Rotation:**
```bash
ls -lh /root/Mining-Guardian/mining_guardian.log*
```

### Known Issues / Manual Fixes (VPS-era)

**CQ-6 to CQ-10:** 9 SQLite connections need manual context manager wrapping
- `api/dashboard_api.py` line 367
- `api/approval_api.py` line 88
- `api/ams_alert_listener.py` lines 96, 122, 135, 150, 165
- `api/slack_command_handler.py` line 69

**CQ-14, CQ-15:** Token access methods need manual lock wrapping (operational SQLite — no longer the live store; see Postgres migration 2026-04-24)

### Rollback Plan (VPS-era)

```bash
cd /root/Mining-Guardian
for f in *.backup_*; do
  orig="${f%.backup_*}"
  cp "$f" "$orig"
done
systemctl restart mining-guardian approval-api dashboard-api
```

### Intelligence Report API service (April 15 2026, VPS-era)

```bash
cd /root/Mining-Guardian && git pull origin main
/root/Mining-Guardian/venv/bin/pip install fastapi uvicorn
cp /root/Mining-Guardian/deploy/intelligence-report.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable intelligence-report.service
systemctl start intelligence-report.service
curl http://localhost:8590/health
# Expected: {"status":"ok","models":226,"version":"2.1.0",…}
```

### Intelligence Report v2.1 Files (April 16 2026, VPS-era)

| File | Purpose |
|------|---------|
| `api/intelligence_report_api.py` | Main API — 1,352+ lines, 9 report sections |
| `intelligence-catalog/data/correction_rules.json` | WhatsMiner cooling type corrections |
| `intelligence-catalog/data/unified_miner_index.json` | 226 merged miner models |
| `intelligence-catalog/data/miner_enrichment_master.csv` | 277 models with detailed specs |
| `deploy/intelligence-report.service` | systemd unit file |

Live data sources (fetched at runtime, cached 15 min):
- CoinGecko API — BTC price USD
- mempool.space API — network difficulty + hashrate
- blockchain.info — fallback

### Success Criteria (VPS-era)

✅ All 8 services running (7 original + intelligence-report)
✅ Hourly scans complete
✅ LLM calls show knowledge context (DG-3)
✅ No connection leak warnings
✅ Slack commands work with authorization
✅ Intelligence Report API returns 226 models + live BTC price on /health
✅ Grafana Intelligence Report dashboard renders HTML reports with 9 sections
✅ Correction rules applied — WhatsMiner cooling types corrected at startup

**Total fixes deployed:** 21 HIGH priority + Intelligence Report (v1.0 → v2.0 → v2.1)
**Documentation:** REPAIR_LOG.md (complete history), INTELLIGENCE_REPORT_API.md (API docs)
**Last updated (Appendix A):** April 16 2026
**Files modified (Appendix A):** 25+ production files
