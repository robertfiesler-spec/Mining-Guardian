# Mining Guardian Deployment Checklist - April 15, 2026

## 21 HIGH PRIORITY FIXES READY FOR DEPLOYMENT

### Pre-Deployment Steps

**1. Environment Variables - Add to .env:**
```bash
# Already present:
OLLAMA_URL=http://100.110.87.1:11434/api/generate

# Need to add:
DASHBOARD_URL=http://127.0.0.1:8585
AURADINE_USER=admin
AURADINE_PASS=admin
AUTHORIZED_SLACK_USER_IDS=U07AGTT8CLD
```

**2. Systemd Service Reload:**
```bash
systemctl daemon-reload
```

**3. Service Restarts (in order):**
```bash
systemctl restart mining-guardian
systemctl restart approval-api
systemctl restart dashboard-api
systemctl restart slack-listener
systemctl restart slack-commands
systemctl restart overnight-automation
systemctl restart mining-guardian-alerts
```

### Post-Deployment Verification

**1. Check Services Running:**
```bash
systemctl status mining-guardian approval-api dashboard-api slack-listener slack-commands overnight-automation
```

**2. Verify Environment Variables Loaded:**
```bash
# Check daemon log for OLLAMA_URL usage
journalctl -u mining-guardian -n 50 | grep -i ollama

# Check if knowledge context appears in LLM calls (DG-3 fix)
tail -f /root/Mining-Gaurdian/mining_guardian.log | grep -i "knowledge\|operator_rules"
```

**3. Test Log Rotation:**
```bash
# Wait until midnight, verify new log file created
ls -lh /root/Mining-Gaurdian/mining_guardian.log*
```

**4. Verify Bare Except Fixes:**
```bash
# Try Ctrl+C on a running process - should stop cleanly now
# Test that exceptions propagate properly
```

**5. Test Auradine Credentials:**
```bash
# Check if env vars used (no hardcoded admin/admin in logs)
journalctl -u mining-guardian | grep -i auradine
```

**6. Test Slack Command Authorization:**
```bash
# Try a command from unauthorized user - should be rejected
# Try from U07AGTT8CLD - should work
```

### Known Issues / Manual Fixes Needed

**CQ-6 to CQ-10:** 9 SQLite connections need manual context manager wrapping
- api/dashboard_api.py line 367
- api/approval_api.py line 88  
- api/ams_alert_listener.py lines 96, 122, 135, 150, 165
- api/slack_command_handler.py line 69

**CQ-14, CQ-15:** Token access methods need manual lock wrapping
- Wrap self._ws_token access with self._token_lock
- Wrap self._token_expiry access with self._token_lock

### Rollback Plan

If issues occur:
```bash
# Restore from backups
cd /root/Mining-Gaurdian
for f in *.backup_*; do
  orig="${f%.backup_*}"
  cp "$f" "$orig"
done

# Restart services
systemctl restart mining-guardian approval-api dashboard-api
```

### New Service: Intelligence Report API (April 15, 2026)

```bash
# 1. Pull latest code
cd /root/Mining-Gaurdian && git pull origin main

# 2. Install FastAPI
/root/Mining-Gaurdian/venv/bin/pip install fastapi uvicorn

# 3. Copy systemd service
cp /root/Mining-Gaurdian/deploy/intelligence-report.service /etc/systemd/system/

# 4. Reload, enable, start
systemctl daemon-reload
systemctl enable intelligence-report.service
systemctl start intelligence-report.service

# 5. Verify
curl http://localhost:8590/health
# Expected: {"status":"ok","models":226,"version":"2.1.0","btc_price":...,"correction_rules":3}
```

### Intelligence Report v2.1 Files (April 16, 2026)

The following files are required for the Intelligence Report API v2.1:

| File | Purpose |
|------|---------|
| `api/intelligence_report_api.py` | Main API — 1,352+ lines, 9 report sections, live BTC/network data, correction rules engine |
| `intelligence-catalog/data/correction_rules.json` | WhatsMiner cooling type corrections (3 rules, 44 model corrections) |
| `intelligence-catalog/data/unified_miner_index.json` | 226 merged miner models (slug-deduplicated) |
| `intelligence-catalog/data/miner_enrichment_master.csv` | 277 models with detailed specs |
| `deploy/intelligence-report.service` | systemd unit file |

Live data sources (fetched at runtime, cached 15 min):
- CoinGecko API — BTC price in USD
- mempool.space API — network difficulty + hashrate
- blockchain.info — fallback for difficulty/hashrate

### Success Criteria

✅ All 8 services running without errors (7 original + intelligence-report)
✅ Hourly scans complete successfully  
✅ LLM calls show knowledge context (DG-3)
✅ No connection leak warnings in logs
✅ Slack commands work with authorization
✅ Intelligence Report API returns 226 models + live BTC price on /health
✅ Grafana Intelligence Report dashboard renders HTML reports with 9 sections
✅ Correction rules applied — WhatsMiner cooling types corrected at startup

---

**Total fixes deployed:** 21 HIGH priority items + Intelligence Report feature (v1.0 → v2.0 → v2.1)
**Documentation:** REPAIR_LOG.md (complete history), INTELLIGENCE_REPORT_API.md (API docs)
**Last updated:** April 16, 2026
**Files modified:** 25+ production files
