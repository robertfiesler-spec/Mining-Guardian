# Mining Guardian — AI Learning Roadmap
## Path to 48-Hour Full Autonomous Test

**Branch:** `feature/ai-learning-enhancements`
**Status:** ALL 8 FEATURES COMPLETE — Ready for 48hr test
**Rule:** Before building anything, examine every available data point. No unused signals.

---

## Current Mode
**FULL-DAY AUTONOMOUS** — Active 24/7
Overnight automation runs around the clock. LOW-risk actions execute without approval.
Max auto-restarts: 2 per window. All 6 services active on VPS.

---

## Available Data Points (full inventory)

| Table | Key Signals | Rows |
|---|---|---|
| miner_readings | hashrate_pct, temp_chip, temp_board, uptime, error_codes, consumption | 41,938 |
| chain_readings | voltage, freq_mhz, temp_board, hw_errors, rate_mhs, consumption_w | 23,562 |
| miner_state_readings | max_temp_board, max_temp_chip, hashrate_medium/low, temp ranges | 11,760 |
| pool_readings | accepted, rejected, rejection rate trend | 8,372 |
| hvac_readings | supply_temp, return_temp, delta_t, diff_pressure, VFD%, alarms | 817 |
| ams_notifications | hashrateDropLevel (874), hotBoard (498), workerOffline (5861) | 33,643 |
| log_metrics | psu_voltage (4M), chip_hashrate (1.2M), system_health (972k) | 6,142,167 |
| miner_hardware | chip_bin, bad_chips_count, pcb_version, ideal_hashrate | 12 |
| miner_restarts | outcome, hashrate_before/after, recovery_time_scans | 28 |
| weather_readings | outside temp, humidity | 854 |
| scans | total_miners, online, offline, issues | 855 |
| action_audit_log | decisions, denial reasons, outcomes | 328 |

---

## Feature Build Status

### Feature 1: Outcome Feedback Loop
**Status:** COMPLETE
**File:** `ai/outcome_checker.py`
**Data used:** miner_restarts, miner_readings, scans, knowledge.json
**What it does:** Labels every restart SUCCESS/FAILURE/PARTIAL/PENDING. Updates miner profiles in knowledge.json. Runs after every scan.
**First results:** 4 SUCCESS (.56, .227, .125, .48), 22 FAILURE (dead board miners)

### Feature 2: Confidence Scoring
**Status:** COMPLETE
**File:** `ai/confidence_scorer.py`
**Data used:** miner_restarts (outcomes), miner_readings (stability), fingerprint modifier
**What it does:** Scores 0-100 before any action. Gates: >=80 AUTO, 50-79 ASK, <50 HOLD. Shown in Slack as emoji 🟢🟡🔴.
**Weights:** per-miner success rate 60%, fleet rate 25%, stability 15%, fingerprint modifier ±15pts

### Feature 3: Denial Reason Capture
**Status:** COMPLETE
**File:** `api/slack_approval_listener.py`
**Data used:** Slack thread replies, action_audit_log
**What it does:** After DENY, bot asks "Why?" in thread. Stores reason in action_audit_log.notes as DENIAL_REASON:. Feeds weekly LLM training.

### Feature 4: Miner Fingerprinting v2
**Status:** COMPLETE (full data audit)
**File:** `ai/fingerprint_builder.py`
**Data used:** ALL available — miner_readings, chain_readings, miner_state_readings, pool_readings, ams_notifications, miner_hardware, miner_restarts, known_dead_boards
**What it does:** Per-miner behavioral profile with confidence_modifier (-0.5 to +0.5). Runs after weekly training.
**Modifiers:** voltage drop -15%, dead boards -30%, bad chips -5% each, hot board AMS alerts penalized, high rejection rate penalized

### Feature 5: HVAC/Environment Correlation
**Status:** COMPLETE
**File:** `ai/hvac_correlator.py`
**Data used:** hvac_readings, scans, miner_readings, weather_readings
**What it does:** Detects facility events when 3+ miners flag with HVAC stress. Pearson correlation supply_temp vs flags. Result: -0.029 (miner issues are hardware, not facility).
**Current:** 0% facility stress, facility running normally.

### Feature 6: Pre-Failure Prediction v2
**Status:** COMPLETE (full data audit — 11 signals)
**File:** `ai/predictor.py`
**Data used:** ALL available — miner_readings, chain_readings, miner_state_readings, pool_readings, ams_notifications, hvac_readings, miner_restarts
**11 signals:**
1. Hashrate trend decline (>15% over 5 scans)
2. Volatility spike (2.5x above baseline)
3. Board rate imbalance (30% divergence)
4. Chip temp creep (4°C rise, skips when HVAC stressed)
5. Historical pre-failure pattern match (shape similarity)
6. Board voltage drop (<14.2V — catches .45, .49 at 13.36V!)
7. Board temp elevated (>70°C, skips when HVAC stressed)
8. Pool rejection spike (>0.5%)
9. AMS alert spike in 24h (hashrateDropLevel, hotBoard, workerOffline)
10. Uptime reset detection (unscheduled reboot)
11. Max temp trending high (>80°C max board temp)
**First run (v2):** 10 predictions including .45 and .49 at 13.36V board voltage — completely invisible before

### Feature 7: Repair Shop Data Ingestion
**Status:** PENDING — blocked on dataset format from contact
**File:** TBD — `ai/repair_data_ingestor.py`
**Plan:** Normalize repair data to internal schema, merge via combine_knowledge.py

### Feature 8: Action Diversity
**Status:** COMPLETE (full data audit)
**File:** `ai/action_diversity.py`
**Data used:** miner_readings, chain_readings, miner_state_readings, pool_readings, ams_notifications, hvac_readings, config.json
**4 new action types:**
- POWER_PROFILE_DOWN (gate 75%): temp_chip, board_temp, max_temp, hvac_supply, current_profile — BiXBiT only
- POWER_PROFILE_UP (gate 80%): temp_chip, hvac_supply, hvac_delta_t, current_profile
- ECO_MODE_FLEET (gate 80%): hvac_supply >80°F, delta_t, pump VFD%
- POOL_FAILOVER (gate 85%): rejection rate 30-scan trend + AMS corroboration + backup_pool config
**First run:** .152 recommended POWER_PROFILE_UP (82% confidence, chip 67°C, conditions good)
**Note:** Pool failover requires config.backup_pool_url to be set

---

## New Rule (Applied Going Forward)
Before building any feature: audit every table, every column, every row count.
Use everything that's relevant. The data is the gold mine.

---

## 48-Hour Autonomous Test

**Ready to run.** Start after review pass on all 8 features.

**Test report will cover:**

| Metric | Description |
|---|---|
| Total actions taken | Count by type including new action types |
| Success rate | From outcome feedback per action type |
| Confidence calibration | Did high-confidence actions succeed more? |
| Predictions made | How many? How many preceded actual failures? |
| Fingerprint modifiers | Did per-miner modifiers improve accuracy? |
| Denial reasons captured | What did operator judgment add? |
| HVAC events | Facility vs miner problem separation |
| Action diversity | Power profiles, eco mode, pool actions taken |
| Fleet hashrate/uptime | vs 7-day baseline |

---

## Technical Notes
- HVAC/BAS integration is one-off for Rob's warehouse — not in future deployment templates
- S19JPro dead hashboard issues (.36, .177, .195) suppressed — AMS tickets #2662, #2663, #2661
- Pool failover requires backup_pool_url in config.json — not currently set
- Feature 7 blocked pending repair shop dataset format
- AH3880 board voltage 0.29V is Auradine firmware reporting format (not a real fault)
- All features compile clean, all 6 VPS services active
