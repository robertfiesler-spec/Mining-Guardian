# Session Log — April 13, 2026

## Summary
Integrated S19J Pro container HVAC system into Mining Guardian. All AI analysis now correlates miners with their correct cooling system.

## Major Accomplishments

### 1. S19J Pro HVAC Integration
- Added second HVAC system at 192.168.189.235
- Mac HVAC collector polls both systems every 5 minutes
- VPS API receives and stores readings by system_id

### 2. AI Script Updates
All AI scripts now use the correct HVAC system per miner:
- daily_deep_dive.py — Per-miner HVAC selection
- local_llm_analyzer.py — Shows both systems in prompts
- predictor.py — System-aware predictions
- action_diversity.py — Fleet-level analysis
- hvac_correlator.py — System-aware correlation

### 3. Operator Rule #5 Added
S19J Pro CT fans are manually at 100% — no VFD feedback shown. This is intentional, NOT a fault.

### 4. Documentation Created/Updated
- NEW: docs/HVAC_SYSTEMS.md — Complete HVAC documentation
- NEW: docs/OPERATOR_RULES.md — All operator rules in one place  
- UPDATED: docs/WAREHOUSE_MECHANICAL.md — References new docs
- UPDATED: docs/CRON_SCHEDULE.md — Added Mac HVAC collector

## System Mapping Rule

Simple rule: S19JPro -> s19jpro system. Everything else -> warehouse.

| Miner Type | HVAC System | IP |
|------------|-------------|-----|
| S19JPro | s19jpro | 192.168.189.235 |
| Everything else | warehouse | 192.168.188.235 |

## Current HVAC Readings

| System | Supply | Return | Delta-T | Notes |
|--------|--------|--------|---------|-------|
| Warehouse | 75F | 86F | 11F | Normal |
| S19J Pro | 89F | 103F | 14F | Running warmer |

## Commits
- 43ac433 — feat: add S19J Pro HVAC system integration
- 0b3aab9 — fix: wire all AI scripts to use correct HVAC per miner
- 9d4ece4 — docs: add S19J Pro CT fan note

## Services Status
- mining-guardian.service - RUNNING
- dashboard-api.service - RUNNING
- com.bixbit.hvac-collector (Mac launchd) - RUNNING

## Files Changed (VPS)
- ai/action_diversity.py
- ai/daily_deep_dive.py
- ai/hvac_correlator.py
- ai/local_llm_analyzer.py
- ai/predictor.py
- api/dashboard_api.py
- clients/hvac_client.py
- config.json
- knowledge.json
- docs/CRON_SCHEDULE.md
- docs/HVAC_SYSTEMS.md
- docs/OPERATOR_RULES.md
- docs/WAREHOUSE_MECHANICAL.md

## Mac Files Created
- /Users/BigBobby/Documents/GitHub/mac-scripts/hvac_collector.py
- /Users/BigBobby/Library/LaunchAgents/com.bixbit.hvac-collector.plist

---
*Session started: ~3:30 AM CDT*
*Session ended: ~5:15 AM CDT*


---

## Session 2 — Morning Fixes (05:35 CDT)

### Issues Fixed

1. **Log Failure Reports to mg-logs**
   - Problem: Log failure reports from daemon were going to mining-guardian
   - Fix: Changed post_to_channel to post_to_logs on line 5103
   - Commit: e886720

2. **Grafana Recent AI Analyses Panel**
   - Problem: Panel showed DOCTYPE is not valid JSON error
   - Cause: Relative URL did not work via grafana.fieslerfamily.com
   - Fix: Updated panel to use absolute URL for dashboard API

3. **AI Analysis Confidence Scores**
   - Problem: Reports did not show confidence percentages
   - Fix: Updated LLM prompt in local_llm_analyzer.py to request per-miner confidence
   - Format: - **[IP]** XX confidence: [issue and reason]

### Operator Rule 6 Added
- S19J Pro Overheating Boards - Aging Hardware
- Try ONE restart with log capture before/after
- If restart does not help, mark as aging and let run
- New table: s19jpro_overheat_tracking
- Commit: 7e7c6d8

### Services Restarted
- mining-guardian.service - Active
- dashboard-api.service - Active


---

## Session 3 — S19J Pro HVAC in Scans (06:00 CDT)

### Changes Made
Daemon now includes BOTH HVAC systems in every scan context sent to Qwen.

**What Changed:**
1. Import: Added poll_all_systems from hvac_client
2. Polling: Calls poll_all_systems() to get both warehouse and s19jpro
3. Context: hvac_data dict now contains both systems:
   - warehouse: supply_f, return_f, delta_t
   - s19jpro: supply_f, return_f, delta_t, container_f, outside_air_f
4. System prompt: Explains "TWO HVAC systems"
5. Output label: "HVAC (both systems)"

**Commit:** 086c6bf

### Verified Working
- Mac HVAC collector pushing both systems every 5 min
- VPS receiving POST /api/hvac/ingest for both
- Database has readings for warehouse and s19jpro
- Scan #1473 completed at 06:04 with 49 miners

### Current HVAC Readings (06:04)
| System | Supply | Return | Delta-T |
|--------|--------|--------|---------|
| Warehouse | 75F | 86F | 11F |
| S19J Pro | 89F | 104F | 15F |

### All Commits Today (9 total)
1. 43ac433 — feat: add S19J Pro HVAC system integration
2. 0b3aab9 — fix: wire all AI scripts to correct HVAC per miner
3. 9d4ece4 — docs: add S19J Pro CT fan note
4. df699ca — docs: comprehensive HVAC systems documentation
5. e3e18d5 — docs: add S19J Pro HVAC fix to REPAIR_LOG
6. 7e7c6d8 — feat: add operator rule #6 - S19J Pro aging hardware
7. e886720 — fix: AI analysis improvements
8. d565a27 — docs: add session 2 fixes to log
9. 086c6bf — feat: include S19J Pro HVAC data in scans

### Services Status
All services running and healthy.
