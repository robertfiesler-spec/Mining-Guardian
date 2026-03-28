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

## Roadmap

- [ ] **Mining Guardian Dashboard — Phase 1 (Retool)**
  - Fast, professional internal dashboard — no heavy frontend build required
  - Live fleet status with charts and color-coded miner health
  - Per-miner historical data — hashrate trends, temp history, uptime over time
  - Settings management — change rules, thresholds, dry run toggle from the UI
  - Alert history — full log of everything flagged and what action was taken
- [ ] **Mining Guardian Dashboard — Phase 2 (Custom React app)**
  - Fully owned by BiXBiT — no monthly fees, white-label ready for customers
  - Multi-customer support — switch between customer sites from one interface
  - AI predictions panel — local LLM learns fleet patterns, surfaces failure warnings
  - Professional branded UI deployable per customer
- [x] SQLite database — scan history and per-miner telemetry logging
- [x] Daily log file — headless Mac Mini operation ready
- [x] Deprecation warnings fixed — timezone-aware datetime throughout
- [x] launchd watchdog — auto-start and crash recovery on Mac Mini boot
- [x] Customer setup script — one command (`zsh setup.sh`) deploys to any new Mac Mini
- [ ] OpenClaw webhook — structured findings to local LLM (built, pending OpenClaw setup)
- [x] Slack integration — live fleet alerts posted to #mining-guardian after every scan
- [x] Morning briefing — 7am fleet summary posted to Slack automatically via cron
- [ ] Predictive failure detection — trending historical temp and hashrate data
- [ ] Firmware version drift detection across fleet

---

*Built by Rob Fiesler — BiXBiT USA*
