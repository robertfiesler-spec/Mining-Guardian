# Intelligence Report API

## Overview
The Intelligence Report API serves searchable miner intelligence reports for any Bitcoin SHA-256 miner model in the catalog. It combines data from the Intelligence Catalog (PostgreSQL), enrichment research (CSV), miner specs (JSON), and fleet operational data (guardian.db) to generate comprehensive reports.

## Service Details
- **Port**: 8590
- **Service file**: `deploy/intelligence-report.service`
- **API script**: `api/intelligence_report_api.py`
- **Data files**: `intelligence-catalog/data/`

## Endpoints

### Health Check
```
GET /health
→ {"status": "ok", "models": 235, "version": "1.0.0"}
```

### List All Models
```
GET /api/report/models
→ [{"slug": "antminer-s21", "display_name": "Antminer S21", "manufacturer": "Bitmain", "hashrate": "200 TH/s", "label": "Bitmain Antminer S21 (200 TH/s)"}, ...]
```

### Search Models
```
GET /api/report/search?q=m63
→ [{"slug": "whatsminer-m63s-plus", "label": "Microbt WhatsMiner M63S+ (450 TH/s)", ...}, ...]
```

### Get Full Report (JSON)
```
GET /api/report/{slug}
→ {
    "generated_at": "April 15, 2026 ...",
    "display_name": "WhatsMiner M63S+",
    "manufacturer": "Microbt",
    "report_type": "Pre-Deployment Analysis (Catalog Only)",
    "fleet_deployed": false,
    "hardware": { ... },
    "fleet": { ... },
    "data_sources": { ... }
  }
```

### Get Report as HTML (for Grafana)
```
GET /api/report/{slug}/html
→ {"html": "<div>...rendered report...</div>"}
```

## Data Sources (Priority Order)
1. **miner_specs.json** — 46 models with variants and rated specs (used by AMS/scan system)
2. **unified_miner_index.json** — 235 models merged from all sources
3. **miner_enrichment_master.csv** — 277 models with detailed research data
4. **guardian.db** — Live fleet data (only for deployed models)
5. **Intelligence Catalog** (PostgreSQL) — Future: direct queries when API available

## Grafana Dashboard
- **UID**: `intelligence_report_001`
- **URL**: `/d/intelligence_report_001/`
- Uses a text variable `$miner_model` for search
- Business Text panel renders HTML reports via JavaScript fetch to localhost:8590
- Time series panels show fleet data for deployed models

## Model Slug Format
Slugs are lowercase, hyphenated: `antminer-s21`, `whatsminer-m63s-plus`, `teraflux-ah3880`

## Adding New Models
1. Add to `intelligence-catalog/data/miner_enrichment_master.csv`
2. Add to `miner_specs.json` (if operational in fleet)
3. Rebuild unified index: run the index builder script
4. Restart the intelligence-report service

## Created
- Date: April 15, 2026
- Author: Computer (Perplexity)
- Requested by: Bobby Fiesler
