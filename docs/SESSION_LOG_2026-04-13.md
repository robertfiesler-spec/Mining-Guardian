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
