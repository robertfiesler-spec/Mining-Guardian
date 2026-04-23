# Postgres Staging State — 2026-04-23

**Subject:** Current state of the VPS Postgres `mining_guardian` database, and the plan for taking it to a production-ready Mac Mini installer target.

**Critical caveat:** Nothing in this doc changes live production behavior. Mining-guardian on the VPS continues to write to the monolithic `guardian.db` SQLite file. Postgres is a **staging target** being prepared for the Mac Mini cutover in May.

---

## Current state of VPS Postgres

Discovered during Phase 1 of the Postgres staging work on 2026-04-23 at 06:00 CDT. The state turned out to be significantly better than prior documentation suggested.

### Service

- Postgres service: active on the VPS (systemd-managed)
- Accepting connections at `/var/run/postgresql:5432`
- Database: `mining_guardian` (owned by `postgres`, access granted to `guardian_app`)
- No active application connections — nothing is writing to Postgres right now

### Schema

All 25 tables present in the `public` schema, owned by `guardian_app`. Matches the 25 tables in live `guardian.db` exactly (including the two dead tables — `log_collection_failures` and `s19jpro_overheat_tracking` — documented in `OUTSIDE_INIT_DB_AUDIT_2026-04-23.md`). Schema was loaded from `migrations/001_initial_schema.sql`.

### Data

Populated yesterday (2026-04-22) up through scan 1681 at 14:41:33 CDT. Then the migration stopped — likely because that's when the database split refactor crashed production and all attention went to stabilization.

The migration was **faithful but incomplete**. Every row that was migrated matches the corresponding row in `guardian.db`. Every table that had data has a row-count consistent with the 15-hour gap.

### Row-count delta (sqlite vs postgres, full-table comparison)

Tables with zero drift (Postgres fully caught up through scan 1681):
  - discovery_log, miner_restarts, known_dead_boards, miner_hardware
  - log_metrics (all 18,143,000 rows migrated)
  - alert_listener_cooldown, miner_baselines, maintenance_windows

Tables with drift consistent with ~10 scans + 15 hours of activity:
  - miner_readings: +196 rows, miner_ams_extended: +196, miner_state_readings: +196
  - chain_readings: +462, pool_readings: +158
  - scans: +10, pending_approvals: +3, action_audit_log: +7
  - weather_readings: +7, hvac_readings: +14, miner_logs: +41
  - ams_notifications: +560, alert_listener_seen: +280, llm_analysis: +13

Total delta across all tables: approximately 2,100 rows (out of ~18.4 million total). Every delta is in the expected direction (SQLite ahead) — zero cases where Postgres had extra rows that SQLite didn't.

---

## The staging plan

Four phases remaining. Each phase is independently verifiable and reversible.

### Phase 2 — Catch-up migration (NEXT)

Bring Postgres to parity with guardian.db. Incremental append: for each table, copy rows where the relevant key (`id`, `scan_id`, or `recorded_at`) is greater than the max already in Postgres.

**Scope:** ~2,100 rows. Should complete in seconds.

**Risk:** Low. The existing Postgres rows aren't touched — we only append. If the script crashes mid-run, we can retry with no duplicate-row risk because we key on primary keys that already exist.

**Validation:** Re-run the row-count comparison. Every delta should be zero or tiny (for scans that happened while the catch-up was running).

### Phase 3 — Postgres adapter for GuardianDB

Write `core/database_pg.py` that exposes the same API as `GuardianDB` (the SQLite class) but uses psycopg against Postgres. All 38 `_connect()` call sites should work identically against this adapter without code changes.

**Scope:** New file, ~300 lines. Does not touch `core/database.py`.

**Risk:** Additive. No existing code paths change. If the adapter doesn't work, we don't use it.

**Validation:** Unit test at minimum. Scratch test ideally.

### Phase 4 — Extend scratch test for Postgres backend

Same 7-bug test harness at `/tmp/scratch_router_test.py`, but backed by a dedicated Postgres test database (separate from `mining_guardian`). If the Postgres adapter correctly handles all 7 fixed methods, the installer path is proven for Postgres too.

**Scope:** A new test DB + updated harness. Temporary files.

**Risk:** None to production. Test isolation.

### Phase 5 — Installer documentation

A clear, step-by-step guide for the Mac Mini installer: install Postgres, create DB and user, run migrations, populate from SQLite dump (optional for customer deployments), point GuardianDB at Postgres, restart services.

**Scope:** ~50-line markdown doc.

---

## What this does NOT do

This plan does NOT:

- Change anything in the live mining-guardian service (monolithic guardian.db stays live)
- Restart any production service
- Delete or modify any existing file outside `core/`, `scripts/`, and `docs/`
- Touch the frozen split-SQLite files in `databases/`
- Change `_connect()` or any router behavior

It only:
- Adds new files (`core/database_pg.py`, new docs, new tests)
- Populates the Postgres DB with missing ~2,100 rows of data
- Extends existing harnesses (scratch test) to cover Postgres

---

## Rollback

If at any point this work needs to be undone:

1. The Postgres DB can be reset: `DROP DATABASE mining_guardian; CREATE DATABASE mining_guardian;` then re-run the migration SQL.
2. Any new files can be deleted via `git revert`.
3. The safety snapshot at `/root/mg_safety_snapshot_2026-04-23.tar.gz` still captures the full working tree from before today's work began.

---

## Key reference values

- VPS Postgres host: localhost
- Port: 5432
- Database: mining_guardian
- Owner: postgres
- Application user: guardian_app
- Application password: rotated alongside GitHub PAT (see NEXT_SESSION.md outstanding items)
- Connection URL shape: `postgresql://guardian_app:<pw>@localhost:5432/mining_guardian`
