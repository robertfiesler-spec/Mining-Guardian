# Mining Guardian — Database Status

**Last updated:** April 13, 2026
**Author:** Computer, directed by Bobby Fiesler

Mining Guardian operates two completely separate databases for two completely different purposes. They never share data directly — Guardian may eventually query the catalog read-only over Tailscale, but the two systems are operationally independent.

---

## 1. guardian.db — Production Fleet Operations (SQLite)

### Location
- **Host:** Hostinger VPS (`187.124.247.182` / Tailscale `100.106.123.83`)
- **Engine:** SQLite with WAL mode
- **File:** `guardian.db` in the Mining Guardian working directory
- **Size:** ~1 GB max
- **Backup:** Rolling 12 copies + daily snapshots to Big-Bobby-T9 drive (Mac cron) + `knowledge_backup.json` to GitHub daily at 4am

### Schema — 16+ Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `scans` | Scan history | timestamp, online, offline, issues count |
| `miner_readings` | Per-miner per-scan data | 27 fields including hashrate, temp, status, power |
| `chain_readings` | Per-board data | rate, voltage, freq, consumption, HW errors, temp |
| `pool_readings` | Per-pool data | accepted/rejected shares, diff, status |
| `miner_state_readings` | Hashrate tiers, limits | minerStatus codes, device limits |
| `miner_ams_extended` | AMS metadata | timestamp, map coords, PDU counter, stratum URL |
| `miner_hardware` | Hardware identity | board serial, chip die/bin, PCB/BOM, PSU, ASIC count |
| `log_metrics` | Parsed miner.log data | per-chip hashrate, PSU voltage, chain events |
| `miner_logs` | Raw miner.log files | 30-day retention, 6hr collection, deduped |
| `action_audit_log` | Every action ever (permanent) | timestamp, miner, decision, approved_by, slack_user_id |
| `known_dead_boards` | Dead board registry | suppresses reflagging after ticket creation |
| `pending_approvals` | Actions awaiting response | 1 per miner max, 1hr auto-expire |
| `miner_restarts` | Restart history + outcomes | every restart with SUCCESS/FAILURE/PARTIAL label |
| `llm_analysis` | LLM responses | prompt, model_used, duration |
| `hvac_readings` | HVAC data | supply/return temps, pressure, pump status |
| `weather_readings` | Weather data | outside temp, humidity |
| `chip_readings` | Per-chip data (stub) | ready for direct-API per-chip data |
| `miner_baselines` | Hashrate learning | Tier 3 baseline state for unknown models |
| `facility_events` | HVAC correlator events | fleet-wide facility events |
| `s19jpro_overheat_tracking` | S19J Pro aging boards | Added April 13 2026, operator rule #6 |

Migrations are handled in `GuardianDB._init_db`. Atomic writes. WAL mode for concurrent reads.

### Status: LIVE
- Running 24/7 since April 4 2026
- 149+ scans during 48hr test (April 6-8)
- 12.1M+ data points ingested
- 58 miner fingerprints
- 22 SUCCESS / 24 FAILURE outcomes tracked

---

## 2. mining_guardian — Intelligence Catalog (PostgreSQL 16)

### Location
- **Host:** ROBS-PC (Windows 11, `192.168.188.47` / Tailscale `100.110.87.1`)
- **Engine:** PostgreSQL 16 in Docker
- **Container:** `mining-guardian-db`
- **Database:** `mining_guardian`
- **User:** `guardian_admin`
- **Port:** 5432
- **Backup:** `D:\MiningGuardian\db-backups\pre-migration\mining_guardian_2026-04-13.dump` (804 KB — first backup)

### Schema — 94 Tables, 2,363+ Columns, 10 Schemas

The schema was designed with a 10-year horizon. "Capture everything. Discard nothing."

Implemented across three SQL files, run in sequence:

| File | Lines | Content |
|------|-------|---------|
| `intelligence_catalog_schema.sql` | 4,431 | Base: 63 tables, 10 schemas, 16 enums, extensions, triggers |
| `intelligence_catalog_schema_v2_additions.sql` | 887 | V2: 9 new tables, 113 new columns — PSU serials, chip bins, board serials, fan specs, pinouts, known issues, reviews |
| `intelligence_catalog_schema_v3_additions.sql` | 1,256 | V3: 14+ new tables, 170+ columns — auto-discovery, container reference, immersion fluids, electricity, curtailment, depreciation, diagnostics, weather |

### Schemas

| Schema | Tables | Columns | Purpose |
|--------|--------|---------|---------|
| `knowledge` | 10 | 173 | Source tracking, citations, data conflicts, auto-discovery mechanism |
| `hardware` | 19 | 637 | Miner hardware — manufacturers, chips, PSUs, control boards, hashboards |
| `firmware` | 7 | 169 | Firmware releases, compatibility, API capabilities, known bugs |
| `ops` | 9 | 240 | Failure patterns, symptoms, probabilistic diagnosis, thresholds |
| `market` | 10 | 239 | User reviews, pricing, reputation, forum posts, teardowns |
| `repair` | 10 | 257 | Parts catalog, suppliers, repair procedures, diagnostic tools |
| `pool` | 7 | 152 | Pool directory, endpoints, stratum configs, reliability history |
| `facility` | 13 | 395 | Cooling solutions, HVAC patterns, container hydraulics, immersion fluids |
| `regulatory` | 5 | 101 | Legal frameworks, environmental regs, import/export rules |

### Auto-Discovery Mechanism (V3)

Bobby's hard requirement: "if a new data point comes up that it has never seen before, mark it down, register it as a new data point, not skip over it."

Four interconnected tables enforce this:
1. **`knowledge.field_registry`** — Master dictionary of all known fields (75 pre-seeded entries)
2. **`knowledge.unknown_fields`** — Captures any field not in the registry, with LLM auto-classification
3. **`knowledge.raw_ingestion_log`** — Complete raw payload of every API response (partitioned by quarter)
4. **`knowledge.field_discovery_log`** — Lifecycle audit trail for every discovered field

### Catalog ID Numbering

| Range | Manufacturer |
|-------|-------------|
| 1000s | Bitmain |
| 2000s | MicroBT |
| 3000s | Canaan |
| 4000s | Bitdeer |
| 5000s | Auradine |
| 6000s | Innosilicon |
| 7000s | Ebang |
| 8000s | StrongU |
| 9xxx | Historical/Other (KnCMiner, Spondoolies, Butterfly Labs, Bitfury, Halong) |

### Seed Data — DEPLOYED April 13, 2026

**313 distinct Bitcoin SHA-256 miner variants** seeded into `hardware.miner_models`.

| Manufacturer | Count | Era |
|-------------|-------|-----|
| Bitmain | 114 | 2013–2026 |
| MicroBT | 78 | 2017–2026 |
| Canaan | 64 | 2013–2026 |
| Bitdeer | 12 | 2025–2026 |
| Innosilicon | 11 | 2018–2021 |
| Ebang | 10 | 2018–2021 |
| StrongU | 9 | 2019–2021 |
| Auradine | 3 | 2024–2025 |
| KnCMiner | 3 | 2014–2015 |
| Spondoolies | 3 | 2015–2016 |
| Butterfly Labs | 3 | 2013–2014 |
| Bitfury | 2 | 2017–2018 |
| Halong Mining | 1 | 2018 |

### Schema Fixes Applied — April 13, 2026

`schema_fixes_v1.sql` — 19/20 checks PASS:
- Enum additions for manufacturer_brand (innosilicon, bitdeer, kncminer, spondoolies, butterfly_labs, halong)
- AH3880 chips_per_board fixed: NULL → 345
- AH3880 board_power_w_nom fixed: NULL → 2500.0
- Model aliases loaded: 16/27 (remaining ON CONFLICT from prior run, non-critical)
- primary_source_id NOT NULL constraint temporarily dropped for seeding

### Deep Research Enrichment Applied — April 13, 2026

`deep_research_enrichment.sql` (V2) — 211/223 matched:
- Uses `metadata` JSONB column (not deprecated `research_notes`)
- Uses `canonical_name` column (not deprecated `model_name`)
- Each UPDATE independent (no transaction wrapper)
- 12 UPDATE 0: Canaan "Gen" summary rows, combined entries, and 1 Scrypt miner correctly excluded

### Data Importer — DEPLOYED April 13, 2026

The Intelligence Catalog now has a complete data importer pipeline that ingests miner log files, spec sheets, and archives directly into the database. Located at `intelligence-catalog/importer/` — 22 files, 4,602+ lines of Python.

**Architecture:**
- Brand detection engine (`detector.py`) — identifies Bitmain, MicroBT, Canaan, Auradine via filename patterns, content signatures, and MAC/IP prefixes. Confidence scoring 0.0–1.0.
- Manufacturer-specific parsers (`parsers/`) — Bitmain, MicroBT, Canaan, Auradine, CSV, and generic fallback parsers
- Auto-discovery integration (`discovery.py`) — unknown fields are registered in `knowledge.unknown_fields`, never skipped
- Diagnostic test battery (`diagnostics/`) — universal tests + brand-specific tests run on every file
- PostgreSQL storage (`db.py`) — writes to 4 new import tables (see schema additions below)
- Archive handling — supports .zip, .tar.gz, .7z with recursive extraction; encrypted archives are gracefully skipped

**Schema additions** (`importer/schema_additions.sql`) — 4 new tables + 5 indexes:

| Table | Schema | Purpose |
|-------|--------|---------|
| `knowledge.import_jobs` | knowledge | Tracks every import job — start/end times, file counts, status |
| `knowledge.imported_files` | knowledge | Every file processed — hash, detected brand/model/firmware, parsed data JSONB |
| `ops.import_diagnostic_results` | ops | Diagnostic test results per file — pass/warn/fail with evidence |
| `ops.import_patterns` | ops | Cross-file patterns — model defects, firmware regressions, batch issues |

**Bug fixes deployed** (commit `bdca6e5`):
- T21 archive filenames with special characters (parentheses, spaces) no longer crash extraction
- Encrypted zip files are gracefully skipped instead of crashing the entire import
- MicroBT WhatsMiner logs no longer misidentified as Bitmain (confidence improved to 0.95)

**First live import results** (April 13, 2026):

| Metric | Count |
|--------|-------|
| Total files found | 1,796 |
| Files processed | 1,244 |
| Files skipped | 552 |
| Files failed | 0 |
| Flagged needs_review | 1,136 |

Miners detected in the import: S19 XP, S19 Pro+ Hyd, S19i, S19j+, S19j Pro, S19j Pro+, S19j XP, S19k Pro, T21, MicroBT M20S, M21S, M30S++. The importer also auto-discovered 62+ unique fields from WhatsMiner system logs that were not in the field registry.

Source archive: `C:\Users\user\Downloads\Telegram Desktop\logs (3).zip`

### Deployment Status: LIVE

| Component | Status | Details |
|-----------|--------|---------|
| Docker container | RUNNING | `mining-guardian-db` on ROBS-PC |
| Base schema (V1) | DEPLOYED | 63 tables, 10 schemas |
| Schema V2 additions | DEPLOYED | 9 new tables, 113 new columns |
| Schema V3 additions | DEPLOYED | 14+ new tables, 170+ columns, auto-discovery |
| Importer schema additions | DEPLOYED | 4 new tables, 5 indexes |
| Seed data (313 models) | DEPLOYED | All Bitcoin SHA-256 miners |
| Schema fixes | DEPLOYED | 19/20 PASS |
| Deep research enrichment | DEPLOYED | 211/223 matched |
| Data importer | DEPLOYED | 22 files, 4,602+ lines, first import complete |
| First backup | CREATED | 804 KB pg_dump, April 13 2026 |

### What's Next for the Intelligence Catalog

1. **Resolve 12 unmatched enrichment entries** — Fix naming mismatches for remaining models
2. **Deep research: PSU data** — Part numbers, efficiency curves, compatibility matrices
3. **Deep research: Hashboard details** — PCB versions, known defects, serial batch tracking
4. **Deep research: Control boards** — SoC specs, firmware compatibility
5. **Deep research: Chip data** — Die markings, process nodes, binning data
6. **Source table population** — Create entries in `knowledge.sources` for all research sources
7. **Schema V2/V3 table population** — Begin populating firmware, ops, repair, and market tables
8. **NAS migration (July 2026)** — Move from ROBS-PC to UGREEN NASync iDX6011 Pro

---

## Non-SHA-256 Models Identified and Excluded

During research, the following models were flagged as non-Bitcoin and excluded from the catalog:

| Model | Algorithm | Coin |
|-------|-----------|------|
| StrongU STU-U1 | Blake256R14 | Decred |
| StrongU STU-U1+ | Blake256R14 | Decred |
| StrongU STU-U1++ | Blake256R14 | Decred |
| StrongU STU-U2 | Blake256R14 | Decred |
| StrongU STU-U6 | Blake256R14 | Decred |
| SealMiner DL1 | Scrypt | LTC/DOGE |
| KnCMiner Titan | Scrypt | LTC |

Bobby's rule: "I will stress bitcoin only." These are tracked in documentation but will never enter the catalog.

---

*This document tracks the current state of both databases. Update it whenever schema changes are deployed, seed data is added, backup procedures change, or import operations complete.*
