# Mining Guardian — COMPLETE AI SYSTEM AUDIT v2

**Date:** April 10, 2026  
**Purpose:** Full audit of every AI component, every data flow, every feedback loop  
**Verdict:** THE SYSTEM IS NOT LEARNING FROM ITSELF — MAJOR GAPS EXIST

---

## EXECUTIVE SUMMARY

Mining Guardian has **24 database tables**, **17 knowledge structures**, and **13 AI processors** — but they are not properly connected. Data flows in, gets processed, gets stored... and often dies there.

**The fundamental problem:** Components are siloed. Each does its job but doesn't share with others.

---

## THE COMPLETE DATA INVENTORY

### Database Tables (22 tables, 14M+ rows)

| Table | Rows | Written By | Read By | Status |
|-------|------|------------|---------|--------|
| miner_readings | 69K | mining_guardian | Most AI components | ✅ Good |
| chain_readings | 80K | mining_guardian | Multiple components | ✅ Good |
| pool_readings | 28K | mining_guardian | Deep dive, training | ✅ Good |
| miner_logs | 821 | mining_guardian | Deep dive, log compare | ✅ Good |
| log_metrics | 13.7M | mining_guardian | Fingerprint, predictor | ✅ Good |
| miner_restarts | 69 | mining_guardian, outcome | Confidence, fingerprint | ✅ Good |
| action_audit_log | 836 | mining_guardian | Fingerprint, denials | ✅ Good |
| hvac_readings | 1.4K | mining_guardian | HVAC correlator only | ⚠️ Partial |
| weather_readings | 1.3K | mining_guardian | Deep dive, training | ✅ Good |
| miner_hardware | 90 | mining_guardian | Deep dive, fingerprint | ✅ Good |
| known_dead_boards | 17 | mining_guardian | Suppression logic | ✅ Good |
| ams_notifications | 56K | mining_guardian | Alert listener | ⚠️ Partial |
| miner_ams_extended | 38K | mining_guardian | **NOBODY** | ❌ ORPHANED |
| miner_baselines | 0 | **NEVER USED** | **NOBODY** | ❌ DEAD |
| chip_readings | 0 | **NEVER USED** | **NOBODY** | ❌ DEAD |
| miner_state_readings | 38K | mining_guardian | Action diversity, FP | ✅ Good |
| llm_analysis | 800 | local_llm | AI score only | ⚠️ Partial |
| scans | 1.4K | mining_guardian | All components | ✅ Good |
| pending_approvals | 642 | mining_guardian | Approval flow | ✅ Good |
| alert_listener_seen | 1.8K | alert_listener | Alert listener only | ⚠️ Internal |
| alert_listener_cooldown | 4 | alert_listener | Alert listener only | ⚠️ Internal |

### Knowledge.json Structures (17 keys)

| Structure | Entries | Written By | Read By | Status |
|-----------|---------|------------|---------|--------|
| llm_scan_analyses | 218 | local_llm_analyzer | Weekly train, local_llm (now) | ✅ Good |
| daily_deep_analyses | 1 | daily_deep_dive | Weekly train, refinement | ✅ Good |
| cross_miner_analysis | 6 | weekly training | Refinement only | ⚠️ NOT IN HOURLY |
| refined_insights | 14 | insight_manager | local_llm_analyzer | ✅ Good |
| operator_rules | 3 | local_llm_analyzer | Weekly train, deep dive | ⚠️ NOT IN HOURLY |
| miner_fingerprints | 58 | fingerprint_builder | Daily deep dive | ⚠️ NOT IN HOURLY |
| miner_profiles | 58 | outcome_checker | Score, backup | ✅ Good |
| predictions | 200 | predictor | **NOBODY** | ❌ ORPHANED |
| known_issues | 50 | combine_knowledge | Multiple (count only) | ⚠️ PARTIAL |
| patterns | 7 | combine_knowledge | local_llm_analyzer | ✅ Good |
| hvac_correlation | 5 keys | weekly_train | **NOBODY** | ❌ ORPHANED |
| fleet_summary | 8 keys | combine_knowledge | Backup only | ⚠️ Partial |
| baselines | 0 | **NEVER USED** | **NOBODY** | ❌ DEAD |
| weekly_refinement_chain | 2 | refinement_chain | Refinement only | ⚠️ Internal |

---

## AI PROCESSOR ANALYSIS

### 1. LOCAL_LLM_ANALYZER (Hourly Qwen Scan) — GRADE: D

**The operator-facing component. Should have ALL knowledge. Currently blind to most of it.**

| Data Source | Should Read | Currently Reads | Gap |
|-------------|-------------|-----------------|-----|
| patterns | ✅ | ✅ | None |
| refined_insights | ✅ | ✅ | None |
| llm_scan_analyses (prev) | ✅ | ✅ (just fixed) | None |
| predictions | ✅ | ❌ | **CRITICAL** |
| operator_rules | ✅ | ❌ | **CRITICAL** |
| miner_fingerprints | ✅ | ❌ | **HIGH** |
| cross_miner_analysis | ✅ | ❌ | **HIGH** |
| hvac_correlation | ✅ | ❌ | **MEDIUM** |
| known_issues (full) | ✅ | ❌ (count only) | **MEDIUM** |

**Missing context:** The hourly LLM makes recommendations without knowing:
- Which miners have pre-failure signals (predictions)
- What Bobby has taught (operator_rules)
- Each miner's behavioral history (fingerprints)
- Strategic insights from weekly training (cross_miner_analysis)


### 2. PREDICTOR — GRADE: F

**Runs 12 pre-failure signals on every scan. Output goes nowhere.**

| Data Source | Should Read | Currently Reads | Gap |
|-------------|-------------|-----------------|-----|
| miner_readings | ✅ | ✅ | None |
| chain_readings | ✅ | ✅ | None |
| log_metrics | ✅ | ✅ | None |
| miner_fingerprints | ✅ | ❌ | **HIGH** |
| hvac_correlation | ✅ | ❌ | **MEDIUM** |

| Output | Should Be Read By | Actually Read By | Gap |
|--------|-------------------|------------------|-----|
| predictions | hourly LLM, daily DD, weekly train, confidence, Slack | **NOBODY** | **CRITICAL** |

**The predictor is a complete dead end.** It calculates sophisticated pre-failure signals, stores 200 predictions... and nothing happens. No component reads them. No Slack alerts. No influence on recommendations.

---

### 3. DAILY_DEEP_DIVE — GRADE: B

**Good but missing strategic context.**

| Data Source | Should Read | Currently Reads | Gap |
|-------------|-------------|-----------------|-----|
| miner_fingerprints | ✅ | ✅ | None |
| operator_rules | ✅ | ✅ | None |
| daily_deep_analyses (prev) | ✅ | ✅ | None |
| predictions | ✅ | ❌ | **HIGH** |
| cross_miner_analysis | ✅ | ❌ | **MEDIUM** |
| hvac_correlation | ✅ | ❌ | **MEDIUM** |

---

### 4. CONFIDENCE_SCORER — GRADE: C

**Calculates confidence but missing key inputs.**

| Data Source | Should Read | Currently Reads | Gap |
|-------------|-------------|-----------------|-----|
| miner_restarts (db) | ✅ | ✅ | None |
| miner_fingerprints | ✅ | ✅ (via function) | None |
| predictions | ✅ | ❌ | **HIGH** |
| operator_rules | ✅ | ❌ | **HIGH** |
| hvac_correlation | ✅ | ❌ | **MEDIUM** |

**Missing:** If a miner shows 4 pre-failure signals, confidence should be lower. If facility is stressed, restart confidence should drop.

---

### 5. ACTION_DIVERSITY — GRADE: C

**Generates alternative actions but blind to key data.**

| Data Source | Should Read | Currently Reads | Gap |
|-------------|-------------|-----------------|-----|
| miner_readings | ✅ | ✅ | None |
| chain_readings | ✅ | ✅ | None |
| predictions | ✅ | ❌ | **HIGH** |
| miner_fingerprints | ✅ | ❌ | **HIGH** |
| operator_rules | ✅ | ❌ | **MEDIUM** |

**Missing:** For a miner with 30% restart success rate (fingerprint), action diversity should suggest alternatives. For a miner with pre-failure signals (predictions), it should suggest investigation over restart.

---

### 6. OUTCOME_CHECKER — GRADE: B

**Good outcome tracking but no prediction validation.**

| Data Source | Should Read | Currently Reads | Gap |
|-------------|-------------|-----------------|-----|
| miner_restarts | ✅ | ✅ | None |
| miner_readings | ✅ | ✅ | None |
| predictions | ✅ | ❌ | **HIGH** |

**Critical missing loop:** When a miner fails, did we predict it? When a miner recovers, was our prediction wrong? This feedback should tune the predictor.

---

### 7. WEEKLY TRAINING (train_cohort.py) — GRADE: B+

**Most comprehensive reader, but still missing some data.**

| Data Source | Should Read | Currently Reads | Gap |
|-------------|-------------|-----------------|-----|
| llm_scan_analyses | ✅ | ✅ | None |
| daily_deep_analyses | ✅ | ✅ | None |
| operator_rules | ✅ | ✅ | None |
| predictions | ✅ | ❌ | **MEDIUM** |
| miner_fingerprints | ✅ | ❌ | **MEDIUM** |
| hvac_correlation | ✅ | ❌ | **MEDIUM** |

---

### 8. HVAC_CORRELATOR — GRADE: F

**Calculates facility patterns that nobody reads.**

**Output `hvac_correlation`:** Written to knowledge.json, read by **NOBODY**.

---

### 9. FINGERPRINT_BUILDER — GRADE: A

**Well integrated. Builds profiles that others use.**

---

## ORPHANED DATA STRUCTURES

These exist, get updated, and serve no purpose:

| Structure | Size | Problem |
|-----------|------|---------|
| predictions | 200 items | Calculated every scan, never used |
| hvac_correlation | 5 keys | Calculated weekly, never used |
| miner_ams_extended | 38K rows | Written every scan, never read |
| miner_baselines | 0 rows | Table exists, never populated |
| chip_readings | 0 rows | Table exists, never populated |
| baselines (knowledge) | 0 entries | Structure exists, never populated |


---

## BROKEN FEEDBACK LOOPS

### Loop 1: PREDICTION VALIDATION ❌ BROKEN

```
predictor.py flags miner X with pre-failure signals
    → predictions stored (200 items)
        → miner X later fails OR recovers
            → outcome_checker evaluates
                → BUT NEVER CHECKS IF PREDICTION WAS CORRECT
                    → predictor never learns if its signals work
```

**Fix:** outcome_checker should validate predictions against actual outcomes.

---

### Loop 2: FINGERPRINT → PREDICTION ❌ BROKEN

```
fingerprint_builder shows miner X has 30% restart success
    → predictor runs risk assessment
        → BUT DOESN'T KNOW ABOUT THE BAD FINGERPRINT
            → calculates risk without behavioral history
```

**Fix:** predictor should read fingerprints.

---

### Loop 3: HVAC → FLEET CORRELATION ❌ BROKEN

```
hvac_correlator detects facility stress (high temps, pumps maxed)
    → hvac_correlation stored
        → hourly LLM flags miners
            → BUT DOESN'T KNOW FACILITY IS STRESSED
                → recommends restarts that won't help
```

**Fix:** hourly LLM and confidence_scorer should read hvac_correlation.

---

### Loop 4: WEEKLY → DAILY OPERATIONS ❌ BROKEN

```
weekly training learns: BOM X.X miners fail 60% of the time
    → cross_miner_analysis stores insight
        → hourly LLM flags a BOM X.X miner
            → BUT DOESN'T KNOW ABOUT THE WEEKLY INSIGHT
                → treats it like any other miner
```

**Fix:** hourly LLM should read cross_miner_analysis.

---

### Loop 5: OPERATOR RULES → DECISIONS ❌ BROKEN

```
Bobby denies a restart: "too soon after power cycle"
    → operator_rules stores: "20-min cooldown rule"
        → next scan, hourly LLM recommends restart 15 min after power cycle
            → DOESN'T KNOW BOBBY ALREADY TAUGHT THIS
                → violates learned rule
```

**Fix:** hourly LLM should read operator_rules prominently.

---

### Loop 6: PREDICTIONS → PROACTIVE ALERTS ❌ BROKEN

```
predictor sees miner X has 4 pre-failure signals
    → predictions stored
        → miner X keeps running
            → NO ALERT TO BOBBY
                → miner fails 2 days later
                    → Bobby: "why didn't you warn me?"
```

**Fix:** Predictions should generate Slack alerts for high-risk miners.

---

## THE COMPLETE FIX LIST

### Priority 1: Feed predictions into hourly LLM (CRITICAL)
**Impact:** LLM can say "this miner shows 3 pre-failure signals"  
**Effort:** 30 min  
**Files:** local_llm_analyzer.py

### Priority 2: Feed operator_rules into hourly LLM (CRITICAL)
**Impact:** LLM respects Bobby's taught rules  
**Effort:** 15 min  
**Files:** local_llm_analyzer.py

### Priority 3: Feed fingerprints into hourly LLM (HIGH)
**Impact:** LLM knows each miner's behavioral history  
**Effort:** 30 min  
**Files:** local_llm_analyzer.py

### Priority 4: Feed cross_miner_analysis into hourly LLM (HIGH)
**Impact:** Weekly strategic learnings inform daily operations  
**Effort:** 20 min  
**Files:** local_llm_analyzer.py

### Priority 5: Feed predictions into predictor (HIGH)
**Impact:** Fingerprints inform risk calculations  
**Effort:** 45 min  
**Files:** predictor.py

### Priority 6: Validate predictions in outcome_checker (HIGH)
**Impact:** Predictor learns from actual outcomes  
**Effort:** 1 hour  
**Files:** outcome_checker.py

### Priority 7: Feed predictions into confidence_scorer (MEDIUM)
**Impact:** Pre-failure signals reduce restart confidence  
**Effort:** 30 min  
**Files:** confidence_scorer.py

### Priority 8: Feed predictions into action_diversity (MEDIUM)
**Impact:** At-risk miners get alternative suggestions  
**Effort:** 30 min  
**Files:** action_diversity.py

### Priority 9: Add prediction alerts to Slack (MEDIUM)
**Impact:** Bobby warned about at-risk miners proactively  
**Effort:** 45 min  
**Files:** mining_guardian.py

### Priority 10: Feed hvac_correlation into hourly LLM (LOW - your HVAC is fine)
**Impact:** Facility stress context in recommendations  
**Effort:** 15 min  
**Files:** local_llm_analyzer.py

### Priority 11: Clean up dead tables (LOW)
**Impact:** Code cleanliness  
**Effort:** 30 min  
**Files:** Schema cleanup

---

## TOTAL ESTIMATED EFFORT

| Priority | Items | Time |
|----------|-------|------|
| Critical | 2 | 45 min |
| High | 4 | 2.5 hours |
| Medium | 3 | 1.75 hours |
| Low | 2 | 45 min |
| **Total** | **11** | **~6 hours** |

---

## THE VISION: FULLY CONNECTED AI

When complete, every component will read what it needs:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MINING GUARDIAN — FULLY CONNECTED                         │
└─────────────────────────────────────────────────────────────────────────────┘

                        ┌─────────────────────┐
                        │   HOURLY LLM SCAN   │
                        │   (sees everything) │
                        └──────────┬──────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
        ▼                          ▼                          ▼
┌───────────────┐        ┌───────────────┐        ┌───────────────┐
│  predictions  │        │ fingerprints  │        │operator_rules │
│  (pre-fail)   │        │  (behavior)   │        │ (Bobby said)  │
└───────┬───────┘        └───────┬───────┘        └───────┬───────┘
        │                        │                        │
        │    ┌───────────────────┼───────────────────┐    │
        │    │                   │                   │    │
        ▼    ▼                   ▼                   ▼    ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│confidence_scorer│     │ action_diversity│     │ outcome_checker │
│ (factors all)   │     │ (factors all)   │     │ (validates all) │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                        │                        │
        └────────────────────────┼────────────────────────┘
                                 │
                        ┌────────▼────────┐
                        │  SLACK OUTPUT   │
                        │ (informed recs) │
                        └─────────────────┘
```

---

## CONCLUSION

Mining Guardian is collecting excellent data but not using it. The system has:
- **200 predictions** going nowhere
- **58 fingerprints** the hourly LLM can't see
- **3 operator rules** Bobby taught that get ignored
- **6 weekly strategic insights** that don't flow into daily operations
- **38K rows** of AMS extended data sitting unused

**This is why it felt like the AI wasn't learning** — the learning WAS happening, but the results were going into storage without feeding back into operations.

**Next session priority:** Wire everything together. Start with the hourly LLM — make it see ALL the knowledge the system has accumulated.

---

*Audit completed April 10, 2026*
*Committed to docs/COMPLETE_AI_AUDIT_V2_2026-04-10.md*
