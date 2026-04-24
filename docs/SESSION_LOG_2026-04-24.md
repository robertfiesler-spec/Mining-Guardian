# Session Log — 2026-04-24

**Operator:** Bobby Fiesler (BigBobby)
**Agent:** Claude (via Desktop Commander)
**Session duration:** ~10am CDT through ~2pm CDT
**Commits shipped:** 9 on origin/main (one from parallel Perplexity session, 8 from this session)
**Context:** Full-day migration cleanup + pre-Monday Mac Mini deploy prep

---

## TL;DR

The Postgres migration started yesterday (2026-04-23) was functionally complete this morning but three legacy paths still pointed at the archived `guardian.db`: the AI dashboard stack, core/llm_analyzer.py, and the daily HVAC INSERT. Each crashed silently rather than erroring loudly because the try/except blocks were swallowing. All three were fixed in discrete commits. A late-afternoon conversation surfaced that `core/mining_guardian.py` was still pulling logs through AMS despite the operator having moved away from AMS log exports weeks ago due to reliability problems. That path was converted to direct HTTP, unifying it with the existing 1pm cron approach. Three documentation files were created mid-session and one was created at session end to capture everything for Monday handoff.

---

## Opening state (2026-04-24 ~10am CDT)

- **VPS:** Hostinger KVM 8 at 187.124.247.182, 8 systemd services active, all on Postgres
- **Origin HEAD:** 95c001d ("fix: morning_briefing GROUP BY + cost_tracker recursion" — shipped overnight)
- **Known issue going in:** llm_analysis table frozen at 1036 rows since 2026-04-23T00:07:44 (silent INSERT failures against archived guardian.db)
- **AMS state:** transient — 0 online / 55 offline in scans 1714-1718 (hub issue)
- **Deadline:** Mac Mini arrives Monday 2026-04-27 (original memory said 04-28, corrected during this session)

---

## Commits shipped this session (chronological)

### 1. e4bc8fa — fix(hvac): write system_id, outside_air_f, container_temp_f in save_hvac

**Problem identified:** Operator reported HVAC dashboards showing "No data" in Grafana despite the scan loop running. Investigation revealed `core/database_pg.py::save_hvac` INSERT had 14 columns while the table schema had 18. Three missing:
- `system_id` — the label distinguishing warehouse vs s19jpro. NULL everywhere since 2026-04-23.
- `outside_air_f` — outside air temp from the s19jpro controller
- `container_temp_f` — interior container temp from the s19jpro controller. Had never landed since the Postgres port.

**Investigation path:**
1. `\d hvac_readings` on live Postgres → showed 18 columns with `system_id text DEFAULT NULL`
2. Queried last 10 hvac_readings → every row had `system_id = NULL`, and every OTHER row had only `return_temp_f` populated (no supply, no container)
3. Read HVACSnapshot dataclass in `clients/hvac_client.py` → dataclass has all three fields, correctly populated by poll_all_systems_with_db_fallback
4. Read save_hvac INSERT → only 14 columns, dropping three

**Fix:**
- INSERT grew from 14 to 17 columns × 17 %s × 17 values
- Added `sys_id = getattr(hvac, "system_id", None) or "warehouse"` fallback for safety
- Applied `ALTER TABLE hvac_readings ALTER COLUMN system_id SET DEFAULT 'warehouse'` as a DB-level safety net
- Backfill of ~50 historical NULL rows from Apr 23 through Apr 24 12:30 was **explicitly declined by operator** — those rows remain NULL, creating a ~24h gap in Grafana last-7d panels that heals automatically as time rolls forward

**Verification:**
- Mining-guardian restarted at 12:01 CDT, first scan after restart wrote both systems correctly
- Warehouse: supply=74.18, return=83.55
- S19jpro: supply=92.94, return=108.53, outside=91.32, **container=101.87 (first time ever landing)**

**Related documentation:** see `HVAC_ARCHITECTURE.md` for the full two-system model.

---

### 2. ec61cce — fix(postgres): convert AI dashboard stack to psycopg2

**Problem identified:** Operator reported `/ai/dashboard` endpoint returning 500. Investigation showed three files in the rendering chain were still pure SQLite, missed during yesterday's Phase 7 sweep:
- `api/ai_dashboard_api.py` (499 LOC) — the HTML renderer, entry point from `dashboard-api` service at `/ai/dashboard` route
- `ai/ai_score.py` (263 LOC) — `calculate_score()` aggregates across 12 tables
- `ai/confidence_scorer.py` (350 LOC) — per-miner + fleet-wide confidence scoring

**Investigation path:**
1. `grep -c 'sqlite3\\.connect' api/ai_dashboard_api.py` → 1 site
2. `grep -c 'sqlite3\\.connect' ai/ai_score.py` → 1 site with conn=None fallback logic
3. `grep -c 'sqlite3\\.connect' ai/confidence_scorer.py` → 1 site, 7 ? placeholders
4. Manual `curl -s http://localhost:8585/ai/dashboard` → HTTP 500, traceback in dashboard-api journal

**Fix pattern (same as all Phase 7 files):**
- Replaced `import sqlite3` + `DB_PATH` with `import psycopg2` + `_pg_dsn()` + `_PgConnWrapper` class
- `_PgConnWrapper` mimics sqlite3.Connection's `.execute(sql, params)` shortcut (returns cursor) using DictCursor rows for integer+name indexing compatibility
- `sqlite3.connect(DB_PATH)` → `_PgConnWrapper(psycopg2.connect(_pg_dsn()))`

**Bugs encountered during conversion (all fixed in the same commit):**
- `datetime(a.timestamp, '+5 minutes')` — SQLite-only function. Rewrote to `(a.timestamp::timestamp + INTERVAL '5 minutes')`. One instance in `get_recent_auto_actions` LEFT JOIN.
- `(? IS NULL OR restart_type LIKE ?)` — psycopg2 could not infer parameter type for bare `?` in `IS NULL` comparison. Fix: explicit `(%s::text IS NULL OR restart_type LIKE %s)`. Two instances.
- `SELECT miner_id, ip, model, SUM(...) ... GROUP BY miner_id` — same bug class as morning_briefing yesterday. Postgres rejects non-aggregated columns not in GROUP BY. Fix: added `ip, model` to GROUP BY in `get_fleet_confidence_summary`.
- Unescaped `%` in LIKE patterns — three instances of `LIKE '%PREEMPTIVE%'` needed to become `LIKE '%%PREEMPTIVE%%'` for psycopg2's parameter formatter.
- Removed `sqlite3.Connection` type hints on internal helper functions (non-essential, cleaner without the dependency).

**Verification:**
- `render_ai_dashboard_html()` produced 205,181 chars with zero error markers
- `get_fleet_confidence_summary()` returned 56 miners
- `calculate_score()` returned total_score=83,799 (was 0 before fix)
- Direct HTTP: `curl -sw 'HTTP %{http_code} | %{size_download} bytes | %{time_total}s' http://localhost:8585/ai/dashboard` → `HTTP 200 | 205861 bytes | 1.267s`

---

### 3. be25526 — fix(postgres): convert core/llm_analyzer.py to psycopg2

**CRITICAL HIDDEN BUG — this was the biggest find of the session.**

**Problem:** The `llm_analysis` audit table had been frozen at 1036 rows since 2026-04-23T00:07:44. Every LLM call for 24 hours — today's daily deep dive at 4am, this morning's weekly_train, every Slack /analyze command — had silently crashed writing to the archived guardian.db. The Qwen/Claude response text still made it into knowledge.json via KnowledgeManager, but the per-call audit trail (what prompt, what response, what model, how long) was being lost.

**Scope of affected file:**
- `core/llm_analyzer.py` (330 lines)
- 4 `sqlite3.connect` sites: `__init__`, `_ensure_table`, `deep_analyze`, `analyze_issues`, `analyze_single_miner`
- 3 INSERT statements (all write to llm_analysis)
- 1 `_ensure_table()` with `CREATE TABLE IF NOT EXISTS` using `INTEGER PRIMARY KEY AUTOINCREMENT` (SQLite-only)
- 8 `?` placeholders
- Imported by 18 files in the repo; 6 are in production (train_cohort, train_llm, train_llm_pass2, train_comprehensive, slack_command_handler, daily_deep_dive)

**Conversion pattern — different from the Phase 7 _PgConnWrapper approach:**
This file is 100% write-only (no fetchone/fetchall patterns to preserve), so instead of _PgConnWrapper it uses raw `psycopg2.connect()` + `with conn.cursor()` + `try/finally close()`. Simpler, fewer moving parts, matches the context-managed pattern used in save_hvac.

**Specific changes:**
- Top-of-file: `import sqlite3` → `import psycopg2` + `from psycopg2.extras import DictCursor`
- `DB_PATH` kept as "postgres" sentinel to preserve constructor signature (multiple callers pass db_path positionally via default)
- `_ensure_table` DDL changed from `INTEGER PRIMARY KEY AUTOINCREMENT` to `SERIAL PRIMARY KEY`; the CREATE TABLE IF NOT EXISTS is idempotent against the existing Postgres table which already has the correct schema from `migrations/001_initial_schema.sql`
- 8 `?` → `%s`

**Verification methodology — monkey-patched LLM clients to avoid calling real services:**
- Instantiated `LLMAnalyzer()` → _ensure_table ran, no-op against existing table
- Monkey-patched `_query_claude` to return `('mocked response', 42, 'smoke-test-model')`
- Called `deep_analyze('test prompt')` → wrote row id=1038 with `model_used='smoke-test-model'`, `duration_ms=42`
- Monkey-patched `_query_llm` to return `('mocked fleet response', 55)`
- Called `analyze_issues(9999, [...])` → wrote row id=1039 with `scan_id=9999`, `miner_id='fleet'`
- Both test rows confirmed in DB via direct psql query, then DELETEd
- All 5 production callers imported successfully via importlib

**Services restarted to pick up new code:** mining-guardian (llm_scan_hook uses LLMAnalyzer during scans), slack-commands (/analyze slash command uses it). Both active.

**What to check tomorrow:** `SELECT COUNT(*), MAX(analyzed_at) FROM llm_analysis`. Count should jump from 1036 to ~1080+ after tonight's midnight weekly_train exercises all three INSERT paths for real.

---

### 4. 126f1c7 — cleanup: remove dead import sqlite3 from 3 active files

**Problem:** Operator asked for dead `import sqlite3` cleanup. Memory-from-context had listed 5 candidate files but investigation showed only 3 were actually dead imports (the other 5 were orphaned files with real SQLite code, not bare imports — those are Phase 1 leftover cleanup deferred to a separate archival pass).

**Files with truly dead bare imports:**
- `ai/llm_scan_hook.py` — `import sqlite3` with zero usages
- `api/trends_api.py` — `import sqlite3` with zero usages
- `core/mining_guardian.py` — `import sqlite3` with zero usages + one stale docstring on line 1966 describing the old WAL thread-safety model

**Fix:** `sed -i '/^import sqlite3$/d'` on all three. Updated the mining_guardian docstring to describe the current per-call psycopg2 pattern.

**Deferred (5 truly-orphaned files — real SQLite code, no live imports, NOT touched this session):**
- `core/database.py` — the old GuardianDB class (pre-migration)
- `core/database_router.py` — Phase 1 multi-DB routing, reverted
- `core/db_compat.py` — Phase 1 compatibility shim
- `core/db_helper.py` — Phase 1 connection helper
- `core/s19jpro_overheat_handler.py` — orphaned overheat logic, folded into mining_guardian

These are safer as a dedicated archive pass post-Monday.

**Verification:** All three modified files compile, import cleanly, and mining-guardian restarted without issue.

---

### 5. b8acfbe — cleanup: standardize on GUARDIAN_PG_DBNAME env var

**CAUGHT DURING DOCUMENTATION AUDIT.** Operator asked "is everything documented?" and while writing POSTGRES_MIGRATION_STATUS_2026-04-24.md I noticed the four files I converted today used `os.environ.get('GUARDIAN_PG_DB', 'mining_guardian')` while everything else in the codebase — Phase 7 files, `.env`, the crontab — uses `GUARDIAN_PG_DBNAME`.

The four files happened to work by accident because when `GUARDIAN_PG_DB` is not set they fell through to the `'mining_guardian'` default. But anything running against a non-default DB name — crucially, the upcoming `mining_guardian_dryrun` scratch DB used for the Monday fresh-install dry run — would have silently connected to the wrong database.

**Fix:** Renamed `GUARDIAN_PG_DB` → `GUARDIAN_PG_DBNAME` in:
- `core/llm_analyzer.py`
- `ai/ai_score.py`
- `ai/confidence_scorer.py`
- `api/ai_dashboard_api.py`

**Verification:** All four files compile. Services restarted (dashboard-api, mining-guardian, slack-commands). AI dashboard still renders 205k chars. Fleet summary still 56 miners. AI score = 83,799.

**Lesson:** this one is in the ledger because the bug was found by documentation, not by an error. If operator had not asked for docs, the Monday fresh-install dry run would have failed mysteriously.

---

### 6. ecf2322 — docs: 2026-04-24 migration status + HVAC architecture + Mac Mini runbook

Three new documentation files written mid-session:

1. **`docs/POSTGRES_MIGRATION_STATUS_2026-04-24.md`** — supersedes yesterday's status doc which was marked "final" this morning before four more conversions shipped
2. **`docs/HVAC_ARCHITECTURE.md`** — evergreen reference for the two-HVAC-system model, with the operator rule about low delta-T being intentional
3. **`docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md`** — step-by-step Monday procedure, pre-flight dry run, cutover order, known gotchas, emergency rollback

---

### 7. 181acc1 — docs: fix Mac Mini deploy date to Monday 2026-04-27

Runbook had written 04-28. Parallel session's `SESSION_HANDOFF_2026-04-24.md` had 04-27. Operator confirmed 04-27 is correct (Monday). One-character sed fix.

---

### 8. 8191aa6 — refactor(logs): eliminate AMS log path, direct HTTP only

**The biggest architectural change of the session.** After operator clarified the backstory — "we don't download through AMS anymore, it was failing, it would take 4 hours and only download 5 logs" — we converted every remaining AMS-based log call to direct HTTP.

**Two-phase refactor in one commit:**

**Phase 1 — `_collect_logs_nonblocking` (pre/post restart pairing, 6 call sites):**
- Completely rewrote the helper to use `HTTPDigestAuth('root', 'root')` and POST to `http://{ip}/cgi-bin/create_log_backup.cgi` with a JSON body like `["/2026-04/24"]`
- Response format: `{"stats": "success", "code": "L000", "msg": "Antminer_S19j_Pro_2026-04-24.tar.bz2"}` — the msg field is the filename to download from `http://{ip}/log/{filename}`
- Extract `miner.log` from the tar, pass to existing `self.db.save_logs(miner_id, model, label, {filename: content})`
- Signature grew to accept `ip: str = ""` — if caller does not provide it, helper falls back to looking up the most recent IP from `miner_readings` via self.db._connect()
- Pre/post pairing is preserved via the `label` parameter as before — `save_logs` writes the label as `health_status`, the AI pairs by matching labels across the two rows

**Phase 1 call sites updated (6 total):**
- `execute_board_restart` line 840 (pre-restart-board-check) and line 882 (post-restart-board-check)
- `execute_restart` line 1215 (pre-restart) and line 1285 (post-restart)
- `execute_pdu_cycle` line 1544 (pre-pdu-cycle) and line 1617 (post-pdu-cycle)

All six callers had `ip` available locally from the `issue: Dict[str, Any]` parameter.

**Phase 2 — `collect_logs()` method body replaced with no-op:**
- The original body (~180 lines) spawned a background thread on EVERY hourly scan to pull fresh AMS log exports for every online miner in parallel with 15 workers, with a 10-minute per-miner timeout, plus a retry pass with 20-minute timeout, plus a tracked-retry pass — three layers of retries because the AMS path was never reliable
- Replaced with a debug-log no-op. `scripts/direct_collect_logs.py` (the 1pm cron) is now the SOLE owner of daily baseline log collection
- The method signature and docstring are preserved so `run_once()` at line 2281 still calls `self.collect_logs(miners, issues)` — it just immediately returns

**Impact:**
- 183 net lines removed from core/mining_guardian.py (145 added, 328 deleted)
- Zero AMS log API calls remaining in core/mining_guardian.py
- Every hourly scan no longer spawns a background AMS log thread that would consume a WebSocket connection and potentially block for up to 20 minutes
- Pre/post restart pairs now complete in ~30-60s (direct HTTP) instead of 2+ minutes (AMS export + poll cycle)

**Smoke testing methodology:**
Real miner 53499 at `192.168.188.125` (known-healthy S19JPro):
- Test 1 — explicit IP path: returned 1 file (`nvdata/2026-04/24/cglog_init_2026-04-24_00-00-31/miner.log`), 673,647 bytes, row id=2098 persisted, confirmed via direct psql
- Test 2 — IP fallback via DB lookup: `ip=""` passed, helper queried `miner_readings WHERE miner_id=53499 ORDER BY id DESC LIMIT 1`, got `192.168.188.125`, returned 670,035 bytes, row persisted
- Test rows cleaned up via `DELETE FROM miner_logs WHERE health_status LIKE 'smoke%'`

**Services restarted:** mining-guardian, overnight-automation. Both active.

**Retained intentionally (not touched):** `scripts/cleanup_ams_logs.py` — this script is for cleaning up old log archives on the AMS server side, not for runtime log collection. Harmless.

---

## Parallel commit from the other session

### 96a7ea3 — docs: master session handoff 2026-04-24 for fresh chat pickup

**Not from this agent.** Rob's parallel Perplexity session committed this while this session was working. Pure documentation (new file: `docs/SESSION_HANDOFF_2026-04-24.md`, 399 lines). No code conflicts. Required a `git pull --rebase origin main` before pushing `ecf2322` but rebase was clean (different files).

That doc describes Rob's 6-point plan (Field Intelligence DB + 83-archive re-import, remove OpenClaw + switch Slack to Bolt Socket Mode, top-down architecture review, full audit, installer screens 6-8 + packaging, Mac Mini cutover Monday April 27). None of those items overlap with this session's work.

---

## Non-committed work (side quests)

### Amshub Pi restart

Early in the session the operator reported AMS showing 0 online / 55 offline across scans 1714-1718. Investigation via SSH to 192.168.188.30 (bixbit/bixbit) found the amshub binary had died inside its tmux session. Restart:

```
ssh bixbit@192.168.188.30
tmux attach -t hub
# (restart the binary — exact command lives on the Pi)
# Ctrl+B d to detach
```

Verified recovery: within 2 minutes AMS cloud showed 49/55 miners online. No commit needed — this is Pi-side operations, not repo code. **Important rule preserved:** Do NOT install a systemd unit for amshub without coordinating with the Pi's programmer (currently on vacation). The tmux model is intentional.

### AMS session staleness (the "6 miners back online" issue)

Operator reported that 6 warehouse miners previously offline were now back online and asked to confirm they'd be scanned going forward. Screenshot from AMS UI showed: **62 total miners, 52 ON, 10 OFF, 8.47 PH/s**. But mining-guardian DB scans 1719-1722 were showing only 56 total miners.

**Root cause diagnosed:** long-running AMS WebSocket sessions hold a workspace snapshot that does not automatically refresh when AMS surfaces new or recovered miners. A fresh-token script test via `AMSClient.get_miners()` immediately returned 62 miners. Mining-guardian had been running since 12:01 CDT with a stale workspace view.

**Fix:** `systemctl restart mining-guardian`. Scan 1723 at 13:13 CDT wrote 62 total, 52 online, 10 offline — exact match with AMS UI. Restarted all 6 services with AMS sessions: mining-guardian, mining-guardian-alerts, slack-listener, slack-commands, overnight-automation, approval-api. All active on fresh tokens.

**Documented in:** AMS_INTEGRATION.md (see the "session staleness" section).

### Log collection architecture conversation

Operator clarified that `scripts/direct_collect_logs.py` is the right pattern (direct HTTP) and that the AMS `/log/export` path had been abandoned weeks ago due to 4-hour stuck exports and 5-of-N success rates. This led to the Phase 1+2 refactor in commit 8191aa6 above. No separate code shipped from this conversation — the fix IS the refactor.

### Documentation audit

Operator asked "is everything documented?" — honest answer was no, docs/ folder had not been updated since 10:46am this morning. That triggered three new docs (`POSTGRES_MIGRATION_STATUS_2026-04-24.md`, `HVAC_ARCHITECTURE.md`, `MAC_MINI_DEPLOYMENT_RUNBOOK.md`) and the discovery of the GUARDIAN_PG_DB env var bug — which is itself a worked example of "documentation finds bugs."

---

## Cumulative deferred items (entering 2026-04-25 morning)

**Monday blocker:**
1. **Fresh-install dry run** against a scratch `mining_guardian_dryrun` Postgres DB. Procedure documented in `docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md` section "Pre-flight 1. Fresh-install dry run (CRITICAL)". Not yet executed. If any service fails to come up against a clean empty schema, we find out Monday at the worst possible moment.

**Non-blocking cleanup:**
2. **Archive orphaned Phase 1 files** (`core/database.py`, `core/database_router.py`, `core/db_compat.py`, `core/db_helper.py`, `core/s19jpro_overheat_handler.py`) into `archive/phase1_sqlite_2026-04-24/`. Safe now (no live imports) but could cause confusion or accidental re-imports.
3. **HVAC client SQLite fallback cache.** `clients/hvac_client.py` still tries to read a fallback cache from the deleted guardian.db via try/except that now silently fails. Produces "no such table: hvac_readings" on stderr every scan. Cosmetic noise, not functional.
4. **Add `idx_hvac_readings_system_recorded` index** for Grafana panel query performance. `CREATE INDEX IF NOT EXISTS idx_hvac_readings_system_recorded ON hvac_readings (system_id, recorded_at);` — optimization not correctness.
5. **Merge HVAC_SYSTEMS.md (2026-04-21) and HVAC_ARCHITECTURE.md (2026-04-24)** or at least cross-reference them. Both exist, slight overlap, neither links the other.
6. **Build `slack_actions_handler.py` replacement** that routes through local channels (VPS-only today via OpenClaw; Mac Mini has no public ingress so needs alternative before cutover).

**Operator rules locked this session (do NOT override):**
- No temp flag/warning below 84°C — 76°C yellow is display-only
- HVAC delta-T at USA 188 is intentionally low and correct — never recommend HVAC investigation for low delta-T
- Amshub Pi tmux model is intentional, do NOT install systemd unit without the Pi programmer
- All log collection goes through direct HTTP now — no new code should call ams.collect_fresh_miner_logs or ams.collect_miner_logs
- GUARDIAN_PG_DBNAME is the canonical env var name (not GUARDIAN_PG_DB)
- Mac Mini path has both a space AND the typo: `/Users/BigBobby/Documents/GitHub/Mining Gaurdian` — always quote

---

## Session metrics

- **Commits authored here:** 8 (e4bc8fa, ec61cce, be25526, 126f1c7, b8acfbe, ecf2322, 181acc1, 8191aa6)
- **Commits from parallel session:** 1 (96a7ea3)
- **Origin HEAD at session end:** 8191aa6 — but will change once this log is added
- **Lines of Python changed:** +145 / -328 (net -183 in mining_guardian.py alone) plus 4 files each with +_pg_dsn / +_PgConnWrapper boilerplate
- **Lines of docs added:** ~900 across 4 new files + this session log
- **Services restarted:** mining-guardian (3x), dashboard-api (1x), slack-commands (2x), slack-listener (1x), overnight-automation (2x), approval-api (1x), mining-guardian-alerts (1x) — plus Pi-side amshub binary restart
- **Test suite:** 48/48 passing on every commit via pre-commit hook
- **Fleet state at session end:** 62 miners total, 52 online, 10 offline (matches AMS UI exactly)
