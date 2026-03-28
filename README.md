# Mining Guardian

**Autonomous fleet monitoring and remediation system for Bitcoin mining operations.**

Mining Guardian runs on a local Mac Mini connected directly to the mining network. It connects to the BiXBiT AMS platform via authenticated WebSocket and REST API, scans every miner in the fleet every 5 minutes, and delivers actionable alerts to the operator via Slack. A local LLM (OpenClaw) provides plain-English diagnosis and decision support.

Humans stay in the loop on all remediation actions. Mining Guardian detects, explains, and recommends — operators approve.

---

## Current Status — March 2026

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
| OpenClaw / local LLM | 🔜 Mac Mini setup |
| Retool dashboard | ✅ Phase 1 live |
| Automations | 🔜 Pending AMS access |
| Facility map integration | 🔜 Monday setup |

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
│  ├── Scans 53 miners every 5 min                 │
│  ├── Hashrate % + chip temp analysis             │
│  ├── PDU cycle / firmware restart logic          │
│  ├── Miner log collection + 7-day purge          │
│  ├── AMS notification polling (40/scan)          │
│  ├── Weather data (Open-Meteo, Fort Worth TX)    │
│  ├── SQLite DB — all scan + telemetry history    │
│  └── Sends findings to OpenClaw + Slack          │
│                                                  │
│  dashboard_api.py  (FastAPI :8585)               │
│  ├── /fleet/latest — current scan status         │
│  ├── /fleet/history — scan history               │
│  ├── /miners/flagged — flagged miners            │
│  ├── /miners/most_flagged — trouble list         │
│  ├── /miners/{id}/history — miner telemetry      │
│  ├── /miners/{id}/logs — collected log files     │
│  ├── /temps/hot_miners — warm/hot miners         │
│  ├── /temps/history — fleet temp trends          │
│  ├── /weather/history — ambient conditions       │
│  ├── /notifications/recent — AMS alerts          │
│  ├── /notifications/summary — alert counts       │
│  └── /restarts/recent — restart events           │
│                                                  │
│  OpenClaw  (local LLM — pending Mac Mini)        │
│  └── Interprets logs + recommends actions        │
└──────────────────────────────────────────────────┘
        │
        │  Slack → #mining-guardian
        ▼
   Operator approves or denies action
        │
        ▼
   AMS executes approved command
```

---

## How It Works

1. **Auth** — Cookie-based JWT login. User token → workspace-scoped token → auto-refreshed before expiry
2. **Scan** — Fetches full miner list via `miners/list_ws` WebSocket with automatic pagination
3. **Evaluate** — Each miner analyzed for hashrate % of max and chip temperature zone
4. **Notify AMS** — Pulls 40 AMS-generated alerts per scan; deduped against own findings
5. **Log** — Downloads log files from flagged miners; stores in SQLite with 7-day rolling purge
6. **Report** — Clean terminal output + grouped Slack message with human-readable alerts
7. **API** — Dashboard API serves all data as JSON for Retool and future React dashboard

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

### Sensor Errors
- Negative temp readings flagged as **sensor error** — not treated as real values

### Power Data Priority Rule
**Always prefer PDU outlet readings over miner-reported consumption.**
Smart PDUs measure actual AC power at the wall. Miner-reported numbers are estimates.
Fall back to miner-reported only if no PDU is assigned.

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
| `change_power_profile(ids, profile)` | `POST /miners/dcs/change_overclock_config` | Change power/overclock profile |
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
| `get_event_history(id)` | `POST /miners/request_list` | Event history (miners AND PDUs) |
| `get_notifications(type, limit)` | `POST /notifications/channels` | AMS alerts |
| `get_notifications_count()` | `GET /notifications/count` | Unread count |
| `delete_notification(id)` | `DELETE /notifications/channels/{id}` | Dismiss alert |

### Logs
| Method | Endpoint | Description |
|---|---|---|
| `trigger_log_export(id)` | `POST /log/export` | Generate log zip on miner |
| `get_log_list(id)` | `POST /log/get_log_list` | List available logs |
| `download_log(id, filename)` | `POST /log/download` | Download log zip |
| `collect_miner_logs(id)` | — | Download + extract 3 key log files |

### PDU
| Method | Endpoint | Description |
|---|---|---|
| `get_pdu_detail(pdu_id)` | `WSS pdus/ws` | Per-outlet voltage, current, power |
| `get_pdu_stats()` | `WSS pdus/statistic` | Fleet-wide PDU power summary |

### Facility & Tickets
| Method | Endpoint | Description |
|---|---|---|
| `get_map_groups()` | `GET /map/groups` | Facility rows, racks, sections |
| `get_map_layout()` | `WSS map/ws` | Full spatial miner layout |
| `get_tickets()` | `GET /ticket` | Maintenance ticket list |
| `create_ticket(title, desc, priority)` | `POST /ticket` | Create maintenance ticket |
| `get_ticket_statuses()` | `GET /ticket/status` | Available ticket statuses |

### Deliberately Out of Scope
- **Pool management** — security risk, not touched by Mining Guardian
- **Miner settings** — naming/config left to AMS UI


---

## Dashboard API

FastAPI server on `http://localhost:8585`. Start it:
```bash
source venv/bin/activate
python dashboard_api.py
```
Interactive docs: `http://localhost:8585/docs`

---

## Database

SQLite at `guardian.db` in the repo folder.

| Table | Contents | Retention |
|---|---|---|
| `scans` | Scan summaries | Permanent |
| `miner_readings` | Per-miner telemetry per scan | Permanent |
| `miner_logs` | Raw log file content | 7-day rolling purge |
| `miner_restarts` | Restart events + elevated monitoring | Permanent |
| `ams_notifications` | AMS-generated alerts | Permanent |
| `weather_readings` | Ambient temp/humidity per scan | Permanent |

### Useful Queries

```sql
-- Scan history
SELECT scanned_at, total_miners, online, offline, issues
FROM scans ORDER BY id DESC;

-- Most flagged miners
SELECT miner_id, ip, model, action, COUNT(*) as times_flagged
FROM miner_readings WHERE action IS NOT NULL
GROUP BY miner_id ORDER BY times_flagged DESC;

-- AMS notification breakdown
SELECT key, alert_level, COUNT(*) as count
FROM ams_notifications
GROUP BY key, alert_level ORDER BY count DESC;

-- Miners in elevated monitoring
SELECT miner_id, ip, model, restarted_at, elevated_until
FROM miner_restarts WHERE elevated_until > datetime('now');
```

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

## Running

```bash
# Single scan
source venv/bin/activate
export $(grep -v '^#' .env | xargs) && python mining_guardian.py

# Dashboard API
source venv/bin/activate
python dashboard_api.py
```

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
launchctl list | grep mining-guardian
```

---

## Monday Action Items (2026-03-30)

**At the facility:**
- [ ] Physically verify PDU connections for 25 offline miners
- [ ] Update AMS PDU assignments for all verified connections
- [ ] Set up facility map in AMS (miners get location data automatically)
- [ ] Investigate miner 53475 — S21EXPHyd, online but only 1–3% hashrate
- [ ] Re-run Mining Guardian after PDU + map setup

**Mac Mini setup:**
- [ ] Install OpenClaw + local LLM
- [ ] Configure OpenClaw webhook in `config.json`
- [ ] Deploy Mining Guardian via `setup.sh`
- [ ] Install launchd watchdog


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
- AMS notification polling — 40 alerts per scan, human-readable
- Weather integration (Open-Meteo, Fort Worth TX)
- Slack reporting — grouped by model, deduped, no repetition
- Post-restart elevated monitoring (3 hours)
- Dashboard API — FastAPI server on :8585 with 13 endpoints
- DB Browser for SQLite — visual database inspection
- launchd watchdog + customer setup script

### 🔧 Phase 2 — Dashboard (In Progress)

**Retool Dashboard — Phase 2a (live, internal)**
- [x] Connected to live guardian.db via FastAPI + cloudflared tunnel
- [x] 4 stat tiles — Total Miners, Online, Offline, Issues
- [x] Currently Flagged Miners table — 31 results, live
- [x] Most Flagged Miners (All Time) trouble list
- [x] AMS Alert Summary — 5 alert types with counts
- [x] Outside Temperature history chart
- [ ] Facility map integration (Monday after AMS map setup)
- [ ] Permanent tunnel solution (cloudflared named tunnel or Mac Mini local hosting)
- [ ] Scan history chart — online/offline trend over time

**React Dashboard — Phase 2b (white-label, customer-facing)**
- [ ] Fully owned by BiXBiT, no Retool dependency
- [ ] Multi-customer support
- [ ] AI predictions panel

### 🔜 Phase 3 — AI Diagnosis
- [ ] OpenClaw webhook integration (pending Mac Mini)
- [ ] Log tagging — healthy / underperforming / failed / recovered
- [ ] Active LLM diagnosis for flagged miners
- [ ] Predictive failure detection — early warning patterns per model
- [ ] Plain-English Slack summaries from LLM

### 🔜 Phase 4 — Full Fleet Control
- [ ] Automations (pending AMS access)
- [ ] Ticket auto-creation for physical intervention miners
- [ ] Overclocking profile management per model
- [ ] Container monitoring (immersion + hydro)
- [ ] Firmware version drift detection

### 🔜 Phase 5 — Multi-Customer Platform
- [ ] Packaged Mac Mini installer — one script, guided setup
- [ ] Central management console — all customer sites
- [ ] White-labeled customer portal

---

*Built by Rob Fiesler — BiXBiT USA CTO*
