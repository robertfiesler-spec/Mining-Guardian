# Latent Bugs in Mining Guardian

**Created:** April 13, 2026
**Last Updated:** April 28, 2026 (addendum from PR #25 live-DB import + post-rename cleanup)

This file is the canonical registry of known but unfixed defects in the Mining Guardian
codebase. Every bug here has been **observed or confirmed** during real work — none of
this is theoretical. Each entry must include enough detail that any future session can
pick up the fix without re-deriving the context.

---

## Table of Contents

| ID  | Severity | Subject                                                           | Status     |
|-----|----------|-------------------------------------------------------------------|------------|
| B-1 | Low      | predictor.py NameError (~line 4619)                               | Not fixed  |
| B-2 | Low      | mining_guardian.py NameError in `_escalate_board_issue` (~4040)   | Not fixed  |
| B-3 | High     | `000_bootstrap_field_log_tables.sql` non-partitioned shape trap   | Not fixed  |
| B-4 | High     | `mg_import.insert_raw_json` silently swallows ingestion errors    | Not fixed  |
| B-5 | Medium   | `mg_import.py` raw_json index targets nonexistent column          | Patched out|
| B-6 | Medium   | `docs/CRON_SCHEDULE.md` references retired `Mining-Gaurdian/` typo | Not fixed  |
| B-7 | Medium   | Live migrations `002_layer2` + staging not committed to the repo  | Not fixed  |

---

## Severity Definitions

- **High** — Active defect with confirmed evidence; can corrupt data, hide failures,
  or block a future operator from running a script as-documented. Must be fixed before
  the May-5-class install gate or explicitly waived.
- **Medium** — Confirmed defect, but the workaround in place is stable. Will bite a
  future operator who reads the docs/code literally and doesn't know about the patch.
- **Low** — Code-review finding only; never observed at runtime.

---

# High-Severity Bugs

## B-3 — `000_bootstrap_field_log_tables.sql` migration trap

**Severity:** High
**Status:** Not fixed (deliberately skipped during 2026-04-27 import; flagged for post-install rebase)
**Discovered:** 2026-04-27 (PR #25 addendum #3)
**Location:** `mg_import_tool/sql/migrations/000_bootstrap_field_log_tables.sql`

### Description

The `000_bootstrap_field_log_tables.sql` migration creates `field_log_imports` and
`field_log_raw_json` as **non-partitioned** tables, and includes a `file_path_in_archive`
column that does not exist on the live partitioned variant currently running in the
`mining-guardian-db` Postgres 16 container.

Applying this migration on top of the live DB would either (a) fail outright on the
shape mismatch, or (b) — worse — succeed against an empty schema and produce a
different table layout than the one production has been running on for weeks. Either
outcome is data-corruption-grade for any future operator who runs the migrations
in numerical order without reading the addendum.

### Evidence

- During the 2026-04-27 live-DB migration session, the operator deliberately skipped
  `000_bootstrap_field_log_tables.sql` and only applied `002_layer2` plus the staging
  migration. See `docs/SESSION_LOG_2026-04-27.md` addendum #3.
- A diff between the migration's `CREATE TABLE` and the live `\d field_log_imports`
  output confirms the partitioning clause and the `file_path_in_archive` column are
  the disagreement points.

### Reproduction

Any future fresh-install path that runs `mg_import_tool/sql/migrations/*.sql` in
order will trip this. The current "live DB" was built by applying `001_initial_schema.sql`
plus the partition-aware schema delivered manually months ago, so `000_*` was never
exercised in production.

### Fix Plan

1. Rebase `000_bootstrap_field_log_tables.sql` onto the partitioned shape that the
   live DB actually uses (drop `file_path_in_archive`, add `PARTITION BY` clause,
   and the per-quarter partition children).
2. Add a guard at the top of the file: `DO $$ BEGIN IF EXISTS (...) THEN RAISE
   NOTICE 'already applied'; RETURN; END IF; END $$;` to make it idempotent.
3. Add a regression test in `tests/test_migrations.py` that diffs the post-migration
   schema against the canonical partitioned shape captured in `docs/db/SCHEMA.md`.
4. Mark this bug as fixed in this file with the PR number and commit SHA.

### References

- `docs/SESSION_LOG_2026-04-27.md` — addendum #3
- PR #25 (squashed as `6f0b5a2`)
- `docs/DECISIONS.md` D-1 (Postgres-as-canonical)

---

## B-4 — `mg_import.insert_raw_json` silently swallows ingestion errors

**Severity:** High
**Status:** Not fixed (post-install TODO)
**Discovered:** 2026-04-27 (PR #25 addendum #3)
**Location:** `mg_import_tool/mg_import.py` — `insert_raw_json()` function

### Description

`insert_raw_json()` opens an autocommit-isolated connection and wraps the entire
insert in a broad `try / except Exception: pass`. Any failure — schema mismatch,
unique-constraint violation, JSON type error, network blip, anything — is swallowed
silently. The outer caller never sees the failure, no log line is produced, and the
import driver happily reports "all archives processed" while the raw-JSON table has
been left starved.

### Evidence

After the 2026-04-27 live import of 127 archives:

```
mining_guardian=# SELECT count(*) FROM field_log_raw_json;
 count
-------
     3

mining_guardian=# SELECT count(*) FROM field_log_imports;
 count
-------
   127
```

127 imports succeeded. 124 raw-JSON inserts failed silently. The discrepancy was only
caught because the operator ran the post-import baseline diff (Block H of the runbook).
With no diff, the silent loss would have shipped to production.

### Reproduction

Any archive whose top-level JSON shape doesn't match the (currently undocumented)
constraints on `field_log_raw_json` will trigger the swallow. The exact failing shape
is not yet known because, by definition, the exception is discarded before it can
be logged.

### Fix Plan

1. Replace the bare `except Exception: pass` with `except Exception as e: logger.error(...);
   raise` (or, if the autocommit isolation is intentional, log + re-raise inside the
   connection's `__exit__`).
2. Add a unit test that injects a deliberately malformed JSON shape and asserts the
   exception propagates.
3. Backfill the 124 missing rows from the on-disk archives once root cause is known.
4. Add a runtime invariant check at the end of `run_full_import.py`:
   `assert raw_json_count >= imports_count * 0.95` (or similar threshold) and fail
   loudly if violated.

### References

- `docs/SESSION_LOG_2026-04-27.md` — addendum #3
- PR #25 (squashed as `6f0b5a2`)
- B-5 below — the index patch is part of why raw-JSON inserts were failing

---

# Medium-Severity Bugs

## B-5 — `mg_import.py` raw_json index targets nonexistent column

**Severity:** Medium
**Status:** Patched out (lines 1315-1316 commented out 2026-04-27); needs proper fix
**Discovered:** 2026-04-27 (PR #25 addendum #3)
**Location:** `mg_import_tool/mg_import.py` lines 1315-1316

### Description

The `mg_import.py` driver attempted to `CREATE INDEX ... ON field_log_raw_json
(raw_json_jsonb_field)` against the live partitioned table, but the live partitioned
variant does **not** have a `raw_json_jsonb_field` column — that column only exists
on the non-partitioned shape from the (broken) `000_bootstrap_field_log_tables.sql`
migration (see B-3).

The lines were commented out during the 2026-04-27 import to unblock the run, with
the marker:

```python
# 2026-04-27: partitioned raw_json table — see docs/SESSION_LOG addendum #3
```

The patch is stable but it's a surface-level fix. The *real* fix is to converge
the partitioned-vs-non-partitioned schema disagreement (which is B-3), then restore
the index against the correct column name.

### Evidence

`git blame` on `mg_import.py:1315-1316` shows the comment-out commit on the
`mg/pr25-bulk-import-tools` branch, merged via PR #25.

### Reproduction

Any operator who reverts the comment-out without first fixing B-3 will hit:
```
psycopg2.errors.UndefinedColumn: column "raw_json_jsonb_field" does not exist
```

### Fix Plan

Coupled to B-3. Fix B-3 first (rebase `000_bootstrap_*` onto partitioned shape),
then:

1. Confirm the partitioned table exposes a `raw_json_jsonb_field` column (or pick
   the correct equivalent column name — likely `payload` or `data`).
2. Uncomment lines 1315-1316 and update the column reference.
3. Add `CONCURRENTLY` to the index creation if the table is large.
4. Remove the `# 2026-04-27` marker comment.

### References

- `docs/SESSION_LOG_2026-04-27.md` — addendum #3
- B-3 (root cause)
- PR #25 (squashed as `6f0b5a2`)

---

## B-6 — `docs/CRON_SCHEDULE.md` references retired `Mining-Gaurdian/` typo

**Severity:** Medium
**Status:** Not fixed
**Discovered:** 2026-04-28 (this session, while reviewing post-rename cleanup)
**Location:** `docs/CRON_SCHEDULE.md`

### Description

On Sunday 2026-04-26, the VPS directory was renamed from `/root/Mining-Gaurdian/`
(typo, missing the `r`) to `/root/Mining-Guardian/` (correct spelling) as part of
PR #1. The cron jobs documented in `docs/CRON_SCHEDULE.md` still reference the old
typoed path. Any operator who copies these cron lines onto a freshly-provisioned
VPS will end up writing to a directory that does not exist — silent failure, since
cron's stderr is mailed to root and routinely ignored.

The actual cron jobs running on the live Hostinger VPS (187.124.247.182) were
updated in place during the 2026-04-26 rename, so production is fine. The risk
is purely "future re-install copies stale doc."

### Evidence

```bash
$ grep -n 'Mining-Gaurdian' docs/CRON_SCHEDULE.md
# (expected: several hits — full list TBD when fix is opened)
```

### Reproduction

Any greenfield VPS deploy that uses `docs/CRON_SCHEDULE.md` as its source of truth
will install crons pointing at the wrong path.

### Fix Plan

1. `Select-String -Path docs/CRON_SCHEDULE.md -Pattern 'Mining-Gaurdian'` to enumerate
   every hit.
2. Replace `Mining-Gaurdian` → `Mining-Guardian` (note the position of the `r`).
3. Add a CI lint that fails the build if the string `Mining-Gaurdian` appears
   anywhere in the repo (the tag `archive/installer-build-20260428` is the only
   legitimate reference and lives outside the working tree).
4. Optional: add a one-line note at the top of `CRON_SCHEDULE.md` explaining the
   2026-04-26 rename for historical context.

### References

- PR #1 (2026-04-26) — VPS directory rename
- `docs/CLAUDE.md` — Repo paths section

---

## B-7 — Live migrations `002_layer2` + staging not committed to the repo

**Severity:** Medium
**Status:** Not fixed
**Discovered:** 2026-04-28 (this session, post-import audit)
**Location:** `migrations/` — should contain `002_layer2_*.sql` and the staging
migration; currently contains only `001_initial_schema.sql` and
`migrate_sqlite_to_postgres.py`.

### Description

During the 2026-04-27 live-DB cutover, two migrations were applied to the running
Postgres 16 container:

1. `002_layer2_*.sql` — adds the layer-2 partitioned tables and indexes.
2. The staging migration — wires up the staging schema used by `mg_import_tool`.

Both were applied from the operator's local working copy. Neither was committed
to the repo. The repo's `migrations/` directory therefore does **not** describe
the current shape of the live DB; anyone reconstructing the DB from the repo will
end up at `001_initial_schema.sql` only.

### Evidence

```bash
$ ls migrations/
001_initial_schema.sql
migrate_sqlite_to_postgres.py
```

vs. the live DB which has the layer-2 partitioned tables present and populated
with 127 rows.

### Reproduction

A fresh `git clone` + `docker compose up` + `psql -f migrations/*.sql` will produce
a DB that cannot accept the import driver's INSERTs (column mismatch, partition
not declared).

### Fix Plan

1. Locate the two `.sql` files on the operator's local disk (likely under the
   working clone or `/tmp/` from the 2026-04-27 session).
2. Verify they are byte-identical to what was applied in production by diffing
   against the `pg_catalog`-extracted DDL of the live DB.
3. Commit them as `migrations/002_layer2_<descriptive_suffix>.sql` and
   `migrations/003_staging_<descriptive_suffix>.sql`, in the order they were
   applied.
4. Add a `migrations/README.md` that explains the apply order and what each file
   does.
5. Update `docs/CLAUDE.md` and `docs/SESSION_LOG_2026-04-27.md` to point at the
   committed paths.

### References

- `docs/SESSION_LOG_2026-04-27.md` — addendum #3
- PR #25 (squashed as `6f0b5a2`)
- `docs/DECISIONS.md` D-1 (Postgres-as-canonical)

---

# Low-Severity Bugs

## B-1 — `predictor.py` NameError (~line 4619)

**Severity:** Low
**Status:** Not triggered in 1,482 scans (as of 2026-04-13)
**Discovered:** 2026-04-12 (code review)
**Location:** `predictor.py` ~line 4619

### Description

A variable is referenced before assignment on a code path that has never been
exercised in production. Caught during the April 12 manual code review.

### Fix Plan

Fix when next editing the file. Add a unit test that exercises the code path
to prevent regression.

### References

- `docs/REPAIR_LOG.md` 2026-04-12 entry

---

## B-2 — `mining_guardian.py` NameError in `_escalate_board_issue` (~line 4040)

**Severity:** Low
**Status:** Not triggered in 1,482 scans (as of 2026-04-13)
**Discovered:** 2026-04-12 (code review)
**Location:** `mining_guardian.py` ~line 4040, `_escalate_board_issue`

### Description

NameError on a rarely-taken escalation branch. Same review as B-1.

### Fix Plan

Fix when next editing the file. Add a unit test that exercises the escalation
branch to prevent regression.

### References

- `docs/REPAIR_LOG.md` 2026-04-12 entry

---

# Process Notes

- New bugs go in here **before** any cleanup or refactor that would erase the
  evidence trail. Over-document — assume the next session has zero memory.
- Every entry must include: severity, status, discovery date, location, description,
  evidence (with literal output where possible), reproduction, fix plan, references.
- When a bug is fixed, do **not** delete the entry. Move it to a "Resolved" section
  at the bottom (to be added on first resolution) with the PR number, commit SHA,
  and date.
- Severity ordering inside each section is by ID, not by priority — priority is
  determined by status + the "Status" field of each entry.
