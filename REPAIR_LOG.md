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
- Cron job tested: `python3 -c 'import scripts.daily_collect_logs; print("OK")'` passes
- Confidence import tested: `from ai.confidence_scorer import get_confidence` works
- Daemon restarted, running (PID 291367)

**Hardware facts established:**
- **S19JPro:** 3 boards (Chain 0, 1, 2) — runs in immersion (air machine converted)
- **AH3880 Auradine:** 2 boards only
- Any insight referencing Chain[3] on these models is hallucinated

**Status:** All three fixes committed as `7382037` and pushed to GitHub. Confidence scores should appear on the next scan with recommendations.

---

### 2026-04-10 · Hourly scans were seeing procurement advice instead of operational patterns

**What Bobby thought the program was doing:**
The refined insights system has two jobs: (1) help Claude make strategic procurement decisions during weekly training ("don't buy this PCB/BOM combo"), and (2) help Qwen during hourly scans recognize performance and reliability patterns ("this miner matches a known failure mode"). These are fundamentally different use cases — one is strategic/purchasing, one is operational/monitoring. The hourly scans should see operational patterns like "Board 0 death cascade" or "PSU voltage instability precedes failure," NOT procurement advice like "REJECT 0110/0020 boards" or "KEEP buying 0130/0010."

**What was actually happening:**
When we first wired refined_insights into `scripts/local_llm_analyzer.py`, we dumped ALL 12 insights into the hourly scan prompt with labels like `[DONT BUY]` and `[GOOD]`. Qwen was seeing strategic procurement verdicts during real-time operational scans where they don't belong. The prompt said "FLEET INTELLIGENCE" but it was really "PURCHASING ADVICE" — wrong context entirely.

**Why it mattered:**
Hourly scans are about "what's happening right now and what action should I take." Showing Qwen "don't buy 0110/0020 boards" during a scan is useless noise — Qwen can't un-buy hardware that's already in the mine. Worse, it clutters the prompt with irrelevant context and might confuse the model about what it's supposed to be doing. The strategic insights belong in weekly Claude training where purchasing decisions can actually be influenced.

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

Also renamed the prompt section from "FLEET INTELLIGENCE" to "OPERATIONAL INTELLIGENCE."

**What we deliberately DIDN'T touch:**
- The strategic insights still exist in `knowledge.json` — just filtered out of hourly scan prompts
- Weekly Claude training still sees ALL insights

**How we verified:**
- Tested prompt builder shows "OPERATIONAL INTELLIGENCE (6 patterns)" with only TUNE/WATCH/INVESTIGATE entries
- Daemon restarted and running

**Status:** Complete. Committed as `f04d703`.

---

### 2026-04-10 · Three silent-skip bugs fixed — clobber, ghost file, and parallel-path mistake

**What Bobby thought the program was doing:**
The learning loop should work like this: Qwen analyzes every scan and writes to `knowledge['llm_scan_analyses']`. On Sunday, Claude reads that stream plus everything else and produces a fleet synthesis written to `knowledge['cross_miner_analysis']`. The whole point is that every piece of analysis flows to where it needs to be for the next consumer to read it.

**What was actually happening:**
Three separate bugs, all in the same "silent-skip" class — code logs success but state doesn't actually change:

1. **Clobber bug in weekly training.** `ai/train_cohort.py` wrote Claude's fleet synthesis to `knowledge['cross_miner_analysis']` via direct file write, then called `km.save()` immediately after. Problem: `km` held an in-memory snapshot from BEFORE the direct write, so `km.save()` serialized stale state right over the fresh synthesis.

2. **Frozen stream bug via ghost file.** `scripts/llm_scan_hook.py` was UNTRACKED in git. It had config key mismatches and NO write path to `knowledge['llm_scan_analyses']` — it called Qwen, posted to Slack, but never persisted anything.

3. **Parallel-path mistake.** An inline Qwen call was added to the main scan loop as a workaround. Once the ghost file was fixed, this became redundant.

**What we changed:**
- **Clobber fix (commit f7fee4f):** Reordered so `km.save()` fires FIRST, then direct write fires LAST.
- **Ghost file fix (commit b3a5902):** Fixed config keys, added persist path, added file to git tracking.
- **Parallel-path revert (commit 355bad2):** Removed the inline Qwen call.

**Status:** All three fixes shipped and verified.

---

*[Earlier entries from April 9 continue below in the full file]*
