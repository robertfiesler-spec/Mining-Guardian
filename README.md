# Mining Guardian 🤖⛏️

Autonomous Bitcoin mining fleet monitoring system for BiXBiT USA.
Monitors 49+ miners across liquid-cooled racks and immersion tanks,
diagnoses problems with a local LLM, and executes approved actions via Slack.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Hostinger VPS (32GB, 8 vCPU, Ubuntu 24.04)            │
│                                                          │
│  Mining Guardian (systemd) ─── scans every 5 min        │
│  Dashboard API (systemd)  ─── port 8585                 │
│  Approval API (systemd)   ─── port 8686                 │
│  Slack Listener (systemd) ─── polls every 10s           │
│  OpenClaw (Docker)        ─── Slack + LLM gateway       │
│  Ollama (systemd)         ─── LLaMA 3.1 8B             │
│  Tailscale                ─── VPN to mining network     │
└──────────────┬──────────────────────────────────────────┘
               │ Tailscale VPN
┌──────────────┴──────────────────────────────────────────┐
│  Mac (Tailscale Gateway)                                 │
│  Routes 192.168.188.0/24 mining network to VPS          │
│  Dashboard API + Cloudflare tunnel for Retool            │
└──────────────┬──────────────────────────────────────────┘
               │ LAN
┌──────────────┴──────────────────────────────────────────┐
│  Mining Network (192.168.188.x)                          │
│  49 miners │ 2 PDUs │ Immersion Tank │ HVAC system      │
└─────────────────────────────────────────────────────────┘
```

## Fleet Breakdown

| Model | Count | Firmware | Cooling | Notes |
|-------|-------|----------|---------|-------|
| Antminer S19J Pro | ~36 | BiXBiT | Hydro (2U rack) | Main fleet |
| Antminer S19J Pro | 5 | Stock | Hydro (2U rack) | AMS only |
| Teraflux AH3880 | 2 | Auradine | Hydro (2U rack) | PDU 163 |
| Antminer S21 EXP Hydro | 2 | BiXBiT | Hydro (Bitmain shoebox) | PDU 164 |
| Antminer S21 Immersion | 2 | BiXBiT | Immersion (Tank B100) | Ports 19/20 |

## Services (all auto-start on boot)

| Service | Port | Description |
|---------|------|-------------|
| mining-guardian | — | Fleet scanner, Slack reporter, log collector |
| dashboard-api | 8585 | REST API for Retool + chart pages |
| approval-api | 8686 | APPROVE/DENY webhook for Slack flow |
| slack-listener | — | Polls Slack threads for APPROVE/DENY replies |
| ollama | 11434 | Local LLM (LLaMA 3.1 8B) |
| openclaw (Docker) | 58910 | Slack Socket Mode + LLM gateway |

## Scan Flow

1. Every 5 min: scan fleet via AMS WebSocket API
2. Evaluate each miner: hashrate vs profile, chip temp, board health
3. Post to #mining-guardian in Slack (throttled to 1/hour)
4. Save to SQLite: miner_readings, scans, pending_approvals
5. LLM analyzes flagged miners (skips when AMS down or >20 issues)
6. Update knowledge.json with fleet patterns
7. Operator replies APPROVE/DENY → Slack listener triggers actions

## AMS-Down Detection

When AMS reports all miners offline, Mining Guardian:
- Sends ONE hourly message: "AMS is offline" with weather + mechanical only
- Skips all miner analysis, LLM analysis, and pending approvals
- Resumes normal scanning the moment AMS reports any miner online

## LLM Knowledge System

- `knowledge.json` — persistent memory, updated every scan
- Accumulates: miner flag counts, issue history, fleet stats, LLM insights
- Every LLM prompt includes accumulated knowledge as context
- Weekly deep training: Sundays 3am via cron (weekly_train.py)
- System prompt teaches: profile management, liquid cooling, remediation options

## Dead Board Handling

1. First detection → flag as RESTART_CHECK_BOARDS
2. Operator approves → collect pre-restart logs, restart, monitor boards
3. If boards recover → resolved, back to normal scanning
4. If boards still dead → register in known_dead_boards table, create ticket
5. Known dead boards are suppressed from future scans — no repeat flagging

## Key Files

| File | Purpose |
|------|---------|
| mining_guardian.py | Main scanner, analyzer, Slack reporter |
| dashboard_api.py | REST API + HTML chart pages |
| approval_api.py | APPROVE/DENY webhook endpoint |
| slack_approval_listener.py | Polls Slack for APPROVE/DENY replies |
| llm_analyzer.py | Ollama LLM integration |
| knowledge_manager.py | Persistent knowledge.json manager |
| facility_monitor.py | PDU + immersion tank + HVAC polling |
| train_llm.py | Pass 1: CGMiner log analysis |
| train_llm_pass2.py | Pass 2: fleet-wide scan data analysis |
| weekly_train.py | Cron job combining both passes |
| config.json | Runtime config (gitignored) |
| .env | Credentials (gitignored) |
| knowledge.json | LLM persistent memory (gitignored) |
| guardian.db | SQLite database (gitignored) |

## VPS Deployment (Hostinger KVM 8)

- IP: 187.124.247.182
- SSH: root@187.124.247.182
- Tailscale: 100.106.123.83 (srv1549463)
- Expires: 2026-05-01 (auto-renewal on)
- Cost: $25.99/month

## Setup (new VPS)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1:8b

# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up --accept-routes

# Clone repo
apt install -y python3-pip python3-venv git
git clone https://github.com/robertfiesler-spec/Mining-Gaurdian.git
cd Mining-Gaurdian
python3 -m venv venv
source venv/bin/activate
pip install requests websocket-client fastapi uvicorn python-dotenv slack-sdk

# Create .env and config.json (see examples in repo)
# Enable systemd services (mining-guardian, dashboard-api, approval-api, slack-listener)
```

## Retool Dashboard

URL: https://dashboard.fieslerfamily.com (via Cloudflare tunnel)

Layout:
1. Stat tiles: Total Miners | Online | Offline | Issues
2. Currently Flagged Miners table
3. ⚡ Warehouse Power — Live (iFrame /charts/power)
4. 🌡️ Environment Monitor — 5 Day Trend (iFrame /charts/environment)
5. 🧠 AI Insights — LLM Analysis (iFrame /charts/llm-insights)
