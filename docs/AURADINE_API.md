# Auradine Teraflux AH3880 API Reference

*Source: Teraflux API Reference (api.md 2025-02-19) + AH3880 Hardware Reference*

---

> ⚠️ **Architecture note:** AMS is always the primary route for all miner commands in Mining Guardian. The Mac Mini only needs LAN access to AMS — not direct access to each miner. AMS provides the audit log. This direct device API is documented as a reference and fallback only.

## Overview

The AH3880 exposes two API surfaces that Mining Guardian can use:

| API Type | Port | Auth | Access |
|---|---|---|---|
| HTTP(S)/REST | 8080 (HTTP) / 8443 (HTTPS) | JWT token | Read + Write |
| CGMiner TCP | 4028 | None | Read-only |

Default credentials: `admin` / `admin`

Tokens are obtained via `POST /token` and must be passed as `Token: <jwt>` header on every REST call. Tokens are valid ~1 hour. The `auradine_client.py` handles token acquisition and renewal automatically.

---

## Critical Operational Rules

**Before cutting PDU power or disconnecting coolant:**
Always place the miner in standby first via `POST /mode` with `sleep: on`. The AH3880 hardware reference explicitly states that disconnecting coolant without a graceful standby can damage the cooling plate. This is different from Bitmain/WhatsMiner behavior — never hard-cut PDU on an AH3880 without standby first.

**Cooling system requirements:**
- Liquid working temp: 10°C to 60°C
- Rated flow: 5–20 L/min (±10%)
- Max pressure: 400 kPa
- pH: 6–8
- Replace coolant annually

---

## REST API Endpoints

### Authentication

```
POST /token
Body: {"command":"token","user":"admin","password":"admin"}
Returns: JWT token in Token[0].Token
```

### Read Endpoints (Monitoring)

| Endpoint | Method | Description |
|---|---|---|
| `/summary` | GET | Hashrate (MHS av/5s/1m/5m/15m), shares, HW errors |
| `/temperature` | GET | Per-chip + per-board temps, all 3 hashboards |
| `/mode` | GET | Current mode, sleep state, target TH/s or watts |
| `/psu` | GET | PSU power in/out (watts), voltages, temps, fan RPM |
| `/fan` | GET | Fan IDs, speed, target, max RPM |
| `/led` | GET | LED status code (see table below) |
| `/ipreport` | GET | IP, MAC, model, FluxOS version, serial numbers |
| `/devdetails` | GET | Model + chip count per hashboard |
| `/devs` | GET | Per-board hashrate, shares, HW errors |
| `/pools` | GET | Pool connection status (read-only, out of scope) |
| `/version` | GET | FluxOS firmware version string |
| `/frequency` | GET | Per-ASIC chip frequencies |
| `/voltage` | GET | Per-ASIC chip voltages |
| `/network` | GET | Network config: IP, mask, gateway, DNS |
| `/asccount` | GET | Total board count + total chip count |

### Write Endpoints (Control)

| Endpoint | Method | Description |
|---|---|---|
| `/mode` | POST | Set mode (eco/normal/turbo/custom) or sleep on/off |
| `/restart` | POST | Reboot system, restart miner process, or restart API |
| `/firmware-upgrade` | POST | Download and stage firmware update |
| `/network` | POST | Change network config (static or DHCP) |
| `/factory-reset` | POST | Factory reset (erases all config) |

---

## LED Status Codes

| Code | Status | Meaning |
|---|---|---|
| 1 | NO_POWER | No power |
| 2 | NORMAL | Operating normally |
| 3 | LOCATE_MINER | Flash LEDs active (both LEDs flash green) |
| 4 | TEMPERATURE | Temperature issue |
| 5 | POOL_CONFIG | Pool configuration incorrect |
| 6 | NETWORK | Network connectivity issue |
| 7 | CONTROL_BOARD | Control board fault (likely MicroSD corruption) |
| 8 | HASH_RATE_LOW | Hash rate below 90% of target |
| 9 | FAN_ISSUE | PSU fan malfunction |
| 10 | HASHBOARD_ISSUE | One or more hashboards not functioning |
| 11 | PSU_ISSUE | PSU malfunction |
| 12 | TUNING | Autotune in progress |
| 13 | STANDBY | Miner in standby/sleep mode |
| 14 | RESETTING | Factory reset in progress |
| 15 | WARMING | Warm-up mode (STAT=Yellow flashing) |
| 16 | UPGRADING | Firmware upgrade in progress |
| 19 | LOW_COOLANT | Low coolant level detected |

---

## Operating Modes

| Mode | Description | Notes |
|---|---|---|
| `turbo` | Maximum hashrate | ~600 TH/s on AH3880. In AMS shows as "turbo" — needs manual profile map entry |
| `normal` | Balanced default | ~500 TH/s estimated |
| `eco` | Efficiency optimized | Algorithm iterates to find best efficiency |
| `custom` | User-defined target | Set via TH/s target or watt limit |
| sleep | Standby | Mining stopped, fans at 20% |

**Profile map note:** When AMS reports `currentProfile = "turbo"` for an AH3880, the rated TH/s is **600**. This is the only named profile that requires manual mapping — all other Auradine profiles are set via the custom mode API and return numerical values.

---

## CGMiner TCP API (Port 4028, No Auth)

Read-only commands available via raw TCP:

```
summary     → hashrate + shares snapshot
version     → FluxOS version
pools       → pool status
devs        → per-board stats
stats       → timing/call stats
asccount    → board + chip count
devdetails  → board model info
coin        → network difficulty
config      → miner config summary
```

TCP command format:
```json
{"command": "summary"}
```
Send as newline-terminated JSON string over TCP socket.

---

## Key Differences from WhatsMiner/Bitmain

| Feature | AH3880 (Auradine) | WhatsMiner | Bitmain Antminer |
|---|---|---|---|
| Direct API port | 8443 (HTTPS REST) | 4028 (TCP) | 4028 (TCP) |
| Auth | JWT token | None (encrypted) | None |
| Safe shutdown | Must call standby via API | power_off command | power_off via API |
| Profile names | "turbo", custom numeric | Low/Normal/High | Numeric strings |
| Coolant leak sensor | Yes (LED code 19) | No | No |
| Chip count | 396 (3 boards × 132) | Varies | Varies |

---

## Hardware Specs (AH3880)

| Spec | Value |
|---|---|
| Form factor | 2U rackmount, 26.2 × 19.1 × 3.5 inches |
| Weight | 64 lbs / 29 kg |
| Power input | 380–480 VAC, 3-phase, 20A per phase |
| Cooling | Hydro-cooled (liquid inlet/outlet at rear) |
| Operating temp | -20°C to 50°C (-4°F to 122°F) |
| Liquid working temp | 10°C to 60°C |
| Rated liquid flow | 5–20 L/min |
| Ports | Ethernet: 10/100/1000 Mbps |
| Network ports | 80 (HTTP), 443 (HTTPS), 4028 (TCP API), 8443 (REST API) |
| Outbound required | api.auradine.com, customer.auradine.com, update.auradine.com |

---

## Files

- `auradine_client.py` — Python client implementation
- `Teraflux_API_Reference.pdf` — Full Auradine REST + TCP API reference
- `Teraflux_AH3880_Hardware_Reference.pdf` — Hardware guide, cooling system, LED codes
