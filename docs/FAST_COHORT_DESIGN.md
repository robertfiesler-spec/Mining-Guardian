# Fast Cohort Analysis — Design Document

**Created:** 2026-04-19
**Branch:** feature/fast-cohort-analysis
**Status:** In Development

---

## Problem Statement

The current per-miner deep dive approach is too slow:

| Metric | Current | At Scale (500 miners) |
|--------|---------|----------------------|
| Time per miner | ~135 min | N/A |
| Total time | 33 miners × 135 min = 74 hrs | 500 × 135 min = 1,125 hrs (47 days!) |
| Prompt size | 35K chars / 22K tokens | Same |

**Root cause:** Processing 22,000 tokens per miner × 33 miners = 726,000 total tokens processed individually. Most of this is redundant — similar miners get similar prompts.

---

## Solution: Cohort-First Analysis

Instead of analyzing each miner individually, we:

1. **Group miners into cohorts** (already doing this in weekly_train.py)
2. **Analyze cohorts as a batch** — one LLM call for 5-10 similar miners
3. **Flag outliers** for individual attention only if needed
4. **Skip per-miner deep dive** unless flagged

### Why This Works

- Miners in the same cohort share: model, firmware, PCB/BOM, chip bin, cooling type
- If 10 S19JPro BiXBiT PCB=0110 miners are all healthy → one call confirms all 10
- Only outliers (performing differently from cohort) need individual analysis

---

## Architecture Comparison

### Old Approach (Too Slow)
```
Daily 4PM:
├── Per-miner deep dive (Qwen) — 135 min × 33 = 74 hours
├── Fleet synthesis (Qwen) — 30 min
└── Total: 75+ hours (BROKEN)

Daily 3AM:
├── Cohort training (Claude) — 20 cohorts × 30 sec = 10 min
├── Refinement (Qwen + Claude) — 30 min
└── Total: 40 min
```

### New Approach (Fast)
```
Daily 4PM:
├── Cohort analysis (Qwen) — 20 cohorts × 5 min = 100 min (~1.5 hrs)
├── Outlier deep dive (Qwen) — only flagged miners, ~10-15 min each
├── Fleet synthesis (Qwen) — 10 min
└── Total: 2-3 hours MAX

Daily 3AM:
├── Claude refinement — 30 min (unchanged)
└── Total: 30 min
```

**Speed improvement:** 75+ hours → 2-3 hours = **25-30x faster**

---

## Cohort Analysis Design

### Input per Cohort
- Cohort definition (model/firmware/pcb/chip_bin/cooling)
- List of miners in cohort (5-15 typically)
- Summary stats: avg hashrate, avg temp, avg efficiency
- Outlier flags: any miner >2 std dev from cohort mean
- Recent alerts/issues for cohort members

### Output per Cohort
- Overall cohort health assessment (GREEN/YELLOW/RED)
- Common issues affecting the cohort
- Specific outliers needing individual attention
- Recommended actions (if any)

### Prompt Size Target
- Current per-miner: 35K chars
- New per-cohort: 8-12K chars (includes summary for all cohort members)
- Reduction: 3-4x smaller prompts

---

## Implementation Plan

### Phase 1: Build Cohort Analyzer
1. Create `ai/cohort_analyzer.py` — new fast analysis script
2. Reuse cohort grouping logic from `weekly_train.py`
3. Build cohort summary prompt (compact, no raw logs)
4. Test with Qwen — target <10 min per cohort

### Phase 2: Outlier Detection
1. Calculate cohort statistics (mean, std dev)
2. Flag miners >2 std dev from mean on: hashrate, temp, efficiency
3. Only these flagged miners get individual deep dive

### Phase 3: Replace Daily Deep Dive
1. Disable old `daily_deep_dive.py` (or archive)
2. New cron: `cohort_analyzer.py` at 4PM
3. Outlier deep dives run immediately after cohort pass

### Phase 4: Optimize Further
1. Parallel cohort analysis (if needed)
2. Cache cohort baselines (skip healthy cohorts entirely)
3. Incremental updates (only re-analyze changed data)

---

## Key Principles

1. **Cohorts first, individuals second** — batch similar miners
2. **Outliers only** — dont waste time on healthy miners
3. **Compact prompts** — summaries, not raw logs
4. **Fast feedback** — operator sees results in <3 hours, not 3 days

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Total analysis time (50 miners) | < 3 hours |
| Total analysis time (500 miners) | < 6 hours |
| Per-cohort analysis | < 10 min |
| Outlier detection accuracy | > 90% |

---

## Files to Create

- `ai/cohort_analyzer.py` — main new script
- `ai/cohort_prompts.py` — prompt templates for cohort analysis
- `tests/test_cohort_analyzer.py` — unit tests

## Files to Modify

- `crontab` — replace deep_dive with cohort_analyzer
- `docs/CRON_SCHEDULE.md` — update documentation

