# Mining Guardian

Autonomous Bitcoin mining fleet monitoring system for BiXBiT USA.
Monitors 49+ miners across liquid-cooled racks and an immersion tank,
diagnoses problems with a two-tier AI system, and executes approved
actions via Slack — all running 24/7 with no Mac required.

---

## Architecture

```
Hostinger VPS (187.124.247.182)
  ├── Mining Guardian (systemd)     — scans fleet every 5 min
  ├── Dashboard API (systemd)       — Retool data + chart pages
  ├── Approval API (systemd)        — APPROVE/DENY webhook
  ├── Slack Listener (systemd)      — polls threads for APPROVE/DENY
  ├── Slack Commands (systemd)      — interactive bot
  └── Cloudflare Tunnel (systemd)   — dashboard.fieslerfamily.com

Windows PC at Facility (Tailscale 100.110.87.1)
  ├── Tailscale gateway             — routes VPS to 192.168.188.0/24
  └── Ollama + Qwen2.5 32B (4090)  — local LLM on RTX 4090

Anthropic Claude API               — weekly training + knowledge merges
```

---

## Two-Tier AI System

| Tier | Model | Hardware | Used For | Cost |
|------|-------|----------|----------|------|
| Local | Qwen2.5 32B Q4_K_M | RTX 4090 (24GB VRAM) | Every scan, Slack commands | Free |
| Cloud | Claude Sonnet | Anthropic API | Weekly training, knowledge merges | ~$1-2/mo |

Ollama on the VPS is stopped to save CPU. All LLM queries route to the
Windows PC 4090 over Tailscale at http://100.110.87.1:11434.

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
- Model aliases mapped in config.json (AMS reports inconsistent names)

---

## Services (VPS — all systemd, all auto-start on boot)

| Service | Port | Description |
|---------|------|-------------|
| mining-guardian | — | Fleet scanner, evaluator, Slack reporter |
| dashboard-api | 8585 | REST API + Retool chart pages |
| approval-api | 8686 | APPROVE/DENY webhook |
| slack-listener | — | Polls #mining-guardian for APPROVE/DENY replies |
| slack-commands | — | Interactive Slack bot |
| cloudflared | — | Tunnel: dashboard.fieslerfamily.com → VPS:8585 |
| ollama | — | STOPPED (LLM runs on Windows PC 4090) |

---

## Cloudflare Tunnel

Tunnel ID: `2530d257-66be-4bd4-a056-13c12585c86f`
- `dashboard.fieslerfamily.com` → `localhost:8585` (Retool dashboard)
- `slack.fieslerfamily.com` → `localhost:8686` (approval webhook)

Tunnel runs on VPS via systemd. Mac is no longer required.

---

## Slack Commands

Type any of these in **#mining-guardian**:

| Command | Response |
|---------|----------|
| `status` | Fleet overview — online/offline/issues |
| `miner 192.168.188.x` | Detailed lookup for a specific miner |
| `hot` | Miners in yellow or red temp zone |
| `dead` | Known dead boards (suppressed from scan spam) |
| `btc` | Current Bitcoin price + estimated daily revenue |
| `knowledge` | What the AI has learned — patterns, insights, top flagged |
| Anything else | Forwarded to Qwen 32B with full fleet context |

---

## Scan Flow (every 5 minutes)

1. Poll PDUs (163, 164) + Immersion Tank B100 + HVAC for facility data
2. Fetch weather (Fort Worth, TX)
3. Scan fleet via AMS WebSocket API
4. Evaluate each miner: hashrate vs active profile, chip temp, board count
5. Post to Slack — throttled to **1 message per hour**
6. Save scan to SQLite (`guardian.db`)
7. Send flagged miners to Qwen 32B on 4090 for LLM analysis
8. Update `knowledge.json` with new insights
9. Operator replies **APPROVE** or **DENY** in Slack thread

---

## AMS-Down Detection

When all 49 miners report offline = AMS is down, not a real fleet issue.
Mining Guardian sends **one clean hourly message** with weather + mechanical data only.
No false alarm spam. Normal scanning resumes automatically when AMS returns.

---

## Dead Board Handling

1. Dead board detected → flag as `RESTART_CHECK_BOARDS`
2. Operator approves → collect pre-restart logs → restart → monitor boards
3. Board recovered → resolved, monitoring continues
4. Still dead after restart → register in `known_dead_boards` table → create ticket → **stop reflagging**

---

## Log Collection

| When | What |
|------|------|
| Daily (all miners) | Once per day per miner — good and bad — for LLM learning |
| Pre-restart | Collected before every restart for baseline comparison |
| Post-restart | Collected after stabilization to verify board recovery |

No duplicates — daily limit prevents log spam and resource waste.

---

## Knowledge System

`knowledge.json` is the LLM's persistent memory — gitignored but backed up daily.

- Updated after **every scan** with fleet stats, miner flag counts, issue history
- LLM insights saved **back** into knowledge (feedback loop)
- Every LLM prompt includes accumulated knowledge as context
- **Weekly deep training** via Claude API (cron: Sundays 3am)
- **Daily backup** to GitHub as `knowledge_backup.json` (cron: daily 4am)
- **Federated merge** across sites via `combine_knowledge.py` — LLM synthesizes
  knowledge from multiple Guardian deployments into a master file

Current state: 58 miners tracked, 24 known issues, 9 confirmed patterns.

---

## Facility

| Device | IP | Description |
|--------|----|-------------|
| PDU 163 (orient_RPDU) | 192.168.188.15 | 2U hydro rack power |
| PDU 164 (orient_RPDU) | 192.168.188.16 | Bitmain hydro / S21 EXP Hydro |
| Immersion Tank B100 | 192.168.188.20 | Fog Hashing B100, 20 outlets |
| HVAC | 192.168.188.235 | Cooling system monitoring |

Tank B100: Port 19 = miner 64345, Port 20 = miner 64346, Port 22 = tank cooling system (6.8 kW hardwired).

---

## Key Files

| File | Purpose |
|------|---------|
| `mining_guardian.py` | Main scanner, evaluator, Slack reporter |
| `dashboard_api.py` | REST API + chart HTML pages (power, environment, LLM insights) |
| `approval_api.py` | APPROVE/DENY webhook handler |
| `slack_approval_listener.py` | Polls Slack threads, triggers approval API |
| `slack_command_handler.py` | Interactive Slack bot (status, btc, knowledge, etc.) |
| `llm_analyzer.py` | Two-tier LLM: Ollama (local) + Claude API (deep analysis) |
| `knowledge_manager.py` | Persistent `knowledge.json` manager |
| `facility_monitor.py` | PDU + immersion tank + HVAC polling |
| `combine_knowledge.py` | Federated knowledge merger across Guardian sites |
| `weekly_train.py` | Weekly deep training via Claude API (cron: Sun 3am) |
| `backup_knowledge.py` | Daily knowledge backup to GitHub (cron: daily 4am) |
| `train_llm.py` | One-shot training pass on historical CGMiner logs |
| `train_llm_pass2.py` | One-shot training pass on scan readings + AMS notifications |
| `config.json` | Runtime config + profile map (gitignored) |
| `config_template.json` | Template for config.json — **never cp over live config.json** |
| `knowledge.json` | LLM persistent memory (gitignored) |
| `knowledge_backup.json` | Tracked backup of knowledge.json (pushed to GitHub daily) |

---

## Infrastructure

| Component | Details |
|-----------|---------|
| VPS | Hostinger KVM 8, 32GB RAM, 8 vCPU, Ubuntu 24.04, $25.99/mo |
| VPS IP | 187.124.247.182 (public), 100.106.123.83 (Tailscale) |
| GPU PC | Windows, RTX 4090 24GB VRAM, 32GB RAM, Tailscale 100.110.87.1 |
| Ollama model | qwen2.5:32b-instruct-q4_K_M (20GB, runs on 4090 VRAM) |
| Fallback model | llama3.1:8b on VPS (stopped, kept as backup) |
| Database | SQLite `guardian.db` — 27-field miner_readings + audit log |
| Retool | dashboard.fieslerfamily.com via Cloudflare tunnel on VPS |

---

## Cron Jobs (VPS)

```
0 3 * * 0   weekly_train.py       # Deep training via Claude API — Sundays 3am
0 4 * * *   backup_knowledge.py   # Push knowledge_backup.json to GitHub — daily 4am
```

---

## Planned / Upcoming

- Repair shop data ingestion — 1M+ data points + logs from partner repair shop
- Mac Mini on-site deployment (delayed) — will replace VPS as primary Guardian host
- Auradine AH3880 direct API (port 8443) — third firmware API path TBD
- Container monitoring (BiXBiT access pending) — supply/return temps, flow rate, PUE
- Daily morning report — 7am Slack summary of overnight events
- Retool approve/deny buttons (Phase 3) — requires OpenClaw on Mac Mini
