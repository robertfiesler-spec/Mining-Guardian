# Mining Guardian — Confidence Scoring System

## Overview

The confidence scoring system rates how confident the AI is before taking any action. Higher confidence = more likely to succeed based on historical data.

**Gates:**
- **≥ 80%** → AUTO: Execute automatically (overnight automation)
- **50-79%** → ASK: Send to Slack for human approval
- **< 50%** → HOLD: Do not act, alert only

---

## Where Confidence is Calculated

**File:** `ai/confidence_scorer.py`

**Entry Point:** `get_confidence(miner_id, ip, action_type, hashrate_pct=None)`

**Returns:** `(confidence_score: int, reason: str)`

---

## Scoring Formula

### Three Components (weighted average):

| Component | Weight | Source | What it measures |
|-----------|--------|--------|------------------|
| **Miner History** | 60% | `miner_restarts` table | Success rate for THIS specific miner |
| **Fleet History** | 25% | `miner_restarts` table | Success rate across ALL miners (fallback) |
| **Stability** | 15% | `miner_readings` table | Hashrate variance (volatile = lower confidence) |

### Additional Modifiers:

| Modifier | Range | Source | When applied |
|----------|-------|--------|--------------|
| **Fingerprint Risk** | ±15 pts | `knowledge.json` | Poor restart history in fingerprint |
| **Pre-Failure Penalty** | -5 to -15 pts | `knowledge.json` | Active prediction signals |

---

## How Each Component Works

### 1. Miner Success Rate (60% weight)

```sql
SELECT outcome, COUNT(*) FROM miner_restarts
WHERE miner_id = ? AND restarted_at >= (30 days ago)
  AND outcome IN ('SUCCESS', 'FAILURE', 'PARTIAL')
GROUP BY outcome
```

**Calculation:**
- SUCCESS counts as 1.0
- PARTIAL counts as 0.5
- FAILURE counts as 0.0
- Rate = (SUCCESS + PARTIAL*0.5) / TOTAL * 100

**Trust Threshold:**
- ≥ 3 outcomes: Full weight (60%)
- 1-2 outcomes: Partial weight (proportional blend with fleet)
- 0 outcomes: Uses fleet rate only

### 2. Fleet Success Rate (25% weight)

Same calculation as miner rate, but across all miners.

**Current Stats (April 13, 2026):**
- 76 total outcomes
- 43 SUCCESS, 31 FAILURE, 2 PARTIAL
- **Fleet success rate: 58%**

### 3. Stability Score (15% weight)

```sql
SELECT hashrate_pct FROM miner_readings
WHERE miner_id = ? AND status = 'online'
ORDER BY id DESC LIMIT 10
```

**Calculation:**
- Uses coefficient of variation (CV) = std_dev / mean
- CV of 0 (perfectly stable) → 100% stability
- CV of 0.5+ (very volatile) → 0% stability

**Example:**
- Hashrates: [95, 96, 94, 95, 97] → CV ≈ 0.01 → Stability 98%
- Hashrates: [50, 100, 30, 90, 60] → CV ≈ 0.4 → Stability 20%

---

## Data Sources

### miner_restarts table

Stores every restart with outcome:

```sql
CREATE TABLE miner_restarts (
    id INTEGER PRIMARY KEY,
    miner_id TEXT,
    ip TEXT,
    model TEXT,
    restart_type TEXT,      -- 'AUTO_OVERNIGHT_RESTART', 'MANUAL_APPROVED', etc.
    restarted_at TEXT,
    outcome TEXT,           -- 'SUCCESS', 'FAILURE', 'PARTIAL', 'PENDING'
    hashrate_before REAL,
    hashrate_after REAL,
    recovery_time_scans INTEGER
);
```

**How outcomes are determined:**

| Outcome | Criteria |
|---------|----------|
| SUCCESS | Hashrate improved AND stayed stable for 2+ scans |
| FAILURE | Hashrate worse OR miner went offline |
| PARTIAL | Some improvement but not back to rated |
| PENDING | Not enough time to evaluate yet |

### miner_readings table

Stores scan data every 30-60 minutes:

```sql
CREATE TABLE miner_readings (
    id INTEGER PRIMARY KEY,
    scan_id INTEGER,
    miner_id TEXT,
    ip TEXT,
    hashrate_pct REAL,  -- Current hashrate as % of rated
    status TEXT,        -- 'online', 'offline', 'ams_sync'
    temp_chip REAL,
    temp_board REAL
);
```

---

## Example Calculations

### Example 1: New Miner (No History)

**Input:** miner_id=53999, ip=192.168.188.250, action=RESTART

**Data:**
- Miner outcomes: 0
- Fleet success: 58% (76 outcomes)
- Stability: 85%

**Calculation:**
```
history_score = fleet_score = 58%  (no miner data)
raw = 58% * 0.85 + 85% * 0.15 = 49.3% + 12.75% = 62%
```

**Result:** 62% [ASK] — "this miner: no history yet | fleet: 58% (76 outcomes) | stability: 85%"

### Example 2: Reliable Miner

**Input:** miner_id=53486, ip=192.168.188.56, action=RESTART

**Data:**
- Miner outcomes: 4 SUCCESS, 0 FAILURE = 100%
- Fleet success: 58%
- Stability: 95%

**Calculation:**
```
miner_score = 100%
history_score = (100% * 0.6 + 58% * 0.25) / 0.85 = 87.6%
raw = 87.6% * 0.85 + 95% * 0.15 = 74.5% + 14.25% = 88.75%
```

**Result:** 89% [AUTO] — "this miner: 100% success (4 outcomes) | fleet: 58% | stability: 95%"

### Example 3: Problematic Miner

**Input:** miner_id=53477, ip=192.168.188.36, action=RESTART

**Data:**
- Miner outcomes: 0 SUCCESS, 7 FAILURE = 0%
- Fleet success: 58%
- Stability: 60%
- Fingerprint risk: +15 pts (poor restart history)

**Calculation:**
```
miner_score = 0%
history_score = (0% * 0.6 + 58% * 0.25) / 0.85 = 17.1%
raw = 17.1% * 0.85 + 60% * 0.15 = 14.5% + 9% = 23.5%
+ fingerprint penalty = -15 pts
= 8.5% → 9%
```

**Result:** 9% [HOLD] — "this miner: 0% success (7 outcomes) | fleet: 58% | stability: 60%"

---

## Where Confidence is Used

### 1. Overnight Automation (`core/overnight_automation.py`)

```python
# Only auto-execute if confidence >= 80%
conf, _ = get_confidence(miner_id, ip, action_type)
if conf >= 80:
    execute_action(action)
else:
    skip_action(action, reason="confidence too low")
```

### 2. Slack Approval Messages (`core/mining_guardian.py`)

```python
# Show confidence in approval request
conf, reason = get_confidence(miner_id, ip, action)
message = f"*{action}* for {ip}\nConfidence: {conf}%\n{reason}"
```

### 3. Dashboard Display (`api/ai_dashboard_api.py`)

- Recent Autonomous Actions table
- Pre-Failure Predictions table
- Live Action Queue

---

## How to Improve Confidence

1. **Record Outcomes** — Every restart gets labeled SUCCESS/FAILURE/PARTIAL
2. **Build History** — More outcomes = more trusted miner-specific rate
3. **Reduce Volatility** — Stable hashrates = higher stability score
4. **Learn Patterns** — Fingerprints capture behavioral issues

---

## Files Involved

| File | Purpose |
|------|---------|
| `ai/confidence_scorer.py` | Main scoring logic |
| `core/database.py` | `record_restart()`, `update_restart_outcome()` |
| `core/overnight_automation.py` | Uses confidence to gate auto-execution |
| `core/mining_guardian.py` | Shows confidence in Slack messages |
| `api/ai_dashboard_api.py` | Displays confidence in dashboard |

---

## Recent Fixes (April 13, 2026)

**Bug:** `_action_to_restart_type()` filtered to only MANUAL_APPROVED
- This excluded AUTO_OVERNIGHT restarts from history
- Fleet showed 24% (23 outcomes) instead of 58% (76 outcomes)

**Fix:** RESTART now counts ALL restart types
- Commit: 110bced
