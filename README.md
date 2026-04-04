# Mining Guardian

Autonomous Bitcoin mining fleet monitoring system for BiXBiT USA in Fort Worth, TX.
Monitors 49+ miners across liquid-cooled racks and an immersion tank,
diagnoses problems with a two-tier AI system, and manages the full action
lifecycle — from detection through approval, execution, ticket creation,
and suppression — all running 24/7 with no Mac required.

---

## Architecture

```
Hostinger VPS (187.124.247.182 / Tailscale 100.106.123.83)
  ├── mining-guardian (systemd)         — scans fleet every 5 min
  ├── dashboard-api (systemd :8585)     — Retool + Grafana data + chart pages
  ├── approval-api (systemd :8686)      — APPROVE/DENY execution
  ├── slack-listener (systemd)          — polls threads for text approvals + escalation
  ├── slack-commands (systemd)          — fleet intelligence bot
  ├── overnight-automation (systemd)    — autonomous low-risk actions 10pm–6am
  ├── cloudflared (systemd)             — dashboard.fieslerfamily.com + slack.fieslerfamily.com tunnels
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

- Ollama on VPS stopped to save CPU — all LLM routes to Windows PC over Tailscale
- Claude path does NOT fall back to Ollama during outages — scan loop never blocks
- Fleet knowledge context (HW errors, pool rejections, dead boards, chronic miners) included in every LLM prompt
- `model_used` in `llm_analysis` table always reflects the actual backend that ran

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
- Temp thresholds: 🟡 Yellow 76°C, 🔴 Red 86°C (all models, all cooling types)
- Board count per model is read from `miner_specs.json` — AH3880 correctly treated as 2-board
- PDUs: orient_RPDU 163 @ 192.168.188.15, 164 @ 192.168.188.16

---

## Services (VPS — all systemd, auto-start on boot)

| Service | Port | Description |
|---------|------|-------------|
| mining-guardian | — | Scans fleet every 5 min, evaluates all miners |
| dashboard-api | 8585 | REST API for Retool + Grafana embedded chart pages |
| approval-api | 8686 | Handles APPROVE/DENY/approve_selected calls |
| slack-listener | — | Polls threads for text approvals, escalation alerts |
| slack-commands | — | Conversational fleet intelligence bot |
| overnight-automation | — | Auto-executes low-risk actions 10pm–6am |
| cloudflared | — | dashboard.fieslerfamily.com → :8585, slack.fieslerfamily.com → :8686 |
| prometheus | 9090 | Metrics scraper, 30s interval |
| grafana | 3000 | grafana.fieslerfamily.com — fleet dashboards |


---

## Grafana Dashboards (grafana.fieslerfamily.com)

Five dashboards, all fed by Prometheus scraping `dashboard-api:8585/metrics`.

| Dashboard | UID | Contents |
|-----------|-----|----------|
| Mining Guardian — Main | bfi3t0krwak1sd | 14 stat tiles, fleet/HVAC/temp/pool/HW error charts |
| Fleet Overview | efi3msabjg2kge | Online/offline/issues, HVAC trends |
| Per Miner | cfi3mt5a450xse | Hashrate/temp/PDU/board charts + status/history panel |
| Board Health | afi3p5mhapn9ce | Per-board voltage/freq/HW errors/power |
| Pool Stats | afi3q9w5ishz4f | Accepted/rejected shares, rejection rate |

Prometheus metrics include:
- Per-miner: hashrate %, temp, PDU power, flags
- Per-board: rate MH/s, voltage, frequency, power, HW errors, temp
- Per-pool: accepted shares, rejected shares, rejection rate %
- Fleet: online count, offline count, flagged count
- HVAC: supply/return temps, delta-T, differential pressure
- Weather: outside temp, humidity

---

## Database Tables

| Table | Purpose |
|-------|---------|
| `miner_readings` | Every scan — 27 fields per miner |
| `chain_readings` | Per-board: rate, voltage, freq, consumption, HW errors, temp |
| `pool_readings` | Per-pool: accepted/rejected shares, diff, status |
| `miner_state_readings` | Hashrate tiers, device limits, minerStatus codes |
| `miner_ams_extended` | AMS timestamp, map coords, PDU counter, stratum URL |
| `miner_hardware` | Board name, serial, chip die/marking/tech, PCB/BOM version, control board, PSU, ASIC count |
| `log_metrics` | Per-chip hashrate, PSU voltage, system health, chain events — parsed from miner.log |
| `miner_logs` | Full raw miner.log files (30-day retention, 6hr collection, deduped) |
| `action_audit_log` | Every action ever: timestamp, miner, decision, approved_by, slack_user_id |
| `known_dead_boards` | Dead board registry — suppresses reflagging after ticket creation |
| `pending_approvals` | Actions waiting for operator response |
| `llm_analysis` | Every LLM response with prompt, model_used, duration |
| `hvac_readings` | HVAC supply/return/pressure/pump data |
| `weather_readings` | Outside temp and humidity |

---

## Approval Flow

Scan posts to Slack with a numbered miner list in thread. Reply:
- `APPROVE` — approve all pending actions
- `DENY` — deny all
- `approve 1,3` — approve miners 1 and 3 by number
- `approve .36,.46` — approve by IP suffix

OpenClaw owns Socket Mode — Block Kit buttons are not used (conflict).
Text-based polling runs every 15 seconds.

---

## Dead Board Lifecycle

1. Dead board detected → flagged as `RESTART_CHECK_BOARDS`
2. Operator approves → restart executed, logs collected before + after
3. Board still dead → **AMS ticket auto-created** (priority: high)
4. **Next Slack report** → one-time notice: ticket created, miner removed
5. **All future reports** → miner silently suppressed
6. Board physically repaired → resolve in AMS → monitoring resumes

Dead board miners are **never** shown in the approval queue.

---

## Overnight Automation (10pm–6am)

| Risk | Action | Criteria | Auto-execute |
|------|--------|----------|--------------|
| AUTO | Firmware restart | First attempt tonight, no board issues, no PDU assigned | ✅ Yes |
| AUTO | PDU cycle | First attempt, PDU assigned | ✅ Yes |
| HOLD | Any restart | Already restarted tonight (1-per-night cap enforced) | ⏸ Skip — logged once |
| MANUAL | Board restart | Dead hashboard detected | ❌ Never |
| MANUAL | Physical cycle | No PDU assigned | ❌ Never |

- `dry_run: true` in config.json fully blocks all AMS calls — no accidental execution
- 1-per-night restart cap correctly counts `AUTO_OVERNIGHT` audit rows
- HOLD decisions logged once per overnight window — no audit trail spam
- At 6am when window closes → posts summary via OpenClaw to Slack


---

## LLM Training System

### Scan-cycle analysis (every 5 min)
- Qwen2.5 32B via Ollama on Windows PC RTX 4090
- Includes accumulated fleet knowledge context every query:
  - Hardware identity count, boards with HW errors (last 7 days)
  - Pool rejection spikes (>1%, last 24h)
  - Known dead boards + ticket status
  - Chronic flagged miners with issue history
  - Recent LLM insights

### Weekly comprehensive training (Sunday 3am)
`train_comprehensive.py` feeds ALL accumulated data to Claude API per miner:

- **Full miner logs** — no truncation, sectioned into boot/init + mid-operation + tail
- **Per-board chain data** — avg/min/max rate, voltage, freq, HW errors, dead reading count
- **PSU voltage trend** — avg/min/max voltage, estimated power (from log_metrics)
- **System health** — CPU%, miner CPU%, free RAM (from log_metrics)
- **Per-chip hashrate** — which chips underperform vs target (from log_metrics)
- **Chain attach/detach events** — timestamps, frequency (from log_metrics)
- **Pool data** — accepted/rejected/rejection rate history
- **Full audit trail** — every action, who approved, outcome
- **Scan-to-scan delta analysis** — significant swings (≥10% HR or ≥5°C) over last 50 scans
- **Restart outcome correlation** — before/after for every approved restart (RESOLVED / NOT RESOLVED)
- **HVAC/weather correlation** — facility environment over last 30 days

### Cross-miner correlation pass (end of weekly training)
`get_cross_miner_correlations()` groups the entire fleet by:
- Chip bin grade — does chip quality predict failure rate?
- Chip die/technology — different silicon, different behavior
- Board serial batch — same SN prefix = same production run, often fails together
- PCB/BOM version — newer revisions may have fixed design issues
- PSU version — PSU firmware behavior across models
- Fleet-wide restart effectiveness — do restarts actually work or mask hardware issues?

---

## Log Collection

- **Frequency:** every 6 hours
- **Retention:** 30 days
- **Deduplication:** same log file never saved twice
- **Hardware parsing:** every miner.log auto-parsed for board name, serial, chip die, PCB version on save
- **Log metrics extraction:** per-chip hashrate, PSU voltage, system health, chain events stored in `log_metrics` table

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

---

## Knowledge System

- `knowledge.json` (gitignored) — updates every scan
- `knowledge_backup.json` (tracked) — pushed to GitHub daily at 4am
- Weekly deep training via Claude API every Sunday at 3am
- Deduplication runs on every save — no duplicate patterns
- `combine_knowledge.py` — federated multi-site knowledge merger (future use)

---

## Retool Dashboard (dashboard.fieslerfamily.com)

Layout: Stat tiles → Currently Flagged table → ⚡ Warehouse Power iFrame → 🌡️ Environment iFrame

- Environment chart: downsampled to 4 points/day (6h buckets) — clean 20-point 5-day trend
- Power chart: live PDU + tank readings, 30s refresh
- Stat tiles: fleet totals, online/offline, issue count

---

## Per-Miner Status Page

`GET /miner/status_html/{ip}` — dark-themed HTML page with:
- Current status badge (FLAGGED / OK / OFFLINE / DEAD BOARD)
- Action badge, model, hashrate%, temp, PDU power, profile, issue text
- Full audit history table (timestamp, APPROVED/DENIED color-coded, action, approved_by, problem)

Embedded in Grafana Per Miner dashboard via JavaScript fetch.


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

## AI Toolkit

Installed: v0.5.0-alpha (James Scaggs / jamesscaggs/ai-toolkit)

Provides slash commands for Claude Code (VS Code extension or terminal):
- `/kickoff` — initialize session, read CLAUDE.md + project context
- `/create-plan` — break a feature into a tracked checklist
- `/iterate` — execute plan items in batches with auto-checkpoint
- `/learn` — turn a correction into a permanent rule in CLAUDE.md
- `/checkpoint` / `/catchup` — save and restore session state across context clears
- `/verify` — lint, type check, tests
- `/review` / `/security-check` / `/pre-pr-check` — quality gates

CLAUDE.md contains Mining Guardian-specific rules that Claude Code reads every session:
critical safety rules, architecture rules, domain conventions, known infrastructure.

---

## Key Files

| File | Purpose |
|------|---------|
| `mining_guardian.py` | Main scanner, evaluator, Slack reporter. `dry_run` enforced in all action paths |
| `dashboard_api.py` | REST API + chart HTML pages + Prometheus /metrics endpoint |
| `approval_api.py` | APPROVE/DENY + approve_selected endpoints |
| `slack_approval_listener.py` | Text-based polling approval handler |
| `slack_command_handler.py` | Conversational fleet intelligence bot |
| `overnight_automation.py` | Autonomous overnight action engine |
| `morning_briefing.py` | Daily 7am Slack briefing |
| `llm_analyzer.py` | Two-tier LLM: Qwen2.5 32B (scans) + Claude API (training) |
| `knowledge_manager.py` | Persistent knowledge.json with live DB context in every LLM prompt |
| `hashrate_evaluation.py` | Three-tier hashrate evaluation + `get_boards()` per-model board count |
| `train_comprehensive.py` | Weekly comprehensive training: full logs + all DB tables + cross-miner correlations |
| `train_llm.py` | Per-miner log-based training (sectioned, no truncation) |
| `weekly_train.py` | Cron entry point — runs train_comprehensive.py |
| `deep_analysis_claude.py` | Ad-hoc fleet analysis via Claude API (NULL-safe, chunked, error-handled) |
| `facility_monitor.py` | PDU + tank polling |
| `hvac_client.py` | HVAC/mechanical system client |
| `container_monitor.py` | Built, NOT active — waiting for BiXBiT access |
| `combine_knowledge.py` | Federated multi-site knowledge merger |
| `backup_knowledge.py` | Daily knowledge backup to GitHub |
| `config.json` | Runtime config + profile map (gitignored) |
| `knowledge.json` | LLM persistent memory (gitignored) |
| `knowledge_backup.json` | Tracked backup pushed to GitHub daily |
| `miner_specs.json` | Per-model specs: board count, rated TH/s, profile maps |
| `guardian.db` | SQLite database — never delete, never overwrite with template |

---

## Bug Fixes Applied (this session)

### overnight_automation.py
- PDU cycles now pass `pdu_id` and `outlet` into the executor — no more silent no-ops logged as success
- Restart count query now matches `decision='AUTO_OVERNIGHT'` — 1-per-night cap actually works
- HOLD decisions deduplicated — each hold logged once per window, not every 5 minutes

### deep_analysis_claude.py
- NULL-safe formatting via `_safe_fmt()` — SQL aggregates returning NULL no longer crash the run
- Proper API error handling — `raise_for_status()` + try/except for timeout, HTTP, and parse errors
- Real prompt chunking by character budget — most-flagged miners first, scales as fleet grows

### llm_analyzer.py
- Removed Ollama fallback from `_query_claude` — Claude outage can no longer block scans for 300s
- `model_used` now reflects the actual backend that ran, not just whether the API key is set
- Claude path now includes fleet knowledge context — same as Ollama path always had

### mining_guardian.py + hashrate_evaluation.py
- `dry_run: true` now enforced in `execute_restart`, `execute_pdu_cycle`, and dead-board restart path
- `_analyze_chains` now takes `expected_boards` parameter — AH3880 correctly reported as 2-board
- `MinerSpecsLoader.get_boards()` added — reads board count from `miner_specs.json` per model
- Console report banner now shows actual dry_run state instead of hardcoded `True`

---

## Pending / Upcoming

- Fix AMS SYNC false alarms (13 miners showing as offline in AMS but verified online)
- Repair shop data ingestion — 1M+ data points from partner (waiting)
- Mac Mini on-site deployment — will replace VPS (delayed ~1 month)
- Auradine AH3880 direct API (port 8443) — third firmware path TBD
- Container monitoring — built, waiting for BiXBiT access grant

---

## Important Notes

- **Never** `cp config_template.json` over `config.json` on VPS — loses all credentials
- OpenClaw owns Socket Mode — don't run Bolt/slack-bolt in listener (conflict)
- Windows PC must stay on and never sleep — Tailscale gateway AND RTX 4090 LLM
- Pool management and miner settings are out of scope (security policy)
- Dead board issues on S19JPros are suppressed after ticket creation — do not re-raise
- AMS API docs: https://api-staging.dev.bixbit.io/api/doc/index.html
- Slack channel: #mining-guardian (ID: C0AQ8SE1448)
- Grafana: grafana.fieslerfamily.com (admin account)
