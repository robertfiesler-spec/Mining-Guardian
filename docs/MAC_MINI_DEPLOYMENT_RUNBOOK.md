# Mac Mini Deployment Runbook

> ## ⚠️ Status as of 2026-04-29 PM
>
> **Install date: 2026-04-30.** This runbook is canonical; only the date reference shifts (was 2026-04-27, briefly 2026-05-05, now locked at 2026-04-30).
>
> **DB approach:** The Mac Mini stands up its own operational Postgres DB from migrations 001–005 + the 320-row catalog seed. There is no live data copy from the VPS — the VPS is decommissioned for Mining Guardian (Bobby still uses it for his own facility). The optional `restore_from_snapshot.sh` path remains available for any operator who explicitly wants to import a historical operational-DB snapshot from the pre-Mac-Mini era.
>
> **Cloudflare:** NOT used. The locked decision is Mac Mini local-first, loopback-only services. All Cloudflare tunnel references in this runbook describe the pre-Mac-Mini VPS era (historical context); they do not describe the 2026-04-30 install. See `MG_UNIFIED_TODO_LIST.md` and `ROADMAP_TO_MAC_MINI_2026-05-05.md`.

**Target date:** 2026-04-30 (install date, locked)
**Purpose:** step-by-step procedure for deploying Mining Guardian on a local Mac Mini on the Fort Worth facility LAN (superseding the historical Hostinger VPS / srv1549463 era).
**Status:** runbook canonical, install scheduled 2026-04-30.

---

## Why we're moving

The Hostinger VPS (187.124.247.182 / srv1549463, historical) was always staging. Production on a Mac Mini means:

- Local LAN access to AMS at 192.168.188.x, miners at 192.168.188.x / 192.168.189.x, HVAC controllers at 192.168.188.235 and 192.168.189.235, the Amshub Pi at 192.168.188.30 — no Tailscale dependency for anything on-site.
- No public ingress. The three Cloudflare tunnels that existed on the historical VPS (dashboard.fieslerfamily.com, slack.fieslerfamily.com, grafana.fieslerfamily.com) are not used in the Mac Mini architecture — services bind to loopback only.
- Local LLM (Qwen on ROBS-PC) stays primary, no Claude API in the hot path. Claude API still used for weekly training and cohort refinement only.
- Target: 1 Mac Mini per container, scales to 120–240 miners per instance.

---

## Pre-flight (do before Mac Mini arrives)

These are independent of hardware and can be done any time before Monday.

### 1. Fresh-install dry run (CRITICAL)

Spin up a scratch Postgres DB and verify all 8 services come up cleanly against an empty schema. This catches any missing CREATE TABLE IF NOT EXISTS or migration gaps **before** they become an install-day fire.

> **Note:** The historical dry-run steps below were written for the pre-Mac-Mini VPS era (root@srv1549463 / 187.124.247.182). On the Mac Mini install (2026-04-30), run these same commands locally on the Mac Mini against its own Postgres instance — substitute `localhost` for `187.124.247.182` and use the Mac Mini user context.

    # Create scratch DB
    sudo -u postgres psql <<SQL
    CREATE DATABASE mining_guardian_dryrun OWNER guardian_app;
    GRANT ALL PRIVILEGES ON DATABASE mining_guardian_dryrun TO guardian_app;
    SQL

    # Apply canonical schema
    cd /root/Mining-Guardian
    set -a; source .env; set +a
    PGPASSWORD="\$GUARDIAN_PG_PASSWORD" psql -h localhost -U guardian_app \\
        -d mining_guardian_dryrun -f migrations/001_initial_schema.sql

    # Expect: ~18 CREATE TABLE statements, ~23 CREATE INDEX statements, no errors.

    # Point test .env at dryrun DB
    cp .env .env.backup
    sed -i 's/GUARDIAN_PG_DBNAME=mining_guardian/GUARDIAN_PG_DBNAME=mining_guardian_dryrun/' .env

    # Restart services ONE AT A TIME; check logs
    for svc in mining-guardian dashboard-api approval-api slack-listener \\
               slack-commands overnight-automation mining-guardian-alerts; do
        echo === Testing \$svc against dryrun DB ===
        systemctl restart "\$svc"
        sleep 10
        systemctl is-active "\$svc" || echo FAILED: \$svc
        journalctl -u "\$svc" --since '15 seconds ago' | grep -iE 'error|traceback|does not exist' | head
    done

    # Restore real .env and revert all services
    mv .env.backup .env
    systemctl restart mining-guardian dashboard-api approval-api slack-listener \\
                      slack-commands overnight-automation mining-guardian-alerts

    # Drop the scratch DB
    sudo -u postgres psql -c 'DROP DATABASE mining_guardian_dryrun;'

**What to fix if dry run fails:**
- 'table does not exist' → missing CREATE TABLE in migrations/001_initial_schema.sql; add it
- 'column does not exist' → migration has an older schema than the code expects; reconcile against \\d <tablename> on live
- 'permission denied' → owner/grant issue on the DB, re-check OWNER guardian_app and GRANT ALL

### 2. Knowledge snapshot (optional — historical VPS snapshot path)

> **2026-04-29 PM update:** The Mac Mini install (2026-04-30) starts from migrations 001–005 + the 320-row catalog seed. No live data copy from the VPS is required or expected — the VPS is decommissioned for MG. The steps below are the `restore_from_snapshot.sh` optional path, preserved for any operator who explicitly wants to import a pre-Mac-Mini operational-DB snapshot.

To export the historical VPS state (optional):

    cd /root/Mining-Guardian
    set -a; source .env; set +a

    # Full Postgres dump
    PGPASSWORD="\$GUARDIAN_PG_PASSWORD" pg_dump -h localhost -U guardian_app \\
        mining_guardian > /tmp/mining_guardian_\$(date +%Y%m%d).sql
    gzip /tmp/mining_guardian_\$(date +%Y%m%d).sql

    # knowledge.json (accumulated fleet learning)
    cp knowledge.json /tmp/knowledge_\$(date +%Y%m%d).json

    # config.json (profile map, miner filters, thresholds)
    cp config.json /tmp/config_\$(date +%Y%m%d).json

    # .env (will edit paths/hosts for Mac Mini)
    cp .env /tmp/env_\$(date +%Y%m%d).txt

Transfer these files to a USB drive or Bobby's Mac before the install date if using the optional snapshot restore path.

### 3. Cloudflare tunnel shutdown (historical VPS — already superseded)

> **2026-04-29 PM:** The Cloudflare tunnel path is NOT taken in the Mac Mini architecture. The locked decision is loopback-only services. The commands below are historical record of the VPS-era tunnel teardown. No action needed for the 2026-04-30 install.

    # Historical VPS tunnel shutdown (decommissioned for MG — do NOT run for Mac Mini install):
    # systemctl stop cloudflared
    # systemctl disable cloudflared
    # Tunnels can also be deleted via Cloudflare dashboard afterward.

---

## Mac Mini install (Monday)

### Phase 1: base system (30 min)

1. Unbox, connect power, monitor, keyboard, ethernet to facility LAN.
2. Complete macOS setup wizard. Set hostname: mining-guardian-188 (or similar).
3. Install Homebrew
4. Install core deps:

       brew install python@3.12 postgresql@16 git
       brew services start postgresql@16

5. Clone repo with the PAT:

       mkdir -p ~/Documents/GitHub
       cd ~/Documents/GitHub
       git clone https://github.com/robertfiesler-spec/Mining-Guardian.git "Mining Gaurdian"
       # Note: Mac path keeps the typo + space for consistency with Bobby's existing local

### Phase 2: Postgres setup (15 min)

> **Secret handling:** the DB password lives in `MG_DB_PASSWORD` (export it in
> your shell or source `~/.mining-guardian/secrets.env` before running these
> commands). Never paste the literal into the runbook, shell history, or git.

    # Load secret into the current shell (one-time per session)
    set -a; source ~/.mining-guardian/secrets.env; set +a
    : "${MG_DB_PASSWORD:?MG_DB_PASSWORD must be set before running Phase 2}"

    # Create role and DB (canonical Mac Mini setup — guardian_app, db mining_guardian)
    psql postgres <<SQL
    CREATE ROLE guardian_app WITH LOGIN PASSWORD '${MG_DB_PASSWORD}';
    CREATE DATABASE mining_guardian OWNER guardian_app;
    GRANT ALL PRIVILEGES ON DATABASE mining_guardian TO guardian_app;
    SQL

    # Standard path: apply migrations 001-005 + 320-row catalog seed
    # (no VPS dump required — the VPS is decommissioned for MG)
    PGPASSWORD="$MG_DB_PASSWORD" psql -h localhost -U guardian_app \\
        mining_guardian -f migrations/001_initial_schema.sql
    # ... apply migrations 002-005 in order ...
    # ... run scripts/seed_catalog.sh to load 320-row Bitcoin SHA-256 catalog ...

    # Optional snapshot restore path (only if operator explicitly wants pre-Mac-Mini history):
    # gunzip /path/to/mining_guardian_YYYYMMDD.sql.gz
    # PGPASSWORD="$MG_DB_PASSWORD" psql -h localhost -U guardian_app \\
    #     mining_guardian < /path/to/mining_guardian_YYYYMMDD.sql

    # Verify DB is up
    PGPASSWORD="$MG_DB_PASSWORD" psql -h localhost -U guardian_app mining_guardian \\
        -c 'SELECT COUNT(*) FROM scans, miner_readings, hvac_readings, llm_analysis;'

### Phase 3: Python env (10 min)

    cd "~/Documents/GitHub/Mining Gaurdian"
    python3.12 -m venv venv
    venv/bin/pip install -r requirements.txt
    venv/bin/python -c 'from core.database_pg import GuardianPGDB; print("ok")'

### Phase 4: .env (5 min)

Create a fresh .env on the Mac Mini (use the repo's `.env.example` as template; the historical VPS `.env` is a starting reference but paths and hosts differ):

- PYTHONPATH: /Users/BigBobby/Documents/GitHub/Mining-Guardian
- GUARDIAN_PG_HOST: localhost
- GUARDIAN_PG_DBNAME: mining_guardian
- GUARDIAN_PG_USER: guardian_app
- OLLAMA_URL: http://100.110.87.1:11434/api/generate (ROBS-PC on Tailscale — or http://localhost:11434 if running Ollama on Mac Mini)
- ECLYPSE_USER / ECLYPSE_PASS: same (HVAC BAS creds)
- AMS credentials: same

### Phase 5: launchd services (30 min)

Replace the 8 Linux systemd units with 8 macOS launchd .plist files in ~/Library/LaunchAgents/. Each plist needs:

- Label (com.bixbit.mining-guardian, etc.)
- ProgramArguments pointing to the venv Python and the script
- WorkingDirectory
- EnvironmentVariables (all GUARDIAN_PG_* + PYTHONPATH)
- KeepAlive = true
- StandardOutPath / StandardErrorPath → /tmp/<svc>.log

Template plists should live in deploy/macos/ (create these during dry-run prep — NOT YET DONE).

    # Load each service
    for p in ~/Library/LaunchAgents/com.bixbit.*.plist; do
        launchctl load "\$p"
    done

    # Verify all 8 running
    launchctl list | grep com.bixbit

### Phase 6: cron migration (10 min)

macOS cron works the same as Linux cron but env handling is different. crontab -e, use the historical VPS crontab as a reference, adjust paths:

- `/root/Mining-Guardian` (historical VPS path) → `/Users/BigBobby/Documents/GitHub/Mining-Guardian`
- PYTHONPATH accordingly
- venv/bin/python path

### Phase 7: LAN verification (15 min)

With Mac Mini on local LAN, ALL of these should be reachable directly (no Tailscale):

    # AMS
    curl -s http://<ams-host>/api/... | head

    # HVAC warehouse
    curl -s http://192.168.188.235/... | head

    # HVAC s19jpro
    curl -s http://192.168.189.235/... | head

    # Amshub Pi
    ssh bixbit@192.168.188.30 'tmux ls'

    # Local LLM
    curl -s http://100.110.87.1:11434/api/tags | head

Trigger a manual scan and confirm it completes:

    cd "~/Documents/GitHub/Mining Gaurdian"
    venv/bin/python core/mining_guardian.py --once 2>&1 | tail -30

Check that HVAC wrote two rows (warehouse + s19jpro), AMS got ~55 miners, and the scans table got a new row.

### Phase 8: Cutover (15 min)

Once Mac Mini has logged >=1 clean scan + HVAC write + Slack message:

1. Stop all 8 services on the historical VPS (if any are still running — VPS is decommissioned for MG but Bobby may keep it for his own facility)
2. Cloudflare tunnels: NOT applicable — the Mac Mini install is loopback-only, no Cloudflare. If any historical VPS tunnels remain active they can be torn down via the Cloudflare dashboard.
3. Confirm Mac Mini is handling all scan cycles for >=1 hour
4. VPS stays up for Bobby's own facility use — it is not deleted, only decommissioned for Mining Guardian

---

## Known gotchas

**GUARDIAN_PG_DBNAME vs GUARDIAN_PG_DB** — the code standardized on GUARDIAN_PG_DBNAME as of 2026-04-24. Do not introduce the shorter variant when writing new code.

**Repo paths after the 2026-04-26 rename (PR #1)** — the historical VPS path was `/root/Mining-Guardian/` (no typo, no space). The Mac Mini canonical path is `/Users/BigBobby/Documents/GitHub/Mining-Guardian/` (no typo, no space, hyphenated). The historical typo path `/root/Mining-Gaurdian/` and the historical space-and-typo Mac path `/Users/BigBobby/Documents/GitHub/Mining Gaurdian/` are both retired. The OLD-20260428 backup of the historical Mac clone gets deleted Wed 2026-04-29.

**Cloudflare tunnels (historical VPS context only):** The Mac Mini install does NOT use Cloudflare. If any VPS-era tunnels remain active and must be torn down, do so from the Cloudflare dashboard — stopping them before stopping VPS services avoids 502 errors to any remaining Slack/Retool users of the historical VPS setup.

**ROBS-PC must stay on and awake.** It advertises 192.168.188.0/24 and 192.168.189.0/24 as Tailscale routes AND hosts the local LLM at 100.110.87.1:11434. If it sleeps, HVAC polling fails from any non-LAN location, and all LLM calls fail. Mac Mini on local LAN removes the Tailscale dependency for HVAC/miners but NOT for the LLM. If ROBS-PC becomes unreliable, the fallback is to run Ollama on the Mac Mini itself (slower — M-series GPU is weaker than an RTX 4090).

**Note on ROBS-PC vs historical VPS:** ROBS-PC (192.168.188.47 on LAN, Tailscale 100.110.87.1) is Bobby's personal workstation — separate from the historical Hostinger VPS (srv1549463 / 187.124.247.182 / Tailscale 100.106.123.83). ROBS-PC is not decommissioned; the VPS is decommissioned for MG.

**Amshub Pi is NOT a systemd service.** The AMS hub runs in a tmux session named 'hub' on 192.168.188.30 (bixbit/bixbit). Do NOT install a systemd unit without coordination with the Pi's programmer. If the Pi needs restart, ssh bixbit@192.168.188.30, tmux attach -t hub, restart the binary, Ctrl+B d to detach.

**Pre-commit hook runs 48 tests on every commit.** Budget ~90 seconds per commit. If a commit appears to hang, it's the test suite. Do not Ctrl+C — git log --oneline -1 from another terminal shows whether the commit has actually completed.

---

## Emergency rollback

If Mac Mini has a fatal problem post-install, the rollback path is to restore from the pre-install operational-DB snapshot (see Phase 2 optional snapshot path) on a fresh Mac Mini or replacement hardware. The historical VPS (srv1549463 / 187.124.247.182) is decommissioned for MG and should NOT be used as a rollback target.

> **Historical VPS rollback note (pre-Mac-Mini era):** The old runbook described restarting cloudflared + 8 systemd services on the VPS as a rollback. That path no longer applies — the VPS is decommissioned for MG. Preserved here as context only.

**Data divergence (if snapshot was used):** Mac Mini wrote some rows the snapshot does not have. Options:

1. Accept the gap (simpler) — re-import from live data sources after rollback
2. pg_dump from Mac Mini and pg_restore selected tables to fresh Postgres (complex)

For <24h of rollback, option 1 is almost always right.

---

## Post-Monday follow-ups

Documented separately; not part of the deploy itself:

- Archive orphaned SQLite files (core/database.py, etc.) to archive/phase1_sqlite_YYYY-MM-DD/
- Remove the SQLite fallback cache in clients/hvac_client.py (eliminates 'no such table' stderr noise)
- Add the suggested idx_hvac_readings_system_recorded index for Grafana performance
- Build slack_actions_handler.py replacement that routes through OpenClaw (the historical VPS-era version used Cloudflare tunnel inbound; Mac Mini needs the OpenClaw Socket Mode path per CLOUDFLARE_MIGRATION.md)
- Multi-container federation design (when a 2nd site comes online)
