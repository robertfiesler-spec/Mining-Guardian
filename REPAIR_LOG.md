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

## April 11, 2026 — Daily Log Collection Fix (CRITICAL)

### Problem
Only 7 miners getting fresh logs daily instead of 39 eligible miners.

**Root causes:**
1. 24-hour dedup check was skipping miners that had any log in past 24h
2. When fresh export failed, system gave up instead of trying existing logs
3. Some miners (64407, 54567, 53529) have broken AMS log exports — all exports status=3 (failed)
4. A2 model (53476) returns False from trigger_log_export

### Fix (commit 81edb54)

1. **REMOVED 24-hour dedup** — every miner now attempts fresh log collection every day
2. **ADDED fallback to existing logs** — when fresh export fails, download most recent ready log
3. **Tagged fallback logs** as "daily_baseline_fallback" to distinguish from fresh

### New Operator Rule
> DAILY LOG COLLECTION MANDATORY: Every online miner MUST get a fresh log export every day.
> No 24-hour dedup — fresh logs are critical for AI learning. If fresh export fails,
> fall back to most recent existing ready log. Problem miners with broken AMS exports
> should be investigated physically.

### Problem Miners (require physical investigation)
- **64407** (S21e XP Hyd, 192.168.188.26) — 92 failed exports, 0 ready
- **54567** (S19JPro, 192.168.188.35) — 55 failed exports, 0 ready
- **53529** (S21EXPHyd, 192.168.188.25) — 92 failed, 1 ready from March 30
- **53476** (A2, 192.168.188.31) — trigger_log_export returns False (model limitation?)




---

## April 11, 2026 — Daily Log Collection v2 (commit 769cda0)

### Final Implementation
1. **No 24h dedup** — every miner attempts fresh export daily
2. **No old log fallback** — fresh exports only (old logs are waste)
3. **Slack report** — after retry pass, sends report of failed miners with:
   - Miner IP address
   - Model name  
   - Last successful log date
4. **DB tracking** — log_collection_failures table for history

### How It Works Now
- Pass 1: 15 parallel workers, 10-min timeout per miner
- Pass 2 (retry): 5 workers, 20-min timeout for failed miners
- Slack Report: Lists all miners that still failed after retry

### Problem Miners to Fix Physically
| IP | Model | Issue |
|----|-------|-------|
| 192.168.188.26 | S21e XP Hyd | 92 failed exports |
| 192.168.188.35 | S19JPro | Never got a log |
| 192.168.188.25 | S21EXPHyd | Last log March 30 |
| 192.168.188.31 | A2 | Model doesnt support AMS export |


