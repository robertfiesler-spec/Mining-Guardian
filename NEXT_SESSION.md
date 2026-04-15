# Next Session Priorities

**Last Updated:** April 15, 2026 (evening)
**Status:** Intelligence Report API RUNNING on VPS (235 models), iframe render endpoint pushed, dashboard-api restart needed

---

## IMMEDIATE — Activate iframe rendering on VPS (2 commands)

The Intelligence Report API is live on the VPS (port 8590, 235 models confirmed). Three bugs were found and fixed during deployment (see REPAIR_LOG.md April 15 evening entry). The final fix — iframe-based rendering for Grafana — has been pushed to GitHub but the VPS dashboard-api service needs a restart to pick it up.

**Bobby needs to run these 2 commands on the VPS:**

```bash
cd /root/Mining-Gaurdian && git pull origin main
```

```bash
systemctl restart dashboard-api
```

Then refresh the Grafana Intelligence Report dashboard at:
https://grafana.fieslerfamily.com/d/intelligence_report_001/

Type a miner model (e.g. `antminer-s19jpro`) in the search variable and the report should render inside an iframe.

**Why iframe instead of Business Text plugin:**
- Grafana's built-in text panel strips `<script>` tags (security)
- Business Text plugin v6.2.0 was installed but requires Grafana 11+ (VPS runs 10.4.1)
- The iframe approach works on any Grafana version — `dashboard_api.py` serves full HTML pages at `/api/report/{slug}/html/render` through the Cloudflare tunnel

**Verification after restart:**
```bash
curl http://localhost:8585/api/report/antminer-s19jpro/html/render
```
Should return a full HTML page with dark theme containing the S19J Pro intelligence report.

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
