# Mining Intelligence Catalog Status

> ## ⚠️ Status as of 2026-05-07 (P-021)
>
> **Two-DB cooperative architecture (locked).** The Mac Mini runs ONE Postgres 16 container (`mining-guardian-db`, port 5432, role `mg`) hosting TWO distinct logical databases that cooperate as one system. They are NOT collapsed into a single schema:
>
> | DB | Role | Used by |
> |---|---|---|
> | `mining_guardian` (operational) | Scan/audit/AI tables, fleet state, Slack-approval state, `mg.*` schemas | Scanner (`core/mining_guardian.py`), approval API, dashboard API, console |
> | `mining_guardian_catalog` (intelligence catalog) | `hardware.*`, `firmware.*`, `ops.*`, `repair.*`, `staging.*` reference tables | Catalog API, `ai/catalog_context.py` reader on every scan, `catalog_updater.py --add-from-csv` writer (daily) |
>
> **Daily update flow (P-021 NEW):**
> 1. The 5 Perplexity-driven scheduled tasks (Aggregator Watcher, Manufacturer Model Watcher, Firmware Tracker, Community Intel Scanner, Deep Enrichment Sweep) write JSON/CSV to `${INSTALL_ROOT}/cron_tracking/<watcher>/`. They do NOT write directly to either DB.
> 2. `com.miningguardian.scheduled.catalog-import` plist runs daily at 04:30 CDT. It dispatches `intelligence-catalog/tools/run_daily_catalog_import.sh` via `scheduled_job_launcher.sh`. The wrapper picks the most recent `.csv` in `cron_tracking/enrichment_sweep/` and calls `catalog_updater.py --add-from-csv <csv>`. The other four watchers' DB writers remain future-PR scope (see `docs/INTEL_CATALOG_FULL_BRIEF_2026-05-02.md` §351-354).
> 3. Operator-controlled escalation: rows in `staging.miner_model_proposals` are promoted to `hardware.miner_models` by an operator review (manual `catalog_updater.py --add-model` or future console action), keeping the operator in the loop per Vision Anchor 1.
>
> **Identifiers / aliases (P-021):**
> - `hardware.model_aliases` (catalog DB) — Tier-1, exact slug ↔ canonical name.
> - **P-021 supplement:** `003_live_short_name_aliases.sql` adds AMS short names (`S19JPro`, `S21EXPHyd`, `S21Imm`, `AH3880`) at apply time, resolving `miner_model_id` against the live catalog seed (no frozen UUIDs, no FK drift).
> - `mg.model_family_aliases` (operational DB) — Tier-2, family ↔ hashrate. Production resolver path for the BiXBiT fleet's 9 model families.
>
> **API surface (P-021 schema fix):** `/api/v1/knowledge/miner/{slug}` and `ai/catalog_context.py` now use schema-correct FKs everywhere. Pre-P-021 these queried `WHERE model_id = …` against tables whose actual FK is `miner_model_id` / `primary_model_id` / `affected_model_id` — the scanner crashed on every catalog read with `column "model_id" does not exist` (B-30). PSU lookup JOINs `hardware.psu_compatibility` (M2M); firmware-versions JOIN `firmware.firmware_compatibility(firmware_id, miner_model_id)`.
>
> **Earlier banner (now superseded):** the prior 2026-04-29 banner stated catalog `db=mining_guardian, user=guardian_app` — that was always wrong; catalog DB has been `mining_guardian_catalog` since the postinstall config froze, and runtime user has been `mg` since P-020 fixed the `guardian_app` defaults.
>
> The body below is preserved as a historical status snapshot from April 16, 2026.

**Created:** April 13, 2026
**Last Updated:** April 16, 2026 (body); banner updated 2026-04-29 PM
**Phase 1 Target (historical):** ROBS-PC (192.168.188.47) — superseded by Mac Mini
**Phase 2 Target:** Mac Mini (2026-04-30, locked) — then UGREEN NAS (July 2026)

## Current Status (historical — as of April 16, 2026): OPERATIONAL on ROBS-PC

PostgreSQL 16 was live on ROBS-PC with the full Intelligence Catalog:
- **165 tables** across 10 schemas (knowledge, hardware, firmware, ops, market, repair, pool, facility, regulatory, seed)
- **1,712+ columns**, **320+ indexes**, **115+ triggers**
- **226 Bitcoin SHA-256 miner models** indexed (slug-deduplicated from 235 raw entries)
- **Auto-discovery system**: 4 tables ensure no data point is ever lost
- **Grafana datasource connected** — PostgreSQL on ROBS-PC:5432 (historical; now Mac Mini)

## Intelligence Report API — v2.1.0 (historical — was on VPS, now decommissioned for MG)

A REST API serving searchable miner intelligence reports to Grafana. Major rewrite from v1.0 (542 lines) to v2.0 (1,352+ lines) to v2.1 (live data + correction rules).

- **Port:** 8590 (systemd service: `intelligence-report.service`)
- **File:** `api/intelligence_report_api.py` — 1,352+ lines
- **Version:** 2.1.0 (deployed April 16, 2026)
- **Data sources:** `unified_miner_index.json` (226 models after slug merge) + `miner_enrichment_master.csv` (277 models) + `miner_specs.json` (46 models) + `guardian.db` (fleet data)
- **Live data:** CoinGecko (BTC price), mempool.space (difficulty/hashrate), blockchain.info (fallback) — 15-min cache with thread-safe double-check locking
- **Correction rules engine:** `intelligence-catalog/data/correction_rules.json` — pattern-matching rules applied at startup to fix known data issues (regex, contains, endswith matching)
- **9 report sections:** Header/Overview, Key Specifications, Variants & Revisions, Known Issues & Failure Patterns, Firmware & Software, Repair & Maintenance, Profitability Analysis (live BTC), Cooling & Environment, Fleet Intelligence
- **Grafana dashboard:** `intelligence_report_001` — searchable text input + dropdown, full HTML report rendering
- **Status:** DEPLOYED and RUNNING on VPS (historical — VPS decommissioned for MG as of 2026-04-30 Mac Mini install)

### Correction Rules (v2.1)

The correction rules engine fixes known data quality issues without touching source data files:
- **WhatsMiner cooling convention:** last digit of base model number determines cooling type (0=air, 3=hydro, 6=immersion)
- **3 rules active:** M*0 → Air-Cooled, M*3 → Hydro, M*6 → Immersion
- **44 model corrections** applied at startup
- **Models needing Bobby's review:** M21, M32, M61, M64, M65, M72, M78, M79, M7d (don't match 0/3/6 pattern)

See `docs/INTELLIGENCE_REPORT_API.md` for full endpoint documentation.

## Data Pipeline

1. **Catalog research** completed — all major SHA-256 manufacturers covered (Bitmain, MicroBT, Canaan, Bitdeer, Auradine, Innosilicon, Ebang, StrongU)
2. **Enrichment master CSV** — 277 models with detailed specs, efficiency, firmware, cooling, known issues
3. **Unified miner index** — 226 models (slug-deduplicated from 235 raw entries, 9 duplicates merged)
4. **Fleet integration** — models deployed in Bobby's fleet were joined with operational data from `guardian.db` during the VPS era (historical SQLite snapshot — not live). Post-2026-04-30 the join is against PostgreSQL `mining_guardian` on the Mac Mini.
5. **Live network data** — BTC price, network difficulty, global hashrate fetched from CoinGecko + mempool.space (15-min cache)
6. **Correction rules engine** — `correction_rules.json` applies pattern-matched fixes at startup (WhatsMiner cooling types, etc.)

## Catalog ID Numbering
- 1000s = Bitmain
- 2000s = MicroBT
- 3000s = Canaan
- 4000s = Bitdeer
- 5000s = Auradine
- 6000s = Innosilicon
- 7000s = Ebang
- 8000s = StrongU
- 9xxx = Historical/Other

## Next Steps

- [x] Deploy Intelligence Report API on VPS (port 8590) — DONE (v2.1.0, April 16) (historical — VPS decommissioned for MG)
- [x] Live BTC price + network difficulty in profitability section — DONE (v2.1.0)
- [x] Correction rules engine for known data issues — DONE (v2.1.0)
- [ ] Weekend database knowledge review — Bobby will review and correct model data during flights
- [ ] Add Qwen AI analysis paragraphs to reports (requires Qwen reachable from API)
- [ ] Add PDF download button to Grafana dashboard
- [ ] Auto-import pipeline — catalog searches internet for updates daily
- [ ] Repair shop data ingestion (Feature 7, blocked on James/ACS dataset)
- [ ] NAS migration (July 2026) — `pg_dump` → file copy → `pg_restore`, ~20 min for 60 GB

## Architecture Vision

> **2026-04-29 PM update:** The vision below was written for the ROBS-PC-as-master era. The current locked architecture has the catalog on the Mac Mini (not ROBS-PC as master). The Mac Mini is not a "READ copy" — it IS the operational DB. Future multi-site architecture (multiple Mac Minis, NAS backup) is on the roadmap.

The Intelligence Catalog is a living, learning system:
- **Mac Mini** = operational DB host (2026-04-30 install, port 5432, user `guardian_app`, db `mining_guardian`)
- Customer Mac Minis get full catalog access (all miner models, not just their fleet)
- 1 Mac Mini per 1-2 containers, max ~500 miners
- NAS migration July 2026, cloud backup on top

*(Historical note: ROBS-PC was the Phase 1 master — that architecture was evaluated and superseded by Mac Mini.)*

See `intelligence-catalog/seed-data/README.md` for full architecture documentation. The legacy `intelligence/` directory is deprecated as of 2026-04-27 — see `intelligence/DEPRECATED.md` and `docs/CATALOG_ORPHAN_TABLES_2026-04-28.md`.
