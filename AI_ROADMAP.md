# Mining Guardian — AI Learning Roadmap
## Path to 48-Hour Full Autonomous Test

**Branch:** `feature/ai-learning-enhancements`  
**Goal:** Build all 8 AI learning features, then run a full 48-hour autonomous test with complete reporting.

---

## Current Mode
**FULL-DAY AUTONOMOUS** — Active as of 2026-04-05  
Overnight automation now runs 24/7. LOW-risk actions (first firmware restart, first PDU cycle) execute without approval. Dead boards and physical cycles still require manual approval. Max auto-restarts: 2 per window.

---

## Current AI Capabilities (Baseline)

| Capability | Status | Notes |
|---|---|---|
| Behavioral scan data accumulation | ✅ Active | Every scan, all miners |
| Delta / scan-to-scan change detection | ✅ Active | Flags hashrate drops, temp spikes |
| Cross-miner correlation | ✅ Active | Detects fleet-wide patterns |
| Restart correlation tracking | ✅ Active | Links restarts to prior delta changes |
| Action audit log | ✅ Active | 327 entries, 7 days of history |
| Weekly LLM synthesis | ✅ Active | Sundays 3am via weekly_train.py |
| Miner profiles in knowledge base | ✅ Active | 58 profiles, growing |
| Low-risk overnight automation | ✅ Active | Now 24/7 full-day mode |

---

## Feature Build Queue

Build order is strict — each feature feeds the next. Do not reorder.

---

### Feature 1: Outcome Feedback Loop
**Status:** 🔴 Not built  
**Priority:** CRITICAL — everything else is blind without this  
**Branch target:** `feature/ai-learning-enhancements`

**What it does:**  
After every restart action, the system checks 2–3 scans later whether the miner recovered. Writes the result (SUCCESS / FAILURE / PARTIAL) back to `miner_restarts.outcome`. This creates labeled training data for every action taken.

**Definition of success:**
- Hashrate returns to ≥ 80% of rated within 3 scans
- Stays there for 2+ consecutive scans
- No re-flag within 30 minutes

**Implementation plan:**
- Add `outcome` TEXT column to `miner_restarts` table
- Add `outcome_checked_at` TIMESTAMP column
- New `outcome_checker.py` service: runs every scan, finds restarts without outcomes, checks if miner recovered
- Write outcome back to DB + update `knowledge.json` miner profile
- Outcome data flows into weekly LLM training

**DB schema change:**
```sql
ALTER TABLE miner_restarts ADD COLUMN outcome TEXT;         -- SUCCESS / FAILURE / PARTIAL
ALTER TABLE miner_restarts ADD COLUMN outcome_checked_at TEXT;
ALTER TABLE miner_restarts ADD COLUMN hashrate_before REAL;
ALTER TABLE miner_restarts ADD COLUMN hashrate_after REAL;
ALTER TABLE miner_restarts ADD COLUMN recovery_time_scans INTEGER;
```

**Files to create/modify:**
- `outcome_checker.py` (new)
- `mining_guardian.py` — call outcome checker after each scan
- `weekly_train.py` — include outcome data in LLM training prompt
- `guardian.db` — schema migration

---

### Feature 2: Confidence Scoring
**Status:** 🔴 Not built  
**Depends on:** Feature 1 (outcomes)

**What it does:**  
Before acting, the AI rates its own confidence (0–100) based on: how many times it has seen this exact situation, what the success rate was, and how stable the miner's recent history is. Confidence gates autonomy.

**Confidence thresholds:**
| Score | Action |
|---|---|
| ≥ 80 | Execute automatically (no approval needed) |
| 50–79 | Send to Slack for approval with confidence shown |
| < 50 | HOLD — send alert, do not act |

**Confidence formula (v1):**
```
base_score       = historical_success_rate * 60    # max 60 pts
consistency_bonus = (1 - hashrate_variance) * 20   # max 20 pts
history_bonus    = min(action_count / 10, 1) * 20  # max 20 pts — more history = more confidence
confidence       = base_score + consistency_bonus + history_bonus
```

**Implementation plan:**
- New `confidence_scorer.py` module
- `get_confidence(miner_id, action_type)` → returns 0-100
- Integrated into `mining_guardian.py` decision path
- Confidence score logged to `action_audit_log.notes`
- Shown in Slack approval messages: `[Confidence: 73%]`

---

### Feature 3: Denial Reason Capture
**Status:** 🔴 Not built  
**Depends on:** Feature 2 (confidence scoring)

**What it does:**  
When Rob denies an action in Slack, the bot posts a follow-up asking for a reason. The reason is stored in `action_audit_log.notes` and fed into the confidence scorer as a negative signal.

**UX flow:**
1. Mining Guardian posts approval request
2. Rob replies DENY
3. Bot immediately replies in thread: `"Got it — denied. Why? (optional, type a reason or skip)"`
4. If Rob replies within 5 minutes, reason is stored
5. Reason is parsed by LLM weekly to extract patterns: "denied because hashrate was already recovering"

**Implementation plan:**
- Modify `slack_approval_listener.py` — after DENY, post follow-up thread message
- Poll thread for reply within 5 minutes
- Store reason in `action_audit_log.notes`
- `weekly_train.py` — include denial reasons in LLM training

---

### Feature 4: Miner Fingerprinting
**Status:** 🔴 Not built  
**Depends on:** Features 1 + 2 (outcomes + confidence)

**What it does:**  
Builds a per-miner behavioral profile from accumulated outcome history. Every miner has a personality — restart success rate, typical recovery time, hashrate stability, how often it flags. Confidence scoring becomes per-miner instead of fleet-wide.

**Per-miner fingerprint schema:**
```json
{
  "miner_id": "53477",
  "ip": "192.168.188.36",
  "model": "S19JPro",
  "restart_success_rate": 0.72,
  "avg_recovery_time_scans": 2.3,
  "hashrate_stability_score": 0.85,
  "flag_frequency_per_week": 1.4,
  "known_issues": ["dead_board_0"],
  "confidence_modifier": -0.15,
  "last_updated": "2026-04-05T15:00:00"
}
```

**Implementation plan:**
- `fingerprint_builder.py` (new) — runs weekly, builds profiles from outcome history
- Profiles stored in `knowledge.json` under `miner_fingerprints`
- `confidence_scorer.py` applies per-miner modifier from fingerprint
- Fingerprints shown in weekly training prompt to LLM

---

### Feature 5: HVAC / Environment Correlation
**Status:** 🔴 Not built  
**Depends on:** Features 1 + 4 (outcomes + fingerprints)

**What it does:**  
Correlates BAS/HVAC sensor data (supply water temp, return temp, differential pressure, VFD %) to miner behavior. Learns facility-level patterns: "when supply water exceeds 75°F, 6+ miners flag within 2 scans." Distinguishes facility problems from individual miner problems.

**Correlations to detect:**
- Supply water temp → fleet hashrate drops
- Differential pressure → cooling efficiency → temps
- CW Pump VFD % → cooling capacity → miner temps
- Time-of-day patterns in environmental data

**Implementation plan:**
- `hvac_correlator.py` (new) — runs after each scan, checks HVAC metrics against miner issues
- If 3+ miners flag simultaneously AND HVAC metric is elevated → log as facility event, not miner events
- Facility events stored separately in `knowledge.json` under `facility_events`
- Weekly training includes HVAC correlation patterns
- Slack reports: distinguish "Facility Alert" from "Miner Alert"

---

### Feature 6: Pre-Failure Prediction
**Status:** 🔴 Not built  
**Depends on:** Features 1 + 4 + 5 (outcomes + fingerprints + HVAC)

**What it does:**  
Instead of reacting when a miner breaks, predict it 2–3 scans before it happens. Detects the pattern that historically precedes a failure for a specific miner and flags it proactively.

**Prediction signals (per-miner):**
- Gradual hashrate decline on a specific board over N scans
- Temperature creep without environmental cause
- Increasing HW error rate trend
- Pattern matches historical pre-failure signature from fingerprint

**Implementation plan:**
- `predictor.py` (new) — runs every scan, checks each miner's recent trend against fingerprint
- Prediction confidence threshold: ≥ 70% match to historical pre-failure pattern
- Prediction actions: MONITOR_CLOSE (no restart yet, watch carefully) or PREEMPTIVE_RESTART
- Prediction accuracy tracked in outcome feedback loop
- Weekly training includes prediction accuracy data

---

### Feature 7: Repair Shop Data Ingestion
**Status:** 🔴 Not built — pending dataset  
**Depends on:** All previous features

**What it does:**  
Ingests large failure/repair datasets from the miner repair shop contact. Labeled failure modes, symptoms, and resolutions. Massively accelerates learning by giving the AI failure patterns it hasn't seen yet in this mine.

**Expected dataset format (TBD):**
- Miner model, failure symptom, board-level readings, resolution
- Repair outcome (board replaced, cleaned, RMA'd)
- Time to failure from first symptom

**Implementation plan:**
- `repair_data_ingestor.py` (new) — one-time + periodic ingestion script
- Normalize repair data to internal schema
- Feed through `combine_knowledge.py` LLM synthesis
- Merged into `master_knowledge.json` for distribution

---

### Feature 8: Action Diversity
**Status:** 🔴 Not built  
**Depends on:** All previous features + confidence scoring mature

**What it does:**  
Expands the AI's action toolkit beyond RESTART / PDU_CYCLE / RESTART_CHECK_BOARDS. New actions added with confidence gating — only unlocked when the AI has demonstrated reliability.

**New actions (confidence-gated):**
| Action | Min Confidence | Description |
|---|---|---|
| POWER_PROFILE_TUNE | 75 | Reduce/increase miner wattage via BiXBiT API |
| ECO_MODE | 80 | Switch to eco profile during high temp events |
| POOL_FAILOVER | 85 | Switch to backup pool if primary rejection > threshold |
| PREEMPTIVE_RESTART | 70 | Restart before failure based on prediction |

---

## 48-Hour Autonomous Test

**Planned start:** After all 8 features are built and validated on main.  
**Duration:** 48 continuous hours, full autonomy.

**Test report will include:**

| Metric | Description |
|---|---|
| Total actions taken | Count by type |
| Success rate per action type | From outcome feedback |
| Confidence score distribution | Did confidence calibrate correctly? |
| Situations auto-handled | No human needed |
| Situations escalated | Why? Low confidence or new situation? |
| Miner fingerprints built | How many miners profiled? |
| Patterns learned | New entries in knowledge.json |
| HVAC events detected | Facility vs miner problems |
| Predictions made | Accuracy rate |
| Fleet uptime / hashrate vs baseline | Did we improve or maintain? |

---

## Technical Notes

- HVAC/BAS integration is one-off for this warehouse — do not include in future deployment templates
- S19JPro dead hashboard issues (.36, .177, .195) are suppressed — AMS tickets #2662, #2663, #2661 created
- Repair shop data ingestion format TBD pending dataset from contact
- All features must maintain backward compatibility with existing `guardian.db` schema via migrations
- Every new DB column gets a migration in `mining_guardian.py` `_init_db()`
- Config safety rule: Never `cp config_template.json` over `config.json` on VPS
