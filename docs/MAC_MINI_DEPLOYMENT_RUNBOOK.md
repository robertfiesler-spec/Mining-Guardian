# Mac Mini Deployment Runbook

**Target date:** Monday 2026-04-27 (hardware ETA)
**Purpose:** step-by-step procedure for moving Mining Guardian from the Hostinger VPS (187.124.247.182) to a local Mac Mini on the Fort Worth facility LAN.
**Status:** runbook documented, dry run not yet executed.

---

## Why we're moving

The VPS was always staging. Production on a Mac Mini means:

- Local LAN access to AMS at 192.168.188.x, miners at 192.168.188.x / 192.168.189.x, HVAC controllers at 192.168.188.235 and 192.168.189.235, the Amshub Pi at 192.168.188.30 — no Tailscale dependency for anything on-site.
- No public ingress. The three Cloudflare tunnels (dashboard.fieslerfamily.com, slack.fieslerfamily.com, grafana.fieslerfamily.com) get torn down.
- Local LLM (Qwen on ROBS-PC) stays primary, no Claude API in the hot path. Claude API still used for weekly training and cohort refinement only.
- Target: 1 Mac Mini per container, scales to 120–240 miners per instance.

---

## Pre-flight (do before Mac Mini arrives)

These are independent of hardware and can be done any time before Monday.

### 1. Fresh-install dry run (CRITICAL)

Spin up a scratch Postgres DB and verify all 8 services come up cleanly against an empty schema. This catches any missing CREATE TABLE IF NOT EXISTS or migration gaps **before** they become a Monday fire.

    ssh root@187.124.247.182

    # Create scratch DB
    sudo -u postgres psql <<SQL
    CREATE DATABASE mining_guardian_dryrun OWNER guardian_app;
    GRANT ALL PRIVILEGES ON DATABASE mining_guardian_dryrun TO guardian_app;
    SQL

    # Apply canonical schema
    cd /root/Mining-Gaurdian
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

### 2. Knowledge snapshot to bring across

Before leaving the VPS, export the state that Mac Mini needs on day 1:

    cd /root/Mining-Gaurdian
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

Transfer these files to a USB drive or Bobby's Mac before Monday.

### 3. Cloudflare tunnel shutdown preparation

Do NOT shut down the VPS tunnels until the Mac Mini is up and verified. But have the shutdown command ready:

    systemctl stop cloudflared
    systemctl disable cloudflared
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

    # Create role and DB matching VPS setup
    psql postgres <<SQL
    CREATE ROLE guardian_app WITH LOGIN PASSWORD 'MiningGuardian2026!';
    CREATE DATABASE mining_guardian OWNER guardian_app;
    GRANT ALL PRIVILEGES ON DATABASE mining_guardian TO guardian_app;
    SQL

    # Load from VPS dump (brought over on USB)
    gunzip /path/to/mining_guardian_YYYYMMDD.sql.gz
    PGPASSWORD='MiningGuardian2026!' psql -h localhost -U guardian_app \\
        mining_guardian < /path/to/mining_guardian_YYYYMMDD.sql

    # Verify row counts match VPS
    PGPASSWORD='MiningGuardian2026!' psql -h localhost -U guardian_app mining_guardian \\
        -c 'SELECT COUNT(*) FROM scans, miner_readings, hvac_readings, llm_analysis;'

### Phase 3: Python env (10 min)

    cd "~/Documents/GitHub/Mining Gaurdian"
    python3.12 -m venv venv
    venv/bin/pip install -r requirements.txt
    venv/bin/python -c 'from core.database_pg import GuardianPGDB; print("ok")'

### Phase 4: .env (5 min)

Copy the VPS .env template, edit for Mac Mini paths:

- PYTHONPATH: /Users/BigBobby/Documents/GitHub/Mining Gaurdian
- GUARDIAN_PG_HOST: localhost (same)
- GUARDIAN_PG_DBNAME: mining_guardian (same)
- OLLAMA_URL: http://100.110.87.1:11434/api/generate (same — ROBS-PC on Tailscale)
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

macOS cron works the same as Linux cron but env handling is different. crontab -e, paste VPS crontab, adjust paths:

- /root/Mining-Gaurdian → /Users/BigBobby/Documents/GitHub/Mining Gaurdian
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

1. Stop all 8 services on VPS
2. Stop Cloudflare tunnel: systemctl stop cloudflared && systemctl disable cloudflared
3. Confirm Mac Mini is handling all scan cycles for >=1 hour
4. VPS can stay up idle for 7 days as a hot spare, then be decommissioned

---

## Known gotchas

**GUARDIAN_PG_DBNAME vs GUARDIAN_PG_DB** — the code standardized on GUARDIAN_PG_DBNAME as of 2026-04-24. Do not introduce the shorter variant when writing new code.

**Repo path on Mac** — /Users/BigBobby/Documents/GitHub/Mining Gaurdian has both a space AND the typo 'Gaurdian'. Always quote the path in shell commands. The VPS path /root/Mining-Gaurdian has only the typo (no space).

**Cloudflare tunnels stop BEFORE VPS services stop**, not after. If you stop VPS services first, the tunnels return 502s and Slack/Retool users see errors. Correct order: stop tunnels → confirm Mac Mini is primary → stop VPS services.

**ROBS-PC must stay on and awake.** It advertises 192.168.188.0/24 and 192.168.189.0/24 as Tailscale routes AND hosts the local LLM at 100.110.87.1:11434. If it sleeps, HVAC polling fails from any non-LAN location, and all LLM calls fail. Mac Mini on local LAN removes the Tailscale dependency for HVAC/miners but NOT for the LLM. If ROBS-PC becomes unreliable, the fallback is to run Ollama on the Mac Mini itself (slower — M-series GPU is weaker than an RTX 4090).

**Amshub Pi is NOT a systemd service.** The AMS hub runs in a tmux session named 'hub' on 192.168.188.30 (bixbit/bixbit). Do NOT install a systemd unit without coordination with the Pi's programmer. If the Pi needs restart, ssh bixbit@192.168.188.30, tmux attach -t hub, restart the binary, Ctrl+B d to detach.

**Pre-commit hook runs 48 tests on every commit.** Budget ~90 seconds per commit. If a commit appears to hang, it's the test suite. Do not Ctrl+C — git log --oneline -1 from another terminal shows whether the commit has actually completed.

---

## Emergency rollback

If Mac Mini has a fatal problem post-cutover, roll back within 24h:

    # On VPS (assuming still idle)
    systemctl start cloudflared
    for svc in mining-guardian dashboard-api approval-api slack-listener \\
               slack-commands overnight-automation mining-guardian-alerts; do
        systemctl start "\$svc"
    done

**Data divergence:** Mac Mini wrote some rows the VPS does not have. Options:

1. Accept the gap (simpler) — Mac Mini data is orphaned, re-migrate later
2. pg_dump from Mac Mini and pg_restore selected tables to VPS (complex)

For <24h of rollback, option 1 is almost always right.

---

## Post-Monday follow-ups

Documented separately; not part of the deploy itself:

- Archive orphaned SQLite files (core/database.py, etc.) to archive/phase1_sqlite_YYYY-MM-DD/
- Remove the SQLite fallback cache in clients/hvac_client.py (eliminates 'no such table' stderr noise)
- Add the suggested idx_hvac_readings_system_recorded index for Grafana performance
- Build slack_actions_handler.py replacement that routes through OpenClaw (VPS-only today; needs alt for pure-local Mac Mini operation)
- Multi-container federation design (when a 2nd site comes online)
