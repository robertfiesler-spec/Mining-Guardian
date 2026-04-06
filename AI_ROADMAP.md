# Mining Guardian — AI Learning Roadmap
## Path to 80% Autonomous Operation

**Branch:** `main`
**Status:** 48-HOUR TEST IN PROGRESS (started April 6, 2026)
**Next milestone:** Wednesday April 8 customer demo
**Rule:** Before building anything, examine every available data point. No unused signals.

---

## Current Mode
**FULL-DAY AUTONOMOUS** — Active 24/7
Overnight automation runs 8pm-6am. LOW-risk actions execute without approval.
Max auto-restarts: 2 per window. All 8 services active on VPS.

---

## 48-Hour Test Status (Live — April 6)

| Metric | Value |
|---|---|
| Scans completed | 149+ |
| Data points ingested | 12.1M+ |
| Miner readings | 53,110 |
| Chain readings | 45,180 |
| Log metrics | 12M+ |
| Miner fingerprints | 58 |
| Outcomes tracked | 22 SUCCESS, 24 FAILURE, 1 PENDING |
| Denial reasons captured | 11 |
| Autonomous actions | 25 |
| Known issues | 50 |
| Patterns discovered | 7 |
| AI Score | 40.2K+ (climbing) |

### Denial Reasons Captured (Operator Knowledge)
- "always wait 20 minutes after a power cycle to make changes"
- "miners just restarted, need to wait 20 minutes after restart to download logs then make recommendations"
- "waiting the 20 minutes still"

**Status:** Stored in audit log. Will be fed to Claude Sonnet at next weekly training (Sunday 3am). Not yet reflected in knowledge.json.

---

## Fixes Deployed During 48hr Test (April 6)

### Operational Fixes
- [x] **20-minute post-restart grace period** — Miners suppressed from action recommendations for 20 min after restart (both MG-tracked and manual AMS restarts via uptime check)
- [x] **Hashrate % fix** — Now uses BiXBiT profile parser instead of AMS stock maxHashrate. Fixed 201% → 101%
- [x] **POWER_PROFILE_UP spam fix** — Only fires as recovery after MG steps a miner DOWN. Not for every miner below theoretical max
- [x] **AMS alerts suppressed from Slack** — Still stored in DB for learning, removed from Slack messages (operator request)
- [x] **Deny flow complete** — DENY → "Why?" follow-up → reason captured and stored. Clean two-step workflow
- [x] **Crystal ball single post** — Each recommendation posts once (was duplicating)
- [x] **Pending approvals whitelist** — Added POWER_PROFILE_UP, PREEMPTIVE_RESTART, ECO_MODE, MONITOR_CLOSE to save_pending_approvals
- [x] **Ticket 30-min grace period** — Don't ticket miners restarted < 30 min ago

### Dashboard Fixes
- [x] **Grafana Board Health dropdown** — Fixed metric name (mhs → ths) so miner IP dropdown populates
- [x] **Grafana Pool Stats redesigned** — Hero tiles, rejection rate chart, problem miners table
- [x] **Grafana Main rejection chart** — Replaced per-miner spaghetti with fleet avg + worst miner
- [x] **AI Intelligence Center** — Complete rebuild with live action queue, approve/deny buttons, AI score

### Code Quality (from code review)
- [x] Dead code removed (orphaned method bodies)
- [x] api/slack_listener.py deleted (violated Socket Mode rule)
- [x] Auth bypass in approval_api.py — now fails closed
- [x] Atomic writes in outcome_checker.py
- [ ] DB leaks (bare _connect().execute()) — 3 locations need context managers
- [ ] NameErrors in predictor loop (line 4619) and _escalate_board_issue (line 4040)
- [ ] File handle leak in overnight_automation.py

---

## Feature Build Status

### Feature 1: Outcome Feedback Loop ✅ COMPLETE + LIVE
**File:** `ai/outcome_checker.py`
**Live results:** 22 SUCCESS, 24 FAILURE outcomes tracked and labeled

### Feature 2: Confidence Scoring ✅ COMPLETE + LIVE
**File:** `ai/confidence_scorer.py`
**Live results:** Confidence shown in Slack, gates auto/manual decisions

### Feature 3: Denial Reason Capture ✅ COMPLETE + LIVE
**File:** `api/slack_approval_listener.py`
**Live results:** 11 denial reasons captured from operator
**Gap:** weekly_train.py does NOT read denial reasons yet — only train_comprehensive.py does

### Feature 4: Miner Fingerprinting v2 ✅ COMPLETE + LIVE
**File:** `ai/fingerprint_builder.py`
**Live results:** 58 miner profiles with behavioral fingerprints

### Feature 5: HVAC/Environment Correlation ✅ COMPLETE + LIVE
**File:** `ai/hvac_correlator.py`
**Live results:** 0% facility stress — confirms miner issues are hardware, not environmental

### Feature 6: Pre-Failure Prediction v2 ✅ COMPLETE + LIVE
**File:** `ai/predictor.py`
**Live results:** 23 miners showing pre-failure signals per scan. Predictions currently paused (not posting to Slack)

### Feature 7: Repair Shop Data Ingestion ⏳ PENDING
**Blocked on:** Dataset from contact (James/ACS)

### Feature 8: Action Diversity ✅ COMPLETE + FIXED
**File:** `ai/action_diversity.py`
**Fix applied:** POWER_PROFILE_UP now only fires as recovery action, not constant optimization

---

## Critical Gap: OpenClaw Underutilization

### Current State (Honest Assessment)
OpenClaw is running (Docker, up 4 days) but contributes **zero actions** to the audit log. It owns the Slack Socket Mode connection and posts the morning briefing. That's it.

All intelligence currently lives in Python rules (predictor.py, action_diversity.py, hashrate_evaluation.py) and the Claude Sonnet weekly training. OpenClaw's local LLM is not being used for real-time analysis.

### What OpenClaw Should Be Doing
1. **Real-time scan analysis** — Every scan sends data to local LLM via OpenClaw webhook. LLM writes natural language assessment instead of rules-based flags
2. **Denial reason interpretation** — When operator denies with reason, LLM immediately processes it into an operational rule (not waiting for Sunday training)
3. **Conversational interface** — Operator asks "Why did .35 restart 3 times?" and gets an intelligent answer from fleet data
4. **Pre-action analysis** — Before recommending restart, LLM reviews miner's full history (logs, outcomes, fingerprint) and provides nuanced recommendation
5. **Rich Slack interactions** — Proper Block Kit buttons/forms instead of text-based APPROVE/DENY (OpenClaw owns Socket Mode, so it can handle interactive components)

### Path Forward
- [ ] Route scan data to OpenClaw webhook (already coded, verify working)
- [ ] Build OpenClaw prompt templates for scan analysis
- [ ] Implement real-time denial reason processing via LLM
- [ ] Add conversational query handler ("ask about miner X")
- [ ] Restore Block Kit interactive components through OpenClaw
- [ ] This is a priority for the Mac Mini local deployment

---

## Remaining Roadmap

### Before Wednesday Demo (April 8)
- [ ] Verify AI score visibly climbs in Grafana over 48hr period
- [ ] Document test results for demo narrative
- [ ] Clean up crystal ball message text

### Before Mac Mini Deployment (May 5-9)
- [ ] OpenClaw integration — real-time LLM analysis per scan
- [ ] weekly_train.py — add denial reason ingestion
- [ ] Installer wizard for local Mac Mini deployment
- [ ] macOS launchd services instead of systemd
- [ ] Local web dashboard approve/deny (reduce Slack dependency)
- [ ] Update mechanism that preserves config + DB
- [ ] Operator guide documentation

### Long-Term (Post-Deployment)
- [ ] Repair shop data ingestion (Feature 7)
- [ ] Container monitoring (when live access granted)
- [ ] Multi-site federated knowledge with monthly USB sync
- [ ] Replace Slack with fully local notification system
- [ ] 80% autonomous operation target with operator override

---

## Technical Notes
- HVAC/BAS integration is one-off for Bobby's warehouse — not in deployment templates
- S19JPro dead board repairs explicitly crossed off — do not raise
- Pool failover requires backup_pool_url in config.json — not currently set
- AH3880 board voltage 0.29V is Auradine firmware format (not a fault)
- Feature 7 blocked pending repair shop dataset from James/ACS
- OpenClaw morning briefing runs via Docker Socket Mode. Mining Guardian uses polling for approve/deny to avoid Socket Mode conflict
- All denial reasons will be processed in next weekly training (Sunday 3am)

---

*Last updated: April 6, 2026*
*48hr test in progress — 12M+ data points, 149 scans, 11 operator denial reasons captured*
