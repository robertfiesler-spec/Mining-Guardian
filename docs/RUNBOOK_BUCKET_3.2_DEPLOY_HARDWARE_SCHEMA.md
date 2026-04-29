# Runbook — Deploy Catalog `hardware.*` Schema to VPS Postgres

**Bucket 3.2 of the 2026-04-29 top-to-bottom scope plan.**

**Created:** Wednesday 2026-04-29
**Target:** `mining_guardian` Postgres on VPS `srv1549463` (Tailscale `100.110.87.1`)
**Operator:** Robert (root@srv1549463)
**Time budget:** 5–10 minutes (idempotent — safe to re-run)
**Blocked by:** nothing — all SQL files are committed to `intelligence-catalog/seed-data/`
**Blocks:** Bucket 3.1 (C4 seed_miner_models.sql), Bucket 8.1 (Grafana dropdown that points at `hardware.miner_models`), Bucket 3.3 (C1 dual-write — needs `staging.*` and `hardware.*` to exist), Bucket 3.4 (C3 watcher rewrites)

---

## Why this is a runbook, not a code change

The schema files (`intelligence_catalog_schema.sql`, `_v2_additions.sql`, `_v3_additions.sql`, `staging_schema.sql`, plus the wrapper `deploy_schema.sql`) are already in the repo. The work is **executing them against the live VPS Postgres** — that's a one-shot operator action that has to happen on the VPS itself, not in a sandbox or cloud agent. This runbook gives the exact paste-along blocks plus pre-flight, verification, and rollback.

---

## Pre-flight checks (do all three; ~30 seconds)

### A. SSH to the VPS and pick a working directory

```bash
ssh root@srv1549463        # or via Tailscale: ssh root@100.110.87.1
cd /root/Mining-Guardian
git fetch origin --quiet
git log -1 --oneline origin/main
# should show the most-recent commit on main
```

### B. Confirm the SQL files are present at HEAD

```bash
ls -la intelligence-catalog/seed-data/{deploy_schema.sql,intelligence_catalog_schema.sql,intelligence_catalog_schema_v2_additions.sql,intelligence_catalog_schema_v3_additions.sql,staging_schema.sql,seed_miner_models.sql}
# expect six files, all non-empty
```

### C. Confirm Postgres is reachable and the role exists

```bash
# password for the catalog admin role lives in the installer-managed .env on the VPS
# (or wherever Robert keeps it). The DB role is `guardian_admin`, the DB is `mining_guardian`.
PGPASSWORD="<the catalog admin password>" psql -h 127.0.0.1 -U guardian_admin -d mining_guardian -c '\conninfo'

# expected: "You are connected to database \"mining_guardian\" as user \"guardian_admin\""
```

If the connection fails, **stop**. Don't proceed until `\conninfo` succeeds — running the deploy against the wrong DB or with no DB silently is the worst possible failure mode.

---

## Snapshot before deploy (mandatory)

Idempotent or not, take a snapshot before any DDL. Two minutes of `pg_dump` saves a possible afternoon of recovery.

```bash
TS=$(date +%Y%m%d_%H%M%S)
SNAP_DIR=/root/mg_snapshots/bucket_3_2_pre_deploy_${TS}
mkdir -p "${SNAP_DIR}"
PGPASSWORD="<catalog admin password>" pg_dump \
  -h 127.0.0.1 -U guardian_admin -d mining_guardian \
  --format=custom --compress=9 \
  --file="${SNAP_DIR}/mining_guardian_pre_3.2.dump"

ls -lah "${SNAP_DIR}/mining_guardian_pre_3.2.dump"
echo "Snapshot at: ${SNAP_DIR}/mining_guardian_pre_3.2.dump"
```

If `pg_dump` reports zero bytes or errors, **stop**. Investigate before doing anything else.

---

## What's already in the DB (audit before deploy)

```bash
PGPASSWORD="<catalog admin password>" psql -h 127.0.0.1 -U guardian_admin -d mining_guardian <<'SQL'
\echo '=== Current schemas ==='
SELECT schema_name FROM information_schema.schemata
WHERE schema_name IN ('hardware','firmware','ops','market','repair','pool','facility','regulatory','knowledge','seed','staging')
ORDER BY schema_name;

\echo '=== Tables per schema ==='
SELECT table_schema, COUNT(*) AS tables
FROM information_schema.tables
WHERE table_schema IN ('hardware','firmware','ops','market','repair','pool','facility','regulatory','knowledge','seed','staging')
GROUP BY table_schema ORDER BY table_schema;

\echo '=== hardware.miner_models row count (if table exists) ==='
SELECT COUNT(*) AS miner_models_count FROM hardware.miner_models;

\echo '=== hardware.manufacturers row count (if table exists) ==='
SELECT COUNT(*) AS manufacturers_count FROM hardware.manufacturers;
SQL
```

Three possible states this tells you:

| Audit result | Interpretation | Next action |
|---|---|---|
| Zero schemas listed | Fresh DB | Run **Section A** (full deploy) |
| Some schemas listed, `hardware.miner_models` errors | Partial deploy from earlier session | Run **Section A** anyway — `deploy_schema.sql` is idempotent (`CREATE … IF NOT EXISTS`, `ON CONFLICT DO NOTHING`) |
| All schemas listed, `miner_models` returns >0 | Already deployed | **Skip to Section B (verification only)** — do not re-run unless the row count is wrong |

---

## Section A — Full deploy (idempotent, ~30 seconds wall-time)

Run from the repo root (`/root/Mining-Guardian`) so the `\ir` relative-include directives in `deploy_schema.sql` resolve correctly:

```bash
cd /root/Mining-Guardian/intelligence-catalog/seed-data

PGPASSWORD="<catalog admin password>" psql \
  -h 127.0.0.1 \
  -U guardian_admin \
  -d mining_guardian \
  --set ON_ERROR_STOP=on \
  -f deploy_schema.sql 2>&1 | tee /root/mg_snapshots/bucket_3_2_pre_deploy_${TS}/deploy_schema.log
```

**`ON_ERROR_STOP=on` is required.** Without it, psql will keep going past failures and you'll think the deploy succeeded when it actually short-circuited halfway.

### What success looks like

The very last lines of the output should be (from `deploy_schema.sql:120-122`):

```
            status            | sources_count | manufacturers_count 
------------------------------+---------------+---------------------
 Schema deployment complete   |            15 |                  16
(1 row)
```

- `sources_count` should be **15** (or higher if subsequent runs added more — never less)
- `manufacturers_count` should be **16** (13 brands from the first INSERT + 3 from the second; never less)

### If the deploy errors out

1. **Read the last few lines of the log.** ``ON_ERROR_STOP=on`` means the *first* error is the cause; everything after is noise.
2. Common failures and recovery:
   - `permission denied for schema X` → wrong role; check `psql -c '\du'` and that `guardian_admin` is the DB owner
   - `extension "<name>" does not exist` → install the package on the VPS (e.g., `apt install postgresql-contrib` for `uuid-ossp`)
   - `cannot run inside a transaction block` for `ALTER TYPE` → already happens; lines 50–57 are designed to be re-run-safe individually
3. **Restore from snapshot:**
   ```bash
   PGPASSWORD="<catalog admin password>" pg_restore \
     -h 127.0.0.1 -U guardian_admin -d mining_guardian \
     --clean --if-exists \
     "${SNAP_DIR}/mining_guardian_pre_3.2.dump"
   ```
4. Re-audit (Section above) and decide whether to retry or escalate.

---

## Section B — Verification (ALWAYS do this; ~30 seconds)

Whether you ran Section A fresh or skipped it because the schema was already present, **always** run these checks before declaring victory:

```bash
PGPASSWORD="<catalog admin password>" psql -h 127.0.0.1 -U guardian_admin -d mining_guardian <<'SQL'
\echo '=== 1. All 11 schemas present? ==='
SELECT schema_name FROM information_schema.schemata
WHERE schema_name IN ('hardware','firmware','ops','market','repair','pool','facility','regulatory','knowledge','seed','staging')
ORDER BY schema_name;
-- expect: 11 rows

\echo ''
\echo '=== 2. Tables per schema ==='
SELECT table_schema, COUNT(*) AS tables
FROM information_schema.tables
WHERE table_schema IN ('hardware','firmware','ops','market','repair','pool','facility','regulatory','knowledge','seed','staging')
GROUP BY table_schema ORDER BY table_schema;
-- hardware should be 14+, total across all 11 schemas should be 86+

\echo ''
\echo '=== 3. Critical anchor tables exist and are addressable ==='
SELECT 'hardware.miner_models' AS anchor, COUNT(*) FROM hardware.miner_models
UNION ALL SELECT 'hardware.manufacturers', COUNT(*) FROM hardware.manufacturers
UNION ALL SELECT 'hardware.model_aliases', COUNT(*) FROM hardware.model_aliases
UNION ALL SELECT 'knowledge.sources', COUNT(*) FROM knowledge.sources
UNION ALL SELECT 'knowledge.contributors', COUNT(*) FROM knowledge.contributors
UNION ALL SELECT 'staging.staged_proposals', COUNT(*) FROM staging.staged_proposals;
-- expect:
--   hardware.miner_models     >= 4   (post-Bucket-3.1 will be 313+)
--   hardware.manufacturers    = 16
--   hardware.model_aliases    >= 0
--   knowledge.sources         = 15
--   knowledge.contributors    = 1
--   staging.staged_proposals  = 0   (correct — that's intake for C1)

\echo ''
\echo '=== 4. Catalog API health/detail check (after API key is known) ==='
SELECT table_schema, COUNT(*) FROM information_schema.tables
WHERE table_schema IN ('hardware','firmware','ops','market','repair','pool','facility','regulatory','knowledge','seed')
GROUP BY table_schema ORDER BY table_schema;
-- this is what /api/v1/health/detail (PR #64) returns; should match item 2 minus staging
SQL
```

If any of the four blocks shows unexpected rows or counts, the deploy is **not** complete. Re-run Section A or restore from snapshot.

---

## Post-deploy — what's now unblocked

| Bucket | Item | What it needs from this runbook |
|---|---|---|
| 3.1 | C4 — `seed_miner_models.sql` (313 rows) | Needs `hardware.miner_models` schema (✅ from Section A) |
| 8.1 | Grafana Intelligence Report dropdown | Needs `hardware.miner_models` populated by 3.1 |
| 3.3 | C1 — dual-write Path A | Needs both `staging.staged_proposals` and `hardware.miner_models` |
| 3.4 | C3 — 5 watcher rewrites | Needs `staging.*` (intake) and target `hardware.*` tables |

---

## Rollback

If the deploy succeeded but something downstream broke and we need a clean slate:

```bash
PGPASSWORD="<catalog admin password>" pg_restore \
  -h 127.0.0.1 -U guardian_admin -d mining_guardian \
  --clean --if-exists \
  "${SNAP_DIR}/mining_guardian_pre_3.2.dump"
```

This restores to exactly the state captured by the pre-deploy snapshot. Verify with the same audit query in **Section B**.

---

## Logging this deploy

After a successful Section A + Section B run, append a one-liner to `docs/MG_UNIFIED_TODO_LIST.md` §4.1 to flip the status, and stash the deploy log + audit output at:

```
/root/mg_snapshots/bucket_3_2_pre_deploy_${TS}/
  ├── mining_guardian_pre_3.2.dump
  ├── deploy_schema.log
  └── audit_post_deploy.txt   (paste of Section B output)
```

Then commit a small follow-up doc PR that flips §4 entries from 🔴 OPEN → ✅ DONE with the snapshot directory referenced for forensic continuity.

---

## Why this runbook exists in the repo

Per the user's working principles: "always comprehensive, and always over document" + "stay away from anything cloud only and stay local." The deploy is a manual VPS step that has to be paste-along reproducible six months from now or after a fleet move. Putting the runbook next to the SQL files (rather than in chat scrollback) is the durable form.
