# guardian-db schema reference

This file is a reference for interpreting the JSON returned by the
Mining Guardian `/query/*` endpoints. Use this when you need to
understand what a specific field means or what units it's in.

## Common field meanings

| Field | Meaning |
|---|---|
| `scan_id` | Integer ID of the scan this reading came from. Increments with each scan. |
| `scanned_at` / `scan_time` / `timestamp` | ISO 8601 timestamp (UTC) of when the scan or event happened |
| `ip` | IPv4 address of the miner (e.g., `192.168.188.36`) |
| `miner_id` | BiXBiT AMS internal miner ID (numeric string) |
| `model` | Miner model name (e.g., "Antminer S19JPro", "AH3880", "S21 Hydro") |
| `status` | One of: `online`, `offline`, `ams_sync` (verified online but AMS reports offline) |
| `hashrate` | Current real hashrate (see unit note below) |
| `max_hashrate` | Maximum configured profile hashrate |
| `hashrate_pct` | hashrate as a percentage of max_hashrate |
| `temp_chip` | Highest chip temperature in °C |
| `temp_board` | Highest board temperature in °C |
| `issue` | Human-readable issue description (null if no issue) |
| `action` | Recommended or taken action (RESTART, PDU_CYCLE, PHYSICAL_CYCLE, RESTART_CHECK_BOARDS, MONITOR, TEMP_ACTION_REQUIRED) |
| `map_location` | Physical location of the miner in the facility (row, rack, etc.) |
| `uptime` | String format, how long the miner has been up since last reboot |
| `current_profile` | Name of the BiXBiT hashrate profile the miner is currently running |
| `firmware_manufacturer` | "bixbit", "auradine", or the stock manufacturer name |
| `firmware_version` | Firmware version string |

## IMPORTANT unit and data quirks

### Hashrate units are inconsistent

The `hashrate` and `max_hashrate` columns in `miner_readings` are stored
in **a mix of units depending on the miner model and firmware**. Some
miners report MH/s, some GH/s, some TH/s. The `hashrate_pct` field is
always reliable because it's computed as a ratio on ingestion. **When
summarizing for the user, prefer hashrate_pct and the issue text over
raw hashrate numbers.** If the user specifically asks for a hashrate in
TH/s, double-check the value against what's realistic for the miner
model (e.g., a S19JPro should be ~100-144 TH/s).

### Fleet total hashrate may look wrong

The `fleet_summary` endpoint sums `hashrate` across all miners, but
because of the unit mismatch above, the total can look absurd (e.g.,
"7,446,842 TH/s" which is impossible). If the total looks wrong,
don't report it. Report `online`, `offline`, `flagged`, and
`avg_hashrate_pct` instead — those are reliable.

### Auradine AH3880 chassis has 2 boards, not 3

The AH3880 is a 2-board chassis, so `chain_readings` will only have
rows for board_index 0 and 1 for those miners. The third board slot
doesn't exist physically. An `avg_volt` of 0 for board_index 2 on an
AH3880 is firmware noise, not a real dead board.

### Known dead boards are suppressed from flagged_miners

If a miner is in `known_dead_boards`, it won't appear in
`flagged_miners` results because the Mining Guardian daemon filters it
out (to avoid re-flagging miners that are already ticketed). To see
those miners, use the `known_dead_boards` command.

### Offline miners show 0% hashrate

`worst_performers` excludes offline miners (they'd always be at 0% and
that's not interesting). If the user asks specifically "which miners
are offline", use `flagged_miners` or `fleet_summary` — not
`worst_performers`.

## Facility rules that override data interpretation

### Temperature thresholds

The facility is fully liquid-cooled (hydro racks + immersion tank).
Normal chip temperature range is 60-75°C. The flag threshold is 84°C.

- **Below 84°C:** normal, no comment needed
- **84-85°C:** warm but within spec, note it but don't alarm
- **86°C and above:** actual overheating, worth flagging

Do NOT warn about temperatures below 84°C even if they look higher
than typical air-cooled miners.

### HVAC delta-T

Low delta-T is INTENTIONAL and EXPECTED. The facility runs with a
narrow temperature split and it rises as outside temperatures climb.
Do NOT flag low delta-T as a problem. Do NOT recommend HVAC
investigation because delta-T looks low. Just report the numbers
factually and move on.

### Dead-board miners

If a miner is in `known_dead_boards`, it has already been ticketed and
someone is physically handling it. Do NOT recommend restarts,
diagnostics, or profile changes — just note it's pending physical work.

### No fans, ever

All miners at this facility are liquid-cooled. There are no fans. Do
not mention fan speed, fan failure, airflow, or air cooling in any
response.

## When the user asks for a specific miner by a short name

If the user says ".36" or "133" or similar shorthand, they mean
`192.168.188.36` or `192.168.188.133`. The facility is all on the
`192.168.188.0/24` subnet. Expand the shorthand to a full IP before
calling the skill.
