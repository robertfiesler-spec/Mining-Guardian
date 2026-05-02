# Mining Guardian — Install-Day Unbox Runbook

**Target date:** 2026-04-30 (Mac Mini install)
**Built from:** `v1.0.0-install-ready` (commit `b6b7d72`)
**Headless companion:** `docs/RUNBOOK_HEADLESS_ADDENDUM_2026-04-30.md` (read first if Mini will run without peripherals)
**Authority:** This file. Print it, follow it top to bottom.

---

## 0. Before you touch the Mac Mini — read this

This runbook walks you through the unboxing and install of Mining Guardian on the new Mac Mini in a single sitting. It assumes:

- A fresh Mac Mini (M-series, macOS 14 or 15) out of the box.
- The signed `MiningGuardian-1.0.0-0f849bd217cc.pkg` (sha256 `1e65fe7827ffba2c8cd4daa0c2a42218bb156798521278fd0e567b0cef53a646`) has been Apple-notarized and stapled, and you have it on a USB stick, AirDrop, or a download URL.
- You have these credentials in front of you (do not store them on the Mac):
  - **MG_DB_PASSWORD:** `tX-fhG#iJdm{V?>uuZ35G-Y)O5<UeN=5`
  - **Grafana admin password:** `002300rfNEW`
  - **Apple Dev Team ID:** `ARJZ5FYU94`
  - Slack tokens / webhook URLs from your password manager
- The miner fleet is reachable from the LAN the Mac Mini will sit on.

If anything in those bullets is missing, **stop and resolve it before booting the Mac Mini**.

---

## 1. Out of the box (≈10 min)

1. Unbox the Mac Mini, plug in power and Ethernet.
2. Hold the power button until you see the setup assistant.
3. macOS Setup Assistant:
   - Country: United States
   - Wi-Fi: skip (Ethernet only — this is a server)
   - Apple ID: **Skip / Set Up Later** (this is a service machine, no iCloud)
   - Account name: `mg` ; full name: `Mining Guardian` ; password: from your password manager
   - Touch ID: skip
   - Analytics: **off**
   - Screen Time: skip
   - Siri: skip
4. Once at the desktop, set:
   - **System Settings → Energy:** "Prevent automatic sleeping when display is off" → ON
   - **System Settings → Energy:** "Wake for network access" → ON
   - **System Settings → Energy:** "Start up automatically after a power failure" → ON
   - **System Settings → Sharing:** Computer Name → `mg-mac-mini` ; SSH Remote Login → ON (admin user only)
   - **System Settings → Software Update:** **Off automatic updates.** We pin macOS for the install; updates happen on a schedule, not surprise reboots.
5. Open Terminal. Run:
   ```bash
   sw_vers
   uname -m
   ```
   Confirm Darwin version + arm64. If `x86_64`, stop — this runbook assumes Apple Silicon.

---

## 2. Install Xcode Command Line Tools + Homebrew (≈15 min)

```bash
xcode-select --install
# Click "Install" in the popup. Wait for completion.

# Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
# Follow the post-install instructions to add brew to your PATH:
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
brew --version
```

If `brew --version` does not print a version, stop and re-run the install line.

---

## 3. Drop in the Mining Guardian repo (≈5 min)

```bash
# Clone the repo at the install-ready tag
mkdir -p ~/code && cd ~/code
git clone https://github.com/robertfiesler-spec/Mining-Guardian.git
cd Mining-Guardian
git fetch --tags
git checkout v1.0.0-install-ready
git rev-parse HEAD
# Should print: b6b7d7233c4ee2925c06877028af8057acda049d
```

If the SHA does not match, stop and recheck — you are not on the install-ready tag.

---

## 4. Run the 15-phase installer (`scripts/setup.sh`) (≈45 min)

The installer is the canonical path. Do **not** click the .pkg — the .pkg is for end-user laptops, not the operations Mac Mini. The .pkg invokes a subset of these same scripts plus Apple-style postinstall plumbing.

```bash
cd ~/code/Mining-Guardian
chmod +x scripts/setup.sh
# B-10 FIX (v1.0.2): scripts/setup.sh uses zsh-only syntax (`read VAR?prompt`,
# `read -s VAR?prompt`). Running it under bash (`bash scripts/setup.sh`) on
# Tahoe makes Phase 2 explode at the first read with `bash: -s: invalid
# option`. Always invoke with `zsh`, never `bash`. macOS 14+ already ships
# zsh as /bin/zsh; nothing extra to install.
#
# Optional dry-run first to see all 15 phases (no sudo, no system writes):
DRY_RUN=1 zsh scripts/setup.sh

# Real run (sudo required for Phase 8 Colima service + Phase 11 launchd):
sudo -E zsh scripts/setup.sh 2>&1 | tee ~/mg-install-$(date +%Y%m%d-%H%M).log
```

The 15 phases (rough timing on M-series Mac Mini):

| Phase | What it does | Time |
|---|---|---|
| 01 | Pre-flight: macOS version, arm64, free disk, Homebrew present | 1m |
| 02 | Brew installs: postgresql@16, jq, curl, openssl, python@3.12 | 5m |
| 03 | Python venv + pip install -r requirements.txt | 5m |
| 04 | Postgres setup: 3 DBs (operational, test, catalog) + migrations 001/003/004×2/005 | 5m |
| 05 | Catalog seed: 320 Bitcoin SHA-256 model rows | 2m |
| 06 | Colima + Docker (for Grafana) | 8m |
| 07 | Set MG_DB_PASSWORD via `ALTER ROLE guardian_app WITH PASSWORD ...` | 1m |
| 08 | Ollama install + qwen2.5:7b pull | 10m (download) |
| 09 | Grafana provisioning bundle deployment | 3m |
| 10 | launchd plists installed to `/Library/LaunchDaemons/` | 1m |
| 11 | Slack token wiring (you'll be prompted) | 2m |
| 12 | Initial scan dry-run | 1m |
| 13 | Daemon `launchctl load` + smoke test | 2m |
| 14 | Health check: every API returns 200 | 1m |
| 15 | Summary report | <1m |

**Watch for:**
- Phase 04 should print `Applied 5 migration file(s).` (001, 003, 004_drop_dead_stubs, 004_system_settings, 005_system_schedules)
- Phase 04 should also print `(note: no 002_*.sql in repo — expected for 002 pending B-7)`. That is **correct** — see §7 below.
- Phase 11 will pause and ask for Slack tokens. Paste, hit enter.

If any phase fails, **stop and read the log**. The installer is idempotent — fixing the cause and re-running picks up where it left off.

---

## 5. Post-install smoke tests (≈10 min)

```bash
# 5.1 Daemons all loaded?
sudo launchctl list | grep miningguardian
# Expect 9 entries: alerts, approval-api, dashboard-api, intelligence-report,
# overnight-automation, scanner, slack-commands, slack-listener, feedback-loop

# 5.2 Postgres reachable?
psql -U guardian_app -d mining_guardian -c "\dt"
# Expect to see chip_readings GONE (Bucket 7.2 dropped it) and
# log_collection_failures GONE; field_log_* tables present.

# 5.3 Catalog populated?
psql -U guardian_app -d mining_guardian_catalog -c "SELECT COUNT(*) FROM miner_models;"
# Expect: 320

# 5.4 Dashboard API up?
curl -fsS http://127.0.0.1:8080/api/health
# Expect: {"ok": true, ...}

# 5.5 Grafana up?
open http://127.0.0.1:3000
# Login: admin / 002300rfNEW
# Mining Guardian dashboard should be in the home folder.

# 5.6 Run the test suite end-to-end on the live Mac Mini
cd ~/code/Mining-Guardian
source .venv/bin/activate
pytest tests/ mg_import_tool/tests/ intelligence-catalog/watchers/tests/ -q
# Expect: 392+ passed, 0 failed (45 DB-required skips become passes here)
```

If any of 5.1–5.6 fails, see §8 troubleshooting.

---

## 6. First scan (≈5 min)

```bash
# Trigger one scan manually to confirm the AMS → DB → Slack path is wired.
cd ~/code/Mining-Guardian
source .venv/bin/activate
python -m core.mining_guardian --scan-now --dry-run
# Watch for AMSClient login → fleet pull → DB write → Slack post (alerts channel).
# Dry-run mode does not remediate; it just exercises the read path.
```

If the dry-run scan succeeds and the alerts channel sees a "scan complete" post, you are live. The scanner daemon will then pick up the cadence from `system_schedules` (migration 005) and you can close the laptop.

---

## 7. Carry-over items for after the install

These are intentionally deferred — do not try to resolve any of them on install day.

### 7.1 B-7: live migrations 002_layer2 + staging (VPS-side)

Migration `002_*.sql` is intentionally absent from the repo until it can be canonicalized off the live VPS. The runbook for this lives at `docs/RUNBOOK_BUCKET_5.7_COMMIT_LIVE_MIGRATIONS.md`. The Mac Mini install does not need 002 to come up — the operational DB starts fresh from 001 + 003/004/005 and re-syncs from the VPS via the catalog flow. Plan to resolve B-7 within the first week post-install while the VPS is still running.

### 7.2 Three retained stale branches

`feature/fast-cohort-analysis`, `feature/intelligence-catalog`, `pre-prod-audit-2026-04-25` were retained instead of deleted because they had unique commits never PR'd. Audit per `docs/STALE_BRANCHES_RETAINED_2026-04-29.md` and delete what is superseded.

### 7.3 253 cosmetic pyflakes warnings

`docs/PYFLAKES_RESIDUAL_2026-04-29.txt` lists every unused import, unused local, and missing-placeholder f-string. These do **not** affect runtime — the 6 actual NameError bugs were fixed in PR #92. Plan a cleanup PR per directory (ai/, api/, core/, etc.) post-install.

### 7.4 Carry-forward docstring drift

`api/intelligence_report_api.py:528` docstring still says "LIVE operational data" — wording-only, non-blocking. Schedule with the SQLite-retirement bucket.

### 7.5 SQLite ATTACH comments

`core/database.py:578,782` — same SQLite-retirement bucket.

---

## 8. Troubleshooting (only read if §5 or §6 failed)

### 8.1 "psql: command not found" in phase 04

Homebrew did not link postgresql@16. Run `brew link --force postgresql@16` then re-run phase 04 of setup.sh.

### 8.2 "guardian_app" role already exists with no password

Phase 07 will reset it. If 07 is failing, run by hand:
```bash
psql -U $(whoami) -d postgres -c "ALTER ROLE guardian_app WITH PASSWORD 'tX-fhG#iJdm{V?>uuZ35G-Y)O5<UeN=5';"
```

### 8.3 Dashboard API returns 502 / refuses connections

`launchctl print system/com.miningguardian.dashboard-api` will show whether the daemon is running and what its last exit code was. Check the log file at `/usr/local/var/log/mining-guardian/dashboard-api.log`. Most common cause: Postgres not yet running (race with brew services). Wait 30s, `launchctl kickstart -k system/com.miningguardian.dashboard-api`.

### 8.4 Slack notifications silent

`grep SLACK_BOT_TOKEN ~/.config/mining-guardian/env` — if empty, phase 11 was skipped. Edit the file with your token, then `launchctl kickstart -k` each of the slack daemons.

### 8.5 Migration 002 missing warning in phase 04

**This is expected.** Phase 04 prints `(note: no 002_*.sql in repo — expected for 002 pending B-7)`. This is the dual-004/005 fix from PR #95 doing its job. Continue.

### 8.6 Anything else

Read the log at `~/mg-install-YYYYMMDD-HHMM.log`, find the failing phase, and re-run setup.sh. Setup is idempotent. If you cannot resolve, capture the log and the relevant snippet and reach out before forcing past it. The "rather be late and perfect than early and wrong" rule applies double on install day.

---

## 9. Sign-off

When §5 and §6 all pass:

1. Tag a release on the main repo:
   ```bash
   cd ~/code/Mining-Guardian
   git tag -a v1.0.0-installed-mac-mini-$(date +%Y%m%d) -m "Mac Mini live install $(date +%Y-%m-%d)"
   git push origin v1.0.0-installed-mac-mini-$(date +%Y%m%d)
   ```
2. Flip the `MG_UNIFIED_TODO_LIST.md` "Mac Mini install" row from 🔴 → ✅ with today's date and the tag.
3. Close the laptop. Mac Mini takes over. Watch alerts for 24h.

---

## Appendix A — Repo state at v1.0.0-install-ready

- **Tag:** `v1.0.0-install-ready` → commit `b6b7d72`
- **Main branch:** `main`
- **Open PRs:** 0
- **Test suite:** 394 passed / 65 skipped (DB-required) / 0 failed
- **Static analysis:** 0 NameError bugs; 0 hardcoded secrets; 253 cosmetic pyflakes warnings (deferred)
- **B-6 typo lint:** clean (62 allow-listed hits)
- **Migrations applied by setup.sh:** 001, 003, 004_drop_dead_stubs, 004_system_settings, 005_system_schedules
- **launchd plists:** all 9 valid (Label + ProgramArguments present)
- **Install-day-eve PRs in this tag:** #92 (B-8 imports), #93 (branch triage), #94 (test drift), #95 (migration loop), #96 (unbox runbook), #97 (preflight + handoff)

## Appendix B — File index

- `scripts/setup.sh` — 15-phase installer
- `migrations/` — 001/003/004×2/005 SQL
- `installer/macos-pkg/` — .pkg builder + pre/postinstall + launchd plists
- `docs/LATENT_BUGS.md` — full bug history (B-1..B-8)
- `docs/MG_UNIFIED_TODO_LIST.md` — master todo list, all rows up-to-date as of 2026-04-29
- `docs/RUNBOOK_BUCKET_5.7_COMMIT_LIVE_MIGRATIONS.md` — VPS-side B-7 procedure for after install
- `docs/STALE_BRANCHES_RETAINED_2026-04-29.md` — 3 branches to audit post-install
- `docs/PYFLAKES_RESIDUAL_2026-04-29.txt` — 253 cosmetic warnings to chew through later

---

*Generated 2026-04-29 21:30 UTC by Computer (install-day prep cascade).*
