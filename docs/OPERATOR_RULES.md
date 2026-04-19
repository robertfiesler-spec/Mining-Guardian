# Mining Guardian — Complete Rules Reference

**Last Updated:** 2026-04-18
**Review Session Completed:** All 21 items reviewed with operator

---

## Knowledge Base Structure

| Section | Count | Purpose |
|---------|-------|---------|
| **operator_rules** | 6 | Rules AI uses for miner analysis |
| **pattern_rules** | 4 | Machine-readable patterns for detection |
| **process_rules** | 2 | Workflow rules (operator review process) |
| **hardware_facts** | 3 | Known quantities (reference info, not for AI) |

---

## Operator Rules (For AI Analysis)

These rules are loaded into the AI during miner analysis.

### Rule 1: POST-RESTART READY CHECK
**Status-based, not time-based**

After any restart or power cycle, wait until miner status = **MINING**.

Miner status progression:
- Starting
- Initializing
- Auto tuning
- **MINING** ← Clear to proceed

### Rule 2: DAILY LOG COLLECTION MANDATORY
Every online miner MUST get a fresh log collected daily at 1PM.
Logs collected **directly from miners**, bypasses AMS entirely.

### Rule 3: PCB/BOM QUALITY GATE
PCB=0110/BOM=0020 hardware revision has 4x higher failure rate.
See COMPLETE details in knowledge.json.

### Rule 4: S19J PRO RESTART PROTOCOL
After >3 restart failures: skip firmware restart, escalate to PDU cycle or replacement.
No smart PDUs on S19J Pros = physical site visit required.

### Rule 5: FLEET INVENTORY AUDIT TRIGGER
When analyzed count differs from fleet spec by >5 units → audit within 24 hours.

### Rule 6: ALERT DEDUPLICATION
- Same problem = ONE notification per day max
- Once ticket created in AMS = STOP alerting
- Operator will see tickets in AMS

---

## Pattern Rules (Machine-Readable)

### 1. CHIP_QUALITY_DEGRADATION_PATTERN
**Applies to:** Antminer S19J Pro

**Signals:**
- Efficiency loss trending downward 14+ days
- Chip Bin 3 classification
- PCB=0110/BOM=0020 hardware
- Hashrate below 70% of rated
- Normal temps but low output

**Action:** CREATE TICKET + MONITOR

### 2. PSU_VOLTAGE_DEGRADATION_PATTERN
**Applies to:** Antminer S19J Pro

**Signals:**
- Voltage fluctuation 14.35V-14.85V
- Hashrate volatility with normal temps
- All 3 boards affected simultaneously
- Precedes hashboard death by 3-5 days

**Action:** CREATE TICKET (PSU replacement) - Do NOT restart

### 3. COMPLETE_HARDWARE_FAILURE_PATTERN
**Applies to:** All miner types

**Signals:**
- Zero hashrate
- No temperature readings
- Miner unreachable

**Escalation:**
1. POWER CYCLE: No PDU = manual visit. Smart PDU = turn off socket, wait 10 sec, turn on
2. IF FAILS: Diagnose as BAD PSU
3. CREATE TICKET for PSU replacement
4. REMOVE FROM MONITORING - no more notifications

### 4. PSU_PARTIAL_CIRCUIT_FAILURE_PATTERN
**Applies to:** All miner types

**Signals:**
- Control board powered on (miner reachable)
- ALL hashboards dead simultaneously (0 ASICs)
- Restart loop or repeated fatal errors

**Root Cause:** PSU has dual circuits - control circuit working, hashboard circuit failed.
Rare for all 3 boards to fail at once - more likely PSU.

**Action:** CREATE TICKET → SLEEP MODE → REMOVE FROM MONITORING

---

## Process Rules (Workflow)

### OPERATOR VALIDATION WORKFLOW
1. Present what exists now
2. Present what is proposed
3. Operator answers YES/NO with explanation
4. Lock the decision

### APPROVAL REQUIRES EXPLANATION
All operator decisions (YES/NO) must include reasoning for AI learning.

---

## Hardware Facts (Reference Only)

Not loaded into AI analysis - just known quantities.

| Fact | Description |
|------|-------------|
| S19J Pro CT Fans | Manually set to 100%, no VFD feedback expected |
| S19J Pro Overheating | Aging hardware, not environmental. Fleet decommissioning in ~3 months |
| Warehouse Miners | 2 Auradines (AH3880) offline for maintenance (temporary) |

---

## Key Principles Established

1. **PATTERNS, NOT MINERS** - Rules describe situations/patterns, not specific miner IDs
2. **MODEL = SPECIFIC VARIANT** - S21, S21 XP, S21 Imm, S21 EXP Hydro are all different models
3. **STATUS-BASED, NOT TIME-BASED** - Wait for MINING status, not arbitrary timers
4. **HUMAN VALIDATION REQUIRED** - AI cannot lock rules without operator approval
5. **ONCE A DAY MAX** - Same problem = one notification per day
6. **TICKETS STOP ALERTS** - Once AMS ticket exists, stop Mining Guardian notifications

---

## Review Session Summary (2026-04-18)

**21 items reviewed:**
- 4 pattern rules created
- 6 operator rules kept/updated
- 2 process rules created
- 3 hardware facts established
- 1 rule merged into pattern
- 2 rules removed (obsolete)
- 3 rules moved to hardware_facts
- 2 rules moved to process_rules
- 1 proposal rejected (no lumping models)


---

## Updates — April 19, 2026

### New Approved Patterns

#### HEALTHY_BASELINE_S19JPRO
**Source:** `s19jpro_bixbit_4_0130_stable_hydro`

**Definition:** S19JPro BIXBIT/4/0130/4 cohort (7 miners) showing stable 88%+ hashrate with consistent thermal behavior.

**Use:** Benchmark for S19J Pro comparison. PCB=0130 + BiXBiT firmware = healthy performance baseline.

**Approved by:** Rob Fiesler, 2026-04-19

---

#### PSU_VOLTAGE_DEGRADATION_PATTERN — Signal 6 Added
**Source:** `voltage_regulation_failure_pattern_hydro`

**New Signal 6:** Hashrate volatility (0-200%) with stable temps (67-73°C) indicates PSU voltage issue even without direct voltage readings.

**Context:** Old PSUs pushed over max for 2+ years. This signal is great for future equipment, not a norm for current fleet.

**Approved by:** Rob Fiesler, 2026-04-19

---

#### HIGH_OFFLINE_FREQUENCY_PATTERN
**Source:** `s19jpro_catastrophic_offline_rates_hydro`

**Trigger:**
- Offline frequency >300 events per week
- Normal temps (69-73°C)
- Low hashrate (45-69%)

**Indicates:** Hardware instability (control board or PSU failure), NOT thermal issue.

**Action:** CREATE_TICKET — let operator decide on replacement. This catches miners in failing state between working and dead.

**Approved by:** Rob Fiesler, 2026-04-19

---

### Temporary: HVAC Work Pause

S21 Hydro, S21 Immersion, and Auradine AH3880 miners are OFF until Thursday April 24, 2026 for HVAC system work.

**Skip in analysis until:** 2026-04-24

**Hardware fact ID:** `hvac_work_apr2026`
