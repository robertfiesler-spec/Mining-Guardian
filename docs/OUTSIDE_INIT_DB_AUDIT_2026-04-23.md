# Outside-`_init_db` Schema Audit — 2026-04-23

**Purpose:** Follow-up to `CORE_DATABASE_AUDIT_2026-04-23.md`. That audit
covered the 17 tables created by `GuardianDB._init_db`. This one covers
the 8 tables that exist in the live guardian.db but are created (or
supposed to be created) elsewhere in the codebase.

**Why it matters:** A fresh install — which is what the Mac Mini
installer will do in May — only runs the code paths that actually get
invoked on startup. If a table's CREATE TABLE lives in a module that
gets imported and its init function gets called, we're fine. If the
CREATE TABLE doesn't exist anywhere in the SQLite codebase, or exists
but is never invoked on a fresh install, the first INSERT/SELECT
against that table crashes with "no such table: X".

---

## Tables audited

Live `guardian.db` has 25 tables total. `_init_db` creates 17. The
remaining 8:

| Table                        | CREATE TABLE location                              | Status |
|------------------------------|----------------------------------------------------|--------|
| alert_listener_cooldown      | `api/ams_alert_listener.py:112`                    | Clean  |
| alert_listener_seen          | `api/ams_alert_listener.py:99`                     | Clean  |
| llm_analysis                 | `core/llm_analyzer.py:93`                          | Clean  |
| log_metrics                  | `core/database.py:1467` (outside `_init_db`)       | Clean  |
| maintenance_windows          | `api/maintenance_scheduler.py:33`                  | Clean  |
| miner_baselines              | `core/hashrate_evaluation.py:318`                  | Clean  |
| log_collection_failures      | **nowhere in SQLite code**                         | Dead   |
| s19jpro_overheat_tracking    | **nowhere in SQLite code**                         | Dead   |

---

## The 6 clean tables

For each of the 6 with a real creator, the CREATE TABLE column list
was compared to the live guardian.db schema. **All six are drift-free.**
Every column the live code writes is in the CREATE TABLE that creates
the table. No ALTER TABLE fossils, no silent additions.

Detail:

- **alert_listener_cooldown** — 3 cols: `miner_id` (PK), `last_action`, `last_action_at`.
  Created lazily by `api/ams_alert_listener.py` on first use.
- **alert_listener_seen** — 9 cols. Same file.
- **llm_analysis** — 9 cols. Created by `core/llm_analyzer.py.__init__`.
- **log_metrics** — 14 cols + an index. Created inline by
  `core/database.py::save_log_metrics` which is defensive — runs the
  `CREATE TABLE IF NOT EXISTS` on every call.
- **maintenance_windows** — 10 cols + 2 indexes. Created by
  `api/maintenance_scheduler.py.__init__`.
- **miner_baselines** — 12 cols. Created by
  `core/hashrate_evaluation.py::HashrateEvaluator._ensure_table`.

These all follow one of two patterns that are safe for fresh installs:
(1) the module creates its own table in its `__init__` or on first
call, or (2) the CREATE TABLE is inside the same method that does the
INSERT (so the table exists by the time data is written).

---

## The 2 dead tables

Both of these have live-DB rows of 0, zero callers in the code, and
no SQLite CREATE TABLE anywhere. They exist in the live DB because
someone ran the CREATE TABLE manually at some point, probably while
scaffolding a feature that never shipped.

### log_collection_failures (dead)
- Referenced only in `core/database_router.py` (routing map),
  `migrations/migrate_sqlite_to_postgres.py` (migration list), and
  `scripts/migrate_split_databases.py` (split list).
- No INSERT, no SELECT, no UPDATE anywhere in the codebase.
- 0 rows in live guardian.db.

**Impact on fresh install:** None. Nothing tries to use it.

### s19jpro_overheat_tracking (dead)
- `core/s19jpro_overheat_handler.py` defines 5 functions that
  query/insert/update/delete this table. The functions use raw
  `sqlite3.connect(db_path)` directly (bypasses GuardianDB).
- **No caller** — grep for `check_s19jpro_overheat_status`,
  `record_overheat_first_seen`, etc. returns only the definitions.
- 0 rows in live guardian.db.
- Original intent was "Operator Rule #6: try one restart for
  overheating S19J Pros" per the module docstring. Rule was never
  wired into the production scan loop.

**Impact on fresh install:** None. The handler module loads fine on
import (no top-level DB access). Nothing calls into it. If anything
ever does call into it on a fresh install, it crashes with
"no such table: s19jpro_overheat_tracking" on line 31.

---

## Follow-up cleanup (not urgent)

Two landmines worth defusing when convenient:

1. Decide whether `s19jpro_overheat_handler.py` is still wanted.
   If yes: add its CREATE TABLE to `_init_db` (operational.db block,
   following the pattern used for miner_restarts and pending_approvals
   migrations). If no: delete the module and the dead table row in
   the router config.

2. `log_collection_failures` entry in the router config + migration
   scripts can be removed. The dead table row in live guardian.db
   can stay (it's harmless, and dropping it triggers sqlite_master
   churn that could invalidate the safety snapshot comparisons).

Neither is blocking the Mac Mini installer today.

---

## Bottom line

After the column-drift audit on `_init_db` tables and this
outside-`_init_db` audit, **every live production code path that
touches the DB has been checked against the fresh-install schema**.
No known remaining blockers for a clean Mac Mini install.

The scratch-router test at `/tmp/scratch_router_test.py` stands as a
regression harness — if anyone adds new drift in the future, the test
will catch it by comparing scratch-install behavior to expected writes.
