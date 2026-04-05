# Mining Guardian

Autonomous AI-powered Bitcoin mining fleet monitoring system for BiXBiT USA in Fort Worth, TX.
Monitors 58 miners across liquid-cooled hydro racks and an immersion tank,
diagnoses problems with a two-tier AI system, and manages the full action lifecycle —
from detection through approval, execution, ticket creation, and suppression —
all running 24/7 with no Mac required.

The system learns continuously. Every 5-minute scan updates the knowledge base.
Weekly deep training via Claude API synthesizes everything into fleet-wide patterns.
Knowledge Score, insight count, and autonomy rate are all visible live in Grafana.

---

## Architecture

```
Hostinger VPS (187.124.247.182 / Tailscale 100.106.123.83)
  ├── mining-guardian (systemd)         — scans fleet every 5 min
  ├── dashboard-api (systemd :8585)     — Retool + Grafana data + Prometheus /metrics
  ├── approval-api (systemd :8686)      — APPROVE/DENY execution
  ├── slack-listener (systemd)          — polls threads for text approvals
  ├── slack-commands (systemd)          — fleet intelligence bot
  ├── overnight-automation (systemd)    — autonomous low-risk actions 8pm–6am
  ├── cloudflared (systemd)             — dashboard.fieslerfamily.com + slack.fieslerfamily.com
  ├── Prometheus (systemd :9090)        — metrics scraper (30s interval)
  └── Grafana (systemd :3000)           — grafana.fieslerfamily.com dashboards

Windows PC at Facility (Tailscale 100.110.87.1 / robs-pc)
  ├── Tailscale gateway             — routes 192.168.188.0/24 subnet to VPS
  └── Ollama + Qwen2.5 32B (4090)  — local LLM on RTX 4090, port 11434

Anthropic Claude API               — weekly training, knowledge merges, deep analysis
```

---

## Two-Tier AI System

| Tier | Model | Hardware | Used For | Cost |
|------|-------|----------|----------|------|
| Local | Qwen2.5 32B Q4_K_M | RTX 4090 (24GB VRAM) | Every scan analysis (~4.6s) | Free |
| Cloud | Claude Sonnet | Anthropic API | Weekly training, deep analysis, knowledge merges | ~$1-2/mo |

- Ollama on VPS stopped to save CPU — all LLM queries route to Windows PC over Tailscale
- Claude path does NOT fall back to Ollama during outages — scan loop never blocks
- Fleet knowledge context (HW errors, pool rejections, dead boards, chronic miners) in every LLM prompt
- `model_used` in `llm_analysis` always reflects the actual backend that ran

---

## Fleet

| Model | Count | Firmware | Stock TH/s | Max TH/s | Boards |
|-------|-------|----------|-----------|----------|--------|
| Antminer S19J Pro | ~41 | BiXBiT | 104 | 160 | 3 |
| Teraflux AH3880 | 2 | Auradine | 300 (eco) | 600 (turbo) | 2 |
| Antminer S21 EXP Hydro | 2 | BiXBiT | 430 | 506 | 3 |
| Antminer S21 Imm (.22) | 1 | BiXBiT | 208 | 360 | 3 |
| Antminer S21 Imm (.23) | 1 | BiXBiT | 217 | 347 | 3 |

- All cooling is liquid (hydro racks + immersion tank B100). No air cooling.
- Temp thresholds: 🟡 Yellow 76°C, 🔴 Red 86°C (uniform across all models and cooling types)
- Board count per model read from `miner_specs.json` — AH3880 correctly treated as 2-board
- PDUs: orient_RPDU 163 @ 192.168.188.15, 164 @ 192.168.188.16


---

## Services (VPS — all systemd, auto-start on boot)

| Service | Port | Description |
|---------|------|-------------|
| mining-guardian | — | Scans fleet every 5 min, evaluates all miners |
| dashboard-api | 8585 | REST API + Prometheus /metrics endpoint |
| approval-api | 8686 | Handles APPROVE/DENY/approve_selected calls |
| slack-listener | — | Polls threads for text approvals |
| slack-commands | — | Conversational fleet intelligence bot |
| overnight-automation | — | Auto-executes low-risk actions 8pm–6am |
| cloudflared | — | dashboard.fieslerfamily.com → :8585, slack.fieslerfamily.com → :8686 |
| prometheus | 9090 | Metrics scraper, 30s interval |
| grafana | 3000 | grafana.fieslerfamily.com — all dashboards |

---

## Grafana Dashboards (grafana.fieslerfamily.com)

Six dashboards, all fed by Prometheus scraping `dashboard-api:8585/metrics`.
Search box enabled on all per-miner dropdowns — type any IP suffix to filter instantly.

| Dashboard | UID | Contents |
|-----------|-----|----------|
| Mining Guardian — Main | bfi3t0krwak1sd | 14 stat tiles, fleet/HVAC/temp/pool/HW error charts |
| Fleet Overview | efi3msabjg2kge | Online/offline/issues, HVAC trends |
| Per Miner | cfi3mt5a450xse | Hashrate/temp/PDU/board charts + status/history panel — searchable dropdown |
| Board Health | afi3p5mhapn9ce | Per-board voltage/freq/HW errors/power — searchable dropdown |
| Pool Stats | afi3q9w5ishz4f | Fleet totals + rejection rate + top 5 worst offenders table |
| AI & Learning | llm_learning_001 | Knowledge score, insights growth, autonomy rate, fleet health AI impact |

### Prometheus Metrics (complete list)

**Per-miner:** hashrate %, chip temp, PDU power kW, flagged 0/1, dead boards 0/1
**Per-board:** rate MH/s, voltage, frequency MHz, power W, HW errors, temp °C
**Per-pool:** accepted shares, rejected shares, rejection rate %
**Fleet:** online count, offline count, issues count
**HVAC:** supply/return temps °F, delta-T, differential pressure, spray pump
**Weather:** outside temp °F, humidity %
**AI / Knowledge (new):**
- `mining_guardian_knowledge_score` — composite intelligence score (insights + patterns×10 + profiles)
- `mining_guardian_knowledge_insights_total` — total fleet insights learned
- `mining_guardian_knowledge_patterns_total` — recurring patterns identified
- `mining_guardian_knowledge_miner_profiles_total` — behavioral profiles built
- `mining_guardian_knowledge_last_updated_timestamp` — Unix timestamp of last knowledge update
- `mining_guardian_actions_approved_total` — human-approved actions (all time)
- `mining_guardian_actions_denied_total` — denied actions (all time)
- `mining_guardian_actions_auto_overnight_total` — autonomous overnight actions (all time)
- `mining_guardian_actions_expired_total` — auto-expired unanswered approvals (all time)
- `mining_guardian_restarts_total` — total restarts performed (all time)
- `mining_guardian_tickets_created_total` — AMS tickets created by AI (all time)


---

## Database Tables

| Table | Purpose |
|-------|---------|
| `miner_readings` | Every scan — 27 fields per miner |
| `chain_readings` | Per-board: rate, voltage, freq, consumption, HW errors, temp |
| `pool_readings` | Per-pool: accepted/rejected shares, diff, status |
| `miner_state_readings` | Hashrate tiers, device limits, minerStatus codes |
| `miner_ams_extended` | AMS timestamp, map coords, PDU counter, stratum URL |
| `miner_hardware` | Board name, serial, chip die/marking/tech, PCB/BOM version, PSU, ASIC count |
| `log_metrics` | Per-chip hashrate, PSU voltage, system health, chain events — parsed from miner.log |
| `miner_logs` | Full raw miner.log files (30-day retention, 6hr collection, deduped) |
| `action_audit_log` | Every action ever: timestamp, miner, decision, approved_by, slack_user_id |
| `known_dead_boards` | Dead board registry — suppresses reflagging after ticket creation |
| `pending_approvals` | Actions waiting for operator response (1 per miner max, 1hr auto-expire) |
| `miner_restarts` | Every restart recorded — drives 2-restart escalation logic |
| `llm_analysis` | Every LLM response with prompt, model_used, duration |
| `hvac_readings` | HVAC supply/return/pressure/pump data |
| `weather_readings` | Outside temp and humidity |
| `scans` | Scan history: timestamp, online, offline, issues count |

---

## Approval Flow

Scan posts to Slack with a numbered miner list in thread. Reply:
- `APPROVE` — approve all pending actions in that thread
- `DENY` — deny all
- `approve 1,3` — approve miners 1 and 3 by number
- `approve .36,.46` — approve by IP suffix

**Rules:**
- One pending approval per miner maximum — new scan updates existing row, never stacks
- Auto-expire after **1 hour** with audit log entry — fresh approval raised on next scan
- Only authorized Slack user IDs can trigger hardware actions (AUTHORIZED_SLACK_USER_IDS in .env)
- No Slack scan reports during quiet hours (10pm–5am) — overnight automation runs silently

OpenClaw owns Socket Mode — text-based polling only (no Bolt/slack-bolt conflict).

---

## Escalation Logic (2-Restart Rule)

1. Miner flagged → RESTART action → operator approves (or overnight auto-executes)
2. `miner_restarts` table records every restart (manual and overnight auto)
3. If miner has **2+ restarts in 7 days** and is still failing → action auto-escalates to `RESTART_CHECK_BOARDS`
4. Dead board flow executes → AMS ticket created → one-time Slack notice → miner permanently suppressed

Both manual-approved and overnight auto-restarts count toward the 2-restart threshold.

---

## Dead Board Lifecycle

1. Dead board detected → flagged as `RESTART_CHECK_BOARDS`
2. Operator approves → restart executed, logs collected before + after
3. Board still dead → **AMS ticket auto-created** (priority: high)
4. **Next Slack report** → one-time notice: ticket created, miner removed
5. **All future reports** → miner silently suppressed (known_dead_boards table)
6. Board physically repaired → resolve in AMS → monitoring resumes

Dead board miners are **never** shown in the approval queue.


---

## Overnight Automation (8pm–6am)

| Risk | Action | Criteria | Auto-execute |
|------|--------|----------|--------------|
| AUTO | Firmware restart | First attempt tonight, no board issues | ✅ Yes |
| AUTO | PDU cycle | First attempt, PDU assigned | ✅ Yes |
| HOLD | Any restart | Already restarted tonight (1-per-night cap) | ⏸ Skip — logged once |
| MANUAL | Board restart | Dead hashboard detected | ❌ Never |
| MANUAL | Physical cycle | No PDU assigned | ❌ Never |

- Every auto-restart recorded in `miner_restarts` — counts toward 2-restart escalation threshold
- HOLD decisions logged once per overnight window — no audit trail spam
- At 6am when window closes → posts summary via OpenClaw to Slack
- `dry_run: true` in config.json fully blocks all AMS calls — safe for testing

---

## LLM Training System

### Scan-cycle analysis (every 5 min)
- Qwen2.5 32B via Ollama on Windows PC RTX 4090
- Includes accumulated fleet knowledge context every query
- Knowledge base updated after every scan

### Weekly comprehensive training (Sunday 3am)
`train_comprehensive.py` feeds ALL accumulated data to Claude API per miner:
- Full miner logs — no truncation, sectioned boot/mid/tail
- Per-board chain data — avg/min/max rate, voltage, freq, HW errors
- PSU voltage trend, system health, per-chip hashrate
- Chain attach/detach events, pool history, full audit trail
- Scan-to-scan delta analysis (≥10% HR or ≥5°C swings)
- Restart outcome correlation (before/after every approved restart)
- HVAC/weather correlation over last 30 days

### Cross-miner correlation (end of weekly training)
Groups entire fleet by chip bin, die/tech, board serial batch, PCB/BOM version,
PSU version, and fleet-wide restart effectiveness.

---

## Knowledge System

- `knowledge.json` (gitignored) — updates every scan, atomic write (no corrupt-on-crash)
- `knowledge_backup.json` (tracked) — pushed to GitHub daily at 4am
- Weekly deep training via Claude API every Sunday at 3am
- Deduplication on every save — no duplicate patterns
- `combine_knowledge.py` — federated multi-site knowledge merger (future multi-site use)
- **Knowledge metrics flow into Prometheus/Grafana** — score, insights, patterns all live in AI & Learning dashboard

---

## Security

All credentials in `.env` on VPS — never in source code. Key security measures:
- `approval_api.py` — localhost bind, CORS restricted, shared secret (`INTERNAL_API_SECRET`) on all internal endpoints, Slack signature required + replay protection on `/slack/actions`, `/pending` endpoint requires auth
- `dashboard_api.py` — CORS locked to `dashboard.fieslerfamily.com`, `grafana.fieslerfamily.com`, localhost; XSS escaping on all DB values; param bounds clamped
- `slack_listener.py` — authorized user allowlist (`AUTHORIZED_SLACK_USER_IDS`); duplicate handler removed (was causing double hardware actuation)
- `slack_command_handler.py` — question sanitization (500 char cap, strip control chars)
- No credential defaults in source — `hvac_client.py` and `pdu_client.py` fail loudly if env vars unset
- `.env` is gitignored — 17 keys, all required, none duplicated

---

## Slack Commands (type in #mining-guardian)

| Command | What it does |
|---------|-------------|
| `status` | Current fleet overview |
| `hot` | Miners in yellow/red temp zone |
| `dead` | Known dead boards |
| `btc` | Bitcoin price + revenue estimate |
| `knowledge` | What AI has learned |
| `audit` | Last 10 actions taken |
| `overnight` | What happened overnight |
| `predict` | Which miners are most likely to fail next |
| `miner 192.168.188.36` | Deep dive on one miner |
| Any question | Fleet-aware AI answer with full history context |

AI answers include: current fleet state, 14-day miner history, audit trail,
dead board records, learned patterns, and log snippets for named miners.
No Slack messages sent during quiet hours (10pm–5am).


---

## Cron Jobs (VPS)

```
0 3  * * 0   weekly_train.py       — Comprehensive deep training via Claude API (Sunday 3am)
0 4  * * *   backup_knowledge.py   — Push knowledge_backup.json to GitHub (daily 4am)
0 7  * * *   morning_briefing.py   — Daily briefing to Slack (7am)
*/360 * * *  log collection        — Miner logs collected every 6 hours
```

---

## Backup System

**Big-Bobby-T9 drive** (Mac cron every 5 min when Mac is on):
- `guardian.db` — rolling 12 copies + daily snapshots (30 days)
- `knowledge.json` — rolling 12 copies
- `config.json` + `.env` — latest only
- Location: `/Volumes/Big-Bobby-T9/Bixbit USA/Mining Guardian Backups/`

**GitHub:**
- `knowledge_backup.json` — daily 4am push from VPS
- All code — on every push

---

## Key Files

| File | Purpose |
|------|---------|
| `mining_guardian.py` | Main scanner, evaluator, Slack reporter. `dry_run` enforced in all action paths. 2-restart escalation logic. |
| `dashboard_api.py` | REST API + Prometheus /metrics (incl. AI/knowledge metrics) |
| `approval_api.py` | APPROVE/DENY + approve_selected, auth-hardened |
| `slack_approval_listener.py` | Text-based polling approval handler |
| `slack_listener.py` | Socket Mode listener, auth check, duplicate handler removed |
| `slack_command_handler.py` | Conversational fleet intelligence bot |
| `overnight_automation.py` | Autonomous overnight action engine, records restarts for escalation |
| `morning_briefing.py` | Daily 7am Slack briefing, real fleet TH/s revenue, UTC timestamps |
| `llm_analyzer.py` | Two-tier LLM routing: Qwen2.5 32B (scans) + Claude API (training) |
| `knowledge_manager.py` | Persistent knowledge.json — atomic write, live DB context in every prompt |
| `hashrate_evaluation.py` | Three-tier hashrate evaluation, `statistics.median()`, per-model board count |
| `train_comprehensive.py` | Weekly training: full logs + all DB tables + cross-miner correlations |
| `weekly_train.py` | Cron entry point — runs train_comprehensive.py |
| `deep_analysis_claude.py` | Ad-hoc fleet analysis via Claude API (NULL-safe, chunked) |
| `combine_knowledge.py` | Federated multi-site knowledge merger (UTC timestamps, type-safe patterns) |
| `facility_monitor.py` | PDU + tank polling, credentials from env |
| `hvac_client.py` | HVAC client — requests (not curl), credentials from env |
| `pdu_client.py` | PDU client — no default credentials |
| `export_knowledge.py` | Knowledge export for federated merging (LIMIT 500 on audit log) |
| `miner_verify.py` | TCP verify miner online, recv threshold 20 bytes |
| `container_monitor.py` | Built, NOT active — waiting for BiXBiT access grant |
| `backup_knowledge.py` | Daily knowledge backup to GitHub |
| `backup_db.sh` | Mac cron: pulls guardian.db, knowledge.json, config.json, .env every 5min |
| `config.json` | Runtime config + profile map (gitignored — never overwrite with template) |
| `knowledge.json` | LLM persistent memory (gitignored) |
| `knowledge_backup.json` | Tracked backup pushed to GitHub daily |
| `miner_specs.json` | Per-model specs: board count, rated TH/s, profile maps |
| `guardian.db` | SQLite database — never delete, never overwrite with template |

---

## AI Toolkit

Installed: v0.5.0-alpha

Slash commands for Claude Code (VS Code extension):
- `/kickoff` — initialize session, read CLAUDE.md + project context
- `/create-plan` — break a feature into a tracked checklist
- `/iterate` — execute plan items in batches with auto-checkpoint
- `/learn` — turn a correction into a permanent rule in CLAUDE.md
- `/checkpoint` / `/catchup` — save and restore session state across context clears
- `/review` / `/security-check` / `/pre-pr-check` — quality gates

CLAUDE.md contains Mining Guardian-specific rules that Claude Code reads every session.


---

## Fixes Applied (April 4–5, 2026)

### Security hardening
- `approval_api.py` — INTERNAL_API_SECRET required, localhost bind, CORS restricted, Slack signing + replay protection, `/pending` auth
- `dashboard_api.py` — CORS wildcard removed, XSS escaping, param bounds, stale model name fixed, missing route decorator added
- `slack_listener.py` — duplicate `handle_approval` removed (was causing double hardware actuation), authorized user check added
- `slack_command_handler.py` — question sanitization
- `hvac_client.py` — hardcoded `BigSt@r2020` removed, `subprocess curl` replaced with `requests`
- `pdu_client.py` — `admin/admin` defaults removed from constructor

### Crash/correctness fixes
- `mining_guardian.py` — `pdu_cycle` → `pdu_power_cycle`, `SlackNotifier._connect()` → `GuardianDB()`, `post_to_channel()` added, `_wait_for_stable` ip param fixed, `dry_run` enforced in all 3 action paths, AH3880 correctly treated as 2-board
- `hashrate_evaluation.py` — `statistics.median()` replaces integer division (biased low for even-length lists)
- `miner_verify.py` — recv threshold 100→20 bytes (was truncating CGMiner responses)
- `morning_briefing.py` — `hashrate_ths` → `hashrate/1000`, None format crash fixed, Claude response safe indexing, UTC timestamps, real fleet TH/s revenue
- `knowledge_manager.py` — atomic write via `os.replace()`, `os` import added
- `combine_knowledge.py` — Ollama URL fixed (localhost→Windows PC), model fixed (llama3.1:8b→Qwen2.5 32B), HTTP error checking, mutation bug fixed with `dict(i)`, empty synthesis guard, absolute OUTPUT_PATH, pattern type coercion, UTC timestamps
- `export_knowledge.py` — `LIMIT 500` on unbounded audit log query
- `overnight_automation.py` — hardcoded `/root/Mining-Gaurdian` path replaced with `__file__`-relative, restarts now recorded in `miner_restarts` table for escalation counter

### Operational rules
- Pending approval dedup — one pending per miner (upsert not insert), auto-expire after 1 hour with audit log entry
- Quiet hours 10pm–5am — no Slack scan reports (overnight automation still runs)
- Escalation after 2 failed restarts — both manual and auto count, switches action to `RESTART_CHECK_BOARDS` → ticket
- Overnight window changed from 10pm to 8pm
- Yellow zone MONITOR miners removed from Slack reports (still stored in DB for learning)
- Dead board known-miners suppressed after one-time ticket notice

---

## Roadmap

### ✅ Completed
- [x] Full VPS deployment — all 6 services running on systemd
- [x] Prometheus + Grafana — 6 dashboards with live data
- [x] AI & Learning dashboard — knowledge score, insights growth, autonomy rate (all real Prometheus data)
- [x] Pool Stats simplified — fleet totals + top 5 worst offenders (removed per-miner spaghetti)
- [x] Per-miner search — type-to-filter on all per-miner dropdowns (no more scrolling)
- [x] Two-tier AI — Qwen2.5 32B scans + Claude API weekly training
- [x] Knowledge base → Prometheus — all AI metrics visible in Grafana live
- [x] 2-restart escalation — auto-ticket after 2 failed restarts, both manual and overnight
- [x] Overnight automation — autonomous action engine 8pm–6am
- [x] Quiet hours — no Slack noise 10pm–5am
- [x] 1-hour approval window — unanswered approvals auto-expire, re-raised fresh next scan
- [x] Dead board lifecycle — detect → restart → ticket → suppress
- [x] Security hardening — CORS, auth, credential removal, double-actuation bug fixed
- [x] Federated knowledge system — `combine_knowledge.py` for multi-site merges
- [x] Backup system — rolling DB + daily snapshots to T9 drive + GitHub
- [x] HVAC/BAS integration — Distech Eclypse supply/return/pressure/pump data in Slack + Grafana

### 🔄 In Progress
- [ ] AMS SYNC false alarm fix — 13 miners showing offline in AMS but verified online via TCP
- [ ] Approval flow validation — confirm approved actions execute and post confirmation to Slack

### 📋 Upcoming
- [ ] **Repair shop data ingestion** — 1M+ historical data points from partner repair shop; ingestion script TBD
- [ ] **Mac Mini on-site deployment** — will replace VPS, paired with local LLM via Tailscale (delayed ~1 month)
- [ ] **Container monitoring** — supply/return water, flow rate, pump freq, fan status, conductivity, PUE (waiting for BiXBiT access grant)
- [ ] **Auradine AH3880 direct API** — port 8443 Auradine firmware path; API docs needed
- [ ] **Multi-site federation** — monthly knowledge export per site → `combine_knowledge.py` → master_knowledge.json distributed back
- [ ] **Grafana alerting** — alert rules for hashrate drops, dead boards, HW error spikes
- [ ] **Knowledge score trending** — day-over-day % improvement visible in AI dashboard (accumulates over weeks)
- [ ] **PDU password rotation** — change from admin/admin on PDUs .15 and .16

---

## Important Notes

- **Never** `cp config_template.json` over `config.json` on VPS — loses all credentials (happened twice)
- OpenClaw owns Socket Mode — don't run Bolt/slack-bolt in listener (conflict)
- Windows PC must stay on and never sleep — Tailscale gateway AND RTX 4090 LLM
- Pool management and miner settings are out of scope (security policy)
- S19JPro dead hashboard issues suppressed after ticket creation — do not re-raise
- HVAC/BAS integration is one-off for this warehouse — not included in future deployment templates
- AMS API docs: https://api-staging.dev.bixbit.io/api/doc/index.html
- Slack channel: #mining-guardian (ID: C0AQ8SE1448)
- Grafana: grafana.fieslerfamily.com (admin account)
- GitHub repo: robertfiesler-spec/Mining-Gaurdian (intentional typo in name)
