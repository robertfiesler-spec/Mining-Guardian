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

## Phase list

  1. **Pre-flight audit** — verify Postgres schema has every ALTER TABLE column we added today to SQLite
  2. **Stop all 8 services** (R&D downtime starts here)
  3. **Port trivial methods** (batch 1, ~12 small methods)
  4. **Port medium methods** (batch 2, ~8 methods)
  5. **Port complex methods** (batch 3, the 4 save_X_readings + record_restart + register_dead_boards)
  6. **Stub/defer remaining** (parse_log_metrics stub, parse_and_save_hardware skip)
  7. **Flip imports** in `core/mining_guardian.py`, `notifiers/slack_notifier.py`, `api/ams_alert_listener.py`
  8. **Configure systemd env vars** so services can reach Postgres
  9. **Run test suite + scratch_pg_test** — gate before any service restart
  10. **Final catch-up migration** from guardian.db to Postgres
  11. **Start mining-guardian first**, watch one scan cycle complete in Postgres
  12. **Start remaining 7 services**, watch for errors
  13. **Post-flip verification** — compare write paths, Slack notifications, dashboard
  14. **Documentation** — update NEXT_SESSION.md, commit final state

---

## Phase log

### Phase 0 — Plan written
- **Status:** ✅ Complete
- **Start:** 2026-04-23 ~07:15 CDT
- **End:** 2026-04-23 ~07:20 CDT
- **Output:** this document

### Phase 1 — Pre-flight audit
- **Status:** Pending

### Phase 2 — Stop all services
- **Status:** Pending

### Phase 3 — Port trivial methods
- **Status:** Pending

### Phase 4 — Port medium methods
- **Status:** Pending

### Phase 5 — Port complex methods
- **Status:** Pending

### Phase 6 — Stub/defer remaining
- **Status:** Pending

### Phase 7 — Flip imports
- **Status:** Pending

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
