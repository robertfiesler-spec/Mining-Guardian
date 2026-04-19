# Session Log — 2026-04-18

## Overview

Major operator review session. All 21 AI proposals reviewed and decided.
Knowledge base restructured with clear separation of concerns.

---

## Deep Dive Fix (Critical)

**Problem:** Prompts were 86K+ chars, exceeding 45K limit. S19JPros being skipped.

**Root Cause:**
1. `yesterday_log` was pulling old 1.1MB unfiltered logs from days ago
2. Operator rules grew to 12KB after adding detailed patterns

**Fixes Applied:**
1. Set `yesterday_log = None` (1PM cron provides fresh logs)
2. Reduced `MAX_LOG_CHARS` from 60K to 30K
3. Capped operator rules in prompt to 2K chars (first line only)

**Result:**
- Before: 86,394 chars → SKIPPED
- After: 35,417 chars → PROCESSING ✅

**Commits:**
- `f6c38ea`: Remove yesterday log from deep dive
- `3f53110`: Cap operator rules in deep dive prompt

---

## Operator Review Session

21 items reviewed with operator decisions logged.

### Pattern Rules Created (4)

1. **CHIP_QUALITY_DEGRADATION_PATTERN** - S19J Pro efficiency loss
2. **PSU_VOLTAGE_DEGRADATION_PATTERN** - Voltage fluctuation precedes failure
3. **COMPLETE_HARDWARE_FAILURE_PATTERN** - Zero hashrate, offline
4. **PSU_PARTIAL_CIRCUIT_FAILURE_PATTERN** - Control board on, all boards dead

### Key Decisions

| Item | Decision | Reason |
|------|----------|--------|
| Time-based cooldown | UPDATED | Wait for MINING status, not 20 min |
| Offline miner logic | MERGED | Into COMPLETE_HARDWARE_FAILURE_PATTERN |
| AMS log cleanup | REMOVED | We bypass AMS, collect directly from miners |
| S21/AH3880 baseline | REJECTED | Each model variant needs own baseline |
| CT fans, overheating | MOVED | To hardware_facts (not for AI) |
| Validation workflow | MOVED | To process_rules (not for AI) |

### Knowledge Base Restructure

| Section | Count | Purpose |
|---------|-------|---------|
| operator_rules | 6 | Rules for AI miner analysis |
| pattern_rules | 4 | Machine-readable detection patterns |
| process_rules | 2 | Workflow rules (human review process) |
| hardware_facts | 3 | Known quantities (reference only) |

---

## Cron Schedule Updated

| Job | Old Time | New Time |
|-----|----------|----------|
| Claude training | Midnight | 3 AM |
| Refinement chain | 1 AM | 4 AM |

**Reason:** Deep dive takes ~110 min per miner, needs buffer time.

---

## Key Principles Established

1. **PATTERNS, NOT MINERS** - Rules describe situations, not specific IDs
2. **MODEL = SPECIFIC VARIANT** - S21 XP ≠ S21 Imm ≠ S21 EXP Hydro
3. **STATUS-BASED** - Wait for MINING status, not arbitrary timers
4. **HUMAN VALIDATION** - AI cannot lock rules without operator approval
5. **ONCE A DAY MAX** - Same problem = one notification per day
6. **TICKETS STOP ALERTS** - AMS ticket exists = stop MG notifications

---

## Git Commits

| Commit | Description |
|--------|-------------|
| `1f99deb` | docs: Update OPERATOR_RULES.md and REPAIR.md |
| `3f53110` | fix: Cap operator rules in deep dive prompt |
| `f6c38ea` | fix: Remove yesterday log from deep dive |
| `e81f9e9` | skip: Stock firmware miners excluded from log collection |
| `134737a` | docs: Add comprehensive OPERATOR_RULES.md |
| `6c0dae0` | rule: Add APPROVAL REQUIRES EXPLANATION rule |

---

## Status at End of Session

- Deep dive running with fixed code ✅
- S19JPros processing at ~35K char prompts ✅
- All 21 review items completed ✅
- Knowledge base restructured ✅
- Cron schedule updated ✅

