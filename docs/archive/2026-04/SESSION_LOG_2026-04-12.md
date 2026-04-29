# Session Log — April 12, 2026

## Overview
Major housekeeping, documentation, and AI data gap audit session. Fixed multiple issues and prepared the system for the nightly Claude training run.

## Session Timeline

### Morning/Early Afternoon (prior session)
- AMS log overflow fix — deleted 829 logs, created cleanup script
- Created `docs/CRON_SCHEDULE.md`
- External HDD backup completed
- Log collection: 20/49 miners (41% coverage)

### Afternoon Continuation (~3:30pm - 5:00pm CDT)

#### 1. Grafana AI Dashboard — Confidence % Fix
**Issue**: Bobby noticed confidence percentages were not showing next to AI data in Grafana.

**Root Cause**: `ai_dashboard_api.py` had tables without Conf columns.

**Fix** (commit `84f1f83`):
- Added Conf column to Action Queue table (between Action and HR)
- Added Conf column to Auto Actions table (between Action and Outcome)
- Added Conf column to Predictions table (between Action and Detail)
- Color-coded: green ≥80%, orange 50-79%, red <50%
- Fixed `import re` shadowing bug causing UnboundLocalError

**Files Changed**: `api/ai_dashboard_api.py`

#### 2. Slack Log Failure Report Method Fix
**Issue**: `post_message()` was wrong method name.

**Fix** (commit `2946838`): Changed to `post_to_channel()`

#### 3. New Feature: 4:15pm Daily Log Failure Report
**Request**: Bobby wanted a list of miners that FAILED to get logs sent to Slack at 4:15pm so he could investigate before leaving work.

**Implementation** (commit `4dd1f98`):
- Created `scripts/daily_log_failure_report.py`
- Sends to #mg-logs channel (commit `474b119` fixed channel)
- Groups miners by Online vs Offline
- Shows coverage percentage
- Added to cron: `15 16 * * *`

#### 4. Comprehensive AI Data Gap Audit
Audited all 23 database tables and all AI scripts to find gaps.

**Fixed This Session**:
- `chain_detaches` and `chain_attaches` were computed but NOT saved to fingerprints
- Fix (commit `fcabbcf`): Added to fingerprint output in `fingerprint_builder.py`

**Remaining Gaps Documented** (future improvements):
1. `chip_hashrate` — 2.6M rows of per-chip data NOT USED
2. `psu_voltage` — 9.5M rows, only min_voltage extracted
3. `system_health` — 2.3M rows NOT USED
4. `llm_analysis` — 839 rows of past analyses NOT feeding back
5. `pending_approvals` — approval/denial patterns NOT analyzed

## Git Commits (This Session)
```
fcabbcf feat: add chain_detaches/chain_attaches to fingerprint output
474b119 fix: send log failure report to #mg-logs instead of #mining-guardian
bfbe0ce docs: add 4:15pm log failure report to CRON_SCHEDULE.md
4dd1f98 feat: add 4:15pm daily log failure report to Slack
2946838 fix: use correct Slack method for log failure reports
4fecab6 docs: add repair entry for confidence % fix in AI dashboard
84f1f83 feat: add confidence % column to all AI dashboard tables
```

## Cron Schedule (Final)

| Time | Script | Purpose |
|------|--------|---------|
| 4:00am | `ai/backup_knowledge.py` | GitHub backup of knowledge.json |
| 7:00am | `scripts/morning_briefing.py` | Morning Slack report |
| 10:00am | `scripts/cleanup_ams_logs.py` | Delete ALL AMS logs (stored in DB) |
| 1:00pm | `scripts/daily_collect_logs.py` | Fresh log collection for all miners |
| 4:00pm | `ai/daily_deep_dive.py` | Qwen per-miner analysis (Pass 1) |
| 4:15pm | `scripts/daily_log_failure_report.py` | Slack report of failed log collections |
| 12:00am | `ai/weekly_train.py` | Claude cohort training (Pass 2) |
| 1:00am | `ai/refinement_chain.py` | Qwen reflection + Claude merge (Pass 3+4) |

**Note**: Claude training currently runs DAILY (until ~April 25) for catch-up learning. After April 25, reverts to Sunday-only.

## Data Inventory — What AI Has Access To

### Database Tables (23 total)
| Table | Rows | Used By AI? |
|-------|------|-------------|
| miner_readings | 71,485 | ✅ All AI scripts |
| chain_readings | 85,628 | ✅ deep_dive, fingerprints |
| pool_readings | 30,048 | ✅ deep_dive, fingerprints |
| hvac_readings | 1,436 | ✅ deep_dive, hvac_correlation |
| weather_readings | 1,396 | ✅ deep_dive |
| miner_logs | 995 | ✅ deep_dive, local_llm |
| action_audit_log | 853 | ✅ train_cohort, fingerprints |
| miner_restarts | 77 | ✅ train_cohort, fingerprints |
| miner_hardware | 90 | ✅ train_cohort, fingerprints |
| miner_state_readings | 40,964 | ✅ action_diversity, fingerprints |
| miner_ams_extended | 40,964 | ✅ fingerprints |
| log_metrics | 14,408,856 | ⚠️ Partially (chain_events only) |
| ams_notifications | 57,883 | ✅ predictor, fingerprints |
| known_dead_boards | 21 | ✅ fingerprints, predictor |
| scans | 1,458 | ✅ deep_dive, local_llm |
| llm_analysis | 839 | ❌ Write-only, not read |
| pending_approvals | 660 | ❌ Queue only, not learning |
| alert_listener_* | ~2,800 | Internal use only |

### Knowledge.json Contents
- 58 miner fingerprints (with chain_detaches/attaches now!)
- 50 known issues
- 19 refined insights
- 7 patterns
- 4 operator rules
- 200 predictions
- 10 cross-miner analyses
- 50 LLM scan analyses
- HVAC correlation data

## Known Data Gaps (Future Improvements)

### 1. Per-Chip Hashrate (chip_hashrate) — 2.6M rows
- **Data**: Per-chip hashrate vs expected (value_1 = actual, value_2 = expected)
- **Value**: Identify weak/dead chips (value_1 = 0.0)
- **Status**: NOT USED by any AI script
- **Priority**: HIGH — gold data for chip-level diagnostics

### 2. PSU Voltage Trends — 9.5M rows
- **Data**: PSU voltage readings from cgminer logs
- **Current Use**: Only min_voltage extracted for fingerprints
- **Missing**: Trend analysis, degradation detection, failure prediction
- **Priority**: MEDIUM

### 3. System Health — 2.3M rows
- **Data**: CPU/memory health from cgminer logs
- **Status**: NOT USED
- **Priority**: LOW

### 4. LLM Analysis Feedback — 839 rows
- **Data**: Previous Claude/Qwen analyses stored in llm_analysis table
- **Issue**: Written but never read during training
- **Value**: AI could learn from its own past analyses
- **Priority**: MEDIUM

### 5. Approval Pattern Learning — 660 rows
- **Data**: pending_approvals with 162 approved, 242 denied, 245 expired
- **Issue**: Not feeding into learning
- **Value**: Learn what operator prefers to approve/deny
- **Priority**: LOW

## Files Created/Modified This Session

### Created
- `scripts/daily_log_failure_report.py` — 4:15pm Slack report
- `docs/SESSION_LOG_2026-04-12.md` — This file

### Modified
- `api/ai_dashboard_api.py` — Added confidence columns
- `ai/fingerprint_builder.py` — Added chain_detaches/attaches
- `core/mining_guardian.py` — Fixed Slack method call
- `docs/CRON_SCHEDULE.md` — Added 4:15pm report
- `REPAIR_LOG.md` — Added confidence % fix entry

## Tonight's Run (Midnight)
Everything critical is connected. The Claude training at midnight will have:
- All 15 data tables feeding properly
- Chain attach/detach data in fingerprints (NEW)
- Full action audit log with outcomes
- HVAC correlation data
- 58 miner fingerprints
- All fixes from this week wired in

## Next Session Priority
1. Per-chip hashrate analysis (2.6M rows of unused gold)
2. LLM analysis feedback loop
3. Approval pattern learning

---
*Session ended ~5:00pm CDT, April 12, 2026*
