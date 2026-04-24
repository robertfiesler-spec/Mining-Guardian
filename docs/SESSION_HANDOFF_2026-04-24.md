# Mining Guardian — Master Session Handoff (2026-04-24)

> **Purpose of this document:** Single source of truth for Rob + next-chat-me to pick up where we stopped. Read this first in the new chat. Everything else is supporting detail linked from here.
>
> **Author:** Perplexity Computer (same agent that will continue in the next chat — "just you" per Rob's rule, no Mac Claude).
> **Written:** 2026-04-24 ~12:45 PM CDT, before starting a new chat session.
> **Mac Mini ETA:** Monday April 27. We're working this weekend to be ready.

---

## Rule Set (verbatim, preserve)

- "step by step please i need to focus" — Rob has OCD, needs one action per turn
- "i have ocd and i hate slop or messes"
- "no more autonomous multi-step execution" — narrate every tool call, no writes without greenlight
- "we also need to get rid of all these other versions it is driving my ocd crazy" — version cleanup mentality
- "it is too much lets leave them be for know" re: 289 "Gaurdian" typos — LEAVE ALONE until Mac Mini cutover
- "stay away from anything cloud only and stay local"
- "Bitcoin SHA-256 miners ONLY" — no other algorithms
- **New (this week):** "from now on its just you" — single-agent, no more Mac Claude / PC Claude / VPS Claude parallelism

---

## What This Project Is — The Long View

**Mining Guardian** is a two-part system Rob is building for BiXBiT USA (Fort Worth, TX) — a Bitcoin mining operations monitoring + autonomy platform:

1. **Operational side** — monitors a live fleet (58 miners today) via AMS WebSocket API, detects dead boards, runs restart/repair workflows, posts conversational updates to Slack, and executes overnight automation (10pm–6am) with approval gating. Backed by two AIs: local Qwen 32B on an RTX 4090 (fast per-scan analysis, ~4.6s) and Claude API (deep cohort analysis + knowledge merges).

2. **Intelligence side** — a research/reference database (Field Intelligence Catalog) with every Bitcoin SHA-256 ASIC miner model ever made, their specs, firmware history, field performance notes, repair patterns, and cross-miner intelligence. Operational side queries the catalog read-only for spec lookups; catalog gets continuously enriched by 5 background agents and daily log imports.

**The end goal:** a signed installer that a customer can run on a Mac Mini to bring up both halves locally — operational monitoring + intelligence catalog — with Tailscale linking to their VPS scanner. That installer is the finish line we're pushing toward before the weekend.

---

## Project Timeline — Everything That Got Us Here

### Phase 0 — Operational base (pre-April)
- Fleet scanner, three-tier hashrate evaluation, per-board analysis
- AMS WebSocket integration with sync detection
- Slack approval workflow (`APPROVE`, `DENY`, per-miner `approve 1,3`)
- Dead board lifecycle automation (restart → AMS ticket → suppress → resume on resolve)
- Cron schedule: morning briefing 7am, operator review 8am, log collection 1pm, deep dive 4pm, refinement chain 1am, Claude training midnight, knowledge backup 4am (all CDT)

### Phase 1 — 48-hour test (April 6-8)
149+ scans, 12.1M+ data points, 53K miner readings, 45K chain readings, 58 fingerprints, 22 SUCCESS + 24 FAILURE outcomes, 25 autonomous actions, 50 known issues, 7 patterns discovered. Green signal to go full-day autonomous.

### Phase 2 — Intelligence Catalog stand-up (April 10-15)
- PostgreSQL 16 on ROBS-PC Docker (the PC Docker instance, NOT the VPS)
- 165 tables, 1,712+ columns, 320+ indexes, 115+ triggers
- 10 schemas: knowledge, hardware, firmware, ops, market, repair, pool, facility, regulatory, seed
- 4 auto-discovery tables to ensure no data point is ever lost
- First working dual-database Miner Intelligence Report generator (S19J Pro operational + M63S+ pre-purchase — demo ready April 15)
- 4 AI insights produced with confidence scores: PSU cascade failure (95%), firmware performance gap (87%), miner .206 progressive degradation (94%), end-of-life economics (78%)

### Phase 3 — Database split attempt (April 21-22)
- Commit `d452317`: monolithic SQLite → 4-way split (operational / timeseries / ai_knowledge / audit)
- Crashed April 22 morning on missing `json` import in `save_notifications`
- Fix surfaced 7 cross-table-join bugs (can't SELECT across SQLite databases without ATTACH)
- Reverted at 16:35 CDT — `_connect()` now pinned to legacy monolithic `guardian.db`
- The 4 split DB files still exist, cold, as rollback points. Do not delete.

### Phase 4 — Field Intelligence Pipeline Layer 2 ships (April 22 evening)
- Two-tier resolver built: Tier-1 unique aliases (12,852 seed rows) + Tier-2 family + hashrate disambiguation (1,494 seed rows)
- Fallback to `mg.unresolved_models` manual triage (no guessing)
- v3.3 `mg_import_tool` with SSE streaming API, sha256 dedup, per-archive error isolation, 277 tests passing
- First real archive: 14,178 rows in 0.45 seconds. Committed `3a38112`, pushed.

### Phase 5 — Post-revert stabilization (April 23)
- All 7 cross-table-join bugs fixed across 7 commits (even though `_connect()` currently ignores them — we want them fixed for when the router comes back)
- Detailed audit landed in `docs/CORE_DATABASE_AUDIT_2026-04-23.md`
- Scan 1691 verified clean on new PID 57931 at 05:35 CDT
- 12 commits pushed to origin/main
- **OpenClaw audit landed** (`docs/OPENCLAW_AUDIT_2026-04-23.md`) — OpenClaw is dead code. All sends are silent no-ops. Removal checklist written, deferred until database work stabilized.

### Phase 6 — Field Intelligence schema drift + v3.3 patch (April 23 afternoon → April 24 am)
- Attempting 83-archive mass import revealed schema drift: Mac Claude had silently converted `knowledge.field_log_raw_json` into a **partitioned** table with different columns (`entity_label, archive_filename, source_file, parser, raw_payload, sha256, ingested_at`)
- v3.3 still expected the flat schema — imports failed at the raw_json step
- Rob chose **Option A**: patch v3.3 Python to match the partitioned schema
- Two patch passes:
  - Pass 1 broke the SQL statement splitter on a multi-line `-- dedup` comment block → every downstream INSERT returned `INSERT 0 0`
  - Pass 2 (clean — just blank lines) compiled and ran: **6 of 7 tables green** on `Antminer_S19_2024-06-27_2024-06-29.tar` smoke test
- Final DB counts after smoke test:
  | Table | Count | Status |
  |---|---|---|
  | `knowledge.field_log_imports` | 1 | ✓ |
  | `knowledge.field_log_miner_identity` | 10 | ✓ (ON CONFLICT dedup from yesterday) |
  | **`knowledge.field_log_raw_json`** | **0** | **✗ only failing table** |
  | `knowledge.field_log_pools` | 3 | ✓ |
  | `knowledge.field_log_antminer_boots` | 10 | ✓ |
  | `knowledge.field_log_antminer_autotune` | 14118 | ✓ |
  | `knowledge.field_log_events` | 46 | ✓ (dedup reduced from 240 parsed) |
  | `mg.import_runs` | 1 | ✓ |

### Phase 7 — Documentation + git push (April 22-23 wrap-up)
- `FIELD_INTELLIGENCE_PIPELINE.md` rewritten to reflect two-tier resolver
- `SESSION_LOG_2026-04-22.md` written
- `NEXT_SESSION.md` rewritten to point at 83-archive batch + SQLite→Postgres Phase 2
- Layer 2 paragraph added to AI_ROADMAP build queue
- `.gitignore` cleanup
- `mg_import_tool/` v3.3 (277 tests) committed into repo root
- All pushed to origin/main

### Phase 8 — Where we stopped (today, April 24)
- 6/7 tables green. One bug left: `insert_raw_json()` silently swallows something.
- Rob has NOT yet run the direct-INSERT smoke test against `field_log_raw_json` that will tell us whether the bug is in the Python function or the partitioned table definition.
- Rob wants to start a new chat. This document is that chat's starting point.

---

## The Six-Point Plan — What's Left (Rob's list, verbatim order)

### 1. Finish the database (Field Intelligence) + re-import everything

**What "finish" means:**
- Close the `raw_json` bug. One function is silently failing. Plan is below.
- Re-import the 83-archive batch with all 7 tables populating correctly.
- Confirm per-archive error isolation and sha256 dedup work at batch scale.
- Target ≥95% auto-resolve coverage via the two-tier resolver.

**"AI needs to reference this db constantly":**
This is the part Rob doesn't want to miss. The original vision (see `docs/MONDAY_INTELLIGENCE_CATALOG_PLAN.md`, `docs/DAILY_DEEP_DIVE_DESIGN.md`, `docs/DAILY_LOG_CAPTURE_VISION.md`) is that:
- Every Qwen deep-dive cron (4pm) loads relevant catalog context for the miner being analyzed
- Every Claude cohort training (midnight) pulls cross-fleet patterns from the catalog
- Every intelligence report (`scripts/generate_intelligence_report.py`) is a dual-database join — operational guardian.db + catalog Postgres
- Every new log import enriches the catalog's field-intel columns (common failure modes, typical lifespan, hashboard interchangeability, immersion compatibility, chip degradation observations)

**Need to verify when we pick this up:** is the Qwen deep-dive actually pulling catalog context today, or is the catalog sitting there unqueried because we've been busy shipping it? The generator works (April 15 demo), but is the *cron* using it? First morning task after raw_json is fixed: trace one deep-dive's code path end-to-end and confirm it reads from the catalog.

### 2. Remove OpenClaw (dead weight) + reconfigure Slack

**Why:** OpenClaw is a dead integration — see `docs/OPENCLAW_AUDIT_2026-04-23.md` for the full walkthrough.

**Current state:**
- OpenClaw Docker container running on VPS, owns Slack Socket Mode connection
- `notifiers/openclaw_notifier.py` exists, instantiated with `webhook_url=None`
- Every `send_scan()` and `notify_openclaw()` call is a silent no-op
- `api/slack_approval_listener.py` uses polling instead of Bolt to avoid conflicting with OpenClaw's Socket Mode

**The Slack reconfiguration:**
- Once OpenClaw is gone, Slack Socket Mode becomes available to Mining Guardian directly
- Switch `slack_approval_listener.py` and `slack_command_handler.py` from REST polling → Bolt/Socket Mode
- More efficient, lower latency, one fewer service to keep alive
- Need fresh Slack app credentials (new Bot token + App-level token for Socket Mode)

**Order of operations for this chore:**
1. On VPS: `cd /docker/openclaw-5b5o && docker compose down`
2. Delete volumes (optional — keep session history if unsure)
3. Edit Python (9 file-level changes already documented in the OpenClaw audit checklist)
4. Run test suite (should pass — nothing real touched the notifier)
5. New Slack app: `mining-guardian-bot` with Socket Mode enabled, `chat:write`, `channels:history`, `reactions:read`
6. Swap `slack_approval_listener.py` + `slack_command_handler.py` to Bolt
7. Restart mining-guardian service
8. Verify `#mg-ai-reports` posts still land and `APPROVE`/`DENY` replies still execute
9. Commit: `refactor: remove OpenClaw; Slack direct via Bolt Socket Mode`

### 3. Top-down review — what's there, how it works, what's missing

This is the architecture walkthrough. Output is a single document (`docs/ARCHITECTURE_WALKTHROUGH_2026-04-27.md` or wherever we land) that explains:

- **System map** — every running service on VPS, PC, Mac Mini (post-arrival). Ports, sockets, files, env vars.
- **Data flow** — scan → AMS → miner fingerprint → analysis → knowledge write → Slack post. Same for overnight automation, log collection, cohort training, catalog enrichment.
- **Decision points** — where does human approval gate? Where does Qwen decide? Where does Claude decide? What runs without any AI (pure rule)?
- **Interfaces** — AMS WebSocket, BiXBiT Direct API, Auradine API, Bitmain firmware, MicroBT firmware, Canaan firmware, Slack, AMS REST, VPS-PC Tailscale, PC Postgres, VPS SQLite.
- **Gaps** — what's in `docs/CAPABILITIES.md` but not actually running. What's planned but not documented. What Rob wants that nobody has written down yet.

### 4. Audit — bloat, broken links, security, function, usability, everything

This is the "under every crack" pass. Split into tracks that can run in parallel:

**Track A — Security**
- Credential inventory: every DB password, every API token, every Slack signing secret. What's in env, what's in config files, what's in source.
- GitHub PAT rotation (old one is exposed in session logs)
- Postgres password rotation on PC Docker (`MiningGuardian2026!` is all over this handoff too — rotate after Mac cutover)
- `.env.example` hygiene: no real values, all vars documented
- CORS lockdown: see `docs/CORS_LOCKDOWN_PLAN.md` — verify it's actually applied
- Public-facing endpoints: which VPS ports are internet-reachable? Close everything not explicitly needed.
- Docker container privilege review (any root? any bind-mounts that expose host?)

**Track B — Bloat and dead code**
- OpenClaw removal (item #2 above)
- `knowledge_backup.json` + `guardian.sqbpro` + any other root-level cruft
- `miner_logs/` — is this a live write path or a leftover dev dir?
- `archive/`, `fixes/`, `deploy/` — inventory each, keep or delete
- Unused imports, unreachable code paths, commented-out blocks
- Duplicate scripts (e.g. anything in `scripts/` that does the same job as `ai/` or `core/`)
- 289 "Gaurdian" typos — leave until Mac cutover (Rob's rule)

**Track C — Broken links and dead references**
- Every `import` in Python — does the symbol exist?
- Every `{{ template_var }}` — does the context provide it?
- Every URL in docs — 404 check on the external ones, path check on the internal ones
- Every `config.xxx` reference — does `config.json` actually have that key?
- Every cron log path — does the directory exist and does cron have write access?

**Track D — Function correctness**
- Re-run full test suite (277 tests from `mg_import_tool/` + whatever tests live in `tests/`)
- Scan cadence sanity check: every hour, slack posts every hour, deep dive at 4pm, all landing
- Approval workflow end-to-end: create a fake actionable miner, post, approve, verify execution, verify audit row
- Dead board lifecycle end-to-end: simulate dead board, verify ticket creation, verify suppression, verify resume on resolve
- AI insights: generate one intelligence report, verify both DBs are queried, verify confidence scores round-trip

**Track E — Usability**
- Slack commands: every one in `docs/CAPABILITIES.md` — does it work? Does it return within 3 seconds?
- Error messages: when a command fails, does the user see something actionable?
- Morning briefing clarity: week-old briefings — are they readable without context?
- Grafana dashboards (Rob has shared assets for several — `grafana_fixed_*`) — verify they load on fresh install
- Intelligence report PDFs — render quality, font fallbacks, table overflow

**Track F — Performance / cost**
- LLM budget: Qwen runs free (local GPU), Claude API has a monthly ceiling — what's current burn?
- Postgres query EXPLAIN on the 10 hottest queries in `core/database.py` — any missing indexes?
- VPS disk: `guardian.db` is 6.6 GB. What's growing? Retention policy?
- Crons that take > 60s — profile them.

### 5. Finish the installer

**Target:** Mac Mini gets a single signed installer. Rob runs it, answers a few questions, everything comes up.

**What's already built (from `share_file` names):**
- 5 installer screens mocked + live-run tested:
  - Screen 1: Welcome (branding, license, "let's go")
  - Screen 2: Pre-flight (Docker present? Postgres port free? Tailscale installed?)
  - Screen 3: Site config (facility name, operator name, Slack channel)
  - Screen 4: AMS connection (pick controller, login, verify)
  - Screen 5: Fleet discovery (scan network, list found miners, confirm)
- Branding system (`mining_guardian_branding_system`)
- Logo candidates

**What's not yet built / needs verification:**
- Screen 6+: AI setup (Qwen model download + license acceptance, Claude API key entry)
- Screen 7: Catalog import (download latest catalog snapshot or start fresh?)
- Screen 8: First scan + Slack test post + "you're live" summary
- Packager: how do we bundle? For Mac, a `.pkg` with the Python runtime embedded? Docker Compose as a single bundle? Signed by Rob's dev cert?
- Uninstaller: rare but required for customer trust
- Updater: how does an installed Mining Guardian pull a new version? Self-update? Homebrew tap? Manual re-run of installer?

**Blocking on:** Mac Mini hardware arrival Monday April 27 to test the actual installer path end-to-end.

### 6. Mac Mini arrives Monday — working this weekend

**Pre-Mac checklist (what we want done before Monday):**
- Raw_json bug closed (item #1a)
- 83-archive batch imported cleanly (item #1b)
- OpenClaw removed (item #2)
- Slack reconfigured to Bolt (item #2)
- Top-down review done (item #3)
- Audit complete or at minimum every CRITICAL + HIGH resolved (item #4)
- Installer screens 6-8 mocked (item #5, partial)

**Day-of-Mac checklist:**
- Bring up Mac Mini with Tailscale, join network
- Install Docker Desktop for Mac
- Run the installer against a freshly wiped user account
- Migrate PC Docker Postgres → Mac Docker Postgres (`pg_dump` + restore, ~15 minutes for 500 MB of catalog data)
- Update Tailscale routes so VPS Mining Guardian queries Mac instead of PC
- Run intelligence report generator pointed at Mac — confirm byte-for-byte identical output
- Decommission PC Docker Postgres (container down, volumes retained as rollback)
- Fix 289 "Gaurdian" typos (Rob's rule — this is the cutover moment to do it)

---

## Tomorrow-Morning Immediate Next Actions

In order. One per turn. Don't skip.

1. **Start new chat, paste path to this document:** `Mining-Guardian-d8cbbdcf/docs/SESSION_HANDOFF_2026-04-24.md`. Also paste `docs/DB_STATE_2026-04-23.md` if the new chat needs database context.
2. **Run the raw_json smoke test** (Rob's side, PowerShell):
   ```
   docker exec -e PGPASSWORD='MiningGuardian2026!' mining-guardian-db psql -U guardian_admin -d mining_guardian -c "INSERT INTO knowledge.field_log_raw_json (entity_label, archive_filename, source_file, parser, raw_payload, sha256, ingested_at) VALUES ('test', 'test.tar', 'test.txt', 'mg_import', '{\"hello\":\"world\"}'::jsonb, 'abc123', NOW()); SELECT COUNT(*) FROM knowledge.field_log_raw_json;"
   ```
   Paste the result into the new chat.
3. **Based on that result:** patch `insert_raw_json()` to either log the real error (if the INSERT works standalone) or fix the table/INSERT (if it fails standalone). Redeploy `mg_import.py.patched` → smoke test one archive → verify `raw_json > 0`.
4. **Wire the SSE progress bar in the UI** (optional but recommended before 83-batch — 15 min of JS).
5. **Run the 83-archive batch.** Watch progress, confirm totals, tag commit.
6. **Proceed to item #2 (OpenClaw removal).**

---

## Key Files & Locations (Quick Reference)

### Repo (this workspace)
- **Path:** `/home/user/workspace/Mining-Guardian-d8cbbdcf/`
- **Remote:** `https://github.com/robertfiesler-spec/Mining-Guardian`
- **Push with:** `api_credentials=["github"]`

### Patched import tool
- **Workspace:** `/home/user/workspace/mg_import.py.patched` (233,601 bytes, compiles clean)
- **On PC:** `C:\Users\User\Mining-Guardian\mg_import_tool\mg_import.py`
- **v3.3 pristine backup on PC:** `C:\Users\User\Mining-Guardian\mg_import_tool\.v33_pristine\`

### PC Docker Postgres
- **Container:** `mining-guardian-db`, up 9+ days
- **Creds:** `guardian_admin` / `MiningGuardian2026!` / db `mining_guardian` / port 5432
- **Command pattern:**
  ```
  docker exec -e PGPASSWORD='MiningGuardian2026!' mining-guardian-db psql -U guardian_admin -d mining_guardian -c "..."
  ```
- **12 schemas:** facility, firmware, hardware, knowledge, market, mg, ops, pool, public, regulatory, repair, seed
- **Known counts:** hardware.miner_models=317, hardware.model_aliases=12,852, mg.model_family_aliases=1,494

### VPS Postgres
- **Database:** `mining_guardian` on VPS local Postgres
- **State:** Empty schema from `migrations/001_initial_schema.sql`, 25 tables, zero rows
- **Use:** Reserved for future real SQLite→Postgres migration (not this weekend)

### VPS production SQLite
- **Path:** `/root/Mining-Gaurdian/guardian.db` (monolithic, ~6.6 GB)
- **Split DB rollback points:** `/root/Mining-Gaurdian/databases/{operational,timeseries,ai_knowledge,audit}.db` (cold, do not delete)

### Flask launcher (PC)
```
cd C:\Users\User\Mining-Guardian\mg_import_tool
.\launch_mg_import.bat
```
Serves on `http://localhost:5050`.

### Archive folder (PC)
- `C:\Users\User\Downloads\Telegram Desktop\` — ~12 Antminer tars, part of the 83-batch
- Smoke-test file: `Antminer_S19_2024-06-27_2024-06-29.tar` (1.7 MB, sha256 `6c5f648e...`)
- AVOID: `Antminer_S19_1970-01-01_2024-11-29.tar` (95 KB, corrupt placeholder)

### Key SQL
**Clean slate (does NOT touch identity or raw_json):**
```sql
DELETE FROM knowledge.field_log_imports;
DELETE FROM knowledge.field_log_pools;
DELETE FROM knowledge.field_log_antminer_boots;
DELETE FROM knowledge.field_log_antminer_autotune;
DELETE FROM knowledge.field_log_events;
DELETE FROM mg.import_runs;
```

**Verification:**
```sql
SELECT 'imports' AS tbl, COUNT(*) FROM knowledge.field_log_imports
UNION ALL SELECT 'identity', COUNT(*) FROM knowledge.field_log_miner_identity
UNION ALL SELECT 'raw_json', COUNT(*) FROM knowledge.field_log_raw_json
UNION ALL SELECT 'pools', COUNT(*) FROM knowledge.field_log_pools
UNION ALL SELECT 'boots', COUNT(*) FROM knowledge.field_log_antminer_boots
UNION ALL SELECT 'autotune', COUNT(*) FROM knowledge.field_log_antminer_autotune
UNION ALL SELECT 'events', COUNT(*) FROM knowledge.field_log_events
UNION ALL SELECT 'import_runs', COUNT(*) FROM mg.import_runs;
```

---

## Active Background Crons (running in my agent layer, not on VPS)

All five save to `/home/user/workspace/cron_tracking/<name>/` and only notify on genuine new intel:

| ID | Purpose | Schedule | Status |
|---|---|---|---|
| 4cc981c0 | Aggregator watcher (Hashrate Index, AsicMinerValue, F2Pool, retailers) | 11:43 daily | Ran clean 2026-04-24 6:49am, no new models |
| 920d0231 | Manufacturer watcher (Bitmain, MicroBT, Canaan, Bitdeer, Auradine) | 11:17 daily | Ran clean 2026-04-24 6:25am, no new models |
| aa676933 | Firmware tracker (vendor + Braiins OS + LuxOS + Vnish) | 12:45 daily | Ran clean 2026-04-24 7:57am, no new firmware |
| c8c4678d | Community scanner (Reddit, X, BitcoinTalk, news, YouTube) | 12:19 daily | **Notified 2026-04-24 7:27am** — LuxOS "Power Targeting" update + S23e hydro rumor |
| ebb3af70 | Deep enrichment sweep | 15:57 Mon-Sat | **Escalated 2026-04-24 11:10am** — Friday batch is ~47 models, too large. Needs schedule restructure (suggest 5 models/day). Escalation not yet actioned. |

**Decision pending for the new chat:** restructure enrichment schedule to 5 models/day, or leave it and focus entirely on the 6-point plan?

---

## Outstanding Technical Debt (Post-Weekend, Not Blocking Installer)

1. Credential rotation (GitHub PAT, Postgres password on PC Docker)
2. Backport the 2 PK ALTERs Mac Claude applied live to `migrations/001_initial_schema.sql`
3. Rename `guardian.db` on VPS → `guardian.db.legacy` once real Postgres migration lands
4. Restore crontab from `/tmp/crontab_backup_2026-04-23.txt` if missing
5. Debug dashboard-api `/metrics` 500 error
6. Fix 289 "Gaurdian" typos (planned for Mac cutover)
7. Update `FIELD_INTELLIGENCE_PIPELINE.md` and `AI_ROADMAP.md` once raw_json bug closes and 83-batch imports cleanly

---

## Shared Asset Name Inventory

These are the `name` tags for file versions shared via the asset system. Reuse the same name when updating — creates version history the user can toggle. Full list kept in the session summary, but the most-relevant ones right now:

- `mining_guardian_session_handoff` — this handoff's predecessor (2026-04-23 version)
- `mg_import_py_patched` — the in-flight patched import tool
- `field_intelligence_pipeline_design` — the Layer 2 design doc
- `mining_guardian_ai_audit` — AI behavior audit
- `intelligence_catalog_schema` + `_v2_additions` + `_v3_additions` — catalog schema evolution
- `installer_screen1_welcome_mockup` through `installer_screen5_fleet_discovery_mockup` (+ `_live_run` and `_sad_live_run` variants) — installer wizard
- `mining_guardian_branding_system` — branding
- `grafana_fixed_main` (+ per_miner, ai_learning, fleet, board_health, pool_stats) — dashboards

---

## One-Line Status For The New Chat

> v3.3 import tool patched, 6 of 7 tables green on smoke test, last bug is isolated to `insert_raw_json()`. Plan forward is: close raw_json → 83-batch → remove OpenClaw + switch Slack to Bolt → architecture walkthrough → full audit → installer finishing touches → Mac Mini arrives Monday, cutover.
>
> Everything needed to continue is in this document or in `docs/DB_STATE_2026-04-23.md` + `docs/OPENCLAW_AUDIT_2026-04-23.md` + `AI_ROADMAP.md`. No Mac Claude. Single agent. Step by step.

---

*End of handoff. Pick this up in the new chat. Rob — when you're ready, just tell the new chat "read `docs/SESSION_HANDOFF_2026-04-24.md` first" and we'll be on the same page instantly.*
