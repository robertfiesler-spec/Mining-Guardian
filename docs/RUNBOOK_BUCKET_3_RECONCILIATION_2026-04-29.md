# Bucket 3 / Section 4 Reconciliation — Operator Verification Runbook

**Date:** 2026-04-29 (Wednesday)
**Author:** Mining Guardian agent
**Purpose:** Confirm on the **live ROBS-PC catalog Postgres** that all four C-items (C1 / C3 / C4 / C5) are functionally satisfied — schema deployed, 317 rows seeded, dual-writer wired, watchers staging proposals, feedback loop tested.
**Doctrine:** "rather be late and perfect than early and wrong" — verify before declaring done.

---

## 0. Why this runbook exists

The TODO list (`docs/MG_UNIFIED_TODO_LIST.md` Section 4) had four rows marked 🔴 OPEN that were actually closed on **2026-04-27** in PRs #13 / #15 / #16 / #22. The rows were never flipped at the time. Today's reconciliation:

1. Flipped all four to ✅ DONE in `MG_UNIFIED_TODO_LIST.md` (this PR — Bucket 3 reconciliation)
2. Documented closure evidence per item (PR sha + session log lines)
3. Created **this runbook** so an operator at the ROBS-PC machine can run nine fast verification commands and confirm the live DB matches the documented state

Once Bobby runs and confirms, Section 4 can be moved into Section 1 (Already Done) or archived in a closing note.

---

## 1. Prerequisites (one-time setup at the operator machine)

These are the only environment requirements for the verification:

```bash
# ROBS-PC, PowerShell or cmd:
echo $env:MG_DB_PASSWORD
# Should print the catalog password. If empty, set it:
#   $env:MG_DB_PASSWORD = "tX-fhG#iJdm{V?>uuZ35G-Y)O5<UeN=5"
# (or whatever the current secret is — check secrets.bat / Mac-Mini secrets.env)

# Catalog Postgres container running:
docker ps --filter "name=mining-guardian-db" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
# Expect: mining-guardian-db   Up <duration>   0.0.0.0:5432->5432/tcp
```

If the container isn't running:

```bash
cd intelligence-catalog
docker compose up -d
sleep 3
```

---

## 2. Nine-step verification

Each step is one command. Paste actual output beside each step when filling out this runbook for an audit record.

### 2.1. Schema present (Bucket 3.2 / PR #68)

```powershell
docker exec -e PGPASSWORD=$env:MG_DB_PASSWORD mining-guardian-db `
  psql -U guardian_admin -d mining_guardian -tAc `
  "SELECT count(*) FROM information_schema.tables WHERE table_schema IN ('hardware','ops','market','knowledge','firmware','repair','facility','mg','staging','public');"
```

**Expected:** `98` (95 catalog + 3 staging) per `SESSION_LOG_2026-04-27.md` L656.

### 2.2. C4 — `hardware.miner_models` row count (PR #13)

```powershell
docker exec -e PGPASSWORD=$env:MG_DB_PASSWORD mining-guardian-db `
  psql -U guardian_admin -d mining_guardian -tAc `
  "SELECT count(*) FROM hardware.miner_models;"
```

**Expected:** `324` (320 from `seed_miner_models.sql` + 4 from base schema).

### 2.3. C4 — Idempotency of `seed_catalog.sh`

From inside the container or with psql client locally:

```bash
PGHOST=localhost PGPORT=5432 PGUSER=guardian_admin PGDATABASE=mining_guardian \
  bash scripts/seed_catalog.sh
```

**Expected stdout:**

```
[seed_catalog] hardware.miner_models currently has 317 rows.
[seed_catalog] Already seeded (>= 320 rows). Skipping.
```

**Expected exit:** `0`. This proves the runner is idempotent — re-running on a populated DB is safe.

### 2.4. C3 — Manufacturer & alias counts (PR #16)

```powershell
docker exec -e PGPASSWORD=$env:MG_DB_PASSWORD mining-guardian-db `
  psql -U guardian_admin -d mining_guardian -tAc `
  "SELECT 'manufacturers='||count(*) FROM hardware.manufacturers UNION ALL `
   SELECT 'model_aliases='||count(*) FROM hardware.model_aliases UNION ALL `
   SELECT 'family_aliases='||count(*) FROM mg.model_family_aliases;"
```

**Expected (per `SESSION_HANDOFF_2026-04-24.md` L318 + `SESSION_LOG_2026-04-27.md` L658):**

```
manufacturers=16
model_aliases=12852
family_aliases=1494
```

### 2.5. C3 — Watcher idempotency (PR #16)

```bash
cd intelligence-catalog
python -m watchers.manufacturer_watcher --dry-run --manufacturer bitmain
```

**Expected:** zero new staging rows. If the first run already happened, a dry-run will show *Would create 0 rows* for all three staging tables.

### 2.6. C1 — Dual-writer adapter health (PRs #15 + #16)

```bash
cd /path/to/Mining-Guardian
pytest intelligence-catalog/db/tests/test_dual_writer.py -q
```

**Expected:** all tests pass, no skips. Specifically the UUID adapter test (`test_uuid_adapter_registered_idempotently`) added in the PR #15 → PR #16 follow-up must pass.

### 2.7. C5 — Feedback loop tests (PR #22)

```bash
pytest intelligence-catalog/db/tests/test_feedback_loop.py -q
```

**Expected:** **13/13** pass. The three sync paths (action audit, llm analysis, miner restarts) plus the orchestrator and the fail-soft / dry-run / idempotency cases.

### 2.8. C5 — Source attribution sanity (PR #22)

```powershell
docker exec -e PGPASSWORD=$env:MG_DB_PASSWORD mining-guardian-db `
  psql -U guardian_admin -d mining_guardian -tAc `
  "SELECT source_id, count(*) FROM ops.failure_patterns GROUP BY source_id ORDER BY count(*) DESC;"
```

**Expected (after first real C5 run):** rows attributed to `a0000000-0000-0000-0000-00000000000f` (`bobby_operational`, tier2). On a fresh DB this returns zero rows — that's also acceptable; what matters is that **all** rows present have that exact source UUID.

### 2.9. Catalog API coverage check (PR #22 companion)

```bash
cd intelligence-catalog
python tools/verify_catalog_api_coverage.py
```

**Expected stdout:** "All 21 `_check_table_exists()` callsites in `catalog_api.py` plus 2 C5 probes resolve to existing tables." Exit 0.

---

## 3. Pass / fail decision tree

| If 2.1 fails | Schema not deployed. Re-run Bucket 3.2 path: `psql -U guardian_admin -d mining_guardian -f intelligence-catalog/seed-data/deploy_schema.sql`. |
| If 2.2 < 317 | Seed never ran or table truncated. Run `bash scripts/seed_catalog.sh` (no `--force`). If it still skips, check `--force` path with truncate (see `seed_catalog.sh:124-135`). |
| If 2.3 doesn't say "Already seeded" | Either rows < 320 (see above) or the env vars are pointing at a different DB. Verify `PGHOST` / `PGUSER` / `PGDATABASE`. |
| If 2.4 counts disagree | Likely a partial / failed import. Re-run `compile_all_miners.py` after truncating only the affected tables. **Do not** rerun the manufacturer watcher live — first audit `staging.miner_model_proposals` for unintended pending rows. |
| If 2.5 produces non-zero new rows | Watcher finding **new** data — that's good. Review `staging.*` rows manually before promoting. Idempotency only applies to **already-known** facts. |
| If 2.6 fails | Likely a psycopg2 UUID adapter regression. Check `intelligence-catalog/db/dual_writer.py:_ensure_uuid_adapter()`. |
| If 2.7 < 13/13 | Open issue, do not declare C5 done. The 13-test set is the contract. |
| If 2.8 shows non-`bobby_operational` source on rows in `ops.failure_patterns` | Source attribution drift — investigate which call wrote the row. |
| If 2.9 reports an unresolved table | Either schema drift or `catalog_api.py` references a table that was renamed. Open issue. |

---

## 4. After verification

- [ ] All 9 steps pass → flip `MG_UNIFIED_TODO_LIST.md` § 4.1–4.5 from "DONE-pending-verification" to "DONE-verified-on-ROBS-PC-YYYY-MM-DD"
- [ ] All 9 steps pass → consider archiving § 4 of the unified TODO into Section 1 (Already Done)
- [ ] Any step fails → fix the underlying issue, do **not** re-mark as DONE; capture the gap in `docs/LATENT_BUGS.md`

The Mac Mini install (May 5+) re-runs steps 2.1 / 2.2 / 2.3 / 2.7 automatically as part of `scripts/setup.sh` Phase 5. So this runbook is also a preview of what will be observed on the customer machine.

---

## 5. Cross-references

- `scripts/seed_catalog.sh` (PR #13) — the idempotent seed runner
- `intelligence-catalog/db/dual_writer.py` (PR #15) — Path A dual-write per D-12
- `intelligence-catalog/db/feedback_loop.py` (PR #22) — Layer 5 feedback loop
- `intelligence-catalog/watchers/manufacturer_watcher.py` (PR #16) — C3 framework
- `intelligence-catalog/seed-data/README.md` — canonical install order
- `docs/SESSION_LOG_2026-04-27.md` — Monday's marathon session that closed all of these
- `docs/CATALOG_ORPHAN_TABLES_2026-04-28.md` — orphan-table audit that confirmed `hardware.miner_models = 317`
- `docs/SESSION_HANDOFF_2026-04-24.md` — earlier baseline counts
- `docs/DECISIONS.md` D-12 — Postgres-as-truth ruling
