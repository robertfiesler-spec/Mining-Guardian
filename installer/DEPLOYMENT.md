# Mining Guardian — Local Deployment Package
## Project: Installer Build
### Target: Mac Mini (or comparable mini PC) on local mining network

---

## Vision

Mining Guardian runs as a **fully self-contained local appliance**. One box, plugged into the mining network, monitoring and managing the fleet with zero cloud dependencies during daily operation. The operator interacts through a local web dashboard and Slack. The AI learns locally and phones home only for weekly deep analysis and monthly knowledge sync.

**No VPS. No Cloudflare. No tunnels. No external services required for daily operation.**

---

## Architecture: Local Mac Mini Deployment

```
┌─────────────────────────────────────────────────────────┐
│                    MINING NETWORK (LAN)                  │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │ Miner 1  │  │ Miner 2  │  │ Miner N  │  ← Fleet    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘             │
│       │              │              │                    │
│  ┌────┴──────────────┴──────────────┴────┐             │
│  │           BiXBiT AMS (on-network)     │             │
│  │     WebSocket + REST + Cookie Auth     │             │
│  └──────────────────┬────────────────────┘             │
│                     │                                    │
│  ┌──────────────────┴────────────────────┐             │
│  │         MAC MINI — Mining Guardian     │             │
│  │                                        │             │
│  │  ┌─────────────┐  ┌───────────────┐  │             │
│  │  │  Guardian    │  │  OpenClaw     │  │             │
│  │  │  Daemon      │  │  + Local LLM  │  │             │
│  │  │  (Python)    │  │  (Ollama)     │  │             │
│  │  └──────┬───────┘  └───────────────┘  │             │
│  │         │                              │             │
│  │  ┌──────┴───────┐  ┌───────────────┐  │             │
│  │  │  SQLite DB   │  │  Prometheus   │  │             │
│  │  │  guardian.db  │  │  + Grafana    │  │             │
│  │  └──────────────┘  └───────────────┘  │             │
│  │                                        │             │
│  │  ┌──────────────────────────────────┐  │             │
│  │  │  Local Web Dashboard (:8585)     │  │             │
│  │  │  Grafana (:3000)                 │  │             │
│  │  │  Approval API (:8686)            │  │             │
│  │  └──────────────────────────────────┘  │             │
│  └────────────────────────────────────────┘             │
│                                                         │
│  Operator accesses: http://mac-mini-ip:3000 (Grafana)   │
│                     http://mac-mini-ip:8585 (Dashboard)  │
└─────────────────────────────────────────────────────────┘

External (internet required only for):
  ├── Slack API — notifications + approve/deny workflow
  ├── Claude Sonnet API — weekly training analysis (Sunday 3am)
  ├── Open-Meteo API — weather data (free, no key)
  └── Monthly knowledge export → USB → Bobby → combined → USB back
```

---

## What the Installer Must Do

### Phase 1: Pre-Flight Checks
- [ ] Verify OS (macOS / Linux)
- [ ] Verify Python 3.11+ installed
- [ ] Verify network connectivity to AMS
- [ ] Verify Slack bot token works
- [ ] Check available disk space (minimum 20GB recommended)
- [ ] Check available RAM (minimum 8GB, 16GB+ recommended for local LLM)

### Phase 2: Configuration Wizard (Interactive)
Collects all required info via a step-by-step terminal form or local web form:

**Site Identity:**
- Site name (e.g., "USA 188")
- Site ID (auto-generated or manual)
- Operator name
- Operator Slack user ID

**AMS Connection:**
- AMS URL (e.g., `https://api-staging.dev.bixbit.io/api/v1`)
- AMS email
- AMS password
- AMS workspace ID
- Verify: attempt login + workspace select → confirm miner count

**Fleet Profile:**
- Auto-discover miner models from AMS scan
- For each model: confirm stock TH/s, max TH/s, board count
- BiXBiT firmware miners: auto-detect profile ranges
- Auradine miners: named profiles (eco/turbo)
- Per-miner overrides (S21Imm units with different specs)

**PDU Mapping:**
- Auto-discover PDUs from AMS
- Map PDU outlets to miners (or import from AMS if available)
- Flag miners with NO PDU (S19JPros at USA 188)

**HVAC (Optional):**
- HVAC controller IP (if applicable)
- HVAC endpoint type (Modbus, REST, BACnet)
- Supply/return temp sensor mapping
- Note: HVAC is site-specific — not required for base install

**Slack Integration:**
- Slack bot token (xoxb-...)
- Slack channel ID for #mining-guardian
- Authorized user IDs for approve/deny
- Verify: post a test message to channel

**Local LLM (Optional):**
- OpenClaw installed? (Y/N)
- Ollama model preference (default: llama3.1:8b or route to external GPU)
- Tailscale IP if routing to remote GPU box
- Test LLM connectivity

**Claude API (Weekly Training):**
- Anthropic API key for weekly training
- Confirm: test API call

### Phase 3: Installation
- [ ] Create Python virtual environment
- [ ] Install all pip dependencies
- [ ] Initialize SQLite database (guardian.db)
- [ ] Write config.json from wizard answers
- [ ] Write .env with secrets
- [ ] Install launchd services (macOS) or systemd (Linux)
- [ ] Configure Prometheus scrape targets
- [ ] Import Grafana dashboards (all 6)
- [ ] Configure Grafana datasource (Prometheus)
- [ ] Start all services
- [ ] Verify all services healthy

### Phase 4: First Run
- [ ] Execute first AMS scan — discover all miners
- [ ] Build initial miner_specs from fleet
- [ ] Collect first set of logs
- [ ] Parse hardware identity for all miners
- [ ] Set hashrate baselines to "learning" mode (72-hour window)
- [ ] Post "Mining Guardian Online" to Slack
- [ ] Display first-run summary: miners found, models, profiles, estimated daily revenue

### Phase 5: Verification
- [ ] Dashboard accessible at http://localhost:8585
- [ ] Grafana accessible at http://localhost:3000
- [ ] Slack messages posting correctly
- [ ] AMS connection stable across 3 consecutive scans
- [ ] All miner readings populating in DB
- [ ] Print: "Installation complete. Mining Guardian is monitoring your fleet."

---

## Services (macOS launchd)

| Service | Port | Description |
|---------|------|-------------|
| mining-guardian | — | Main daemon: scan, analyze, remediate |
| dashboard-api | 8585 | Fleet dashboard + AI Intelligence Center |
| approval-api | 8686 | Internal approve/deny API |
| slack-listener | — | Polls Slack for approve/deny replies |
| slack-commands | — | Slash command handler |
| overnight-automation | — | Auto-actions during off-hours |
| prometheus | 9090 | Metrics collection |
| grafana | 3000 | Dashboards and visualization |
| openclaw (optional) | 18789 | Local LLM gateway |

On macOS these run as launchd agents (~/Library/LaunchAgents/) instead of systemd units.
On Linux they run as systemd services (same as current VPS setup).

---

## Directory Structure (Installed)

```
~/mining-guardian/
├── config.json              # Site configuration (generated by wizard)
├── .env                     # Secrets (AMS creds, Slack token, API keys)
├── guardian.db              # SQLite database (all fleet data)
├── knowledge.json           # AI knowledge base (updates every scan)
├── knowledge_backup.json    # Daily backup (git-tracked)
├── miner_specs.json         # Miner model specs and profiles
├── core/                    # Main daemon + support modules
├── api/                     # Dashboard, approval, Slack APIs
├── ai/                      # Training, prediction, fingerprinting
├── clients/                 # AMS, PDU, HVAC, immersion clients
├── monitoring/              # Facility monitoring
├── scripts/                 # Utility scripts
├── logs/                    # Daily log files
├── dashboards/              # Grafana dashboard JSON exports
├── installer/               # Installation scripts and wizard
│   ├── install.sh           # Main installer entry point
│   ├── wizard.py            # Interactive configuration wizard
│   ├── setup_services.py    # Service installation (launchd/systemd)
│   ├── import_dashboards.py # Grafana dashboard import
│   ├── first_run.py         # Initial fleet discovery
│   └── verify.py            # Post-install health check
└── docs/
    ├── DEPLOYMENT.md         # This file
    ├── OPERATOR_GUIDE.md     # How to use Mining Guardian daily
    ├── TROUBLESHOOTING.md    # Common issues and fixes
    └── API_REFERENCE.md      # Internal API documentation
```

---

## Key Design Decisions

### No Cloud Dependencies for Daily Operation
- All scanning, analysis, and remediation happens locally
- SQLite database lives on the Mac Mini — no external DB
- Prometheus + Grafana run locally — no cloud dashboards
- OpenClaw + Ollama run locally for real-time LLM analysis
- Slack is the only external service during daily operation

### Slack as Notification Layer (Not Control Plane)
- Slack delivers notifications and collects approve/deny decisions
- The local web dashboard is the primary control surface
- If Slack is down, the system continues operating autonomously
- Future: local notification system could replace Slack entirely

### Weekly Claude Analysis (Only External AI Call)
- Sunday 3am: system sends anonymized fleet data to Claude Sonnet API
- Claude returns comprehensive analysis, pattern updates, recommendations
- This is the only time the system needs internet access for AI
- If internet is unavailable, training skips that week — no impact on daily operation

### Monthly Knowledge Federation
- Each site exports a knowledge file monthly
- USB drive or secure file transfer to central operator (Bobby)
- combine_knowledge.py merges insights from all sites via Claude
- Updated knowledge pushed back to each site
- No internet required — USB sneakernet works

### Mac Mini Hardware Recommendations
- **Minimum:** Mac Mini M1, 8GB RAM, 256GB SSD
  - Runs all services except local LLM
  - Routes LLM queries to external GPU box via Tailscale
- **Recommended:** Mac Mini M2 Pro, 16GB RAM, 512GB SSD
  - Runs everything including Ollama with llama3.1:8b
  - Fully self-contained, no external GPU needed
- **Optimal:** Mac Mini M4 Pro, 32GB RAM, 512GB SSD
  - Runs larger LLM models (Qwen2.5 32B Q4)
  - Room for growth as fleet expands

---

## What Needs to Be Built

### Installer Scripts
- [ ] `install.sh` — Main entry point, OS detection, dependency install
- [ ] `wizard.py` — Interactive configuration wizard
- [ ] `setup_services.py` — Create launchd plists (macOS) or systemd units (Linux)
- [ ] `import_dashboards.py` — Import all 6 Grafana dashboards via API
- [ ] `first_run.py` — Initial fleet discovery and calibration
- [ ] `verify.py` — Post-install health check
- [ ] `update.sh` — Pull updates, preserve config/DB, restart services
- [ ] `uninstall.sh` — Clean removal

### Configuration Templates
- [ ] `config_template.json` — Annotated config with all fields documented
- [ ] `.env.example` — All required environment variables with descriptions
- [ ] `launchd/` — macOS launchd plist templates for each service
- [ ] `prometheus.yml.template` — Prometheus config template
- [ ] `grafana/provisioning/` — Auto-provisioning for datasource + dashboards

### Documentation
- [ ] `DEPLOYMENT.md` — This file (installation guide)
- [ ] `OPERATOR_GUIDE.md` — Daily operation manual
- [ ] `TROUBLESHOOTING.md` — Common issues and solutions
- [ ] `ARCHITECTURE.md` — System design and data flow
- [ ] `API_REFERENCE.md` — All internal endpoints documented

### Code Changes for Local Deployment
- [ ] Remove all Cloudflare tunnel references
- [ ] Remove VPS-specific paths (/root/Mining-Gaurdian → ~/mining-guardian)
- [ ] Add macOS launchd support alongside systemd
- [ ] Make all service ports configurable via config.json
- [ ] Add local web-based approve/deny (reduce Slack dependency)
- [ ] Add update mechanism that preserves config + DB
- [ ] Add backup/restore for guardian.db
- [ ] Health check endpoint that installer/verify.py can call

---

## Timeline

| Week | Focus |
|------|-------|
| Apr 7-13 | Wednesday demo, 48hr test wrap-up, document findings |
| Apr 14-20 | Installer wizard, service templates, launchd support |
| Apr 21-27 | Dashboard polish, operator guide, first-run experience |
| Apr 28-May 4 | Testing on Bobby's Mac, dry-run installs, bug fixes |
| May 5-9 | **Mac Mini arrives** — real deployment, live testing |
| May 10+ | Iterate based on live deployment findings |

---

## Open Questions
1. Should the local web dashboard replace Slack approve/deny entirely? (Reduces external dependency)
2. Do we ship Ollama pre-configured or let the installer handle it?
3. What's the update mechanism — git pull or packaged releases?
4. Do we need a local backup strategy for guardian.db? (Time Machine covers Mac, but explicit backups might be smarter)
5. Should the installer support headless (SSH-only) installation for Linux mini PCs?
6. Multi-site: does each site need its own Slack channel, or can they share #mining-guardian with site prefixes?

---

*Last updated: April 6, 2026*
*Branch: installer-build*
*Project: Mining Guardian Local Deployment Package*
