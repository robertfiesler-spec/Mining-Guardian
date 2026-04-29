# Runbook — Sandbox Test of `setup.sh` on a Fresh macOS User Account / VM

**Bucket 6e of the 2026-04-29 top-to-bottom scope plan.**

**Created:** Wednesday 2026-04-29
**Target:** A clean macOS 14+ environment — either a brand-new local user account on Robert's iMac or a UTM/VirtualBuddy VM with a fresh macOS install
**Operator:** Robert (local Mac)
**Time budget:** 75–120 minutes (one full pass + recovery from any failures)
**Blocked by:** PRs #74 / #75 / #76 / #77 merged to `main` (the artifacts under test)
**Blocks:** Bucket 6f (`DEPLOYMENT_CHECKLIST.md` update), final installer rebuild (Bucket 6 close-out), customer ship of Mac Mini #2

---

## Why this is a runbook, not a CI job

`scripts/setup.sh` (PR #75) and `scripts/restore_from_snapshot.sh` (PR #76) install Homebrew, Postgres, Grafana, Ollama, Tailscale, write LaunchDaemons, and ask for `sudo`. They are designed to run **on a real Mac with a real keychain and real LAN access to the miners**. None of that is reproducible in a CI runner or in the cloud sandbox the agent runs in.

The only correct way to verify the four installer PRs end-to-end is for the operator to execute setup.sh on a clean macOS environment, observe every phase pass, and verify the post-install state. This runbook is that procedure.

---

## What the four installer PRs claim to do (the contract under test)

| PR | Branch | Claim |
|---|---|---|
| #74 | `feat/bucket-6a-launchd-plists-2026-04-29` | 5 missing LaunchDaemon plists + 8 launcher wrappers + README under `installer/macos-pkg/resources/launchd/` |
| #75 | `feat/bucket-6b-setup-sh-rewrite-2026-04-29` | `scripts/setup.sh` v2 (883 lines, 15 phases) replaces the 178-line stub on `main` |
| #76 | `feat/bucket-6c-restore-from-snapshot-2026-04-29` | `scripts/restore_from_snapshot.sh` (572 lines, 8 phases) — companion for VPS→Mac migration |
| #77 | `feat/bucket-6d-grafana-provisioning-bundle-2026-04-29` | `installer/macos-pkg/resources/grafana/` bundle + `scripts/install_grafana_provisioning.sh` helper |

This runbook tests all four together, plus the existing branding (welcome.html / conclusion.html) and the previously-built `intelligence-catalog/seed-data/*.sql` deploy chain (Bucket 3.2).

---

## Pre-flight checks (do all five; ~5 minutes)

### A. Confirm all four PRs merged to `main`

```bash
cd ~/Documents/GitHub/Mining-Guardian
git fetch origin --quiet
git log --oneline origin/main | head -10
# expect commits from PRs #74, #75, #76, #77 in the recent history

git ls-tree origin/main scripts/setup.sh                          # should be 100755 ~30 KB
git ls-tree origin/main scripts/restore_from_snapshot.sh          # should be 100755 ~22 KB
git ls-tree origin/main scripts/install_grafana_provisioning.sh   # should be 100755 ~10 KB
ls origin/main installer/macos-pkg/resources/launchd/*.plist      # 9 plists total
ls origin/main installer/macos-pkg/resources/grafana/             # README.md + provisioning/ + dashboards/
```

If any are missing, **stop**. Bucket 6e is blocked until those PRs land.

### B. Pick a clean test environment

**Option 1 — Fresh local user account (faster, no VM software):**

1. System Settings → Users & Groups → Add User... → Standard user.
2. Name it `mg-sandbox`, password `MGSandbox2026!` (or whatever; doesn't matter, account is throwaway).
3. Log out, log in as `mg-sandbox`.

**Option 2 — UTM VM (cleaner; full kernel isolation):**

1. UTM (or VirtualBuddy) → New → macOS Sonoma 14.5+ → 8 GB RAM, 60 GB disk.
2. Install macOS, complete the setup wizard with username `mg-sandbox`, no Apple ID, no FileVault.
3. Boot in.

**Option 3 — A spare Mac Mini that has not yet been provisioned.**

> **Recommend Option 1 unless you suspect side-effects from the existing Homebrew/Postgres on Robert's iMac.** Option 1 catches 95% of regressions and is 10× faster to set up. Reserve Option 2 / 3 for the final pre-ship rehearsal.

### C. Network requirements

- The test machine must be on the **same LAN as the miners** (or any LAN — Phase 1 of `setup.sh` only verifies you have a routable network, not that miners are present; the smoke-test phase will skip cleanly if no miners respond).
- For a fully-faithful test: connect to the BiXBiT lab LAN where the 58 S19j Pro miners live.
- Outbound HTTPS to `github.com`, `homebrew.bintray.com`, `formulae.brew.sh`, `objects.githubusercontent.com`, `registry.npmjs.org`, `pypi.org`, `ollama.com`. No corporate proxy.

### D. Hardware / OS minimums (re-verified by `setup.sh` Phase 1)

- macOS 14 (Sonoma) or newer
- arm64 (Apple Silicon) — Phase 1 will warn but not abort on Intel; Mac Mini production target is Apple Silicon
- 16 GB RAM
- 50 GB free on root volume (Postgres + Ollama models = ~10 GB; logs grow to 5+ GB over time)

### E. Operator artifacts to have ready (paste-along during Phase 2)

- Site name (e.g. `bixbit-lab-test`)
- AMS username + password (the miner-management API)
- Slack bot token + signing secret + channel ID (use the staging channel for sandbox tests)
- Scan interval (default `300` s = 5 min)
- Install mode → `dry-run` for the **first** sandbox pass; flip to `live` only after dry-run passes

---

## Phase-by-phase test procedure

The headers below mirror `scripts/setup.sh` v2 phase numbers. For each phase, mark **PASS** / **FAIL** / **SKIP** and copy any error output into a scratch file. We do all 15 phases first, **then** debug failures together — don't pause halfway through; many phase outputs are needed to diagnose earlier ones.

### Phase 1 — Pre-flight

```bash
# Clone the repo into the sandbox account
cd ~
git clone https://github.com/robertfiesler-spec/Mining-Guardian.git
cd Mining-Guardian

# First, dry-run Phase 1 to see what setup.sh will check
zsh scripts/setup.sh --dry-run-install --help | head -40
zsh scripts/setup.sh --dry-run-install   # should bail at Phase 2 prompts in dry-run mode
```

**PASS criteria:** `setup.sh` prints the banner with version + 15 phase names, Phase 1 reports macOS version / arch / RAM / free disk / LAN OK, then either prompts for Phase 2 customer info (live mode) or exits cleanly (dry-run).

### Phase 2 — Customer info

Live mode only. Type the operator artifacts from pre-flight section E. **Verify the password prompt uses `read -s`** (no echo to terminal) for AMS, Postgres, and Slack secrets — this is the S-14 mitigation.

```bash
zsh scripts/setup.sh
# When prompted, paste the values from section E above
```

**PASS criteria:** all secrets read via `read -s`. No password ever appears in the terminal scrollback. `.env` is written to repo root with `chmod 600`.

### Phase 3 — Brew + deps

`setup.sh` installs Homebrew if missing, then `postgresql@16 python@3.12 git ollama grafana tailscale`.

**Watch for:** "Error: Cannot install in Homebrew on ARM processor in Intel default prefix" — means you booted under Rosetta. Open Terminal natively (right-click → Get Info → uncheck "Open using Rosetta") and rerun.

**PASS criteria:**
```bash
brew list --formula | grep -E '^(postgresql@16|python@3.12|git|ollama|grafana|tailscale)$'
# all six should appear
```

### Phase 4 — Postgres

Creates `guardian_app` role + 3 DBs (`mining_guardian`, `mining_guardian_test`, `mining_guardian_catalog`). Applies operational schema from `migrations/001_initial_schema.sql` and (after Bucket 5.7 lands) `002_layer2_*.sql` + `003_c5_notify_triggers.sql` + `004_staging_*.sql`. Applies catalog schema from `intelligence-catalog/seed-data/deploy_schema.sql`.

**PASS criteria:**
```bash
psql -U guardian_app -d mining_guardian -c '\dt' | wc -l                # ≥ 24 tables
psql -U guardian_app -d mining_guardian_catalog -c "\dt hardware.*" | grep miner_models   # 1 row
psql -U guardian_app -d mining_guardian_catalog -c '\dn' | grep -E 'hardware|firmware|ops|knowledge'   # 4 schemas
```

### Phase 5 — Catalog seed

Runs `intelligence-catalog/seed-data/seed_miner_models.sql` — the 313-row C4 dataset.

**PASS criteria:**
```bash
psql -U guardian_app -d mining_guardian_catalog -c "SELECT COUNT(*) FROM hardware.miner_models;"
# expect 313 (or whatever the latest count is — match it to seed_miner_models.sql line count)
```

### Phase 6 — Repo + venv

Creates `~/Mining-Guardian/.venv`, `pip install -r requirements.txt`. The 49-package install takes 2–5 minutes.

**PASS criteria:**
```bash
~/Mining-Guardian/.venv/bin/python -c "import psycopg2, slack_bolt, redis, flask, requests, openai; print('OK')"
~/Mining-Guardian/.venv/bin/pip list | wc -l    # ≥ 50 (49 + pip + setuptools)
```

### Phase 7 — Secrets

Generates new `MG_DB_PASSWORD` (32-char) and `CATALOG_API_KEY` via `openssl rand -hex 32`, writes them to `.env`, `chmod 600`.

**PASS criteria:**
```bash
ls -la ~/Mining-Guardian/.env                       # mode 600
grep -c '^MG_DB_PASSWORD=' ~/Mining-Guardian/.env   # 1
grep -c '^CATALOG_API_KEY=' ~/Mining-Guardian/.env  # 1
# Both values are 32+ random hex chars — never the default sentinel
```

### Phase 8 — Ollama

Pulls `qwen2.5:14b-instruct-q4_K_M` (~9 GB), runs a smoke prompt.

**PASS criteria:**
```bash
ollama list | grep qwen2.5:14b-instruct-q4_K_M
ollama run qwen2.5:14b-instruct-q4_K_M 'Say "OK"' --hidethinking 2>/dev/null   # should print OK
```

### Phase 9 — LaunchDaemons

Renders 9 plists from `installer/macos-pkg/resources/launchd/` with `$HOME` / `$USER` substitution → `~/Library/LaunchAgents/com.miningguardian.*.plist`. `launchctl load` each.

**PASS criteria:**
```bash
ls ~/Library/LaunchAgents/com.miningguardian.*.plist | wc -l   # 9
launchctl list | grep com.miningguardian | wc -l               # 9
launchctl list | grep com.miningguardian | awk '{print $1}'    # PID per service (no '-' = unloaded)
```

If any plist fails to load, run `launchctl error <exit_code>` on the printed exit code and grep `~/Library/Logs/MiningGuardian/launchd_*.log`.

### Phase 10 — Cron

Installs the 9 cron jobs (parallel to LaunchDaemons during the v1→v2 transition; one of the two will be retired in a future bucket — TBD which). Prompts for Full Disk Access for `/usr/sbin/cron`.

**PASS criteria:**
```bash
crontab -l | grep -c MiningGuardian   # 9
```

> **Sandbox note:** if you skipped Full Disk Access prompt, cron will fire but jobs that read `~/Documents` will silently fail. That's expected for the sandbox. For a Mac Mini ship, FDA must be granted.

### Phase 11 — Grafana

`brew services start grafana`. Calls `scripts/install_grafana_provisioning.sh --auto` (after the Phase-11-wires-helper follow-up PR lands; until then, the Phase 11 placeholder yaml is what gets installed — and the helper script can be invoked manually in this sandbox to test PR #77 separately).

```bash
# Optional manual test of PR #77 in isolation
zsh scripts/install_grafana_provisioning.sh --auto --dry-run
zsh scripts/install_grafana_provisioning.sh --auto
brew services restart grafana
```

**PASS criteria:**
```bash
ls /opt/homebrew/var/lib/grafana/provisioning/datasources/mining_guardian.yml
ls /opt/homebrew/var/lib/grafana/provisioning/dashboards/mining_guardian.yml
ls /usr/local/MiningGuardian/grafana/dashboards/*.json | wc -l   # 3
open http://localhost:3000   # admin / admin (change on first login)
# Verify in browser:
#   - 2 datasources visible (Mining Guardian (operational), Mining Guardian Catalog)
#   - "Mining Guardian" folder contains 3 dashboards
#   - All 3 dashboards render their header text panel with navy + BTC orange
#   - Dashboards either show data (if Postgres has scans) or "No data" (clean state)
```

### Phase 12 — Tailscale (optional)

Skipped unless `--tailscale` flag was passed. If invoked, prompts the operator to authenticate via browser.

### Phase 13 — Smoke test

`setup.sh` calls each of the 8 Mining Guardian services with `--dry-run` and checks the exit code. Then runs `core/scanner.py --once` to do a real scan (or "no miners reachable" cleanly if you skipped Section C lab LAN).

**PASS criteria:** all 8 services return exit 0 in dry-run; scanner runs without crashing.

### Phase 14 — Post-install

Posts `Mining Guardian v1.0 setup complete on <hostname>` to the configured Slack channel. Prints a cheat-sheet of common commands. Verifies `.env` still has `dry_run=true`.

**PASS criteria:** Slack message arrives in the staging channel within 30 s.

### Phase 15 — Optional restore (skipped in fresh-install pass)

Only invoked when `--restore-from-snapshot=<tarball>` is passed. **Test this separately**, see "Restore-from-snapshot pass" section below.

---

## Restore-from-snapshot pass (separate run after fresh-install pass)

This tests `scripts/restore_from_snapshot.sh` (PR #76) end-to-end.

### A. Build a snapshot tarball on the VPS

```bash
ssh root@srv1549463
cd /tmp
TS=$(date +%Y%m%d_%H%M%S)
DEST=/tmp/mg_snapshot_srv1549463_${TS}.tar.gz
mkdir -p /tmp/mg_snap_${TS}/{env,postgres,grafana,logs}
cp /root/Mining-Guardian/.env          /tmp/mg_snap_${TS}/env/.env
cp /root/Mining-Guardian/config.json   /tmp/mg_snap_${TS}/env/config.json
sudo -u postgres pg_dump --format=custom mining_guardian > /tmp/mg_snap_${TS}/postgres/mining_guardian.dump
sudo -u postgres pg_dump --format=custom mining_guardian_catalog > /tmp/mg_snap_${TS}/postgres/mining_guardian_catalog.dump
cp /var/lib/grafana/grafana.db /tmp/mg_snap_${TS}/grafana/grafana.db
rsync -a --max-age=7 /root/Mining-Guardian/logs/ /tmp/mg_snap_${TS}/logs/
crontab -l > /tmp/mg_snap_${TS}/crontab.txt
cat > /tmp/mg_snap_${TS}/manifest.txt <<EOF
mining_guardian_snapshot_version: 1
created_at: $(date -Iseconds)
host: $(hostname -f)
postgres_version: $(sudo -u postgres psql -tAc 'SELECT version();')
EOF
tar -czf $DEST -C /tmp/mg_snap_${TS} .
ls -la $DEST    # ~50–500 MB depending on logs volume
```

(These commands are also pasted at the bottom of `scripts/restore_from_snapshot.sh` itself.)

### B. Copy tarball to the Mac

```bash
# From the Mac sandbox account
scp root@100.110.87.1:/tmp/mg_snapshot_srv1549463_*.tar.gz ~/Downloads/
```

### C. First, dry-run the restore

```bash
cd ~/Mining-Guardian
zsh scripts/restore_from_snapshot.sh --tarball=~/Downloads/mg_snapshot_*.tar.gz --dry-run
```

**PASS criteria:** prints the 8-phase plan, manifest details, .env merge plan (showing which keys would be backfilled), Postgres pg_restore plan, no actual writes.

### D. Real restore

```bash
zsh scripts/restore_from_snapshot.sh --tarball=~/Downloads/mg_snapshot_*.tar.gz
```

**PASS criteria:**
```bash
psql -U guardian_app -d mining_guardian -c "SELECT COUNT(*) FROM scans;"      # > 0 (matches VPS)
psql -U guardian_app -d mining_guardian -c "SELECT COUNT(*) FROM miner_readings;"
psql -U guardian_app -d mining_guardian_catalog -c "SELECT COUNT(*) FROM hardware.miner_models;"   # 313
ls ~/Mining-Guardian/.env.bak.*                               # original .env backed up
ls /opt/homebrew/var/lib/grafana/grafana.db.bak.*             # original grafana.db backed up
launchctl list | grep com.miningguardian | wc -l              # 9 (services kickstarted)
```

---

## Failure-mode catalog (what to do when a phase fails)

| Phase | Common failure | Fix |
|---|---|---|
| 1 | "macOS version too old" | Upgrade to Sonoma 14.5+. Setup.sh refuses to proceed. |
| 1 | LAN check fails | Confirm `route -n get default` returns a gateway. Wired Ethernet for the lab. |
| 3 | Homebrew install hangs | Cancel with Ctrl-C, rerun. The brew install script is itself idempotent. |
| 3 | "Cannot install in Intel default prefix" | Reopen Terminal natively (uncheck Rosetta in Get Info). |
| 4 | "role guardian_app already exists" | Phase 4 is idempotent, this is a warning not an error. |
| 4 | "could not connect to Postgres" | `brew services restart postgresql@16 && sleep 3` and rerun Phase 4. |
| 5 | Seed SQL constraint violation | Likely `hardware.manufacturers` not seeded — re-run Phase 4. |
| 6 | `pip install` SSL error | Corporate proxy. Use a different network or set `PIP_INDEX_URL`. |
| 7 | `.env` has default sentinel `CHANGE_ME_DB_PASSWORD` | S-1 mitigation triggered — rerun Phase 7 with `--force`. |
| 8 | Ollama pull stuck | `ollama serve` in another terminal, then retry. ~9 GB download — slow networks take 30+ min. |
| 9 | `launchctl load` returns exit 5 | plist syntax error. `plutil -lint ~/Library/LaunchAgents/com.miningguardian.<name>.plist`. |
| 9 | service `loaded` but PID is `-` | First-launch crash. Check `~/Library/Logs/MiningGuardian/<service>_stderr.log`. |
| 11 | Grafana can't reach Postgres | Datasource yaml password expansion failed. Confirm `${GUARDIAN_PG_PASSWORD}` env var is set in the launchd that runs Grafana — `brew services` runs as the user, so the user's `.zshrc` must export it (or use `secureJsonData.password` with the literal — but never check that in). |
| 11 | "No data" on all dashboards but Postgres has rows | Provisioning loaded the wrong DB. Check yaml `database:` field matches what `psql -l` shows. |
| 13 | Smoke-test scan exits 1 with "no miners" | Expected if not on lab LAN. Not a fail of `setup.sh`. |
| restore | pg_restore "role guardian_app does not exist" | Run setup.sh Phase 4 first; restore_from_snapshot.sh assumes the role exists. |
| restore | grafana.db SQLite is locked | `brew services stop grafana`, restore, `brew services start grafana`. |

---

## What "PASS" means for Bucket 6e overall

All 15 phases of `setup.sh` complete on the **fresh-install pass** with no manual intervention beyond Phase 2 prompts. All 8 phases of `restore_from_snapshot.sh` complete on the **restore pass** without manual intervention. Both passes leave the Mac in a state where:

1. `launchctl list | grep com.miningguardian | wc -l` → `9`
2. `crontab -l | grep -c MiningGuardian` → `9`
3. `psql -U guardian_app -d mining_guardian -c '\dt' | wc -l` → ≥ 24
4. `psql -U guardian_app -d mining_guardian_catalog -c "SELECT COUNT(*) FROM hardware.miner_models;"` → 313
5. `ls /usr/local/MiningGuardian/grafana/dashboards/*.json | wc -l` → 3
6. `open http://localhost:3000` shows 2 datasources and 3 dashboards in a "Mining Guardian" folder
7. `~/Mining-Guardian/.env` mode is `600` and contains a non-default `MG_DB_PASSWORD` and `CATALOG_API_KEY`
8. A Slack ping arrived in the staging channel
9. `launchctl error <exit>` for every service shows `0` (no crash loops)

If any of those nine state-checks fail, file a follow-up issue tagged `bucket-6e` with the failing phase + log excerpt + PR link, and **do not** mark Bucket 6 closed.

---

## Bucket 6e exit criteria → Bucket 6f (DEPLOYMENT_CHECKLIST)

Once both passes succeed, copy the operator-friendly summary of "what setup.sh actually did on this Mac" into `docs/DEPLOYMENT_CHECKLIST.md`. That's Bucket 6f. The checklist is **descriptive of observed reality**, not aspirational — fill it in from the actual sandbox run, not from this runbook.

---

## Sandbox cleanup (after the test passes)

**Option 1 (fresh user account):** System Settings → Users & Groups → delete `mg-sandbox` user, choose "Delete the home folder" → reboot. Reclaims ~25 GB.

**Option 2 (UTM VM):** Delete VM in UTM. Reclaims 60 GB.

**Option 3 (real Mac Mini for the rehearsal):** before factory-resetting, capture a `mg_snapshot_*.tar.gz` from this Mac so the next operator can compare deltas — keep the file in `~/Documents/MG_Sandbox_Snapshots/` for ≥30 days.

---

## TODO sync (this commit / next-PR pattern)

This runbook lands as a doc-only PR (Bucket 6e). The PR flips §7.3 row 7e in `docs/MG_UNIFIED_TODO_LIST.md` from open to "📘 Runbook landed — sandbox exec pending" — same pattern as PR #68 (Bucket 3.2) and PR #73 (Bucket 5.7). The row flips to `✅ DONE` only when Robert reports back that both passes succeeded.

---

## Related PRs / runbooks

- PR #74 — Bucket 6a: 5 plists + 8 launcher wrappers
- PR #75 — Bucket 6b: `scripts/setup.sh` v2
- PR #76 — Bucket 6c: `scripts/restore_from_snapshot.sh`
- PR #77 — Bucket 6d: Grafana provisioning bundle
- PR #68 — Bucket 3.2: `hardware.*` schema deploy runbook (powers Phase 4–5 of this test)
- PR #73 — Bucket 5.7 / B-7: live migrations runbook (must land before Phase 4 produces a fully-correct schema)
