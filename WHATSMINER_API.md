# WhatsMiner Extended Partner API

## Overview
Direct device-level API that connects to each miner via TCP socket on port 4028.
This is separate from AMS — it talks directly to the miner firmware.
Commands are encrypted. Responses are JSON.

Applies to: WhatsMiner devices running BiXBiT firmware.
Bitmain devices: TBD — BiXBiT has custom firmware, may expose same API.

API command status response format:
- Success: `{"STATUS":"S","When":timestamp,"Code":131,"Msg":"API command OK"}`
- Failure: `{"STATUS":"E","When":timestamp,"Code":132,"Msg":"API command ERROR"}`
- Unknown: `{"STATUS":"E","Code":14,"Msg":"invalid cmd"}`

---

## Primary Monitoring Command

### summary
Returns full device status snapshot. Most important command for Mining Guardian.

Key fields returned:
| Field | Description |
|---|---|
| Power Realtime | Current power draw (W) |
| Status | Mining / Suspended / Tuning / Generating Profiles / Restoring / Suspended: High Env. Temp |
| Chip Temp Min/Max/Avg | All three chip temp readings (°C) |
| Chip Temp Target | Target chip temp |
| Chip Temp Protect | Max chip temp limit |
| Fan Speed Percent | Current fan PWM % |
| Fan Speed In/Out | Fan RPM intake/exhaust |
| Env Temp | Environment temperature sensor (°C) |
| MHS av | Average hashrate all time (MH/s) |
| MHS 5s / 1m / 5m / 15m | Hashrate at multiple intervals (MH/s) |
| Power Mode | Low / Normal / High |
| Power Limit | Current power limit (W) |
| Factory GHS | Rated hashrate at factory settings (GH/s) |
| Upfreq Complete | 0=not done, 1=autotune complete |
| PSU Vin0/1/2 | Input voltage per phase |
| PSU Vout / Iout | Output voltage and current |
| PSU Temp0/1/2 | PSU temperature sensors |
| Elapsed | Uptime in seconds |
| Accepted / Rejected | Share counts |
| No Fee Pools Penalty Active | True if fee pool disconnected >10min |

---

## Power Control Commands

### set_low_power / set_normal_power / set_high_power
Switch power mode instantly. No payload required.

### get_user_power_limit
Returns:
- `powerMode`: Low / Normal / High
- `powerLimit`: Current user power limit (W)

### set_user_power_limit
Payload: `{"softRestart":true,"powerMode":1,"powerLimit":1000}`
- `powerMode`: Low / Normal / High (string or int)
- `powerLimit`: Watts
- `softRestart`: true = try to apply without stopping mining (preferred)

**Note:** softRestart only works if device is Mining + has upfreq results + enterprise firmware.

### power_off / power_on
Enable/disable sleep mode — cuts hashboard power.

### deep_power_off / deep_power_on
Full suspend that survives reboot. Use for emergency stops.

### power_status
Returns:
- `suspend`: "true"/"false"
- `deep_suspend`: "true"/"false"

---

## Fan Control Commands

### get_fan_mode
Returns:
- `fan_mode`: "auto" or "manual"
- `manual_fan_speed_percent`: Speed % (10-100)

### set_fan_mode
Payload: `{"fan_mode":"auto","manual_fan_speed_percent":"93"}`

### get_boards_cool_fan_percent / set_boards_cool_fan_percent
Startup cooling fan speed % (10-100).

---

## Temperature Control Commands

### get_cool_temp / set_cool_temp
Set cooldown target temperature.
Types: "default" / "env_temp" / "manual"
Payload example: `{"type":"manual","manual_temp":35}`

### get_env_temp_limit / set_env_temp_limit
Set environment temperature thresholds for auto suspend/resume.
Payload: `{"enabled":"true","resume_env_temp":"50","suspend_env_temp":"65"}`
Note: resume_env_temp must be less than suspend_env_temp.

---

## Profile & Overclock Commands

### get_overclock_info / set_overclock_info
Full overclock parameters:
- `board_temp_target`: Target board temp (°C)
- `freq_target`: Target chip frequency (MHz)
- `power_limit`: Power limit (W) — must be < power_max
- `voltage_target`: Target voltage — must be between voltage_min and voltage_limit
- `power_max`: Max power (W)
- `voltage_limit`: Max voltage
- `voltage_min`: Min voltage
- `soft_restart`: Apply without stopping mining if possible

### get_profile_switcher / set_profile_switcher
Auto-switches profiles based on temperature.
- `lower_temp`: °C at which device selects lower profile
- `raise_temp`: °C at which device selects higher profile
- `max_profile_id`: Highest profile the switcher can set
- `ignore_pwm`: If true, ignores fan PWM when increasing profile
- `profiles`: Array of available profiles with id + name

**Note:** lower_temp must be GREATER than raise_temp (counterintuitive — lower_temp triggers downgrade).

### generate_profiles / stop_profiles_generation
Start/stop autotune profile generation.

### get_profiles_generation_status
Returns: generating_profiles, has_generated_profiles, profiles_generation_error

### find_max_profile / stop_max_profile_search
Search for the maximum profile the device can sustain.

---

## Autotune (Upfreq) Commands

### get_upfreq_params / set_upfreq_params
Key field for hydro/immersion:
- `liquid_temp_dynamic_power_limit_percent`: How much coolant temp affects power limit.
  0% = ignore coolant temp (full power_max always)
  100% = fully respect dynamic limit
  Example: At 100%, if coolant is hot and limit drops to 80%, device runs at 8000W not 10000W.
  **This is critical for hydro/immersion fleet optimization.**

---

## Board-Level Control

### get_board_slots_state / set_board_slots_state
Enable/disable individual hashboards.
- `enabled`: Array of booleans per board, e.g., `[true, true, true, false]`
- `auto_disable`: Auto-reboot on board error, disable if recovery limit exceeded
- `limit_boards_power`: If true, don't redistribute power from disabled boards

### reset_failed_to_power_on_hashboard_reboots
Reset the board recovery reboot counter.

---

## Cooling Mode Detection

### get_liquid_cooling / set_liquid_cooling
Returns cool_mode:
- `"air"` — fan cooled
- `"liquid"` — immersion (not factory-made for it)
- `"hydro"` — liquid cooling system (factory hydro)
- `"immersion"` — factory immersion

**Use this to detect cooling type per miner programmatically.**

---

## LED Control

### set_led
Payload: `{"color":"red","period":1000,"duration":1000,"start":0}`
Or auto mode: `{"param":"auto"}`

### set_led_on / set_led_off / toggle_led
Simple LED enable/disable.

---

## Firmware & System Commands

### get_firmware_version
Returns: custom_version, firmware_version, custom_api_version, custom_api_features

### update_firmware
Multi-step encrypted workflow — send command, wait for "ready", then send firmware bytes.

### restart_btminer
Restart btminer process only (not full reboot).

### reboot
Full device reboot.

### factory_reset
⚠️ Restore factory settings — use with extreme caution.

### net_config
Set network settings: DHCP or static IP/mask/gateway/DNS.

### download_logs
Binary stream download of device logs.

### set_target_freq
Adjust chip frequency by percent: `{"percent":"30"}`
Formula: new_freq = normal_mode_freq × (1 + percent/100)

---

## AMS Integration

### ams_install / ams_uninstall
Install/uninstall AMS agent on the device.
Payload: `{"api_key":"uuid","update_interval":10}`

### get_ams_install_data
Returns whether AMS is installed and the API key.

---

## Mining Guardian Integration Plan

### How this fits with AMS
- AMS: Fleet-level monitoring, workspace management, PDU control, map/tickets
- WhatsMiner API: Per-device fine-grained control not exposed through AMS
- Both needed — complementary, not competing

### Priority commands to add to AMSClient
1. `summary` — richer per-device data than AMS WebSocket (chip temp min/max/avg, env temp, fan RPM, upfreq status)
2. `get_liquid_cooling` — detect cooling mode programmatically per miner
3. `get_user_power_limit` — confirm active power mode per miner
4. `set_user_power_limit` with softRestart — profile changes without mining interruption
5. `get_board_slots_state` — detect disabled boards
6. `get_overclock_info` — full overclock context for LLM analysis

## Architecture — Firmware Detection Strategy

Mining Guardian must be firmware-aware. Not all customers run BiXBiT firmware.
Before using direct device API, detect what's running on each miner.

### Detection Flow
```
Miner in fleet
    ├── BiXBiT firmware → WhatsMiner Extended API (this doc)
    ├── Standard Antminer firmware → Bitmain CGMiner API (separate doc)
    ├── Standard WhatsMiner firmware → Standard WhatsMiner API
    └── Unknown / unresponsive → AMS only, no direct API
```

### Credentials (BiXBiT firmware)
- Bitmain machines running BiXBiT firmware: `root` / `root`
- WhatsMiner machines running BiXBiT firmware: `admin` / `admin`

### Detection Method
1. Check `get_firmware_version` — `custom_api_version` field confirms BiXBiT firmware
2. Check `get_liquid_cooling` — `cool_mode` field confirms cooling type (air/liquid/hydro/immersion)
3. Fall back to AMS-only if direct API unresponsive

### Network Requirement
Direct device API (port 4028) only reachable from local mining network.
Mac Mini deployment (on-site) is required for direct API access.
Remote operation (via AMS) does not have access to port 4028.

### Config in config.json
```json
{
  "direct_api_enabled": true,
  "miner_credentials": {
    "bitmain_bixbit": {"user": "root", "password": "root"},
    "whatsminer_bixbit": {"user": "admin", "password": "admin"}
  }
}
```
