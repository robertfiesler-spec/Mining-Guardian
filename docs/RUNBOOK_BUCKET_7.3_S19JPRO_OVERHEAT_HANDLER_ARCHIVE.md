# RUNBOOK — Bucket 7.3 — Archive `core/s19jpro_overheat_handler.py`

**Date:** 2026-04-29
**Owner:** Mining Guardian core
**PR:** #84

---

## Why

`core/s19jpro_overheat_handler.py` is a Phase 1 SQLite-coupled module that has been **dead code (zero callers) for the entire Postgres era**.

Confirmed three ways:

1. **Grep audit (2026-04-29) — zero call sites:**
   ```
   $ grep -rn "check_s19jpro_overheat_status\|record_overheat_first_seen\|record_restart_attempt\|record_restart_result\|get_aging_s19jpros" --include="*.py"
   # only function definitions in the handler itself
   ```

2. **Documented as orphan in `docs/POSTGRES_MIGRATION_STATUS_2026-04-24.md` line 11:**
   > "The one remaining cleanup is archiving a set of orphaned Phase 1 files (`core/database.py`, `core/database_router.py`, `core/db_compat.py`, `core/db_helper.py`, `core/s19jpro_overheat_handler.py`) that still contain real SQLite code but are not imported by anything live."

3. **The module uses `sqlite3.connect(db_path)`** — incompatible with the live Postgres backend on every call.

The unified TODO §8.1 row for `s19jpro_overheat_tracking` (audit finding **N2**) said: *"🔴 Promote to generic `model_overheat_tracking` OR fold into `ops.failure_patterns`."*

But `docs/EMPTY_STUB_TABLES.md` lines 28-41 says the **Postgres** `s19jpro_overheat_tracking` table is intentional architecture: it activates when an S19J Pro exceeds 84°C, per **Operator Rule #6** in CLAUDE.md (try ONE restart, then mark as aging). The table is fine as-is.

The dead component is the **Phase 1 handler module** — not the table, and not the operator rule.

---

## What this PR does

1. **Move** `core/s19jpro_overheat_handler.py` → `archive/sqlite_phase1/s19jpro_overheat_handler.py` (verbatim, no edits).
2. **Add** `archive/sqlite_phase1/README.md` documenting why the file is archived and providing implementation guidance for the eventual Postgres-backed Operator Rule #6 wiring.
3. **Update** `archive/README.md` to mention the new sub-directory.
4. **Update** `docs/EMPTY_STUB_TABLES.md` — append a "Phase 1 handler archived" note to the s19jpro_overheat_tracking section, with pointer to the archive.
5. **Flip** `docs/MG_UNIFIED_TODO_LIST.md §8.1 row N2` from 🔴 to ✅ Done in the SAME COMMIT (per `todo_sync` convention).

The Postgres table itself stays in place. The operator rule stays in place. The architectural decision — whether to promote the table to generic `model_overheat_tracking` or fold into `ops.failure_patterns` — is **explicitly deferred** to whoever next implements Operator Rule #6 in the live code path. That's a feature-design decision, not a Bucket 7 cleanup decision.

---

## Files changed

| File | Δ |
|---|---|
| `core/s19jpro_overheat_handler.py` | DELETED (118 lines moved) |
| `archive/sqlite_phase1/s19jpro_overheat_handler.py` | NEW (118 lines, identical content) |
| `archive/sqlite_phase1/README.md` | NEW (~70 lines) |
| `archive/README.md` | +5 lines (new sub-section entry) |
| `docs/EMPTY_STUB_TABLES.md` | +6 lines (handler-archived note) |
| `docs/MG_UNIFIED_TODO_LIST.md` | flips §8.1 row N2 to ✅ |
| `docs/RUNBOOK_BUCKET_7.3_S19JPRO_OVERHEAT_HANDLER_ARCHIVE.md` | NEW (this file) |

---

## What is **NOT** in this PR (deliberately deferred)

- **Renaming the Postgres table** to `model_overheat_tracking`. That's a feature-design decision — couple it with the implementation work, not the cleanup.
- **Folding into `ops.failure_patterns`**. Same rationale.
- **Touching the other 4 orphan Phase 1 modules** (`core/database.py`, `core/database_router.py`, `core/db_compat.py`, `core/db_helper.py`). Each of those is bigger scope and earns its own bucket. They are still imported by `migrate_*.py` or each other, even if not by the live boot path; deleting them safely needs a dedicated audit.
- **Any change to operator rule semantics**. Operator Rule #6 in `CLAUDE.md` continues to apply; this PR is purely a code-move + documentation update.

---

## Verification

```bash
# Before: handler is at core/, never imported
$ grep -rn "from core.s19jpro_overheat_handler\|import s19jpro_overheat_handler" --include="*.py"
# (zero hits)

# After: handler moved, still no imports broken (because it had none)
$ test -f core/s19jpro_overheat_handler.py && echo "FAIL: still in core" || echo "OK: moved out of core"
OK: moved out of core

$ test -f archive/sqlite_phase1/s19jpro_overheat_handler.py && echo "OK: archived" || echo "FAIL: not archived"
OK: archived
```

Live boot path is unaffected because the handler had zero callers.

---

## TODO list flip (in same commit per `work.projects.mining_guardian.todo_sync`)

- §8.1 row N2 (`s19jpro_overheat_tracking — model-specific hack`): 🔴 → ✅ Done in PR #84 (handler archived; table promotion deferred to feature work).
