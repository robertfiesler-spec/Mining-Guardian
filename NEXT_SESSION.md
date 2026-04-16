# Next Session Priorities

**Last Updated:** April 16, 2026 (morning)
**Status:** Intelligence Report v2.1 LIVE on VPS, live BTC data, correction rules engine active, all dashboards working

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

## ✅ COMPLETED — Intelligence Report v2.1 LIVE (April 16 morning)

- v2.1.0 deployed on VPS: 226 models, live BTC data, 3 correction rules
- Live BTC price from CoinGecko + network difficulty from mempool.space (15-min cache)
- Correction rules engine: JSON pattern matching, Bobby adds rules without code changes
- WhatsMiner cooling auto-classification: M_0=air, M_3=hydro, M_6=immersion (44 corrections)
- Health check: `{"status":"ok","version":"2.1.0","models":226,"correction_rules":3,"btc_price":74719}`

## ✅ COMPLETED — Intelligence Report v2.0 (April 15 late evening)

- Full 9-section report: Hardware, Firmware, Fleet, Profitability, Market, Repair, Cooling, AI Analysis, Recommendations
- Slug merge: 9 duplicate model pairs consolidated
- Visual redesign: stat cards, progress bars, severity badges, table of contents

## ✅ COMPLETED — Intelligence Report v1.0 Dashboard (April 15 evening)

- Three deployment bugs found and fixed (REPO_DIR, mixed content, script stripping)
- Iframe approach working on Grafana 10.4.1
- All 4 verification items confirmed ✅

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
- [ ] Qwen AI analysis paragraphs in reports (requires Qwen reachable from API)
- [ ] PDF download button in Grafana
- [ ] Auto-enrichment: catalog searches internet for updates daily

---

## MEDIUM PRIORITY (~80 items from code review)
- Magic numbers → constants
- Duplicated code blocks
- Missing docstrings
- TODO comments

---

## KEY FILES CHANGED TODAY (April 15, 2026)

### New Files
- `api/intelligence_report_api.py` — Intelligence Report API (port 8590)
- `deploy/intelligence-report.service` — systemd service file
- `docs/INTELLIGENCE_REPORT_API.md` — API documentation
- `intelligence-catalog/data/unified_miner_index.json` — 235 models merged index

### Updated Files
- `README.md` — architecture, services, dashboards, key files tables
- `AI_ROADMAP.md` — milestones, Grafana section, completed items, last updated
- `docs/INTELLIGENCE_CATALOG_STATUS.md` — full rewrite reflecting live status
- All 6 Grafana operational dashboards — duplicate panels removed, queries fixed

### Git Commits
- `8e05461` — feat: Intelligence Report API (searchable miner reports for 235+ models)
- `fad1096` — docs: update README architecture + AI_ROADMAP with Intelligence Report API status
- (pending) — docs: comprehensive documentation audit pass

---

**Current Status: PRODUCTION READY + INTELLIGENCE REPORT READY FOR DEPLOYMENT**
