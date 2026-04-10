# Session Log — 2026-04-10 (Thursday)

## Summary
Refined Insights quality audit and integration into hourly Qwen scans. Split insights into operational (for scans) vs strategic (for weekly training). Manual Claude training triggered, generating 3 new insights.

---

## Session Timeline

### Morning Session (~9am-12pm CDT)
- Fixed three silent-skip bugs (clobber, ghost file, parallel-path) — committed earlier
- Refined Insights system deployed via commit `b6003c3`
- Fleet count corrected to 58 miners in docs

### Afternoon Session (~1pm-3pm CDT)

**Insight Quality Audit**
- Bobby flagged that several insights were "obvious" not data-driven
- Established rule: An insight must be something you CANNOT know without deep data analysis
- Removed 9 obvious/non-analytical insights:
  - `ah3880_auradine_performance_hydro` — "Auradine is stable" (obvious)
  - `s21_cohorts_stable_hydro` — "S21s are stable" (obvious)
  - `stock_firmware_poor_reliability_hydro` — baseline assumption
  - `temp_threshold_liquid_cooling` — operator rule, not data insight
  - Plus 5 duplicates/overlaps

**Wired Insights into Hourly Scans**
- Modified `scripts/local_llm_analyzer.py` to load refined_insights into scan context
- Initially showed ALL insights including procurement advice — WRONG

**Operational vs Strategic Split (Bobby's Catch)**
- Bobby correctly identified: hourly scans shouldn't see "don't buy this PCB" advice
- Fixed filtering logic:
  - **OPERATIONAL (shown in hourly scans):** TUNE, WATCH, INVESTIGATE, critical REPLACE
  - **STRATEGIC (weekly training only):** REJECT, KEEP, cohort-wide REPLACE
- Renamed prompt section: "FLEET INTELLIGENCE" → "OPERATIONAL INTELLIGENCE"
- Changed task instruction: "INSIGHT CORRELATION" → "PATTERN MATCH"

**Manual Claude Training**
- Triggered `python3 ai/train_cohort.py` manually
- 16 cohorts analyzed, 2 outliers, 1 fleet synthesis
- 18 Claude API calls total (~8 minutes)
- Generated 3 NEW insights:
  1. `bin_3_systematic_failure_hydro` (REJECT, HIGH) — Bin 3 chips 16% worse than Bin 4
  2. `s21exphyd_vendor_failure_hydro` (REPLACE, HIGH) — S21EXPHyd at 46% rated capacity
  3. `chain_3_voltage_failure_hydro` (REPLACE, HIGH) — Chain[3] detachment = PSU failure

---

## Current State

### Refined Insights: 15 total
| Action | Count | Purpose |
|--------|-------|---------|
| REJECT | 5 | Don't buy — strategic |
| REPLACE | 4 | Replace hardware — strategic (3) + operational (1 critical) |
| KEEP | 1 | Keep buying — strategic |
| WATCH | 1 | Monitor pattern — operational |
| INVESTIGATE | 3 | Active degradation — operational |
| TUNE | 1 | Performance rule — operational |

### Operational (shown in hourly scans): 6
### Strategic (weekly training only): 9

---

## Commits This Session
- `f04d703` — feat(ai): wire operational insights into hourly Qwen scan prompts
- `db25c62` — docs: add Apr 10 repair log entry

---

## Next Session Priorities
1. **Verify next hourly scan** shows OPERATIONAL INTELLIGENCE section with 6 patterns
2. **Watch Qwen analysis quality** — does it reference the operational patterns?
3. **Daily deep dive** should run at 4pm CDT — verify it completes
4. **AI_ROADMAP.md** — mark Refined Insights as complete

---

## Files Changed
- `scripts/local_llm_analyzer.py` — operational insight filtering (VPS + committed)
- `knowledge.json` — 15 refined insights (VPS)
- `REPAIR_LOG.md` — new entry documenting the fix
- `docs/SESSION_LOG_2026-04-10.md` — this file

---

## Lessons Learned
1. **Different consumers need different views** — hourly scan analyzer vs weekly trainer both use insights but need filtered subsets
2. **Insight quality matters** — "BiXBiT is better than stock" is not an insight, it's an assumption. Real insights require data you couldn't know otherwise.
3. **Bobby catches context mismatches** — procurement advice in operational scans was immediately flagged as wrong context
