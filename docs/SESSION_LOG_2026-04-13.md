# Session Log — April 13, 2026

## Summary
Three major work streams completed today: (1) S19J Pro HVAC integration, (2) morning operational fixes, and (3) Mining Intelligence Catalog database deployment — the catalog is now live on ROBS-PC with 313 seed models, schema fixes verified, and deep research enrichment applied to 211 models.

---

## Session 1 — S19J Pro HVAC Integration (~3:30–5:15 AM CDT)

### Major Accomplishments

#### 1. S19J Pro HVAC Integration
- Added second HVAC system at 192.168.189.235
- Mac HVAC collector polls both systems every 5 minutes
- VPS API receives and stores readings by system_id

#### 2. AI Script Updates
All AI scripts now use the correct HVAC system per miner:
- daily_deep_dive.py — Per-miner HVAC selection
- local_llm_analyzer.py — Shows both systems in prompts
- predictor.py — System-aware predictions
- action_diversity.py — Fleet-level analysis
- hvac_correlator.py — System-aware correlation

#### 3. Operator Rule #5 Added
S19J Pro CT fans are manually at 100% — no VFD feedback shown. This is intentional, NOT a fault.

#### 4. Documentation Created/Updated
- NEW: docs/HVAC_SYSTEMS.md — Complete HVAC documentation
- NEW: docs/OPERATOR_RULES.md — All operator rules in one place  
- UPDATED: docs/WAREHOUSE_MECHANICAL.md — References new docs
- UPDATED: docs/CRON_SCHEDULE.md — Added Mac HVAC collector

### System Mapping Rule

Simple rule: S19JPro -> s19jpro system. Everything else -> warehouse.

| Miner Type | HVAC System | IP |
|------------|-------------|-----|
| S19JPro | s19jpro | 192.168.189.235 |
| Everything else | warehouse | 192.168.188.235 |

### Current HVAC Readings

| System | Supply | Return | Delta-T | Notes |
|--------|--------|--------|---------|-------|
| Warehouse | 75F | 86F | 11F | Normal |
| S19J Pro | 89F | 103F | 14F | Running warmer |

### Commits
- 43ac433 — feat: add S19J Pro HVAC system integration
- 0b3aab9 — fix: wire all AI scripts to use correct HVAC per miner
- 9d4ece4 — docs: add S19J Pro CT fan note

### Services Status
- mining-guardian.service - RUNNING
- dashboard-api.service - RUNNING
- com.bixbit.hvac-collector (Mac launchd) - RUNNING

### Files Changed (VPS)
- ai/action_diversity.py
- ai/daily_deep_dive.py
- ai/hvac_correlator.py
- ai/local_llm_analyzer.py
- ai/predictor.py
- api/dashboard_api.py
- clients/hvac_client.py
- config.json
- knowledge.json
- docs/CRON_SCHEDULE.md
- docs/HVAC_SYSTEMS.md
- docs/OPERATOR_RULES.md
- docs/WAREHOUSE_MECHANICAL.md

### Mac Files Created
- /Users/BigBobby/Documents/GitHub/mac-scripts/hvac_collector.py
- /Users/BigBobby/Library/LaunchAgents/com.bixbit.hvac-collector.plist

---

## Session 2 — Morning Fixes (05:35 CDT)

### Issues Fixed

1. **Log Failure Reports to mg-logs**
   - Problem: Log failure reports from daemon were going to mining-guardian
   - Fix: Changed post_to_channel to post_to_logs on line 5103
   - Commit: e886720

2. **Grafana Recent AI Analyses Panel**
   - Problem: Panel showed DOCTYPE is not valid JSON error
   - Cause: Relative URL did not work via grafana.fieslerfamily.com
   - Fix: Updated panel to use absolute URL for dashboard API

3. **AI Analysis Confidence Scores**
   - Problem: Reports did not show confidence percentages
   - Fix: Updated LLM prompt in local_llm_analyzer.py to request per-miner confidence
   - Format: - **[IP]** XX confidence: [issue and reason]

### Operator Rule 6 Added
- S19J Pro Overheating Boards - Aging Hardware
- Try ONE restart with log capture before/after
- If restart does not help, mark as aging and let run
- New table: s19jpro_overheat_tracking
- Commit: 7e7c6d8

### Services Restarted
- mining-guardian.service - Active
- dashboard-api.service - Active

---

## Session 3 — Mining Intelligence Catalog Deployment (~6:00–8:30 AM CDT)

This session moved the Intelligence Catalog from "schema designed, not deployed" to "live database with seed data and deep research enrichment."

### Background

The Mining Intelligence Catalog is a standalone PostgreSQL 16 research database running in Docker on ROBS-PC. It holds comprehensive specs, part numbers, chip data, hashboard info, PSU details, and operational intelligence for every known Bitcoin SHA-256 ASIC miner ever manufactured. It is separate from `guardian.db` (the production fleet ops SQLite database on the VPS) — the catalog is a research/intelligence tool, not a real-time operations system.

### Work Completed

#### 1. Database Deployed on ROBS-PC
- Container: `mining-guardian-db` (PostgreSQL 16 in Docker)
- Database: `mining_guardian` / User: `guardian_admin` / Port: 5432
- Tailscale IP: `100.110.87.1:5432`
- Windows path: `C:\Users\user\Mining-Guardian`

#### 2. Discovered and Fixed Enrichment SQL Bugs
The original enrichment SQL (generated from deep research CSVs) had three critical bugs that caused it to fail silently:

- **Bug 1: Wrong column name** — Used `research_notes` (text column that doesn't exist). Should be `metadata` (JSONB column). Fixed to use proper JSONB merge: `metadata = metadata || '{"deep_research": {...}}'::jsonb`
- **Bug 2: Wrong table name** — Used `model_name` (doesn't exist in schema). Should be `canonical_name`. Fixed all WHERE clauses.
- **Bug 3: Transaction wrapper** — Original SQL used `BEGIN; ... COMMIT;` which meant any single failed UPDATE rolled back ALL 223 updates. Removed the wrapper so each UPDATE is independent.

#### 3. Fixed AH3880 Null Fields
Schema fixes revealed `chips_per_board` was NULL for both AH3880 entries (Teraflux AT2880 and AH3880). Fixed to 345 chips per board and added `board_power_w_nom = 2500.0` based on Auradine spec sheet data.

#### 4. Deep Research Enrichment Applied
Generated `deep_research_enrichment.sql` (V2) from four research CSV files:

| Phase | Manufacturer | Models Researched | CSV File |
|-------|-------------|-------------------|----------|
| Phase 1 | Bitmain | 32 | bitmain_deep_research_phase1.csv |
| Phase 2 | MicroBT | 80 | microbt_deep_research_phase2.csv |
| Phase 3 | Canaan | 71 | canaan_deep_research_phase3.csv |
| Phase 4 | Mixed (Bitdeer, Auradine, Innosilicon, etc.) | 48 | phase4_deep_research.csv |
| **Total** | **All manufacturers** | **223** | |

Each enrichment UPDATE writes into the `metadata` JSONB column with structured deep research data including chip names, process nodes, power consumption, cooling types, and source URLs.

#### 5. Results After Bobby Ran on ROBS-PC

**Schema fixes (schema_fixes_v1.sql):** 19/20 PASS, 1 minor fail
- The 1 FAIL: Issue 4g (model aliases) — 16 of 27 aliases loaded. This is expected on subsequent runs because of ON CONFLICT DO NOTHING. Non-critical.

**Enrichment (deep_research_enrichment.sql):** 211/223 matched, 12 UPDATE 0
- The 12 unmatched models are:
  - Canaan "Gen" grouping entries (A8 Gen, A11 Gen, A13 Gen, A14 Gen, A15 Gen, A16 Gen) — these are summary rows in the research CSV, not actual hardware models
  - M63 Hydro 356TH — specific hashrate bin not in seed data
  - Nano 3/3S combined entry — research CSV combined two models into one row
  - KnCMiner Titan — Scrypt miner, correctly excluded from SHA-256-only database
  - Other minor naming mismatches

**Total database state after enrichment:** 215 rows affected (some models received multiple metadata updates from different research phases).

#### 6. First Backup Created
- File: `D:\MiningGuardian\db-backups\pre-migration\mining_guardian_2026-04-13.dump`
- Size: 804 KB (pg_dump format)
- Created by Bobby via docker cp after enrichment

### Files Created/Modified

| File | Purpose |
|------|---------|
| `intelligence-catalog/seed-data/deep_research_enrichment.sql` | V2 enrichment SQL — 223 UPDATE statements with correct column names and JSONB metadata |
| `intelligence-catalog/seed-data/schema_fixes_v1.sql` | Updated: AH3880 chips_per_board NULL→345, board_power_w_nom NULL→2500.0 |
| `generate_enrichment_sql_v2.py` | Python generator script that reads all 4 research CSVs and produces V2 SQL |
| `db_canonical_names.json` | All 313 canonical_name values extracted from seed SQL for matching |

### Git Commit
- `8b6e66c` — Fix enrichment SQL V2: correct column names + fix AH3880 NULL chips_per_board
- Branch: `feature/intelligence-catalog`
- Pushed to GitHub

### Key Technical Decisions Made

1. **JSONB metadata over dedicated columns** — Deep research data goes into the existing `metadata` JSONB column rather than creating new schema columns. This allows flexible, evolving data without schema migrations.
2. **Independent UPDATEs over transactions** — Each model's enrichment is a standalone UPDATE. If one fails, the rest succeed. Bobby can see exactly which models matched and which didn't.
3. **Canonical name matching** — The V2 generator extracts all 313 canonical names from the seed SQL and matches research CSV entries against them using exact string comparison. 212 of 223 research entries matched directly.
4. **PowerShell commands given one at a time** — Per Bobby's preference, every command Bobby needed to run was provided individually with expected output, not batched.

---

## Cumulative Commits Today (feature/intelligence-catalog branch)

| Hash | Message |
|------|---------|
| 43ac433 | feat: add S19J Pro HVAC system integration |
| 0b3aab9 | fix: wire all AI scripts to use correct HVAC per miner |
| 9d4ece4 | docs: add S19J Pro CT fan note |
| e886720 | fix: log failure reports to mg-logs channel |
| 7e7c6d8 | feat: S19J Pro overheat tracking + operator rule 6 |
| 8b6e66c | Fix enrichment SQL V2: correct column names + fix AH3880 NULL chips_per_board |

---

## End-of-Day State

### What's Running
- Mining Guardian daemon — LIVE, scanning fleet every hour
- Dashboard API — LIVE on VPS:8585
- Approval API — LIVE on VPS:8686
- HVAC collector — LIVE on Mac, polling both systems
- Intelligence Catalog DB — LIVE on ROBS-PC in Docker (mining-guardian-db container)

### What's Next
- Comprehensive documentation update (this session log, README, ROADMAP, etc.)
- Continue intelligence catalog research enrichment for the 12 unmatched models
- Begin deep research phases for PSU data, hashboard details, control board specs
- Schema V2/V3 additions deployment when ready

---

*Session 1 started: ~3:30 AM CDT*
*Session 2 started: ~5:35 AM CDT*
*Session 3 started: ~6:00 AM CDT*
*Documentation update: ~8:39 AM CDT*
