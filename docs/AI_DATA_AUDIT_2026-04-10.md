# Mining Guardian — AI Data Architecture Audit

**Date:** April 10, 2026
**Purpose:** Complete analysis of all AI data flows to identify gaps and inefficiencies

---

## Executive Summary

After auditing all AI components, I found **several data structures being written but never read** — orphaned data that the system stores but doesn't use for learning. This is why the system felt like it wasn't learning: much of the learning data was going into a black hole.

### Critical Findings

| Data Structure | Entries | Written By | Read By | Status |
|----------------|---------|------------|---------|--------|
| `llm_scan_analyses` | 218 | Hourly LLM | Hourly LLM (NOW), Weekly training | ✅ FIXED today |
| `daily_deep_analyses` | 1 | Daily deep dive | Weekly training, Refinement chain | ✅ Working |
| `refined_insights` | 14 | Weekly training | Hourly LLM (filtered) | ✅ Working |
| `miner_fingerprints` | 58 | Fingerprint builder | Daily deep dive | ⚠️ PARTIAL |
| `operator_rules` | 3 | Denial processing | Weekly training only | ⚠️ NOT IN HOURLY |
| `predictions` | 200 | Predictor | **NOBODY** | ❌ ORPHANED |
| `known_issues` | 50 | Weekly training | Combine knowledge only | ⚠️ PARTIAL |
| `cross_miner_analysis` | 6 | Weekly training | Refinement chain only | ⚠️ NOT IN HOURLY |
| `hvac_correlation` | 5 keys | HVAC correlator | Weekly training only | ⚠️ NOT IN HOURLY |
| `patterns` | 7 | Weekly training | Hourly LLM | ✅ Working |

---

## Detailed Analysis

### 1. `operator_rules` — NOT USED IN HOURLY LLM ❌

**Problem:** The operator teaches rules via denial reasons. These rules are stored and used in weekly training, but the **hourly LLM never sees them**. 

**Current flow:**
```
Operator denies action → Reason captured → Rule extracted → operator_rules
                                                                 ↓
                                                          weekly training reads it
                                                                 ↓
                                                          BUT hourly LLM never sees it!
```

**Impact:** The hourly LLM keeps making the same mistakes because it doesn't know the operator rules.

**Fix:** Add `operator_rules` to the hourly LLM prompt context.

---

### 2. `predictions` — COMPLETELY ORPHANED ❌

**Problem:** The predictor runs on every scan, generates predictions about pre-failure signals, stores 200 of them in `knowledge.json`... and **NOBODY READS THEM**.

**Current flow:**
```
Predictor runs → predictions stored → ??? (nobody reads this)
```

**Impact:** We have 200 predictions about which miners might fail soon, but the hourly LLM doesn't see them, and they don't influence recommendations.

**Fix:** Feed predictions into the hourly LLM prompt. "These miners show pre-failure signals..."

---

### 3. `miner_fingerprints` — PARTIAL USE ⚠️

**Problem:** 58 fingerprints are built and stored, but:
- Daily deep dive reads them ✅
- Confidence scorer reads them ✅ (via function call)
- **Hourly LLM never sees them** ❌

**Impact:** The hourly LLM doesn't know each miner's behavioral history.

**Fix:** Add fingerprint summary to hourly LLM for flagged miners.

---

### 4. `cross_miner_analysis` — NOT IN HOURLY ⚠️

**Problem:** Claude produces fleet synthesis weekly, stored in `cross_miner_analysis`. The refinement chain reads it, but **hourly LLM never sees the strategic insights**.

**Impact:** Weekly strategic learnings don't flow into daily operations.

**Fix:** Extract key findings from `cross_miner_analysis` into hourly prompt.

---

### 5. `hvac_correlation` — NOT IN HOURLY ⚠️

**Problem:** HVAC correlation patterns are calculated and stored, but only read by weekly training.

**Impact:** Hourly LLM doesn't know about facility-level patterns.

**Note:** Given your HVAC is working correctly, this may not be critical. But the architecture should still close this loop.

---

### 6. `known_issues` — PARTIAL USE ⚠️

**Problem:** 50 known issues discovered over time, but hourly LLM only sees the count (`known_issues_count`), not the actual issues.

**Impact:** LLM knows "there are 50 issues" but can't reference them specifically.

**Fix:** Include recent known_issues in hourly prompt (like we do with patterns).

---

## The Ideal Data Flow (What We Should Build)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         HOURLY LLM PROMPT CONTEXT                        │
│                                                                          │
│  CURRENT DATA (scan)                                                     │
│  ├── Flagged miners                                                      │
│  ├── Restart outcomes (24h)                                              │
│  ├── Operator denials (24h)                                              │
│  ├── Pre/post restart logs                                               │
│  └── HVAC/weather                                                        │
│                                                                          │
│  LEARNED KNOWLEDGE (should ALL be here)                                  │
│  ├── Previous analyses (last 3) ✅ JUST ADDED                            │
│  ├── Patterns (7) ✅ Working                                             │
│  ├── Refined insights (6 operational) ✅ Working                         │
│  ├── Operator rules (3) ❌ MISSING                                       │
│  ├── Predictions (relevant ones) ❌ MISSING                              │
│  ├── Fingerprints (for flagged miners) ❌ MISSING                        │
│  ├── Known issues (recent) ❌ MISSING                                    │
│  └── Cross-miner insights (key findings) ❌ MISSING                      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Recommended Fixes (Priority Order)

### Priority 1: Add `operator_rules` to hourly LLM
The operator's rules should be front and center. If Bobby said "never restart within 20 minutes of power cycle," the LLM should see that rule every scan.

**Effort:** 15 minutes
**Impact:** High — stops LLM from violating known operator preferences

### Priority 2: Add `predictions` to hourly LLM  
We're running a predictor with 12 signals but not using the output! Feed predictions for flagged miners into the prompt.

**Effort:** 20 minutes
**Impact:** High — LLM can say "this miner shows 3 pre-failure signals, prioritize investigation"

### Priority 3: Add `miner_fingerprints` summary for flagged miners
For each flagged miner, include its fingerprint: restart success rate, stability score, known issues.

**Effort:** 30 minutes
**Impact:** Medium — LLM gets per-miner behavioral context

### Priority 4: Add recent `known_issues` to hourly LLM
Include the 5 most recent known issues, not just the count.

**Effort:** 10 minutes
**Impact:** Medium — LLM can reference specific discovered problems

### Priority 5: Extract key findings from `cross_miner_analysis`
Weekly strategic learnings should inform daily operations.

**Effort:** 30 minutes  
**Impact:** Medium — closes the weekly → daily feedback loop

---

## What's Working Well

1. **Daily → Weekly flow:** Daily deep dive feeds weekly training ✅
2. **Weekly → Hourly insights:** Refined insights (operational) feed hourly LLM ✅
3. **Patterns flow:** Patterns from weekly training appear in hourly prompts ✅
4. **Outcome tracking:** Restart outcomes feed fingerprints feed confidence ✅
5. **Previous analyses:** Hourly LLM now sees its own history ✅ (just fixed)

---

## Database Usage (All Tables)

| Table | Rows | Read By | Status |
|-------|------|---------|--------|
| miner_readings | 53K+ | All AI components | ✅ |
| chain_readings | 45K+ | Daily deep dive, Weekly training | ✅ |
| miner_logs | 800+ | Daily deep dive, Log comparison | ✅ |
| action_audit_log | 100+ | Denial processor, Weekly training | ✅ |
| miner_restarts | 50+ | Outcome checker, Fingerprints | ✅ |
| hvac_readings | 100+ | HVAC correlator | ✅ |
| known_dead_boards | ~10 | Dead board suppression | ✅ |
| pending_approvals | ~5 | Approval API | ✅ |

Database usage looks good — the issue is in `knowledge.json` feedback loops.

---

## Summary

The system has good data collection and good weekly training, but the **hourly LLM is blind to most of the learned knowledge**. It's operating in a silo, seeing only:
- Raw scan data
- Patterns
- Refined insights (filtered)
- Its own previous analyses (just added)

It should ALSO see:
- Operator rules
- Predictions
- Fingerprints for flagged miners
- Known issues
- Cross-miner strategic insights

This explains why it felt repetitive and not learning — most of the learning data was stored but never fed back into the operational loop.

---

*Audit completed April 10, 2026. Fixes should be prioritized for next session.*
