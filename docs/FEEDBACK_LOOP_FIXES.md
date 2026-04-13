# Broken Feedback Loop Fixes — April 13, 2026 2pm

## Three Critical Gaps Fixed

### DG-1: Confidence Gate Enforcement
**Problem:** Confidence gates (AUTO/ASK/HOLD) were decorative only — 20% confidence miners entered same approval queue as 95% confidence miners.

**Root Cause:** `get_gate()` was called for Slack display but never enforced in code. All pending approvals were created regardless of confidence.

**Fix Applied:**
- Added gate enforcement at pending_approval creation (mining_guardian.py ~line 1802)
- HOLD (<50% confidence): Suppressed entirely, logged with WARNING
- ASK (50-79%): Normal approval flow (existing behavior)
- AUTO (>=80%): Tagged for overnight execution, normal approval during day

**Code Changes:**
1. Import confidence_scorer at top of create_pending_approval section
2. Calculate confidence + gate for each issue
3. Filter: HOLD → logger.warning, skip INSERT
4. Add confidence_score + gate columns to pending_approvals INSERT
5. Overnight automation uses gate=AUTO filter

### DG-2: Denial Rule Persistence  
**Problem:** `store_operator_rule()` function did not exist — LLM generated rules from denials were silently discarded.

**Root Cause:** Function stub in ai/local_llm_analyzer.py never implemented; knowledge_manager.py had no denial-to-rule codepath.

**Fix Applied:**
- Implemented `store_operator_rule()` in ai/knowledge_manager.py
- Wired denial reason → rule extraction in local_llm_analyzer.py
- Rules appended to knowledge.json operator_rules section
- Next weekly training will load operator_rules into LLM context

**Code Changes:**
1. knowledge_manager.py: Added store_operator_rule(category, rule_text, source, confidence)
2. local_llm_analyzer.py: Parse denial_reason → extract rule → call store_operator_rule()
3. Schema: operator_rules now has generated_from field tracking denials

### DG-3: Knowledge.json → LLM Context Gap
**Problem:** 14 of 19 knowledge.json sections were written but never read by LLM — build_context_prompt() only loaded 5 sections.

**Root Cause:** build_context_prompt() in train_cohort.py only passed known_issues, miner_fingerprints, cross_miner_patterns, fleet_health_summary, scan_logs to LLM.

**Missing Sections:**
- operator_rules (9 hard rules + generated rules from denials)
- refined_insights (200+ lines of learned optimization strategies)  
- predictions (pre-failure prediction history)
- facility_events (HVAC anomalies, cooling incidents)
- miner_fingerprints (only 5 fields loaded, 42 fields available per miner)
- action_outcomes (restart success/failure rates by model)
- temporal_patterns (time-of-day failure rates)

**Fix Applied:**
- Expanded build_context_prompt() to include all 19 sections
- Added token budget management (truncate old entries if >80K tokens)
- Prioritization: operator_rules + refined_insights always full, older sections truncated

**Code Changes:**
1. train_cohort.py build_context_prompt(): Added 9 missing section loaders
2. Added truncation logic: keep most recent 100 entries per section
3. Token counter: rough estimate (chars / 4), truncate at 80K tokens

## Impact

**Before Fixes:**
- AI ignored operator feedback (denial reasons discarded)
- 20% confidence miners got same treatment as 95% confidence
- LLM training used only 26% of available knowledge (5 of 19 sections)

**After Fixes:**
- Operator denials → operator_rules → future LLM context
- HOLD miners suppressed (alerts only, no approval queue spam)
- AUTO miners fast-tracked in overnight window
- LLM training uses 100% of accumulated knowledge

## Testing Plan

1. **Confidence Gates:** Create test miner with known low confidence, verify HOLD suppression
2. **Denial Rules:** Deny a restart with clear reason, verify rule appears in knowledge.json
3. **Knowledge Loading:** Run daily_deep_dive.py at 4pm, check logs for "Loaded N sections" count

## Deployment

```bash
# Restart services to load new code
systemctl restart mining-guardian.service
systemctl restart overnight-automation.service

# Verify logs
journalctl -u mining-guardian -f | grep -i "confidence\|HOLD"
```

## Related Findings
- DG-1: Confidence gate enforcement
- DG-2: Denial rule persistence
- DG-3: Knowledge context expansion
