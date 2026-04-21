# Mining Guardian — Repair & Maintenance Log

**Last Updated:** 2026-04-17

---

## Active Repair Queue

### Miner 53521 — CRITICAL
| Field | Value |
|-------|-------|
| IP | 192.168.188.12 |
| Model | Antminer S19JPro |
| Status | FAILING |
| Identified | 2026-04-16 |
| Source | Daily Deep Dive AI Analysis |

**Problem:**
All 3 hashboards showing 0/126 ASICs detected with 126 bad chips each.

**AI Analysis:**
- Miner enters emergency sleep mode repeatedly
- Multiple restarts have not resolved the issue
- 75% restart success rate (degraded)

**Action Required:**
1. Physical inspection
2. Check for loose connections
3. Likely needs board replacement

---

## Repair History

| Date | Miner | Issue | Resolution |
|------|-------|-------|------------|
| 2026-04-16 | 53521 | All hashboards failing | PENDING |

---

## System Updates Log
### 2026-04-18

**Deep Dive Prompt Size Fix (CRITICAL):**
- ROOT CAUSE: yesterday_log was pulling old 1.1MB unfiltered logs from days ago
- PLUS: Operator rules grew to 12KB after adding detailed pattern rules
- RESULT: Prompts were 86K chars, exceeding 45K limit

**Fixes Applied:**
1. REMOVED yesterday_log lookup - set to None
   - 1PM cron provides fresh daily logs, no need for old comparison
2. REDUCED MAX_LOG_CHARS from 60K to 30K
3. CAPPED operator rules to 2K chars in prompt (first line of each rule only)
4. RESULT: Prompts now ~35K chars, well under 45K limit

**Before:** 86,394 chars = SKIPPED
**After:** 35,417 chars = PROCESSING

**Operator Rules Added:**
1. Rule 8: APPROVAL REQUIRES EXPLANATION
2. Rule 9: PCB/BOM QUALITY GATE + CASCADE FAILURE (with full hardware detail)
3. Rule 10: S19J PRO RESTART PROTOCOL
4. Rule 11: FLEET INVENTORY AUDIT TRIGGER

**Pattern Rules Added:**
1. CHIP_QUALITY_DEGRADATION_PATTERN
2. PSU_VOLTAGE_DEGRADATION_PATTERN

**New Process Established:**
- Daily operator review of AI proposals
- All YES/NO decisions require explanation
- Patterns, not miners - rules describe situations
- More detail always - model, manufacturer, serial patterns, IPs

**Git Commits:**
- 3f53110: fix: Cap operator rules in deep dive prompt to 2K chars
- f6c38ea: fix: Remove yesterday log from deep dive
- e81f9e9: skip: Stock firmware miners excluded from log collection
- 134737a: docs: Add comprehensive OPERATOR_RULES.md
- 6c0dae0: rule: Add APPROVAL REQUIRES EXPLANATION rule

---



### 2026-04-17

**Log Filtering Added:**
- File: scripts/direct_collect_logs.py
- Filters out 50K+ frequency tuning lines per day
- Removes PSU polling, CPU stats, temp reading spam
- Expected: 3MB logs reduced to ~200KB

**Date Filtering Added:**
- Miners return multiple days even when requesting specific date
- Now filters to only keep lines from target date
- Result: 1.9MB logs reduced to ~400KB (80% reduction)

**Prompt Cap Working:**
- 45K char limit in ai/daily_deep_dive.py
- 23 miners skipped (had 86K char prompts)
- 14 miners fully analyzed
- No more 60-90 min per-miner hangs

**Cron Schedule Fixed:**
- AMS cleanup moved from 10:00 to 12:45
- Now runs 15 min before log collection
- Prevents queue overflow issues

**Training Complete:**
- 18 cohorts processed
- 2 new insights added
- 104 miner fingerprints built
- Refinement chain Pass 3+4 complete

---

## Escalation Criteria

A miner should be added to the repair queue when:

1. **AI Deep Dive** flags it as failing with hardware issues
2. **3+ consecutive restart failures** in overnight automation
3. **Dead board** detected and confirmed
4. **Known issues** table shows repeated failures for same problem
5. **Manual operator observation** of physical problems

---

## Integration with Mining Guardian

### Automatic Detection
- Daily Deep Dive analyzes all miners and flags failing units
- Overnight automation tracks restart failures
- Dead board detection creates AMS tickets automatically

### Tables Involved
- known_dead_boards: Miners with confirmed dead boards
- miner_restarts: Restart history and success rates
- llm_analysis: AI analysis results
- action_audit_log: All operator interventions

### Slack Notifications
- Failing miners flagged in #mg-ai-reports
- Dead board tickets in #mg-alerts
- Deep dive reports sent to operator DM

### 2026-04-18 (Evening Session)

**Operator Review Session Completed:**
All 21 AI proposals reviewed with operator decisions logged.

**Knowledge Base Restructured:**
- Created `process_rules` section for workflow rules
- Created `hardware_facts` section for known quantities
- Operator rules reduced from 13 to 6 (lean and focused)

**Pattern Rules Created (4 total):**
1. CHIP_QUALITY_DEGRADATION_PATTERN
2. PSU_VOLTAGE_DEGRADATION_PATTERN  
3. COMPLETE_HARDWARE_FAILURE_PATTERN
4. PSU_PARTIAL_CIRCUIT_FAILURE_PATTERN

**Key Decisions:**
- Rule 1 changed from time-based (20 min) to status-based (wait for MINING)
- Offline miner logic merged into COMPLETE_HARDWARE_FAILURE_PATTERN
- AMS log cleanup removed (we bypass AMS, collect directly from miners)
- CT fans, overheating, warehouse miners moved to hardware_facts
- Validation workflow moved to process_rules

**Cron Schedule Updated:**
- Claude training: midnight → 3 AM
- Refinement chain: 1 AM → 4 AM
(Gives deep dive time to complete)

**Deep Dive Fix Verified:**
- Prompt size: 86K → 35K chars ✅
- S19JPros now processing instead of skipping
- Per-miner time: ~110 min (longer than expected but working)


### 2026-04-21

**Hashrate Units Fix (dashboard_api.py):**
- ROOT CAUSE: Database stores hashrate in MH/s, API was returning raw values
- Display needed TH/s (divide by 1000)

**Endpoints Fixed:**
- /metrics (SQL + Python)
- /query/fleet_summary (total_hashrate, total_max_hashrate)
- /query/flagged_miners
- /query/miner_history
- /query/bottom_miners
- /ask

**Verification:** /query/fleet_summary returns total_hashrate_ths: 3871.7 ✅

**Git Commit:** 332134e

---

**Firmware Detection Fix (core/mining_guardian.py):**
- ROOT CAUSE: AMS API returns empty firmware fields for offline miners
- AMS cannot query device firmware when miner isn't communicating
- 20 miners showed empty firmware_manufacturer/firmware_version

**Discovery:**
- All 20 miners with empty firmware were OFFLINE
- Historical data in miner_readings showed firmware when miners were online
- Example: 192.168.188.52 had BIXBIT/0.9.9.3-stage29.2799 on April 13

**Fix Applied:**
- Added fallback logic in save_scan() (lines 2234-2272)
- If AMS returns empty firmware, query miner_readings for last known value
- Use historical firmware instead of empty string

**Verification:**
- Before: 29/49 miners with firmware (only online miners)
- After: 49/49 miners with firmware ✅
- All 20 offline miners now show historical firmware

**Git Commit:** 557e037

---

**AV-2 Plant Client Implementation:**
- PROBLEM: S19J Pro Container HVAC (192.168.189.235) had no data collection
- Previously just a stub returning None

**API Discovery (via Chrome DevTools):**
- Endpoint: POST https://192.168.189.235/eclypse/dgapi
- Auth: Session-based + Basic (BigStar/BigSt@r2020)
- Framework: Distech DGLux (dgluxjs)
- Format: Subscription-based polling model

**Data Paths Implemented:**
| Path | Description |
|------|-------------|
| /Data/Plant/OAT | Outside Air Temp (°F) |
| /Data/Plant/ContainerSpaceTemp | Container Ceiling (°F) |
| /Data/Plant/CDWST | Supply Temp (°F) |
| /Data/Plant/CDWRT | Return Temp (°F) |
| /Data/Plant/CWP1_Fdbk | CW Pump 1 Speed (%) |
| /Data/Plant/CWP2_Fdbk | CW Pump 2 Speed (%) |
| /Data/Plant/CT1VSDFdbk | CT Fan Speed (%) |

**Note:** VPS cannot reach 192.168.189.x directly - requires ROBS-PC Tailscale route.

**Git Commit:** aa4830e

---

**GitHub Security:**
- Enabled Secret Protection on Mining-Guardian repo
- Push protection + Alert scanning now active

