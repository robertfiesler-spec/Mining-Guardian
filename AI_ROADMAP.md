# Mining Guardian — AI Learning Roadmap

## Path to Autonomous Operation at Customer Sites

**Branch:** `main`
**Status:** Day before customer Mac Mini install (2026-04-30). All R&D phases complete; the product ships as a signed-and-notarized `.pkg` installer that stands up the full stack on a single Mac Mini.
**Rule:** Before building anything, examine every available data point. No unused signals. No proposing alternatives to plans already in the docs.

> 📘 This document is the forward-looking status tracker. For the canonical product vision read `docs/VISION.md` first, then `README.md`. For binding rules read `CLAUDE.md`. For the open work list read `docs/MG_UNIFIED_TODO_LIST.md`.

---

## Current Mode

**FULL-DAY AUTONOMOUS** — Active 24/7
Overnight automation runs 8pm–6am. LOW-risk actions execute without approval. Max auto-restarts: 2 per window. Miners with 3+ FAILURE outcomes are permanently blocked from overnight auto-restart until human review.

**Scan cadence:** 1 scan per hour (`scan_interval_seconds: 3600`, `slack_interval_seconds: 3600`). Matches Slack post throttle — one 🧠 AI analysis post to `#mg-ai-reports` per scan.

**Stack:** Postgres 16 (`mining-guardian-db` container), Ollama natively on Mac Mini (RAM-detected model per D-13), Grafana, Prometheus, daemon under `launchd`. Slack Socket Mode is the only inbound surface; there is no public ingress.

---

## 8 AI Features — Current Status

### Feature 1: Outcome Feedback Loop ✅ LIVE
**File:** `ai/outcome_checker.py`
**How it works:** After every scan, checks restarts without outcomes. SUCCESS if hashrate returns to ≥80% rated within 4 scans and stays there for 2 consecutive scans. PARTIAL if 50-80%. FAILURE if no recovery within 4 scans. Writes back to `miner_restarts.outcome` and updates per-miner fingerprint in `knowledge.json`.

### Feature 2: Confidence Scoring ✅ LIVE
**File:** `ai/confidence_scorer.py`
**How it works:** Blends per-miner success rate (weight 0.60) + fleet-wide success rate (0.25) + stability score (0.15) + fingerprint confidence modifier (±15 points). Gates: ≥80 = AUTO, 50-79 = ASK, <50 = HOLD.

### Feature 3: Denial Reason Capture ✅ LIVE
**Files:** `api/slack_approval_listener.py` + `ai/llm_scan_hook.py`
**How it works:** When the operator denies a recommendation, MG asks "Why?" Reason captured and stored in the audit trail. Reasons feed into Sunday Claude training via `train_cohort.py` for rule refinement.

### Feature 4: Miner Fingerprinting v2 ✅ LIVE
**File:** `ai/fingerprint_builder.py`
**Data used:** restart outcomes, hashrate stability, temps, per-board voltage/freq/HW errors, pool rejection rate, AMS alert counts, chip bin/PCB/PSU, uptime resets, chain detach events, PDU power variance. Produces a confidence modifier (-0.5 to +0.5) that adjusts action confidence per-miner.

### Feature 5: HVAC/Environment Correlation ✅ LIVE
**File:** `ai/hvac_correlator.py`
**How it works:** Calculates facility stress score 0-100 from supply water temp, delta-T, differential pressure, pump VFD %, pump fault, leak alarm. When N+ miners flag simultaneously AND facility stress > 26, logs a `facility_event` to `knowledge.json`. Slack alerts distinguish "Facility Alert" from "Miner Alert."

### Feature 6: Pre-Failure Prediction v2 ✅ LIVE
**File:** `ai/predictor.py`
**12 signals:** hashrate trend decline, volatility spike, board rate imbalance, chip temp creep, historical pattern match, board voltage drop, board temp elevated, pool rejection spike, AMS alert spike, uptime reset, max temp trend, chain attach/detach events.
**Current state:** Running every scan, storing predictions. Slack action recommendation path tunable via confidence threshold.

### Feature 7: Repair Shop Data Ingestion ⏳ BLOCKED
**Blocked on:** Dataset from James Scaggs / Advanced Crypto Services. 1M+ historical data points expected. Will feed into the Mining Intelligence Catalog (`intelligence-catalog/`) on the Mac Mini Postgres instance.

### Feature 8: Action Diversity ✅ LIVE
**File:** `ai/action_diversity.py`
**Actions beyond RESTART/PDU_CYCLE:** POWER_PROFILE_DOWN (≥75 confidence), POWER_PROFILE_UP (≥80, recovery-only), ECO_MODE_FLEET (≥80), POOL_FAILOVER (≥85). All confidence-gated and data-driven.

---

## The Mining Intelligence Catalog

The catalog is the long-term moat. It lives at `intelligence-catalog/` in the repo and is loaded into the operational Postgres database on the Mac Mini.

**What it contains:**

- **Seed dataset:** 321 Bitcoin SHA-256 miners across all major manufacturers (Bitmain, MicroBT, Canaan, Auradine, Bitdeer, etc.) at `intelligence-catalog/seed-data/all_bitcoin_sha256_miners.csv`.
- **Two-tier model resolver:** Tier-1 (`hardware.model_aliases`, 12,852 unambiguous 1:1 mappings — slugs, parenthetical qualifiers, V-codes V10-V100/VE30-VE80/VK10-VK30, retailer SKUs) + Tier-2 (`mg.model_family_aliases`, 1,494 hashrate-disambiguated families with `candidate_model_ids UUID[]` + `candidate_hashrates_ths NUMERIC[]`). Resolver picks nearest hashrate bin (no tolerance), ties break to lower-rated variant.
- **Fallback:** `mg.unresolved_models` — manual GUI triage queue. No guessing.
- **Per-archive tracker:** `mg.import_runs` (ok/failed/partial/skipped) powers SSE progress + `/api/resolver-summary`.
- **Watchers / parsers:** Bitmain, MicroBT, Canaan, Auradine, Bitdeer first-party feeds.
- **Dual-writer + feedback loop:** keeps the operational catalog and the research catalog reconciled.

**Resolver pipeline** (`clients/resolver.py`): normalize → Tier-1 exact → Tier-2 family+hashrate → V-code introspection on both `miner_type` AND `control_board_version` → fallback.

**Intelligence Report API** (`api/intelligence_report_api.py`):

- 226 Bitcoin SHA-256 miner models (9 duplicate slug pairs auto-merged at startup)
- Live data: BTC price (CoinGecko), network difficulty + hashrate (mempool.space), 15-min cache
- Correction rules engine: `intelligence-catalog/data/correction_rules.json`
- Endpoints: `/api/report/models`, `/api/report/search?q=`, `/api/report/{slug}`, `/api/report/{slug}/html`, `/api/report/{slug}/html/render`
- 9 report sections: Hardware Specs, Firmware & Known Issues, Fleet Performance, Profitability & Economics (live), Market Context, Repair & Maintenance, Cooling & Environment, AI Analysis, Recommendations

The catalog is also surfaced in two Grafana dashboards: a model-search/report-rendering dashboard, and a Postgres schema overview.

---

## Two-Tier AI on the Mac Mini

- **Local LLM** (Ollama, native on the Mini): runs on every scan (~4.6s per analysis). Model selected at install time by RAM detection (D-13):
  - 16 GB RAM → `llama3.2:3b` (q4 default)
  - 24 GB RAM or more → `qwen2.5:14b-instruct-q4_K_M`
  - Customer can override the auto-pick before download.
- **Claude API** (Anthropic Sonnet): Sunday weekly training in `train_cohort.py` and ad-hoc deep analysis. Cost ~$1-2/month at current scale. Customer Mac Minis can opt out and run local-LLM-only; Bobby's proof-of-concept mine keeps Claude weekly.

### The Daily Deep Dive (permanent)

`ai/daily_deep_dive.py` — Qwen long-form daily fleet study, per-miner pass + fleet synthesis, no caps. Writes to `knowledge['daily_deep_analyses']`. Sunday Claude weekly training merges those entries via a permanent merge block in `ai/train_cohort.py`. Not scaffolding — never remove. See `docs/DAILY_DEEP_DIVE_DESIGN.md`.

### The 4-Pass Weekly Refinement Chain (permanent)

`ai/refinement_chain.py` — runs after Sunday weekly training to catch and correct errors before output becomes "official" fleet guidance.

1. **Pass 1 (Qwen daily deep dive)** — already in `knowledge["daily_deep_analyses"][0]`
2. **Pass 2 (Claude weekly training)** — already in `knowledge["cross_miner_analysis"][0]`
3. **Pass 3 (Qwen reflection)** — Qwen reads Claude output, identifies errors / disagreements / blind spots
4. **Pass 4 (Claude merged report)** — Claude reads its original output plus Qwen critique, produces final merged report

Pass 4 writes to BOTH `knowledge["weekly_refinement_chain"]` (full chain history) AND `knowledge["cross_miner_analysis"][0]` (overwrites so Sunday merge picks up the corrected version next week). Resume-safe via `--resume-from {3,4}`, WIP checkpointing after each pass, `--smoke-test` ~60s plumbing validation, `--dry-run` plan preview.

First successful run April 10 2026: Qwen caught 4 Claude errors and identified 2 blind spots; Claude accepted all corrections.

---

## Operator-Captured Rules (locked into prompts and code)

These exist because the operator caught a wrong LLM diagnosis once; the rule is now permanent.

- **20-minute post-restart grace period.** After any restart (manual OR overnight auto), suppress the miner from action recommendations for 20 minutes. Wait for `minerStatus = 0` (mining) before evaluating hashrate or recommending next steps.
- **Liquid-cooled fleet temperature.** Chip temps 67-73°C are NORMAL. Action threshold is ≥84°C. There is NO yellow tier — the previous "76°C yellow / 86°C red" rule was wrong and has been removed.
- **HVAC delta-T.** Both HVAC systems are correct. Low delta-T is intentional in cooler months. Do not recommend HVAC investigation based on delta-T alone.
- **Dual HVAC routing.** Warehouse HVAC (192.168.188.235) serves Hydros / S21 Immersion / AH3880. S19J Pro Container HVAC (192.168.189.235) serves S19J Pros only. Routing rule: model starts with "S19JPro" → s19jpro HVAC, otherwise → warehouse HVAC.
- **S19J Pro CT fans manual at 100%.** No VFD feedback. NOT a fault.
- **S19J Pro overheating.** When ≥84°C, try ONE restart with log capture; if still hot, mark as aging and let it run. The `s19jpro_overheat_tracking` table tracks which miners have had their attempt.
- **Dead S19JPro boards suppressed after ticket.** Do not re-raise.
- **Firmware regression diagnosis.** When N+ miners of the same model show identical fault patterns within hours of a firmware update, prefer "firmware regression" over individual hardware failure. Captured from the April 8 AH3880 case (two miners showing PSU IOUT 0x02 trips, DVFS clipping, stratum panics within hours of the same firmware update; both LLMs initially diagnosed "Replace PSU" at HIGH confidence; both were wrong; the firmware was). Now baked into all LLM prompts.

The full canonical list is in `docs/OPERATOR_RULES.md`.

---

## What Got Built (Cumulative Reference)

### Catalog and Field Intelligence

- ✅ Mining Intelligence Catalog — 10 schemas (knowledge, hardware, firmware, ops, market, repair, pool, facility, regulatory, seed), 165+ tables, 1,712+ columns, 320+ indexes, 115+ triggers
- ✅ Field Intelligence Pipeline Layer 2 — Tier-1 + Tier-2 resolver (12,852 + 1,494 aliases), per-archive error isolation, sha256 dedup, SSE progress
- ✅ v3.3 import tool — `POST /api/import-files-stream`, `GET /api/resolver-summary`, `GET /api/unresolved-sample`, `POST /api/cancel-batch`
- ✅ Intelligence Report API (port 8590) — 226 models, live BTC + difficulty data, correction rules engine, 9-section HTML reports rendered via iframe
- ✅ Grafana dashboards — Intelligence Report dashboard (text search + dropdown + report iframe), Intelligence Catalog dashboard (Postgres schema overview), six operational dashboards
- ✅ 277 catalog tests passing

### Operational Hardening (full code review — 53 findings across 35K lines)

- ✅ Phase 1 (commit `88b5b08`): 6 CRITICAL fixes — silently broken predictions (NameError), board escalation crash (undefined `issue`), catalog auth header (Bearer→X-API-Key), fleet synthesis crash (undefined `hvac_system`), SQL syntax error in pool_readings, Auradine missing `import os`
- ✅ Phase 2 (commit `dda6bd0`): approval API transaction safety + case normalization, SlackNotifier.send_scan DB wiring for ticket suppression, AUTHORIZED_SLACK_USER_IDS enforcement, LLM analyzer correct host/model defaults
- ✅ Phase 3: knowledge.json file locking via `core/file_lock.py` (6 writers updated), predictor DB connection leaks closed (try/finally), AMS token lock wired in `_ensure_token()`, `/metrics` endpoint cached (25s TTL), AV2 Plant credentials moved to env vars, Slack handler bounded `OrderedDict` (10K cap), atomic writes in `fingerprint_builder.py` + `hvac_correlator.py`
- ✅ Auth bypass in `approval_api.py` — now fails closed
- ✅ Atomic writes in `outcome_checker.py`
- ✅ Dead code removed (orphaned method bodies)
- ✅ `api/slack_listener.py` deleted (violated Socket Mode rule)
- ✅ Postgres migration (2026-04-23 → 2026-04-24) — operational store moved from SQLite `guardian.db` to Postgres 16 container `mining-guardian-db`, migration gated by `MG_ALLOW_MIGRATION=1` (D-6)
- ✅ Bulk import tooling (PR #25) — 127/136 archives imported live; tooling at `mg_import_tool/`

### Daily Log Capture & 14-Day Rolling Baseline

- ✅ Daily baseline log collection — parallel 15-worker, 10-min cap per miner (commits `95676b6`, `da1edbd`, `e5b9f5c`)
- ✅ Daily deep dive LLM (`ai/daily_deep_dive.py`, 953 lines, Qwen full-fleet study, no caps)
- ✅ Weekly Claude training merges restart comparisons (commit `e90c2be`) — fixed the silent-skip bug where comparisons were written to `known_issues` but trainer read `llm_scan_analyses`
- ✅ `daily_deep_analyses` permanent merge into weekly Claude training
- ✅ Cron entries shipped — see `docs/CRON_SCHEDULE.md` for the canonical list

### AI Pipeline Foundations

- ✅ Cohort-based weekly training (`train_cohort.py`) — scale-first, replaces per-miner blasting
- ✅ Dual-model pre/post restart log comparison (`ai/claude_log_comparison.py`)
- ✅ Federated knowledge system (`ai/combine_knowledge.py`) for multi-site merges
- ✅ Backup system — rolling DB + daily snapshots
- ✅ HVAC/BAS integration — Distech Eclypse supply / return / pressure / pump data in Slack and Grafana
- ✅ Real Auradine API client (`clients/auradine_client.py`, 602 lines)
- ✅ 2-restart escalation — auto-ticket after 2 failed restarts
- ✅ Overnight automation — autonomous action engine 8pm–6am
- ✅ Quiet hours — no Slack noise 10pm–5am
- ✅ 1-hour approval window — unanswered approvals auto-expire, re-raised fresh next scan
- ✅ Dead board lifecycle — detect → restart → ticket → suppress
- ✅ Security hardening — CORS, auth, credential removal, double-actuation bug fixed
- ✅ 6-channel Slack routing architecture — `#mining-guardian`, `-alerts`, `mg-scans`, `mg-ai-reports`, `mg-approvals`, `mg-logs`
- ✅ `/query/*` read-only endpoints in `dashboard_api.py`

### 48-Hour Live Test (April 6–8 2026, historical reference)

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

The April 8 AH3880 firmware regression case (above) was the most important learning of the test and produced the firmware-regression operator rule plus the Daily Log Capture / Daily Deep Dive build.

---

## Build Queue (Current Priority Order)

### P0 — This week (post-install hardening)

1. **Customer Mac Mini install** — ship the `.pkg` and walk the operator through preflight + install + first-run verification. Runbook: `docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md`. Rebuild runbook: `docs/RUNBOOK_PKG_REBUILD.md`. Distribution runbook: `docs/RUNBOOK_DISTRIBUTION_v1.0.0.md`.
2. **Repo polish day** (2026-04-29) — full doc sweep, PR triage of 23 open PRs and 43 stale branches, security sweep (secrets / hardcoded creds / debug=True / 0.0.0.0 binds), code cleanup, test verification, preflight, tag `v1.0.0-install-ready`. Tracking: `docs/REPO_DOC_SWEEP_2026-04-29.md`.
3. **Grafana 321-miner dropdown refresh** (deferred) — Intelligence Report dropdown looks stale relative to the catalog count of 321 miners. Investigate and refresh.

### P1 — Post-install (first weeks)

4. **Customer doc refresh** — final pass on `docs/customer/MiningGuardian_Brochure.pdf`, `MiningGuardian_Program_Instructions.pdf`, `MiningGuardian_Setup_Manual.pdf`. Blocked on real install screenshots.
5. **Web GUI operator console** — `docs/WEB_GUI_OPERATOR_CONSOLE.md`. Live now via approval API mode selector (PR #88) and operator-controlled schedules (PR #90).
6. **PDU password rotation** — change from defaults on PDUs `.15` and `.16`.
7. **Auradine firmware rollback** — waiting on vendor. Roll back `.55` first, observe 24h, then `.28`.

### P2 — Catalog growth

8. **Continue catalog expansion** — finish manufacturer review across all 226 models, surface any remaining unresolved aliases through the GUI triage queue.
9. **Qwen AI analysis paragraphs injected into Intelligence Reports** — currently catalog-only; Qwen-generated analysis paragraphs pending wiring once Qwen is reachable from the report API.
10. **PDF download button within the Grafana Intelligence Report dashboard.**

### P3 — Federation and multi-site

11. **Monthly federation refinement pipeline** — add dual-pass refinement (Claude + local LLM) to `combine_knowledge.py` for higher-quality `master_knowledge.json`.
12. **Multi-site federation at scale** — sync master knowledge across multiple customer Mac Minis monthly via USB.
13. **Knowledge Score trending** — day-over-day improvement visible in AI dashboard (accumulates over weeks).
14. **Grafana alerting** — replaces Slack-based alerting over time for passive notifications.

### P4 — Open Log Uploader and adjacent capabilities

15. **Open Log Uploader** (2-4 week build) — see `docs/OPEN_LOG_UPLOADER_VISION.md`. Any-vendor any-format ingestion engine for repair shop bulk drops.
16. **Auradine AH3880 direct API integration** — port 8443, standby-before-PDU-cut rule, see `docs/AURADINE_API.md`.
17. **Container monitoring integration** — BiXBiT container system mapped in `docs/CONTAINER_MONITORING.md`. Blocked on live access grant.

### P5 — Gated on external inputs

18. **Repair shop data ingestion (Feature 7)** — 1M+ historical data points from James Scaggs / Advanced Crypto Services. Blocked on dataset delivery.

### P6 — Long-term

19. **NAS migration for the catalog** — UGREEN NASync iDX6011 Pro path. `pg_dump` → file copy → `pg_restore`. ~20 min for 60 GB. Optional and customer-specific.

---

## Outbound Endpoints (the only network the Mini needs)

The Mac Mini has no public ingress. The operational loop reaches out to these and nothing else:

| Endpoint | Why | Notes |
|---|---|---|
| AMS API (`api-staging.dev.bixbit.io` or production AMS) | All miner commands | Outbound HTTPS |
| Slack Socket Mode | Conversational AI + button event delivery | Outbound websocket |
| Slack outbound API (`slack.com`) | `chat_postMessage`, etc. | Outbound HTTPS |
| Anthropic Claude API | Weekly training only (Sundays) | Proof-of-concept site only; production customer sites can opt out |
| CoinGecko + mempool.space | Live BTC price + network difficulty/hashrate | 15-min cache |
| Open-Meteo | Weather data | Free, no key |
| NTP | System clock | Standard |
| Tailscale | Optional support access | Customer decision |

---

## Technical Notes

- HVAC/BAS integration is one-off for Bobby's facility — NOT in customer deployment templates by default.
- S19JPro dead board repairs explicitly crossed off — do not raise.
- Pool failover requires `backup_pool_url` in `config.json` — not currently set on the proof-of-concept site.
- AH3880 board voltage 0.29V is Auradine firmware format, NOT a fault — `predictor.py` suppresses voltage signal for Auradine miners.
- All denial reasons feed into Sunday training via `train_cohort.py` → fleet synthesis pass.
- `train_cohort.py` is the scale-first weekly trainer — it's the reference implementation for the entire production architecture. Same code path runs on customer Mac Minis with Qwen instead of Claude.
- **AMS false-offline is an AMS upstream bug, not a Guardian bug.** AMS periodically reports miners as offline when they're actually online. Guardian handles this correctly with the direct-TCP false-offline detection path in `_analyze_miner` (flags as `AMS_SYNC` for up to 10 consecutive scans, then suppresses).
- The Mini is the sole product host — Postgres catalog, app, Ollama, Grafana, log collection all run on one machine. No secondary host, no remote LLM, no public dashboards.

---

*Last updated: April 29 2026 — repo doc sweep day, day before customer Mac Mini install. Roadmap collapsed into the post-install era: removed VPS / OpenClaw / Cloudflare migration backlog (decommissioned on cutover), removed `installer-build` legacy backlog (the live `.pkg` is what ships), removed deprecated `intelligence/` references in favor of the live `intelligence-catalog/` directory, refreshed build queue around install + repo polish + post-install hardening. See `CLAUDE.md` for binding rules, `docs/VISION.md` for the canonical plan, `README.md` for current architecture, and `docs/MG_UNIFIED_TODO_LIST.md` for the canonical open-work list.*
