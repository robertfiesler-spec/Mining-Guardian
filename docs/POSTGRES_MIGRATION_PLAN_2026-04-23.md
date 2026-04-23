# Postgres Migration Plan — 2026-04-23 (R&D)

**Status:** In progress
**Mode:** R&D — production services will be stopped for the duration. Not a race.
**Goal:** Replace SQLite with Postgres as the sole database backend for Mining Guardian on this VPS, by end of session.

---

## Prerequisites already complete (from earlier today)

  - Postgres service running on VPS, reachable at localhost:5432
  - Database `mining_guardian` exists, owned by `guardian_app`
  - Full schema loaded from `migrations/001_initial_schema.sql` (25 tables)
  - Data fully migrated from `guardian.db` to Postgres (0-row drift as of ~06:50 CDT)
  - `core/database_pg.py` adapter exists with 8 methods ported
  - Scratch test harness at `/tmp/scratch_pg_test.py` validates those 8 methods against a fresh `mining_guardian_test` database — 7/7 PASS

## Scope confirmation

Methods called by any of the 8 running services (audited 2026-04-23 ~07:10 CDT):

**Services that call GuardianDB methods directly:**
  - `core/mining_guardian.py` — main scan loop, 26 methods
  - `notifiers/slack_notifier.py` — 2 additional methods
  - `api/ams_alert_listener.py` — 4 additional methods

**Services that do NOT call GuardianDB methods (use raw SQL or don't touch DB):**
  - `api/dashboard_api.py`
  - `api/approval_api.py`
  - `ai/local_llm_analyzer.py`
  - `ai/daily_deep_dive.py`
  - (these services will still need env vars to point raw queries at Postgres)

Total distinct methods to ensure work on Postgres: **32**
Already ported: 8
Remaining to port: **24**
Methods NOT called by any running service, will NOT be ported today: `get_audit_log`, `get_discoveries`, `acknowledge_discovery`, `needs_ticket`, `resolve_dead_boards`, `get_hardware_identity`. They exist in `core/database.py` for future/operator use; if they're ever called later we add them then.

Methods called only from operator scripts (not the scan loop), we port if quick, defer if complex:
  - `parse_and_save_hardware` (only `manual_log_upload.py` calls this) — defer
  - `parse_log_metrics` (called by `save_logs` conditionally) — port as warning-stub

**Important scope expansion (08:40 CDT):** 57 files use `sqlite3.connect` directly, not via `GuardianDB`. Of those, ~10 are production-critical (systemd services + AI cron jobs). Each needs its SQL converted from SQLite syntax (`?` placeholders, `PRAGMA`, `cur.lastrowid`) to Postgres syntax (`%s`, `information_schema`, `RETURNING id`). This was not in the original Option A estimate. New realistic scope: 8-12 hours, which Bobby has approved.

## Phase list (revised 08:40 CDT after discovering raw-sqlite3 scope)

After Phase 2 completed, a fuller audit showed 57 files use `sqlite3.connect()` directly, bypassing GuardianDB. Of those, ~10 run as systemd services or critical cron jobs and must be converted to Postgres before flip. The phase list has been expanded accordingly.

  1. **Pre-flight audit** — Postgres schema matches SQLite (COMPLETE)
  2. **Stop all 8 services** (COMPLETE — R&D downtime in effect)
  3. **Port trivial GuardianDB methods** (batch 1, ~11 small methods)
  4. **Port medium GuardianDB methods** (batch 2, ~8 methods)
  5. **Port complex GuardianDB methods** (batch 3, save_X_readings + record_restart + register_dead_boards)
  6. **Stub/defer remaining GuardianDB methods** (parse_log_metrics stub, parse_and_save_hardware skip)
  7. **Convert raw-sqlite3 service files to psycopg2** — one file per commit:
      - `api/ams_alert_listener.py` (4 DB methods + table init)
      - `api/dashboard_api.py`
      - `api/approval_api.py`
      - `api/slack_approval_listener.py`
      - `api/slack_command_handler.py`
      - `api/intelligence_report_api.py`
      - `core/overnight_automation.py`
      - `core/db_helper.py` / `core/db_compat.py` (if imported by above)
      - `ai/local_llm_analyzer.py` (runs as midnight cron, blocks deep-dive)
      - `ai/daily_deep_dive.py` (4pm cron, blocks AI pipeline)
  8. **Flip imports** in `core/mining_guardian.py`, `notifiers/slack_notifier.py`, `scripts/morning_briefing.py`
  9. **Configure systemd env vars** so services can reach Postgres
  10. **Run test suite + scratch_pg_test** — gate before any service restart
  11. **Final catch-up migration** from guardian.db to Postgres
  12. **Start mining-guardian first**, watch one scan cycle complete in Postgres
  13. **Start remaining 7 services**, watch for errors
  14. **Post-flip verification** — compare write paths, Slack notifications, dashboard
  15. **Documentation + crontab restore** — update NEXT_SESSION.md, `crontab /tmp/crontab_backup_2026-04-23.txt`

---

## Phase log

### Phase 0 — Plan written
- **Status:** ✅ Complete
- **Start:** 2026-04-23 ~07:15 CDT
- **End:** 2026-04-23 ~07:20 CDT
- **Output:** this document

### Phase 1 — Pre-flight audit
- **Status:** ✅ Complete
- **Start:** 2026-04-23 ~07:22 CDT
- **End:** 2026-04-23 ~07:25 CDT
- **Actions taken:**
  - Listed all 25 tables present in Postgres `mining_guardian` schema
  - Compared SQLite `guardian.db` and Postgres column-by-column for 23 tables (all the tables our code writes to)
- **Finding:** Zero schema drift. Every column in SQLite is present in Postgres. Today's migrations (pending_approvals.confidence_score/gate, hvac_readings.system_id/outside_air_f/container_temp_f) are already applied to Postgres. The `maintenance_windows` table, which I flagged earlier as only created by `api/maintenance_scheduler.py`, is already present in Postgres via `migrations/001_initial_schema.sql`.
- **Outcome:** No schema changes needed before the flip. Proceed to Phase 2.


### Phase 2 — Stop all services + disable crontab
- **Status:** ✅ Complete
- **Start:** 2026-04-23 08:27:00 CDT
- **End:** 2026-04-23 08:27:30 CDT
- **Actions taken:**
  - Stopped 8 systemd services in order: mining-guardian, dashboard-api, approval-api, slack-listener, slack-commands, overnight-automation, mining-guardian-alerts, intelligence-report
  - Verified all 8 show `inactive` via `systemctl is-active`
  - Backed up root crontab to `/tmp/crontab_backup_2026-04-23.txt` (37 lines)
  - Cleared root crontab with `crontab -r` to prevent scheduled jobs from firing mid-migration
- **R&D downtime start:** Thu Apr 23 08:27:15 CDT 2026
- **Outcome:** No processes are writing to guardian.db or Postgres right now. Safe to do anything.
- **Rollback action if needed:** `crontab /tmp/crontab_backup_2026-04-23.txt` restores the schedule; `systemctl start <service>` for each brings the services back.


### Phase 3 — Port trivial GuardianDB methods
- **Status:** ✅ Complete
- **Start:** 2026-04-23 ~08:42 CDT
- **End:** 2026-04-23 ~08:58 CDT
- **Commits:** df096fa (schema index fix), 95c5f41 (Phase 3 methods)
- **Actions taken:**
  - Audited the 11 trivial methods originally listed. Confirmed 4 of them (has_seen, record_seen, in_cooldown, set_cooldown) are NOT GuardianDB methods — they live in api/ams_alert_listener.py and use raw sqlite3. They'll be handled in Phase 7 along with that file's full conversion.
  - Ported 7 real GuardianDB trivial methods to core/database_pg.py: _latest_scan_id, has_known_dead_boards, mark_ticket_created, mark_ticket_noticed, get_newly_ticketed, is_elevated_monitoring, get_failed_restart_count. Added close() as a no-op for API compat. Total 8 methods added, 104 lines.
  - Smoke-tested each method against live mining_guardian Postgres. All returned same values as equivalent SQLite queries against guardian.db.
- **Issue found and fixed mid-phase:** migrations/001_initial_schema.sql had 23 CREATE INDEX statements without IF NOT EXISTS, so _init_db() crashed on second instantiation with DuplicateTable. Fixed all 23 via sed. Committed separately as df096fa. This also makes the Mac Mini installer more robust (idempotent schema file).
- **Outcome:** GuardianPGDB now has 15 of 24 needed methods. Proceed to Phase 4.

### Phase 4 — Port medium GuardianDB methods
- **Status:** ✅ Complete
- **Start:** 2026-04-23 ~08:58 CDT
- **End:** 2026-04-23 ~09:20 CDT
- **Commit:** b6688fa
- **Actions taken:**
  - Pulled source of 11 methods: save_notifications, save_weather, save_hvac, load_known_models, save_chain_readings, save_pool_readings, save_miner_state_readings, save_ams_extended, save_discovery, log_action, purge_old_logs
  - Translated to Postgres (? → %s, executemany → execute_batch with page_size=200, SELECT-then-UPDATE-or-INSERT kept on one connection for transactional safety)
  - Added 334 lines to core/database_pg.py (total now 821 lines, 26 public methods)
  - Smoke-tested all 11 against mining_guardian_test Postgres — all OK, correct row counts in every destination table
- **Outcome:** GuardianPGDB has all methods the scan loop writes with. Proceed to Phase 5.

### Phase 5 — Port complex methods + stubs
- **Status:** ✅ Complete
- **Start:** 2026-04-23 ~09:30 CDT
- **End:** 2026-04-23 ~09:42 CDT
- **Commit:** 9963ffe
- **Actions taken:**
  - Ported record_restart (INSERT with elevated_until calc, outcome=PENDING)
  - Ported register_dead_boards (SELECT-then-UPDATE-or-INSERT, with the RealDictCursor gotcha documented — existing[id] not existing[0])
  - Added parse_log_metrics stub that logs debug and returns 0; the 147-line regex parser is deferred, raw logs still get saved by save_logs
  - parse_and_save_hardware deferred entirely — only manual_log_upload.py calls it
- **Coverage check result:** All 28 methods called by core/mining_guardian.py and notifiers/slack_notifier.py on GuardianDB instances are now present on GuardianPGDB. Zero gap for the scan loop.
- **Smoke test:** record_restart created 1 row with outcome=PENDING, hashrate_before=95.5, elevated_until +2h. register_dead_boards insert-then-update produced exactly 1 row with updated board_indices. parse_log_metrics stub returned 0 without error.
- **Outcome:** GuardianPGDB is feature-complete for the scan loop. Proceed to Phase 7 (raw-sqlite3 file rewrites).


### Phase 6 — Stub/defer remaining GuardianDB methods
- **Status:** ✅ Complete (handled as part of Phase 5)
- **Outcome:** parse_log_metrics stubbed in Phase 5 commit 9963ffe. parse_and_save_hardware deferred with no stub — nothing in the scan loop calls it.


### Phase 7 — Convert raw-sqlite3 service files to psycopg2
- **Status:** ⏳ In progress (1/9 complete)
- **Start:** 2026-04-23 ~09:50 CDT
- **Strategy:** one commit per file, smoke-test each before commit. Order: smallest/most-isolated first, biggest (dashboard_api) last.
- **Files:**
  - ✅ 7.1 api/ams_alert_listener.py (494 LOC, 14 sqlite lines) — commit 22f99ec, 2026-04-23 09:58 CDT
  - ⏳ 7.2 core/overnight_automation.py (441 LOC)
  - ⏳ 7.3 api/slack_approval_listener.py (460 LOC)
  - ⏳ 7.4 api/slack_command_handler.py (885 LOC)
  - ⏳ 7.5 api/intelligence_report_api.py (1869 LOC)
  - ⏳ 7.6 ai/local_llm_analyzer.py (637 LOC)
  - ⏳ 7.7 ai/daily_deep_dive.py (1088 LOC)
  - ⏳ 7.8 api/approval_api.py (471 LOC, high placeholder density)
  - ⏳ 7.9 api/dashboard_api.py (3404 LOC, largest)
- **Translation patterns (documented in each commit):**
  - ? → %s
  - INSERT OR REPLACE → INSERT ... ON CONFLICT (pk) DO UPDATE SET col=EXCLUDED.col,...
  - INSERT OR IGNORE → INSERT ... ON CONFLICT DO NOTHING
  - row[0] → row[column_name] (RealDictCursor)
  - sqlite3.OperationalError for missing table → psycopg2.errors.UndefinedTable
  - cur.lastrowid → INSERT ... RETURNING id + cur.fetchone()[id]
  - PRAGMA table_info(X) → SELECT FROM information_schema.columns WHERE table_name='X'
  - datetime('now', '-7 days') → NOW() - INTERVAL '7 days' (in SQL) OR Python datetime.isoformat() + WHERE ts > %s

### Phase 8 — Configure systemd env vars
- **Status:** Pending

### Phase 9 — Run test suite + scratch_pg_test
- **Status:** Pending

### Phase 10 — Final catch-up migration
- **Status:** Pending

### Phase 11 — Start mining-guardian
- **Status:** Pending

### Phase 12 — Start remaining services
- **Status:** Pending

### Phase 13 — Post-flip verification
- **Status:** Pending

### Phase 14 — Documentation
- **Status:** Pending

---

## Rollback procedure (if anything goes wrong at any phase)

1. `git revert` the problem commit
2. `systemctl restart` affected services
3. Verify with `systemctl is-active` and a sample scan
4. Safety snapshot at `/root/mg_safety_snapshot_2026-04-23.tar.gz` is the fallback from 04:24 CDT state if git revert isn't enough

The SQLite backend (`core/database.py`) is not being modified during this migration. If we revert the import flips and restart, services return to SQLite.

---

*This document will be updated at the end of each phase with actual times, commands run, issues hit, and outcomes.*
