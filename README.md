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
  ├── dashboard-api (systemd :8585)     — Retool data + chart pages
  ├── approval-api (systemd :8686)      — APPROVE/DENY execution
  ├── slack-listener (systemd)          — polls threads for text approvals + escalation
  ├── slack-commands (systemd)          — fleet intelligence bot
  ├── overnight-automation (systemd)    — autonomous low-risk actions 10pm–6am
  └── cloudflared (systemd)             — dashboard.fieslerfamily.com tunnel

Windows PC at Facility (Tailscale 100.110.87.1 / robs-pc)
  ├── Tailscale gateway             — routes 192.168.188.0/24 subnet to VPS
  └── Ollama + Qwen2.5 32B (4090)  — local LLM on RTX 4090, port 11434

Anthropic Claude API               — conversational Q&A, weekly training, knowledge merges
```

---

## Two-Tier AI System

| Tier | Model | Hardware | Used For | Cost |
|------|-------|----------|----------|------|
| Local | Qwen2.5 32B Q4_K_M | RTX 4090 (24GB VRAM) | Every scan analysis (~4.6s) | Free |
| Cloud | Claude Sonnet | Anthropic API | Fleet Q&A, weekly training, merges | ~$1-2/mo |

- Ollama on VPS is stopped to save CPU — all LLM routes to Windows PC 4090 over Tailscale
- Fallback: llama3.1:8b still on VPS (stopped, not deleted)
- Knowledge file updates every scan, weekly deep training every Sunday 3am

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
- Temp thresholds: 🟡 Yellow 76°C, 🔴 Red 86°C (all models)
- PDUs: orient_RPDU 163 @ 192.168.188.15, 164 @ 192.168.188.16

---

## Services (VPS — all systemd, auto-start on boot)

| Service | Port | Description |
|---------|------|-------------|
| mining-guardian | — | Scans fleet every 5 min, evaluates all miners |
| dashboard-api | 8585 | REST API for Retool + embedded chart HTML pages |
| approval-api | 8686 | Handles APPROVE/DENY/approve_selected calls |
| slack-listener | — | Polls threads for text approvals, escalation alerts |
| slack-commands | — | Conversational fleet intelligence bot |
| overnight-automation | — | Auto-executes low-risk actions 10pm–6am |
| cloudflared | — | Permanent tunnel: dashboard.fieslerfamily.com → :8585 |

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
| AUTO | Firmware restart | First attempt in 24h, no board issues | ✅ Yes |
| AUTO | PDU cycle | First attempt, PDU assigned | ✅ Yes |
| HOLD | Any restart | Already restarted tonight | ⏸ Skip |
| MANUAL | Board restart | Dead hashboard detected | ❌ Never |
| MANUAL | Physical cycle | No PDU assigned | ❌ Never |

At 6am when window closes → posts summary via OpenClaw to Slack.
Morning briefing cron fires at 7am daily with full overnight report.

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
- 58 miners tracked, 32 known issues, 7 confirmed patterns
- Weekly deep training via Claude API every Sunday at 3am
- Deduplication runs on every save — no duplicate patterns
- `combine_knowledge.py` — federated multi-site knowledge merger (future)

---

## Retool Dashboard (dashboard.fieslerfamily.com)

Layout: Stat tiles → Currently Flagged table → ⚡ Warehouse Power iFrame → 🌡️ Environment iFrame → 🧠 AI Insights iFrame

- Environment chart: downsampled to 4 points/day (6h buckets) — clean 20-point 5-day trend
- Power chart: live PDU + tank readings, 30s refresh
- AI Insights: last 20 LLM analyses with miner IDs and response times
- Stat tiles: fleet totals, online/offline, issue count

---

## Cron Jobs (VPS)

```
0 3 * * 0   weekly_train.py         — Deep training via Claude API (Sundays 3am)
0 4 * * *   backup_knowledge.py     — Push knowledge_backup.json to GitHub (daily 4am)
0 7 * * *   morning_briefing.py     — Daily briefing to Slack (7am)
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
| `mining_guardian.py` | Main scanner, evaluator, Slack reporter |
| `dashboard_api.py` | REST API + chart HTML pages |
| `approval_api.py` | APPROVE/DENY + approve_selected endpoints |
| `slack_approval_listener.py` | Text-based polling approval handler |
| `slack_command_handler.py` | Conversational fleet intelligence bot |
| `overnight_automation.py` | Autonomous overnight action engine |
| `morning_briefing.py` | Daily 7am Slack briefing |
| `llm_analyzer.py` | Two-tier LLM: Ollama + Claude API |
| `knowledge_manager.py` | Persistent knowledge.json (dedup on save) |
| `hashrate_evaluation.py` | Three-tier hashrate evaluation engine |
| `facility_monitor.py` | PDU + tank polling |
| `hvac_client.py` | HVAC/mechanical system client |
| `container_monitor.py` | Built, NOT active — waiting for BiXBiT access |
| `combine_knowledge.py` | Federated multi-site knowledge merger |
| `weekly_train.py` | Weekly deep training via Claude API |
| `backup_knowledge.py` | Daily knowledge backup to GitHub |
| `config.json` | Runtime config + profile map (gitignored) |
| `knowledge.json` | LLM persistent memory (gitignored) |
| `knowledge_backup.json` | Tracked backup pushed to GitHub daily |

---

## Pending / Upcoming

- Repair shop data ingestion — 1M+ data points from partner (waiting)
- Mac Mini on-site deployment — will replace VPS (delayed ~1 month)
- Auradine AH3880 direct API (port 8443) — third firmware path TBD
- Container monitoring — built, waiting for BiXBiT access grant

---

## Important Notes

- **Never** `cp config_template.json` over `config.json` on VPS — loses credentials
- OpenClaw owns Socket Mode — don't run Bolt/slack-bolt in listener (conflict)
- Windows PC must stay on — it's the Tailscale gateway AND the 4090 LLM
- Pool management and miner settings are out of scope (security policy)
- AMS API docs: https://api-staging.dev.bixbit.io/api/doc/index.html
- Slack channel: #mining-guardian (ID: C0AQ8SE1448, private — needs groups:history)
