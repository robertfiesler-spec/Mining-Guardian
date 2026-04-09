# HANDOFF — April 9 2026, mid-morning

**Context budget in the prior chat hit its limit. Bobby is opening a new chat with less history. This doc is the complete state snapshot so the new session can pick up seamlessly.**

Read this doc top to bottom BEFORE taking any action. It has everything you need. Then start from the "YOUR NEXT MOVE" section at the bottom.

---

## First things first — read these files in this order

1. `CLAUDE.md` at repo root — contains THE OPERATING RULES. Read the "Working Principles" and "Deployment Target" sections carefully. They were locked in this morning after yesterday's overrun and are non-negotiable.
2. `docs/RESUME_HERE_2026_04_08_EVENING.md` — last night's handoff, still valid for general context, but the TOP PRIORITY section there (OpenClaw → guardian.db wiring) is the work currently in flight and this doc supersedes it for current state.
3. This doc (you're reading it).

---

## The one-line summary of where we are

**OpenClaw is alive and chatting (as of last night). The `guardian-db` skill that makes it answer real fleet questions has been WRITTEN and COMMITTED to the repo this morning, but it has NOT been INSTALLED in the OpenClaw container yet, and it has NOT been TESTED end-to-end. That is the next work.**

---

## Current state of the code

**Mac repo AND VPS AND GitHub are all in sync at commit `dcd9d28`** as of the time this doc was written.

Commits added this morning (in order):

| Commit | What |
|---|---|
| `27a92a2` | `docs(claude.md): add Working Principles section - 2-vs-10 rule and operating discipline` |
| `28010b8` | `docs(claude.md): add Deployment Target section - Mac mini at customer site, open and useful by default` |
| `68322d4` | `Daily knowledge backup — 2026-04-09 04:00 — 58 miners, 50 insights, 7 patterns` (automated cron, rebased onto main) |
| `70e2f9c` | `feat(dashboard-api): add /query/* read-only endpoints for OpenClaw skill` (342 lines added to `api/dashboard_api.py`, plus `scripts/add_query_endpoints.py` as the inserter script) |
| `dcd9d28` | `feat(openclaw): guardian-db skill - lets OpenClaw answer real fleet questions` (3 files in `deploy/openclaw-skills/guardian-db/`: SKILL.md, query.sh, references/schema.md) |

All pushed to GitHub. All pulled on the VPS. No local modifications pending on either side.

## The phantom commit — explanation for the new session

While the prior Claude session was inspecting the database schema, commit `dcd9d28` appeared on origin/main, committed by `Automation-builds <robertefiesler@gmail.com>`. Prior Claude did NOT make that commit and stopped everything when it discovered it. After discussion with Bobby, the most likely explanation is that it was made by another Claude session earlier in the day (before memory sync) OR by the AI Toolkit automation running `/iterate` or similar. The commit message matches prior Claude's voice because the automation was working from the same CLAUDE.md rules and reached the same design.

**New session: do NOT panic if you see a commit you don't recognize. Automation is a known source of commits on this repo. Check it, verify it, and if it matches what you'd build, proceed.**

## Files to verify exist and look right

Before doing anything, the new session should verify these files are present and not corrupted:

- `CLAUDE.md` at repo root (should be ~180 lines, contains Working Principles and Deployment Target sections)
- `api/dashboard_api.py` (should be ~1818 lines, contains the new `/query/*` endpoints near the end, just before `if __name__ == "__main__":`)
- `deploy/openclaw-skills/guardian-db/SKILL.md` (natural-language description Qwen reads)
- `deploy/openclaw-skills/guardian-db/query.sh` (shell wrapper that calls the /query/* endpoints)
- `deploy/openclaw-skills/guardian-db/references/schema.md` (column reference for the LLM)
- `scripts/add_query_endpoints.py` (the one-shot inserter that added the endpoints, kept for provenance)

Quick verify:
```bash
cd '/Users/BigBobby/Documents/GitHub/Mining Gaurdian'
wc -l CLAUDE.md api/dashboard_api.py deploy/openclaw-skills/guardian-db/SKILL.md deploy/openclaw-skills/guardian-db/query.sh deploy/openclaw-skills/guardian-db/references/schema.md
git log --oneline -5
```

Expected git output: top commit is `dcd9d28 feat(openclaw): guardian-db skill...`

---

## YOUR NEXT MOVE (new session — start here)

The remaining work is **5 ordered steps**. Do them in this order. Each one has a pass/fail test. Do NOT proceed to step N+1 until step N passes.

### Step 1 — Verify the new /query/* endpoints actually work on the VPS

The endpoints are committed in `70e2f9c` and pulled on the VPS. But `dashboard-api` systemd may not have been restarted since the pull, so the new routes may not be live yet. Restart and test.

```bash
# On the VPS
ssh root@187.124.247.182
cd /root/Mining-Gaurdian
python3 -m py_compile api/dashboard_api.py  # syntax check first
systemctl restart dashboard-api
sleep 3
journalctl -u dashboard-api -n 30 --no-pager  # look for errors
curl -s http://127.0.0.1:8585/query/fleet_summary | python3 -m json.tool
curl -s http://127.0.0.1:8585/query/flagged_miners | python3 -m json.tool
curl -s 'http://127.0.0.1:8585/query/recent_actions?hours=4' | python3 -m json.tool
```

**PASS criteria:**
- `py_compile` succeeds (no syntax error)
- `dashboard-api` systemd status is `active (running)`
- journalctl shows no tracebacks
- Each curl returns valid JSON with real data (fleet_summary has a scan_id, flagged_miners has a count, recent_actions has an actions array)

**If any of these fail:** stop, diagnose, do NOT move to Step 2. The skill depends on these endpoints working. Most likely failure mode is a Python indentation or syntax error in the inserted block — the `git diff 68322d4 70e2f9c -- api/dashboard_api.py` will show exactly what was added.

### Step 2 — Verify the VPS host is reachable from inside the OpenClaw container

Before installing the skill, confirm the OpenClaw container can actually reach dashboard-api at the VPS host's Docker bridge IP.

```bash
# From the VPS host
docker inspect openclaw-5b5o-openclaw-1 --format '{{range .NetworkSettings.Networks}}{{.Gateway}}{{end}}'
# Expected: 172.18.0.1 (the Docker bridge gateway)

# From inside the OpenClaw container
docker exec openclaw-5b5o-openclaw-1 sh -c 'curl -s http://172.18.0.1:8585/query/fleet_summary | head -20'
```

**PASS criteria:** curl from inside the container returns valid JSON. Container can reach the host on the Docker bridge gateway IP on port 8585.

**If this fails:** the issue is that Mining Guardian's dashboard-api is bound to `0.0.0.0:8585` (per the last line of the file: `uvicorn.run(app, host="0.0.0.0", port=8585)`), so it SHOULD be reachable from the Docker bridge. If it's not reachable, check for a firewall rule (`ufw status`) blocking the bridge network.

### Step 3 — Inspect the committed skill files (don't assume they're correct)

Even though `dcd9d28` was committed and looks reasonable, the new session should actually READ the three files before installing them in the container. Look for:

- `SKILL.md` — does the description clearly tell Qwen when to invoke the skill? Does it include the operator rules (no temp flagging until 84°C, no HVAC delta-T warnings, no fan/air-cooling references)? Does it have example triggers?
- `query.sh` — does it use `curl` with the correct base URL (`http://172.18.0.1:8585` with a `# TEMP:` comment noting the May 1 forever-value)? Does it have a hard timeout? Does it have a `raw_sql` escape hatch or is that deferred?
- `references/schema.md` — does it match the ACTUAL guardian.db schema (22 tables, specifically miner_readings, chain_readings, action_audit_log, miner_restarts, known_dead_boards, hvac_readings)?

If the files are good, proceed to Step 4. If anything is wrong or missing, fix it on the Mac repo, commit, push, pull on the VPS, then proceed.

### Step 4 — Install the skill into the OpenClaw container

The `deploy/openclaw-skills/guardian-db/` directory in the repo is the SOURCE OF TRUTH. The LIVE copy goes inside the container at `/data/.openclaw/skills/guardian-db/` which is the Docker volume mount that persists across container restarts and recreations. Copy it in:

```bash
# From the VPS host
cd /root/Mining-Gaurdian

# Copy each file into the container volume
docker cp deploy/openclaw-skills/guardian-db/SKILL.md openclaw-5b5o-openclaw-1:/data/.openclaw/skills/guardian-db/SKILL.md
docker cp deploy/openclaw-skills/guardian-db/query.sh openclaw-5b5o-openclaw-1:/data/.openclaw/skills/guardian-db/query.sh
docker cp deploy/openclaw-skills/guardian-db/references/schema.md openclaw-5b5o-openclaw-1:/data/.openclaw/skills/guardian-db/references/schema.md

# Make the shell wrapper executable inside the container
docker exec openclaw-5b5o-openclaw-1 chmod +x /data/.openclaw/skills/guardian-db/query.sh

# Verify
docker exec openclaw-5b5o-openclaw-1 ls -la /data/.openclaw/skills/guardian-db/
docker exec openclaw-5b5o-openclaw-1 ls -la /data/.openclaw/skills/guardian-db/references/

# Restart OpenClaw so the skill registry picks up the new skill
docker restart openclaw-5b5o-openclaw-1
sleep 8
docker logs openclaw-5b5o-openclaw-1 --since 30s 2>&1 | grep -iE 'skill|guardian-db|error' | tail -20
```

**PASS criteria:**
- All three files present inside the container at the right paths
- query.sh is executable (`-rwxr-xr-x`)
- OpenClaw logs after restart show the skill was loaded OR at least no errors about guardian-db
- Slack reconnects cleanly (`[slack] socket mode connected` in the logs)

**If copying into the container fails:** may need to create the parent directory first: `docker exec openclaw-5b5o-openclaw-1 mkdir -p /data/.openclaw/skills/guardian-db/references`

### Step 5 — Acceptance test via Slack DM

The final test. Bobby DMs `@Mining Guardian` from his phone or laptop and asks real fleet questions. Each should get a REAL answer with REAL data, not a generic Qwen guess.

Tests to run (Bobby should run these, Claude watches the OpenClaw logs in parallel):

1. `How many miners are flagged right now?` — should hit /query/flagged_miners
2. `What's the worst-performing miner in the fleet?` — should hit /query/worst_performers
3. `How is the fleet overall?` — should hit /query/fleet_summary
4. `What actions has the bot taken in the last 4 hours?` — should hit /query/recent_actions
5. `Show me miner history for 192.168.188.36 over the last 24 hours` — should hit /query/miner_history/192.168.188.36
6. `Which boards are failing on 192.168.188.55?` — should hit /query/board_health/192.168.188.55

**PASS criteria:** at least 4 out of 6 return real data. If 5 or 6 work, the skill is done. If 3 or fewer work, the SKILL.md description needs tuning so Qwen actually invokes the skill instead of answering from general training.

Watch the logs with:
```bash
ssh root@187.124.247.182 'docker logs -f openclaw-5b5o-openclaw-1 2>&1 | grep -iE "skill|guardian|slack|delivered"'
```

---

## PARKED — items to come back to LATER today (in order)

These are all deferred work. Do NOT tackle them until the 5 steps above are complete and the acceptance test passes.

### P1 — OpenClaw gateway bind-host (webhook push model, Bobby's later-today item)

**Status:** blocked. The OpenClaw gateway is listening on `ws://127.0.0.1:18789` inside the container — container loopback only. Mining Guardian on the host cannot reach it to POST scan data for proactive commentary.

**What was tried:** edited `openclaw.json` to set `gateway.bind = "custom"` and `gateway.customBindHost = "0.0.0.0"`. Config loaded silently, bind did NOT change, gateway still listens on `127.0.0.1`. The `resolveGatewayBindUrl` function exists in `/usr/local/lib/node_modules/openclaw/dist/core-CFWy4f9Z.js` and the config keys match the schema — but something upstream isn't passing the values to that function. The config backup is at `/data/.openclaw/openclaw.json.bak.before-gateway-bind-2026-04-09` inside the container; the edit WAS made but had no effect.

**What the new session should do when tackling this:**
1. Revert the gateway.bind/customBindHost change (set both back to the defaults — remove the keys entirely) since they're inert
2. Find who CALLS `resolveGatewayBindUrl` — grep for `resolveGatewayBindUrl` across the dist/ directory, find the caller, see what config path IT reads from
3. The answer may be nested differently — could be `gateway.transport.bind` or `gateway.runtime.bind` or `channels.gateway.bind`
4. If the supported path is found, use it. If OpenClaw simply doesn't support non-loopback binding in this version, the fallback is to edit OpenClaw's docker-compose to expose port 18789 via `ports: ["127.0.0.1:18789:18789"]` and recreate the container — BUT per CLAUDE.md rules, verify the /data volume persists across recreation before doing this.

**Bobby's note:** he wants the skill working FIRST (which this handoff is about), then the webhook push AFTER.

### P2 — Gitignore and move `deploy/openclaw_config_2026_04_08_LIVE.json`

This file exists untracked in the Mac repo. It's 18KB, contains Slack tokens, and should NOT be committed as-is. Options:

1. Move it out of the repo entirely (e.g., to `~/secrets/openclaw-snapshots/`)
2. Add it to `.gitignore` and leave it in place for reference
3. Scrub the tokens and commit a redacted version

Bobby's preference not yet established. Don't commit it.

### P3 — Fix the VPS remote URL typo

VPS currently has `origin` set to `https://github.com/robertfiesler-spec/Mining-Gaurdian.git` (with the typo). GitHub auto-redirects to the correct `Mining-Guardian.git` but warns "This repository moved." One-line fix:

```bash
ssh root@187.124.247.182 'cd /root/Mining-Gaurdian && git remote set-url origin https://github.com/robertfiesler-spec/Mining-Guardian.git && git remote -v'
```

### P4 — Stale "49 miners" reference in CLAUDE.md

First line of `CLAUDE.md` says "Monitors 49 miners" but fleet is currently 58. Tiny cosmetic fix, 1 line, separate commit.

### P5 — VPS untracked files cleanup

`git status` on the VPS shows a bunch of untracked files from prior sessions:
- `api/dashboard_api.py.bak.before-query-endpoints-2026-04-09` — Claude's backup, safe to delete
- `backups/` directory
- `branding/mining_guardian_*_transparent.png` (4 files) — probably should be committed
- `guardian.db-shm`, `guardian.db-wal` — SQLite journal files, should be gitignored
- `scripts/fix_*.py` (7 files) — old experimental scripts, probably safe to delete or archive
- `scripts/llm_scan_hook.py`, `scripts/local_llm_analyzer.py`, `scripts/test_status.py` — review individually

None are blocking anything. Clean up when time allows.

### P6 — Daily Log Capture & 14-Day Baseline System

Vision doc at `docs/DAILY_LOG_CAPTURE_VISION.md` — the firmware-regression catcher. 3-5 day build. High priority but scheduled for a later sprint, not today.

### P7 — Intelligence catalog Phase 1 deployment

Currently blocked on WSL2/Docker at ROBS-PC. Per last night's doc, 30-minute hard cap on the Windows debug, fall back to native Postgres via EnterpriseDB installer if it doesn't crack. **This is where Bobby was supposed to be spending time this morning but we got pulled into the skill work first.** Come back to it after the skill is working.

---

## Critical facts the new session needs to know

### About the deployment target (rules from CLAUDE.md)

- **The product is a Mac mini at a customer site running docker-compose.** VPS + Cloudflare + host systemd is temporary scaffolding until May 1 2026.
- **Normal internet access is fine.** Grafana, dashboard, approval API all reachable from the internet. Slack via Socket Mode. Outbound HTTPS for training and knowledge sync. "Open and useful by default, tightenable by choice" — customer chooses lockdown via config, we don't pre-lock.
- **The "no media server" rule is about scope discipline, NOT network discipline.** Don't add unrelated services "because why not." But Grafana IS in scope AND IS reachable from the internet.
- **Every new decision gets evaluated by:** "does this make the May 1 migration easier, harder, or neutral?" Answer must never be "harder."
- **Use `# TEMP:` comments** for VPS-specific values that will change on May 1, naming the forever-value.

### About the fleet

- 58 miners total (NOT 49 — CLAUDE.md is stale, P4 above)
- Mixed firmware: 36 BiXBiT, 5 stock, 2 Teraflux AH3880 Auradine
- All liquid cooling — NEVER reference fans or air cooling
- Temp alerting threshold is **84°C chip temp**, NOT 76°C (operator rule)
- HVAC delta-T is intentionally low — do NOT recommend HVAC investigation based on delta-T
- S19JPros with dead boards are suppressed from reports after ticketing — do not re-raise
- Known dead boards list has ~12 entries and grows over time

### About OpenClaw (what IS working as of this handoff)

- Container: `openclaw-5b5o-openclaw-1` on the VPS
- Image: `ghcr.io/hostinger/hvps-openclaw:latest`
- Config file inside container: `/data/.openclaw/openclaw.json` (persisted via Docker volume)
- Bot user in Slack: `U0APQ4VDKGC` (shared with Mining Guardian Python daemon — both backends use the same bot identity)
- Bobby's Slack user ID (allowlisted): `U07AGTT8CLD`
- Slack mode: Socket Mode, outbound WebSocket only (no inbound ports needed)
- DM policy: `allowlist` with `allowFrom=["U07AGTT8CLD"]` — only Bobby can DM the bot
- OAuth scopes (after yesterday's fix): includes `im:write`, `mpim:write`, `groups:write`, all the `*:history` scopes
- Primary LLM: Qwen 2.5 32B on RTX 4090 at `http://100.110.87.1:11434/v1` (Bobby's PC, accessed over Tailscale)
- Fallback LLMs: 22 Nexos-hosted models (GPT-5, Claude Opus/Sonnet 4.6, Gemini, Grok, etc.)
- **What's missing (today's work):** a database skill so it can answer fleet questions instead of generic Qwen guesses

### About the VPS

- Host: `187.124.247.182` (Tailscale: `100.106.123.83`)
- SSH: `ssh root@187.124.247.182`
- Repo: `/root/Mining-Gaurdian/` (note the typo — must quote if there's a space, but there isn't one on the VPS side, only on the Mac side where the folder is `/Users/BigBobby/Documents/GitHub/Mining Gaurdian/` with a space)
- Production DB: `/root/Mining-Gaurdian/guardian.db`
- Mining Guardian systemd service: `mining-guardian.service`
- Dashboard API systemd service: `dashboard-api.service` (port 8585, bound to 0.0.0.0)
- 9 systemd services total, all should be `active (running)`
- Bobby's Tailscale subnet route via Windows PC for 192.168.188.0/24 (USA 188 facility network)

### About the Mac repo

- Path: `/Users/BigBobby/Documents/GitHub/Mining Gaurdian/` (SPACE in the folder name, TYPO in "Gaurdian" — always quote in terminal)
- Git remote: `https://github.com/robertfiesler-spec/Mining-Guardian.git` (correct — no typo)
- Branch: `main`
- Deploy pattern: edit on Mac → commit → push → `ssh root@... 'cd /root/Mining-Gaurdian && git pull'`

---

## Bobby's energy and mindset (important context)

Bobby worked yesterday until ~18:42 clearing a 4-layer Slack auth stack, felt the day as a failure even though the main goal was achieved, and called out a new operating rule this morning: the **2-vs-10 rule** — pick the right fix over the fast fix, no more re-doing work, ~3 weeks to finish.

Today's session has been MUCH more deliberate — reading before editing, backing up before changing, verifying before deploying. That's the new normal. Keep it.

Bobby wants the OpenClaw conversational bot to actually answer fleet questions so he can work faster with it. That's the top priority and the reason the skill work exists at all. Get that working, show him the win in Slack, then tackle the webhook and the WSL2/catalog work.

---

## The clean first message Bobby should send in the new chat

Copy this exactly and paste as your first message in the new chat:

> Picking up from a previous chat that hit its context limit. Read `docs/HANDOFF_2026_04_09_MIDMORNING.md` at the repo root — it has the complete state and a 5-step plan. Start with the "YOUR NEXT MOVE" section. I'm at ROBS-PC. Do NOT re-debug OpenClaw DMs — they work. Do NOT containerize Mining Guardian — that's May 1. Just finish wiring the `guardian-db` skill per the plan, test it end-to-end, and show me a working DM conversation.

That's it. One message. The new Claude reads the handoff, walks the 5 steps, and picks up exactly where we left off.

---

*End of handoff. Good luck.*
