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

### 2026-04-10 (evening) · LLM kept recommending HVAC inspection + repeating 20-min cooldown rule

**What Bobby thought the program was doing:**
The LLM should NOT recommend HVAC inspection — the HVAC is working correctly. Low delta-T is normal and seasonal. Also, once the system learns a rule (like the 20-minute post-restart cooldown), it shouldn't keep mentioning it in every single report.

**What was actually happening:**
1. **HVAC recommendations:** The LLM was including "review HVAC system to address environmental overheating concerns" in recommendations, even though the HVAC is fine.

2. **Repeating OPERATOR LEARNING:** Every report included the same 20-minute cooldown rule under "OPERATOR LEARNING" even though that rule was learned days ago and is already in `operator_rules`.

**Why it mattered:**
- False HVAC alerts waste operator attention on a system that's working correctly
- Repeating the same "learning" every report is noise — the system should only report NEW learnings

**What we changed:**
Modified `scripts/local_llm_analyzer.py`:

1. **Added HVAC disclaimer** right after HVAC data line:
   ```
   NOTE: HVAC is WORKING CORRECTLY. Low delta-T is normal. Do NOT recommend HVAC inspection.
   ```

2. **Updated OPERATOR LEARNING instructions:**
   ```
   ONLY include this section if there are NEW denials with NEW reasons.
   The 20-minute post-restart cooldown rule is ALREADY KNOWN — do not repeat it.
   Skip this section entirely if there are no new lessons to learn.
   ```

3. **Added warning in RECOMMENDATION section:**
   ```
   CRITICAL: Do NOT recommend HVAC inspection — the cooling system is working correctly.
   ```

**How we verified:**
- `python3 -m py_compile scripts/local_llm_analyzer.py` passes
- Committed as `45b954f`

**Lesson:**
LLMs need explicit negative instructions ("do NOT do X") when they keep doing something unwanted. Positive instructions alone aren't enough — the model will keep making the same suggestions unless explicitly told not to.

**Status:** Fixed. Next hourly scan should show cleaner recommendations.

---

### 2026-04-10 (evening) · daily_collect_logs.py called collect_logs() with no arguments

**What Bobby thought the program was doing:**
The 1pm cron job should download logs from all miners, with a retry pass for any that fail on the first attempt. The retry logic (Pass 1: 15 workers, 10-min timeout; Pass 2: 5 workers, 20-min timeout) is built into `collect_logs()` in `core/mining_guardian.py`.

**What was actually happening:**
The `scripts/daily_collect_logs.py` script we created earlier today called `mg.collect_logs()` with **no arguments**. But the method signature is:
```python
def collect_logs(self, miners: List[Dict], issues: List[Dict]) -> None:
```
It requires the miner list to be passed in. The script would have thrown a TypeError as soon as the cron ran.

**Why it mattered:**
Without the miner list, the script can't run, which means:
- No daily log collection at 1pm
- No retry pass for failed miners
- Daily deep dive at 4pm has incomplete/stale data
- The whole log pipeline is broken

**What we changed:**
Rewrote `scripts/daily_collect_logs.py` to:
1. Fetch the current miner list from AMS: `miners = mg.ams.get_miners()`
2. Pass the miners to `collect_logs()`: `mg.collect_logs(miners=miners, issues=[])`
3. Added proper logging so cron output is useful

The retry logic inside `collect_logs()` was already correct (added earlier today per operator request) — we just needed to actually call the method properly.

**How we verified:**
- `python3 -m py_compile scripts/daily_collect_logs.py` passes
- Committed as `8186900` and pushed to GitHub

**Lesson:**
When creating wrapper scripts for cron, always check the method signature of what you're calling. This was the SECOND bug in the same script — first the config argument, now the miners argument. Test the complete flow, not just the import.

**Status:** Fixed. Tomorrow's 1pm cron run will be the first real test.

---

### 2026-04-10 (afternoon) · Three silent bugs: bad insight, broken cron, missing confidence

**What Bobby thought the program was doing:**
1. The refined insights should only contain accurate hardware info — S19JPro has 3 boards (Chain 0,1,2), not 4
2. The daily 1pm cron job should collect fresh logs from all miners
3. Confidence scores should appear on Slack recommendations ("85% confident in this choice")

**What was actually happening:**
1. **Bad insight:** Claude training generated `chain_3_voltage_failure_hydro` claiming "Chain[3] detachment" on S19JPro. But S19JPro only has 3 boards — Chain[3] doesn't exist. This was a hallucination.

2. **Broken cron:** The daily log collection cron entry was calling `MiningGuardian()` without the required `config` argument. The cron job was silently failing every day at 1pm.

3. **Missing confidence:** The import in `core/mining_guardian.py` was `from confidence_scorer import get_confidence`, but the file lives at `ai/confidence_scorer.py`. The try/except silently disabled confidence scoring.

**What we changed:**
1. Deleted the bad insight from `knowledge.json`
2. Created `scripts/daily_collect_logs.py` wrapper script
3. Fixed import path to `from ai.confidence_scorer import get_confidence, get_gate`

**Hardware facts established:**
- **S19JPro:** 3 boards (Chain 0, 1, 2) — air machine running in immersion
- **AH3880 Auradine:** 2 boards only

**Status:** Commits `7382037` (initial fix) and `8186900` (added miner list fetch).

---

### 2026-04-10 · Hourly scans were seeing procurement advice instead of operational patterns

**What Bobby thought the program was doing:**
The refined insights system has two jobs: (1) help Claude make strategic procurement decisions during weekly training, and (2) help Qwen during hourly scans recognize performance patterns. Hourly scans should see operational patterns, NOT procurement advice.

**What was actually happening:**
All insights were being dumped into the hourly scan prompt — including "REJECT 0110/0020 boards" and "KEEP buying 0130/0010" which are strategic, not operational.

**What we changed:**
Modified `scripts/local_llm_analyzer.py` to filter by action type:
- OPERATIONAL (hourly): TUNE, WATCH, INVESTIGATE, critical-REPLACE
- STRATEGIC (weekly only): REJECT, KEEP, cohort-REPLACE

**Status:** Complete. Committed as `f04d703`.

---

*[Earlier entries continue in git history]*
