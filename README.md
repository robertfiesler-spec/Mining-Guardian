# Mining Guardian

Autonomous AI-powered Bitcoin mining fleet monitoring system for BiXBiT USA in Fort Worth, TX. Monitors 58 miners across liquid-cooled hydro racks and an immersion tank, diagnoses problems with a two-tier AI system, and manages the full action lifecycle — from detection through approval, execution, ticket creation, and suppression — all running 24/7 with no Mac required.

The system learns continuously. Every 5-minute scan updates the knowledge base. Weekly deep training via Claude API synthesizes everything into fleet-wide patterns. Knowledge Score, insight count, and autonomy rate are all visible live in Grafana.

> 📘 **Read this first if you're a new Claude session:** `CLAUDE.md` (binding rules), then `docs/VISION.md` (canonical plan), then the rest of this README. The Session Kickoff Protocol in `CLAUDE.md` is mandatory.

---

## Current Phase: R&D on VPS → Mac Mini at Customer Site

**The current VPS deployment is temporary R&D scaffolding, not the product.** The real product is a single Mac mini running a docker-compose stack at a customer site. The stack migrates between May 5–9 2026 when the first Mac mini arrives. See `docs/VISION.md` for the full target architecture and `docs/CLOUDFLARE_MIGRATION.md` for the removal checklist.

---

## Architecture (current R&D phase)

```
Hostinger VPS (187.124.247.182 / Tailscale 100.106.123.83)   ← TEMPORARY
  ├── mining-guardian (systemd)         — scans fleet every 5 min
  ├── dashboard-api (systemd :8585)     — Retool + Grafana data + Prometheus /metrics + /query/* endpoints
  ├── approval-api (systemd :8686)      — APPROVE/DENY/approve_selected execution
  ├── slack-listener (systemd)          — polls Slack threads for text approvals
  ├── slack-commands (systemd)          — fleet intelligence bot
  ├── overnight-automation (systemd)    — autonomous low-risk actions 8pm–6am
  ├── cloudflared (systemd)             — TEMPORARY: dashboard/slack/grafana.fieslerfamily.com tunnels
  ├── Prometheus (systemd :9090)        — metrics scraper (30s interval)
  ├── Grafana (systemd :3000)           — 6 dashboards
  └── OpenClaw (Docker)                 — Slack Socket Mode, conversational LLM gateway

ROBS-PC (Windows, facility R&D center, Tailscale 100.110.87.1)
  ├── Subnet gateway                    — routes 192.168.188.0/24 to VPS
  └── Ollama + Qwen2.5 32B Q4 on RTX 4090 (port 11434)  — local LLM for every-scan analysis

Anthropic Claude API                    — weekly training, knowledge merges, deep analysis
```

**Migration target (May 5-9 2026):** Mining Guardian and OpenClaw become two containers in a single docker-compose stack on a Mac mini at the customer site. All Cloudflare tunnels removed. No public ingress. Outbound-only. See `docs/VISION.md` section 3 for the target architecture diagram.

---

## Two-Tier AI System

| Tier | Model | Hardware | Used For | Cost |
|------|-------|----------|----------|------|
| Local | Qwen2.5 32B Q4_K_M | RTX 4090 (24 GB VRAM) on ROBS-PC | Every scan analysis (~4.6s) + denial processing | Free |
| Cloud | Claude Sonnet | Anthropic API | Weekly cohort training, knowledge merges, deep analysis | ~$1-2/mo |

- Ollama on VPS stopped to save CPU — all LLM queries route to ROBS-PC over Tailscale
- Claude path does NOT fall back to Ollama during outages — scan loop never blocks on Claude
- Fleet knowledge context (HW errors, pool rejections, dead boards, chronic miners) is injected into every LLM prompt via `knowledge_manager.build_context_prompt()`
- `model_used` in `llm_analysis` always reflects the actual backend that ran
- **Production customer Mac minis use local LLM only** — Claude API is proof-of-concept only. The same `train_cohort.py` code path runs on customer sites with Qwen 32B instead of Claude.

---

## Fleet

58 miners total, all liquid-cooled:

| Model | Count | Firmware | Stock TH/s | Max TH/s | Boards |
|-------|-------|----------|-----------|----------|--------|
| Antminer S19J Pro | ~36 | BiXBiT | 104 | 160 | 3 |
| Antminer S19J Pro | 5 | Stock | 104 | — | 3 |
| Antminer S19j Pro (alt AMS code) | 4 | Stock | 104 | — | 3 |
| Teraflux AH3880 | 2 | Auradine FluxOS | 300 (eco) | 600 (turbo) | **2** |
| Antminer S21 EXP Hydro | 2 | BiXBiT | 430 | 506 | 3 |
| Antminer S21 Imm (.22) | 1 | BiXBiT | 208 | 360 | 3 |
| Antminer S21 Imm (.23) | 1 | BiXBiT | 217 | 347 | 3 |

- All cooling is liquid (hydro racks + immersion tank). No air cooling.
- Board count per model read from `miner_specs.json` — AH3880 correctly treated as 2-board
- PDUs: orient_RPDU 163 @ `192.168.188.15`, 164 @ `192.168.188.16`
- S19J Pros have **NO** PDU outlet in AMS — offline remediation is restart → bad PSU ticket

### Operator rules (LOCKED)

- **Temperature:** No yellow tier. 84°C is the only threshold. Below 84°C is normal regardless of cohort average. The previous "76°C yellow / 86°C red" rule is wrong and has been removed. This applies to all prompts, all flagging logic, and the local LLM system prompt.
- **HVAC delta-T:** The USA 188 HVAC system is performing correctly. Low delta-T is intentional and will rise as outside temps climb. Do NOT recommend HVAC investigation based on delta-T.
- **Firmware regression:** When N+ miners of the same model show identical fault patterns within hours of a firmware update, prefer "firmware regression" diagnosis over individual hardware failure.
- **20-minute post-restart grace period:** After any restart (manual or overnight auto), suppress the miner from action recommendations for 20 minutes.
- **Dead S19JPro boards:** Suppressed after ticket creation. Do not re-raise.

---

## Services (VPS — all systemd, auto-start on boot)

| Service | Port | Description |
|---------|------|-------------|
| mining-guardian | — | Scans fleet every 5 min, evaluates all miners, runs 8 AI features in loop |
| dashboard-api | 8585 | REST API + Prometheus /metrics + `/query/*` endpoints (OpenClaw guardian-db skill) |
| approval-api | 8686 | Handles APPROVE/DENY/approve_selected calls (localhost-bound) |
| slack-listener | — | Polls Slack threads for text approvals |
| slack-commands | — | Conversational fleet intelligence bot (migrating into OpenClaw) |
| overnight-automation | — | Auto-executes low-risk actions 8pm–6am |
| cloudflared | — | **TEMPORARY**: dashboard.fieslerfamily.com → :8585, slack.fieslerfamily.com → :8686 — all off by May 5–9 |
| prometheus | 9090 | Metrics scraper, 30s interval |
| grafana | 3000 | All dashboards |
| OpenClaw (Docker) | 18789 | Slack Socket Mode + conversational LLM gateway |

---

## Grafana Dashboards

Six dashboards, all fed by Prometheus scraping `dashboard-api:8585/metrics`. Search box enabled on all per-miner dropdowns — type any IP suffix to filter instantly.

| Dashboard | UID | Contents |
|-----------|-----|----------|
| Mining Guardian — Main | bfi3t0krwak1sd | 14 stat tiles, fleet/HVAC/temp/pool/HW error charts |
| Fleet Overview | efi3msabjg2kge | Online/offline/issues, HVAC trends |
| Per Miner | cfi3mt5a450xse | Hashrate/temp/PDU/board charts + status/history panel |
| Board Health | afi3p5mhapn9ce | Per-board voltage/freq/HW errors/power |
| Pool Stats | afi3q9w5ishz4f | Fleet totals + rejection rate + top 5 worst offenders |
| AI & Learning | llm_learning_001 | Knowledge score, insights growth, autonomy rate, AI impact on fleet health |

### Prometheus Metrics (complete list)

**Per-miner:** hashrate %, chip temp, PDU power kW, flagged 0/1, dead boards 0/1
**Per-board:** rate MH/s, voltage, frequency MHz, power W, HW errors, temp °C
**Per-pool:** accepted shares, rejected shares, rejection rate %
**Fleet:** online count, offline count, issues count
**HVAC:** supply/return temps °F, delta-T, differential pressure, spray pump
**Weather:** outside temp °F, humidity %
**AI / Knowledge:**
- `mining_guardian_knowledge_score` — composite intelligence score (insights + patterns×10 + profiles)
- `mining_guardian_knowledge_insights_total` — total fleet insights learned
- `mining_guardian_knowledge_patterns_total` — recurring patterns identified
- `mining_guardian_knowledge_miner_profiles_total` — behavioral profiles built
- `mining_guardian_knowledge_last_updated_timestamp` — Unix timestamp of last knowledge update
- `mining_guardian_actions_approved_total` — human-approved actions (all time)
- `mining_guardian_actions_denied_total` — denied actions (all time)
- `mining_guardian_actions_auto_overnight_total` — autonomous overnight actions (all time)
- `mining_guardian_actions_expired_total` — auto-expired unanswered approvals (all time)
- `mining_guardian_restarts_total` — total restarts performed (all time)
- `mining_guardian_tickets_created_total` — AMS tickets created by AI (all time)

---

## Database Tables

16 tables in `guardian.db` (SQLite). Atomic writes, migrations handled in `GuardianDB._init_db`.

| Table | Purpose |
|-------|---------|
| `scans` | Scan history: timestamp, online, offline, issues count |
| `miner_readings` | Every scan — 27 fields per miner |
| `chain_readings` | Per-board: rate, voltage, freq, consumption, HW errors, temp |
| `pool_readings` | Per-pool: accepted/rejected shares, diff, status |
| `miner_state_readings` | Hashrate tiers, device limits, minerStatus codes |
| `miner_ams_extended` | AMS timestamp, map coords, PDU counter, stratum URL |
| `miner_hardware` | Board name, serial, chip die/marking/tech, PCB/BOM version, PSU, ASIC count |
| `log_metrics` | Per-chip hashrate, PSU voltage, system health, chain events — parsed from miner.log |
| `miner_logs` | Full raw miner.log files (30-day retention, 6hr collection, deduped) |
| `action_audit_log` | Every action ever: timestamp, miner, decision, approved_by, slack_user_id |
| `known_dead_boards` | Dead board registry — suppresses reflagging after ticket creation |
| `pending_approvals` | Actions waiting for operator response (1 per miner max, 1hr auto-expire) |
| `miner_restarts` | Every restart + outcome feedback (SUCCESS/FAILURE/PARTIAL) |
| `llm_analysis` | Every LLM response with prompt, model_used, duration |
| `hvac_readings` | HVAC supply/return/pressure/pump data |
| `weather_readings` | Outside temp and humidity |
| `chip_readings` (stub) | Ready for direct-API per-chip data |
| `miner_baselines` | Tier 3 hashrate baseline learning state (for unknown models) |
| `facility_events` | HVAC correlator detected fleet-wide events |

---

## The Learning Loop (main feature of the product)

Mining Guardian is a learning loop — every scan feeds it, every operator decision refines it, every week it synthesizes, every month it federates across customer sites. See `docs/VISION.md` section 4 for the full breakdown. Short version:

**Per-scan (every 5 min):** scan → verify → evaluate → save → feed local LLM → run 8 AI features → Slack post (throttled to 1/hr) → overnight auto-execute low-risk actions 8pm-6am.

**Per-action:** APPROVE → execute → outcome checker labels SUCCESS/FAILURE/PARTIAL over next 2-3 scans → update per-miner fingerprint → update confidence scorer. DENY → "Why?" → reason captured → local LLM processes into rule candidate → Sunday Claude training validates.

**Weekly (Sunday 3am):** `train_cohort.py` groups all miners into ~10-15 cohorts by hardware identity (model, firmware, chip bin, PCB version, cooling). Cohort pass analyzes each cohort as a group. Outlier pass does per-miner deep-dive on anything >2σ from cohort mean. Fleet pass synthesizes everything into the weekly report, refines operator rules, and predicts next week's failures. Same code path runs on customer Mac minis with Qwen 32B instead of Claude — cohort count grows sub-linearly with fleet size, keeping cost flat at any scale.

**Weekly refinement (after training):** `ai/refinement_chain.py` runs a 4-pass error-catching loop: (1) read Qwen daily deep dive, (2) read Claude weekly output, (3) Qwen reflects on Claude and identifies errors, (4) Claude merges corrections into final report. The refined report overwrites `cross_miner_analysis[0]` so next week's training picks up the corrected version. Added April 10 2026 after Qwen caught 4 Claude errors in the first run.

**Monthly federation:** each customer site exports `knowledge.json` → Bobby runs `combine_knowledge.py` → master knowledge pushed back to every site → every customer's fleet makes every other customer's fleet smarter. No internet required for the sync.

---

## 8 AI Features (all in `ai/`)

| # | Feature | File | Status |
|---|---|---|---|
| 1 | Outcome feedback loop | `ai/outcome_checker.py` | ✅ LIVE |
| 2 | Confidence scoring (gates autonomy) | `ai/confidence_scorer.py` | ✅ LIVE |
| 3 | Denial reason capture | `api/slack_approval_listener.py` + `ai/llm_scan_hook.py` | ✅ LIVE |
| 4 | Miner fingerprinting v2 | `ai/fingerprint_builder.py` | ✅ LIVE (58 profiles) |
| 5 | HVAC / environment correlation | `ai/hvac_correlator.py` | ✅ LIVE |
| 6 | Pre-failure prediction v2 (12 signals) | `ai/predictor.py` | ✅ LIVE |
| 7 | Repair shop data ingestion | TBD | ⏳ Blocked on dataset from James/ACS |
| 8 | Action diversity (POWER_PROFILE, ECO_MODE, POOL_FAILOVER) | `ai/action_diversity.py` | ✅ LIVE |

All 8 features are wired into `mining_guardian.loop()` in sequence after each scan completes.

---

## Approval Flow

Scan posts to Slack with a numbered miner list in thread. Reply:
- `APPROVE` — approve all pending actions in that thread
- `DENY` — deny all (triggers "Why?" follow-up for reason capture)
- `DENY <reason>` — deny with inline reason, skips follow-up
- `approve 1,3` — approve miners 1 and 3 by number
- `approve .36,.46` — approve by IP suffix

**Rules:**
- One pending approval per miner maximum — new scan updates existing row, never stacks
- Auto-expire after **1 hour** with audit log entry — fresh approval raised on next scan
- Only authorized Slack user IDs can trigger hardware actions (`AUTHORIZED_SLACK_USER_IDS` in `.env`)
- No Slack scan reports during quiet hours (10pm–5am) — overnight automation runs silently

OpenClaw owns Socket Mode — the listener currently uses text-based polling to avoid conflict. On the Mac mini, OpenClaw will route Block Kit button clicks directly to the local approval API via Socket Mode (no public ingress required).

---

## Escalation Logic (2-Restart Rule)

1. Miner flagged → RESTART action → operator approves (or overnight auto-executes)
2. `miner_restarts` table records every restart (manual and overnight auto)
3. If miner has **2+ restarts in 7 days** OR **2+ FAILURE outcomes** from the outcome checker → action auto-escalates to `RESTART_CHECK_BOARDS`
4. Dead board flow executes → AMS ticket created → one-time Slack notice → miner permanently suppressed

Both manual-approved and overnight auto-restarts count toward the 2-restart threshold.

---

## Dead Board Lifecycle

1. Dead board detected → flagged as `RESTART_CHECK_BOARDS`
2. Operator approves → restart executed, logs collected before + after
3. Board still dead → **AMS ticket auto-created** (priority: high)
4. **Next Slack report** → one-time notice: ticket created, miner removed
5. **All future reports** → miner silently suppressed (`known_dead_boards` table)
6. Board physically repaired → resolve in AMS → monitoring resumes

Dead board miners are **never** shown in the approval queue.

---

## Offline Remediation Decision Tree

Implemented in `_analyze_miner`:

1. AMS reports offline → direct TCP verify on port 4028
2. If verify says online: flag as `AMS_SYNC` for up to 10 consecutive scans, then suppress
3. If verify confirms offline:
   - First time offline → firmware RESTART
   - Has PDU + RESTART already tried → PDU_CYCLE
   - No PDU (S19J Pros) OR PDU cycle already tried → PHYSICAL_CYCLE (ticket + human)

---

## Overnight Automation (8pm–6am)

| Risk | Action | Criteria | Auto-execute |
|------|--------|----------|--------------|
| AUTO | Firmware restart | First attempt tonight, no board issues | ✅ Yes |
| AUTO | PDU cycle | First attempt, PDU assigned | ✅ Yes |
| HOLD | Any restart | Already restarted tonight (2-per-night cap) | ⏸ Skip — logged once |
| MANUAL | Board restart | Dead hashboard detected | ❌ Never |
| MANUAL | Physical cycle | No PDU assigned | ❌ Never |

- Every auto-restart recorded in `miner_restarts` — counts toward 2-restart escalation threshold
- HOLD decisions logged once per overnight window — no audit trail spam
- Miners with 3+ FAILURE outcomes are permanently blocked from overnight auto-restart until human review
- At 6am when window closes → posts summary via OpenClaw to Slack
- `dry_run: true` in `config.json` fully blocks all AMS calls — safe for testing

---

## Weekly LLM Training

### Primary trainer: `ai/train_cohort.py` (scale-first)

The production weekly trainer. Designed for fleets of 50-50,000+ miners. Read its docstring before writing anything new that touches the learning loop.

**Three passes:**
1. **Cohort pass** — groups miners by `(model, firmware, chip_bin, pcb_version, cooling)`. One Claude call per cohort with per-cohort aggregates, restart outcomes, top problems, and filtered local LLM observations. At 58 miners this produces 10-15 cohort calls.
2. **Outlier pass** — miners >2σ below cohort hashrate mean or >2σ above cohort temp mean get individual deep analysis. Capped at 30 outliers per run.
3. **Fleet synthesis pass** — ONE final Claude call with everything: all cohort results, all outlier results, all local LLM scan analyses from the week, operator rules, and cross-miner SQL correlations. Produces the weekly executive report.

**Scale comparison (from the `train_cohort.py` docstring):**
- 58 miners → 16-26 Claude calls total
- 500 miners → 36-66 calls
- 5,000 miners → 81-181 calls
- 50,000 miners → 251-651 calls

Cohort count grows sub-linearly — Claude API cost stays flat, local LLM workload stays manageable.

### Legacy trainer: `ai/train_comprehensive.py`

The original per-miner trainer. Hit rate limits at miner #3 of 58. Still used as a helper module by `train_cohort.py` for `get_miner_full_profile`, `build_miner_prompt`, `get_hvac_weather_context`, and `get_cross_miner_correlations`. Not run standalone.

### What feeds the weekly training

- Full miner logs — no truncation, sectioned boot/mid/tail
- Per-board chain data — avg/min/max rate, voltage, freq, HW errors
- PSU voltage trend, system health, per-chip hashrate
- Chain attach/detach events, pool history, full audit trail
- Scan-to-scan delta analysis (≥10% HR or ≥5°C swings)
- Restart outcome correlation (before/after every approved restart)
- HVAC/weather correlation over last 30 days
- Every local LLM scan analysis from the past week (for validation + correction)
- Every operator denial reason from the past week
- **Pre/post restart comparison summaries** (dual-model Qwen + Claude) from `knowledge["known_issues"]` — merged in via the `TEMP_MAY_REMOVE` block (removed on Mac mini arrival)
- **Daily deep dive analyses** (per-miner + fleet synthesis from Qwen 32B) from `knowledge["daily_deep_analyses"]` — merged in via a PERMANENT merge block (not wrapped in TEMP_MAY_REMOVE, stays on forever). See `docs/DAILY_DEEP_DIVE_DESIGN.md` for details.

### Cross-miner correlation (inside the fleet pass)

Groups entire fleet by chip bin, die/tech, board serial batch, PCB/BOM version, PSU version, and fleet-wide restart effectiveness. Flags systematic hardware quality issues, firmware regression candidates, and procurement recommendations.

---

## Daily Log Pipeline (April 9 2026 overhaul)

The daily log collection + deep dive pipeline was overhauled in an afternoon sprint on April 9 2026. Five code commits and six doc commits. See `docs/SESSION_LOG_2026-04-09.md` for the full narrative and `REPAIR_LOG.md` for the entry-by-entry breakdown.

### Daily baseline collection (`collect_logs` in `core/mining_guardian.py`)

- **Schedule (starting April 10 2026):** cron-triggered daily. Every online miner gets one fresh log export per 24 hours.
- **Parallelism:** 15-worker thread pool (`concurrent.futures.ThreadPoolExecutor`). Each worker collects one miner at a time. Stuck miners only block their own worker slot; healthy miners complete in ~20 seconds regardless of what other workers are doing.
- **Per-miner cap:** 10 minutes. If AMS does not produce a fresh log export within 10 minutes for a given miner, that worker gives up and moves on. Post-restart log collection and `_wait_for_stable` paths remain uncapped.
- **Storage:** logs written to `miner_logs` table with `health_status = 'daily_baseline'`. Kept 30 days then purged. Hardware identity parsed from `miner.log` is permanent.
- **Dedup:** 24-hour per-miner check prevents double-collection across overlapping sweeps.
- **Thread safety:** `requests.Session` for concurrent POSTs, per-call sqlite3 connections with WAL mode, counters guarded by `threading.Lock`, `_ensure_token` forced to refresh before spawning the pool.
- **Expected wall time:** 2-5 minutes typical, 10-12 minutes maximum if several miners hit the cap simultaneously.

### Post-restart log collection (unchanged by the April 9 overhaul)

Still single-miner, still uncapped. Pre-restart log pulled BEFORE the restart fires, post-restart log pulled AFTER the miner reaches mining state (via `_wait_for_stable`, no time cap). The pair goes to the dual-model Qwen + Claude comparator which writes to `knowledge["known_issues"]` with `compare:*` miner_id prefix. The Sunday Claude training merges these in via the TEMP_MAY_REMOVE block in `train_cohort.py`.

### Daily deep dive LLM (`ai/daily_deep_dive.py`)

- **Schedule (starting April 10 2026):** cron at 16:00 local, 3 hours after the 13:00 daily collection start. Takes as long as it needs.
- **Runs on:** Qwen 2.5 32B on ROBS-PC (RTX 4090), via Ollama on the Tailscale network. On Mac mini arrival (May), runs locally on May.
- **Two passes:** per-miner (one Qwen call per online miner, full 32K context, full daily log + 24h trends + restart history + hardware identity + fingerprint) then fleet synthesis (one final Qwen call reading all per-miner analyses + 24h HVAC/weather/fleet trends + operator rules + yesterday's deep dive).
- **No caps:** `num_ctx: 32768`, `num_predict: -1`, `temperature: 0.3`, request timeout 14400 seconds (4 hours).
- **Resume-safe:** each per-miner analysis written to `daily_deep_dive_wip/{YYYY-MM-DD}/miner_{id}.json` immediately, mid-run crashes resume from the last completed miner.
- **Output:** stored in `knowledge["daily_deep_analyses"]` (keeps last 30 days). Sunday Claude training picks this up via a PERMANENT merge block in `train_cohort.py`.
- **Expected wall time:** 2-4 hours steady state, less on first few days while yesterday-log comparisons are still being established.
- **Full design:** `docs/DAILY_DEEP_DIVE_DESIGN.md`.

### Per-scan reactive Qwen analysis (unchanged — still runs every hour from scan loop)

`ai/local_llm_analyzer.py` still runs every hour as a reactive pulse. The daily deep dive is ADDITIVE, not a replacement. Both are needed — the reactive path answers "anything wrong right now," the deep dive answers "what did I learn today."

---

## Knowledge System

- `knowledge.json` (gitignored) — updates every scan, atomic write (no corrupt-on-crash)
- `knowledge_backup.json` (tracked) — pushed to GitHub daily at 4am
- Weekly deep training via Claude API every Sunday at 3am via `train_cohort.py`
- Deduplication on every save — no duplicate patterns
- `ai/combine_knowledge.py` — federated multi-site knowledge merger
- **Knowledge metrics flow into Prometheus/Grafana** — score, insights, patterns all live in AI & Learning dashboard
- **Federated sync is USB-friendly** — no internet required for monthly cross-site knowledge merge

---

## Security

All credentials in `.env` on VPS — never in source code. Key security measures:

- **`approval_api.py`** — localhost bind, CORS restricted to known consumers, shared secret (`INTERNAL_API_SECRET`) required on all internal endpoints (fails closed if unset), Slack signature required + replay protection on `/slack/actions`, `/pending` endpoint requires auth
- **`dashboard_api.py`** — CORS locked to `dashboard.fieslerfamily.com`, `grafana.fieslerfamily.com`, localhost; XSS escaping on all DB values; param bounds clamped
- **`slack_approval_listener.py`** — authorized user allowlist via `AUTHORIZED_SLACK_USER_IDS` in `.env`
- **`slack_command_handler.py`** — question sanitization (500 char cap, strip control chars)
- **`hvac_client.py` and `pdu_client.py`** — no credential defaults; fail loudly if env vars unset
- **`.env` is gitignored** — 17 keys required, none duplicated

---

## Slack Commands (type in #mining-guardian)

| Command | What it does |
|---------|-------------|
| `status` | Current fleet overview |
| `hot` | Miners at or above 84°C |
| `dead` | Known dead boards |
| `btc` | Bitcoin price + revenue estimate |
| `knowledge` | What AI has learned |
| `audit` | Last 10 actions taken |
| `overnight` | What happened overnight |
| `predict` | Which miners are most likely to fail next |
| `miner 192.168.188.36` | Deep dive on one miner |
| Any question | Fleet-aware AI answer with full history context |

AI answers include: current fleet state, 14-day miner history, audit trail, dead board records, learned patterns, and log snippets for named miners. No Slack messages sent during quiet hours (10pm–5am).

**Migration note:** these commands currently run through `api/slack_command_handler.py` as systemd service. On the Mac mini they will be migrated into OpenClaw so the conversational layer is unified.

---

## Cron Jobs (VPS)

```
0 3  * * 0   weekly_train.py       — Cohort-based weekly training via Claude API (Sunday 3am)
0 4  * * *   backup_knowledge.py   — Push knowledge_backup.json to GitHub (daily 4am)
0 7  * * *   morning_briefing.py   — Daily briefing to Slack (7am)
*/360 * * *  log collection        — Miner logs collected every 6 hours
```

---

## Backup System

**Big-Bobby-T9 drive** (Mac cron every 5 min when Mac is on):
- `guardian.db` — rolling 12 copies + daily snapshots (30 days)
- `knowledge.json` — rolling 12 copies
- `config.json` + `.env` — latest only
- Location: `/Volumes/Big-Bobby-T9/Bixbit USA/Mining Guardian Backups/`

**GitHub:**
- `knowledge_backup.json` — daily 4am push from VPS
- All code — on every push

---

## Key Files

| File | Purpose |
|------|---------|
| `CLAUDE.md` | **Binding rules for every Claude session. Read first, every time.** |
| `docs/VISION.md` | **Consolidated canonical plan. Read second.** |
| `core/mining_guardian.py` | Main scanner, evaluator, Slack reporter. `dry_run` enforced in all action paths. 2-restart escalation. 5480 lines. |
| `api/dashboard_api.py` | REST API + Prometheus /metrics + `/query/*` endpoints for OpenClaw guardian-db skill |
| `api/approval_api.py` | APPROVE/DENY + approve_selected, auth-hardened, localhost-bound |
| `api/slack_approval_listener.py` | Text-based polling approval handler (temporary until OpenClaw routing) |
| `api/slack_command_handler.py` | Conversational fleet intelligence bot (migrating into OpenClaw) |
| `api/ams_alert_listener.py` | AMS alert listener, queues urgent actions |
| `core/overnight_automation.py` | Autonomous overnight action engine, records restarts for escalation |
| `scripts/morning_briefing.py` | Daily 7am Slack briefing, real fleet TH/s revenue, UTC timestamps |
| `core/llm_analyzer.py` | Two-tier LLM routing: Qwen 32B (scans) + Claude API (training) |
| `ai/knowledge_manager.py` | Persistent knowledge.json — atomic write, live DB context in every prompt |
| `ai/local_llm_analyzer.py` | Every-scan Qwen 32B analysis + denial reason processing |
| `core/hashrate_evaluation.py` | Three-tier hashrate evaluation, `statistics.median()`, per-model board count |
| `ai/train_cohort.py` | **Scale-first weekly Claude training (production path)** |
| `ai/train_comprehensive.py` | Legacy per-miner trainer (helper module only) |
| `ai/weekly_train.py` | Cron entry point — runs train_cohort + fingerprint_builder + hvac_correlator + predictor |
| `ai/deep_analysis_claude.py` | Ad-hoc fleet analysis via Claude API (NULL-safe, chunked) |
| `ai/combine_knowledge.py` | Federated multi-site knowledge merger |
| `ai/export_knowledge.py` | Monthly site knowledge export |
| `clients/auradine_client.py` | Teraflux AH3880 direct API (JWT, port 8443, standby-before-cut rule) |
| `clients/hvac_client.py` | HVAC client — facility-specific, NOT in deployment templates |
| `clients/pdu_client.py` | BiXBiT 2U+PDU client — no default credentials |
| `clients/container_monitor.py` | Built, NOT active — waiting for BiXBiT access grant |
| `core/miner_verify.py` | TCP verify miner online, recv threshold 20 bytes |
| `ai/backup_knowledge.py` | Daily knowledge backup to GitHub |
| `scripts/backup_db.sh` | Mac cron: pulls guardian.db, knowledge.json, config.json, .env every 5min |
| `config.json` | Runtime config + profile map (gitignored — never overwrite with template) |
| `knowledge.json` | LLM persistent memory (gitignored) |
| `knowledge_backup.json` | Tracked backup pushed to GitHub daily |
| `miner_specs.json` | Per-model specs: board count, rated TH/s, profile maps |
| `guardian.db` | SQLite database — never delete, never overwrite with template |
| `installer/DEPLOYMENT.md` | Mac mini installer spec (on `installer-build` branch) — 313 lines |
| `intelligence/README.md` | Mining Intelligence Catalog architecture (Postgres research DB) |

---

## AI Toolkit

Installed: v0.5.0-alpha

Slash commands for Claude Code (VS Code extension):
- `/kickoff` — initialize session, read CLAUDE.md + project context
- `/create-plan` — break a feature into a tracked checklist
- `/iterate` — execute plan items in batches with auto-checkpoint
- `/learn` — turn a correction into a permanent rule in CLAUDE.md
- `/checkpoint` / `/catchup` — save and restore session state across context clears
- `/review` / `/security-check` / `/pre-pr-check` — quality gates

`CLAUDE.md` contains Mining Guardian-specific rules that Claude Code reads every session.

---

## Important Notes

- **Never** `cp config_template.json` over `config.json` on VPS — loses all credentials (happened twice)
- **Never** add Bolt/slack-bolt to any listener — OpenClaw owns Socket Mode, conflicts will break Slack
- **ROBS-PC must stay on and never sleep** — Tailscale subnet gateway AND RTX 4090 LLM host
- **Pool management and miner settings are out of scope** (security policy)
- **S19JPro dead hashboard issues suppressed after ticket creation** — do not re-raise
- **HVAC/BAS integration is one-off for this warehouse** — not included in future deployment templates
- **Cloudflare tunnels are temporary** — all off by May 5–9 2026 when Mac mini arrives
- **The product is a Mac mini appliance at customer sites** — VPS is scaffolding, not the shipping product
- AMS API docs: https://api-staging.dev.bixbit.io/api/doc/index.html
- Slack channel: `#mining-guardian` (ID: C0AQ8SE1448)
- Grafana: `grafana.fieslerfamily.com` (temporary — becomes `http://mac-mini-ip:3000` at customer sites)
- GitHub repo: `robertfiesler-spec/Mining-Gaurdian` (intentional typo in repo name, space in folder name — always quote in terminal)

---

*Last updated: April 9 2026. See `CLAUDE.md` for binding rules and `docs/VISION.md` for the canonical plan. See `AI_ROADMAP.md` for feature status and hard deadlines.*
