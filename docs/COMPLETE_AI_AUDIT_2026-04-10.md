# Mining Guardian — COMPLETE AI SYSTEM AUDIT

**Date:** April 10, 2026
**Purpose:** Full audit of EVERY AI component, EVERY data flow, EVERY feedback loop

---

## THE CORE QUESTION

> "Is everything learning from everything else?"

**Answer: NO.** There are significant gaps where data is collected, processed, and stored — but never used by other components that could benefit from it.

---

## COMPLETE DATA FLOW MAP

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           MINING GUARDIAN AI ARCHITECTURE                         │
└─────────────────────────────────────────────────────────────────────────────────┘

                              ┌──────────────────┐
                              │   AMS API SCAN   │
                              │  (every hour)    │
                              └────────┬─────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                  ▼                  ▼
         ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
         │  miner_readings  │ │  chain_readings  │ │   pool_readings  │
         │    (69K rows)    │ │    (80K rows)    │ │    (28K rows)    │
         └────────┬─────────┘ └────────┬─────────┘ └────────┬─────────┘
                  │                    │                    │
                  └────────────────────┼────────────────────┘
                                       │
         ┌─────────────────────────────┼─────────────────────────────┐
         │                             │                             │
         ▼                             ▼                             ▼
┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐
│ OUTCOME_CHECKER │          │    PREDICTOR    │          │ FINGERPRINT_    │
│ Evaluates       │          │ 12 pre-failure  │          │ BUILDER         │
│ restart success │          │ signals         │          │ Per-miner       │
└────────┬────────┘          └────────┬────────┘          │ behavior        │
         │                            │                   └────────┬────────┘
         ▼                            ▼                            ▼
┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐
│ miner_restarts  │          │  predictions    │          │miner_fingerprints│
│   (69 rows)     │          │  (200 items)    │          │  (58 profiles)  │
└────────┬────────┘          └────────┬────────┘          └────────┬────────┘
         │                            │                            │
         ▼                            ▼                            ▼
┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐
│CONFIDENCE_SCORER│          │       ???       │          │ daily_deep_dive │
│  Reads restarts │          │   WHO READS?    │          │  Reads FPs ✅   │
│       ✅        │          │      ❌         │          └─────────────────┘
└─────────────────┘          └─────────────────┘
```

---

## COMPONENT-BY-COMPONENT ANALYSIS

### 1. OUTCOME_CHECKER ✅ WELL INTEGRATED

| Aspect | Status |
|--------|--------|
| **Reads** | `miner_restarts` table, `miner_readings` for hashrate recovery |
| **Writes** | `miner_restarts.outcome`, `miner_profiles` in knowledge.json |
| **Who uses output** | `confidence_scorer` ✅, `fingerprint_builder` ✅, `train_cohort` ✅ |
| **Grade** | A — Feedback loop is closed |

---

### 2. PREDICTOR ❌ OUTPUT NOT USED

| Aspect | Status |
|--------|--------|
| **Reads** | `miner_readings`, `chain_readings`, 12 signals |
| **Writes** | `predictions` (200 items in knowledge.json) |
| **Who uses output** | **NOBODY** — predictions stored but never read |
| **Grade** | F — Complete dead end |

**Gap:** We run a sophisticated 12-signal pre-failure predictor on EVERY scan, generate predictions... and nobody reads them. The hourly LLM doesn't see them. The daily deep dive doesn't see them. The weekly training doesn't see them.

**Fix needed:** Feed predictions into:
- Hourly LLM prompt (for flagged miners)
- Daily deep dive (per-miner analysis)
- Weekly training (aggregate patterns)

---

### 3. FINGERPRINT_BUILDER ⚠️ PARTIAL USE

| Aspect | Status |
|--------|--------|
| **Reads** | `miner_restarts`, `chain_readings`, `action_audit_log` |
| **Writes** | `miner_fingerprints` (58 profiles) |
| **Who uses output** | `daily_deep_dive` ✅, `confidence_scorer` (via function) ✅ |
| **Grade** | B — Used by some, but hourly LLM is blind |

**Gap:** Hourly LLM doesn't see fingerprints. When it flags a miner, it doesn't know "this miner has 40% restart success rate and frequent reboots."

**Fix needed:** Include fingerprint summary in hourly LLM prompt for each flagged miner.

---

### 4. CONFIDENCE_SCORER ✅ WELL INTEGRATED

| Aspect | Status |
|--------|--------|
| **Reads** | `miner_restarts` (outcomes), fingerprints (via function) |
| **Writes** | Returns confidence score (not stored) |
| **Who uses output** | `mining_guardian.py` for action gating ✅ |
| **Grade** | A — Properly integrated |

---

### 5. HVAC_CORRELATOR ❌ OUTPUT NOT USED

| Aspect | Status |
|--------|--------|
| **Reads** | `hvac_readings`, `miner_readings` |
| **Writes** | `hvac_correlation` (5 keys in knowledge.json) |
| **Who uses output** | `weekly_train.py` writes it... **NOBODY reads it** |
| **Grade** | F — Dead end |

**Gap:** HVAC correlation patterns are calculated weekly but never used by any other component. The hourly LLM doesn't see facility-level correlations.

**Note:** Given Bobby's HVAC is working correctly, this may be lower priority, but the architecture should still close this loop.

---

### 6. ACTION_DIVERSITY ⚠️ PARTIAL

| Aspect | Status |
|--------|--------|
| **Reads** | `miner_readings`, `chain_readings`, power profiles |
| **Writes** | Action recommendations returned to main loop |
| **Who uses output** | `mining_guardian.py` ✅ |
| **Grade** | B — Works but doesn't read predictions or fingerprints |

**Gap:** Action diversity generator doesn't consider:
- Predictions (miners with pre-failure signals)
- Fingerprints (miners with poor restart history)

---

### 7. LOCAL_LLM_ANALYZER (Hourly) ⚠️ MAJOR GAPS

| Aspect | Status |
|--------|--------|
| **Reads** | patterns ✅, refined_insights ✅, previous_analyses ✅ (just fixed) |
| **Missing** | predictions ❌, operator_rules ❌, fingerprints ❌, cross_miner_analysis ❌, known_issues (only count) ❌ |
| **Writes** | `llm_scan_analyses` |
| **Grade** | C — Sees limited context |

**The hourly LLM is the operator-facing component. It should have ACCESS TO ALL LEARNED KNOWLEDGE.**

Currently reads:
- ✅ Raw scan data (flagged miners, outcomes, denials)
- ✅ Patterns (7)
- ✅ Refined insights (6 operational)
- ✅ Its own previous analyses (just fixed)

Does NOT read:
- ❌ `predictions` — "This miner shows 3 pre-failure signals"
- ❌ `operator_rules` — "Bobby said never restart within 20 min"
- ❌ `miner_fingerprints` — "This miner has 40% success rate"
- ❌ `known_issues` — actual issues, not just count
- ❌ `cross_miner_analysis` — strategic insights from weekly training
- ❌ `hvac_correlation` — facility patterns

---

### 8. DAILY_DEEP_DIVE ✅ GOOD, COULD BE BETTER

| Aspect | Status |
|--------|--------|
| **Reads** | fingerprints ✅, operator_rules ✅, yesterday's deep dive ✅, full logs ✅ |
| **Missing** | predictions ❌, cross_miner_analysis ❌ |
| **Writes** | `daily_deep_analyses` |
| **Grade** | B+ — Good but not using all available data |

**Gap:** Daily deep dive should see:
- Predictions for each miner
- Strategic insights from weekly training

---

### 9. WEEKLY TRAINING (train_cohort.py) ✅ COMPREHENSIVE

| Aspect | Status |
|--------|--------|
| **Reads** | llm_scan_analyses ✅, daily_deep_analyses ✅, operator_rules ✅, restarts ✅, cross_miner correlations ✅ |
| **Writes** | cross_miner_analysis, refined_insights |
| **Grade** | A — Reads most data sources |

**Minor gap:** Doesn't read `predictions` or `hvac_correlation`.

---

### 10. REFINEMENT_CHAIN ✅ GOOD

| Aspect | Status |
|--------|--------|
| **Reads** | daily_deep_analyses ✅, cross_miner_analysis ✅ |
| **Writes** | weekly_refinement_chain, corrected cross_miner_analysis |
| **Grade** | A — Good feedback loop |

---

## DATABASE TABLES — USAGE ANALYSIS

| Table | Rows | Used By | Grade |
|-------|------|---------|-------|
| `miner_readings` | 69K | ALL components | ✅ A |
| `chain_readings` | 80K | Multiple components | ✅ A |
| `pool_readings` | 28K | Daily deep dive, weekly training | ✅ B |
| `miner_logs` | 821 | Daily deep dive, log comparison | ✅ B |
| `log_metrics` | 13.7M | Daily deep dive | ⚠️ C (huge, underused?) |
| `hvac_readings` | 1.4K | HVAC correlator only | ⚠️ B |
| `miner_restarts` | 69 | Outcome checker, confidence, fingerprints | ✅ A |
| `action_audit_log` | 836 | Fingerprints, denial processing | ✅ A |
| `miner_hardware` | 90 | Weekly training (cohorts) | ✅ A |
| `miner_baselines` | 0 | **EMPTY** — not being used | ❌ F |
| `chip_readings` | 0 | **EMPTY** — stub table | ❌ F |
| `ams_notifications` | 56K | Alert listener only | ⚠️ C |

---

## KNOWLEDGE.JSON — USAGE MATRIX
