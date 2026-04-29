# Runbook — Commit Live `002_layer2` + Staging Migrations to Repo

**Bucket 5.7 / B-7 of the 2026-04-29 top-to-bottom scope plan.**

**Created:** Wednesday 2026-04-29
**Target:** `migrations/` directory in `robertfiesler-spec/Mining-Guardian`
**Operator:** Robert (root@srv1549463 + sandbox/local clone)
**Time budget:** 15–25 minutes
**Blocked by:** nothing — operator-side SSH access to the VPS is the only requirement
**Blocks:** repo-reproducibility (a fresh `git clone` + `psql -f migrations/*.sql` cannot recreate the live DB shape until this lands)

---

## Why this is a runbook, not a code change

The two missing migrations (`002_layer2_*.sql` and the staging migration) were applied **directly to the running Postgres 16 container on the VPS** during the 2026-04-27 cutover, from the operator's local working copy. The sandbox **does not have the source SQL** — it lives only on the operator's disk and inside the live DB.

A code-only PR cannot fix this; the SQL itself must be retrieved from the VPS. This runbook gives the exact paste-along blocks to:

1. Extract the live shape from the running DB via `pg_dump --schema-only`.
2. Locate the operator's candidate `.sql` files (the originals applied on 2026-04-27).
3. Diff the candidates against the live shape — byte-level confidence that what we commit matches production.
4. Land the canonical files at `migrations/002_layer2_<suffix>.sql` and `migrations/004_staging_<suffix>.sql` (slot 003 is already taken by `003_c5_notify_triggers.sql`).
5. Add `migrations/README.md` documenting apply order.
6. Open a PR that flips B-7 in `docs/LATENT_BUGS.md` to `Fixed`.

> **Numbering note:** the original B-7 fix-plan called for `003_staging_*.sql`. That slot is now occupied by `003_c5_notify_triggers.sql` (PR #58, D-14 PR-4a). The staging migration therefore lands as `004_staging_*.sql`. The apply order on a fresh DB is `001 → 002 → 003 → 004` and is documented explicitly in the new `migrations/README.md`.

---

## Pre-flight checks (do all four; ~60 seconds)

### A. SSH to the VPS

```bash
ssh root@srv1549463        # or via Tailscale: ssh root@100.110.87.1
cd /root/Mining-Guardian
git fetch origin --quiet
git log -1 --oneline origin/main
# should show the most-recent commit on main
```

### B. Confirm Postgres is reachable

```bash
# Catalog admin role + DB; password lives in installer-managed .env
PGPASSWORD="<catalog admin password>" psql -h 127.0.0.1 -U guardian_admin -d mining_guardian -c '\conninfo'
# expected: "You are connected to database \"mining_guardian\" as user \"guardian_admin\""
```

If `\conninfo` fails, **stop**. Do not proceed.

### C. Confirm the live DB actually has the layer-2 tables

```bash
PGPASSWORD="<catalog admin password>" psql -h 127.0.0.1 -U guardian_admin -d mining_guardian <<'SQL'
\echo '=== layer-2 partitioned tables ==='
SELECT n.nspname AS schema, c.relname AS table, c.relkind
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','p')                 -- regular + partitioned
  AND (c.relname ~ 'layer2|layer_2'
       OR n.nspname = 'staging')
ORDER BY n.nspname, c.relname;

\echo '=== staging schema tables ==='
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'staging'
ORDER BY table_name;
SQL
```

Expect at least:
- One or more layer-2 partitioned parents (likely under `knowledge.*` or a dedicated schema).
- The staging schema with its tables present.

If neither shows up, **stop** — the premise of B-7 is wrong and the bug needs re-diagnosis. Capture the output and abort the runbook.

### D. Sanity-check the operator's local candidates

The two `.sql` files were applied from a working copy on 2026-04-27. Likely locations to search on the VPS:

```bash
# in the repo working copy
ls -la /root/Mining-Guardian/migrations/*.sql
ls -la /root/Mining-Guardian/*.sql 2>/dev/null
ls -la /root/Mining-Guardian/intelligence-catalog/seed-data/*.sql 2>/dev/null

# in /tmp from the cutover session
ls -la /tmp/*layer2*.sql 2>/dev/null
ls -la /tmp/*staging*.sql 2>/dev/null

# under root's home
ls -la /root/*layer2*.sql 2>/dev/null
ls -la /root/*staging*.sql 2>/dev/null

# anywhere on the box (last resort)
find / -name '*layer2*.sql' 2>/dev/null
find / -name '*staging*.sql' 2>/dev/null | grep -v 'mg_import_tool/sql/migrations'
```

Capture the path of every candidate file. Note: `mg_import_tool/sql/migrations/000_bootstrap_field_log_tables.sql` is **not** the staging migration we're after — that's a separate `mg_import_tool` bootstrap. Filter it out.

If **no** candidate files are found anywhere, skip directly to **Step 2 (reconstruct from live DB)** — `pg_dump --schema-only` is authoritative and is enough to commit the canonical files even if the originals are lost.

---

## Mandatory snapshot

We are not modifying the live DB in this runbook (read-only `pg_dump`), but take a safety snapshot anyway in case the operator runs anything else mid-stream.

```bash
TS=$(date +%Y%m%d_%H%M%S)
SNAP_DIR=/root/mg_snapshots/bucket_5_7_pre_extract_${TS}
mkdir -p "${SNAP_DIR}"
PGPASSWORD="<catalog admin password>" pg_dump \
  -h 127.0.0.1 -U guardian_admin -d mining_guardian \
  --format=custom --compress=9 \
  --file="${SNAP_DIR}/mining_guardian_pre_5.7.dump"

ls -lah "${SNAP_DIR}/mining_guardian_pre_5.7.dump"
echo "Snapshot at: ${SNAP_DIR}/mining_guardian_pre_5.7.dump"
```

---

## Step 1 — Extract the live layer-2 + staging shape

Make a working directory on the VPS for this runbook only:

```bash
WORK=/root/mg_b7_working_${TS}
mkdir -p "${WORK}"
cd "${WORK}"
```

### 1a. Layer-2 schema-only dump

The layer-2 tables likely live in `knowledge.*` (per `mg_import_tool/sql/migrations/000_bootstrap_field_log_tables.sql` patterns) or a dedicated `layer2` schema. Adjust `-n` flag once Pre-flight C confirms which.

```bash
# Replace <schema> with whichever schema Pre-flight C showed the layer-2 tables in.
# If layer-2 tables are spread across multiple schemas, repeat for each, or omit -n
# to dump all schemas and slice in step 1c.

PGPASSWORD="<catalog admin password>" pg_dump \
  -h 127.0.0.1 -U guardian_admin -d mining_guardian \
  --schema-only --no-owner --no-privileges \
  -n knowledge \
  --file="${WORK}/live_layer2_full.sql"

wc -l "${WORK}/live_layer2_full.sql"
head -30 "${WORK}/live_layer2_full.sql"
```

### 1b. Staging schema-only dump

```bash
PGPASSWORD="<catalog admin password>" pg_dump \
  -h 127.0.0.1 -U guardian_admin -d mining_guardian \
  --schema-only --no-owner --no-privileges \
  -n staging \
  --file="${WORK}/live_staging_full.sql"

wc -l "${WORK}/live_staging_full.sql"
head -30 "${WORK}/live_staging_full.sql"
```

### 1c. Slice down to just the layer-2 objects

The full `knowledge` dump will include objects from `001_initial_schema.sql` and `mg_import_tool` bootstrap. We only want the *delta* introduced by `002_layer2`. Identify which tables are layer-2:

```bash
PGPASSWORD="<catalog admin password>" psql -h 127.0.0.1 -U guardian_admin -d mining_guardian <<'SQL' > "${WORK}/layer2_object_list.txt"
\t on
\a
SELECT n.nspname || '.' || c.relname
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','p','i')
  AND c.relname ~ 'layer2|layer_2|_l2_'
ORDER BY n.nspname, c.relname;
SQL

cat "${WORK}/layer2_object_list.txt"
```

Then dump only those objects by name:

```bash
# Build a -t flag list from layer2_object_list.txt
TFLAGS=$(awk 'NF { printf " -t %s", $0 }' "${WORK}/layer2_object_list.txt")
echo "TFLAGS=${TFLAGS}"

PGPASSWORD="<catalog admin password>" pg_dump \
  -h 127.0.0.1 -U guardian_admin -d mining_guardian \
  --schema-only --no-owner --no-privileges \
  ${TFLAGS} \
  --file="${WORK}/live_layer2_only.sql"

wc -l "${WORK}/live_layer2_only.sql"
```

`live_layer2_only.sql` is now the **authoritative DDL** for everything `002_layer2` introduced.

### 1d. Capture object inventories for the PR description

```bash
{
  echo "## Layer-2 objects extracted from live DB"
  cat "${WORK}/layer2_object_list.txt"
  echo
  echo "## Staging objects extracted from live DB"
  PGPASSWORD="<catalog admin password>" psql -h 127.0.0.1 -U guardian_admin -d mining_guardian -t -A -c \
    "SELECT table_schema || '.' || table_name FROM information_schema.tables WHERE table_schema = 'staging' ORDER BY 1;"
} > "${WORK}/B7_object_inventory.txt"

cat "${WORK}/B7_object_inventory.txt"
```

Keep `B7_object_inventory.txt` — it goes into the PR body verbatim.

---

## Step 2 — Diff against the operator's candidates

For each candidate file you found in Pre-flight D:

```bash
CAND=/path/to/candidate.sql        # set per file

# 2a. Normalise both sides: strip comments, blank lines, leading/trailing whitespace
normalise() {
  grep -vE '^\s*(--|$)' "$1" | sed 's/[[:space:]]*$//' | sort
}

normalise "${CAND}" > "${WORK}/cand_norm.txt"
normalise "${WORK}/live_layer2_only.sql" > "${WORK}/live_norm.txt"

# 2b. Diff — what's in the candidate that's not in live, and vice versa?
diff -u "${WORK}/live_norm.txt" "${WORK}/cand_norm.txt" | head -80
```

**Decision table for the diff result:**

| Diff outcome | Interpretation | Action |
|---|---|---|
| Empty diff | Candidate matches live exactly | Commit the **candidate** verbatim — operators recognise it; it's the original artefact. |
| Live has objects candidate doesn't | Candidate is incomplete (e.g. someone added an index live and never updated the file) | Commit `live_layer2_only.sql` (rename per Step 3 below); add a note in the PR body that the candidate was incomplete. |
| Candidate has objects live doesn't | Candidate had cruft that was never applied, OR an object was later dropped | Strip the cruft from the candidate and commit; document each removed line in the PR body. |
| Both differ in non-trivial ways | Originals diverged from live | Commit `live_layer2_only.sql` (live is canonical); attach the candidate to the PR for archive. |

Do the same for staging (`live_staging_full.sql` vs the staging candidate).

---

## Step 3 — Build the canonical commit-ready files

### 3a. Pick the descriptive suffix

Look at what the migration actually does. Examples:

- `002_layer2_partitioned_field_log.sql` — if it adds partitioned `field_log_*` tables.
- `002_layer2_unmatched_buffer.sql` — if it adds the unmatched-row buffer.
- `002_layer2_full.sql` — if you can't pick one thing.

Whatever the suffix, it must:
- Be lowercase, snake_case.
- End with `.sql`.
- Be specific enough that a future operator reading `ls migrations/` understands what the file does without opening it.

### 3b. Header every committed file

Every committed file gets a standard header so apply order and provenance are unambiguous:

```sql
-- migrations/002_layer2_<suffix>.sql
-- B-7 — Layer-2 partitioned tables (originally applied 2026-04-27 against live DB).
-- This file was reconstructed from the live Postgres 16 schema on 2026-04-29 via
-- pg_dump --schema-only, then byte-diffed against the operator's source-of-record
-- candidate at <path on VPS at extraction time>.
-- See docs/RUNBOOK_BUCKET_5.7_COMMIT_LIVE_MIGRATIONS.md.

-- Apply order: this file runs after 001_initial_schema.sql and before
-- 003_c5_notify_triggers.sql.

-- ---- BEGIN MIGRATION ----
```

And:

```sql
-- migrations/004_staging_<suffix>.sql
-- B-7 — Staging schema for mg_import_tool (originally applied 2026-04-27).
-- Reconstructed 2026-04-29 from live DB via pg_dump --schema-only.
-- See docs/RUNBOOK_BUCKET_5.7_COMMIT_LIVE_MIGRATIONS.md.
--
-- Slot 003 is intentionally taken by 003_c5_notify_triggers.sql (D-14 PR-4a).
-- This staging migration lands at slot 004 and applies after the C5 triggers,
-- which is correct: the triggers fire on operational tables that already exist
-- in 001/002; staging is independent and may be added/dropped without affecting
-- the trigger graph.

-- Apply order: 001 → 002 → 003 → 004.

-- ---- BEGIN MIGRATION ----
```

Save the two files to the operator's local clone (or scp from the VPS to the sandbox-side clone):

```bash
# On the VPS, after building the two final files in ${WORK}:
scp "${WORK}/002_layer2_<suffix>.sql" "${WORK}/004_staging_<suffix>.sql" \
    operator-laptop:~/Mining-Guardian/migrations/
```

Or, if the runbook operator is working directly in the cloud sandbox clone, transfer via `gh api` upload (Git Data API blob → tree → commit, same pattern as PR #69 deletion + addition; not reproduced here).

### 3c. Write `migrations/README.md`

Drop this file at `migrations/README.md` to lock the apply order in:

```markdown
# Mining Guardian — Database Migrations

Migrations are plain `.sql` files applied in lexical order against the
`mining_guardian` Postgres 16 database. Apply with:

    psql -h 127.0.0.1 -U guardian_admin -d mining_guardian \
         -v ON_ERROR_STOP=1 -f migrations/<file>.sql

## Apply order

| Order | File | Purpose | First applied |
|-------|------|---------|---------------|
| 001 | `001_initial_schema.sql` | Initial schema port from SQLite | 2026-04-21 |
| 002 | `002_layer2_<suffix>.sql` | Layer-2 partitioned tables for field-log imports | 2026-04-27 (reconstructed and committed 2026-04-29 — B-7) |
| 003 | `003_c5_notify_triggers.sql` | C5 NOTIFY triggers (D-14 PR-4a) | 2026-04-28 |
| 004 | `004_staging_<suffix>.sql` | Staging schema used by `mg_import_tool` | 2026-04-27 (reconstructed and committed 2026-04-29 — B-7) |

The `migrate_sqlite_to_postgres.py` helper is **not** a migration — it's a one-shot
backfill tool used during the initial 2026-04-21 cutover. It does not need to be
re-run on a fresh install; `001` is sufficient.

## Re-running on a fresh install

A fresh `git clone` + `docker compose up postgres` followed by

    for f in migrations/[0-9][0-9][0-9]_*.sql; do
      psql -h 127.0.0.1 -U guardian_admin -d mining_guardian \
           -v ON_ERROR_STOP=1 -f "$f" || break
    done

reproduces the production schema as of 2026-04-29.

## Authoring new migrations

- Pick the next free 3-digit slot: `005_*.sql`, `006_*.sql`, etc.
- Always include a header comment with file path, purpose, and apply-order
  context (see existing files for the pattern).
- Wrap multi-statement migrations in `BEGIN; ... COMMIT;` so partial failures
  roll back.
- Add a row to the table above in the **same commit** as the new file.
```

### 3d. Flip B-7 in `docs/LATENT_BUGS.md`

In the same commit, change two places:

**Index row** (around the top table):

```diff
-| B-7 | Medium   | Live migrations `002_layer2` + staging not committed to the repo  | Not fixed  |
+| B-7 | Medium   | Live migrations `002_layer2` + staging not committed to the repo  | ✅ Fixed (2026-04-29) |
```

**Detail section header**:

```diff
-## B-7 — Live migrations `002_layer2` + staging not committed to the repo
-
-**Severity:** Medium
-**Status:** Not fixed
+## B-7 — Live migrations `002_layer2` + staging not committed to the repo  ✅ Fixed (2026-04-29)
+
+**Severity:** Medium
+**Status:** ✅ Fixed (PR #<this PR>, 2026-04-29)
```

And append a `### Fix Applied` block at the end of the B-7 section:

```markdown
### Fix Applied — 2026-04-29

- Extracted live DDL from VPS Postgres 16 via `pg_dump --schema-only` (read-only).
- Diffed against operator-side candidate files; commit content per
  `docs/RUNBOOK_BUCKET_5.7_COMMIT_LIVE_MIGRATIONS.md` Step 2 decision table.
- Committed:
  - `migrations/002_layer2_<suffix>.sql`
  - `migrations/004_staging_<suffix>.sql` (slot 003 was already taken by
    `003_c5_notify_triggers.sql`; staging migrates the tail of the apply chain
    and is independent of the trigger graph).
  - `migrations/README.md` (apply order + fresh-install instructions).
- Verification:
  ```bash
  ls migrations/
  # 001_initial_schema.sql
  # 002_layer2_<suffix>.sql
  # 003_c5_notify_triggers.sql
  # 004_staging_<suffix>.sql
  # README.md
  # migrate_sqlite_to_postgres.py

  grep -c '^| B-7 ' docs/LATENT_BUGS.md   # > 0
  grep '✅ Fixed' docs/LATENT_BUGS.md | grep -c B-7   # = 2 (index + detail header)
  ```
```

---

## Step 4 — Open the PR

Branch name: `fix/b7-commit-live-migrations-2026-04-29`

PR title: `fix(B-7): commit live 002_layer2 + 004_staging migrations + migrations/README`

PR body must include:

1. The output of Step 1d (`B7_object_inventory.txt`) verbatim.
2. The Step 2 decision-table outcome for each file (which lane each one fell into).
3. The verification grep block from Step 3d.
4. A note: *"Schema content was reconstructed from the live VPS Postgres 16 DB on 2026-04-29 via `pg_dump --schema-only` per `docs/RUNBOOK_BUCKET_5.7_COMMIT_LIVE_MIGRATIONS.md`. The original 2026-04-27 application is documented in `docs/SESSION_LOG_2026-04-27.md` addendum #3."*
5. Reviewer checklist:
   - [ ] `ls migrations/` shows files at slots 001, 002, 003, 004 plus `README.md` plus `migrate_sqlite_to_postgres.py`.
   - [ ] Both new files have the standard header (path, B-7 reference, apply-order context).
   - [ ] `migrations/README.md` apply-order table includes both new files with correct dates.
   - [ ] B-7 row in `docs/LATENT_BUGS.md` index reads `✅ Fixed (2026-04-29)`.
   - [ ] B-7 detail section reads `✅ Fixed (2026-04-29)` in the header AND has a `### Fix Applied — 2026-04-29` block.

---

## Rollback

This runbook is read-only against the live DB. Nothing to roll back DB-side.

If the PR lands and turns out to disagree with the live DB:

```bash
git revert <PR-merge-commit-sha>
```

The DB itself is untouched by either landing or reverting the PR — the migrations are documenting state that already exists, not changing it.

---

## Post-runbook unblocks

Landing this PR:

- ✅ Closes B-7.
- ✅ Closes Bucket 5 entirely (B-1, B-2, B-4, B-6 already done).
- ✅ Unblocks anyone reconstructing the DB from `git clone` (no more silent column-mismatch failures on `mg_import_tool` INSERTs against a half-built schema).
- ✅ Lands the last paste-along Bucket-5 deliverable; the rest of the unified TODO can move to Bucket 6 (installer rebuild) without holding a B-7 caveat.

---

## Operator quick-reference (TL;DR)

```bash
# 1. Pre-flight (A/B/C/D above), then snapshot.
# 2. Extract live shape:
ssh root@srv1549463
TS=$(date +%Y%m%d_%H%M%S)
WORK=/root/mg_b7_working_${TS}
mkdir -p "${WORK}" && cd "${WORK}"

PGPASSWORD="<pw>" pg_dump -h 127.0.0.1 -U guardian_admin -d mining_guardian \
  --schema-only --no-owner --no-privileges -n staging \
  --file="${WORK}/live_staging_full.sql"

# (plus the layer-2 -t-list dump per Step 1c)

# 3. Diff against operator candidates per Step 2 table.
# 4. Build canonical files with headers per Step 3a/3b.
# 5. Drop in migrations/README.md per Step 3c.
# 6. Flip B-7 in docs/LATENT_BUGS.md per Step 3d.
# 7. Open PR per Step 4.
```

---

**End of Runbook — Bucket 5.7 / B-7.**
