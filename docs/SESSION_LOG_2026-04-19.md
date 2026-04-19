# Mining Guardian Session Log — April 19, 2026

**Session Duration:** ~3 hours  
**Operator:** Rob Fiesler (Bobby)  
**Assistant:** Claude  
**Primary Focus:** Claude API fallback implementation, full learning cycle completion, operator insight review

---

## CRITICAL ISSUE RESOLVED: Qwen Running on CPU

### Problem Identified
- Qwen 2.5 32B on ROBS-PC was running on **CPU instead of GPU**
- `size_vram: 0` in Ollama API confirmed GPU not being used
- Result: **135 minutes per miner** (vs expected 5 minutes with GPU)
- Root cause: Unknown — happened between April 14-15

### Timing Evidence
| Date | Time per Miner | Status |
|------|----------------|--------|
| April 10-14 | 3-8 minutes | ✅ GPU working |
| April 15 | 39 minutes | ⚠️ First slowdown |
| April 18-19 | 135 minutes | ❌ CPU only |

### Solution: Claude API Fallback
Since Bobby is away from facility until Tuesday, implemented temporary Claude API fallback:

**Files Modified:**
1. `/root/Mining-Gaurdian/ai/daily_deep_dive.py`
   - Added `query_claude()` function
   - Added `query_llm()` router that checks `USE_CLAUDE_FALLBACK` env var
   - All `query_qwen()` calls replaced with `query_llm()`

2. `/root/Mining-Gaurdian/ai/refinement_chain.py`
   - Added `fire_pass_3_claude_fallback()` function
   - Added `fire_pass_3()` router that checks `USE_CLAUDE_FALLBACK` env var
   - Pass 3 calls routed through dispatcher

**Crontab Updated:**
```bash
# Pass 1 and Pass 3 now include USE_CLAUDE_FALLBACK=1
0 16 * * * cd /root/Mining-Gaurdian && USE_CLAUDE_FALLBACK=1 PYTHONPATH=/root/Mining-Gaurdian ...
0 1 * * * cd /root/Mining-Gaurdian && USE_CLAUDE_FALLBACK=1 PYTHONPATH=/root/Mining-Gaurdian ...
```

### Tuesday Rollback Instructions
```bash
# 1. Fix GPU on ROBS-PC
nvidia-smi  # Verify GPU visible
# Restart Ollama if needed

# 2. Remove fallback from crontab
crontab -e
# Remove USE_CLAUDE_FALLBACK=1 from Pass 1 and Pass 3 lines

# 3. Test
cd /root/Mining-Gaurdian && python3 ai/daily_deep_dive.py --dry-run
# Should show "Qwen call" not "Claude call"
```

---

## FULL LEARNING CYCLE COMPLETED

### Performance Comparison
| Pass | With Qwen (CPU) | With Claude Fallback |
|------|-----------------|----------------------|
| Pass 1: Deep Dive (33 miners) | ~73 hours | **19.8 minutes** |
| Pass 2: Cohort Training | 25 min | 25 min (already Claude) |
| Pass 3: Reflection | ~2 hours | **~5 minutes** |
| Pass 4: Final Merge | 2 min | 2 min (already Claude) |
| **TOTAL** | **~76 hours** | **~52 minutes** |

### Results
- **Pass 1:** 33 miners analyzed, 0 failures, 19.8 min total
- **Pass 2:** 20 cohorts + 2 outliers + fleet synthesis
- **Pass 3:** 7864 chars reflection
- **Pass 4:** 6803 chars final merged report
- **Knowledge.json:** Updated with all 4 passes

---

## INSIGHT FILTER SYSTEM CREATED

### Problem
AI was proposing insights that duplicated existing rules or contradicted each other.

### Solution
Created `/root/Mining-Gaurdian/ai/insight_filter.py` that:
1. Cross-references insights against existing operator_rules and pattern_rules
2. Marks duplicates as "already_covered"
3. Identifies contradictory insights (e.g., "0110 is worse" vs "0130 is worse")
4. Consolidates duplicate insights

### Filter Results (36 total insights)
| Status | Count | Description |
|--------|-------|-------------|
| Already covered | 10 | Matched existing rules/patterns |
| Contradictory | 6 | AI confused itself (PCB data) |
| Duplicates | 7 | Same insight said multiple ways |
| HVAC Paused | 3 | S21/Auradine - revisit Thursday |
| Adjusted | 1 | S21 - HVAC context added |
| Approved | 3 | New patterns locked |
| Rejected | 8 | Not actionable or too specific |

---

## OPERATOR INSIGHT REVIEW

### Review Process Established
- One insight at a time (not all at once)
- Claude provides recommendation with explanation
- Operator decides: YES / NO / ADJUST
- All decisions documented with full explanation for future audit

---

## APPROVED INSIGHTS (3 New Patterns)

### 1. s19jpro_bixbit_4_0130_stable_hydro
**Insight:** S19JPro BIXBIT/4/0130/4 cohort (7 miners) showing stable 88%+ hashrate with consistent thermal behavior.

**Decision:** APPROVED as healthy baseline for S19J Pro comparison. PCB=0130 + BiXBiT firmware = benchmark for healthy performance.

**Decided by:** Rob Fiesler  
**Date:** 2026-04-19

---

### 2. voltage_regulation_failure_pattern_hydro
**Insight:** Miners showing 0-200% hashrate volatility with normal chip temps (67-73°C) indicate systematic PSU voltage regulation failures.

**Decision:** APPROVED - Add as Signal 6 to PSU_VOLTAGE_DEGRADATION_PATTERN: Hashrate volatility (0-200%) with stable temps indicates PSU issue even without direct voltage readings.

**Context:** These old PSUs have been pushed over max capacity for 2+ years, so this is expected behavior for aging equipment. This signal is a great feature for future when newer equipment starts to fail, but not a norm for current fleet.

**Decided by:** Rob Fiesler  
**Date:** 2026-04-19

---

### 3. s19jpro_catastrophic_offline_rates_hydro
**Insight:** S19J Pro miners showing >300 offline events per week achieve only 45-69% hashrate despite optimal temperatures.

**Decision:** APPROVED as new signal: High offline frequency (>300/week) with normal temps (69-73°C) + low hashrate (45-69%) = hardware instability (control board or PSU), not thermal issue.

**Action:** CREATE_TICKET, not REPLACE - let the operator decide on replacement. This catches miners in the failing state between working and dead.

**Decided by:** Rob Fiesler  
**Date:** 2026-04-19

---

## REJECTED INSIGHTS (8 Total)

### 1. s19jpro_bixbit_2_0110_board0_hydro
**Insight:** Board 0 death cascade pattern in PCB=0110 miners.

**Rejection Reason:** Already covered by CHIP_QUALITY_DEGRADATION_PATTERN. Pattern detects board failures regardless of which board dies first. Adding "Board 0 specifically" would be over-specific.

---

### 2. miner_53482_chip_degradation_hydro
**Insight:** Specific miner 53482 showing chip degradation.

**Rejection Reason:** This is a specific miner, not a pattern. Rules should describe situations, not individual miner IDs. CHIP_QUALITY_DEGRADATION_PATTERN already catches this behavior.

---

### 3. chain3_detachment_bixbit_hydro
**Insight:** Chain 3 detachment errors on PCB=0110 miners.

**Rejection Reason:** Chain detachment symptom is already caught by existing board analysis (_analyze_chains). Root cause (PSU voltage instability) is covered by PSU_VOLTAGE_DEGRADATION_PATTERN. Adding Chain 3 specifically would be over-specific - the action is the same regardless of which chain/board detaches.

---

### 4. restart_success_threshold_hydro
**Insight:** Cohorts with less than 25% restart success are beyond software recovery.

**Rejection Reason:** The existing rule (2+ failed restarts in 7 days -> escalate to RESTART_CHECK_BOARDS) handles this at the miner level. Adding cohort-level thresholds adds complexity without changing the outcome.

---

### 5. bin_3_degradation_pattern_hydro
**Insight:** Chip Bin 3 vs Bin 1 performance gap.

**Rejection Reason:** Already covered - Chip Bin 3 performance gap is already included as Signal 2 in CHIP_QUALITY_DEGRADATION_PATTERN. The exact same data point (68.3% vs 152.7%) is documented there.

---

### 6. extreme_hashrate_volatility_hydro
**Insight:** 0-200% hashrate swings with normal temps.

**Rejection Reason:** Duplicate of voltage_regulation_failure_pattern_hydro which we approved. Same signal, different wording.

---

### 7. bixbit_vs_stock_performance_hydro
**Insight:** BiXBiT firmware outperforms Stock by 15-30%.

**Rejection Reason:** This is a known operational decision, not a pattern to detect. BiXBiT firmware is already the standard firmware policy; the Stock firmware miners are exceptions for specific reasons. No actionable rule needed.

---

### 8. unknown_fw_failure_cascade_hydro
**Insight:** Unknown firmware miners performing poorly.

**Rejection Reason:** "Unknown firmware" is a data quality issue, not a pattern. The poor performance of these miners is likely already caught by other patterns (offline events, hashrate degradation). The action should be to fix the firmware detection, not create a rule around "unknown."

---

### 9. unknown_firmware_zero_readings_hydro
**Insight:** 8 miners with unknown firmware and zero telemetry.

**Rejection Reason:** Zero telemetry is already caught by COMPLETE_HARDWARE_FAILURE_PATTERN. The "unknown firmware" aspect is a data quality issue to fix in the code, not a rule for the AI.

---

## HVAC WORK PAUSE

### Hardware Fact Added
S21 Hydro, S21 Immersion, and Auradine AH3880 miners are OFF until Thursday April 24, 2026 for HVAC system work.

**Insights Paused:**
- s21exphyd_vendor_failure_hydro
- s21_immersion_performance_immersion  
- ah3880_software_failure_hydro
- ah3880_power_delivery_limitation_hydro

**Resume Date:** 2026-04-24 (Thursday)

**Knowledge.json Entry:**
```json
{
  "id": "hvac_work_apr2026",
  "fact": "S21 Hydro, S21 Immersion, and Auradine AH3880 miners are OFF until Thursday April 24 2026 for HVAC system work.",
  "expires": "2026-04-24",
  "action": "SKIP_UNTIL_THURSDAY"
}
```

---

## CRON SCHEDULE (Current)

```
# Pass 1 - Deep dive with Claude fallback (4pm)
0 16 * * * USE_CLAUDE_FALLBACK=1 ... daily_deep_dive.py

# Pass 2 - Claude cohort training (midnight)
0 0 * * * ... weekly_train.py

# Pass 3+4 - Refinement chain with Claude fallback (1am)
0 1 * * * USE_CLAUDE_FALLBACK=1 ... refinement_chain.py

# Other jobs unchanged
0 4 * * * ... backup_knowledge.py
0 7 * * * ... morning_briefing.py
45 12 * * * ... cleanup_ams_logs.py
0 13 * * * ... direct_collect_logs.py
15 16 * * * ... daily_log_failure_report.py
0 8 * * * ... daily_operator_review.py
```

---

## GIT COMMITS

```
ce6d843 - feat: Add Claude API fallback for Pass 1 and Pass 3
```

---

## FILES CREATED/MODIFIED

| File | Action | Description |
|------|--------|-------------|
| ai/daily_deep_dive.py | Modified | Added Claude fallback functions |
| ai/refinement_chain.py | Modified | Added Claude fallback for Pass 3 |
| ai/insight_filter.py | Created | Filter insights against existing rules |
| docs/SESSION_LOG_2026-04-19.md | Created | This document |

---

## NEXT STEPS

### Automatic (Cron will handle)
- 1pm: Fresh log collection
- 4pm: Pass 1 deep dive (Claude fallback)
- Midnight: Pass 2 cohort training
- 1am: Pass 3+4 refinement chain (Claude fallback)

### Tuesday April 22
1. Fix GPU on ROBS-PC (nvidia-smi, restart Ollama)
2. Remove USE_CLAUDE_FALLBACK from crontab
3. Test Qwen performance (~5 min/miner expected)
4. Verify full pipeline runs with Qwen

### Thursday April 24
1. HVAC work complete
2. S21 and Auradine miners back online
3. Review paused insights
4. Resume normal monitoring for all equipment

---

## KEY LEARNINGS

1. **Claude fallback works** — 52 min vs 76 hours for full cycle
2. **Insight filtering is essential** — AI generates duplicates/contradictions without cross-referencing existing rules
3. **One insight at a time** — Better operator experience than reviewing 36 at once
4. **Document decisions with explanations** — Enables future audit and helps AI learn what to propose vs reject
5. **Patterns not miners** — Rules should describe situations, not specific miner IDs
