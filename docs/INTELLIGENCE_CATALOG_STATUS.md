# Mining Intelligence Catalog Status

**Created:** April 13, 2026
**Last Updated:** April 16, 2026
**Phase 1 Target:** ROBS-PC (192.168.188.47) — LIVE
**Phase 2 Target:** UGREEN NAS (July 2026)

## Current Status: OPERATIONAL

PostgreSQL 16 is live on ROBS-PC with the full Intelligence Catalog:
- **165 tables** across 10 schemas (knowledge, hardware, firmware, ops, market, repair, pool, facility, regulatory, seed)
- **1,712+ columns**, **320+ indexes**, **115+ triggers**
- **226 Bitcoin SHA-256 miner models** indexed (slug-deduplicated from 235 raw entries)
- **Auto-discovery system**: 4 tables ensure no data point is ever lost
- **Grafana datasource connected** — PostgreSQL on ROBS-PC:5432

## Intelligence Report API — v2.1.0 (Live on VPS)

A REST API serving searchable miner intelligence reports to Grafana. Major rewrite from v1.0 (542 lines) to v2.0 (1,352+ lines) to v2.1 (live data + correction rules).

- **Port:** 8590 (systemd service: `intelligence-report.service`)
- **File:** `api/intelligence_report_api.py` — 1,352+ lines
- **Version:** 2.1.0 (deployed April 16, 2026)
- **Data sources:** `unified_miner_index.json` (226 models after slug merge) + `miner_enrichment_master.csv` (277 models) + `miner_specs.json` (46 models) + `guardian.db` (fleet data)
- **Live data:** CoinGecko (BTC price), mempool.space (difficulty/hashrate), blockchain.info (fallback) — 15-min cache with thread-safe double-check locking
- **Correction rules engine:** `intelligence-catalog/data/correction_rules.json` — pattern-matching rules applied at startup to fix known data issues (regex, contains, endswith matching)
- **9 report sections:** Header/Overview, Key Specifications, Variants & Revisions, Known Issues & Failure Patterns, Firmware & Software, Repair & Maintenance, Profitability Analysis (live BTC), Cooling & Environment, Fleet Intelligence
- **Grafana dashboard:** `intelligence_report_001` — searchable text input + dropdown, full HTML report rendering
- **Status:** DEPLOYED and RUNNING on VPS

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
4. **Fleet integration** — models deployed in Bobby's fleet get live operational data from guardian.db
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

- [x] Deploy Intelligence Report API on VPS (port 8590) — DONE (v2.1.0, April 16)
- [x] Live BTC price + network difficulty in profitability section — DONE (v2.1.0)
- [x] Correction rules engine for known data issues — DONE (v2.1.0)
- [ ] Weekend database knowledge review — Bobby will review and correct model data during flights
- [ ] Add Qwen AI analysis paragraphs to reports (requires Qwen reachable from API)
- [ ] Add PDF download button to Grafana dashboard
- [ ] Auto-import pipeline — catalog searches internet for updates daily
- [ ] Repair shop data ingestion (Feature 7, blocked on James/ACS dataset)
- [ ] NAS migration (July 2026) — `pg_dump` → file copy → `pg_restore`, ~20 min for 60 GB

## Architecture Vision

The Intelligence Catalog is a living, learning system:
- ROBS-PC = MASTER golden copy
- Customer Mac minis get READ copies updated monthly
- All customers get full catalog access (all miner models, not just their fleet)
- 1 Mac mini per 1-2 containers, max ~500 miners
- NAS migration July 2026, cloud backup on top

See `intelligence-catalog/seed-data/README.md` for full architecture documentation. The legacy `intelligence/` directory is deprecated as of 2026-04-27 — see `intelligence/DEPRECATED.md` and `docs/CATALOG_ORPHAN_TABLES_2026-04-28.md`.
