# Mining Intelligence Catalog Status

**Created:** April 13, 2026
**Last Updated:** April 15, 2026
**Phase 1 Target:** ROBS-PC (192.168.188.47) — LIVE
**Phase 2 Target:** UGREEN NAS (July 2026)

## Current Status: OPERATIONAL

PostgreSQL 16 is live on ROBS-PC with the full Intelligence Catalog:
- **165 tables** across 10 schemas (knowledge, hardware, firmware, ops, market, repair, pool, facility, regulatory, seed)
- **1,712+ columns**, **320+ indexes**, **115+ triggers**
- **235+ Bitcoin SHA-256 miner models** indexed
- **Auto-discovery system**: 4 tables ensure no data point is ever lost
- **Grafana datasource connected** — PostgreSQL on ROBS-PC:5432

## Intelligence Report API (Built April 15, 2026)

A REST API serving searchable miner intelligence reports to Grafana:
- **Port:** 8590 (systemd service: `intelligence-report.service`)
- **File:** `api/intelligence_report_api.py`
- **Data sources:** `unified_miner_index.json` (235 models) + `miner_enrichment_master.csv` (277 models) + `miner_specs.json` (46 models) + `guardian.db` (fleet data)
- **Grafana dashboard:** `intelligence_report_001` — searchable text input + dropdown, HTML report rendering
- **Status:** Built and tested. Awaiting VPS deployment (Bobby runs the commands).

See `docs/INTELLIGENCE_REPORT_API.md` for full endpoint documentation.

## Data Pipeline

1. **Catalog research** completed — all major SHA-256 manufacturers covered (Bitmain, MicroBT, Canaan, Bitdeer, Auradine, Innosilicon, Ebang, StrongU)
2. **Enrichment master CSV** — 277 models with detailed specs, efficiency, firmware, cooling, known issues
3. **Unified miner index** — 235 models merged from all sources with slug-based lookup
4. **Fleet integration** — models deployed in Bobby's fleet get live operational data from guardian.db

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

- [ ] Deploy Intelligence Report API on VPS (port 8590)
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

See `intelligence/README.md` for full architecture documentation.
