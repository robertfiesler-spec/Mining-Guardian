# Mining Guardian

**Autonomous fleet monitoring and remediation system for Bitcoin mining operations.**

Mining Guardian runs on a local Mac Mini connected directly to the mining network. It connects to the BiXBiT AMS platform via authenticated WebSocket and REST API, scans every miner in the fleet, and delivers actionable alerts to the operator via Slack. A local LLM (via OpenClaw) provides plain-English diagnosis and decision support.

Humans stay in the loop on all remediation actions. Mining Guardian detects, explains, and recommends — operators approve.

---

## Current Status — March 30, 2026

| Component | Status |
|---|---|
| AMS authentication (cookie JWT) | ✅ Live |
| Full fleet scan via WebSocket | ✅ Live |
| Hashrate + temperature analysis | ✅ Live |
| PDU power cycle | ✅ Built |
| Firmware restart | ✅ Built |
| SQLite database (all scans) | ✅ Live |
| Miner log collection | ✅ Live |
| Weather data per scan | ✅ Live |
| AMS notifications (40/scan) | ✅ Live |
| Slack reporting | ✅ Live |
| Dashboard API (FastAPI :8585) | ✅ Live |
| Retool dashboard (Phase 1) | ✅ Live via cloudflared tunnel |
| Action audit log | ✅ Live |
| Knowledge export / combine | ✅ Built |
| Slack approval flow | 🔧 In progress — polling listener next |
| OpenClaw / local LLM | 🔜 Mac Mini arriving this week |
| Automations | 🔜 Pending AMS access |
| Facility map integration | 🔜 Pending AMS map setup |

---

## Fleet Status (as of 2026-03-30)

- **44 miners** in AMS (cleaned up — offline miners removed)
- **43 online** | **1 offline** (53490 — S19JPro, no PDU assigned)
- **1 underperforming** (53476 — A2, 0% hashrate, firmware restart needed)
- **6 monitoring** (S19JPros running 76–84°C)
- Facility: Fort Worth, TX | Two PDUs at 192.168.188.15 and .16
- Subnet: 192.168.188.x


---

## System Architecture

```
BiXBiT AMS (cloud)
        │
        │  WebSocket + REST (cookie-based JWT)
        ▼
┌──────────────────────────────────────────────────┐
│              Mac Mini (local network)            │
│                                                  │
│  mining_guardian.py  (Python daemon)             │
│  ├── Scans fleet every 5 min                     │
│  ├── Hashrate % + chip temp analysis             │
│  ├── PDU cycle / firmware restart logic          │
│  ├── Miner log collection + 7-day purge          │
│  ├── AMS notification polling (40/scan)          │
│  ├── Weather data (Open-Meteo, Fort Worth TX)    │
│  ├── SQLite DB — all scan + telemetry history    │
│  └── Posts findings to Slack                     │
│                                                  │
│  slack_listener.py  (approval polling loop)      │
│  ├── Polls #mining-guardian every 5 seconds      │
│  ├── Detects APPROVE / DENY in scan threads      │
│  ├── Executes approved actions via AMS           │
│  └── Writes to permanent audit log               │
│                                                  │
│  dashboard_api.py  (FastAPI :8585)               │
│  ├── Exposed via cloudflared tunnel              │
│  ├── dashboard.fieslerfamily.com                 │
│  └── 13+ endpoints for Retool + future UI        │
│                                                  │
│  OpenClaw  (local LLM — pending Mac Mini)        │
│  ├── Ollama runtime + Qwen3/LLaMA model          │
│  ├── Handles ALL Slack channel I/O               │
│  ├── Mining Guardian posts to OpenClaw webhook   │
│  └── RAG over miner logs + knowledge.json        │
└──────────────────────────────────────────────────┘
        │
        │  Slack → #mining-guardian (private channel)
        ▼
   Operator approves or denies action
        │
        ▼
   AMS executes approved command
```

---

## Slack Approval Flow

### Current Architecture (Polling — active path)
The listener polls Slack every 5 seconds using `conversations.replies` — no Socket Mode, no webhooks, no tunnel required. Simple and reliable.

```
mining_guardian.py → posts scan to #mining-guardian → saves thread_ts to pending_approvals
slack_listener.py  → polls every 5s → finds APPROVE/DENY → executes via AMS → logs audit
```

### Why Polling (not Socket Mode)
- `#mining-guardian` is a **private channel** — requires `groups:history` scope
- Socket Mode event delivery was unreliable across multiple fresh app installs
- Polling confirmed working: token reads channel successfully (`conversations.history → True`)
- Up to 5-second delay on approval — acceptable for mining fleet operations

### Slack App (api.slack.com/apps — App ID: A0APJEN0GGN)
**Bot Token Scopes required:**
- `channels:history`, `channels:read`, `groups:history` ← critical for private channel
- `chat:write`, `chat:write.public`, `incoming-webhook`
- `reactions:read`, `reactions:write`, `users:read`

**Socket Mode:** Enabled (for future OpenClaw integration)

**Bot must be invited to #mining-guardian:**
```
/invite @Mining Guardian
```

### Future Architecture (OpenClaw — pending Mac Mini)
Once OpenClaw is installed on the Mac Mini, Mining Guardian will post to OpenClaw's Gateway webhook (`localhost:18789/hooks`) and OpenClaw will handle all Slack I/O through its own battle-tested Bolt/Socket Mode connection. No separate `slack_listener.py` needed.


---

## OpenClaw + Local LLM Integration (Pending Mac Mini)

### What OpenClaw Is
OpenClaw is a local AI agent platform that runs a Gateway process on your machine (`localhost:18789`). It handles all messaging channel integrations — Slack, Telegram, WhatsApp, etc. — so Mining Guardian doesn't need to manage its own Slack listener.

### Integration Plan
1. Install OpenClaw: `npm install -g openclaw && openclaw onboard`
2. Configure Slack channel in `~/.openclaw/openclaw.json` using existing bot/app tokens
3. Enable `hooks` in config so Mining Guardian can POST scan results to OpenClaw
4. Mining Guardian posts to `localhost:18789/hooks` → OpenClaw delivers to Slack with APPROVE/DENY buttons
5. OpenClaw receives button clicks and fires callback to Mining Guardian

### Local LLM for Log Analysis
**Architecture: RAG (Retrieval-Augmented Generation) — not fine-tuning**
- Miner logs → ChromaDB (vector embeddings)
- Current scan data → context window
- LLM reasons over retrieved log history → intelligent recommendations

**Recommended Stack:**
| Component | Choice | Why |
|---|---|---|
| Runtime | Ollama | Simple, runs as background service, HTTP API at localhost:11434 |
| Model (16GB Mac Mini) | LLaMA 3.2 8B (Q4_K_M) | Fits comfortably, fast inference |
| Model (32GB Mac Mini) | Qwen3-Coder 32B (Q4_K_M) | Best for log analysis + pattern recognition |
| Vector DB | ChromaDB | Simple Python integration, no server needed |

**OpenClaw config for Ollama:**
```json
{
  "agents": {
    "defaults": {
      "model": { "primary": "ollama/qwen3-coder:32b" }
    }
  }
}
```

---

## Retool Dashboard

Phase 1 live at: `https://robfiesler25.retool.com/apps/Mining%20Guardian`

**Connected via:** `https://dashboard.fieslerfamily.com` (Cloudflare tunnel → localhost:8585)

| Panel | Status |
|---|---|
| Total Miners / Online / Offline / Issues tiles | ✅ Live |
| Currently Flagged Miners table | ✅ Live |
| Most Flagged Miners (All Time) | ✅ Live |
| AMS Alert Summary | ✅ Live |
| Outside Temperature chart | ✅ Live |
| Scan history trend chart | 🔜 Phase 2 |
| Facility map panel | 🔜 After AMS map setup |
| Per-miner drill-down | 🔜 Phase 2 |

**To start dashboard API:**
```bash
source venv/bin/activate
export $(grep -v '^#' .env | xargs)
python dashboard_api.py
```

**Cloudflare tunnel** (must be running for Retool to connect):
```bash
cloudflared tunnel run mining-guardian
```
Tunnel config: `~/.cloudflared/config.yml`
- `slack.fieslerfamily.com` → localhost:8686 (Slack listener)
- `dashboard.fieslerfamily.com` → localhost:8585 (Dashboard API)

---

## morning.sh (Daily Briefing)

Cron job fires at 7am daily, logs to `~/morning-log.txt`.

**Contents:** Bitcoin price (Coinbase API), system stats, network check, parallel miner subnet scan, Mining Guardian last scan summary, Slack post to #mining-guardian.

**Sleep fix:** `caffeinate -i -w $$` added — prevents Mac from sleeping during cron run.

**macOS Full Disk Access required for cron:**
System Settings → Privacy & Security → Full Disk Access → add `/usr/sbin/cron`

**Cron entry:**
```
0 7 * * * /bin/zsh /Users/BigBobby/Documents/GitHub/mac-scripts/morning.sh >> /Users/BigBobby/morning-log.txt 2>&1
```


---

## Analysis Logic

### Hashrate
- **Below 90% of `maxHashrate`** → flagged, firmware restart recommended
- **0% (offline)** → flagged as critical

### Chip Temperature
| Zone | Range | Action |
|---|---|---|
| 🟢 Green | Below 76°C | Healthy |
| 🟡 Yellow | 76–85°C | Monitor |
| 🔴 Red | 86°C+ | Action required |

### Power Data Priority Rule
**Always prefer PDU outlet readings over miner-reported consumption.**
Smart PDUs measure actual AC power at the wall. Miner-reported numbers are estimates.
Fall back to miner-reported only if no PDU is assigned.

### AMS Miner Profile
Each miner runs a power profile that dictates its operating speed and power draw. Profile management is visible in AMS and accessible via `change_power_profile()`. This is intentionally out of scope for autonomous action — profile changes require operator decision.

Profile names vary by miner model. Some use descriptive names (`turbo`), others use rated specs (`440 TH/s - 5396 W`). Mining Guardian parses the spec-format names automatically to extract rated hashrate. Named profiles require a manual lookup table in `config.json`.

**Known profiles — Antminer S21EXPHyd:**
330 TH/s - 3959 W | 352 TH/s - 4238 W | 374 TH/s - 4481 W | 396 TH/s - 4787 W | 418 TH/s - 5093 W | 440 TH/s - 5396 W

**Known profiles — Teraflex AH3880:**
`turbo` = 600 TH/s (named profile — requires manual mapping)

Hashrate analysis compares actual hashrate against the **active profile's rated TH/s**, not the absolute maximum. A miner running a lower profile is healthy at that profile's rated output.

---

## Remediation Actions

| Situation | Action |
|---|---|
| Miner offline + PDU assigned | PDU power cycle — cut outlet, wait 5s, restore |
| Miner offline, no PDU | Physical visit required — flagged in Slack |
| Miner online but underperforming | Firmware restart via AMS |
| Chip temp 86°C+ | Operator chooses: restart / lower profile / raise cooling |

After any restart: logs collected immediately on boot, elevated monitoring for 3 hours.

---

## AMS Endpoint Library

All methods live on `AMSClient` in `mining_guardian.py`.

### Miner Control
| Method | Endpoint | Description |
|---|---|---|
| `change_power_profile(ids, profile)` | `POST /miners/dcs/change_overclock_config` | Change power/speed profile |
| `start_miner(ids)` | `POST /miners/dcs/start` | Start miners |
| `stop_miner(ids)` | `POST /miners/dcs/stop` | Stop miners |
| `reboot_miner(ids)` | `POST /miners/dcs/reboot` | Firmware reboot |
| `led_on(ids)` / `led_off(ids)` | `POST /miners/dcs/led_on` / `led_off` | Flash LED to locate miner |
| `pdu_power_cycle(pdu_id, outlet)` | `POST /pdus/dcs/set_control_outlet` | Cut + restore outlet power |

### Miner Data
| Method | Endpoint | Description |
|---|---|---|
| `get_miners()` | `WSS miners/list_ws` | Full fleet list with telemetry |
| `get_miner_stats(id, range)` | `POST /miner_stats/device_charts` | Hashrate/power/temp history |
| `get_miner_boards(id)` | `WSS miners/chips_ws` | Per-chip frequency (126 chips/board) |
| `get_event_history(id)` | `POST /miners/request_list` | Event history |
| `get_notifications(type, limit)` | `POST /notifications/channels` | AMS alerts |
| `get_pdu_power_by_miner(id)` | PDU outlet data | **PDU power draw takes priority over miner-reported** |

### Facility & Map
| Method | Endpoint | Description |
|---|---|---|
| `get_map_groups()` | `GET /map/groups` | Facility rows, racks, sections |
| `get_map_layout()` | `WSS map/ws` | Full spatial miner layout with physical location |
| `get_tickets()` | `GET /ticket` | Maintenance tickets |
| `create_ticket(title, desc, priority)` | `POST /ticket` | Create maintenance ticket |

### Deliberately Out of Scope
- **Pool management** — security risk
- **Miner settings** — naming/config left to AMS UI
- **Power profile changes** — operator decision only

---

## Database

SQLite at `guardian.db`.

| Table | Contents | Retention |
|---|---|---|
| `scans` | Scan summaries | Permanent |
| `miner_readings` | Per-miner telemetry per scan | Permanent |
| `miner_logs` | Raw log file content | 7-day rolling purge |
| `miner_restarts` | Restart events + elevated monitoring | Permanent |
| `ams_notifications` | AMS-generated alerts | Permanent |
| `weather_readings` | Ambient temp/humidity per scan | Permanent |
| `pending_approvals` | Pending APPROVE/DENY per scan thread | Cleared on decision |
| `action_audit_log` | Every approval/denial ever — permanent | Never expires |

### Audit Log Fields
`timestamp, date, scan_id, miner_id, ip, model, problem, action_taken, decision, approved_by, slack_user_id, notes`

---

## Configuration

`config.json` (gitignored):
```json
{
  "ams_base_url":      "https://api-staging.dev.bixbit.io/api/v1",
  "ams_email":         "env:AMS_EMAIL",
  "ams_password":      "env:AMS_PASSWORD",
  "ams_workspace_id":  "env:AMS_WORKSPACE_ID",
  "slack_webhook_url": "env:SLACK_WEBHOOK_URL",
  "dry_run":           true,
  "scan_interval_seconds": 300,
  "approval_mode":     "manual"
}
```


---

## Roadmap

### ✅ Phase 1 — Core Monitoring (Complete)
- AMS auth with auto token refresh
- Full fleet scan via WebSocket, paginated
- Hashrate % + chip temperature zone analysis
- PDU power cycle for offline miners
- Firmware restart for underperforming miners
- SQLite database — permanent scan + telemetry history
- Miner log collection with 7-day rolling purge
- AMS notification polling — 40 alerts per scan
- Weather integration (Open-Meteo, Fort Worth TX)
- Slack reporting — grouped by model, deduped
- Post-restart elevated monitoring (3 hours)
- Dashboard API — FastAPI :8585, 13+ endpoints
- Action audit log — permanent, never-expiring
- Knowledge export/combine — federated learning system
- launchd watchdog + customer setup script
- morning.sh — daily briefing cron at 7am

### 🔧 Phase 2 — Approval Flow + Dashboard (In Progress)
- [x] Slack bot posting scans to #mining-guardian
- [x] Pending approvals saved with thread timestamps
- [x] Full approval flow tested — PDU cycles and restarts execute correctly
- [x] Audit log with operator display name
- [x] Retool Phase 1 dashboard live (via cloudflared tunnel)
- [x] AMS cleanup — fleet down to 44 accurate miners
- [ ] **Polling-based Slack listener** — replace Socket Mode with 5-second poll
- [ ] Retool scan history trend chart
- [ ] Retool facility map panel (after AMS map setup)

### 🔜 Phase 3 — OpenClaw + Local LLM (This Week — Mac Mini arriving)
- [ ] Install OpenClaw on Mac Mini
- [ ] Configure Slack integration via OpenClaw (replaces slack_listener.py)
- [ ] Install Ollama + Qwen3-Coder or LLaMA 3.2 (depending on RAM)
- [ ] Wire Mining Guardian → OpenClaw webhook for scan delivery + approval
- [ ] RAG pipeline: miner logs → ChromaDB → LLM context
- [ ] Plain-English Slack summaries from LLM
- [ ] Load master_knowledge.json into LLM context

### 🔜 Phase 4 — AI Diagnosis
- [ ] Log tagging — healthy / underperforming / failed / recovered
- [ ] Predictive failure detection per miner model
- [ ] Cross-customer pattern matching via federated knowledge
- [ ] AMS map location included in all alerts
- [ ] Ticket auto-creation for physical intervention miners

### 🔜 Phase 5 — Full Fleet Control
- [ ] Automations (pending AMS access)
- [ ] Overclocking profile management per model
- [ ] Container monitoring (immersion + hydro)
- [ ] Firmware version drift detection
- [ ] React dashboard (white-label, customer-facing)

### 🔜 Phase 6 — Multi-Customer Platform
- [ ] Packaged Mac Mini installer — one script, guided setup
- [ ] Central management console — all customer sites
- [ ] White-labeled customer portal

---

## Mac Mini Deployment

```bash
git clone https://github.com/robertfiesler-spec/Mining-Gaurdian.git
cd "Mining Gaurdian"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in credentials
export $(grep -v '^#' .env | xargs) && python mining_guardian.py

# Install watchdog
cp com.bixbit.mining-guardian.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.bixbit.mining-guardian.plist

# Install OpenClaw
npm install -g openclaw
openclaw onboard
```

---

## Running

```bash
# Single scan
source venv/bin/activate
export $(grep -v '^#' .env | xargs) && python mining_guardian.py

# Dashboard API (required for Retool)
source venv/bin/activate && python dashboard_api.py

# Cloudflare tunnel (required for Retool)
cloudflared tunnel run mining-guardian

# Slack listener (polling mode — coming next)
source venv/bin/activate
export $(grep -v '^#' .env | xargs) && python slack_listener.py
```

---

*Built by Rob Fiesler — BiXBiT USA CTO*

---

## AMS Facility Map

Physical layout of the BiXBiT Fort Worth facility as mapped in AMS (`staging-ui.dev.bixbit.io/map`).

| Rack | Total Slots | Miners Placed | Cooling Type |
|---|---|---|---|
| 2U | 20 | 2 | Hydro |
| BITMAIN | 18 | 2 | Hydro (1 slot currently won't accept placement) |
| IMMERSION | 20 | 2 | Immersion |

**38 miners currently show `N/A` for map location** — AMS map population is pending.

Map position format: `Row N, Col N` — available via `get_map_layout()` WSS endpoint.
Every Slack alert must include the miner's map location when available.
Map has three visualization modes: Temperature, Hashrate, Power.

---

## AMS Miner Data Available Per Miner

| Tab | Data | Mining Guardian Usage |
|---|---|---|
| Overview | Hashrate, temp, PDU kW, profile, fans, PSU | Per-scan telemetry |
| Statistic | 24h/week/month hashrate + consumption + temp charts | LLM trend analysis |
| Boards | Per-chip frequency, temp, voltage (3 boards × ~160 chips) | LLM deep diagnostics |
| Events | Command history with Pending/Success/Error status | Action confirmation |
| Logs | cgminer.conf, autotune profile, power calibration | LLM config context |

### PDU Power Data
Each miner overview shows real-time PDU outlet reading (e.g. `PDU #164/3 — 5.65 kW`) with a toggle slider for manual outlet control. PDU reading is the authoritative power source — always preferred over miner-reported consumption.

### Profile Data
Profile is shown in the miner overview firmware section and in the Overclock modal. Format varies by model:
- Spec format (auto-parseable): `440 TH/s - 5396 W` — Mining Guardian extracts rated TH/s from the name
- Named format (manual mapping required): `turbo` = 600 TH/s on Teraflex AH3880

Hashrate analysis compares actual TH/s against the **active profile's rated TH/s**, not absolute max.

### Known Profile Maps

**Antminer S21EXPHyd** (auto-parsed from name):
`330 TH/s - 3959 W` | `352 TH/s - 4238 W` | `374 TH/s - 4481 W` | `396 TH/s - 4787 W` | `418 TH/s - 5093 W` | `440 TH/s - 5396 W`

**Teraflex AH3880** (named — requires manual config mapping):
`turbo` = 600 TH/s

*Additional model profiles to be defined in config.json as fleet is documented.*
