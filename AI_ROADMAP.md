# Mining Guardian — AI Learning Roadmap

## Path to Autonomous Operation at Customer Sites

**Branch:** `main`
**Status:** Post 48-hr test — approaching Mac mini migration (May 5–9 2026)
**Current phase:** Post-code-review hardening complete (all CRITICAL + HIGH resolved) — OpenClaw conversational wiring + installer prep
**Rule:** Before building anything, examine every available data point. No unused signals. No proposing alternatives to plans already in the docs.

> 📘 This document is the forward-looking status tracker. For the canonical product vision read `docs/VISION.md` first, then `README.md`. For binding rules read `CLAUDE.md`.

---

## Current Mode
**FULL-DAY AUTONOMOUS** — Active 24/7
Overnight automation runs 8pm–6am. LOW-risk actions execute without approval. Max auto-restarts: 2 per window. Miners with 3+ FAILURE outcomes are permanently blocked from overnight auto-restart until human review. All VPS services active.

**Scan cadence:** 1 scan per hour (`scan_interval_seconds: 3600`, `slack_interval_seconds: 3600`). Matches Slack post throttle — one 🧠 AI analysis post to `#mg-ai-reports` per scan. Confirmed April 9 2026 after diagnostic sweep. Faster cadence (hourly) was the early dev value and is not used in production.

---

## 48-Hour Test Results (April 6–8 2026)

| Metric | Final |
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
| AI Score | 40.2K+ |

### Denial Reasons Captured (Operator Knowledge)
- "always wait 20 minutes after a power cycle to make changes"
---

## Recent Feature Completions (2026-04-15)

### Intelligence Catalog Integration + Miner Intelligence Report Generator ✅ COMPLETED

**Status:** DEMO READY — dual-database architecture operational, example reports generated

**What Was Built:**
Dual-database report generator synthesizing operational fleet data (guardian.db SQLite) with industry-wide intelligence (PostgreSQL catalog with 165 tables tracking 300+ miner deployments).

**Architecture:**
- **Database 1:** Intelligence Catalog (PostgreSQL on ROBS-PC) — 165 tables, 1,712+ columns, 320+ indexes, 115+ triggers
- **Database 2:** guardian.db (SQLite on VPS) — 5.8 GB operational data
- **10 Schemas:** knowledge, hardware, firmware, ops, market, repair, pool, facility, regulatory, seed
- **Auto-discovery system:** 4 tables ensure no data point is ever lost
- **Target capacity:** 1M+ repair records from BiXBiT service network

**Example Reports Created:**

1. **S19J Pro Operational Intelligence** (miner IN fleet — 18 deployed)
   - Document: 1,066 lines, 42 KB markdown
   - Shows: Bobby's actual 18 miners, real performance history, specific failures
   - AI Analysis (4 insights with confidence scores):
     - PSU Cascade Failure Pattern (95% confidence, $1,800 preventive vs $4,200 reactive)
     - Unknown Firmware Performance Gap (87% confidence, +19% hashrate potential)
     - Miner .206 Progressive Degradation (94% confidence, 72-hour failure prediction)
     - End-of-Life Economics (78% confidence, gradual S21 migration path)

2. **WhatsMiner M63S+ Pre-Purchase Intelligence** (miner NOT in fleet — catalog-only)
   - Data source: 322 documented M63S+ deployments from catalog
   - AI Analysis (4 pre-purchase warnings):
     - Immersion Incompatibility (92% confidence, 18.2% vs 4.7% failure rate)
     - Profitability Threshold (84% confidence, needs $0.075/kWh or $121k BTC)
     - Integration Complexity ($1,200-1,800 cost, 7-14 days to stable operation)
     - Parts Supply Chain Risk (86% confidence, 2-3 week lead times)

**Key Value Proposition:**
- **WITH operational data:** "Here's what YOUR miners are doing, YOUR failures, YOUR specific action items"
- **WITHOUT operational data:** "Here's what 322 deployments show, pre-purchase warnings, avoid this $50k mistake"

**Grafana Integration:**
- Intelligence Report Dashboard: https://grafana.fieslerfamily.com/d/intelligence_report_001/ (searchable miner lookup, HTML reports)
- Intelligence Catalog Dashboard: https://grafana.fieslerfamily.com/d/cfj6drj3pbk74b (PostgreSQL schema overview)
- PostgreSQL datasource connected (ROBS-PC:5432)
- Intelligence Report API on port 8590 serves 235+ model reports via iframe rendering (Business Text plugin incompatible with Grafana 10.4.1)

**Business Impact:**
- Pre-purchase intelligence prevents $50k+ deployment mistakes
- Network effects: More BiXBiT customers = better AI intelligence for everyone
- Service revenue: Premium tier with full catalog access
- Repair shop data integration: BiXBiT techs feed repair records back, creating competitive moat

**What's Next (Vision Complete, Implementation Pending):**
- [x] Interactive catalog query interface → **DONE 2026-04-15** — Intelligence Report API (port 8590) + Grafana dashboard
- [x] Searchable miner lookup across 235+ models → **DONE 2026-04-15** — text search + dropdown in Grafana
- [ ] Full 40-page PDF rendering (markdown complete, PDF converter compresses output)
- [ ] Qwen AI analysis paragraphs injected into report (requires Qwen reachable from API)
- [ ] PDF download button within Grafana dashboard
- [ ] Additional enrichment: auto-import new data points as catalog grows

**Intelligence Report API (Built 2026-04-15):**
- File: `api/intelligence_report_api.py`
- Port: 8590 (systemd: `intelligence-report.service`)
- 235+ Bitcoin SHA-256 miner models searchable
- Data sources: `unified_miner_index.json` + `miner_enrichment_master.csv` + `miner_specs.json` + `guardian.db`
- Endpoints: `/api/report/models`, `/api/report/search?q=`, `/api/report/{slug}`, `/api/report/{slug}/html`, `/api/report/{slug}/html/render`
- HTML rendering via iframe approach — `dashboard_api.py` proxy serves full HTML pages at `/api/report/{slug}/html/render` through Cloudflare tunnel
- Grafana dashboard: `intelligence_report_001` at `/d/intelligence_report_001/`
- Business Text plugin v6.2.0 installed on VPS but requires Grafana 11+ — will be usable after Grafana upgrade or on Mac mini deployments

**Status:** ✅ FULLY OPERATIONAL — API running on VPS (235 models), iframe rendering confirmed working in Grafana (verified April 15 6:28 PM CDT)

**Deployment Bugs Fixed (April 15 evening):**
1. **REPO_DIR path bug** — API pointed to `api/` instead of repo root, returned 0 models. Fixed: `REPO_DIR = BASE_DIR.parent` (commit `2bb7305`)
2. **Mixed content / localhost bug** — browser couldn't reach VPS localhost. Fixed: HTTPS proxy route in `dashboard_api.py` (commit `af82ce2`)
3. **Script stripping bug** — Grafana text panel strips `<script>` tags, Business Text needs Grafana 11+. Fixed: iframe approach with `/api/report/{slug}/html/render` endpoint (commit `e3acf26`)

---

## 48-Hour Test Results (April 6–8 2026)
- "miners just restarted, need to wait 20 minutes after restart to download logs then make recommendations"
- "waiting the 20 minutes still"

All captured in the audit log. The 20-min post-restart grace rule is now baked into `_analyze_miner` directly. Additional denial reasons flow into Sunday Claude training via `train_cohort.py` for rule refinement.

### The April 8 AH3880 Firmware Regression — most important learning of the test

Bobby updated firmware on both AH3880 miners (`192.168.188.28` and `.55`). Both immediately showed identical faults: PSU IOUT 0x02 overcurrent trips, DVFS voltage clipping at Vmin/Vmax, pool stratum panics, hashrate stuck at ~79%. Dual-model analysis (Qwen + Claude) both confidently diagnosed "Replace PSU" at HIGH confidence. **Both were wrong.** The PSUs were fine — the new firmware was mismanaging DVFS power delivery in a way that looked like PSU instability.

Bobby corrected the diagnosis in 5 seconds with one operator insight: "I just updated the firmware on both." Both LLMs then correctly re-diagnosed as firmware regression and recommended rollback instead of PSU replacement.

**The permanent operator rule added from this:** When N+ miners of the same model show identical fault patterns within hours of a firmware update, prefer "firmware regression" diagnosis over individual hardware failure. Now baked into all LLM prompts and stored in `knowledge.json` as `operator_learning:firmware_regression_2026_04_08`.

**The build item this generated:** Daily Log Capture & 14-Day Rolling Baseline system (see `docs/DAILY_LOG_CAPTURE_VISION.md`). This would have caught the regression automatically on the first post-update scan without needing Bobby's insight — the system would have seen "two miners of the same model showing identical fault patterns within hours of firmware_changes rows" and flagged it as a regression candidate before either LLM ran its first analysis. **3-5 day build, highest priority post-demo.**

---

## Fixes Deployed During 48hr Test

### Operational Fixes
- [x] **20-minute post-restart grace period** — miners suppressed from action recommendations for 20 min after restart (both MG-tracked and manual AMS restarts via uptime check)
- [x] **Hashrate % fix** — now uses BiXBiT profile parser instead of AMS stock maxHashrate. Fixed 201% → 101%
- [x] **POWER_PROFILE_UP spam fix** — only fires as recovery after MG steps a miner DOWN, not for every miner below theoretical max
- [x] **AMS alerts suppressed from Slack** — still stored in DB for learning, removed from Slack messages (operator request)
- [x] **Deny flow complete** — DENY → "Why?" follow-up → reason captured and stored. Clean two-step workflow, or inline with `DENY <reason>`
- [x] **Crystal ball single post** — each recommendation posts once (was duplicating)
- [x] **Pending approvals whitelist** — POWER_PROFILE_UP, PREEMPTIVE_RESTART, ECO_MODE, MONITOR_CLOSE added to `save_pending_approvals`
- [x] **Ticket 30-min grace period** — don't ticket miners restarted < 30 min ago
- [x] **Temperature threshold corrected** — 84°C only, no yellow tier. All flagging logic, prompt templates, and local LLM system prompt updated.

### Dashboard Fixes
- [x] Grafana Board Health dropdown — fixed metric name (mhs → ths) so miner IP dropdown populates
- [x] Grafana Pool Stats redesigned — hero tiles, rejection rate chart, problem miners table
- [x] Grafana Main rejection chart — replaced per-miner spaghetti with fleet avg + worst miner
- [x] AI Intelligence Center — complete rebuild with live action queue, approve/deny buttons, AI score

### Code Quality (from code review — 53 findings across 35K lines)
- [x] Dead code removed (orphaned method bodies)
- [x] `api/slack_listener.py` deleted (violated Socket Mode rule)
- [x] Auth bypass in `approval_api.py` — now fails closed
- [x] Atomic writes in `outcome_checker.py`
- [x] DB leaks (bare `_connect().execute()`) — context managers added in predictor.py (Phase 3)
- [x] NameErrors in predictor loop and `_escalate_board_issue` — fixed (Phase 1)
- [x] knowledge.json file locking — `core/file_lock.py` shared utility, 6 writers updated (Phase 3)
- [x] AMS token lock wired in `_ensure_token()` — thread safety for parallel workers (Phase 3)
- [x] `/metrics` endpoint cached — 25s TTL reduces SQLite load (Phase 3)
- [x] AV2 Plant credentials moved to env vars (Phase 3)
- [x] Slack handler memory leak — bounded `OrderedDict` capped at 10K entries (Phase 3)
- [x] Atomic writes in `fingerprint_builder.py` + `hvac_correlator.py` (Phase 3)
- [x] Approval API transaction safety + case normalization (Phase 2)
- [x] Slack auth enforcement — `AUTHORIZED_SLACK_USER_IDS` actually checked (Phase 2)
- [x] LLM analyzer correct host/model defaults (Phase 2)
- [ ] File handle leak in `overnight_automation.py` (MEDIUM)
- [ ] **Log file rotation bug** (MEDIUM, found April 9 2026 diagnostic) — `_setup_logging()` in `core/mining_guardian.py` computes the log filename once at module import and never rolls over at midnight. Fix: replace `FileHandler` with `TimedRotatingFileHandler(when='midnight', backupCount=14)`. Doesn't affect operation — `journalctl -u mining-guardian` has complete records — but file-based log inspection is misleading until fixed.

---

## 8 AI Features — Current Status

### Feature 1: Outcome Feedback Loop ✅ LIVE
**File:** `ai/outcome_checker.py`
**Results:** 22 SUCCESS, 24 FAILURE outcomes tracked and labeled during the 48hr test
**How it works:** After every scan, checks restarts without outcomes. SUCCESS if hashrate returns to ≥80% rated within 4 scans and stays there for 2 consecutive scans. PARTIAL if 50-80%. FAILURE if no recovery within 4 scans. Writes back to `miner_restarts.outcome` and updates per-miner fingerprint in `knowledge.json`.

### Feature 2: Confidence Scoring ✅ LIVE
**File:** `ai/confidence_scorer.py`
**Results:** Confidence shown in Slack, gates auto/manual decisions
**How it works:** Blends per-miner success rate (weight 0.60) + fleet-wide success rate (0.25) + stability score (0.15) + fingerprint confidence modifier (±15 points). Gates: ≥80 = AUTO, 50-79 = ASK, <50 = HOLD.

### Feature 3: Denial Reason Capture ✅ LIVE
**Files:** `api/slack_approval_listener.py` + `ai/llm_scan_hook.py`
**Results:** 11 denial reasons captured during 48hr test
**Gap:** `weekly_train.py` does NOT read denial reasons directly — only `train_comprehensive.py` does, and `train_cohort.py` uses it as a helper. Verify this is actually feeding into the Sunday training. **HIGH priority fix before next Sunday.**

### Feature 4: Miner Fingerprinting v2 ✅ LIVE
**File:** `ai/fingerprint_builder.py`
**Results:** 58 profiles with behavioral fingerprints
**Data used:** restart outcomes, hashrate stability, temps, per-board voltage/freq/HW errors, pool rejection rate, AMS alert counts, chip bin/PCB/PSU, uptime resets, chain detach events, PDU power variance. Produces a confidence modifier (-0.5 to +0.5) that adjusts action confidence per-miner.

### Feature 5: HVAC/Environment Correlation ✅ LIVE
**File:** `ai/hvac_correlator.py`
**Results:** 0% facility stress consistently — confirms miner issues are hardware, not environmental
**How it works:** Calculates facility stress score 0-100 from supply water temp, delta-T, differential pressure, pump VFD %, pump fault, leak alarm. When N+ miners flag simultaneously AND facility stress > 26, logs a `facility_event` to `knowledge.json`. Slack alerts distinguish "Facility Alert" from "Miner Alert."

### Feature 6: Pre-Failure Prediction v2 ✅ LIVE (currently paused from Slack)
**File:** `ai/predictor.py`
**12 signals:** hashrate trend decline, volatility spike, board rate imbalance, chip temp creep, historical pattern match, board voltage drop, board temp elevated, pool rejection spike, AMS alert spike, uptime reset, max temp trend, chain attach/detach events.
**Current state:** Running every scan, storing predictions, but NOT posting to Slack. Predictions are being stored for review but the action recommendation path is paused pending confidence threshold tuning.

### Feature 7: Repair Shop Data Ingestion ⏳ BLOCKED
**Blocked on:** Dataset from James Scaggs / Advanced Crypto Services. 1M+ historical data points expected. Will feed into the Mining Intelligence Catalog (Postgres research DB on ROBS-PC → NAS in July) rather than `guardian.db`. See `intelligence/README.md`.

### Feature 8: Action Diversity ✅ LIVE (fixed during test)
**File:** `ai/action_diversity.py`
**New actions beyond RESTART/PDU_CYCLE:** POWER_PROFILE_DOWN (≥75 confidence), POWER_PROFILE_UP (≥80), ECO_MODE_FLEET (≥80), POOL_FAILOVER (≥85). All confidence-gated and data-driven.
**Fix applied:** POWER_PROFILE_UP now only fires as recovery after MG stepped a miner DOWN — was firing for every miner below theoretical max, spamming the queue.

---

## The OpenClaw Conversational Layer

### What OpenClaw is

OpenClaw is the Slack conversational brain. It owns Socket Mode (outbound-only, no public ingress), routes DMs and @mentions to the local LLM, handles Block Kit interactions, and on the Mac mini will route button clicks directly to the local approval API. It is an integral part of the product architecture, not a separate add-on.

**As of April 8 2026:** OpenClaw is running in Docker, Socket Mode connected, verified delivering replies to Bobby's Slack user `U07AGTT8CLD`.

### What OpenClaw needs to do (target state)

1. **Real-time conversational fleet queries** — operator asks "Why did .35 restart 3 times?" and gets an intelligent answer built from live `guardian.db` data via the guardian-db skill. ← **top priority**
2. **Block Kit button click routing** — APPROVE/DENY buttons route through Socket Mode → localhost approval API (replaces Cloudflare tunnel path)
3. **Real-time scan narration** — post-scan summaries in natural language instead of rules-based flag lists
4. **Real-time denial reason processing** — operator denial reasons go through local LLM immediately for rule extraction, not waiting for Sunday training
5. **Pre-action analysis** — before recommending restart, LLM reviews miner's full history and provides nuanced recommendation

### Current blocker: guardian-db skill loading

The guardian-db skill files exist at `deploy/openclaw-skills/guardian-db/` on disk and inside the container at `/data/.openclaw/skills/guardian-db/`. OpenClaw isn't auto-discovering them. `loadWorkspaceSkillEntries` exists in the dist bundle but isn't being called for the guardian-db path.

**Three paths forward** (try in this order):
1. Find the config key that enables user skill auto-discovery in OpenClaw
2. Install as a bundled skill via docker-compose volume mount
3. Read the OpenClaw docs directly instead of guessing at internals

**Time budget:** 2 hours max on this. If none of the three paths work in 2 hours, escalate and reassess — but do NOT pivot to "build a webpage instead of using OpenClaw." OpenClaw is the conversational brain, not an obstacle to route around.

---

## Migration to Mac Mini — Hard Deadline May 5–9 2026

**`fieslerfamily.com` is Bobby's personal R&D-only domain.** Every service that currently uses a Cloudflare tunnel must move off before the Mac mini arrives. There is **no public ingress** at a customer site — outbound internet only (AMS, Slack Socket Mode, Claude API for weekly training, Open-Meteo for weather).

See `docs/CLOUDFLARE_MIGRATION.md` for full detail.

### Migration checklist

- [ ] `dashboard.fieslerfamily.com` (VPS:8585) → `http://mac-mini-ip:8585` on Mac mini
- [ ] `slack.fieslerfamily.com` (VPS:8686) → OpenClaw Socket Mode → `localhost:8686`
- [ ] `grafana.fieslerfamily.com` (VPS:3000) → `http://mac-mini-ip:3000` on Mac mini
- [ ] Build OpenClaw `block_actions` handler that forwards button clicks to local approval API
- [ ] Update `api/slack_block_kit.py` `action_id` values to use `mg_` prefix so OpenClaw can identify Mining Guardian buttons
- [ ] Delete `api/slack_actions_handler.py` — its design requires public ingress
- [ ] Remove Cloudflare tunnel systemd units from `deploy/`
- [ ] Audit: `grep -rn 'fieslerfamily' . --include='*.py' --include='*.md' --include='*.json' --include='*.service'` and resolve every hit
- [ ] No customer-facing code or documentation references `fieslerfamily.com`
- [ ] Containerize Mining Guardian — docker-compose stack with Mining Guardian, OpenClaw, Prometheus, Grafana, Ollama as services
- [ ] Shared volumes for `guardian.db`, `knowledge.json`, `logs/` between Mining Guardian and OpenClaw containers
- [ ] Service-name DNS for inter-container communication (not localhost:port hardcodes)

### Outbound-only endpoints that remain

| Endpoint | Why | Notes |
|---|---|---|
| AMS API (`api-staging.dev.bixbit.io` or production AMS) | All miner commands | Outbound HTTPS |
| Slack Socket Mode (via OpenClaw) | Conversational AI + button event delivery | Outbound websocket |
| Slack outbound API (`slack.com`) | `chat_postMessage`, etc. | Outbound HTTPS |
| Anthropic Claude API | Weekly training only (Sundays 3am) | Proof-of-concept site only; production customer sites use local LLM only |
| Open-Meteo | Weather data | Free, no key |
| NTP | System clock | Standard |
| Tailscale | Optional support access | Customer decision |

### Customer installer

**`installer/DEPLOYMENT.md` already exists** on the `installer-build` branch (313 lines, committed April 6 2026). It specifies:

- Pre-flight checks (OS, Python 3.11+, AMS connectivity, Slack token, disk/RAM)
- Interactive configuration wizard (site identity, AMS, fleet auto-discovery, PDU mapping, Slack, local LLM, Claude API)
- Installation steps (venv, dependencies, DB init, config/env write, launchd services, Grafana provisioning)
- First-run verification (AMS scan, log collection, hardware parse, baseline learning mode, Slack test)
- macOS launchd services + Linux systemd alternative
- Directory structure under `~/mining-guardian/`
- Hardware recommendations: Mac mini M1 8GB (minimum), M2 Pro 16GB (recommended), M4 Pro 32GB (optimal)
- Timeline and open questions

**Do NOT write a new installer plan.** Update the existing one. The work begins May 3 2026.

---

## Build Queue (Current Priority Order)

### P0 — Immediate (this week)

1. **Wire OpenClaw to `guardian.db` via guardian-db skill**
   Unblock the skill auto-discovery issue. 2hr time budget on the skill-loading investigation. This is the top priority because OpenClaw is the conversational brain of the product and without it, the LLM can't answer real-time operator questions with live fleet data.

2. **Daily Log Capture & 14-day rolling baseline** — PARTIALLY SHIPPED April 9 2026
   See `docs/DAILY_LOG_CAPTURE_VISION.md` for original plan. Status after April 9 afternoon sprint:
   - ✅ Daily baseline log collection (`collect_logs` in `core/mining_guardian.py`) — parallel 15-worker, 10-min cap per miner, commits `95676b6` + `da1edbd` + `e5b9f5c`
   - ✅ Daily deep dive LLM (`ai/daily_deep_dive.py`, 953 lines) — Qwen 32B full study of fleet once a day, commit `da1edbd`. See `docs/DAILY_DEEP_DIVE_DESIGN.md`
   - ✅ Weekly Claude training merges restart comparisons — `TEMP_MAY_REMOVE` block in `ai/train_cohort.py`, commit `e90c2be`
   - ⏳ `daily_deep_analyses` permanent merge into weekly Claude training — apply script written but not shipped
   - ⏳ `firmware_changes` table + scan-loop change detector — not started
   - ⏳ `ai/regression_detector.py` + Slack alert wiring for firmware regression detection — not started
   - ⏳ Cron entries for 1pm daily collection + 4pm daily deep dive — not yet added to VPS crontab

3. **`weekly_train.py` denial reason ingestion gap**
   Verify denial reasons are actually flowing into Sunday's `train_cohort.py` run. `train_comprehensive.py` reads them; confirm the cohort trainer inherits them via its imports. Fix before next Sunday if broken.

4. **Ship the `daily_deep_analyses` permanent merge block in `ai/train_cohort.py`**
   Apply script written as `.apply_dd_merge.py` in working tree. Extends the existing merge block to pull `daily_deep_analyses` entries from `knowledge.json` into the Sunday Claude weekly training stream. NOT wrapped in `TEMP_MAY_REMOVE` — this is permanent infrastructure per operator rule.

5. **Add VPS cron entries for daily collection + daily deep dive**
   - `0 13 * * * ...` daily log collection forced at 1pm local
   - `0 16 * * * ...` daily deep dive fires at 4pm local
   Needs a small helper in `mining_guardian.py` (or a standalone script) to force `collect_logs` to run outside the hourly scan loop.

6. **Physically inspect miner 53482 (192.168.188.46)**
   BiXBiT S19JPro, running 83.5% of target, error codes 412 + 101, firmware `BiXBiT 0.9.9.3-stage29.2799`, AMS log export hung. Discovered during April 9 afternoon sprint. The hourly reactive scan has been silently ignoring it because 83.5% is above the hashrate flag and 70°C is below the temperature flag. Needs operator eyeballs or an AMS ticket.

### P1 — Before Mac Mini arrival (May 5–9)

4. **OpenClaw `block_actions` handler** — forward Block Kit button clicks via Socket Mode to local approval API
5. **`mg_` action_id prefix** in `api/slack_block_kit.py`
6. **Delete `api/slack_actions_handler.py`** (requires public ingress)
7. **`grep -rn 'fieslerfamily'` cleanup** — resolve every hit
8. **CORS audit** — lock all CORS rules to localhost + service-name DNS
9. **Docker-compose stack definition** — Mining Guardian, OpenClaw, Prometheus, Grafana, Ollama as services
10. **Shared volumes** — `guardian.db`, `knowledge.json`, `logs/` between containers
11. **Log rotation fix** — hourly fix in `core/mining_guardian.py` `_setup_logging()`, see Code Quality section above

### P2 — Customer installer work (starts May 3)

12. **Update `installer/DEPLOYMENT.md`** on `installer-build` branch with findings from VPS operation
13. **Build `installer/install.sh`** — OS detection, dependency install
14. **Build `installer/wizard.py`** — interactive configuration
15. **Build `installer/setup_services.py`** — launchd plists (macOS) + systemd units (Linux)
16. **Build `installer/first_run.py`** — initial fleet discovery + baseline learning
17. **Build `installer/verify.py`** — post-install health check
18. **Operator guide** — `docs/OPERATOR_GUIDE.md`
19. **Troubleshooting guide** — `docs/TROUBLESHOOTING.md`
20. **API reference** — `docs/API_REFERENCE.md`

### P3 — Post-Mac mini launch

21. **Open Log Uploader** (2-4 week build) — see `docs/OPEN_LOG_UPLOADER_VISION.md`. 4 phases, 10 open design questions to resolve first. Any-vendor any-format ingestion engine for repair shop bulk drops.
22. **Mining Intelligence Catalog Phase 1** on ROBS-PC — see `intelligence/README.md`. Blocked on Thunderbolt 4 SSD enclosure delivery AND WSL2/Docker virtualization conflict (Memory Integrity likely). **30-minute hard cap** on WSL2 debug, fall back to native Postgres via EnterpriseDB installer.
23. **Monthly federation refinement pipeline** — add dual-pass refinement (Claude + local LLM) to `combine_knowledge.py` for higher-quality `master_knowledge.json`
24. **Auradine AH3880 direct API integration** — port 8443, standby-before-PDU-cut rule, see `docs/AURADINE_API.md`
25. **Auradine firmware rollback** — waiting on vendor. Roll back `.55` first, observe 24h, then `.28`.

### P4 — Gated on external inputs

26. **Repair shop data ingestion (Feature 7)** — 1M+ historical data points from James Scaggs / ACS. Blocked on dataset delivery.
27. **Container monitoring integration** — BiXBiT container system mapped in `docs/CONTAINER_MONITORING.md`. Blocked on live access grant.
28. **NAS migration (Mining Intelligence Catalog Phase 2)** — July 2026, UGREEN NASync iDX6011 Pro. `pg_dump` → file copy → `pg_restore`. ~20 min for 60 GB.

### P5 — Long-term

29. **Multi-site federation at scale** — sync master knowledge across multiple customer deployments monthly via USB
30. **Grafana alerting** — replaces Slack-based alerting over time for passive notifications
31. **Knowledge Score trending** — day-over-day improvement visible in AI dashboard (accumulates over weeks)
32. **PDU password rotation** — change from defaults on PDUs `.15` and `.16`

---

## Completed Items (for reference)

### ✅ Completed April 15 2026 (Intelligence Report + Dashboard Fixes)

- [x] Intelligence Report API built (`api/intelligence_report_api.py`, port 8590) — 235+ Bitcoin SHA-256 models searchable, HTML report rendering
- [x] Intelligence Report Grafana dashboard (`intelligence_report_001`) — text search + dropdown, Business Text panel for HTML reports, fleet time-series
- [x] All 6 operational Grafana dashboards fixed — removed duplicate panels from AI & Learning, Main, Fleet, Per Miner, Board Health, Pool Stats
- [x] Unified miner index built — merged all data sources into `unified_miner_index.json` (235 models)
- [x] systemd service file for Intelligence Report API (`deploy/intelligence-report.service`)
- [x] API documentation (`docs/INTELLIGENCE_REPORT_API.md`)
- [x] README.md updated — architecture diagram, services table, dashboards table, key files
- [x] AI_ROADMAP.md updated — milestones marked complete, API details documented

### ✅ Completed April 10–14 2026 (Code Review + Hardening)

- [x] Full code review — 53 findings across 35K lines of code (April 14)
- [x] **Phase 1** (commit 88b5b08): 6 CRITICAL fixes — silently broken predictions (NameError), board escalation crash (undefined `issue`), catalog auth header (Bearer→X-API-Key), fleet synthesis crash (undefined `hvac_system`), SQL syntax error in pool_readings, Auradine missing `import os`
- [x] **Phase 2** (commit dda6bd0): 4 fixes — approval API transaction safety + case normalization, SlackNotifier.send_scan DB wiring for ticket suppression, AUTHORIZED_SLACK_USER_IDS enforcement, LLM analyzer correct host/model defaults
- [x] **Phase 3** (this commit): 7 fixes — knowledge.json file locking (6 writers), predictor DB connection leaks (try/finally), AMS token lock wired, /metrics cached (25s TTL), AV2 credentials to env vars, Slack handler bounded sets (10K cap), atomic writes in fingerprint_builder + hvac_correlator
- [x] REPAIR_LOG.md — 17 new entries covering all Phase 1/2/3 fixes
- [x] README.md — updated security, knowledge system, AI features status, code review summary
- [x] .env.example — complete reference for all 30+ env vars (was only 4)
- [x] Comprehensive AI audit — 12 feedback loops verified closed, orphaned hvac_correlation fixed (April 11)
- [x] Operator rule consolidation — 3 cooldown rules → 1 unified 20-min rule (April 11)
- [x] Correct local_llm_analyzer.py deployed to production (April 11)

### ✅ Completed April 4–9 2026

- [x] Full VPS deployment — all services running on systemd
- [x] Prometheus + Grafana — 7 dashboards with live data
- [x] AI & Learning dashboard — knowledge score, insights growth, autonomy rate (all real Prometheus data)
- [x] Pool Stats simplified — fleet totals + top 5 worst offenders
- [x] Per-miner search — type-to-filter on all per-miner dropdowns
- [x] Two-tier AI — Qwen 2.5 32B scans + Claude API weekly training
- [x] Knowledge base → Prometheus — all AI metrics visible in Grafana live
- [x] Cohort-based weekly training (`train_cohort.py`) — scale-first, replaces per-miner blasting
- [x] Dual-model pre/post restart log comparison (`ai/claude_log_comparison.py`)
- [x] Daily log collection fix — removed hidden caps, parallel 15-worker sweep with 10-min per-miner cap (April 9, commits `95676b6` / `da1edbd` / `e5b9f5c`)
- [x] Weekly Claude training picks up dual-model restart comparisons (April 9, commit `e90c2be`) — silent-skip bug where comparisons were written to `known_issues` but trainer read `llm_scan_analyses`
- [x] Daily Deep Dive LLM (`ai/daily_deep_dive.py`) — Qwen 32B long-form daily fleet study, per-miner pass + fleet synthesis, no caps (April 9, commit `da1edbd`). See `docs/DAILY_DEEP_DIVE_DESIGN.md`
- [x] 4-Pass Weekly Refinement Chain (`ai/refinement_chain.py`) — Qwen reflects on Claude weekly output, catches errors, Claude merges corrections. Resume-safe with WIP checkpointing. First run April 10 2026 caught 4 Claude errors. See `CLAUDE.md` section "The 4-Pass Weekly Refinement Chain"
- [x] REPAIR_LOG.md created — layman-terms record of bugs and fixes (April 9, commit `d6c2871`)
- [x] `docs/SESSION_LOG_2026-04-09.md` — full narrative of April 9 afternoon log pipeline sprint
- [x] CLAUDE.md — added May Migration Changes section, Working Practices section (document-as-you-go + context compaction awareness)
- [x] Real Auradine API client (`clients/auradine_client.py`, 602 lines)
- [x] 2-restart escalation — auto-ticket after 2 failed restarts, both manual and overnight
- [x] Overnight automation — autonomous action engine 8pm–6am
- [x] Quiet hours — no Slack noise 10pm–5am
- [x] 1-hour approval window — unanswered approvals auto-expire, re-raised fresh next scan
- [x] Dead board lifecycle — detect → restart → ticket → suppress
- [x] Security hardening — CORS, auth, credential removal, double-actuation bug fixed
- [x] Federated knowledge system — `ai/combine_knowledge.py` for multi-site merges
- [x] Backup system — rolling DB + daily snapshots to T9 drive + GitHub
- [x] HVAC/BAS integration — Distech Eclypse supply/return/pressure/pump data in Slack + Grafana
- [x] 48hr live test — 149 scans, 12.1M data points, 58 fingerprints, 22/24 outcomes, 11 denial reasons
- [x] Temperature operator rule locked — 84°C only, no yellow tier
- [x] HVAC operator rule locked — do not flag based on delta-T
- [x] Firmware regression operator rule captured — N+ same-model miners with identical faults after firmware update = regression candidate, not hardware failure
- [x] 6-channel Slack routing architecture — #mining-guardian, -alerts, mg-scans, mg-ai-reports, mg-approvals, mg-logs
- [x] `/query/*` read-only endpoints in `dashboard_api.py` for OpenClaw guardian-db skill consumption
- [x] OpenClaw Docker container running + Socket Mode connected
- [x] Vision consolidation (April 9) — `docs/VISION.md` created, `CLAUDE.md` rewritten with Session Kickoff Protocol + Vision Anchors + Failure Modes + Document Map
- [x] Morning kickoff prompt pinned in `#mg-ai-reports` and saved to `docs/MORNING_KICKOFF_PROMPT.md`
- [x] Diagnostic sweep (April 9) — confirmed scan cadence is 1/hour by config, confirmed AMS false-offline issue is an AMS upstream bug (not Guardian), identified log rotation bug in `_setup_logging()`

---

## Technical Notes

- HVAC/BAS integration is one-off for Bobby's warehouse — NOT in customer deployment templates
- S19JPro dead board repairs explicitly crossed off — do not raise
- Pool failover requires `backup_pool_url` in `config.json` — not currently set
- AH3880 board voltage 0.29V is Auradine firmware format, NOT a fault — `predictor.py` suppresses voltage signal for Auradine miners
- Feature 7 blocked pending repair shop dataset from James/ACS
- OpenClaw Socket Mode owns the Slack connection — never add Bolt/slack-bolt elsewhere
- All denial reasons feed into Sunday training via `train_cohort.py` → fleet synthesis pass
- `train_cohort.py` is the scale-first weekly trainer — it's the reference implementation for the entire production architecture. Same code path runs on customer Mac minis with Qwen 32B instead of Claude.
- **AMS false-offline is an AMS upstream bug, not a Guardian bug.** AMS periodically reports miners as offline when they're actually online. Guardian handles this correctly with the direct-TCP false-offline detection path in `_analyze_miner` (flags as `AMS_SYNC` for up to 10 consecutive scans, then suppresses). The 9 "missing" miners seen during the April 9 diagnostic (49 visible vs 58 historical) is an expression of this AMS bug — not a Guardian problem. Fix is being worked on by the AMS team separately.

---

*Last updated: April 15, 2026 — Intelligence Report API built + Grafana dashboard live, all 6 operational dashboards fixed (duplicate panels removed), code review hardening complete, approaching Mac mini migration. See `CLAUDE.md` for binding rules, `docs/VISION.md` for the canonical plan, and `README.md` for current architecture reference.*
