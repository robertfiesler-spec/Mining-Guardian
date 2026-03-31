# Mining Guardian

**Autonomous fleet monitoring and remediation system for Bitcoin mining operations.**

Mining Guardian runs on a local Mac Mini connected to the mining network. It connects
to the BiXBiT AMS platform via authenticated WebSocket and REST API, scans every miner
in the fleet, and delivers actionable alerts to the operator via Slack. A local LLM
(via OpenClaw) provides plain-English diagnosis and decision support.

Humans stay in the loop on all remediation actions. Mining Guardian detects, explains,
and recommends — operators approve.

---

## Current Status — March 31, 2026

| Component | Status |
|---|---|
| AMS authentication (cookie JWT) | ✅ Live |
| Full fleet scan via WebSocket | ✅ Live |
| Three-tier hashrate evaluation | ✅ Live |
| Dead hashboard detection | ✅ Live |
| AMS false-offline verification (TCP:4028) | ✅ Live |
| Firmware-aware miner routing | ✅ Live |
| PDU power cycle | ✅ Built |
| Firmware restart | ✅ Built |
| Dead board restart + log compare flow | ✅ Built |
| Post-restart common_status stability polling | ✅ Built |
| SQLite database (27-field schema) | ✅ Live |
| Miner log collection | ✅ Live |
| Weather data per scan | ✅ Live |
| AMS notifications (40/scan) | ✅ Live |
| Slack reporting | ✅ Live |
| Dashboard API (FastAPI :8585) | ✅ Live |
| Retool dashboard Phase 1 | ✅ Live via cloudflared tunnel |
| Action audit log | ✅ Live |
| Knowledge export / combine | ✅ Built |
| miner_specs.json (35+ models) | ✅ Built |
| PDU clients (163 @ .15, 164 @ .16) | ✅ Live |
| Immersion tank client (B100 @ .20) | ✅ Live |
| Facility monitor (all 3 infra sources) | ✅ Live in scan report |
| Auradine AH3880 direct client (reference) | ✅ Documented |
| BiXBiT direct API docs (port 4029 fallback) | ✅ Documented |
| morning.sh daily briefing | ✅ Live (cron 7am) |
| OpenClaw / local LLM | 🔜 Mac Mini arriving this week |
| Profile map (config.json) | 🔜 Pending walk-through session |
| Second S21 EXP Hyd added to AMS | 🔜 Pending Rob (IP: .26) |


---

## Fleet — USA 188 (192.168.188.x)

### Outside Container (own power — no PDU access)
- **39 × Antminer S19JPro** — all on BiXBiT firmware, immersion cooled
- Monitored via AMS only. TCP:4028 used for false-offline verification.

### Warehouse / R&D Center

| Device | Count | IP | PDU | Cooling | AMS |
|---|---|---|---|---|---|
| Auradine AH3880 | 2 | .27, .28 | PDU 163 outlets 3+4 | Hydro | ✅ |
| Antminer S21 EXP Hyd | 1 | .25 | PDU 164 outlet 3 | Hydro | ✅ |
| Antminer S21 EXP Hyd | 1 | .26 | PDU 164 outlet 4 | Hydro | ⏳ Add to AMS |
| Antminer S21 Imm | 2 | .22, .23 | Tank B100 ports 19+20 | Immersion | ✅ |

**Total fleet in AMS: 48 miners** (49 once second S21 EXP Hyd is added)

### Infrastructure

| Device | IP | Client | Data |
|---|---|---|---|
| BiXBiT 2U+PDU (rack PDU) | 192.168.188.15 | pdu_client.py | L1-3 V/A/kW, per-outlet kW |
| BiXBiT Bitmain PDU (shoebox rack) | 192.168.188.16 | pdu_client.py | L1-3 V/A/kW, per-outlet kW |
| Fog Hashing Elite 1 (immersion tank) | 192.168.188.20 | immersion_client.py | Fluid temps, pump, per-port kW |

**PDU power readings always take priority over miner-reported consumption.**

---

## Firmware Routing

Mining Guardian uses firmware-aware evaluation. The correct API path depends on what firmware the miner is running.

| Firmware | Detection | Primary Path | Direct API |
|---|---|---|---|
| BiXBiT (Bitmain) | `firmwareManufacturer == "BiXBiT"` or profile string present | AMS → all commands | Port 4029 fallback (docs/BIXBIT_DIRECT_API.md) |
| Stock Antminer | `firmwareManufacturer == "Stock"` | AMS → all commands | CGMiner TCP:4028 (read-only) |
| Auradine | `firmwareManufacturer == "Auradine"` | AMS → all commands | Port 8443 fallback (AURADINE_API.md) |
| Unknown | Empty firmware field | AMS + Tier 3 baseline learning | TCP:4028 verify only |

**Architecture rule: ALL commands go through AMS first. Direct APIs are fallback only.**
Reason: AMS provides audit log, single auth layer, and network simplicity.
Mac Mini only needs LAN access to AMS — not direct IP to each miner.


---

## Three-Tier Hashrate Evaluation

Mining Guardian evaluates every miner against the most accurate baseline available.

### Tier 1 — BiXBiT Profile (live from AMS)
For miners on BiXBiT firmware. Calls AMS `miner_config` to get `profilesList`,
parses `currentProfile` string (e.g. `"144 TH/s - ~4913 W"`) stripping the `~`,
and compares actual hashrate against that profile's rated TH/s.
Covers: 36 BiXBiT S19JPros + 2 Auradine AH3880s (turbo = 600 TH/s).

### Tier 2 — Published Spec Lookup
For miners on Stock/Auradine firmware with a known model.
Looks up `miner_specs.json` by AMS model code.
Covers: Stock S19JPros at 104 TH/s, plus 35+ models from Bitmain, Bitdeer, MicroBT, Canaan.

### Tier 3 — Learned Baseline
For miners with unrecognized models or no published spec.
72-hour learning window, minimum 36 samples, ±10% tolerance band.
During learning window: still monitors temps, boards, and offline status — just not hashrate drift.

**Evaluation threshold: 90% of rated TH/s.** Below this triggers a RESTART or RESTART_CHECK_BOARDS action.

---

## Dead Hashboard Detection

Each miner has 3 hashboards. Mining Guardian checks `chains` data from AMS per scan.

| Board State | Signature | % Output | Action |
|---|---|---|---|
| All 3 boards healthy | All chains > threshold | ~100% | No action |
| 1 board dead | 1 chain ≈ 0 MH/s | ~66% | RESTART_CHECK_BOARDS |
| 2 boards dead | 2 chains ≈ 0 MH/s | ~33% | RESTART_CHECK_BOARDS |

### RESTART_CHECK_BOARDS Flow (execute_board_restart)
1. Attempt pre-restart log collection (30s timeout — skip silently if offline)
2. Send restart via AMS
3. Phase 1: poll for miner online (up to 10 min, every 15s)
4. Phase 2: poll `common_status` via TCP:4029 for `"mining"` (primary)
   OR poll AMS minerStatus==0 + hashrate>0 (fallback if TCP unavailable)
   Require 2 consecutive stable polls. Up to 45 min.
   If `"emergency"` detected → escalate immediately.
5. Collect post-restart logs (non-blocking)
6. Compare board states before vs after
7. If board recovered → resolve, log it
8. If board still dead → create AMS ticket + Slack alert (physical inspection required)

**Pre-restart log rule applies to ALL restarts** — not just dead board cases.

---

## AMS False-Offline Detection

AMS occasionally reports a miner as offline when it's actually running (WebSocket sync lag,
recent reboot, etc.). Before taking any offline action, Mining Guardian verifies:

1. Attempt TCP connect to miner IP on port 4028
2. If port responds → miner is alive, AMS is out of sync → skip this scan cycle, no alert
3. If port does not respond → genuinely offline → proceed with action

This resolved 5 false PHYSICAL_CYCLE flags that were showing healthy miners as needing
manual intervention. Both miners at .50 and .31 were confirmed reachable despite AMS
reporting offline.

---

## Model Mismatch Handling

AMS can have a miner registered with the wrong model (e.g. miner 53476 registered as
`sealminer-a2` but is actually an S19JPro). Mining Guardian resolves this by priority:

1. If `currentProfile` parses as a valid BiXBiT profile → use profile TH/s (Tier 1), display `name` field
2. If `name` field contains model string → use that for display
3. Fall back to `shortModel` from AMS only if no profile or name available


---

## Facility Monitor

`facility_monitor.py` polls all three infrastructure devices every scan and appends
a warehouse section to the scan report.

### PDU Clients (pdu_client.py)
Auth: HMAC-SHA1 login (custom BiXBiT PDU firmware, port 80).
Data: L1/L2/L3 voltage, current, total kW, total kWh, per-outlet kW.
PDU 163 @ .15: Auradine rack — outlets 3+4 = AH3880s (~9.9 kW each)
PDU 164 @ .16: Bitmain shoebox rack — outlets 3+4 = S21EXPHyd (~5.5 kW each)

### Immersion Tank Client (immersion_client.py)
Device: Fog Hashing Elite 1 (B100) @ 192.168.188.20
Auth: None (open REST JSON API)
Data: fluid in/out temp, pump status, fluid level alarms, per-port kW, mining switch state
Ports 19+20: S21 Imm miners (~6-6.3 kW each)
Port 22: support equipment (not a miner — ~6.9 kW cooling/pump load)

### Miner → Outlet Map
```
192.168.188.27 (AH3880)      → PDU 163 outlet 3
192.168.188.28 (AH3880)      → PDU 163 outlet 4
192.168.188.25 (S21EXPHyd)   → PDU 164 outlet 3
192.168.188.26 (S21EXPHyd)   → PDU 164 outlet 4  (pending AMS ID)
192.168.188.22 (S21 Imm)     → Tank B100 port 19
192.168.188.23 (S21 Imm)     → Tank B100 port 20
```

---

## Temperature Thresholds

**Uniform across ALL cooling types (air, immersion, hydro).**
Immersion miners are overclocked and run at higher TH/s than stock, which means
they run as hot or hotter than air-cooled miners. Same thresholds apply.

| Zone | Chip Temp | Action |
|---|---|---|
| 🟢 Healthy | < 76°C | None |
| 🟡 Monitor | 76–85°C | Watch next scan |
| 🔴 Action | ≥ 86°C | Alert operator |

---

## System Architecture

```
BiXBiT AMS (cloud / staging)
        │
        │  WebSocket + REST (cookie-based JWT)
        ▼
┌──────────────────────────────────────────────────────┐
│               Mac Mini (local network)               │
│                                                      │
│  mining_guardian.py  (Python daemon)                 │
│  ├── Scans fleet every 5 min via AMS WebSocket       │
│  ├── Three-tier hashrate evaluation                  │
│  ├── Dead hashboard detection + remediation flow     │
│  ├── AMS false-offline TCP:4028 verification         │
│  ├── PDU power cycle / firmware restart via AMS      │
│  ├── Miner log collection + 7-day purge              │
│  ├── AMS notification polling (40/scan)              │
│  ├── Weather data (Open-Meteo, Fort Worth TX)        │
│  ├── SQLite DB — 27-field schema, all history        │
│  ├── FacilityMonitor — PDU 163/164 + tank B100       │
│  └── Posts findings to OpenClaw webhook              │
│                                                      │
│  facility_monitor.py                                 │
│  ├── pdu_client.py → PDU 163 @ .15, PDU 164 @ .16   │
│  └── immersion_client.py → Tank B100 @ .20           │
│                                                      │
│  hashrate_evaluation.py                              │
│  ├── MinerSpecsLoader (miner_specs.json)             │
│  └── BaselineManager (Tier 3 learning window)        │
│                                                      │
│  dashboard_api.py  (FastAPI :8585)                   │
│  ├── Exposed via cloudflared tunnel                  │
│  ├── dashboard.fieslerfamily.com                     │
│  └── 15+ endpoints for Retool                        │
│                                                      │
│  OpenClaw  (pending Mac Mini install)                │
│  ├── Handles ALL Slack I/O                           │
│  ├── Mining Guardian POSTs to localhost:18789/hooks  │
│  ├── Delivers APPROVE/DENY buttons in Slack          │
│  └── Ollama local LLM for log analysis               │
└──────────────────────────────────────────────────────┘
        │
        ▼  Slack → #mining-guardian
   Operator approves or denies → AMS executes
```


---

## Roadmap

### ✅ Complete
- AMS cookie-based JWT auth with auto token refresh
- Full fleet WebSocket scan, paginated
- Three-tier hashrate evaluation (BiXBiT profile / spec lookup / learned baseline)
- Dead hashboard detection (chain-level data from AMS)
- RESTART_CHECK_BOARDS flow with pre/post log compare and ticket escalation
- Post-restart stability polling via common_status (TCP:4029) + AMS fallback
- AMS false-offline verification via TCP:4028
- AMS model mismatch fix (profile string + name field over AMS model field)
- Firmware-aware evaluation routing (BiXBiT / Stock / Auradine / Unknown)
- miner_specs.json — 35+ models: Bitmain, Bitdeer, MicroBT, Canaan
- Tier 3 baseline learning system (72hr window, 36 samples min)
- PDU clients — BiXBiT 2U+PDU HMAC-SHA1 auth (163 @ .15, 164 @ .16)
- Immersion tank client — Fog Hashing Elite 1 REST API (B100 @ .20)
- FacilityMonitor — all 3 infrastructure sources, wired into scan report
- Miner → outlet map in facility_monitor.py
- DB schema upgrade to 27 fields (mac, cooling_mode, profile, firmware, PDU power, etc.)
- Temperature thresholds: uniform 76°C yellow / 86°C red across all cooling types
- PDU power rule: PDU readings always take priority over miner-reported consumption
- Permanent action audit log
- Knowledge export + federated combine system
- Dashboard API (FastAPI :8585, 15+ endpoints)
- Retool Phase 1 dashboard (via cloudflared tunnel at dashboard.fieslerfamily.com)
- morning.sh daily briefing (cron 7am, caffeinate fix, Full Disk Access confirmed)
- AMS API fully documented (153 endpoints, AMS_API.md)
- Auradine AH3880 direct API documented (AURADINE_API.md — reference/fallback)
- WhatsMiner direct API documented (WHATSMINER_API.md — reference/fallback)
- BiXBiT Bitmain direct API documented (docs/BIXBIT_DIRECT_API.md — reference/fallback)

### 🔜 Next Up
- Add second S21 EXP Hyd (.26) to AMS — Rob's action item
  → Tell me the AMS ID and I'll update PDU_OUTLET_MAP in facility_monitor.py
- Profile map session — walk through each miner model to build config.json profile table
- Wire execute_board_restart into OpenClaw approval callback (Mac Mini task)
- Pre-restart log collection for regular RESTART actions (same non-blocking approach)

### 🔜 Mac Mini Arrival (this week)
- Install OpenClaw + configure Slack integration
- Install Ollama + Qwen3-Coder or LLaMA 3.2 (depending on RAM)
- Wire Mining Guardian → OpenClaw webhook (already coded: POST to localhost:18789/hooks)
- Test full APPROVE/DENY flow end-to-end via Slack
- Deploy Mining Guardian as launchd service

### 🔜 Future
- Container monitoring (USA 188 containers — build when live access granted)
- Retool Phase 2: scan history trend chart, facility map panel, per-miner drill-down
- Firmware version drift detection across fleet
- Predictive failure detection from log patterns
- Cross-customer federated knowledge (master_knowledge.json pipeline)
- React dashboard (white-label, customer-facing)
- Multi-customer platform + packaged Mac Mini installer

---

## Direct Device API Reference

All three direct APIs are documented as **reference and fallback only**.
AMS is always the primary path. Direct APIs are used only if AMS is unreachable.

| File | Device | Port | Auth |
|---|---|---|---|
| docs/BIXBIT_DIRECT_API.md | BiXBiT Bitmain firmware miners | 4029 (write), 4028 (read) | Token + AES-ECB (enc=false for default pw) |
| AURADINE_API.md | Auradine AH3880 | 8443 HTTPS | JWT Bearer token |
| WHATSMINER_API.md | WhatsMiner (MicroBT) | 4028 TCP | Token-based |

Key commands available via BiXBiT direct API (docs/BIXBIT_DIRECT_API.md):
- `common_status` — authoritative device state: mining / auto-tuning / starting / emergency
- `get_events` — structured event log (used for pre/post restart comparison)
- `set_work_mode Sleep` — graceful standby before PDU cut
- `restart` / `reboot` — firmware restart vs full OS reboot
- `get_profiles` — full profile list with TH/s and wattage names


---

## Running

```bash
# Single scan (test)
source venv/bin/activate
export $(grep -v '^#' .env | xargs) && python mining_guardian.py

# Dashboard API (required for Retool)
source venv/bin/activate && python dashboard_api.py

# Cloudflare tunnel (required for Retool)
cloudflared tunnel run mining-guardian
```

---

## Configuration

`config.json` (gitignored):
```json
{
  "ams_base_url":           "https://api-staging.dev.bixbit.io/api/v1",
  "ams_email":              "env:AMS_EMAIL",
  "ams_password":           "env:AMS_PASSWORD",
  "ams_workspace_id":       "env:AMS_WORKSPACE_ID",
  "slack_webhook_url":      "env:SLACK_WEBHOOK_URL",
  "dry_run":                true,
  "scan_interval_seconds":  300,
  "approval_mode":          "manual"
}
```

---

## Database Schema

SQLite at `guardian.db`. Key tables:

| Table | Contents | Retention |
|---|---|---|
| `scans` | Scan summaries | Permanent |
| `miner_readings` | 27-field per-miner telemetry per scan | Permanent |
| `miner_logs` | Raw log file content | 7-day rolling purge |
| `miner_restarts` | Restart events | Permanent |
| `ams_notifications` | AMS-generated alerts | Permanent |
| `weather_readings` | Ambient temp/humidity per scan | Permanent |
| `pending_approvals` | Pending APPROVE/DENY per scan thread | Cleared on decision |
| `action_audit_log` | Every approval/denial — permanent record | Never expires |
| `miner_baselines` | Tier 3 learned baselines per miner | Permanent |

`miner_readings` 27 fields include: mac, cooling_mode, current_profile,
firmware_manufacturer, firmware_version, pdu_power, map_location, error_codes,
consumption, temp_board, and all standard hashrate/temp/fan fields.

---

## Mac Mini Deployment

```bash
git clone https://github.com/robertfiesler-spec/Mining-Gaurdian.git
cd "Mining Gaurdian"
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in credentials
export $(grep -v '^#' .env | xargs) && python mining_guardian.py

# launchd watchdog
cp com.bixbit.mining-guardian.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.bixbit.mining-guardian.plist

# OpenClaw (pending)
npm install -g openclaw && openclaw onboard
```

---

*Built by Rob Fiesler — BiXBiT USA CTO*
