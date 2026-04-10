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

2. **Broken cron:** The daily log collection cron entry was:
   ```
   python -c "from core.mining_guardian import MiningGuardian; mg = MiningGuardian(); mg.collect_logs()"
   ```
   This failed because `MiningGuardian()` requires a `config` argument. The cron job was silently failing every day at 1pm.

3. **Missing confidence:** The import in `core/mining_guardian.py` was `from confidence_scorer import get_confidence`, but the file lives at `ai/confidence_scorer.py`. The try/except block caught the ImportError and silently set `_has_confidence = False`, so all confidence scoring was disabled.

**Why it mattered:**
- Bad insights pollute the knowledge base and give wrong advice
- Broken cron means no daily log collection = daily deep dive has no fresh data
- Missing confidence removes a key operator feedback signal from Slack

**What we changed:**

1. **Deleted the bad insight:**
   ```python
   del k['refined_insights']['chain_3_voltage_failure_hydro']
   ```
   Now 14 insights remain.

2. **Created `scripts/daily_collect_logs.py`** — a proper wrapper script that loads config:
   ```python
   config = GuardianConfig.from_file('/root/Mining-Gaurdian/config.json')
   mg = MiningGuardian(config)
   mg.collect_logs()
   ```
   Updated crontab to use the new script.

3. **Fixed import path:**
   ```python
   from ai.confidence_scorer import get_confidence, get_gate
   ```
   
**How we verified:**
- Insight count now 14 (was 15)
- Confidence import tested: `from ai.confidence_scorer import get_confidence` works
- Daemon restarted, running (PID 291367)

**Hardware facts established:**
- **S19JPro:** 3 boards (Chain 0, 1, 2) — runs in immersion (air machine converted)
- **AH3880 Auradine:** 2 boards only
- Any insight referencing Chain[3] on these models is hallucinated

**Status:** Commits `7382037` (initial fix) and `8186900` (added miner list fetch). See entry above for the second fix to this script.

---

### 2026-04-10 · Hourly scans were seeing procurement advice instead of operational patterns

**What Bobby thought the program was doing:**
The refined insights system has two jobs: (1) help Claude make strategic procurement decisions during weekly training ("don't buy this PCB/BOM combo"), and (2) help Qwen during hourly scans recognize performance and reliability patterns ("this miner matches a known failure mode"). These are fundamentally different use cases — one is strategic/purchasing, one is operational/monitoring.

**What was actually happening:**
When we first wired refined_insights into `scripts/local_llm_analyzer.py`, we dumped ALL insights into the hourly scan prompt with labels like `[DONT BUY]` and `[GOOD]`. Qwen was seeing strategic procurement verdicts during real-time operational scans where they don't belong.

**What we changed:**
Modified `scripts/local_llm_analyzer.py` to filter insights by action type:

**Now shown in hourly scans (OPERATIONAL):**
- `TUNE` — performance rules like restart success threshold
- `WATCH` — reliability patterns like Board 0 death cascade
- `INVESTIGATE` — active degradation alerts like PSU voltage instability
- `REPLACE` with "critical" in key — specific miner failures (not cohort-wide)

**NOT shown in hourly scans (STRATEGIC):**
- `REJECT` — procurement advice ("don't buy this combo")
- `KEEP` — procurement advice ("keep buying this combo")
- `REPLACE` cohort-wide — strategic hardware rotation decisions

**Status:** Complete. Committed as `f04d703`.

---

### 2026-04-10 · Three silent-skip bugs fixed — clobber, ghost file, and parallel-path mistake

**What Bobby thought the program was doing:**
The learning loop should work like this: Qwen analyzes every scan and writes to `knowledge['llm_scan_analyses']`. On Sunday, Claude reads that stream plus everything else and produces a fleet synthesis.

**What was actually happening:**
Three separate bugs, all in the same "silent-skip" class:

1. **Clobber bug in weekly training.** `ai/train_cohort.py` wrote Claude's fleet synthesis via direct file write, then called `km.save()` immediately after — which clobbered the fresh write with stale in-memory state.

2. **Frozen stream bug via ghost file.** `scripts/llm_scan_hook.py` was UNTRACKED in git with config key mismatches and NO write path to `knowledge['llm_scan_analyses']`.

3. **Parallel-path mistake.** An inline Qwen call was added to the main scan loop as a workaround. Once the ghost file was fixed, this became redundant.

**What we changed:**
- Clobber fix (commit f7fee4f): Reordered so `km.save()` fires FIRST, then direct write fires LAST.
- Ghost file fix (commit b3a5902): Fixed config keys, added persist path, added file to git tracking.
- Parallel-path revert (commit 355bad2): Removed the inline Qwen call.

**Status:** All three fixes shipped and verified.

---

*[Earlier entries continue in git history]*
