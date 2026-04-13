# Mining Guardian — Vision & Canonical Plan

**Last synthesized:** April 13, 2026
**Status:** Living document — update when any of the source docs change
**Purpose:** Single source of truth for Mining Guardian's vision, architecture,
and roadmap. Every new Claude session reads this FIRST before touching code.

This document synthesizes and consolidates:
- `README.md` (architecture)
- `AI_ROADMAP.md` (feature status)
- `docs/CAPABILITIES.md` (what it does)
- `docs/OPENCLAW_INTEGRATION.md` (conversational brain design)
- `docs/CLOUDFLARE_MIGRATION.md` (Mac mini migration)
- `docs/DAILY_LOG_CAPTURE_VISION.md` (regression detection)
- `docs/OPEN_LOG_UPLOADER_VISION.md` (any-vendor ingestion)
- `intelligence/README.md` (research database)
- `installer/DEPLOYMENT.md` on `installer-build` branch (customer installer)

If any of the above conflict with this doc, this doc is wrong — update it.

---

## 1. The One-Paragraph Version

Mining Guardian is an AI-powered autonomous fleet monitoring and remediation
system for Bitcoin mining facilities. It ships as a single Mac mini running a
docker-compose stack at each customer site, scans the fleet every 5 minutes via
the BiXBiT AMS API, diagnoses problems with a two-tier LLM (local Qwen 2.5 32B
for per-scan analysis + Claude Sonnet for weekly deep training), manages the
full action lifecycle (detection → operator approval → execution → outcome
verification → ticket creation → permanent suppression), and continuously
learns from every scan, every operator decision, and every restart outcome.
Each customer deployment exports its knowledge monthly and receives back a
synthesized master knowledge file combining insights from every site, so every
fleet makes every other fleet smarter over time. The conversational interface
is a Slack bot (OpenClaw) that routes operator questions to the local LLM and
Block Kit button clicks to the local approval API via Socket Mode, requiring
zero public ingress at the customer site.

## 2. The Five Vision Anchors

These are the immutable rules. They constrain every design decision.

**1. The LLM IS the product.** The main feature of Mining Guardian is the LLM
getting smarter over time. Every scan feeds it. Every denial refines it. Every
week Claude deeply re-analyzes the fleet. Every month all customer deployments
share knowledge. Any solution that removes the LLM from the operator's
decision flow is the wrong solution.

**2. OpenClaw is the conversational brain, not a replacement target.** OpenClaw
owns Slack Socket Mode, routes DMs and @mentions to the local LLM, and on the
Mac mini will also route Block Kit button clicks back to the local approval
API — all via outbound-only Socket Mode with no public ingress. Fix OpenClaw
when it's broken; don't build around it.

**3. The Mac mini is THE product.** The VPS, Cloudflare tunnels, systemd
services, and `fieslerfamily.com` domains are all R&D scaffolding. The real
product is a single Mac mini running docker-compose at a customer site with
only outbound internet. The entire stack migrates between May 5–9 2026.

**4. Scale-first, always.** Designed for 5,000+ miners per site, not 58. The
cohort-based training architecture (`train_cohort.py`) is the reference: miners
are grouped by hardware identity, analyzed as cohorts, with per-miner deep
dives only for outliers. Cohort count grows sub-linearly with fleet size, so
Claude API cost stays flat across mine sizes and local LLM workload stays
manageable.

**5. Federated learning across customer sites.** Each customer Mac mini exports
`knowledge.json` monthly. Bobby runs `combine_knowledge.py` (optionally with
refinement passes through Claude + local LLM) to merge all site knowledge into
`master_knowledge.json`, which is pushed back to every site. No internet
required for the sync — USB or manual transfer works. Every customer's fleet
makes every other customer's fleet smarter.

## 3. Target Architecture (what we're building toward)

```
┌─────────────────────────────────────────────────────────────┐
│                     CUSTOMER SITE                            │
│                                                              │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐   Mining fleet       │
│  │ Miner 1 │  │ Miner 2 │  │ Miner N │   (58 → 5000+)       │
│  └────┬────┘  └────┬────┘  └────┬────┘                      │
│       │            │            │                           │
│  ┌────┴────────────┴────────────┴────┐                      │
│  │       BiXBiT AMS (LAN)             │                      │
│  │   WebSocket + REST + Cookie Auth   │                      │
│  └────────────────┬───────────────────┘                      │
│                   │                                          │
│  ┌────────────────┴──────────────────────────────────┐       │
│  │           MAC MINI — Mining Guardian               │       │
│  │            (docker-compose stack)                  │       │
│  │                                                    │       │
│  │  ┌──────────────┐  ┌──────────────┐              │       │
│  │  │ mining-      │  │  openclaw    │              │       │
│  │  │ guardian     │◄─┤  (Socket     │              │       │
│  │  │ (Python)     │  │   Mode)      │              │       │
│  │  └──────┬───────┘  └──────┬───────┘              │       │
│  │         │                 │                       │       │
│  │  ┌──────┴─────────────────┴───────┐              │       │
│  │  │  Shared volumes: guardian.db,   │              │       │
│  │  │  knowledge.json, logs/          │              │       │
│  │  └─────────────────────────────────┘              │       │
│  │                                                    │       │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────┐  │       │
│  │  │ prometheus  │  │   grafana   │  │ ollama   │  │       │
│  │  │ (:9090)     │  │   (:3000)   │  │ Qwen 32B │  │       │
│  │  └─────────────┘  └─────────────┘  └──────────┘  │       │
│  │                                                    │       │
│  │  Dashboard (:8585)   Approval API (:8686 local)   │       │
│  └──────────────────────┬─────────────────────────────┘       │
│                         │                                    │
│  Operator access:       │                                    │
│    http://mac-mini-ip:3000 (Grafana)                        │
│    http://mac-mini-ip:8585 (Dashboard)                      │
└─────────────────────────┼────────────────────────────────────┘
                          │
           OUTBOUND ONLY (no public ingress):
               ├── AMS API (or production AMS host)
               ├── slack.com (Socket Mode + chat.postMessage)
               ├── api.anthropic.com (weekly training only)
               ├── open-meteo.com (weather, free, no key)
               └── Tailscale (optional, support access only)
```

## 4. The Learning Loop (the main feature)

This is the single most important mental model for this project.

### 4a. Per-scan loop (every 5 minutes)

1. **Scan** — Mining Guardian polls AMS via WebSocket, gets all miner state
2. **Verify** — false-offline detection via direct TCP (port 4028)
3. **Evaluate** — `_analyze_miner` runs the three-tier hashrate resolver +
   thermal check (≥84°C only) + dead board check + offline decision tree
4. **Store** — scan results written to `guardian.db` across 16 tables
5. **Feed the LLM** — local Qwen 2.5 32B on ROBS-PC receives the scan,
   analyzes it, writes findings into `knowledge.json`
6. **Run the 8 AI features** in sequence in the main `loop()`:
   - Outcome checker (evaluate previous restarts)
   - HVAC correlator (facility stress score)
   - Predictor (12 pre-failure signals)
   - Action diversity (POWER_PROFILE_DOWN, ECO_MODE, POOL_FAILOVER, etc.)
   - Local LLM scan hook (background thread)
7. **Post to Slack** — throttled to once per hour, includes scan summary +
   crystal ball recommendations with approve/deny workflow
8. **Overnight automation** — during 8pm-6am, LOW-risk actions auto-execute
   without approval; 3+ FAILURE outcomes block auto-restart permanently

### 4b. Per-action learning (every time an operator approves/denies)

1. **APPROVE** → action executes via AMS → outcome checker evaluates success
   over the next 2-3 scans → SUCCESS / FAILURE / PARTIAL label written to
   `miner_restarts` table → updates per-miner fingerprint in `knowledge.json`
   → updates fleet-wide success rate in confidence scorer
2. **DENY** → two-step flow: operator replies DENY → Mining Guardian asks
   "Why?" → operator's reason is captured in `action_audit_log` → local LLM
   (via `llm_scan_hook.run_denial_processing_llm`) processes the reason into
   an operational rule candidate → Sunday Claude training validates and
   refines the rule → rule gets baked into future scan-time LLM prompts

### 4c. Weekly training (Sunday 3am)

**`train_cohort.py`** (the scale-first weekly trainer, replaces
`train_comprehensive.py` which hit rate limits at miner #3).

1. **Cohort pass** — group all miners by `(model, firmware, chip_bin, pcb_version, cooling)`.
   At 58 miners this produces ~10-15 cohorts. Send one Claude call per cohort
   with per-cohort aggregates, restart outcome history, top problems, and
   filtered local LLM observations.
2. **Outlier pass** — miners >2σ below their cohort's hashrate mean or >2σ
   above cohort's temp mean get individual deep analysis. Capped at 30
   outliers per run.
3. **Fleet synthesis pass** — one final Claude call with ALL cohort results,
   ALL outlier results, ALL local LLM scan analyses from the past week,
   operator rules, and cross-miner SQL correlations. Produces the weekly
   executive report, fleet-wide patterns, predictive warnings, and refined
   operator rules.
4. **Storage** — every cohort/outlier/fleet result stored in `knowledge.json`
   under `known_issues`, `cross_miner_analysis`, and `llm_scan_analyses`.

This is the same code path that will run on customer Mac minis using Qwen 32B
instead of Claude. The cohort approach makes the workload manageable at any
scale — each Mac mini runs ~30 cohort analyses per training cycle regardless
of whether the fleet is 50 or 5,000 miners.

### 4d. Monthly federation (across customer sites)

1. Each customer Mac mini runs `export_knowledge.py` monthly → produces
   `site_<id>_knowledge.json`
2. Bobby collects all site files (USB, email, any transfer method)
3. Bobby runs `combine_knowledge.py` — merges all sites weighted by confidence,
   produces `master_knowledge.json` with LLM synthesis
4. **Refinement passes** (Bobby's requested enhancement): pipe the master
   through Claude once for cleanup and once through the local LLM for
   consistency checking before distribution
5. Master gets pushed back to every customer site
6. Each site's local LLM uses master knowledge as baseline context in every
   scan-time prompt

No internet is required for any step of this loop. Sneakernet works. Every
customer's fleet makes every other customer's fleet smarter.

## 5. Fleet — Current State (R&D site USA 188)

**58 miners total**, all liquid-cooled:

| Model | Count | Firmware | Cooling | Rated TH/s | Boards |
|---|---|---|---|---|---|
| Antminer S19J Pro | ~36 | BiXBiT | Hydro 2U | 104 (stock) → 160 (max profile) | 3 |
| Antminer S19J Pro | 5 | Stock | Hydro 2U | 104 | 3 |
| Antminer S19j Pro (alt AMS code) | 4 | Stock | Hydro 2U | 104 | 3 |
| Teraflux AH3880 (Auradine) | 2 | Auradine FluxOS | Hydro 2U | 300 (eco) → 600 (turbo) | **2** |
| Antminer S21 EXP Hydro | 2 | BiXBiT | Hydro 2U | 430 (stock) → 506 (max) | 3 |
| Antminer S21 Immersion (.22) | 1 | BiXBiT | Immersion | 208 (stock) → 360 (max) | 3 |
| Antminer S21 Immersion (.23) | 1 | BiXBiT | Immersion | 217 (stock) → 347 (max) | 3 |

**Temp thresholds (LOCKED operator rule):** No yellow tier. 84°C is the only
threshold. Below 84°C is normal regardless of cooling type or cohort average.

**PDU access:** S21 Hydro and S21 Imm have AMS PDU outlets. S19J Pros do NOT
have PDU outlets in AMS — offline remediation is restart → bad PSU ticket.

## 6. System Components

### 6a. Core daemon (`core/mining_guardian.py`, 5480 lines)

The heart of the system. Contains:

- `AMSClient` — cookie-based JWT auth, WebSocket read path, REST write path
- `PolicyEngine` — rule-based finding evaluation
- `RemediationPlanner` — builds action patches
- `ApprovalInterface` — routes findings to operator
- `OpenClawNotifier` — sends scan data to OpenClaw webhook
- `RemediationCooldown` — prevents action spam
- `WeatherCollector` — Open-Meteo weather
- `GuardianDB` — 16-table SQLite schema with atomic writes and migrations
- `SlackNotifier` — 6-channel routing with Block Kit support
- `MiningGuardian` — the main orchestrator with `run_once()` and `loop()`

The `loop()` method runs all 8 AI features in order after each scan.

### 6b. AI layer (`ai/`)

| File | Purpose |
|---|---|
| `train_cohort.py` | Scale-first weekly Claude training (main weekly entry point) |
| `train_comprehensive.py` | Per-miner weekly trainer (deprecated at scale, used as helper by train_cohort) |
| `weekly_train.py` | Cron entry — calls train_cohort + fingerprint_builder + hvac_correlator + predictor |
| `combine_knowledge.py` | Federated multi-site knowledge merger |
| `export_knowledge.py` | Monthly site knowledge export |
| `knowledge_manager.py` | Persistent knowledge.json with atomic writes + context prompt builder |
| `local_llm_analyzer.py` | Runs Qwen 2.5 32B after EVERY scan, processes denials into rules |
| `claude_log_comparison.py` | Dual-model Claude pre/post restart comparison |
| `backup_knowledge.py` | Daily 4am knowledge.json → GitHub backup |
| `outcome_checker.py` | Feature 1 — restart outcome labeling |
| `confidence_scorer.py` | Feature 2 — per-action confidence scoring |
| `fingerprint_builder.py` | Feature 4 — per-miner behavioral fingerprints |
| `hvac_correlator.py` | Feature 5 — HVAC/environment correlation |
| `predictor.py` | Feature 6 — 12-signal pre-failure prediction |
| `action_diversity.py` | Feature 8 — POWER_PROFILE_DOWN/UP, ECO_MODE, POOL_FAILOVER |
| `ai_score.py` | Composite Knowledge Score calculator |
| `llm_scan_hook.py` | Post-scan LLM hook dispatcher |
| `deep_analysis_claude.py` | Ad-hoc Claude fleet analysis |

**8 AI features status** (as of April 9 2026):
1. ✅ Outcome feedback loop — LIVE
2. ✅ Confidence scoring — LIVE, gates autonomy
3. ✅ Denial reason capture — LIVE, 11 reasons captured during 48hr test
4. ✅ Miner fingerprinting v2 — LIVE, 58 profiles
5. ✅ HVAC/environment correlation — LIVE
6. ✅ Pre-failure prediction v2 — LIVE (12 signals including chain_events)
7. ⏳ Repair shop data ingestion — blocked on dataset from James/ACS
8. ✅ Action diversity — LIVE with POWER_PROFILE_UP fix

### 6c. API layer (`api/`)

| File | Port | Purpose |
|---|---|---|
| `dashboard_api.py` | 8585 | REST API + Prometheus /metrics + Retool endpoints + Grafana iframes + `/query/*` (for OpenClaw guardian-db skill) |
| `approval_api.py` | 8686 | APPROVE/DENY/approve_selected + Slack interactive block_actions (local-bound) |
| `slack_approval_listener.py` | — | Polls Slack threads for text APPROVE/DENY replies (will be replaced by OpenClaw routing) |
| `slack_command_handler.py` | — | Conversational fleet intelligence bot (will migrate into OpenClaw) |
| `slack_block_kit.py` | — | Block Kit message builder |
| `slack_actions_handler.py` | — | DEPRECATED — requires public ingress, delete before May 5 |
| `ams_alert_listener.py` | — | Listens for AMS alerts, queues urgent actions |
| `ai_dashboard_api.py` | — | AI Intelligence Center dashboard |

### 6d. Clients (`clients/`)

| File | Purpose |
|---|---|
| `auradine_client.py` | Teraflux AH3880 direct API (JWT auth, port 8443, standby-before-power-cut rule) |
| `container_monitor.py` | BiXBiT container infrastructure monitor (waiting for live access) |
| `hvac_client.py` | Distech Eclypse BAS (facility-specific, NOT in deployment templates) |
| `immersion_client.py` | Fog Hashing Elite 1 immersion tank |
| `pdu_client.py` | BiXBiT 2U+PDU client |

### 6e. Database (16 tables in `guardian.db`)

1. `scans` — scan history
2. `miner_readings` — 27 fields per miner per scan
3. `chain_readings` — per-board: rate, voltage, freq, consumption, HW errors, temp
4. `pool_readings` — per-pool accepted/rejected shares
5. `miner_state_readings` — hashrate tiers, device limits, minerStatus codes
6. `miner_ams_extended` — AMS timestamp, map coords, PDU counter
7. `miner_hardware` — board serial, chip die/bin, PCB/BOM version, PSU
8. `log_metrics` — per-chip hashrate, PSU voltage, system health, chain events
9. `miner_logs` — full raw miner.log files (30-day retention)
10. `action_audit_log` — every action ever (permanent)
11. `known_dead_boards` — dead board registry with ticket tracking
12. `pending_approvals` — actions awaiting operator response (1 per miner max, 1hr expire)
13. `miner_restarts` — every restart + outcome feedback
14. `llm_analysis` — every LLM response with prompt, model, duration
15. `hvac_readings` — supply/return/pressure/pump data
16. `weather_readings` — outside temp and humidity
17. `chip_readings` (stub) — ready for direct-API per-chip data
18. `miner_baselines` — Tier 3 hashrate baseline learning state
19. `facility_events` — HVAC correlator detected fleet-wide events

(The exact count varies by version, but the schema is stable and migrations are
handled in `GuardianDB._init_db`.)

## 7. Hard Deadlines & Migration

### May 3, 2026 — Customer installer work begins
- Update the existing `installer/DEPLOYMENT.md` on the `installer-build` branch
- Do NOT write a new installer plan — the 313-line spec from April 6 exists
- Build the wizard, launchd plists, verify scripts per that spec

### May 5–9, 2026 — Mac mini arrives
- Containerize Mining Guardian (docker-compose)
- Deploy to Mac mini
- All Cloudflare tunnels off
- All VPS services migrated
- No public ingress at customer sites
- Interactive Slack buttons route via OpenClaw Socket Mode → localhost approval API
- Delete `api/slack_actions_handler.py`
- `grep -rn 'fieslerfamily'` and resolve every hit

### July 2026 — Intelligence catalog migrates to NAS
- UGREEN NASync iDX6011 Pro arrives
- Postgres + intelligence catalog moves from ROBS-PC to NAS
- `pg_dump` → file copy → `pg_restore` (~20 minutes for 60GB)
- ROBS-PC stays as subnet gateway + LLM host, freed of DB duties

## 8. Build Queue (in priority order)

### In progress or imminent

1. **Wire OpenClaw to guardian.db** via the `guardian-db` skill. The skill
   files exist at `deploy/openclaw-skills/guardian-db/` and inside the
   container at `/data/.openclaw/skills/guardian-db/`. The blocker is that
   OpenClaw doesn't auto-discover user skills — `loadWorkspaceSkillEntries`
   exists in the dist bundle but isn't being called for the `guardian-db`
   path. Three paths forward: (a) find the config key, (b) install as bundled
   skill via docker-compose volume mount, (c) read the OpenClaw docs directly.
2. **Apply Grafana wordmark** to remaining 5 dashboards (2 min each, manual)
3. **Set Slack channel icons** (manual via workspace UI, 90 sec per branding checklist)

### Post-demo, high priority

4. **Daily Log Capture & 14-day Rolling Baseline** (3-5 day build) — would have
   caught the April 8 AH3880 firmware regression on the first post-update
   scan. See `docs/DAILY_LOG_CAPTURE_VISION.md`. Build order: cron script →
   firmware_changes table → regression detector → dual-model comparison →
   backfill. HIGH PRIORITY.
5. **weekly_train.py denial reason ingestion gap** — `train_comprehensive.py`
   reads denial reasons but `weekly_train.py` does not. Fix before next
   Sunday training.
6. **Auradine firmware rollback** — waiting on vendor reply. Roll back .55
   first, observe 24h, then .28.

### Pre-Mac mini (by May 5)

7. **OpenClaw `block_actions` handler** — forward button clicks to local
   approval API via Socket Mode
8. **`mg_` action_id prefix** in `api/slack_block_kit.py` so OpenClaw can
   identify Mining Guardian buttons
9. **Delete `api/slack_actions_handler.py`** (requires public ingress)
10. **CORS audit** — `grep -rn 'fieslerfamily'` and resolve every hit
11. **Customer installer wizard** — update and execute `installer/DEPLOYMENT.md`
    on `installer-build` branch

### Post-demo, medium priority

12. **Open Log Uploader** (2-4 week build) — any-vendor any-format ingestion
    engine. See `docs/OPEN_LOG_UPLOADER_VISION.md`. 4 phases, 10 open design
    questions to resolve first.
13. ~~**Intelligence catalog Phase 1**~~ — **COMPLETED April 13, 2026.**
    PostgreSQL 16 deployed on ROBS-PC in Docker. 90-table schema (V1+V2+V3).
    313 Bitcoin SHA-256 miner models seeded. Deep research enrichment applied
    to 211 models. See `docs/DATABASE_STATUS.md`.
13a. **Intelligence catalog enrichment** — ongoing. PSU data, hashboard details,
    control board specs, chip data, source table population, firmware/ops/repair
    schema tables. See `intelligence-catalog/research/MINER_CATALOG_RESEARCH_NOTES.md`.
14. **Monthly federation refinement pipeline** — add dual-pass refinement
    (Claude + local LLM) to `combine_knowledge.py` for higher-quality master
    knowledge synthesis.

### Long-term / gated

15. **Repair shop data ingestion** — 1M+ data points from James Scaggs/ACS,
    ingestion worker pool, failure signature library. Blocked on dataset.
16. **Container monitoring integration** — BiXBiT container system mapped
    in `docs/CONTAINER_MONITORING.md`, waiting for live access grant.
17. **Multi-site federated deployment** — scale beyond USA 188 to additional
    customer sites.
18. **Grafana alerting** — replaces Slack-based alerting over time.

## 9. The Morning Kickoff Ritual

Every Claude session for this project starts with this exact sequence. See the
full version in `CLAUDE.md` under "Session Kickoff Protocol."

1. Read `CLAUDE.md` (binding rules)
2. Read `docs/VISION.md` (this file)
3. Read `README.md` (current architecture)
4. Read `AI_ROADMAP.md` (feature status + deadlines)
5. Read most recent `docs/RESUME_HERE_*` or `HANDOFF_*` note
6. Run `git status`, `git log --oneline -20`, `git branch -a`
7. Come back with a 5-section report, no questions until it's delivered

## 10. What This Product Is NOT

- NOT a pool management system (out of scope, security policy)
- NOT a miner settings manager (out of scope, security policy)
- NOT a cloud-hosted SaaS (it's a local appliance)
- NOT a hardened bunker (open and useful by default, tightenable by choice)
- NOT a home lab (scope discipline — Mining Guardian + OpenClaw + what they need, nothing else)
- NOT dependent on external AI services for daily operation (Claude API is
  weekly-only; Qwen 32B runs locally)
- NOT dependent on Slack being available (Slack is a notification layer, not
  a control plane)

---

*This document exists so that no Claude session ever again asks "what is the
vision for Mining Guardian?" The answer is above. Read it first.
Last updated April 13, 2026.*
