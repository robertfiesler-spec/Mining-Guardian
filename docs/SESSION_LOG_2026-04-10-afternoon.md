# Session Log — April 10, 2026 (Afternoon/Evening)

**Branch:** `main`
**Focus:** Insight filtering fixes, cron repairs, confidence scorer fix, Monday planning

---

## Session Summary

This session fixed **four** silent bugs and created a comprehensive Monday build plan for the Mining Intelligence Catalog.

---

## Fixes Deployed

### 1. Bad Insight Deleted — `chain_3_voltage_failure_hydro`

**Problem:** Claude training generated an insight claiming "Chain[3] detachment" on S19JPro miners. But S19JPro only has 3 boards (Chain 0, 1, 2). Chain[3] doesn't exist — this was a hallucination.

**Fix:** Deleted the bad insight from `knowledge.json` on VPS.

**Hardware facts established:**
- S19JPro: 3 boards (Chain 0, 1, 2) — air machine running in immersion
- AH3880 Auradine: 2 boards only

---

### 2. Daily Log Collection Cron Fixed (TWICE)

**Problem #1:** The original cron job was:
```
python -c "from core.mining_guardian import MiningGuardian; mg = MiningGuardian(); mg.collect_logs()"
```
This failed because `MiningGuardian()` requires a `config` argument.

**First fix (commit `7382037`):** Created `scripts/daily_collect_logs.py` wrapper that loads config.

**Problem #2:** The wrapper called `mg.collect_logs()` with NO arguments, but the method signature requires `miners` and `issues`:
```python
def collect_logs(self, miners: List[Dict], issues: List[Dict]) -> None:
```

**Second fix (commit `8186900`):** Updated script to:
1. Fetch miner list from AMS: `miners = mg.ams.get_miners()`
2. Pass to method: `mg.collect_logs(miners=miners, issues=[])`

**Why the retry logic matters:** The `collect_logs()` method has built-in retry:
- Pass 1: 15 workers, 10-minute timeout per miner
- Pass 2 (RETRY): 5 workers, 20-minute timeout for any failures

This was already implemented but never ran because the script couldn't even call the method.

---

### 3. Confidence Scorer Import Fixed

**Problem:** The import in `core/mining_guardian.py` was:
```python
from confidence_scorer import get_confidence
```
But the file lives at `ai/confidence_scorer.py`. The try/except silently disabled confidence scoring.

**Fix:** Changed to:
```python
from ai.confidence_scorer import get_confidence, get_gate
```

---

### 4. Operational vs Strategic Insight Filtering

**Problem:** Hourly scans were showing procurement advice ("don't buy this PCB") instead of operational patterns.

**Fix:** Modified `scripts/local_llm_analyzer.py` to filter by action type:
- OPERATIONAL (hourly): TUNE, WATCH, INVESTIGATE, critical-REPLACE
- STRATEGIC (weekly only): REJECT, KEEP, cohort-REPLACE

---

## Git Commits This Session

| Commit | Description |
|--------|-------------|
| `f04d703` | feat(ai): wire operational insights into hourly Qwen scan prompts |
| `7382037` | fix: confidence scorer import path + daily log collection cron script |
| `cd316ea` | docs: add Apr 10 afternoon fixes |
| `6dd87f7` | docs: add Monday Intelligence Catalog plan + session log |
| `8186900` | fix: daily_collect_logs.py now fetches miners from AMS before calling collect_logs |

---

## Documents Created/Updated

1. **`docs/MONDAY_INTELLIGENCE_CATALOG_PLAN.md`** — 75-minute build plan for Monday
2. **`REPAIR_LOG.md`** — Updated with all four fixes
3. **This session log**

---

## Current State

### Daily Deep Dive Status
- **Running now** — started 4pm CDT, currently on miner 32/45
- Using logs collected earlier today (30 of 49 miners have fresh logs)
- Will complete in ~1 hour

### Log Collection Stats (today)
- 30 unique miners with fresh logs
- 176 MB total log data
- 19 miners missing logs (some offline, some AMS timeouts)
- Tomorrow's 1pm cron will run the fixed script with retry pass

### Refined Insights: 14 total
- 6 operational (shown in hourly scans)
- 8 strategic (weekly training only)
- 1 deleted (hallucinated Chain[3])

### Cron Jobs (all 6 configured)
```
0 4 * * *   backup_knowledge.py
0 7 * * *   morning_briefing.py  
0 13 * * *  daily_collect_logs.py  ← FIXED (twice!)
0 16 * * *  daily_deep_dive.py     ← RUNNING NOW
0 0 * * *   weekly_train.py
0 1 * * *   refinement_chain.py
```

---

## Verification Items

| Item | Status |
|------|--------|
| Confidence scores in Slack | ⏳ Next scan |
| OPERATIONAL INTELLIGENCE in Qwen prompts | ✅ Deployed |
| Daily deep dive completion | 🔄 Running (32/45) |
| Daily log cron (tomorrow 1pm) | ⏳ Will verify |
| Retry pass for failed log downloads | ⏳ Will verify tomorrow |

---

*Session ended ~18:45 CDT. All fixes committed and pushed.*
