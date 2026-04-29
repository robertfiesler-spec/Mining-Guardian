# Bucket 7.2 — Drop empty stub tables `chip_readings` + `log_collection_failures`

**Date:** 2026-04-29
**PR:** Bucket 7.2 (this PR)
**Authority:**
- `docs/MG_UNIFIED_TODO_LIST.md` §8.1 — both rows marked 🔴 with "Recommend drop"
- `docs/EMPTY_STUB_TABLES.md`
- Audit findings H1 (`chip_readings`) + H3 (`log_collection_failures`)

## What this PR changes

| File | Change |
|---|---|
| `migrations/004_drop_dead_stubs.sql` | NEW — `BEGIN; DROP INDEX/TABLE IF EXISTS …; COMMIT;` for both tables. Idempotent. |
| `migrations/001_initial_schema.sql` | Removed the two `CREATE TABLE` blocks + their indexes, replaced with multi-line comment pointers to migration 004. Net: 458 → 438 lines. |
| `docs/MG_UNIFIED_TODO_LIST.md` | Flipped both §8.1 rows (H1, H3) to ✅ in the same commit. |
| `docs/RUNBOOK_BUCKET_7.2_DROP_DEAD_STUBS.md` | NEW — this file. |

## Why these tables are dead

### `chip_readings` (H1)

* **Designed for:** Per-chip frequency / voltage / temperature samples pulled from miner direct APIs.
* **Why it's empty:** The per-chip extraction path was scoped but never built. The actually-populated path is `log_metrics` (raw mining log lines, parsed for hashrate/temp).
* **Verified empty in production:** VPS Postgres on 2026-04-29 — `SELECT COUNT(*) FROM chip_readings` returns 0.
* **Verified no writers in non-archive code:** `grep -rn "INSERT.*chip_readings\|UPDATE.*chip_readings" --include='*.py' . | grep -v archive/` returns empty.

### `log_collection_failures` (H3)

* **Designed for:** Tracking which miners we couldn't pull mining logs from (per-day rollup with consecutive-failure counts).
* **Why it's empty:** Never wired. Failure events are instead surfaced through `discovery_log` and the Slack notifier path.
* **Verified empty in production:** VPS Postgres on 2026-04-29 — `SELECT COUNT(*) FROM log_collection_failures` returns 0.
* **Verified no writers in non-archive code:** Same grep for `log_collection_failures` returns only the SQLite-era CREATE in `core/database.py` and the routing entry in `core/database_router.py` (both legacy; covered below).

## Safety review

1. **No FK dependents.**
   ```
   SELECT conname, conrelid::regclass FROM pg_constraint
    WHERE contype = 'f'
      AND confrelid IN ('chip_readings'::regclass,
                        'log_collection_failures'::regclass);
   -- expect: 0 rows on VPS Postgres (verified 2026-04-29).
   ```
2. **No views or matviews read from them.** Verified by grepping `pg_views.definition` and `pg_matviews.definition` for the table names.
3. **Both tables are empty in production** (VPS Postgres — see above).
4. **SQLite-era code in `core/database.py` and `core/database_router.py` still references both tables.** Left in place per the standing constraint "NEVER refer to SQLite as live". The SQLite path is being retired separately (future bucket); that retirement will sweep these references along with the rest of the SQLite code in one go. Touching them here would expand scope.

## What is intentionally NOT in scope

* Removing `chip_readings` / `log_collection_failures` from `core/database.py` SQLite bootstrap. (SQLite retirement is its own bucket.)
* Removing entries from `core/database_router.py:TABLE_ROUTING`. (Same.)
* Removing entries from `migrations/migrate_sqlite_to_postgres.py` and `scripts/migrate_split_databases.py` / `scripts/migrate_to_postgres.py`. These are one-shot historical migrations and listing dead tables there is harmless — the scripts are guarded behind `MG_ALLOW_MIGRATION=1` and won't be re-run.

## Apply on existing nodes

```
# VPS / Mac-Mini Postgres (after this PR merges):
psql -U mg -d mining_guardian -v ON_ERROR_STOP=1 \
  -f migrations/004_drop_dead_stubs.sql

# Verify:
psql -U mg -d mining_guardian -c "
  SELECT COUNT(*) AS still_present FROM information_schema.tables
   WHERE table_name IN ('chip_readings','log_collection_failures');
"
# expect: still_present = 0
```

The Mac-Mini installer's `step_apply_migrations` already loops over `migrations/*.sql` in numerical order — it will pick up `004` automatically. Re-running the migration on a node where the tables are already gone is a clean no-op (only NOTICE messages, no errors).

## Reverting

If a regression surfaces:

```
git revert <merge-commit-sha>            # restores the CREATE blocks
psql -U mg -d mining_guardian -f migrations/001_initial_schema.sql  # idempotent CREATEs come back
```

The drop is non-destructive in the sense that the tables are empty — there is no data loss.
