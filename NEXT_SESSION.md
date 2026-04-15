# Next Session Priorities

**Last Updated:** April 15, 2026 (evening)
**Status:** Intelligence Report Dashboard LIVE, all operational dashboards working, documentation current

---

## ✅ COMPLETED — Intelligence Report Dashboard LIVE (April 15 evening)

The Intelligence Report dashboard is fully operational at:
https://grafana.fieslerfamily.com/d/intelligence_report_001/

- 235 miner models searchable via text input or quick-select buttons
- Full HTML reports render inline via iframe (dark theme matches Grafana)
- Sections: Hardware Specs, Model Variants, Firmware & Known Issues, Fleet Status, Sources
- Three deployment bugs found and fixed (see REPAIR_LOG.md April 15 evening entry)
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
