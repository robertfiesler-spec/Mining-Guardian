# Mining Guardian

**Autonomous fleet monitoring and remediation system for bitcoin mining operations.**

Mining Guardian runs on a local Mac Mini connected directly to the mining network. It connects to the BiXBiT AMS via authenticated WebSocket and REST API, scans every miner in the fleet for performance and temperature issues, and delivers actionable recommendations to the operator via Slack — with a local LLM (OpenClaw) providing plain-English interpretation and decision support.

Humans stay in the loop on all remediation actions. Mining Guardian detects, explains, and recommends — operators approve.

---

## System Architecture

```
BiXBiT AMS (cloud)
        │
        │  WebSocket + REST (cookie-based JWT auth)
        ▼
┌─────────────────────────────────────┐
│         Mac Mini (local network)    │
│                                     │
│  Mining Guardian (Python daemon)    │
│  ├── Scans all miners every N min   │
│  ├── Evaluates hashrate & temps     │
│  ├── Recommends PDU cycle or reboot │
│  ├── Logs every scan to disk        │
│  └── Sends findings to OpenClaw     │
│                                     │
│  OpenClaw (local LLM)               │
│  └── Interprets findings            │
│      Drafts plain-English summaries │
│      Routes recommendations → Slack │
└─────────────────────────────────────┘
        │
        │  Slack notifications
        ▼
   Operator (Rob) — approves or denies actions
        │
        ▼
   AMS executes approved command
```

---

## How It Works

1. **Auth** — Cookie-based JWT login to BiXBiT AMS. User token → workspace-scoped token → auto-refreshed before expiry
2. **Scan** — Fetches full miner list via WebSocket (`miners/list_ws`) with automatic pagination across all pages
3. **Evaluate** — Each miner is analyzed for hashrate % of max and chip temperature zone
4. **Report** — Clean terminal report groups miners into: PDU power cycle needed, firmware restart needed, temp monitor, and healthy
5. **Notify** — Findings sent to OpenClaw webhook; local LLM interprets and posts to Slack
6. **Remediate** — Operator approves action via Slack; Mining Guardian executes via AMS API

---

## Performance & Temperature Logic

### Hashrate
- **Below 90% of `maxHashrate`** → flagged, firmware restart recommended
- **0% (offline)** → flagged as critical

### Chip Temperature
| Zone | Range | Action |
|------|-------|--------|
| 🟢 Green | Below 76°C | Healthy — no action |
| 🟡 Yellow | 76–85°C | Monitor |
| 🔴 Red | 86°C+ | Operator chooses: restart / lower power / raise cooling |

### Sensor Errors
- Negative temp readings (e.g. `-64°C`) are flagged as **sensor error** — not treated as real values

---

## Remediation Actions

Mining Guardian distinguishes between two types of restart based on miner state:

| Situation | Recommended Action |
|---|---|
| Miner **offline** + PDU assigned | **PDU power cycle** — cut outlet power, wait 5s, restore |
| Miner **offline**, no PDU assigned | **Firmware restart** via AMS |
| Miner **online but underperforming** | **Firmware restart** via AMS |
| Chip temp **86°C+** | Operator chooses: restart / lower power profile / raise cooling |

PDU outlet control uses `POST /pdus/dcs/set_control_outlet` with the miner's `pduOutlet.pduID` and `pduOutlet.outletIndex` pulled directly from live miner data.

---

## Deployment Target

Mining Guardian is designed to run as a persistent daemon on a **local Mac Mini** inside the mining facility:

- Direct local network access to miners — no cloud dependency for core operations
- Paired with **OpenClaw** (local LLM) for intelligent finding interpretation
- Slack integration for remote operator visibility and approval
- Scan results logged to disk for historical trending

---

## Mac Mini Deployment (Production)

This is the intended production setup — Mining Guardian running headlessly on a local Mac Mini inside the mining facility.

### Prerequisites
- Mac Mini connected to the mining network
- Python 3.9+ installed
- Git installed
- `.env` file with credentials in the repo folder

### Step 1 — Clone the repo
```bash
git clone https://github.com/robertfiesler-spec/Mining-Gaurdian.git
cd "Mining Gaurdian"
```

### Step 2 — Create and activate the virtual environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install requests websocket-client
```

### Step 3 — Create your credentials file
```bash
cp .env.example .env
```
Edit `.env` and fill in your AMS email, password, and workspace ID.

### Step 4 — Create your config file
```bash
cp config.example.json config.json
```
Edit `config.json` if needed (base URL, dry_run setting, scan interval, etc.).

### Step 5 — Test a single scan first
```bash
source venv/bin/activate
export $(grep -v '^#' .env | xargs) && python mining_guardian.py
```
Verify the report looks correct before enabling the watchdog.

### Step 6 — Install the launchd watchdog
```bash
cp com.bixbit.mining-guardian.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.bixbit.mining-guardian.plist
```

### Step 7 — Verify it's running
```bash
launchctl list | grep mining-guardian
```
You should see a line with `com.bixbit.mining-guardian`. If the second column shows `0` it's running clean. Any other number is an exit code — check the error log.

### Checking logs
```bash
# Today's scan log
cat "/Users/BigBobby/Documents/GitHub/Mining Gaurdian/logs/guardian_$(date +%Y-%m-%d).log"

# launchd startup errors
cat "/Users/BigBobby/Documents/GitHub/Mining Gaurdian/logs/launchd_stderr.log"
```

### Stopping the watchdog
```bash
launchctl unload ~/Library/LaunchAgents/com.bixbit.mining-guardian.plist
```

### Removing it completely
```bash
launchctl unload ~/Library/LaunchAgents/com.bixbit.mining-guardian.plist
rm ~/Library/LaunchAgents/com.bixbit.mining-guardian.plist
```

---

## Configuration

On first run, `config.example.json` is generated. Copy and edit it:

```bash
cp config.example.json config.json
```

Key fields:

```json
{
  "ams_base_url": "https://api-staging.dev.bixbit.io/api/v1",
  "ams_email":        "env:AMS_EMAIL",
  "ams_password":     "env:AMS_PASSWORD",
  "ams_workspace_id": "env:AMS_WORKSPACE_ID",
  "dry_run": true,
  "scan_interval_seconds": 300,
  "approval_mode": "manual"
}
```

**Secret management** — prefix any value with `env:` to pull it from the environment:

```bash
export AMS_EMAIL=your@email.com
export AMS_PASSWORD=yourpassword
export AMS_WORKSPACE_ID=119
```

Or store in a `.env` file (gitignored) and load with:

```bash
export $(grep -v '^#' .env | xargs) && python mining_guardian.py
```

---

## Running

Single scan (prints report to terminal):

```bash
python mining_guardian.py
```

Continuous loop:

```python
from mining_guardian import GuardianConfig, MiningGuardian
config = GuardianConfig.from_file("config.json")
MiningGuardian(config).loop()
```

---

## Repository Structure

```
Mining Gaurdian/
├── mining_guardian.py      # Core daemon — AMS client, analysis engine, report printer
├── ams_auth_test.py        # Standalone auth + WebSocket proof-of-concept
├── config.json             # Live config (gitignored)
├── config.example.json     # Auto-generated reference config
├── .env                    # Credentials (gitignored)
├── .env.example            # Credential template
├── .gitignore
└── README.md
```

---

## Safety Model

- `dry_run: true` is the default — no changes are sent to miners until explicitly disabled
- All remediation actions require operator approval via Slack before execution
- PDU power cycling is a destructive action — always confirmed before execution
- The local LLM provides recommendations only — it does not execute actions autonomously

---

## Full AMS API Capability Map

Mining Guardian has owner-level access to the full BiXBiT AMS API. Below is everything available — current usage noted.

### Miners
| Permission | Description | Status |
|---|---|---|
| `minerShow` | Read miner list and telemetry | ✅ In use |
| `minerStart` / `minerStop` | Start and stop miners | 🔜 Planned |
| `minerReboot` | Firmware restart | 🔜 Planned |
| `minerChangeSettings` | Change power profile, overclocking, config | 🔜 Planned |
| `minerOverclock` | Overclocking controls | 🔜 Planned |
| `minerChangePool` | Switch mining pool | 🔜 Planned |
| `minerChangeFee` | Change fee settings | 🔜 Planned |
| `minerChangePassword` | Change miner password | 🔜 Planned |
| `minerChangeNetwork` | Change network config | 🔜 Planned |
| `minerLed` | Flash LED to physically locate a miner | 🔜 Planned |
| `minerLogsShow` / `minerExportLogs` | Pull and download miner logs | 🔜 Critical — AI diagnosis |
| `minerEventsShow` | Per-miner event history | 🔜 Critical — AI diagnosis |
| `minerExport` | Export miner data | 🔜 Planned |
| `minerStartGenerateProfile` / `minerStopGenerateProfile` | Auto power profile generation | 🔜 Planned |
| `minerStatsShow` | Per-miner stats | 🔜 Planned |

### PDUs
| Permission | Description | Status |
|---|---|---|
| `pduShow` | Read PDU list and outlet status | 🔜 Planned |
| `pduStatsShow` | PDU power consumption stats | 🔜 Planned |
| `pduEventShow` | PDU event history | 🔜 Planned |
| `pduCmdToggleOutlets` | Power cycle outlets | ✅ In use |
| `pduAttachMiner` / `pduDetachMiner` | Manage PDU-miner assignments | 🔜 Planned |

### Pools
| Permission | Description | Status |
|---|---|---|
| `poolShow` / `poolCreate` / `poolEdit` / `poolDelete` | Full pool management | 🔜 Dashboard |

### Automations
| Permission | Description | Status |
|---|---|---|
| `automatizationShow/Create/Edit/Delete` | Create and manage AMS automation rules | 🔜 Dashboard |

### Maps
| Permission | Description | Status |
|---|---|---|
| `mapShow` | View facility map | 🔜 Dashboard |
| `mapAssignMiner` / `mapUnassignMiner` | Assign miners to physical map locations | 🔜 Dashboard |
| `mapImport/ExportLayout` | Import/export facility layouts | 🔜 Dashboard |

### Tickets
| Permission | Description | Status |
|---|---|---|
| `ticketShow/Create/Edit/Delete` | Full maintenance ticket system | 🔜 Dashboard |
| `ticketCommentCreate/Edit/Delete` | Ticket comments | 🔜 Dashboard |

### Teams & Notifications
| Permission | Description | Status |
|---|---|---|
| `teamShow/Invite/Detach` | Manage team members | 🔜 Dashboard |
| `notificationShow/Delete` | Fleet notifications | 🔜 Dashboard |

### Containers
| Permission | Description | Status |
|---|---|---|
| `containerShow/StatsShow/EventsShow` | Immersion/hydro container monitoring | 🔜 Planned |
| `containerChangeSettings/ExecuteCmd` | Container control commands | 🔜 Planned |

---

## AI Diagnosis & Predictive Failure Detection

This is the core intelligence layer of Mining Guardian — the feature that separates it from a simple monitoring tool.

### How It Works

Mining Guardian continuously downloads miner logs from the AMS API and feeds them to the local LLM (OpenClaw). Over time the LLM builds a pattern library:

```
Phase 1 — Data Collection
Every scan cycle:
  ├── Download logs for every miner (healthy + unhealthy)
  ├── Store raw logs in SQLite with miner ID, timestamp, status
  └── Tag logs: healthy / underperforming / failed / recovered

Phase 2 — Pattern Learning
Local LLM analyzes the log database:
  ├── "What do healthy S19JPro logs look like?"
  ├── "What patterns appear in logs 24-48 hours before a failure?"
  ├── "Which chip error codes correlate with hashrate drops?"
  └── Builds a model per miner type (S19, S21, AH3880, etc.)

Phase 3 — Active Diagnosis
When a miner underperforms:
  ├── Mining Guardian pulls that miner's recent logs
  ├── Sends logs + pattern library context to LLM
  ├── LLM compares against known failure signatures
  └── Returns: root cause assessment + recommended action

Phase 4 — Predictive Alerts
For every online miner each scan:
  ├── LLM scores current log patterns against failure signatures
  ├── Flags miners showing early warning signs
  └── Posts to Slack: "Miner 53483 showing chip error pattern
      consistent with pre-failure state on 3 other S19JPros.
      Recommend inspection within 48 hours."
```

### What Miner Logs Contain
- Per-chip error rates and error codes
- Temperature readings at chip level (not just board averages)
- Pool connection events — drops, latency, reconnects
- Fan speed history and anomalies
- Restart and crash events with timestamps
- Power fluctuation records
- Firmware error codes

### Log Collection Strategy
- **Download frequency:** Every scan cycle for flagged miners, every 6 hours for healthy miners
- **Storage:** Raw logs in SQLite `miner_logs` table, tagged by miner ID, model, and health status
- **Retention:** 90 days rolling window — enough history to train on without unbounded disk growth
- **LLM context:** Logs sent to OpenClaw in structured batches, not raw dumps

### Diagnosis Workflow
```
Miner flagged as underperforming
        ↓
Mining Guardian pulls last 24h of logs
        ↓
Sends to OpenClaw: "Diagnose this miner.
Here are its logs. Here are examples of
healthy logs from same model. What's wrong
and what should we do?"
        ↓
LLM returns structured diagnosis:
  - Likely root cause
  - Confidence level
  - Recommended action (restart / profile change / physical inspection)
  - Urgency (immediate / 24h / 7 days)
        ↓
Posted to #mining-guardian in Slack
Operator approves recommended action
```

---

## Roadmap

### Phase 1 — Core Monitoring (✅ Complete)
- [x] Cookie-based AMS authentication with auto token refresh
- [x] Full fleet scan via WebSocket with automatic pagination
- [x] Hashrate % of max threshold monitoring (90% floor)
- [x] Chip temperature zone monitoring (green/yellow/red)
- [x] PDU power cycle for offline miners
- [x] Firmware restart for underperforming online miners
- [x] SQLite database — scan history and per-miner telemetry
- [x] Daily rotating log file — headless Mac Mini ready
- [x] Slack integration — live fleet alerts to #mining-guardian
- [x] Morning briefing — 7am fleet summary posted to Slack via cron
- [x] launchd watchdog — auto-start and crash recovery on boot
- [x] Customer setup script — one command deploys to any Mac Mini

### Phase 2 — AI Diagnosis (🔜 Next)
- [ ] Miner log downloader — pull and store logs per miner per cycle
- [ ] Log tagging system — healthy / underperforming / failed / recovered
- [ ] OpenClaw integration — send logs to local LLM for analysis
- [ ] Active diagnosis — LLM diagnoses underperforming miners from logs
- [ ] Pattern library — LLM builds failure signatures per miner model
- [ ] Predictive alerts — early warning before miners fail

### Phase 3 — Dashboard (🔜 Planned)
- [ ] **Retool dashboard** (Phase 3a — fast, internal)
  - Live fleet status with color-coded miner health
  - Historical hashrate and temperature charts per miner
  - Settings management — rules, thresholds, dry run toggle
  - Alert history and action log
- [ ] **Custom React dashboard** (Phase 3b — white-label, customer-facing)
  - Fully owned by BiXBiT, no monthly fees
  - Multi-customer support — switch between sites
  - AI predictions panel — LLM insights and trend analysis
  - Professional branded UI per customer

### Phase 4 — Full Fleet Control (🔜 Planned)
- [ ] Pool management — switch, create, edit pools from dashboard
- [ ] Overclocking controls — profile management per miner model
- [ ] Automation rules — create AMS automations from Mining Guardian
- [ ] Facility map — visual miner layout with status overlay
- [ ] Maintenance tickets — create and track issues per miner
- [ ] Container monitoring — immersion and hydro unit support
- [ ] Firmware version drift detection across fleet
- [ ] LED locator — flash miner LED from dashboard for physical identification

### Phase 5 — Multi-Customer Platform (🔜 Planned)
- [ ] Packaged Mac Mini installer — one script sets up everything
  - Mining Guardian daemon
  - OpenClaw + local LLM
  - Slack workspace integration
  - Customer-specific config
  - Guided setup wizard (no technical knowledge required)
- [ ] Central management console — BiXBiT sees all customer sites
- [ ] White-labeled customer portal
- [ ] Automated onboarding flow

---

---

*Built by Rob Fiesler — BiXBiT USA*
