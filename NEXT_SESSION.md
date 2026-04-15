# Next Session Priorities

**Last Updated:** April 15, 2026
**Status:** Intelligence Report API built, all dashboards fixed, documentation updated

---

## IMMEDIATE — Deploy Intelligence Report API on VPS

Bobby has the step-by-step deployment commands (10 steps). Once he runs them:
1. `git pull origin main` on VPS
2. `pip install fastapi uvicorn`
3. Copy systemd service, enable, start
4. Verify: `curl http://localhost:8590/health` → 235 models
5. Open Grafana dashboard at `/d/intelligence_report_001/` and search a miner

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
