# Postgres Migration — Status 2026-04-24

**Supersedes:** `POSTGRES_MIGRATION_STATUS_2026-04-23.md`
**Last verified live:** 2026-04-24 12:40 CDT
**Status:** Migration functionally complete. All active code paths on Postgres. Fresh-install dry run (Mac Mini deploy prep) still pending.

---

## TL;DR

Every file in active production code paths now reads and writes Postgres. SQLite is gone from the live boot path. The one remaining cleanup is archiving a set of orphaned Phase 1 files (`core/database.py`, `core/database_router.py`, `core/db_compat.py`, `core/db_helper.py`, `core/s19jpro_overheat_handler.py`) that still contain real SQLite code but are not imported by anything live.

**Last SQLite write anywhere:** 2026-04-23 afternoon, before Phase 8 flip.
**Last SQLite-related runtime bug:** today's `llm_analysis` table frozen at 1036 rows from 2026-04-23T00:07:44 through 2026-04-24 ~12:30 (fixed in be25526).

---

## What shipped on 2026-04-24

Six commits, in order. All tested, all pushed.

### 95c001d — morning_briefing GROUP BY + cost_tracker recursion

Two Postgres-strictness bugs that crashed their respective daily crons the first time they ran against Postgres.

**scripts/morning_briefing.py** — had a `SELECT miner_id, model, COUNT(*) FROM ... GROUP BY miner_id` query. SQLite quietly picks an arbitrary `model` per group; Postgres rejects as ambiguous. Fix: added `model` to the `GROUP BY` clause. Same bug class bit us in `ai/train_cohort.py` yesterday and in `ai/confidence_scorer.py::get_fleet_confidence_summary` today.

**monitoring/cost_tracker.py** — a `_get_connection()` helper called itself via a wrapper, hitting Python's recursion limit on first use. Fix: flatten the call chain.

### e4bc8fa — HVAC save_hvac 3-column fix

**Problem:** the Postgres port of `core/database_pg.py::save_hvac` dropped three columns from the INSERT statement: `system_id`, `outside_air_f`, `container_temp_f`. Every HVAC row written since 2026-04-23 had `system_id = NULL`, which meant Grafana panels filtering by `system_id = 'warehouse'` or `'s19jpro'` showed No data. Separately, the S19J Pro container's `container_temp_f` was never landing anywhere.

**Fix:** INSERT now has 17 columns × 17 %s placeholders × 17 values. Also applied `ALTER TABLE hvac_readings ALTER COLUMN system_id SET DEFAULT 'warehouse'` as a safety net. Backfill of the ~50 NULL rows was explicitly declined.

**Verified live:** Warehouse supply=74.18, return=83.55. S19jpro supply=92.94, return=108.53, outside=91.32, container=101.87. See HVAC_ARCHITECTURE.md for the full two-system model.

### ec61cce — AI dashboard stack Postgres conversion

The /ai/dashboard route was returning HTTP 500 since guardian.db was archived. Three files in the rendering chain were still pure SQLite, missed during the Phase 7 sweep:

- api/ai_dashboard_api.py (499 LOC) — the HTML renderer
- ai/ai_score.py (263 LOC) — calculate_score querying 12 tables
- ai/confidence_scorer.py (350 LOC) — per-miner and fleet confidence

All three converted to the `_PgConnWrapper` pattern. Notable bugs hit along the way:

- `datetime(a.timestamp, '+5 minutes')` — SQLite-only, rewrote to `(a.timestamp::timestamp + INTERVAL '5 minutes')`
- `(? IS NULL OR restart_type LIKE ?)` — psycopg2 could not infer parameter type for bare ? in IS NULL. Added explicit `%s::text` cast.
- `SELECT miner_id, ip, model, SUM(...) ... GROUP BY miner_id` — same GROUP BY bug class. Added ip, model to GROUP BY.
- Unescaped % in LIKE patterns — `LIKE '%PREEMPTIVE%'` to `LIKE '%%PREEMPTIVE%%'` for psycopg2.

**Verified live:** GET /ai/dashboard returns HTTP 200 in 1.3s with 205k chars of HTML, zero error markers. Score total = 83,799. Fleet confidence summary covers 56 miners.

### be25526 — core/llm_analyzer.py Postgres conversion

**Critical hidden bug.** The `llm_analysis` audit table had been frozen at 1036 rows since 2026-04-23T00:07:44 because `core/llm_analyzer.py` was still pure SQLite and every INSERT silently crashed against the archived guardian.db. The Qwen/Claude responses themselves still made it into knowledge.json via KnowledgeManager, but the per-call audit trail (what prompt, what response, what model, how long) was being lost for 24 hours.

Tonight's midnight weekly_train would have been the second midnight in a row losing audit rows.

**Scope:** 330 lines, 4 sqlite3.connect sites, 3 INSERT statements (deep_analyze, analyze_issues, analyze_single_miner), 1 _ensure_table method, 8 ? placeholders. Imported by 18 files (6 production, rest are scripts/tests).

**Conversion pattern differs from Phase 7:** this file is write-only (no fetchone/fetchall to preserve), so instead of _PgConnWrapper it uses raw psycopg2.connect() + with conn.cursor() + try/finally close(). Simpler.

**Verified live:** Instantiated LLMAnalyzer(), monkey-patched _query_claude and _query_llm to return mock responses, exercised deep_analyze and analyze_issues end-to-end, both wrote rows successfully (ids 1038 and 1039), then cleaned up test rows.

**What to check tomorrow morning:** SELECT COUNT(*), MAX(analyzed_at) FROM llm_analysis. Count should have jumped from 1036 to ~1080+ after tonight's midnight weekly_train.

### 126f1c7 — dead import sqlite3 cleanup

Three files had bare `import sqlite3` lines with no remaining usages: ai/llm_scan_hook.py, api/trends_api.py, core/mining_guardian.py. Also updated a stale docstring in mining_guardian.py line 1966 describing the old SQLite WAL thread-safety model.

### (next commit) — GUARDIAN_PG_DBNAME env var consistency

**Found during documentation audit** — today's four conversions (llm_analyzer, ai_score, confidence_scorer, ai_dashboard_api) were written using `os.environ.get('GUARDIAN_PG_DB', 'mining_guardian')`. The rest of the codebase (all Phase 7 files) and the actual .env and crontab use `GUARDIAN_PG_DBNAME`. Today's files happened to work by coincidence — they fell through to the 'mining_guardian' default — but the inconsistency would have broken anything running against a non-default DB name. Fixed by renaming GUARDIAN_PG_DB to GUARDIAN_PG_DBNAME in all 4 files.

---

## Current system state

### 8 systemd services (all active, all on Postgres)

- approval-api.service :8686 — Slack approval webhook
- dashboard-api.service :8585 — Retool + /ai/dashboard
- grafana-server.service :3000 — Grafana
- mining-guardian-alerts.service — AMS WebSocket alert listener
- mining-guardian.service — Main scan loop (hourly)
- overnight-automation.service — 8pm-6am auto-execute low-risk
- prometheus.service :9090 — Metrics
- slack-commands.service — Slack slash commands
- slack-listener.service — Slack events API

### Cron jobs

- daily 4am: ai/backup_knowledge.py
- daily 7am: scripts/morning_briefing.py
- daily 1pm: scripts/direct_collect_logs.py
- daily 4pm: ai/daily_deep_dive.py
- daily 4:15p: scripts/daily_log_failure_report.py
- daily 12am: ai/weekly_train.py

Cron's env block defines `GUARDIAN_PG_DBNAME=mining_guardian` (and matching HOST/PORT/USER/PASSWORD). Every script now reads this consistently.

---

## What's left

### Before Monday Mac Mini deploy (hard deadline)

**Fresh-install dry run.** Not yet done. The Mac Mini installer will: drop any existing mining_guardian Postgres DB, recreate it from migrations/001_initial_schema.sql, git pull the repo, start the 8 services. If any service fails to come up against a clean empty schema, we find out at the worst possible moment.

**Runbook:** see MAC_MINI_DEPLOYMENT_RUNBOOK.md for the full procedure. The runbook itself is documented; the dry run has not been executed yet.

### Deferred (not blocking)

**Orphaned Phase 1 files.** Five files still contain real SQLite code but are not imported by any live module:

- core/database.py (old GuardianDB class — pre-migration)
- core/database_router.py (Phase 1 multi-DB routing, reverted)
- core/db_compat.py (Phase 1 compatibility shim)
- core/db_helper.py (Phase 1 connection helper)
- core/s19jpro_overheat_handler.py (orphaned; overheat logic now in mining_guardian)

Leaving them is safe (nothing imports them) but confusing for future readers. Recommended archival: move to archive/phase1_sqlite_2026-04-24/ with a README noting why. Low urgency.

**HVAC client SQLite fallback cache.** clients/hvac_client.py still tries to read a fallback cache from the deleted guardian.db via a try/except that now silently fails. Produces 'no such table: hvac_readings' on stderr every scan. Cosmetic noise, not functional — live polling works fine.

**The 24-hour llm_analysis gap.** Rows from 2026-04-23T00:07:44 through 2026-04-24 ~12:30 do not exist. ~50 lost audit rows. Not recoverable without the actual prompts/responses that went to Qwen/Claude. The knowledge they produced is preserved in knowledge.json; only the per-call audit trail is missing.

---

## References

- docs/HVAC_ARCHITECTURE.md — the two-system model (warehouse + s19jpro), low delta-T operator rule, Grafana dependency on system_id
- docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md — step-by-step Monday install procedure
- docs/POSTGRES_MIGRATION_PLAN_2026-04-23.md — the Phase 1-8 migration plan (historical)
- docs/POSTGRES_MIGRATION_STATUS_2026-04-23.md — previous status doc, **this file supersedes it**
- migrations/001_initial_schema.sql — canonical Postgres schema
