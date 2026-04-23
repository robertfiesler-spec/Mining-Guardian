# Postgres Migration Status — 2026-04-23 end-of-day snapshot

## TL;DR

**Mining Guardian is running on Postgres.** SQLite writes have stopped. All 8
systemd services are active on the Postgres backend. Scan 1695 landed cleanly
in Postgres at 12:10 CDT. Zero service restart loops.

**ONE known issue remains:** `dashboard-api /metrics` endpoint returns 500.
Not user-facing. Prometheus scrape target only.

## Service state (verified 12:47 CDT)

| Service | Status | Notes |
|---|---|---|
| mining-guardian | active | Scan 1695 at 12:10 CDT (1 hour interval) |
| dashboard-api | active | /metrics returns 500 — see below |
| approval-api | active | No errors |
| slack-listener | active | No errors |
| slack-commands | active | No errors |
| overnight-automation | active | No errors |
| mining-guardian-alerts | active | No errors |
| intelligence-report | active | No errors |

**All services: zero restarts since initial startup.**

## Database state

- **Postgres `mining_guardian`**: 1694 scans, max_id=1695, latest 12:10 CDT
- **SQLite `guardian.db`**: 1693 scans, max_id=1694, latest 07:51 CDT (frozen)
- Full parity achieved via final catch-up migration at ~11:40 CDT
- **`guardian.db` has NOT been renamed yet** — still at its original path
- Tables with PK added live via ALTER TABLE today (not yet in schema file):
  - `miner_baselines` → added PK (miner_id)
  - `alert_listener_seen` → added PK (notification_id)

## Known outstanding issues

### 1. dashboard-api /metrics endpoint

**Symptom:** HTTP 500 every time Prometheus scrapes /metrics (every 30s).

**Evidence gathered so far:**
- Two sequential errors: IndexError: tuple index out of range at line 698
  (`.fetchone()[0]` on SQL COUNT(*) result) → followed by NameError: 'logger'
  not defined in the except handler at line 715.
- Standalone test of same query via _PgConnWrapper returns DictRow with
  `row[0] == integer` correctly. **Cannot reproduce outside of live service.**
- Cleared __pycache__, force-restarted service (PID changed). Error persists.
- DictCursor is in use and verified (grep confirms RealDictCursor count is 0).
- Not a cached-code issue (pycache cleared, PID confirmed new).

**Theories worth testing next:**
- Maybe FastAPI/Starlette caches something at import time that differs from
  interactive import.
- Maybe the /metrics function has module-level state that initializes once
  and breaks subsequent calls.
- The `logger` NameError suggests maybe there's a scope issue where logger
  isn't imported at the top level of dashboard_api.py.
- Need to add a print statement above line 698 to see what row actually is
  when the service runs it.

### 2. Two table PK additions not yet in schema file

`migrations/001_initial_schema.sql` does not declare PRIMARY KEY on
`miner_baselines.miner_id` or `alert_listener_seen.notification_id`. We added
both via ALTER TABLE on live Postgres today. Fresh installs (Mac Mini) will
lack these constraints unless we backport. Small, planned follow-up.

### 3. Crontab still cleared

Crontab was cleared at 08:27 CDT for migration. Backup at
`/tmp/crontab_backup_2026-04-23.txt` (37 lines). Restore via
`crontab /tmp/crontab_backup_2026-04-23.txt` whenever ready.

### 4. guardian.db not renamed yet

Bobby chose Option B (rename to `.frozen.2026-04-23`). We deferred rename
until /metrics is green. Still pending.

## Git state

- 41 commits on origin today
- Latest: 1c8bd05 fix(postgres): use DictCursor for hybrid int/string row access + ROUND::numeric cast
- All 48 pytest tests passing

## Resume checklist for next session

1. Debug dashboard-api /metrics 500 error (attach pdb or add print, reproduce
   in service context)
2. Backport miner_baselines PK and alert_listener_seen PK to
   migrations/001_initial_schema.sql
3. Verify one more full scan cycle completes on Postgres
4. Rename guardian.db → guardian.db.frozen.2026-04-23
5. Restore crontab from /tmp/crontab_backup_2026-04-23.txt
6. Update docs/POSTGRES_MIGRATION_PLAN_2026-04-23.md phase log (phases 11-15)
7. Consider removing OpenClaw (see docs/OPENCLAW_AUDIT_2026-04-23.md) — separate
   task, not blocking

## What worked today (for the record)

- Systematic Phase 7 file-by-file conversion
- `_PgConnWrapper` pattern — saved rewriting dozens of `conn.execute()` sites
- Pre-flight test caught `hashrate_evaluation.py` before services crashed
- Schema-drift fixes via ALTER TABLE kept services working during transition
- Bobby's instinct check on OpenClaw saved us from converting dead code
