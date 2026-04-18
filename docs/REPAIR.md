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
