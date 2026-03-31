# BiXBiT Direct Device API (Bitmain Firmware)

## ARCHITECTURE RULE — READ FIRST

ALL miner commands go through AMS first.

AMS is the primary control path for Mining Guardian. Every command sent through AMS
is recorded in the audit log with timestamp, user, and action. Commands sent directly
to port 4029 bypass that audit trail entirely.

This file is reference documentation and a fallback only.
Use the direct API ONLY if:
  1. AMS is unreachable (network failure, AMS server down), AND
  2. The operation cannot wait for AMS to recover

The Mac Mini only needs LAN access to AMS — not direct IP access to each miner.
Direct device access requires being on the same local subnet (192.168.188.x).

---

## Transport

Port 4028 — CGMiner read-only compat. No auth. Commands: summary, stats, pools.
             This is what Mining Guardian currently uses for false-offline verification.

Port 4029 — Full BiXBiT API. Supports all read + write commands.
             Requires token + AES-ECB for encrypted commands.
             Unencrypted commands (enc: false) work without a token.

All commands are sent as newline-terminated JSON over raw TCP.

Unencrypted format:
  {"enc": false, "data": "<base64(command_json)>"}

Encrypted format:
  {"enc": true, "sign": "<sha256_signature>", "data": "<base64(AES_ECB_encrypted)>"}

IMPORTANT: Encryption does NOT work with the default password (root).
For default-password miners (root/root), all commands must use enc: false.
Write commands sent unencrypted to a default-password miner still work.

---

## Authentication (encrypted path — non-default password only)

Step 1: Call get_token (unencrypted) → returns key_base, sign_base, time
Step 2: password_hash = MD5("root:antMiner Configuration:<device_password>")
Step 3: key  = SHA256(key_base + password_hash)
Step 4: sign = SHA256(sign_base + key + time)
Step 5: Encrypt payload bytes with AES-ECB, key = first 16 bytes of key string
Step 6: Base64-encode encrypted result → this is the data field

Token lasts 30 minutes. Unlimited simultaneous tokens allowed.
Changing the device password does NOT invalidate existing tokens.


---

## Key Commands for Mining Guardian

### Read-only (port 4028 or 4029, no auth needed)

common_status
  Returns the current device state. Most important command for post-restart polling.
  Response field: common_status (string)
  Values:
    "mining"            — fully up and hashing, safe to evaluate
    "auto-tuning"       — tuning chips, hashrate will be unstable
    "starting"          — firmware starting up
    "initializing"      — early boot stage
    "sleeping"          — sleep mode active (set_work_mode Sleep was called)
    "emergency"         — entered emergency mode due to too many restarts
    "shutting-down"     — graceful shutdown in progress
    "generating-power-log" — calculating power consumption data
    "generating-profiles"  — generating profile presets
    "stopped"           — work stopped
    "failure"           — driver startup failed
    "none"              — firmware not running
  Use this instead of AMS minerStatus for post-restart stability detection.
  Wait for "mining" before collecting post-restart logs or evaluating boards.

summary
  High-level device stats. Available on port 4028 (no auth).
  Key fields: GHS 5s, GHS 30m, GHS av, Power Estimated, Hardware Errors, Elapsed

stats
  Per-chain and per-chip data. Detailed diagnostic.
  Key fields per chain: chain_rateN, chain_consumptionN, chain_hwN
  Key fields: temp_chipN (string "n1-n2-n3"), temp_pcbN, fan1-4, rate_unit ("GH/s")
  chain[n].chain_status: 0=Good, 2=Bad, 3=Disabled
  chain[n].asic_bad_num: count of bad chips on that board
  chain[n].power: watts consumed by that board

get_events
  Returns the device event log. Pull before and after restarts.
  Each event: { code, cause, log_type, timestamp }
  This is the structured equivalent of what AMS calls "logs".
  Use for pre/post restart comparison in execute_board_restart flow.

version
  Returns firmware version, API version, PSU model.
  Key field: BixFirmware (e.g. "0.9.9.3-stage21.0"), Type ("Antminer S19j Pro")


### Write commands (port 4029, require encryption unless default password)

get_work_mode / set_work_mode
  Get or set Sleep/Normal mode.
  set_work_mode parameter: {"work_mode": "Sleep"} or {"work_mode": "Normal"}
  OPERATIONAL RULE: Always call set_work_mode Sleep and wait for common_status
  to return "sleeping" BEFORE cutting PDU power. Same rule as Auradine AH3880.
  Never do a hard PDU cut on a running BiXBiT miner.

restart
  Restarts the mining firmware (faster than reboot, no OS restart).
  Preferred for hashboard recovery attempts.

reboot
  Full device reboot (OS + firmware). Slower, use only when restart fails.

get_profile / get_profiles
  get_profile: returns the currently configured profile (freq, startup_voltage, max_voltage, name, id)
  get_profiles: returns all available profiles
  Profile name format: "144 TH/s - ~4913 W" — same format AMS uses in currentProfile field
  Profile id format: "736:14000:14500" (freq:startup_voltage:max_voltage)
  NOTE: get_profile returns config-file profile, not necessarily the running profile
  if the switcher has changed it. Use AMS currentProfile for the live value.

set_profile
  Change the active profile. Parameter: {freq, startup_voltage, max_voltage}
  The id and name fields are ignored — only the numeric values matter.
  AMS is preferred for profile changes (audit log). Use this only as fallback.

get_switcher_settings / set_switcher_settings
  The auto-profile switcher. Automatically lowers profile if:
    - chip temp exceeds lower_profile_if_temp_above
    - power draw exceeds lower_profile_if_power_above
  Raises profile if temp drops below raise_profile_if_temp_below.
  max_profile_id caps how high the switcher can go.
  Mining Guardian should read this to understand dynamic profile behavior.

remove_events
  Clears the event log. Do NOT call this — Mining Guardian should read events,
  never delete them. Event history is valuable diagnostic data.

---

## Profile System Notes

Profile ID format: "freq:startup_voltage:max_voltage" e.g. "736:14000:14500"
Profile name format: "144 TH/s - ~4913 W" (tilde before watt value = estimated)

To change a profile via AMS (preferred path):
  1. Call AMS miner_config endpoint to get profilesList for the miner
  2. Find the profile matching desired TH/s by parsing the name string
  3. Send AMS change_overclock_config with the profileName (the id string)

To change a profile via direct API (fallback only):
  1. Call get_profiles to get available profiles
  2. Match desired TH/s from name field
  3. Call set_profile with {freq, startup_voltage, max_voltage} from that profile

---

## Post-Restart Polling (replacing AMS minerStatus check)

After calling restart or reboot via AMS (primary) or direct API (fallback):

Phase 1 — Wait for device to respond (up to 10 minutes):
  Poll common_status every 15s on port 4029
  Continue when any response is received (device is booting)

Phase 2 — Wait for stable mining state (up to 45 minutes):
  Continue polling common_status every 30s
  Wait for "mining" on 2 consecutive polls
  Do NOT evaluate hashrate or board state while in any other status
  If "emergency" appears — escalate immediately, do not wait further

Phase 3 — Post-restart log collection and board comparison:
  Call get_events to collect post-restart event log
  Compare with pre-restart events
  Check stats chain[n].chain_status and asic_bad_num for each board

This flow is implemented in execute_board_restart() in mining_guardian.py.
The common_status "mining" check replaces the previous AMS-based minerStatus==0 check.

---

## Units Reference

Hashrate fields in stats: rate_unit is "GH/s" for BTC miners
  chain_rateN values are in GH/s → divide by 1000 to get TH/s
  GHS 5s / GHS av in summary are also GH/s

Power fields:
  chain[n].power — watts for that board
  power_estimated in summary — device's self-calculated total watts
  fans_power — watts consumed by fans only

Temperature fields:
  temp_chipN — string format "n1-n2-n3" (multiple sensor readings per board)
  temp_pcbN  — PCB/board temp string
  device_chip_temp — single max chip temp integer
  device_board_temp — single max board temp integer
