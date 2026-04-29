# archive/sqlite_phase1/

Phase 1 (SQLite-era) modules that were never imported by the live Postgres-era
codebase. Archived rather than deleted so that the operator-rule semantics they
encode remain discoverable when the corresponding Postgres-backed feature is
implemented.

## Provenance

`docs/POSTGRES_MIGRATION_STATUS_2026-04-24.md` line 11 lists these modules
explicitly as "orphaned Phase 1 files...not imported by anything live":

- `core/database.py`
- `core/database_router.py`
- `core/db_compat.py`
- `core/db_helper.py`
- `core/s19jpro_overheat_handler.py`

This directory currently archives only the s19jpro_overheat_handler. The other
four orphan files are bigger-scope SQLite-retirement work and remain in `core/`
for now, gated behind their own bucket.

## Contents

### s19jpro_overheat_handler.py
- **Archived:** 2026-04-29 (Bucket 7.3, PR #84)
- **Original location:** `core/s19jpro_overheat_handler.py`
- **Purpose at time of write:** Enforce **Operator Rule #6** for S19J Pro
  overheating — try ONE restart, if it doesn't help mark as aging hardware and
  let it run.
- **Why archived (not deleted):** The operator rule is still active per
  `CLAUDE.md`. The SQLite-coupled implementation is dead (zero callers, see
  grep below) but the design intent is real. When someone wires the rule up
  against the live Postgres `s19jpro_overheat_tracking` table, this file is
  the historical reference for the state-machine semantics:

  | State | Meaning | Trigger |
  |---|---|---|
  | `new` | First time seeing overheat, should try restart | no row in tracking table |
  | `restart_pending` | Restart done, waiting for comparison | `restart_attempted_at` set, `restart_helped IS NULL` |
  | `aging` | Restart didn't help, leave alone | `marked_aging_at` set OR `restart_helped = 0` |
  | `not_s19jpro` | Wrong model, ignore | `model` doesn't start with `S19JPro` |

- **Why it was dead:** The handler used `sqlite3.connect(db_path)` against the
  Phase 1 split-DB layout (`ai_knowledge.db`). Postgres migration moved the
  table to `hardware.s19jpro_overheat_tracking` (see `migrations/001_initial_schema.sql:404`),
  but no live module called the handler functions, so the rule never enforced.
  Confirmed by grep on 2026-04-29:
  ```
  $ grep -rn "check_s19jpro_overheat_status\|record_overheat_first_seen\|record_restart_attempt\|record_restart_result\|get_aging_s19jpros" --include="*.py"
  # only function definitions in the handler itself — zero call sites
  ```

## Future implementation guidance

When you implement Operator Rule #6 against the live Postgres table:

1. Use `psycopg2` / `psycopg2.pool` (NOT sqlite3) — the live database is Postgres on the VPS / Mac Mini.
2. Use the live connection helper used everywhere else (`core/database_pg.py`).
3. The table lives in the `public` schema (`s19jpro_overheat_tracking`) — see migration 001.
4. Wire the rule into the per-miner analysis loop in `core/mining_guardian.py:_analyze_miner` (the same place the offline-remediation decision tree lives).
5. Per the unified TODO §8.1 N2, decide whether to:
   - (a) keep the table model-specific (`s19jpro_overheat_tracking`),
   - (b) generalize it into `model_overheat_tracking` keyed by `model`, or
   - (c) fold it into the existing `ops.failure_patterns` table.
   That's a feature-design decision, not a cleanup decision.

When the rule is wired up live, **delete this archive copy** — it will have served its purpose.
