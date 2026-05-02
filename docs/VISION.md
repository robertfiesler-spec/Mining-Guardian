# Mining Guardian — Vision & Canonical Plan

**Last synthesized:** 2026-04-29 (post 2026-04-29 repo doc sweep, on the eve of the 2026-04-30 Mac Mini install)
**Status:** Living document — update when any source doc changes
**Purpose:** Single source of truth for Mining Guardian's vision, architecture, and roadmap. Every new Claude session reads this FIRST after `CLAUDE.md`.

This document synthesizes and consolidates:
- `README.md` (architecture)
- `AI_ROADMAP.md` (feature status)
- `docs/CAPABILITIES.md` (what it does)
- `docs/DECISIONS.md` (locked decisions, especially D-7 through D-14)
- `docs/INTELLIGENCE_CATALOG_STATUS.md` (catalog wiring)
- `docs/OPEN_LOG_UPLOADER_VISION.md` (any-vendor ingestion vision)
- `intelligence-catalog/seed-data/all_bitcoin_sha256_miners.csv` (the SHA-256 seed — 320 miners at v1.0.2, growing)
- `installer/macos-pkg/README.md` (the customer installer .pkg)

If any of the above conflict with this doc, this doc is wrong — update it.

---

## 1. The One-Paragraph Version

Mining Guardian is an AI-powered autonomous fleet monitoring and remediation system for Bitcoin SHA-256 mining facilities. It ships as a single Mac Mini at each customer site running PostgreSQL 16 (operational + reference DBs colocated), Ollama (model selected at install time per available RAM — `llama3.2:3b` on 16 GB, `qwen2.5:14b-instruct-q4_K_M` on 24 GB+), and the Mining Guardian Python stack under launchd. It scans the fleet on the operator's schedule (default hourly) via the BiXBiT AMS API, diagnoses problems with a two-tier LLM (local Ollama for per-scan analysis + Claude Sonnet for opt-in weekly deep training), manages the full action lifecycle (detection → operator approval via Slack or the Web GUI Operator Console → execution → outcome verification → ticket creation → permanent suppression), and continuously learns by writing every operational outcome straight into the Mining Intelligence Catalog (D-14 live-reference architecture — no scheduled refresh, every read returns the catalog as it was at that moment). Each customer deployment can export catalog deltas for federated learning across sites, so every fleet makes every other fleet smarter over time. Approval and conversational control flow through Slack (Socket Mode, outbound-only) and the loopback-only Web GUI; remote operator access is via Tailscale to the Mini, with the data plane staying on the Mini.

## 2. The Vision Anchors

These are the immutable rules. They constrain every design decision.

**1. The catalog is sacred.** The Mining Intelligence Catalog (`intelligence-catalog/`) is the single source of truth for everything known about Bitcoin SHA-256 ASIC miners — manufacturer specs, firmware quirks, failure patterns, war stories, repair-shop intelligence. The 320-miner SHA-256 seed (current at v1.0.2) is the floor; we only grow it. Any change that drops, divorces, or duplicates catalog data is the wrong change.

**2. The LLM IS the product.** The main feature of Mining Guardian is the LLM getting smarter over time. Every scan feeds it. Every denial refines it. Every operational outcome flows back into the catalog within ~100 ms (D-14). Any solution that removes the LLM from the operator's decision flow is the wrong solution.

**3. The Mac Mini is THE product.** The original VPS, Cloudflare tunnels, and `fieslerfamily.com` domains were R&D scaffolding (decommissioned for MG; only Bobby's facility-side dev infra remains). The real product is a single Mac Mini at the customer site under launchd with only outbound internet — Postgres on the Mini, Ollama on the Mini, the catalog on the Mini, the Web GUI on the Mini's loopback.

**4. Scale-first, always.** Designed for 5,000+ miners per site, not 58. The cohort-based training architecture (`ai/train_cohort.py`) is the reference: miners are grouped by hardware identity, analyzed as cohorts, with per-miner deep dives only for outliers. Cohort count grows sub-linearly with fleet size, so Claude API cost stays flat across mine sizes and local LLM workload stays manageable.

**5. Federated learning across customer sites.** Each customer Mac Mini can export catalog deltas. Bobby merges site deltas (optionally with refinement passes through Claude + local LLM) into a master catalog snapshot, which is pushed back to every site. No public internet required for the sync — USB or manual transfer works. Every customer's fleet makes every other customer's fleet smarter.

**6. Bitcoin SHA-256 only.** No altcoins, no GPU mining, no FPGA. The catalog scope, the parsers, the failure libraries — all SHA-256 ASIC.

**7. Local-first, always.** No cloud-only dependencies. Claude API is opt-in and weekly-only. The Mini is fully functional without internet for the operational loop; only Slack notifications and the optional Claude training cycle require outbound connectivity.

## 3. Target Architecture (the live shape as of the 2026-04-30 install)

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
│  │              (launchd-managed services)            │       │
│  │                                                    │       │
│  │  ┌──────────────┐   ┌──────────────────────────┐  │       │
│  │  │ scan daemon  │◄──┤ approval_api (8686, lo)  │  │       │
│  │  │ core/mg.py   │   │ + Web GUI Operator       │  │       │
│  │  │              │   │   Console                │  │       │
│  │  └──────┬───────┘   └──────────────────────────┘  │       │
│  │         │                                          │       │
│  │  ┌──────┴───────────────────────────────────────┐ │       │
│  │  │  PostgreSQL 16 on the Mini                    │ │       │
│  │  │   - mining_guardian (operational)             │ │       │
│  │  │   - intelligence_catalog (reference)          │ │       │
│  │  │   D-14: live cross-reference, no TTL cache    │ │       │
│  │  └────────────────────────────────────────────────┘│       │
│  │                                                    │       │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────┐  │       │
│  │  │ prometheus  │  │   grafana   │  │ ollama   │  │       │
│  │  │             │  │             │  │ (local)  │  │       │
│  │  └─────────────┘  └─────────────┘  └──────────┘  │       │
│  │                                                    │       │
│  │  Dashboard (:8585 lo)   Approval API (:8686 lo)   │       │
│  └──────────────────────┬─────────────────────────────┘       │
│                         │                                    │
│  Operator access:       │                                    │
│    Web GUI on the Mini's loopback                            │
│    + Tailscale to the Mini for remote ops                    │
└─────────────────────────┼────────────────────────────────────┘
                          │
           OUTBOUND ONLY (no public ingress):
               ├── BiXBiT AMS (customer's AMS host)
               ├── slack.com (Socket Mode + chat.postMessage)
               ├── api.anthropic.com (opt-in weekly training only)
               ├── open-meteo.com (weather, free, no key)
               └── Tailscale (operator support access only)
```

## 4. The Learning Loop (the main feature)

This is the single most important mental model for this project.

### 4a. Per-scan loop (operator schedule, default hourly)

1. **Scan** — Mining Guardian polls AMS via WebSocket, gets all miner state.
2. **Verify** — false-offline detection via direct TCP (port 4028 / 8443).
3. **Evaluate** — `_analyze_miner` runs the three-tier hashrate resolver + thermal check (≥84°C only) + dead-board check + offline decision tree, **consulting the catalog** for `hardware.miner_models` specs, `ops.failure_patterns`, `hardware.model_known_issues`, and `market.war_stories` per D-14.
4. **Store** — scan results written to the operational Postgres (`mining_guardian` DB).
5. **Feed the LLM** — local Ollama receives the scan, analyzes it, writes findings; the analysis is logged to `public.llm_analysis`.
6. **Run the AI features in sequence** in the main `loop()`:
   - Outcome checker (evaluate previous restarts)
   - HVAC correlator (facility stress score)
   - Predictor (12 pre-failure signals)
   - Action diversity (POWER_PROFILE_DOWN, ECO_MODE, POOL_FAILOVER, etc.)
   - Local LLM scan hook (background thread)
7. **Post to Slack** + Web GUI — scan summary + crystal-ball recommendations with approve/deny workflow. Automation mode (`full_auto` / `semi_auto` / `manual`) gates which actions execute without approval.
8. **Operator-defined overnight window** (default 10 p.m.–6 a.m.) — LOW-risk actions auto-execute when automation mode allows; 3+ FAILURE outcomes block auto-restart permanently.
9. **D-14 feedback** — every operational write fires `NOTIFY catalog_feedback`. The `feedback_loop_daemon` LISTENs and folds the outcome into the catalog within ~100 ms.

### 4b. Per-action learning (every time an operator approves/denies)

1. **APPROVE** → action executes via AMS → outcome checker evaluates success over the next 2–3 scans → SUCCESS / FAILURE / PARTIAL label written to `miner_restarts` → fired into the catalog (`ops.failure_patterns`, `hardware.model_known_issues`) via the D-14 NOTIFY → confidence scorer is updated.
2. **DENY** → two-step flow: operator replies DENY → Mining Guardian asks "Why?" → operator's reason is captured in `action_audit_log` → local LLM (`ai/llm_scan_hook.run_denial_processing_llm`) processes the reason into an operational rule candidate → the optional Sunday Claude training validates and refines the rule → rule gets baked into future scan-time LLM prompts.

### 4c. Weekly training (Sunday 3 a.m., opt-in)

`ai/train_cohort.py` — the scale-first weekly trainer (replaces `train_comprehensive.py`, which hit rate limits at miner #3):

1. **Cohort pass** — group all miners by `(model, firmware, chip_bin, pcb_version, cooling)`. At 58 miners this produces ~10–15 cohorts. One Claude call per cohort with per-cohort aggregates, restart outcome history, top problems, and filtered local LLM observations.
2. **Outlier pass** — miners >2σ below their cohort's hashrate mean or >2σ above cohort's temp mean get individual deep analysis. Capped at 30 outliers per run.
3. **Fleet synthesis pass** — one final Claude call with all cohort results, all outlier results, all local LLM scan analyses from the past week, operator rules, and cross-miner SQL correlations. Produces the weekly executive report, fleet-wide patterns, predictive warnings, and refined operator rules.
4. **Storage** — every cohort/outlier/fleet result is written into the catalog (`market.war_stories`, `ops.failure_patterns`) and into `public.llm_analysis` on the operational side.

The same code path runs on customer Mac Minis using local Ollama instead of Claude when the customer has opted out of cloud training. The cohort approach makes the workload manageable at any scale — each Mac Mini runs ~30 cohort analyses per training cycle regardless of whether the fleet is 50 or 5,000 miners.

### 4d. Monthly federation (across customer sites)

1. Each customer Mac Mini runs an export job → produces `site_<id>_catalog_delta.json`.
2. Bobby collects all site files (USB, email, any transfer method).
3. Bobby runs the catalog merge tool — merges all sites weighted by confidence, produces a master catalog snapshot with LLM synthesis.
4. **Refinement passes**: pipe the master through Claude once for cleanup and once through the local LLM for consistency checking before distribution.
5. Master catalog snapshot gets pushed back to every customer site (USB or manual transfer; no internet required).
6. Each site's local LLM uses the master catalog as baseline context in every scan-time prompt.

No public internet is required for any step of this loop. Sneakernet works.

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

**Temp thresholds (LOCKED operator rule):** No yellow tier. 84°C is the only threshold. Below 84°C is normal regardless of cooling type or cohort average.

**PDU access:** S21 Hydro and S21 Imm have AMS PDU outlets. S19J Pros do NOT have PDU outlets in AMS — offline remediation is restart → bad-PSU ticket.

## 6. System Components

### 6a. Core daemon (`core/mining_guardian.py`)

The heart of the system. Contains:

- `AMSClient` — cookie-based JWT auth, WebSocket read path, REST write path
- `PolicyEngine` — rule-based finding evaluation
- `RemediationPlanner` — builds action patches
- `ApprovalInterface` — routes findings to operator (Slack + Web GUI)
- `RemediationCooldown` — prevents action spam
- `WeatherCollector` — Open-Meteo weather
- `SlackNotifier` — channel routing with Block Kit support
- `MiningGuardian` — the main orchestrator with `run_once()` and `loop()`

The `loop()` method runs all AI features in order after each scan and consults the catalog per D-14.

### 6b. AI layer (`ai/`)

| File | Purpose |
|---|---|
| `train_cohort.py` | Scale-first weekly Claude training (opt-in main weekly entry point) |
| `weekly_train.py` | Cron entry — calls `train_cohort` + `fingerprint_builder` + `hvac_correlator` + `predictor` |
| `catalog_context.py` | Catalog client used by scan-time and AI paths (per D-14: no client-side cache, fail-loud) |
| `daily_deep_dive.py` | The April 8 case-study path that consults the catalog and refines weekly |
| `local_llm_analyzer.py` | Runs the local Ollama model after every scan; processes denials into rules |
| `outcome_checker.py` | Restart outcome labeling (psycopg-native rewrite per D-3) |
| `confidence_scorer.py` | Per-action confidence scoring |
| `fingerprint_builder.py` | Per-miner behavioral fingerprints |
| `hvac_correlator.py` | HVAC/environment correlation |
| `predictor.py` | 12-signal pre-failure prediction |
| `action_diversity.py` | POWER_PROFILE_DOWN/UP, ECO_MODE, POOL_FAILOVER |

### 6c. API layer (`approval_api/`, `api/`)

| Component | Port | Purpose |
|---|---|---|
| `approval_api` (FastAPI) | 8686 (lo) | Approve/deny + Web GUI Operator Console + automation-mode selector + operator-controlled schedules (PR #88, PR #90) |
| `dashboard_api.py` | 8585 (lo) | REST + Prometheus `/metrics` + Grafana iframes |
| `slack_command_handler.py` | — | Conversational fleet intelligence bot |
| `slack_block_kit.py` | — | Block Kit message builder |
| `ams_alert_listener.py` | — | Listens for AMS alerts, queues urgent actions |

All HTTP surfaces bind to `127.0.0.1`. Remote access is via Tailscale to the Mini.

### 6d. Clients (`clients/`)

| File | Purpose |
|---|---|
| `auradine_client.py` | Teraflux AH3880 direct API (JWT auth, port 8443, standby-before-power-cut rule) |
| `container_monitor.py` | BiXBiT container infrastructure monitor (waiting for live access) |
| `hvac_client.py` | Distech Eclypse BAS (facility-specific, NOT in deployment templates) |
| `immersion_client.py` | Fog Hashing Elite 1 immersion tank |
| `pdu_client.py` | BiXBiT 2U+PDU client |

### 6e. Database — Postgres 16 on the Mini

Two databases in one Postgres instance, per D-14:

- **`mining_guardian` (operational):** scans, miner_readings, chain_readings, pool_readings, action_audit_log, miner_restarts, llm_analysis, hvac_readings, weather_readings, pending_approvals, known_dead_boards, system_settings, system_schedules.
- **`intelligence_catalog` (reference):** `hardware.miner_models`, `hardware.manufacturers`, `hardware.model_known_issues`, `ops.failure_patterns`, `market.war_stories`, `knowledge.field_registry`, `knowledge.sources`. Seeded with the 320-miner SHA-256 catalog at v1.0.2 install time (the catalog grows post-install as models are added).

## 7. Deadlines & Install

### 2026-04-30 — Mac Mini install (live)

- Operator runs the installer .pkg from PR #79 on a fresh Mac
- Postgres 16 + the 5 catalog migrations (001–005) + Ollama + launchd plists for all services
- Catalog seed loads (320 SHA-256 miners at v1.0.2; grows over time)
- Smoke tests: scan loop, AMS reach, all services, Slack ping, Grafana datasource, Ollama smoke
- If green: tag `v1.0.0`, write `docs/INSTALL_REPORT_2026-04-30.md`
- If red: pre-defined rollback (re-run installer next day)

### Post-install (May 2026)

- Customer-facing doc refresh once we have post-install screenshots (Setup Manual, Program Instructions, Brochure)
- Operator-controlled schedules (§10.7) tuning based on real-world cadence
- Web GUI Operator Console (§10.1, §10.2) iteration

## 8. Build Queue (in priority order, post-install)

1. Address the Grafana miner-dropdown so it queries `hardware.miner_models` live instead of a hardcoded list (the catalog grows over time — 320 at v1.0.2) (deferred from earlier — verify dashboard reflects the live `hardware.miner_models` count (320 at v1.0.2; the dashboard must follow the table, not a static number)).
2. Customer-facing doc refresh (Setup Manual, Program Instructions, Brochure §10.4 / §10.5 / §10.6 — blocked on screenshots from the live install).
3. Repair-shop data ingestion (gated on the dataset arrival from James / ACS).
4. Container monitoring activation (gated on BiXBiT API access).
5. Open Log Uploader vision (`docs/OPEN_LOG_UPLOADER_VISION.md`) — multi-vendor log ingestion, post-MVP work.
6. Federated catalog tooling (catalog merge tool + refinement passes).
7. Grafana alerting that complements Slack notifications.

## 9. The Morning Kickoff Ritual

Every Claude session for this project starts with the exact sequence in `CLAUDE.md` under "Session Kickoff Protocol." The ordered reading list is:

1. `CLAUDE.md` (binding rules)
2. `docs/VISION.md` (this file)
3. `docs/DECISIONS.md` (locked decisions)
4. `README.md` (current architecture)
5. `AI_ROADMAP.md` (feature status)
6. `docs/ROADMAP_TO_MAC_MINI_2026-05-05.md` (historical install plan, superseded by the 2026-04-30 actual install)
7. `REPAIR_LOG.md` (live regression log)
8. `docs/LATENT_BUGS.md`
9. `docs/MG_UNIFIED_TODO_LIST.md`
10. Most recent `docs/SESSION_LOG_*` (now under `docs/archive/2026-04/`, historical only)
11. Git state
12. Open PRs

## 10. What This Product Is NOT

- NOT a pool-management system (out of scope, security policy)
- NOT a miner-settings manager (out of scope, security policy)
- NOT a cloud-hosted SaaS (it's a local appliance)
- NOT a hardened bunker (open and useful by default, tightenable by choice)
- NOT a home lab (scope discipline — Mining Guardian + the catalog + what they need, nothing else)
- NOT dependent on external AI services for daily operation (Claude API is opt-in and weekly-only; local Ollama runs the operational loop)
- NOT dependent on Slack being available (Slack is a notification layer, not a control plane — the Web GUI Operator Console is the loopback control plane)
- NOT multi-coin or non-SHA-256 (Bitcoin SHA-256 ASIC only)

---

*This document exists so that no Claude session ever again asks "what is the vision for Mining Guardian?" The answer is above. Read it first.*
