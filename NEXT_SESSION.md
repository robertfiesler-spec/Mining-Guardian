# Next Session Priorities

**Last Updated:** April 16, 2026 (evening)
**Status:** Intelligence Report v2.2.0 LIVE on VPS — fleet data working, AMS data quality investigation needed

---

## IMMEDIATE — AMS Data Investigation

The fleet section of the Intelligence Report is now pulling real data from guardian.db, but the values appear to be rated/expected values rather than actual live readings. All readings are suspiciously round numbers.

**What we found:**
- `miner_state_readings.hashrate_medium` = 90000, 70000, 67500 GH/s (always round)
- `miner_state_readings.max_temp_chip` = 100.0, 90.0, 85.0, 80.0 (only 4 distinct values)
- `miner_state_readings.max_consumption` = 6000.0 (always the same)
- `chip_readings` table has 0 rows — per-chip data never collected
- `chain_readings` table exists but not checked yet
- All 32 S19J Pros show identical readings per scan

**What we need:**
1. Access AMS directly to see what real data looks like
2. Understand how Mining Guardian's scan loop collects data from AMS
3. Fix data collection to capture actual live readings (not rated specs)
4. Populate chip_readings with real per-chip temp/freq/voltage data

**Bobby offered AMS access via:**
- Web-based AMS (not localhost)
- Tailscale VPN access possible
- Also has AMS API available

---

## WEEKEND — Database Knowledge Review Session (Bobby has flights)

Bobby plans to use flight time to do a deep review of all manufacturers and capture correction rules for the Intelligence Catalog.

**What's ready:**
- Correction rules engine is live: `intelligence-catalog/data/correction_rules.json`
- WhatsMiner 0/3/6 cooling rules already done (44 auto-corrections)
- Pattern matching supports: `endswith:`, `startswith:`, `contains:`, `exact:`, `regex:`
- Can set any field: top-level, `specs.*`, or `enrichment.*`

**Models needing classification (don't fit 0/3/6 pattern):**
- WhatsMiner: M21, M32, M61, M64, M65, M72, M78, M79, M7d

**Manufacturers to review:**
- Bitmain (naming conventions, cooling variants, J/Pro/XP/Hydro suffixes)
- MicroBT (remaining non-0/3/6 models)
- Canaan (Avalon series patterns)
- Bitdeer, Auradine, Innosilicon, Ebang, StrongU

---

## ✅ COMPLETED — Intelligence Report v2.2.0 (April 16 evening)

- Fleet data rewrite: queries `miner_hardware.device_name` + `miner_state_readings` (actual guardian.db schema)
- 32 S19J Pros detected, 96 boards, online/offline status, hashrate, temps
- Hashrate GH/s → TH/s conversion, `miner_status` 0=online mapping
- 3-strategy device_name search (direct, normalized, short name)
- Board health tracking from `miner_hardware.bad_chips_count`
- Error boundaries on all API endpoints — no more 500 errors

## ✅ COMPLETED — Intelligence Report v2.1.1 (April 16 afternoon)

- Fixed 500 errors: 4 unsafe float() calls, slug suffix merge, error boundaries
- Dashboard proxy reads error body from 4xx/5xx responses

## ✅ COMPLETED — Intelligence Report v2.1 (April 16 morning)

- v2.1.0 deployed: 225 models, live BTC data, 3 correction rules
- Live BTC price from CoinGecko + network difficulty from mempool.space (15-min cache)
- Correction rules engine: JSON pattern matching, Bobby adds rules without code changes

## ✅ COMPLETED — Intelligence Report v2.0 (April 15 late evening)

- Full 9-section report: Hardware, Firmware, Fleet, Profitability, Market, Repair, Cooling, AI Analysis, Recommendations
- Slug merge: 10 duplicate model pairs consolidated (225 unique from 235 raw)
- Visual redesign: stat cards, progress bars, severity badges, table of contents

## ✅ COMPLETED — Intelligence Report v1.0 Dashboard (April 15 evening)

- Three deployment bugs found and fixed (REPO_DIR, mixed content, script stripping)
- Iframe approach working on Grafana 10.4.1

---

## REMAINING HIGH PRIORITY

### From Code Review (~5-6 hours)
- **CQ-6 to CQ-10:** 9 SQLite connections need context manager wrapping
  - api/approval_api.py (5 locations)
  - api/ams_alert_listener.py (5 locations)
  - api/slack_command_handler.py (1 location)
  - api/dashboard_api.py (1 location)
- **CQ-14, CQ-15:** Token access methods need lock wrapping (infrastructure done)
- **DG-4 to DG-15:** Predictor signal improvements (PSU voltage, time-of-day, spatial, board temp delta, chip freq deviation, pool stability, 7-day baseline)

### From P0 Build Queue
1. **Wire OpenClaw to guardian.db via guardian-db skill** — 2hr time budget
2. **Daily Log Capture remaining items:**
   - `firmware_changes` table + scan-loop change detector
   - `ai/regression_detector.py` + Slack alert wiring
   - VPS cron entries for 1pm collection + 4pm deep dive
3. **Weekly train denial reason ingestion gap** — verify before next Sunday
4. **Ship daily_deep_analyses permanent merge block** in train_cohort.py

### Intelligence Report Enhancements
- [ ] Fix AMS data collection — real readings instead of rated specs
- [ ] Qwen AI analysis paragraphs in reports (requires Qwen reachable from API)
- [ ] PDF download button in Grafana
- [ ] Auto-enrichment: catalog searches internet for updates daily
- [ ] Update Grafana landing page panel text from "235+" to "225 models"

---

## MEDIUM PRIORITY (~80 items from code review)
- Magic numbers → constants
- Duplicated code blocks
- Missing docstrings
- TODO comments

---

## guardian.db Schema Reference (discovered April 16)

**Tables with data:**
| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `miner_hardware` | Hardware inventory, 1 row per board | `miner_id` (AMS ID), `device_name` (model), `board_index`, `serial_number`, `chip_die`, `bad_chips_count` |
| `miner_state_readings` | Per-scan readings per miner | `miner_id`, `hashrate_medium` (GH/s), `max_temp_chip` (°C), `miner_status` (0=online, 3/6=issue), `max_consumption` (W) |
| `miner_restarts` | Restart history | `miner_id`, `ip`, `outcome`, `hashrate_before/after`, `recovery_time_scans` |
| `miner_baselines` | Learning baselines | `miner_id`, `model` (currently empty), `baseline_hashrate_ths`, `baseline_power_kw` |
| `scans` | Scan summaries | `total_miners`, `online`, `offline`, `issues` |
| `chip_readings` | Per-chip data (EMPTY) | `miner_id`, `board_index`, `chip_index`, `freq_mhz`, `voltage_mv`, `temp_c` |
| `chain_readings` | Per-chain data (unchecked) | TBD |
| `miner_logs` | Miner log entries | TBD |
| `pool_readings` | Pool stats | TBD |
| `hvac_readings` | HVAC data | TBD |

**Bobby's fleet:** 32 Antminer S19j Pro, 96 boards (3 per miner), AMS IDs in 53xxx-64xxx range

**Key facts:**
- `miner_id` = AMS inventory number (not IP, not model name)
- `hashrate_medium` is in GH/s (divide by 1000 for TH/s)
- `miner_status`: 0 = online/normal (44,451 readings), 3 = issue (1,509), 6 = critical (198)
- `max_temp_chip` only has 4 distinct values: 100, 90, 85, 80 — likely rounded or rated

---

**Current Status: v2.2.0 LIVE — Fleet data connected but AMS data quality needs investigation**
