# Mining Guardian

Autonomous Bitcoin mining fleet monitoring system. Runs on a Mac Mini at the customer site. Monitors a SHA-256 ASIC fleet, diagnoses problems with a two-tier AI system, and manages the full action lifecycle — detection, approval, execution, ticket creation, and suppression — 24/7.

The system learns continuously. Every hourly scan refines its knowledge base. Weekly cohort training synthesizes everything into fleet-wide patterns. Knowledge score, insight count, and autonomy rate are all visible live in Grafana.

> 📘 **New here?** Read `CLAUDE.md` first (binding rules), then `docs/VISION.md` (canonical plan). The customer-facing install runbook is `DEPLOYMENT_CHECKLIST.md`. The doc audit/sweep ledger is `docs/REPO_DOC_SWEEP_2026-04-29.md`.

---

## What this product is

A self-contained appliance that drops onto a customer's network as a Mac Mini. No cloud, no public ingress, no recurring SaaS bill. Outbound-only. Bitcoin SHA-256 miners only.

**As of 2026-04-29:** the installer (PR #79) builds a signed `.pkg` from the repo. First customer install is tomorrow morning (2026-04-30) at BiXBiT USA, Fort Worth, TX. The catalog of supported miner models lives in Postgres on the same Mac Mini and currently covers **321 SHA-256 miners** across the major manufacturers.

---

## Architecture (Mac Mini era — current)

```
Mac Mini (customer site, on local LAN, on Tailscale)
  ├── Postgres 16                          — catalog DB + runtime state (single source of truth)
  ├── mining-guardian (launchd)            — fleet scanner, every hour
  ├── dashboard-api (launchd :8585)        — REST + Prometheus /metrics + /query/* endpoints
  ├── approval-api (launchd :8686)         — APPROVE/DENY/approve_selected + operator web GUI
  ├── intelligence-report-api (launchd :8590) — Miner Intelligence Report API (321 models)
  ├── overnight-automation (launchd)       — autonomous low-risk actions, schedule-driven
  ├── slack-listener (launchd)             — text-based approval polling
  ├── slack-commands (launchd)             — fleet intelligence chat bot
  ├── ams-alerts (launchd)                 — AMS alert listener
  ├── feedback-loop-daemon (launchd)       — catalog feedback merger
  ├── Prometheus (launchd :9090)           — metrics scraper, 30s interval
  ├── Grafana (launchd :3000)              — operational + intelligence dashboards
  └── Ollama + Qwen2.5 32B (Mac neural cores) — local LLM, every-scan + daily deep dive
```

**No Cloudflare tunnels. No Docker. No public ingress.** Operator accesses the web GUI on the Mac Mini directly (or via Tailscale from elsewhere).

The first deployment uses Anthropic Claude API for *weekly* training only (proof of concept). The production code path runs entirely local — `train_cohort.py` swaps Claude for Qwen 32B on customer Mac Minis with no other code changes.

---

## Two-Tier AI System

| Tier | Model | Hardware | Used For | Cost |
|------|-------|----------|----------|------|
| Local | Qwen 2.5 32B Q4_K_M | Mac Mini (Apple Silicon, neural cores) | Every-scan analysis (~5s) + denial reason processing + daily deep dive | Free |
| Cloud | Claude Sonnet | Anthropic API (first deployment only) | Weekly cohort training + knowledge merges | ~$1–2/mo for the test fleet |

- Fleet knowledge context (HW errors, pool rejections, dead boards, chronic miners) is injected into every LLM prompt via `knowledge_manager.build_context_prompt()`.
- The Claude path does NOT fall back to Qwen during outages — the scan loop never blocks on Claude.
- `model_used` in `llm_analysis` always reflects the actual backend that ran.
- **Future customer sites use Qwen only.** Claude is removed at second-customer install.

---

## Fleet (first customer — BiXBiT USA, Fort Worth, TX)

58 miners total, all liquid-cooled (hydro racks + immersion tank, no air cooling):

| Model | Count | Firmware | Stock TH/s | Max TH/s | Boards |
|-------|-------|----------|-----------|----------|--------|
| Antminer S19J Pro | ~36 | BiXBiT | 104 | 160 | 3 |
| Antminer S19J Pro | 5 | Stock | 104 | — | 3 |
| Antminer S19J Pro (alt AMS code) | 4 | Stock | 104 | — | 3 |
| Teraflux AH3880 | 2 | Auradine FluxOS | 300 (eco) | 600 (turbo) | **2** |
| Antminer S21 EXP Hydro | 2 | BiXBiT | 430 | 506 | 3 |
| Antminer S21 Imm (.22) | 1 | BiXBiT | 208 | 360 | 3 |
| Antminer S21 Imm (.23) | 1 | BiXBiT | 217 | 347 | 3 |

- Board count per model read from `miner_specs.json` — AH3880 correctly treated as 2-board.
- PDUs: orient_RPDU 163 @ `192.168.188.15`, 164 @ `192.168.188.16`.
- S19J Pros have **NO** PDU outlet in AMS — offline remediation is restart → bad PSU ticket.

### Operator rules (LOCKED)

- **Temperature:** 84°C is the only flag threshold. Below 84°C is normal regardless of cohort average. No yellow tier.
- **HVAC delta-T:** Both HVAC systems perform correctly. Low delta-T is intentional and rises with outside temps. Do NOT recommend HVAC investigation based on delta-T.
- **Dual HVAC:** Two cooling systems — warehouse (`192.168.188.235`) for Hydros/S21/AH3880, S19JPro container (`192.168.189.235`) for S19J Pros only. Mining Guardian polls both every hour and assigns each miner to the correct HVAC.
- **Firmware regression:** When N+ miners of the same model show identical fault patterns within hours of a firmware update, prefer the firmware-regression diagnosis over per-miner hardware failure.
- **20-minute post-restart grace period:** After any restart (manual or overnight auto), suppress the miner from action recommendations for 20 minutes.
- **Dead S19JPro boards:** Suppressed after ticket creation. Do not re-raise.

---

## Services (all launchd on Mac Mini)

| Service | Port | Description |
|---------|------|-------------|
| `com.miningguardian.mining-guardian` | — | Scans the fleet every hour, evaluates miners, runs the AI feature pipeline |
| `com.miningguardian.dashboard-api` | 8585 | REST + Prometheus `/metrics` + `/query/*` endpoints |
| `com.miningguardian.approval-api` | 8686 | APPROVE/DENY/approve_selected + operator web GUI (`/ui/`) |
| `com.miningguardian.intelligence-report` | 8590 | Miner Intelligence Report API — 321 models, live BTC/difficulty, correction-rules engine |
| `com.miningguardian.overnight-automation` | — | Autonomous low-risk actions, schedule-driven (window from `system_schedules`) |
| `com.miningguardian.slack-listener` | — | Polls Slack threads for text approvals — interval from `system_schedules` |
| `com.miningguardian.slack-commands` | — | Conversational fleet intelligence bot |
| `com.miningguardian.alerts` | — | AMS alert listener — interval from `system_schedules` |
| `com.miningguardian.feedback-loop-daemon` | — | Catalog feedback merger |
| `com.miningguardian.prometheus` | 9090 | Metrics scraper, 30s interval |
| `com.miningguardian.grafana` | 3000 | Dashboards |

All services are macOS LaunchDaemons. Plists live in `installer/macos-pkg/resources/launchd/`. Launcher wrappers (PATH, Homebrew, env vars) live in `installer/macos-pkg/resources/launchd/launchers/`.

---

## Operator Web GUI (PR #88, §10.1/§10.2)

The approval API serves an operator console at `http://localhost:8686/ui/`:

- **Approvals tab** — review and approve/deny pending actions.
- **Mode tab** — switch automation mode: `MANUAL`, `OVERNIGHT_AUTO`, or `FULL_AUTO`. Mode change requires confirm + writes to `system_settings`.
- **Schedules tab** (PR #90, §10.7) — set time windows, intervals, and DOW chips for every recurring job. Daemons hot-reload on each loop, no service restart needed.

Backed by tables `system_settings` (migration `004`) and `system_schedules` (migration `005`).

### Schedules covered

| Job | Type | Default | Reads from |
|-----|------|---------|-----------|
| Overnight automation window | window (start–end + DOW) | 20:00–06:00, every day | `core/overnight_automation.py` |
| AMS alert poll | interval (seconds) | 30s | `api/ams_alert_listener.py` |
| Slack listener poll | interval (seconds) | 5s | `api/slack_approval_listener.py` |
| Catalog auto-refresh | interval (seconds) | 300s | `api/intelligence_report_api.py` |

If the DB is unreachable the code falls open to in-file defaults that mirror the migration seed exactly. No service ever blocks on the DB.

---

## Postgres + Catalog DB (single source of truth)

One Postgres 16 instance on the Mac Mini hosts both the live runtime state and the catalog. SQLite is no longer used anywhere — the migration completed before the Mac Mini era.

### Migrations (run in order at install)

| File | Purpose |
|------|---------|
| `migrations/001_initial.sql` | Base runtime schema (scans, miner_readings, action_audit_log, etc.) |
| `migrations/002_layer2.sql` | Hardware identity, knowledge tables, fingerprints |
| `migrations/003_c5_notify_triggers.sql` | LISTEN/NOTIFY triggers for live UI updates |
| `migrations/004_system_settings.sql` | `system_settings` (operator mode + read-only flag) |
| `migrations/005_system_schedules.sql` | `system_schedules` (4-row seed for the 4 jobs above) |

### Catalog (`intelligence-catalog/`)

- **`intelligence-catalog/seed-data/all_bitcoin_sha256_miners.csv`** — 321 SHA-256 miners across Bitmain, MicroBT, Canaan, Auradine, Bitdeer, and others.
- **`intelligence-catalog/catalog-api/catalog_api.py`** — Catalog HTTP API (read-mostly).
- **`intelligence-catalog/db/dual_writer.py` + `feedback_loop.py`** — Catalog enrichment writes back to the master Postgres instance.
- **`intelligence-catalog/watchers/parsers/`** — Per-manufacturer firmware/spec watchers (Bitmain, MicroBT, Canaan, Auradine, Bitdeer).

The legacy `intelligence/` directory (Phase 1 design notes) was removed in the 2026-04-29 doc sweep. See `docs/REPO_DOC_SWEEP_2026-04-29.md`.

---

## Grafana Dashboards (provisioned by installer)

Seven dashboards. Six operational ones fed by Prometheus scraping `dashboard-api:8585/metrics`. One intelligence dashboard fed by the Intelligence Report API on port 8590.

| Dashboard | UID | Contents |
|-----------|-----|----------|
| Mining Guardian — Main | `bfi3t0krwak1sd` | 14 stat tiles, fleet/HVAC/temp/pool/HW error charts |
| Fleet Overview | `efi3msabjg2kge` | Online/offline/issues, HVAC trends |
| Per-Miner | `cfi3mt5a450xse` | Hashrate/temp/PDU/board charts + status/history panel |
| Board Health | `afi3p5mhapn9ce` | Per-board voltage/freq/HW errors/power |
| Pool Stats | `afi3q9w5ishz4f` | Fleet totals + rejection rate + top 5 worst offenders |
| AI & Learning | `llm_learning_001` | Knowledge score, insights growth, autonomy rate |
| Intelligence Report | `intelligence_report_001` | Searchable miner lookup across all 321 models, full HTML reports, live BTC/network data |

Per-miner dropdown in the Intelligence Report dashboard is query-driven against the catalog (PR #87) — no hardcoded miner list. Type any IP suffix or model substring to filter.

### Prometheus Metrics

**Per-miner:** hashrate %, chip temp, PDU power kW, flagged 0/1, dead boards 0/1.
**Per-board:** rate MH/s, voltage, frequency MHz, power W, HW errors, temp °C.
**Per-pool:** accepted shares, rejected shares, rejection rate %.
**Fleet:** online count, offline count, issues count.
**HVAC:** supply/return temps °F, delta-T, differential pressure, spray pump.
**Weather:** outside temp °F, humidity %.
**AI / Knowledge:** `mining_guardian_knowledge_score`, `_insights_total`, `_patterns_total`, `_miner_profiles_total`, `_last_updated_timestamp`, `_actions_approved_total`, `_actions_denied_total`, `_actions_auto_overnight_total`, `_actions_expired_total`, `_restarts_total`, `_tickets_created_total`.

---

## The Learning Loop

Mining Guardian is a learning loop — every scan feeds it, every operator decision refines it, every week it synthesizes, every month it federates across customer sites. See `docs/VISION.md` §4 for the full breakdown.

**Per-scan (every hour):** scan → verify → evaluate → save → feed local LLM → run AI features → Slack post (throttled) → overnight auto-execute low-risk actions during the configured window.

**Per-action:** APPROVE → execute → outcome checker labels SUCCESS/FAILURE/PARTIAL over the next 2–3 scans → update per-miner fingerprint → update confidence scorer. DENY → "Why?" → reason captured → local LLM processes into rule candidate → weekly Claude/Qwen training validates.

**Weekly (Sunday 3am):** `train_cohort.py` groups miners into ~10–15 cohorts by hardware identity (model, firmware, chip bin, PCB version, cooling). Cohort pass analyzes each cohort. Outlier pass deep-dives on anything >2σ from cohort mean. Fleet pass synthesizes everything. Same code path runs with Qwen 32B on customer Mac Minis.

**Weekly refinement:** `ai/refinement_chain.py` runs a 4-pass error-catching loop over the weekly output. Added April 10 2026 after Qwen caught 4 Claude errors in the first run.

**Monthly federation:** each customer site exports `knowledge.json` → `combine_knowledge.py` → master knowledge pushed back to every site. No internet required. USB-friendly.

---

## AI Features (all in `ai/`)

| # | Feature | File | Status |
|---|---|---|---|
| 1 | Outcome feedback loop | `ai/outcome_checker.py` | ✅ LIVE |
| 2 | Confidence scoring (gates autonomy) | `ai/confidence_scorer.py` | ✅ LIVE |
| 3 | Denial reason capture | `api/slack_approval_listener.py` + `ai/llm_scan_hook.py` | ✅ LIVE |
| 4 | Miner fingerprinting v2 | `ai/fingerprint_builder.py` | ✅ LIVE |
| 5 | HVAC / environment correlation | `ai/hvac_correlator.py` | ✅ LIVE |
| 6 | Pre-failure prediction v3 (14 signals) | `ai/predictor.py` | ✅ LIVE |
| 7 | Repair shop data ingestion | TBD | ⏳ Blocked on dataset from James/ACS |
| 8 | Action diversity (POWER_PROFILE, ECO_MODE, POOL_FAILOVER) | `ai/action_diversity.py` | ✅ LIVE |

All wired into `mining_guardian.loop()` after each scan.

---

## Approval Flow

Scan posts to Slack with a numbered miner list in thread. Reply:
- `APPROVE` — approve all pending actions in that thread
- `DENY` — deny all (triggers "Why?" follow-up for reason capture)
- `DENY <reason>` — deny with inline reason, skips follow-up
- `approve 1,3` — approve miners 1 and 3 by number
- `approve .36,.46` — approve by IP suffix

Or use the operator web GUI at `http://localhost:8686/ui/`.

**Rules:**
- One pending approval per miner. New scan updates the existing row, never stacks.
- Auto-expire after 1 hour with audit-log entry — fresh approval raised on next scan.
- Authorized Slack user IDs only (`AUTHORIZED_SLACK_USER_IDS` in `.env`).
- No Slack scan reports during quiet hours (configurable; default 10pm–5am) — overnight automation runs silently.

---

## Escalation (2-Restart Rule)

1. Miner flagged → RESTART → operator approves (or overnight auto-executes).
2. `miner_restarts` records every restart.
3. **2+ restarts in 7 days** OR **2+ FAILURE outcomes** → action auto-escalates to `RESTART_CHECK_BOARDS`.
4. Dead-board flow → AMS ticket created (priority high) → one-time Slack notice → miner permanently suppressed (`known_dead_boards`).

Both manual and overnight auto-restarts count toward the threshold.

---

## Offline Remediation Decision Tree

(`_analyze_miner` in `core/mining_guardian.py`)

1. AMS reports offline → direct TCP verify on port 4028.
2. Verify says online → flag `AMS_SYNC` for up to 10 consecutive scans, then suppress.
3. Verify confirms offline:
   - First time → firmware RESTART.
   - PDU available + RESTART already tried → PDU_CYCLE.
   - No PDU (S19J Pros) OR PDU cycle already tried → PHYSICAL_CYCLE (ticket + human).

---

## Overnight Automation

Window read live from `system_schedules.overnight_window`. Default: 20:00–06:00 every day.

| Risk | Action | Criteria | Auto-execute |
|------|--------|----------|--------------|
| AUTO | Firmware restart | First attempt tonight, no board issues | ✅ |
| AUTO | PDU cycle | First attempt, PDU assigned | ✅ |
| HOLD | Any restart | Already restarted tonight (2-per-night cap) | ⏸ Skip — logged once |
| MANUAL | Board restart | Dead hashboard | ❌ Never |
| MANUAL | Physical cycle | No PDU assigned | ❌ Never |

- Every auto-restart counted in `miner_restarts` for escalation.
- Miners with 3+ FAILURE outcomes are blocked from overnight auto-restart until human review.
- 6am window close → posts summary to Slack.
- `dry_run: true` in `config.json` blocks all AMS calls — safe for testing.

---

## Slack Commands

Type in `#mining-guardian`:

| Command | What it does |
|---------|-------------|
| `status` | Current fleet overview |
| `hot` | Miners ≥ 84°C |
| `dead` | Known dead boards |
| `btc` | BTC price + revenue estimate |
| `knowledge` | What the AI has learned |
| `audit` | Last 10 actions |
| `overnight` | What happened overnight |
| `predict` | Most likely next failures |
| `miner <ip>` | Deep dive on one miner |
| Free-form question | Fleet-aware AI answer with full history context |

No Slack messages during quiet hours. Operator-controlled via `system_schedules`.

---

## Backups

**Mac Mini local backup (cron):**
- `pg_dump mining_guardian` → rotating snapshots (12 hourly + 30 daily).
- `knowledge.json` → 12 rolling copies.
- `config.json` + `.env` → latest only.

**External drive (when attached):**
- Mirrors the local snapshot directory.

**GitHub:**
- `knowledge_backup.json` pushed daily by `ai/backup_knowledge.py`.
- All code on every push.

---

## Key Files

| File | Purpose |
|------|---------|
| `CLAUDE.md` | **Binding rules for every Claude session. Read first.** |
| `docs/VISION.md` | Canonical plan. Read second. |
| `DEPLOYMENT_CHECKLIST.md` | Customer-site install runbook (Mac Mini era). |
| `core/mining_guardian.py` | Main scanner / evaluator / Slack reporter. `dry_run` enforced everywhere. |
| `api/dashboard_api.py` | REST + Prometheus + `/query/*`. |
| `api/approval_api.py` | APPROVE/DENY + operator web GUI. |
| `api/slack_approval_listener.py` | Text-based Slack approval handler. |
| `api/slack_command_handler.py` | Conversational fleet intelligence bot. |
| `api/ams_alert_listener.py` | AMS alert listener. |
| `api/intelligence_report_api.py` | Miner Intelligence Report (321 models). |
| `api/system_settings.py` | Operator mode + global flags. |
| `api/system_schedules.py` | Operator-controlled schedules (PR #90). |
| `core/overnight_automation.py` | Autonomous overnight engine. |
| `core/llm_analyzer.py` | Two-tier LLM routing (Qwen + Claude). |
| `ai/knowledge_manager.py` | Persistent `knowledge.json` with file locking. |
| `ai/local_llm_analyzer.py` | Every-scan Qwen 32B + denial reason processing. |
| `ai/daily_deep_dive.py` | Daily Qwen per-miner + fleet synthesis. |
| `ai/train_cohort.py` | **Production weekly cohort trainer.** |
| `ai/refinement_chain.py` | 4-pass weekly error-catching loop. |
| `ai/combine_knowledge.py` | Federated multi-site knowledge merger. |
| `clients/auradine_client.py` | Teraflux AH3880 direct API. |
| `clients/hvac_client.py` | HVAC client (facility-specific). |
| `clients/pdu_client.py` | BiXBiT 2U+PDU client. |
| `installer/macos-pkg/` | Mac Mini `.pkg` installer (PR #79). |
| `migrations/` | Postgres migrations 001–005. |
| `intelligence-catalog/` | Catalog API + 321-miner seed CSV + watchers. |

---

## Repo Hygiene Conventions

- **Every fix PR flips its corresponding row in `docs/MG_UNIFIED_TODO_LIST.md` from 🔴 OPEN to ✅ DONE in the same commit.**
- **Never branch a feature PR off another open feature PR.** Stacked PRs lose work in squash. Always branch off `main`.
- **Never** `cp config_template.json` over `config.json` on a live host — loses credentials.
- `.env` is gitignored. `.env.example` documents every variable.
- `knowledge.json` is gitignored; `knowledge_backup.json` (tracked) is the daily push target.
- Bitcoin SHA-256 miners only. No altcoin / multi-algo support.

---

## Important Notes

- **Local-only deployment.** Cloud is not in scope.
- **Pool management and miner settings are out of scope** (security policy).
- **HVAC/BAS integration** is one-off for the BiXBiT USA warehouse — not in deployment templates.
- **AMS API docs:** https://api-staging.dev.bixbit.io/api/doc/index.html
- **Slack channel:** `#mining-guardian` (ID `C0AQ8SE1448`).
- **GitHub repo:** `robertfiesler-spec/Mining-Guardian` (the original 2024 repo had an intentional typo `Mining-Gaurdian`; renamed in PR #1 on 2026-04-26).

---

## Status (2026-04-29)

- Repo is on `main @ 3ea5e72` post-PR #90 squash.
- Bucket 0–8 + Bucket 10 are ✅ done. Bucket 9 §10.1/§10.2/§10.7 ✅ done. §10.4/§10.5/§10.6 (customer doc refresh) is the only remaining item, blocked on dashboard screenshots from the running install.
- Tomorrow morning (2026-04-30): Mac Mini install at BiXBiT USA, Fort Worth, TX.
- See `docs/MG_UNIFIED_TODO_LIST.md` for the full task ledger.

---

*Last updated: 2026-04-29. Maintained as part of the doc sweep — see `docs/REPO_DOC_SWEEP_2026-04-29.md` for the full audit ledger.*
