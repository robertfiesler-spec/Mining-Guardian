# Mining Guardian

AI-powered Bitcoin mining fleet monitor for BiXBiT USA, Fort Worth TX.
Monitors 49 miners across hydro racks and immersion tanks. Provides automated
remediation, Slack approval workflow, Grafana dashboards, and LLM-based
pattern learning.

## Stack Context

- **Language**: Python 3.12
- **Primary service**: mining_guardian.py — systemd daemon, runs every 5 min
- **Dashboard API**: dashboard_api.py — FastAPI on port 8585
- **Database**: SQLite (guardian.db) — never delete, never cp config_template.json over config.json
- **Monitoring**: Prometheus + Grafana (grafana.fieslerfamily.com)
- **LLM**: Qwen2.5 32B on Windows PC RTX 4090 via Ollama + Tailscale (primary), Claude API (weekly training)
- **Notifications**: Slack via Socket Mode (OpenClaw owns the connection)
- **Infrastructure**: VPS (Hostinger KVM 8, 187.124.247.182), Tailscale, Cloudflare tunnels

## Project-Specific Rules

### Critical Safety Rules — Never Violate

- NEVER cp config_template.json over config.json — overwrites AMS credentials and Slack tokens
- NEVER delete or truncate guardian.db — all historical data lives here
- NEVER add Bolt/slack-bolt — OpenClaw owns Socket Mode, conflicts will break Slack
- Pool management and miner settings are explicitly OUT OF SCOPE
- Dead board issues on S19JPros are suppressed after ticket creation — do not re-raise

### Architecture Rules

- ALL miner commands go through AMS first — direct device APIs (port 4028/4028) are fallback only
- PDU power readings ALWAYS take priority over miner-reported consumption
- Problem descriptions stated once at top, miners listed underneath — never repeat per miner
- Never truncate IP lists with "+N more" — show all miners
- Slack reporting throttled to 1 per hour maximum

### Domain Conventions

- Miner status: ONLINE / OFFLINE / AMS_SYNC (verified online but AMS says offline)
- Actions: RESTART / PDU_CYCLE / PHYSICAL_CYCLE / RESTART_CHECK_BOARDS / MONITOR / TEMP_ACTION_REQUIRED
- Temp zones: GREEN <76°C | YELLOW 76-85°C | RED 86°C+
- All cooling is liquid (hydro + immersion) — no fans, no air cooling references
- Hashrate thresholds: flag if below 80% of rated TH/s

### Repo Conventions

- Repo name has intentional space and typo: "Mining Gaurdian" — always quote in terminal
- Python files use venv — always `source venv/bin/activate` before running
- Commit messages: brief description of what changed and why
- Always test imports before pushing: `python3 -m py_compile <file>`

### Known Infrastructure

- VPS: root@187.124.247.182 (Tailscale: 100.106.123.83)
- Windows PC LLM: http://100.110.87.1:11434 (Qwen2.5 32B, must stay on)
- AMS API: https://api-staging.dev.bixbit.io/api/v1 (workspace 119)
- Grafana: grafana.fieslerfamily.com (admin / see memory)
- Dashboard: dashboard.fieslerfamily.com → VPS:8585
- Slack: slack.fieslerfamily.com → VPS:8686

## What Good Looks Like

- Clean, readable Python — no unnecessary complexity
- Every new DB table has an index on (miner_id, scanned_at)
- Every new Prometheus metric has correct labels (miner_ip, model, site, map_location)
- LLM prompts are concise — operators are busy, 10-15 lines max response
- Dashboard API endpoints return JSON only — no HTML except the status_html route
- All services restart cleanly via systemctl — no manual intervention needed

<!-- AI TOOLKIT INTEGRATION -->
## AI Toolkit

Installed: v0.5.0-alpha

### Workflow

```
/kickoff → /create-plan → /iterate → commit → /pre-pr-check → push
```

Use `/learn` immediately after correcting any mistake to make it permanent.

### Available Commands

See `.claude/WORKFLOW.md` for full command reference.

Key commands for this project:
- `/kickoff` — start session, read project context
- `/create-plan` — break feature into checklist
- `/iterate` — execute plan items in batches
- `/verify` — run linting/type checks
- `/learn` — turn a correction into a permanent rule
- `/checkpoint` — save session state before clearing context
- `/catchup` — restore from checkpoint after /clear
