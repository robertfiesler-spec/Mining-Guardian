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

---

## Production Migration — Cloudflare Removal

**Hard deadline:** May 5-9, 2026 (Mac Mini arrival window)

`fieslerfamily.com` is Bobby's personal R&D-only domain. Every service that
currently uses a Cloudflare tunnel must move to the local Mac Mini before the
production architecture is locked in. There is **no public ingress** at a
customer site — outbound internet only (AMS, OpenClaw socket, Slack outbound).

See `docs/CLOUDFLARE_MIGRATION.md` for full detail.

### Migration checklist

- [ ] `dashboard.fieslerfamily.com` (VPS:8585) → `localhost:8585` on Mac Mini
- [ ] `slack.fieslerfamily.com` (VPS:8686) → OpenClaw socket → `localhost:8686`
- [ ] `grafana.fieslerfamily.com` (VPS:3000) → `localhost:3000` on Mac Mini
- [ ] Block Kit interactive button routing: build OpenClaw `block_actions`
      handler that forwards to local approval API
- [ ] Update `api/slack_block_kit.py` action_id values to use `mg_` prefix
      so OpenClaw can recognize Mining Guardian buttons
- [ ] Delete or formally deprecate `api/slack_actions_handler.py` — its design
      requires public ingress and won't work on a Mac Mini
- [ ] Remove Cloudflare tunnel systemd units from `deploy/`
- [ ] Audit: `grep -rn 'fieslerfamily' . --include='*.py' --include='*.md' --include='*.json' --include='*.service'`
      and resolve every hit (migrate to localhost, migrate to Tailscale, or
      remove)
- [ ] No customer-facing code or documentation references `fieslerfamily.com`

### Outbound-only requirements that stay

| Endpoint | Why | Notes |
|---|---|---|
| AMS API (`api-staging.dev.bixbit.io` or production AMS) | All miner commands | Outbound HTTPS |
| OpenClaw → Slack | Conversational AI + button event delivery | Outbound websocket (Socket Mode) |
| Slack outbound API (`slack.com`) | `chat_postMessage`, etc. | Outbound HTTPS |
| NTP | System clock | Standard |
| Tailscale | Support access only | Optional, operator decision |

---

## Mining Intelligence Catalog (NEW — April 8 2026)

**Status:** ARCHITECTURE DESIGNED — install pending hardware

**Purpose:** Standalone backend research and intelligence database for ingesting 50–100 GB of miner spec sheets, community knowledge, repair shop dumps, and historical logs. NOT a replacement for guardian.db — runs in parallel as a parallel research environment.

### Why standalone

| | guardian.db (production) | miner_intelligence (research) |
|---|---|---|
| Engine | SQLite | PostgreSQL 16 |
| Host | VPS (100.106.123.83) | ROBS-PC (192.168.188.47) → NAS in July |
| Size | ~1 GB max | 50-100 GB target, 1 TB ceiling |
| Workload | Real-time fleet ops | Batch ingestion + LLM analysis |
| Volatility | Production-stable | Schema may evolve, rebuilds OK |
| Audience | Mining Guardian + operator | Bobby + LLMs only |

The two databases are deliberately separated so the research side can iterate freely without risking production stability. Guardian eventually queries the catalog read-only over Tailscale for spec lookups and pattern matches, but never depends on the catalog being available.

### Three data streams (planned)

1. **Vendor spec data** — Every miner ever made. Scraped from manufacturer sites, datasheets, archived pages, operator-uploaded PDFs. One row per miner model with TH/s, watts, voltage, board count, chip type, PSU options, control board variants.
2. **Community knowledge** — Reddit posts, forum threads, blog reviews, teardown writeups, war stories. Failure modes, reputation, hardware quirks. Full-text indexed.
3. **Real-world logs and operational data** — Bobby's existing fleet, his friend's repair shop dump (1M+ data points expected), future data dumps Bobby is procuring.

### Hardware

**Phase 1 (now → July 2026): ROBS-PC**
- AMD Ryzen 7 7800X3D (8c/16t, 96 MB L3 V-Cache)
- 32 GB RAM (upgrading to 64-128 GB in ~1 month)
- 2 TB SATA SSD via Thunderbolt 4 enclosure (enclosure on order)
- Static IP `192.168.188.47` (DHCP reservation)
- WSL2 + Docker Desktop (install in progress — virtualization conflict to debug)
- Already runs Qwen 2.5 32B Q4 on RTX 4090

**Phase 2 (July 2026 onward): UGREEN NASync iDX6011 Pro**
- Intel Core Ultra 7 255H, 16c/16t, 96 TOPS AI
- 64 GB LPDDR5x RAM
- 180 TB raw HDD + 18 TB NVMe cache configuration
- Dual 10 GbE, native Docker support
- Migration: pg_dump → file copy → pg_restore. ~20 min for 60 GB.

### Files

| Location | Purpose |
|---|---|
| `intelligence/README.md` | Project documentation, install procedure, security model |
| `intelligence/docker-compose.yml` | Postgres 16 container definition |
| `intelligence/postgres-tuning.conf` | Performance tuning for Ryzen 7800X3D + 32 GB RAM |
| `intelligence/.env.example` | Secrets file template |
| `intelligence/schema/` | (TBD) SQL files defining tables, indexes |
| `intelligence/scripts/` | (TBD) Ingestion, web research, backup scripts |

### Build phases

1. **Phase 0 — install on ROBS-PC** (gated on Thunderbolt 4 SSD enclosure delivery + Docker Desktop fix). Postgres in Docker, listening on `192.168.188.47:5432`, reachable from VPS via existing Tailscale subnet route.
2. **Phase 1 — schema** (gated on Q2-Q10 design questions). Tables: `model_specs`, `community_knowledge`, `log_archive`, `log_metrics`, `diagnostic_test_results`, `dual_model_verdicts`, `known_patterns`, `ingestion_log`, `web_research_cache`, `miner_hardware_components`.
3. **Phase 2 — vendor spec scraper** (build pipeline that hits manufacturer sites, archive.org, vendor PDFs, populates `model_specs` for every miner family Bobby has ever heard of). Runs once per model, cached forever, refreshed monthly.
4. **Phase 3 — community knowledge ingestion** (Reddit/forum/blog scraper, full-text indexed, tagged by miner family).
5. **Phase 4 — log ingestion pipeline** (folder watcher, content-based detection, parser plugin pattern, dual-model LLM analysis, idempotent re-runs).
6. **Phase 5 — search interface** (CLI + raw SQL).
7. **Phase 6 — Guardian integration** (read-only API exposed to Mining Guardian for spec lookups and pattern matches).
8. **Phase 7 — NAS migration** (July 2026, one pg_dump + restore).

### Backup strategy (3-2-1 rule)

1. **Primary** — live database on ROBS-PC SSD → NAS RAID 5/6 in July
2. **Secondary local** — daily pg_dump to backup folder, 14 days retained
3. **Off-site** — encrypted nightly upload to Backblaze B2, 30 days retained

### Open questions to resolve before schema is finalized

See `docs/RESUME_HERE_2026_04_08_EVENING.md` for the full Q2-Q10 list. Bobby is answering them tonight from home.

