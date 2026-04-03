# Mining Guardian 🤖⛏️

Autonomous Bitcoin mining fleet monitoring system for BiXBiT USA.
Monitors 49+ miners across liquid-cooled racks and immersion tanks,
diagnoses problems with a two-tier AI system, and executes approved actions via Slack.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Hostinger VPS (32GB RAM, 8 vCPU, Ubuntu 24.04)        │
│  IP: 187.124.247.182 | Tailscale: 100.106.123.83       │
│                                                          │
│  Mining Guardian ──── scans every 5 min (systemd)       │
│  Dashboard API   ──── port 8585 (systemd)               │
│  Approval API    ──── port 8686 (systemd)               │
│  Slack Listener  ──── polls APPROVE/DENY (systemd)      │
│  Slack Commands  ──── interactive bot (systemd)         │
│  Claude API      ──── weekly deep training              │
│  Tailscale       ──── VPN to mining network             │
└──────────────┬──────────────────────────────────────────┘
               │ Tailscale VPN
┌──────────────┴──────────────────────────────────────────┐
│  Windows PC (Facility) — Tailscale: 100.110.87.1        │
│  NVIDIA RTX 4090 (24GB VRAM) + 32GB RAM                 │
│                                                          │
│  Ollama ──── Qwen2.5 32B Q4 (GPU inference)             │
│  Tailscale ── gateway to 192.168.188.0/24               │
└──────────────┬──────────────────────────────────────────┘
               │ LAN
┌──────────────┴──────────────────────────────────────────┐
│  Mining Network (192.168.188.x)                          │
│  49 miners | 2 PDUs | Immersion Tank B100 | HVAC        │
└─────────────────────────────────────────────────────────┘
```

## Two-Tier AI System

| Tier | Model | Hardware | Purpose | Cost |
|------|-------|----------|---------|------|
| Local (fast) | Qwen2.5 32B Q4_K_M | RTX 4090 GPU | Every scan analysis, Slack commands | Free |
| Cloud (smart) | Claude Sonnet | Anthropic API | Weekly training, knowledge merge, deep analysis | ~$1-2/mo |
| Fallback | LLaMA 3.1 8B | VPS CPU | If GPU unreachable | Free |

The VPS sends LLM queries to the Windows PC's 4090 over Tailscale.
GPU inference delivers 32B model responses in 10-90 seconds vs 5+ minutes on CPU.

## Fleet Breakdown

| Model | Count | Firmware | Cooling | Stock TH/s | Max TH/s | Boards |
|-------|-------|----------|---------|-----------|----------|--------|
| Antminer S19J Pro | ~41 | BiXBiT | Hydro (2U rack) | 104 | 160 | 3 |
| Teraflux AH3880 | 2 | Auradine | Hydro (2U rack) | 300 (eco) | 600 (turbo) | 2 |
| Antminer S21 EXP Hydro | 2 | BiXBiT | Hydro (Bitmain) | 430 | 506 | 3 |
| Antminer S21 Imm (.22) | 1 | BiXBiT | Immersion (Tank B100) | 208 | 360 | 3 |
| Antminer S21 Imm (.23) | 1 | BiXBiT | Immersion (Tank B100) | 217 | 347 | 3 |

All cooling is liquid (hydro racks + immersion tank). No air cooling.
Temp thresholds: Yellow 76°C, Red 86°C (standard across all models).
AMS model aliases: S19JPro, Antminer S19JPro, Antminer S19j Pro, A2 → all map to S19J Pro.

## Services (all auto-start on boot)

| Service | Port | Location | Description |
|---------|------|----------|-------------|
| mining-guardian | — | VPS | Fleet scanner, analyzer, Slack reporter |
| dashboard-api | 8585 | VPS | REST API + chart pages for Retool |
| approval-api | 8686 | VPS | APPROVE/DENY webhook for Slack flow |
| slack-listener | — | VPS | Polls Slack threads for APPROVE/DENY replies |
| slack-commands | — | VPS | Interactive Slack bot |
| ollama | 11434 | Windows PC | Qwen2.5 32B on RTX 4090 GPU |

## Scan Flow

1. Poll PDUs + immersion tank + HVAC for facility data
2. Fetch weather from OpenWeather API
3. Scan fleet via AMS WebSocket API
4. Evaluate each miner: hashrate vs active profile, chip temp, board health
5. Post to #mining-guardian in Slack (throttled to 1/hour)
6. Save to SQLite: miner_readings, scans, pending_approvals
7. LLM analyzes flagged miners via Qwen 32B on 4090 (skips when AMS down or >20 issues)
8. Update knowledge.json with fleet patterns and LLM insights
9. Operator replies APPROVE/DENY in Slack → listener triggers actions via AMS API

## AMS-Down Detection

When AMS reports all miners offline, Mining Guardian sends ONE hourly message
with weather + mechanical data only. No false alarm spam. No LLM analysis wasted.
Resumes normal scanning the moment any miner reports online.

## Slack Features

### Automated Reports (hourly)
Fleet status, weather, warehouse mechanical, flagged miners grouped by action type.
Yellow zone shows count only (no IP spam). AMS alerts show count for noisy events, IPs for critical.

### APPROVE/DENY Flow
Reply APPROVE or DENY in any scan thread. Slack listener detects within 10 seconds,
calls Approval API, executes restarts via AMS, posts confirmation back in thread.
Audit log tracks every approval/denial with user, timestamp, miner details.

### Interactive Commands (type in #mining-guardian)
- **status** — current fleet overview
- **miner \<ip\>** — detailed miner lookup
- **hot** — list miners in yellow/red temp zone
- **dead** — list known dead boards
- **btc** — Bitcoin price + estimated daily revenue
- **knowledge** — what the AI has learned
- Any other text → forwarded to Qwen 32B with full fleet knowledge context

## LLM Knowledge System

### Persistent Memory (knowledge.json)
Updated after EVERY scan with fleet stats, miner flag counts, issue history.
Every LLM prompt includes accumulated knowledge. LLM insights saved back (feedback loop).

### Weekly Deep Training (Sundays 3am)
Pass 1: CGMiner log analysis. Pass 2: Fleet-wide scan + AMS notification analysis.
Uses Claude API for deeper intelligence than local models.

### Daily Knowledge Backup (4am)
Copies knowledge.json to knowledge_backup.json, commits and pushes to GitHub automatically.

### Federated Knowledge Merge (combine_knowledge.py)
Takes knowledge files from multiple Mining Guardian deployments. Feeds ALL to the LLM
for intelligent synthesis — not just concatenation, a LEARNING EVENT. Discovers cross-site
patterns, weights confidence by confirmation count, generates NEW insights. No internet required.

### Key Patterns Learned
- Chain detachment can indicate bad/dying hashboard, not just firmware glitch
- Pre/post restart log comparison reveals hardware vs firmware root cause
- Single miner overheating → lower TH/s profile before adjusting cooling
- Multiple miners overheating simultaneously → environmental cause, check HVAC
- Dead hashboard after 1 restart → maintenance ticket, stop reflagging

## Dead Board Handling

1. Detected → flag RESTART_CHECK_BOARDS
2. Approved → collect pre-restart logs, restart, monitor boards
3. Recovered → resolved, back to normal scanning
4. Still dead → register in known_dead_boards, create ticket, stop reflagging

## Log Collection

- **Daily:** Once per day for ALL miners (good and bad) — balanced LLM training data
- **Pre-restart:** Collected before every restart for before/after comparison
- **Post-restart:** Collected after stabilization to verify board recovery
- **No duplicates:** Daily limit prevents collecting same miner's logs repeatedly

## Key Files

| File | Purpose |
|------|---------|
| mining_guardian.py | Main scanner, analyzer, Slack reporter |
| dashboard_api.py | REST API + HTML chart pages for Retool |
| approval_api.py | APPROVE/DENY webhook endpoint |
| slack_approval_listener.py | Polls Slack for APPROVE/DENY replies |
| slack_command_handler.py | Interactive Slack bot commands |
| llm_analyzer.py | Two-tier LLM: Ollama (local GPU) + Claude API (cloud) |
| knowledge_manager.py | Persistent knowledge.json manager |
| facility_monitor.py | PDU + immersion tank + HVAC polling |
| combine_knowledge.py | Federated knowledge merger with LLM synthesis |
| train_llm.py | Pass 1: CGMiner log analysis |
| train_llm_pass2.py | Pass 2: fleet-wide scan data analysis |
| weekly_train.py | Cron job combining both training passes |
| backup_knowledge.py | Daily knowledge.json backup to GitHub |
| config.json | Runtime config with profile map (gitignored) |
| config_template.json | Profile map template (tracked in git) |
| .env | Credentials (gitignored) |
| knowledge.json | LLM persistent memory (gitignored) |
| knowledge_backup.json | Daily backup of knowledge.json (tracked) |
| guardian.db | SQLite database (gitignored) |

## Infrastructure

### Hostinger VPS (KVM 8)
- 8 vCPU, 32GB RAM, 400GB NVMe, Ubuntu 24.04
- IP: 187.124.247.182 | Tailscale: 100.106.123.83
- Cost: $25.99/month

### Windows PC (Facility)
- NVIDIA RTX 4090 (24GB VRAM), 32GB RAM
- Tailscale: 100.110.87.1
- Runs Ollama with Qwen2.5 32B Q4_K_M on GPU
- Tailscale gateway advertising 192.168.188.0/24

### Cron Jobs (VPS)
- `0 3 * * 0` — Weekly LLM deep training (Sundays 3am)
- `0 4 * * *` — Daily knowledge backup to GitHub (4am)

### Retool Dashboard
- URL: https://dashboard.fieslerfamily.com (via Cloudflare tunnel)
- Layout: Stat tiles → Flagged Miners → Power chart → Environment chart → AI Insights

## Future: Mac Mini Deployment

Mining Guardian is designed for eventual local deployment on a Mac Mini at the facility.
Apple Silicon runs LLM inference efficiently on unified memory. Direct network access
eliminates Tailscale dependency. Fully air-gapped capable — no cloud required.
