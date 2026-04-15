# Next Session Priorities

**Last Updated:** April 15, 2026 (evening)
**Status:** Intelligence Report Dashboard LIVE, all operational dashboards working, documentation current

---

## IMMEDIATE — Deploy Intelligence Report v2.0 on VPS (2 commands)

The Intelligence Report API has been upgraded from v1.0 (3 sections) to v2.0 (full 9-section report).

**Bobby needs to run:**

```bash
cd /root/Mining-Gaurdian && git pull origin main
```

```bash
systemctl restart intelligence-report && systemctl restart dashboard-api
```

Then refresh the Grafana Intelligence Report dashboard and search any miner.

**What's new in v2.0:**
- Slug merge: 9 duplicate model pairs consolidated (226 unique models, was 235 with dupes)
- Section 4: Profitability & Economics (BTC mining calculator, 5 electricity rate tiers, breakeven)
- Section 5: Market Context (generation classification, competitor comparison)
- Section 6: Repair & Maintenance (failure patterns by manufacturer, maintenance schedule)
- Section 7: Cooling & Environment (BTU output, CFM requirements, best practices)
- Section 8: AI Analysis (catalog-based insights with confidence scores)
- Section 9: Recommendations (buy/hold/sell, fleet actions, pre-deployment checklist)
- Full visual redesign: stat cards, progress bars, severity badges, table of contents

---

## ✅ COMPLETED — Intelligence Report v1.0 Dashboard LIVE (April 15 evening)

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
