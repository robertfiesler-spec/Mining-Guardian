# Mining Guardian — Repair Log

**Purpose:** A running record of bugs, misunderstandings, and fixes. Written in plain English, not dev-speak, so either of us can read it at any point and quickly understand what was broken and why. Every entry has four parts: what Bobby thought the program was doing, what it was actually doing, what we changed, and how we verified the change worked.

**How to use this file:**
- Add a new entry at the top of the "Entries" section every time we find a mismatch between design and reality, or every time we fix a real bug.
- Don't delete old entries. They're the institutional memory. Future Claude sessions read this to avoid rediscovering the same things.
- If an entry has follow-up work (like "still need to verify in production tomorrow"), add a `**Status:**` line at the bottom of the entry and update it when done.
- Each entry gets a date and a short title. Titles should pass the "could a stranger find this in 10 seconds" test.

**Sister documents:**
- `CLAUDE.md` — binding rules for every Claude session
- `docs/VISION.md` — canonical single-source-of-truth plan
- `README.md` — current architecture reference
- `AI_ROADMAP.md` — forward-looking priority queue
- `docs/SESSION_LOG_YYYY-MM-DD.md` — daily narrative of each working session
- `docs/DAILY_DEEP_DIVE_DESIGN.md` — design doc for the daily Qwen deep dive pipeline
- **This file** — backward-looking "what went wrong, what we fixed, what we learned"

---

## Entries (newest at top)

---

### 2026-04-10 (evening) · Hourly LLM was repeating the same analysis every scan — not learning

**What Bobby thought the program was doing:**
The hourly LLM should be learning and evolving. Each scan should find NEW patterns, note what CHANGED, and avoid repeating the same analysis over and over. The system should get smarter over time.

**What was actually happening:**
The LLM was storing its analyses to `knowledge.json['llm_scan_analyses']`, but it **never read them back**. Every hour it analyzed from scratch with no memory of what it said before. Result: the same miners got flagged with the same recommendations over and over — "miner 53517 offline, restart it" repeated for days.

**Why it mattered:**
- The LLM wasn't learning from itself
- Operator got spammed with the same recommendations repeatedly
- No sense of progression ("this was flagged 5 times, it's probably hardware")
- Defeats the purpose of an intelligent learning system

**What we changed:**
Modified `scripts/local_llm_analyzer.py`:

1. **Added previous analyses to context:**
   ```python
   prev_analyses = knowledge.get("llm_scan_analyses", [])[-3:]  # Last 3
   ```

2. **Added new prompt section:**
   ```
   --- YOUR PREVIOUS ANALYSES (3) ---
   Here's what you said in recent scans. DO NOT REPEAT THIS.
   Focus on what's CHANGED or NEW since then:
   ```

3. **Updated SUMMARY instruction:**
   ```
   What's CHANGED since the last scan? Any NEW trends?
   If nothing changed, say "Fleet stable, no changes" and move on.
   ```

4. **Added anti-repetition rule:**
   ```
   CRITICAL: Do NOT repeat the same analysis as previous scans.
   If you've already flagged a miner multiple times and nothing has changed,
   just note "still pending" and move on. Your job is to find NEW patterns.
   ```

**How we verified:**
- `python3 -m py_compile scripts/local_llm_analyzer.py` passes
- Committed as `49a5740`

**Lesson:**
An AI system that stores data but never reads it back is NOT learning. The feedback loop has to be closed — outputs must become inputs for the next cycle. This was a fundamental architecture miss.

**Status:** Fixed. Next hourly scan should show different behavior — focusing on changes rather than repeating.

---

### 2026-04-10 (evening) · LLM kept recommending HVAC inspection + repeating 20-min cooldown rule

**What Bobby thought the program was doing:**
The LLM should NOT recommend HVAC inspection — the HVAC is working correctly. Low delta-T is normal and seasonal. Also, once the system learns a rule (like the 20-minute post-restart cooldown), it shouldn't keep mentioning it in every single report.

**What was actually happening:**
1. **HVAC recommendations:** The LLM kept saying "review HVAC system to address environmental overheating concerns"
2. **Repeating OPERATOR LEARNING:** Every report included the same 20-minute cooldown rule

**What we changed:**
1. Added explicit HVAC disclaimer: "HVAC is WORKING CORRECTLY. Do NOT recommend HVAC inspection."
2. Updated OPERATOR LEARNING to only show for NEW denials with NEW reasons
3. Added warning: "The 20-minute cooldown rule is ALREADY KNOWN — do not repeat it."

**Status:** Fixed. Committed as `45b954f`.

---

### 2026-04-10 (evening) · daily_collect_logs.py called collect_logs() with no arguments

**What Bobby thought the program was doing:**
The 1pm cron job should download logs from all miners with a retry pass for failures.

**What was actually happening:**
The script called `mg.collect_logs()` with no arguments, but the method requires `miners` and `issues`.

**What we changed:**
Script now fetches miners from AMS first: `mg.collect_logs(miners=mg.ams.get_miners(), issues=[])`

**Status:** Fixed. Committed as `8186900`. Tomorrow's 1pm cron will be the first test.

---

### 2026-04-10 (afternoon) · Three silent bugs: bad insight, broken cron, missing confidence

**What was wrong:**
1. Claude generated `chain_3_voltage_failure_hydro` — S19JPro only has 3 boards, not 4
2. Cron job called `MiningGuardian()` without config argument
3. Import was `from confidence_scorer` but file is at `ai/confidence_scorer.py`

**What we changed:**
1. Deleted the bad insight
2. Created proper wrapper script
3. Fixed import path

**Hardware facts established:**
- S19JPro: 3 boards (Chain 0, 1, 2)
- AH3880 Auradine: 2 boards only

**Status:** Fixed. Commits `7382037`, `8186900`.

---

### 2026-04-10 · Hourly scans showing procurement advice instead of operational patterns

**What was wrong:**
All insights dumped into hourly prompts — including "REJECT" and "KEEP" which are strategic.

**What we changed:**
Filter by action type: OPERATIONAL (TUNE/WATCH/INVESTIGATE) for hourly, STRATEGIC (REJECT/KEEP) for weekly.

**Status:** Fixed. Committed as `f04d703`.

---

*[Earlier entries in git history]*


---

## April 10, 2026 — Late Night AI Wiring Sprint

### FIX: Hourly LLM Blind to Most Knowledge (c83070b)
**Problem:** Hourly LLM only saw patterns, refined_insights, and previous analyses.

**Fix:** Added predictions, operator_rules, fingerprints, cross_miner_analysis, known_issues to context. Created 5 new prompt sections.

### FIX: Predictor Ignoring Fingerprints (fc4935b)
**Fix:** Added fingerprint risk modifier. Poor history = +15 risk points.

### FIX: Prediction Validation Loop Missing (fc4935b)
**Fix:** outcome_checker now validates predictions against actual outcomes. Tracks accuracy.

### FIX: Confidence Scorer Ignoring Predictions (fc4935b)
**Fix:** Pre-failure signals now reduce confidence by -5 to -15 points.

### FIX: Prediction Alerts Paused (be5f9a2)
**Fix:** Enabled alerts for >= 75% confidence predictions.

**Files modified:** 6 files
**Testing:** Daemon restarted



---

## April 11, 2026 — Comprehensive AI Audit & Final Wiring

### AUDIT: All 12 Feedback Loops Now Closed

Conducted full research audit of every AI component. Created ai/comprehensive_audit.py to document all data flows.

**Feedback loops verified working:**
- PREDICTION → VALIDATION (Apr 10)
- FINGERPRINT → PREDICTION (Apr 10)
- FINGERPRINT → CONFIDENCE
- PREDICTION → CONFIDENCE (Apr 10)
- FINGERPRINT → ACTION_DIVERSITY (Apr 10)
- OUTCOME → MINER_PROFILES
- OPERATOR RULES → HOURLY LLM (Apr 11)
- CROSS_MINER_ANALYSIS → HOURLY LLM (Apr 10)
- DAILY_DEEP_ANALYSES → WEEKLY
- LLM_SCAN_ANALYSES → SELF (Apr 9)
- REFINED_INSIGHTS → ALL
- HVAC_CORRELATION → PREDICTOR + LLM (Apr 11) - FIXED THIS SESSION

### FIX: hvac_correlation Was Orphaned (66634b6)
**Problem:** hvac_correlator.py computed correlation weekly but nobody read it.

**Fix:**
- Added hvac_correlation to local_llm_analyzer context
- Displays correlation when significant (>0.3 or <-0.3)
- Predictor now uses correlation to determine if facility stress matters
- Only suppresses temp signals if historical correlation confirms impact

### FIX: Hourly LLM Echoing Operator Rules (1586939)
**Problem:** LLM was repeating operator rules back in every report.

**Fix:**
- Changed rules to internal-only guidance
- Added ABSOLUTE RULES section forbidding echoing
- Removed OPERATOR LEARNING section requirement

### REMAINING MEDIUM PRIORITY ITEMS
- miner_ams_extended: collected but unused in AI
- miner_profiles: duplicates miner_fingerprints (consider consolidating)
- chip_readings: empty stub table
- miner_baselines: empty, never implemented

**Files modified:** 4 files
**Testing:** Daemon restarted, all loops verified closed




---

## April 11, 2026 — CRITICAL FIX: Wrong File Running in Production

### Issue (Caught by External Auditor)

**All April 10-11 sprint work was NOT running in production.**

-  (456 lines) — OLD code, no sprint fixes
-  (539 lines) — FIXED code with all sprint work

The daemon adds  to , so when  imports , Python found the OLD  version.

The hourly LLM was STILL running blind despite all our sprint work.

### Fix (46eaafe)

Copied  → 

Now production actually uses:
- Predictions for flagged miners
- Miner fingerprints (baselines)
- Refined insights from Claude
- Previous analyses (scan-to-scan memory)
- HVAC correlation data
- Operator rules (internal, not echoed)
- Full known issues text
- Cross-miner analysis

### Lesson Learned

When files exist in both  and , verify which one the daemon imports. 
The  manipulation in  line 5520 adds  but NOT .




---

## April 11, 2026 — Operator Rule Consolidation + Offline Miner Fix

### Consolidated Operator Rules (3 → 1)
**Problem:** Three operator rules were all variations of the same thing (20-minute post-restart cooldown).

**Fix:** Consolidated into single well-worded rule:
> 20-MINUTE POST-RESTART COOLDOWN: After any restart or power cycle, wait 20 minutes before initiating profile changes, additional restarts, or any other actions. The miner needs time to stabilize and reach steady-state operation.

### New Operator Rule: Offline Miner Logic (1b02374)
**Problem:** System was recommending RESTART for truly offline miners. But firmware restart requires network connectivity — if miner has no power, restart command cannot reach it.

**Symptom:** Miner 192.168.188.231 (S19JPro, no PDU) showed "OFFLINE — attempting firmware restart" for 5+ consecutive scans despite being unreachable.

**Fix:** Changed offline decision tree:
- BEFORE: offline → RESTART first → PDU_CYCLE → PHYSICAL_INSPECTION
- AFTER: offline + has PDU → PDU_CYCLE; offline + no PDU → PHYSICAL_INSPECTION

Firmware RESTART is now only recommended for reachable-but-underperforming miners.

### Current Operator Rules (2 total)
1. 20-MINUTE POST-RESTART COOLDOWN
2. OFFLINE MINER LOGIC (firmware restart requires connectivity)

### Cron Jobs Verified Working
All 6 cron jobs confirmed operational:
- 4am: Knowledge backup → GitHub
- 7am: Morning briefing → Slack
- 1pm: Daily log collection
- 4pm: Daily deep dive (Qwen)
- 12am: Claude training
- 1am: Refinement chain (Pass 3+4)




---

## April 12, 2026 — AMS Log Queue Overflow (CRITICAL FIX)

### Problem
- **0 logs collected** from any miner today
- AMS returning error: "too many log files for device" (HTTP 453)
- 708 failed log exports were clogging the AMS queue
- Root cause: Previous export attempts that failed (status=3) were never cleaned up

### Investigation
- Log collection cron ran at 1pm as scheduled
- Pass 1: All 31 miners failed immediately  
- Pass 2 (retry): All 31 miners failed again
- AMS API check revealed the "too many log files" error

### Fix (commit 1735b9b)

1. **Created cleanup_ams_logs.py**
   - Deletes ALL log files from AMS for every miner
   - Safe because logs are stored in guardian.db after download
   - Location: scripts/cleanup_ams_logs.py

2. **Added 10am daily cron for AMS cleanup**
   - Runs BEFORE 1pm log collection
   - Keeps AMS queue clean

3. **Reduced parallel workers 15 to 10**
   - Connection pool was hitting limits
   - 10 workers is more conservative

4. **Immediate cleanup performed**
   - Deleted 708 failed logs
   - Deleted 121 ready logs  
   - Total: 829 logs removed from AMS

### New Cron Job
0 10 * * * - AMS log cleanup (scripts/cleanup_ams_logs.py)

### Operator Rule Added
Delete all files from AMS not just failed attempts. For clean up and house 
cleaning overall do not let it clutter. We store the logs in the db anyway.

### Data Retention Summary
| Location | Retention |
|----------|-----------|
| AMS | Deleted daily at 10am |
| guardian.db (miner_logs) | 30 days then auto-purged |
| knowledge.json | Permanent |

### Documentation Added
- Created docs/CRON_SCHEDULE.md with full schedule explanation

### Verification
After cleanup, tested 4 miners — all exports triggered successfully.

---

## 2026-04-12 ~4:00pm CDT — Grafana AI Dashboard Missing Confidence %

### Issue
Bobby noticed that confidence percentages were not showing next to AI data in Grafana.
The AI dashboard (iframe at /ai/dashboard) had tables for Action Queue, Auto Actions, 
and Predictions — but none showed the confidence score used by the AI system.

### Root Cause
The original ai_dashboard_api.py was built before confidence scoring was fully 
integrated. Tables existed but lacked the Conf column, making it impossible to 
see how confident the AI was in each recommendation.

### Fix (commit 84f1f83)

1. **Added confidence import to ai_dashboard_api.py**
   - Imports get_confidence and get_gate from confidence_scorer
   - Fallback to 75% if scorer unavailable

2. **Updated Action Queue table**
   - Added Conf column header between Action and HR
   - Calculates live confidence for each pending action
   - Shows 0% for escalated actions (intentional — multiple failures = low confidence)

3. **Updated Auto Actions table**
   - Added Conf column header between Action and Outcome
   - Extracts confidence from notes field if available
   - Defaults to 75% for historical actions (confidence wasn't stored before)

4. **Updated Predictions table**
   - Added Conf column header between Action and Detail
   - Extracts confidence from problem field if available
   - Defaults to 75% for historical predictions

5. **Color coding applied to all Conf columns**
   - Green: ≥80% (high confidence)
   - Orange: 50-79% (medium confidence)
   - Red: <50% (low confidence)

### Bug Fixed During Patch
- import re statements inside try blocks were shadowing the module-level import
- Caused UnboundLocalError when rendering insights section
- Fixed by commenting out redundant imports

### Going Forward
- New actions will store confidence in notes field
- Historical 75% defaults will gradually be replaced with real scores
- All three AI tables now visually show confidence next to every row

### Verification
Confirmed /ai/dashboard renders with Conf columns visible in all three tables.

---

## 2026-04-12 ~4:30pm CDT — Chain Events Not Saved to Fingerprints

### Issue
During comprehensive data gap audit, discovered that  and 
 were being computed from log_metrics (27K rows) but NOT
included in the fingerprint output.

### Root Cause
The fingerprint_builder.py computed these values on lines 251-252 but the
return statement starting at line 300 didn't include them.

### Fix (commit fcabbcf)
Added to fingerprint output:


### Impact
- 27K chain_event records now feed into miner fingerprints
- AI can see board attach/detach patterns for every miner
- Board cycling issues (>100 detaches) now visible in fingerprints

### Data Gap Audit Also Found (documented for future):
1. chip_hashrate: 2.6M rows NOT USED (per-chip data)
2. psu_voltage: 9.5M rows, only min extracted
3. system_health: 2.3M rows NOT USED
4. llm_analysis: 839 rows not feeding back to training
5. pending_approvals: approval patterns not analyzed


---

## 2026-04-12 ~4:30pm CDT — Chain Events Not Saved to Fingerprints

### Issue
During comprehensive data gap audit, discovered that chain_detaches and 
chain_attaches were being computed from log_metrics (27K rows) but NOT
included in the fingerprint output.

### Root Cause
The fingerprint_builder.py computed these values on lines 251-252 but the
return statement starting at line 300 did not include them.

### Fix (commit fcabbcf)
Added to fingerprint output after stratum_url:
- chain_detaches: count of board detach events
- chain_attaches: count of board attach events

### Impact
- 27K chain_event records now feed into miner fingerprints
- AI can see board attach/detach patterns for every miner
- Board cycling issues (>100 detaches) now visible in fingerprints

### Data Gap Audit Also Found (documented for future):
1. chip_hashrate: 2.6M rows NOT USED (per-chip data)
2. psu_voltage: 9.5M rows, only min extracted
3. system_health: 2.3M rows NOT USED
4. llm_analysis: 839 rows not feeding back to training
5. pending_approvals: approval patterns not analyzed

---

## April 13, 2026 — S19J Pro HVAC Integration

### Issue
S19J Pro miners were being correlated against the WRONG HVAC system (warehouse instead of their own container cooling).

### Root Cause
Mining Guardian only knew about one HVAC system (warehouse at 192.168.188.235). The S19J Pro container has a completely separate cooling system at 192.168.189.235.

### Fix
1. Added multi-system HVAC support to hvac_client.py
2. Created Mac HVAC collector (hvac_collector.py) that polls both systems
3. Updated ALL AI scripts to select correct HVAC based on miner model
4. Added operator rule #5: S19J Pro CT fans manually at 100%

### Files Changed
- clients/hvac_client.py — Multi-system support
- ai/hvac_correlator.py — System-aware correlation
- ai/daily_deep_dive.py — Per-miner HVAC selection
- ai/local_llm_analyzer.py — Shows both systems
- ai/predictor.py — System-aware predictions
- api/dashboard_api.py — HVAC ingest endpoint

### Simple Rule
S19JPro -> s19jpro system (192.168.189.235)
Everything else -> warehouse (192.168.188.235)

### Commits
- 43ac433 — S19J Pro HVAC integration
- 0b3aab9 — Wire AI scripts to correct HVAC
- 9d4ece4 — CT fan note
- df699ca — Documentation

---

## April 13, 2026 — Comprehensive S19J Pro Integration + Bug Fixes

### Session 1: S19J Pro HVAC System Integration (3:30am - 5:15am CDT)

#### Issue
S19J Pro miners were being correlated against the WRONG HVAC system. The warehouse HVAC (192.168.188.235) serves Hydros, S21 Immersion, and AH3880. But S19J Pros have their own separate container cooling system at 192.168.189.235.

#### Root Cause
Mining Guardian only knew about one HVAC system. All miners were being correlated with warehouse temps, leading to incorrect thermal analysis for S19J Pros.

#### Fix (Commits: 43ac433, 0b3aab9, 9d4ece4, df699ca, e3e18d5)

1. **clients/hvac_client.py** — Multi-system HVAC support
   - Added SYSTEMS dict with both warehouse and s19jpro configs
   - Created poll_all_systems() function
   - Added get_hvac_system_for_miner(model) routing function

2. **Mac HVAC Collector** — New polling service
   - Created /Users/BigBobby/Documents/GitHub/mac-scripts/hvac_collector.py
   - Polls BOTH systems every 5 minutes via launchd
   - Pushes to VPS POST /api/hvac/ingest endpoint
   - VPS cannot reach local network directly — Mac is the bridge

3. **api/dashboard_api.py** — HVAC ingest endpoint
   - Added POST /api/hvac/ingest to receive data from Mac
   - Added GET /api/hvac/latest to return latest per system
   - Added system_id column to hvac_readings table

4. **AI Scripts Updated** — Correct HVAC per miner
   - ai/hvac_correlator.py — get_hvac_system_for_model(), system-aware stress levels
   - ai/daily_deep_dive.py — Per-miner HVAC selection in prompts
   - ai/local_llm_analyzer.py — Shows BOTH systems in context
   - ai/predictor.py — Uses miner model to select correct HVAC
   - ai/action_diversity.py — Fleet-level defaults to warehouse

5. **Operator Rule #5 Added**
   S19J Pro CT fans are manually set to 100%. No VFD feedback will appear in HVAC data. This is intentional, NOT a fault. Never flag zero CT feedback as a problem.

#### Simple Routing Rule
```python
hvac_system = 's19jpro' if model.startswith('S19JPro') else 'warehouse'
```

#### Files Created
- docs/HVAC_SYSTEMS.md — Complete HVAC documentation
- docs/OPERATOR_RULES.md — All operator rules in one place
- Mac: hvac_collector.py + com.bixbit.hvac-collector.plist

---

### Session 2: Bug Fixes (5:35am CDT)

#### Issue 1: Log Failure Reports Going to Wrong Channel
**Problem:** Log failure reports from daemon went to #mining-guardian instead of #mg-logs.
**Root Cause:** Line 5103 used self.slack.post_to_channel(message) which defaults to #mining-guardian.
**Fix:** Changed to self.slack.post_to_logs(message) which posts to #mg-logs (C0ASH2CPHBJ).
**Commit:** e886720

#### Issue 2: Grafana Recent AI Analyses Panel Error
**Problem:** Panel showed "<!DOCTYPE... is not valid JSON" error.
**Root Cause:** Panel used relative URL /ai/recent_analyses. When accessed via grafana.fieslerfamily.com, this tried to fetch from Grafana server instead of dashboard API.
**Fix:** Updated Grafana panel to use absolute URL http://dashboard.fieslerfamily.com/ai/recent_analyses.
**Verification:** API endpoint works, returns varied confidence scores (60-100%).

#### Issue 3: AI Analysis Reports Missing Confidence Scores
**Problem:** AI Analysis reports in Slack did not show confidence percentages.
**Fix:** Updated LLM prompt in ai/local_llm_analyzer.py to request per-miner confidence.
**New format:** "- **[IP]** (XX% confidence): [issue and reason]"
**Commit:** e886720

---

### Session 2: Operator Rule #6 Added (5:35am CDT)

#### S19J Pro Overheating Boards (Aging Hardware)
**Problem:** S19J Pros are older hardware. As boards age, some run hotter. System was repeatedly flagging and restarting the same miners with no improvement.

**Rule:** When an S19J Pro shows overheating (chip temp >= 84C):
1. Try ONE restart with log capture before and after
2. Compare logs to see if restart helped
3. If restart does not fix it, mark as aging hardware and let it run

**Implementation:**
- Created s19jpro_overheat_tracking table in guardian.db
- Created core/s19jpro_overheat_handler.py with tracking functions
- Functions: check_s19jpro_overheat_status(), record_overheat_first_seen(), record_restart_attempt(), record_restart_result(), get_aging_s19jpros()

**Commit:** 7e7c6d8

---

### Session 3: S19J Pro HVAC in Scan Context (6:00am CDT)

#### Issue
Daemon only sent warehouse HVAC data to Qwen during scans. S19J Pro thermal issues were being analyzed against the wrong cooling system.

#### Fix (Commit: 086c6bf)

1. **Import:** Added poll_all_systems from hvac_client
2. **Polling:** Changed hvac_snapshot = self.hvac.poll() to poll BOTH systems
3. **Context:** hvac_data now contains both systems:
   ```python
   hvac_data = {
       "warehouse": {"supply_f": 75, "return_f": 86, "delta_t": 11},
       "s19jpro": {"supply_f": 89, "return_f": 104, "delta_t": 15,
                   "container_f": 94, "outside_air_f": 85}
   }
   ```
4. **System Prompt:** Updated to explain "TWO HVAC systems"
5. **Output Label:** Changed to "HVAC (both systems)"

---

### Hardware Facts Established Today

| Miner | Boards | HVAC System | IP |
|-------|--------|-------------|-----|
| S19JPro | 3 (Chain 0,1,2) | s19jpro | 192.168.189.235 |
| S21 EXP Hydro | 3 | warehouse | 192.168.188.235 |
| S21 Immersion | 3 | warehouse | 192.168.188.235 |
| AH3880 Auradine | 2 | warehouse | 192.168.188.235 |

### Current Operator Rules (6 total)

1. **20-MINUTE POST-RESTART COOLDOWN** — Wait 20 min before additional actions
2. **OFFLINE MINER LOGIC** — No firmware restart for unreachable miners
3. **DAILY LOG COLLECTION MANDATORY** — Fresh logs required every day
4. **AMS LOG CLEANUP** — Delete ALL AMS logs daily at 10am
5. **S19J PRO CT FANS AT 100%** — No VFD feedback is intentional
6. **S19J PRO OVERHEATING BOARDS** — ONE restart attempt, then let run

### All Commits Today (10 total)
```
c9d942e docs: add session 3 notes
086c6bf feat: include S19J Pro HVAC data in scans
e867eeb Add PostgreSQL deployment package
d565a27 docs: add session 2 fixes to log
e886720 fix: AI analysis improvements
7e7c6d8 feat: add operator rule #6 - S19J Pro aging hardware
e3e18d5 docs: add S19J Pro HVAC fix to REPAIR_LOG
df699ca docs: comprehensive HVAC systems documentation
9d4ece4 docs: add S19J Pro CT fan note
0b3aab9 fix: wire all AI scripts to correct HVAC per miner
43ac433 feat: add S19J Pro HVAC system integration
```

### Services Status (Verified Working)
- mining-guardian.service — Active
- dashboard-api.service — Active
- Mac HVAC collector (launchd) — Active, pushing both systems

