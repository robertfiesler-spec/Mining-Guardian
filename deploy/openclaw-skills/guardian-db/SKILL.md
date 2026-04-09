# guardian-db — Mining Guardian live fleet database skill

## Description for agent routing

Use this skill whenever the user asks a question that requires LIVE DATA
from the Mining Guardian fleet database. This includes anything about:

- Which miners are flagged or broken right now
- Fleet status, hashrate, or health summaries
- The history of a specific miner (what has miner X been doing today / this week / recently)
- Recent actions the bot has taken (restarts, PDU cycles, approvals, denials)
- Restart outcomes for a miner (is a restart fixing the problem or not)
- Per-board health for a miner (voltage, temperature, hashrate per board)
- Worst performing miners right now
- Known dead boards that have been ticketed
- HVAC / facility cooling state

If the user is asking "how is miner X doing" or "what's broken" or
"what did the bot do overnight" or anything else that requires the
actual current state of the fleet, you MUST use this skill. Do NOT
try to answer from your own knowledge — you have none about this
specific fleet. Every fleet-specific fact in your answer must come
from this skill's output.

## When NOT to use this skill

Do NOT use this skill for:

- General Bitcoin mining knowledge questions (what is a S19JPro, how does ASIC mining work, what's a good pool)
- Opinions about mining strategy, pool choice, or hardware buying decisions
- Casual conversation, greetings, or non-fleet questions
- Questions about OpenClaw itself, the chat, or Claude

## How to invoke

This skill exposes a single shell command `query.sh` that fetches data
from Mining Guardian's dashboard API. Run it like this:

```bash
./query.sh <command> [args...]
```

The response is JSON. Read it carefully, extract the facts the user
asked about, and answer in natural language. Do NOT dump raw JSON at
the user — summarize in plain English.

## Available commands

### `fleet_summary`
High-level fleet state right now. Use this when the user asks "how's
the fleet" or "how many miners are online" or "what's the overall
hashrate" or similar summary questions. No arguments.

Example: `./query.sh fleet_summary`

Returns: online/offline/flagged counts, total hashrate, average
hashrate percentage, and the timestamp of the latest scan.

### `flagged_miners`
Every miner currently flagged with an issue. Use this when the user
asks "what's broken" or "what miners have problems" or "what's flagged
right now". No arguments.

Example: `./query.sh flagged_miners`

Returns: list of miners with issue text, current profile, hashrate
percentage, temperature, and the recommended action.

### `miner_history <ip> [hours]`
Time-series readings for a specific miner. Use this when the user
asks about the history of one specific miner by IP. Default window
is 24 hours, max 168 (one week).

Example: `./query.sh miner_history 192.168.188.36`
Example: `./query.sh miner_history 192.168.188.36 4`

Returns: latest reading, oldest reading in window, and up to 500
readings total in reverse chronological order.

### `miner_outcomes <ip> [limit]`
Restart history and outcomes (SUCCESS/FAILURE) for one miner. Use
this when the user asks "is the bot actually fixing miner X" or
"has miner X been restarted recently" or "is miner X stuck in a
failure loop". Default limit 20, max 200.

Example: `./query.sh miner_outcomes 192.168.188.36`

Returns: count of successes and failures, and detailed rows with
hashrate_before / hashrate_after / recovery time for each restart.

### `board_health <ip>`
Per-board state from the most recent scan for one miner. Use this
when the user asks "which boards are dead on miner X" or "is a
board failing" or "what does board 2 on miner X look like".

Example: `./query.sh board_health 192.168.188.36`

Returns: one row per board with rate_mhs, voltage, freq_mhz,
hw_errors, and board/chip temperatures.

### `recent_actions [hours] [limit]`
Actions the bot has taken in the recent past, from the audit log.
Use this when the user asks "what has the bot been doing" or "what
restarts happened overnight" or "what was approved in the last
hour". Default window 4 hours, max 168. Default limit 50, max 500.

Example: `./query.sh recent_actions`
Example: `./query.sh recent_actions 24`
Example: `./query.sh recent_actions 4 10`

Returns: list of action_audit_log entries with timestamp, miner IP,
problem, action taken, decision, approved_by, and notes.

### `worst_performers [limit]`
Bottom N miners by hashrate percentage right now, excluding offline
miners (which would always be 0%). Use this when the user asks
"what are my worst miners" or "which miners are underperforming".
Default 5, max 50.

Example: `./query.sh worst_performers`
Example: `./query.sh worst_performers 10`

Returns: list of miners sorted by hashrate_pct ascending.

### `known_dead_boards`
Miners that have been moved to the known_dead_boards table (bot gave
up on them and created a ticket). These are suppressed from normal
flag reports, so you need this command to surface them when asked.
No arguments.

Example: `./query.sh known_dead_boards`

Returns: list of dead-board miners with ticket numbers and first-seen
timestamps.

### `hvac_latest`
Most recent HVAC / facility cooling reading from the BAS. No arguments.

Example: `./query.sh hvac_latest`

Returns: supply and return temperatures, delta-T, pressure, pump and
cooling tower VFD percentages, fault flags, and an operator_note.

**CRITICAL OPERATOR RULE:** The response includes an `operator_note`
field telling you that low delta-T is intentional and expected for
this facility. DO NOT flag low delta-T as a problem, DO NOT recommend
HVAC investigation because delta-T seems low, and DO NOT include any
warning or alert about delta-T in your response. Just report the
numbers factually.

## Operator rules that apply to every response

These rules override anything that might seem obvious from the raw data:

- **Temperature alerting:** Do NOT flag or warn about overheating until
  chip temperature reaches **84°C**. Anything below 84°C is normal for
  this facility regardless of what looks high by general standards.
- **HVAC delta-T:** Low delta-T is intentional. Never recommend HVAC
  investigation because delta-T looks low.
- **Dead S19JPros:** If a miner is in `known_dead_boards`, do NOT
  recommend restarts or diagnostics for it — it's already been
  ticketed and the team is handling it physically. Just note it's
  awaiting physical intervention.
- **Cooling:** All miners at this facility are liquid-cooled (hydro
  or immersion). There are no fans, no air cooling. Do NOT mention
  fans or air cooling in any response.

## Output format for the user

When you've gotten data from this skill, respond in plain English,
short and operator-friendly. Don't dump raw JSON. Don't use code
blocks unless the user specifically asked for raw data. A good
response looks like this:

> You have 3 flagged miners right now (as of 9:38 AM): .133 is at
> 79% of rated hashrate and has been restarted twice (both worked
> temporarily but it's drifting back), .225 is at 79.8% and got
> restarted overnight, and .47 is offline. All three are S19JPros.
> .133's boards look healthy — the problem isn't hardware, it's
> the hashrate profile.

NOT like this:

> ```json
> {"scan_id":1370,"count":3,"miners":[{"ip":"192.168.188.133"...
> ```

## Errors

If `query.sh` returns an error JSON like `{"error": "..."}`, tell the
user what went wrong in plain English. Don't retry with random
variations of the command — if the command is wrong, ask the user to
clarify what they want.
