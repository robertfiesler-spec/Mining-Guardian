# AMS BiXBiT API Reference

*Source: Live spec from https://api-staging.dev.bixbit.io/api/doc/doc.json — 153 endpoints*

---

## Authentication

AMS uses **cookie-based JWT** — NOT bearer tokens in headers.

```
POST /auth/login         → sets session cookie
POST /auth/select_workspace  → scopes session to workspace
```

All subsequent calls use the session cookie automatically (handled by AMSClient).
The `_ensure_token()` method in AMSClient handles both steps.

---

## Miner Commands (DCS = Direct Control System)

All DCS commands POST to `/miners/dcs/<action>` with body:
```json
{"ids": [<miner_id>, ...], "selectionMode": ""}
```
`selectionMode` is optional — leave empty string for targeted IDs.

| Endpoint | Action | Notes |
|---|---|---|
| `POST /miners/dcs/reboot` | Firmware reboot | Safe restart — goes through AMS audit |
| `POST /miners/dcs/start` | Start mining | Wake from stopped state |
| `POST /miners/dcs/stop` | Stop mining | Graceful stop — use before PDU cut |
| `POST /miners/dcs/led_on` | Flash LED on | Locate miner in rack |
| `POST /miners/dcs/led_off` | Flash LED off | Stop locate |
| `POST /miners/dcs/generate_profile` | Start autotune | Generates optimized profile |
| `POST /miners/dcs/stop_generate_profile` | Stop autotune | Abort profile generation |
| `POST /miners/dcs/change_overclock_config` | Change profile | See profile section below |
| `POST /miners/dcs/upgrade_psu` | PSU firmware update | BiXBiT-specific |
| `POST /miners/dcs/enable_psu_fan` | Enable PSU fan | BiXBiT-specific |
| `POST /miners/dcs/disable_psu_fan` | Disable PSU fan | BiXBiT-specific |
| `PATCH /miners/dcs/change_network_config` | Change IP/DHCP | Fields: protocol, ip, mask, gateway, dnsServers |
| `PATCH /miners/dcs/change_password` | Change miner password | Fields: oldPassword, newPassword |
| `POST /miners/dcs/change_pools` | Update pool config | OUT OF SCOPE for Mining Guardian |
| `POST /miners/dcs/change_hotel_fee` | Hotel fee config | BiXBiT colocation billing feature |

---

## Profile / Overclock Config

### How profiles work on BiXBiT firmware

`POST /miners/miner_config` with `{"id": <miner_id>}` returns the full overclock config:

```json
{
  "minerConfig": {
    "overclockConfig": {
      "currentProfile": "144 TH/s - ~4913 W",
      "profilesList": [
        {"profileName": "763:14200:14700", "profileStr": "144 TH/s - ~4913 W"},
        {"profileName": "736:14000:14500", "profileStr": "139 TH/s - ~4590 W"},
        ...
      ],
      "generated": false
    },
    "currentProfile": "144 TH/s - ~4913 W"
  }
}
```

**Key insight:** `profileName` is the internal identifier (`freq:voltage:voltage` format).
`profileStr` is the human-readable label shown in AMS (`"144 TH/s - ~4913 W"`).

To change profile: `POST /miners/dcs/change_overclock_config`:
```json
{
  "ids": [53477],
  "config": {"profileName": "736:14000:14500"}
}
```

### Full profile list — Antminer S19JPro (BiXBiT firmware)

| profileStr | profileName | TH/s | ~Watts |
|---|---|---|---|
| 56 TH/s - ~1429 W | 300:12250:12500 | 56 | 1429 |
| 61 TH/s - ~1537 W | 327:12250:12500 | 61 | 1537 |
| 67 TH/s - ~1636 W | 354:12250:12500 | 67 | 1636 |
| 72 TH/s - ~1746 W | 382:12250:12500 | 72 | 1746 |
| 77 TH/s - ~1861 W | 409:12250:12500 | 77 | 1861 |
| 82 TH/s - ~2102 W | 436:12400:12800 | 82 | 2102 |
| 87 TH/s - ~2196 W | 463:12400:12800 | 87 | 2196 |
| 93 TH/s - ~2455 W | 491:12650:13150 | 93 | 2455 |
| 98 TH/s - ~2630 W | 518:12750:13250 | 98 | 2630 |
| 103 TH/s - ~2857 W | 545:13000:13500 | 103 | 2857 |
| 108 TH/s - ~3035 W | 572:13100:13600 | 108 | 3035 |
| 113 TH/s - ~3287 W | 600:13300:13800 | 113 | 3287 |
| 118 TH/s - ~3492 W | 627:13400:13900 | 118 | 3492 |
| 123 TH/s - ~3733 W | 654:13550:14050 | 123 | 3733 |
| 129 TH/s - ~4000 W | 681:13700:14200 | 129 | 4000 |
| 134 TH/s - ~4299 W | 709:13850:14350 | 134 | 4299 |
| 139 TH/s - ~4590 W | 736:14000:14500 | 139 | 4590 |
| **144 TH/s - ~4913 W** | **763:14200:14700** | **144** | **4913** ← current |

**Profile parsing rule:** `profileStr` format is `"{TH/s} TH/s - ~{W} W"`. Strip the `~` 
before parsing watts. Extract TH/s as the first number.

---

## Miner Settings (AMS Thresholds)

`POST /miners/get_device_settings` with `{"id": <miner_id>}` returns the alerting thresholds
AMS uses for this miner model. These are NOT the same as the active profile — they're the
fleet-wide limits Mining Guardian uses to decide when to flag something.

```json
{
  "deviceSettings": {
    "maxHashrate": 75000,       ← MH/s = 75 TH/s (WARNING: not the profile max!)
    "hashrateMedium": 67500,    ← medium alert threshold
    "hashrateLow": 52500,       ← low alert threshold
    "maxTempBoard": 85,         ← °C board temp max
    "maxTempChip": 100,         ← °C chip temp max
    "tempChipMedium": 90,       ← medium temp alert
    "tempChipLow": 70,          ← low temp alert
    "maxConsumption": 6000,     ← watts max
    "consumptionMedium": 4800,
    "consumptionLow": 3600,
    "maxFanSpeed": 6000,        ← RPM
    "fanSpeedLow": 1200,
    "fanSpeedMedium": 2400,
    "idleConsumption": 100
  }
}
```

**IMPORTANT:** `maxHashrate: 75000 MH/s = 75 TH/s` is the AMS alert threshold, NOT the
device's rated hashrate. The miner is currently running at 144 TH/s on its active profile.
Mining Guardian MUST compare actual hashrate against `currentProfile`'s rated TH/s,
not against `maxHashrate`.

---

## Miner Config (Full Device State)

`POST /miners/miner_config` with `{"id": <miner_id>}` returns:

```json
{
  "minerConfig": {
    "ledStatus": false,
    "coolingMode": 4,
    "poolConfig": [...],
    "networkConfig": {"hostname": "Antminer", "dhcp": true, ...},
    "hotelFeeConfig": [],
    "overclockConfig": {
      "currentProfile": "144 TH/s - ~4913 W",
      "profilesList": [...],
      "generated": false
    },
    "currentProfile": "144 TH/s - ~4913 W"
  }
}
```

---

## PDU Commands

| Endpoint | Action | Body |
|---|---|---|
| `POST /pdus/dcs/set_control_outlet` | Toggle single outlet | pduID, outletIndex, state |
| `POST /pdus/dcs/mass_off_outlets` | Cut all outlets on PDU | ids: [pduID] |
| `POST /pdus/attach_miner` | Assign miner to PDU outlet | minerID, pduID, outletIndex |
| `POST /pdus/untie_miner` | Remove miner from PDU | pduID, outletIndex |
| `POST /pdus/dcs/set_outlet_current` | Set outlet current limit | |
| `POST /pdus/dcs/set_voltage` | Set PDU voltage threshold | |

**PDU power cycle flow** (correct sequence through AMS):
1. `POST /miners/dcs/stop` — graceful stop first
2. Wait ~5s
3. `POST /pdus/dcs/set_control_outlet` — cut power
4. Wait off_delay seconds
5. `POST /pdus/dcs/set_control_outlet` — restore power
6. `POST /miners/dcs/start` — start mining

---

## Miner Settings Update (AMS Thresholds)

`POST /miners/change_settings` — updates the alerting thresholds in AMS for a miner:

```json
{
  "id": 53477,
  "code": "antminer-s19jpro",
  "title": "Antminer S19JPro",
  "maxHashrate": 75000,
  "hashrateMedium": 67500,
  "hashrateLow": 52500,
  ...all fields required
}
```

---

## Automatization Rules

AMS has a built-in automation engine. Mining Guardian can create/read/delete rules:

`POST /automatization/rule`:
```json
{
  "ruleName": "string",
  "ruleType": "string",
  "actionName": "string",
  "condition": {},
  "deviceIDs": [53477]
}
```

`GET /automatization/location_list` — get locations for rule targeting.

---

## Fleet Models in This Workspace

From `/miners/available_filters`:

| AMS Model Code | Display Name |
|---|---|
| `antminer-s19jpro` | Antminer S19JPro |
| `antminer-s19j-pro` | Antminer S19J Pro |
| `antminer-s21-imm` | Antminer S21 Immersion |
| `antminer-s21e-xp-hydro` | Antminer S21EXPHyd |
| `teraflux-ah3880` | Teraflux AH3880 |
| `sealminer-a2` | SealMiner A2 |

---

## Container Commands

| Endpoint | Action |
|---|---|
| `POST /containers/do_request` | Send command to container |
| `POST /containers/request` | Single container command |
| `POST /containers/set_config` | Update container config (alarms, auto, manual) |
| `POST /containers/change_settings` | Change container settings |
| `GET /containers/ws` | WebSocket for live container data |
| `GET /containers/list_ws` | WebSocket for container list |
| `GET /containers/statistic` | Container statistics |

Container config has three sections: `alert` (thresholds), `auto` (PID targets), `manual` (fixed setpoints).

---

## Key Files

- `ams_api_spec.json` — full 153-endpoint OpenAPI spec (541KB, gitignored)
- `mining_guardian.py` — AMSClient implements the most-used endpoints
