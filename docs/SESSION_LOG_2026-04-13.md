# Session Log — April 13, 2026

## Summary
Four major work streams completed today: (1) S19J Pro HVAC integration, (2) morning operational fixes, (3) Mining Intelligence Catalog database deployment — the catalog is now live on ROBS-PC with 313 seed models, schema fixes verified, and deep research enrichment applied to 211 models, and (4) Intelligence Catalog data importer — built, bug-fixed, deployed, and first live import completed (1,244 files processed, 0 failed).

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

## Session 4 — Intelligence Catalog Data Importer (~9:00–11:10 AM CDT)

This session built, debugged, and deployed the Intelligence Catalog's data importer, then ran the first live import on Bobby's Telegram log archive.

### Background

With the catalog schema deployed and 313 models seeded, the next step was building the machinery to actually ingest miner data — log files, spec sheets, archives from repair shops, Telegram dumps, etc. The importer needed to detect which manufacturer and model a file belongs to, parse it with the right brand-specific parser, run diagnostics, register unknown fields via auto-discovery, and store everything in PostgreSQL.

### Work Completed

#### 1. Importer Built and Deployed (commit `0a37f94`)
Complete importer pipeline at `intelligence-catalog/importer/` — 22 files, 4,602+ lines:

| Component | File(s) | Purpose |
|-----------|---------|--------|
| Brand detector | `detector.py` | Identifies Bitmain, MicroBT, Canaan, Auradine from filenames, content, MAC/IP prefixes |
| Parsers | `parsers/*.py` | 6 parsers: Bitmain, MicroBT, Canaan, Auradine, CSV, generic fallback |
| Auto-discovery | `discovery.py` | Registers unknown fields in `knowledge.unknown_fields` — never skips |
| Diagnostics | `diagnostics/*.py` | Universal + brand-specific test battery on every file |
| DB layer | `db.py` | PostgreSQL writes to 4 new tables |
| Orchestrator | `importer.py` | Walks archives/folders, coordinates detection → parsing → diagnostics → storage |
| Models | `models.py` | Data classes for import results, file metadata, diagnostic outcomes |
| Config | `config.py` | Database connection, paths, thresholds |
| Schema | `schema_additions.sql` | 4 new tables + 5 indexes |

Schema additions deployed to ROBS-PC:
- `knowledge.import_jobs` — tracks every import run
- `knowledge.imported_files` — every file with hash, detected brand/model, parsed JSONB data
- `ops.import_diagnostic_results` — per-file test results
- `ops.import_patterns` — cross-file pattern detection

#### 2. Dry Run #1 — Identified 3 Bugs
First dry run on Bobby's Telegram archive revealed:
- T21 archive files with special characters (parentheses, spaces) crashed the zip extraction
- Encrypted zip files crashed the entire import instead of being skipped
- MicroBT WhatsMiner system logs were being misidentified as Bitmain (wrong brand detection)

#### 3. Bug Fixes (commit `bdca6e5`)
All three bugs fixed in `extractor.py` and `detector.py`:
- T21 fix: Archive name sanitization before extraction, handles parentheses/spaces/special chars
- Encrypted zip fix: Try-catch around zip extraction, graceful skip with `processing_status='skipped'` and note "Encrypted archive"
- MicroBT fix: Added WhatsMiner-specific content signatures ("WhatsMiner", "btminerng", "MicroBT"), boosted MicroBT filename pattern weights, added negative signal for Bitmain when WhatsMiner patterns detected. Confidence improved to 0.95.

Bobby deployed: `git pull` — 2 files changed, 47 insertions, 7 deletions.

#### 4. Dry Run #2 — All Fixes Confirmed
Second dry run showed dramatic improvement:

| Metric | Dry Run 1 | Dry Run 2 |
|--------|-----------|----------|
| Total files | 622 | 1,796 |
| Processed | 307 | 1,244 |
| T21 extracting | No (crash) | Yes |
| Encrypted files | Crash | Graceful skip |
| MicroBT detection | Misidentified | 0.95 confidence |

#### 5. First Live Import — SUCCESS
Bobby approved and ran the live import:

| Metric | Count |
|--------|-------|
| Total files found | 1,796 |
| Files processed | 1,244 |
| Files skipped | 552 |
| Files failed | 0 |
| Flagged needs_review | 1,136 |

Miners detected: S19 XP, S19 Pro+ Hyd, S19i, S19j+, S19j Pro, S19j Pro+, S19j XP, S19k Pro, T21, MicroBT M20S, M21S, M30S++

The importer auto-discovered 62+ unique fields from WhatsMiner system logs that were not in the field registry — validating the auto-discovery mechanism built into the V3 schema.

Source archive: `C:\Users\user\Downloads\Telegram Desktop\logs (3).zip`

### Key Technical Decisions Made

1. **Confidence-based brand detection** — Instead of simple pattern matching, the detector uses a weighted scoring system across filename patterns, content signatures, MAC prefixes, and IP ranges. This handles ambiguous files (e.g., WhatsMiner logs that mention Bitmain chip names) by looking at the preponderance of evidence.
2. **Independent file processing** — Each file is processed independently. One failure does not stop the import. Files that fail are marked `failed` with a note, not silently dropped.
3. **needs_review as default** — Any file that the importer cannot confidently match to a catalog model gets flagged `needs_review` rather than auto-approved. Bobby reviews these manually. This is conservative by design.
4. **Auto-discovery first** — Unknown fields are registered in `knowledge.unknown_fields` before any parsing happens. The importer literally cannot skip a field it doesn't recognize.

### Commits
- `0a37f94` — feat(importer): add complete Intelligence Catalog data importer
- `bdca6e5` — fix: importer — T21 archive names, encrypted zips, MicroBT detection

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
| cc829e2 | docs: comprehensive documentation update — Intelligence Catalog LIVE, HVAC integration, architecture |
| 0a37f94 | feat(importer): add complete Intelligence Catalog data importer |
| bdca6e5 | fix: importer — T21 archive names, encrypted zips, MicroBT detection |

---

## End-of-Day State

### What's Running
- Mining Guardian daemon — LIVE, scanning fleet every hour
- Dashboard API — LIVE on VPS:8585
- Approval API — LIVE on VPS:8686
- HVAC collector — LIVE on Mac, polling both systems
- Intelligence Catalog DB — LIVE on ROBS-PC in Docker (mining-guardian-db container)

### What's Next
- Resolve 12 unmatched enrichment entries (Canaan Gen summaries, M63 Hydro 356TH, Nano 3/3S combined, naming mismatches)
- Triage the 1,136 needs_review import files
- Continue intelligence catalog research enrichment (PSU data, hashboard details, control board specs)
- Begin populating Schema V2/V3 tables with operational and firmware data

---

*Session 1 started: ~3:30 AM CDT*
*Session 2 started: ~5:35 AM CDT*
*Session 3 started: ~6:00 AM CDT*
*Session 4 started: ~9:00 AM CDT*
*Documentation update: ~11:10 AM CDT*
