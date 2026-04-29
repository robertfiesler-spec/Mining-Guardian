# RUNBOOK — Bucket 7.6 — MG_ALLOW_MIGRATION runtime guards on migrate_*.py

**Date:** 2026-04-29
**Owner:** Mining Guardian core
**PR:** #83
**Decision reference:** `docs/DECISIONS.md` D-6 (locked 2026-04-24)

---

## Why

Three SQLite→Postgres migration scripts live in the repo:

1. `migrations/migrate_sqlite_to_postgres.py` — full single-DB migration (282 lines, batched 10k-row inserts, supports 18M+ rows).
2. `scripts/migrate_split_databases.py` — splits the monolithic `guardian.db` into 4 logical SQLite files.
3. `scripts/migrate_to_postgres.py` — migrates the 4 split SQLite databases into Postgres.

All three are **destructive**: they overwrite live Postgres rows with stale or empty SQLite data if run by accident.

Decision D-6 (`docs/DECISIONS.md`, 2026-04-24) requires every migration script to raise an exception unless `MG_ALLOW_MIGRATION=1` is set in the environment. Implementation status was marked **⏸ Needs verify in current code** in the unified TODO §9 row 6.

A grep audit on 2026-04-29 found:

| Script | Has `MG_ALLOW_MIGRATION` guard? |
|---|---|
| `migrations/migrate_sqlite_to_postgres.py` | ❌ No |
| `scripts/migrate_split_databases.py` | ❌ No |
| `scripts/migrate_to_postgres.py` | ❌ No (only a comment at line 24 referencing D-6, no actual code) |

So the decision was locked but never implemented. Bucket 7.6 closes that gap.

---

## What this PR does

Adds the same guard block at module scope in all three scripts, immediately after the import block and before any database connection logic or environment-dependent constants.

### Guard block (identical across all three files)

```python
# ---------------------------------------------------------------------------
# Safety guard — see docs/DECISIONS.md D-6.
# This script is destructive: it copies SQLite contents into Postgres and can
# clobber live operational data if run by mistake. Bucket 7.6 (2026-04-29) added
# this runtime guard to all three migrate_*.py scripts. To run the migration
# intentionally, set MG_ALLOW_MIGRATION=1 in the environment.
# ---------------------------------------------------------------------------
if not os.environ.get("MG_ALLOW_MIGRATION"):
    sys.stderr.write(
        "ERROR: %s is gated.\n"
        "       Set MG_ALLOW_MIGRATION=1 to run this destructive migration.\n"
        "       See docs/DECISIONS.md D-6 for context.\n"
        % Path(__file__).name
    )
    sys.exit(2)
# ---------------------------------------------------------------------------
```

### Why module-level (not inside `main()`)

- These scripts are CLI-only (no other Python file imports them — verified with `grep -r "import migrate_\|from migrations.migrate_\|from scripts.migrate_"`, returns 0 hits).
- `migrate_to_postgres.py` line 25-33 has a `PG_CONFIG` dict that **raises `EnvironmentError`** if `MG_DB_PASSWORD` is not set. If we put the guard inside `main()`, the script would crash at import time on a stricter error before reaching the guard. Module-level placement bypasses that.
- Exit code `2` (not `1`) signals "operational refusal" distinct from runtime error.

### Why `sys.stderr.write` + `sys.exit(2)` (not `raise`)

- `raise` would print a Python traceback, which is noisy and looks like a bug.
- A clean stderr message + non-zero exit code matches Unix convention for guarded scripts.

---

## Files changed

| File | Before | After | Δ |
|---|---|---|---|
| `migrations/migrate_sqlite_to_postgres.py` | 282 lines | 297 lines | +15 |
| `scripts/migrate_split_databases.py` | 252 lines | 267 lines | +15 |
| `scripts/migrate_to_postgres.py` | 276 lines | 291 lines | +15 |
| `docs/MG_UNIFIED_TODO_LIST.md` | — | flips §9 row 6 to ✅ + adds note in §8.1 row 6 | TODO sync |
| `docs/RUNBOOK_BUCKET_7.6_MIGRATION_GUARDS.md` | — | new | this file |

Total: **+~120 / -2** across 5 files.

---

## Local verification (already run on agent sandbox)

```
$ python3 -m py_compile patched_migrate_*.py
  → all three: OK

$ unset MG_ALLOW_MIGRATION
$ python3 patched_migrate_sqlite_to_postgres.py
ERROR: patched_migrate_sqlite_to_postgres.py is gated.
       Set MG_ALLOW_MIGRATION=1 to run this destructive migration.
       See docs/DECISIONS.md D-6 for context.
  exit code: 2

$ python3 patched_migrate_split_databases.py
ERROR: patched_migrate_split_databases.py is gated. ...
  exit code: 2

$ python3 patched_migrate_to_postgres.py
ERROR: patched_migrate_to_postgres.py is gated. ...
  exit code: 2
```

All three exit cleanly with the gated error and no traceback, before any DB import or connection.

---

## How to run a migration intentionally (post-PR)

```bash
# On the operator's box, with backups taken:
export MG_ALLOW_MIGRATION=1
python3 scripts/migrate_to_postgres.py
unset MG_ALLOW_MIGRATION
```

The variable is **deliberately ephemeral** — `unset` it after the run so accidental re-execution from shell history is also gated.

---

## Out of scope (deferred)

- **Hard-deletion of the migrate scripts.** Per D-6, deletion is deferred to post-Mac-Mini cutover, on the theory that we may need one more emergency re-import during the install dry-runs. After cutover, all three scripts move to `archive/migrations/` (Bucket 7 Phase 2).
- **`core/database_pg.py` / `core/database_router.py` references.** Both still import these scripts indirectly (as historical breadcrumbs in `__doc__` and similar). Those references are no-ops at runtime — left alone for the SQLite-retirement bucket.

---

## TODO list flips (in same commit per `work.projects.mining_guardian.todo_sync`)

- §8.1 row 6 (`migrate_sqlite_to_postgres.py`): note updated — guard now confirmed, ALL three scripts guarded.
- §9 row 6 (D-6 implementation status): ⏸ Needs verify → ✅ Done in PR #83.

---

## Change history

- 2026-04-24 — D-6 locked.
- 2026-04-29 — grep audit confirmed all three scripts unguarded. Bucket 7.6 patch shipped (PR #83).
