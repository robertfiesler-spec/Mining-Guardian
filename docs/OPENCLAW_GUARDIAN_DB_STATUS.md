# OpenClaw Guardian-DB Skill Status

**Created:** April 13, 2026 ~6:20pm CDT  
**Time Invested:** 1 hour  
**Status:** INFRASTRUCTURE COMPLETE, DISCOVERY TESTING NEEDED

## What Works ✅

1. **Skill files correctly placed** — `/data/.openclaw/skills/guardian-db/` in container
2. **All 9 API endpoints functional** — dashboard_api.py /query/* endpoints verified
3. **Skill executes successfully** — Tested `query.sh fleet_summary`, returns live JSON
4. **OpenClaw Socket Mode connected** — Slack connectivity active
5. **Container restarted** — Fresh boot completed, nativeSkills: auto enabled

## Skill Commands Available

The guardian-db skill exposes 9 commands via query.sh:

1. **fleet_summary** — High-level fleet state (online/offline/flagged counts, hashrate)
2. **flagged_miners** — All miners currently with issues
3. **miner_history <ip> [hours]** — Time-series readings for specific miner
4. **miner_outcomes <ip> [limit]** — Restart history and SUCCESS/FAILURE outcomes
5. **board_health <ip>** — Per-board state for one miner
6. **recent_actions [hours] [limit]** — Actions from audit log
7. **worst_performers [limit]** — Bottom N miners by hashrate %
8. **known_dead_boards** — Miners with tickets, suppressed from reports
9. **hvac_latest** — Most recent HVAC/facility cooling reading

All commands tested manually in container — all return proper JSON.

## Discovery Issue ❓

OpenClaw config shows `"nativeSkills": "auto"` which should auto-discover skills in `/data/.openclaw/skills/`. However, we havent yet tested if the LLM can actually SEE and USE the guardian-db skill when responding to Slack messages.
