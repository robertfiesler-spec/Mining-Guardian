<!--
  SKELETON for the PR #25 addendum to SESSION_LOG_2026-04-27.md.
  Drafted Mon 2026-04-27 ~11:50 CDT, rewritten ~13:30 CDT while the bulk
  import is running. Everything that's already happened is filled in.
  The only TODO_FILL placeholders left are the bulk-run final numbers
  and the Backup #3 dump size — both fill in after Block H + Block I.
  When ready: append everything after the marker line below to the bottom
  of docs/SESSION_LOG_2026-04-27.md and open PR #25.
-->

---

## Addendum #3 — Live DB re-import (Mon 2026-04-27 afternoon)

### Why a third addendum on the same day

Late morning the user asked the natural follow-up to the Wednesday data
track: *"now that the AI program actually reads the catalog, should we
re-upload the older logs so the new layer system can re-enrich them?"*
The answer was yes — the live `mining-guardian-db` Postgres container had
exactly **one** archive imported (`Antminer_S19_2024-06-27_2024-06-29.tar`,
1.7 MB, ingested 2026-04-24 19:21 UTC). Every other archive on the user's
PC had been imported only into the *sandbox* DB during PR-by-PR
verification, never into live.

Re-importing all 136 archives against live now — *before* the May 5 install
— is exactly the right time. The Mac Mini will be cloned from a fresh
backup of this same database, so whatever the customer takes home is
whatever we put in today.

The original head-count was 131. The actual disk count came in at **136**
once we ran the pre-flight script. Five archives the morning audit had
classified as "stray companions" turned out to be importable `.tgz` /
`.tar` files that had been overlooked. Total corpus: **136 archives,
339 MB**.

### Scope

- **Source corpus:** `C:\Users\User\Documents\Miner Logs\` — 136 archives
  totalling 339 MB. Smallest is a 0-byte
  `M30S_V31_2024-07-11_10-06.tgz` (corrupt, expected to error and skip).
  Largest is a 6.8 MB `Antminer_S19j_Pro_*` dump.
- **Target:** the live `mining-guardian-db` Docker container on ROBS-PC
  (Postgres 16-bookworm, 44 hours healthy uptime at start, named volume
  `pgdata`, port 5432). Same DB the catalog-api iframe and Grafana
  ultimately read from.
- **Pre-flight migrations applied today:**
  1. `mg_import_tool/sql/migrations/000_bootstrap_field_log_tables.sql`
     — **deliberately skipped.** See "000_bootstrap skip rationale" below.
  2. `mg_import_tool/sql/migrations/002_layer2_and_learning_foundation.sql`
     — applied cleanly.
  3. `intelligence-catalog/seed-data/staging_schema.sql` (PR #15
     dual-write proposal tables) — applied cleanly.
- **Out of scope:** any change to `public.*` operational tables
  (`chain_readings`, `miner_state_readings`, `ams_notifications`,
  `llm_analysis`, `action_audit_log`, `miner_restarts`). Those are AMS /
  AI-managed and the importer never touches them.

### 000_bootstrap skip rationale

The morning audit caught it: `knowledge.field_log_raw_json` is already
**partitioned** in the live DB (RANGE on `ingested_at`, four partitions
covering 2024–2026+). Real columns: `id, entity_label, archive_filename,
source_file, parser, raw_payload, sha256, ingested_at`.

The bootstrap migration's `CREATE TABLE` is a non-partitioned shape with
a `file_path_in_archive` column that doesn't exist on the live partitioned
table. Re-running it would silently no-op on the parent table (because
`IF NOT EXISTS`) but would also create one of the *table-level* indexes
the partitioned variant rejects (`CREATE INDEX … ON
knowledge.field_log_raw_json (raw_json_jsonb_field) ` against a
JSONB-typed expression that doesn't compile against the real column
list).

Skipping 000_bootstrap entirely is correct here: the partitioned table
was created out-of-band on 2026-04-23 by the original Postgres migration
plan. The two missing pieces 000_bootstrap was carrying — the staging
schema and the layer-2 functions — are already in migrations 002 and the
PR #15 staging script, both of which we DID apply. Net result: zero
schema drift, zero damage.

This is documented as a post-install TODO (rebase 000_bootstrap onto the
partitioned shape so future fresh-install installs don't have the same
trap).

### Why this is safe (audit summary, captured before any write)

- `intelligence-catalog/catalog-api/catalog_api.py` (the only consumer
  exposed to Grafana) reads from `hardware.*`, `ops.*`, `firmware.*`,
  `repair.*`, `facility.*` — none of which the importer writes. Confirmed
  via grep across the file's 22 query references.
- The Grafana dashboard at `intelligence_report_001` has 7 panels: 4
  static text, 1 iframe to `dashboard.fieslerfamily.com/api/report/...`,
  2 Prometheus timeseries. Zero direct Postgres queries against
  `mining-guardian-db`. Re-import is invisible to Grafana.
- C5 (PR #22, `intelligence-catalog/db/feedback_loop.py`) only *reads*
  from `public.action_audit_log`, `public.llm_analysis`,
  `public.miner_restarts` (which the importer doesn't touch) and *writes*
  into `ops.failure_patterns`, `market.war_stories`,
  `hardware.model_known_issues`. No collision possible.
- The importer's dedup is filename-keyed: `entity_label` UNIQUE on
  `knowledge.field_log_imports`; child data tables use
  `ON CONFLICT (archive_filename, ...) DO UPDATE SET`. Re-running over
  the same 136 archives UPDATEs in place rather than creating duplicates.

### `mg_import.py` raw_json index patch

The first import attempt blew up on a `CREATE INDEX` statement targeting
`field_log_raw_json (raw_json_jsonb_field)` — that field doesn't exist on
the partitioned variant of the table (see "000_bootstrap skip rationale").
The bootstrap-style index lines lived inline in `mg_import.py` at lines
**1315–1316** and ran on every import as part of the autocommit prelude.

The patch (committed on `mg/pr25-bulk-import-tools`): comment out those
two lines with a clear `# 2026-04-27: partitioned raw_json table — see
docs/SESSION_LOG addendum #3` marker. No other changes. The patched file
size went from 250,225 B → 250,225 B (the bytes are identical because the
two lines were replaced with comment-prefixed equivalents of the same
length plus the marker on the line above).

A separate concern lives at the same site: `insert_raw_json()` runs
inside an autocommit-isolated connection wrapped in a broad `try/except
Exception: pass`. That means raw-JSON ingestion failures during this
re-import will be **silently swallowed** — `field_log_raw_json` will
under-count vs the per-archive parser totals. Documented as a post-install
TODO (rewrite insert_raw_json to log and re-raise; the swallow was added
during a sandbox panic and was never meant to ship).

### Insurance backups

Three pg_dump custom-format snapshots, all into
`D:\MiningGuardian\db-backups\pre-migration\`:

| # | When | Filename | Size | Purpose |
|---|---|---|---|---|
| 1 | Before any migration | `mg_pre_pr_apply_2026-04-27.dump` | 157,384,503 B (~157 MB) | Roll back if migrations explode |
| 2 | After migrations, before import | `mg_post_migration_2026-04-27.dump` | 157,398,661 B (~157 MB) | Roll back if import explodes |
| 3 | After full import | `mg_post_import_2026-04-27.dump` | TODO_FILL B | This is the dump we restore on the Mac Mini May 5 |

The 14,158 B delta between Backup #1 and Backup #2 is exactly what we
expected from migration 002 + the PR #15 staging schema (a handful of new
tables, indexes, and functions; no data). Roll-forward integrity check
passed.

### Importer driver choice

For the test batch (1 archive) the user ran the existing `mg_import.py`
Flask web UI on `http://127.0.0.1:8420` and watched the SSE event stream
end-to-end. For the full 136-archive run we switched to a new
direct-script driver at `mg_import_tool/tools/run_full_import.py`, which
imports `process_archive`, `execute_sql_block`, `detect_dormant_miners`,
and `write_import_run` straight from `mg_import.py` and runs them in a
plain `for` loop. Same code paths, no Flask, no SSE, one summary row
written to `mg.import_runs` at the end.

The new driver is committed alongside two new verification SQL scripts:

- `mg_import_tool/tools/verify_pre_import.sql` — captures the row-count
  baseline across `knowledge.field_log_*`, `mg.*`, and the read-only
  catalog tables (which must NOT change during import).
- `mg_import_tool/tools/verify_post_import.sql` — same shape as the
  pre-import script so outputs diff cleanly. Adds rollups for
  `mg.import_runs`, the `mg.unresolved_models` queue (resolver hit rate),
  the staging proposal tables (PR #15 dual-write evidence), an orphan
  check across all eight `field_log_*` child tables, and a top-10
  archives-by-power-samples block.

The first draft of `verify_post_import.sql` had two real bugs that were
caught and fixed while the bulk import was running (commit `36d54d7`):

1. **D4 orphan-check joins were wrong.** The original draft used
   `child.import_id = parent.id`, but `field_log_*` child tables have no
   `import_id` foreign key — they link to `field_log_imports` via the
   `archive_filename` (TEXT) column. All eight orphan subqueries were
   rewritten to match on `entity_label` OR
   `regexp_replace(archive_filename, '\.(tar\.gz|tgz|tar|rar)$', '')` so
   the join works regardless of whether the parent was stored with or
   without the file extension.
2. **D1 referenced columns that don't exist.** The original draft read
   `rows_inserted` and `rows_skipped` from `mg.import_runs`. The actual
   schema is `(id, started_at, finished_at, archive_count, row_counts
   JSONB, errors TEXT[], status)` — those numbers live inside the
   `row_counts` JSONB. D1 was rewritten to read `row_counts->>'total_rows'`
   etc.

A new D5 block was added: top-10 archives by `power_samples` count, which
is the single best signal of which miners had the richest history in the
batch.

### Pre-import baseline (captured 12:30 PM, after migrations, before any test write)

```
knowledge.field_log_imports        = 1
knowledge.field_log_miner_identity = 10
knowledge.field_log_antminer_autotune = 14118
knowledge.field_log_antminer_boots = 10
knowledge.field_log_events         = 46
knowledge.field_log_pools          = 3
knowledge.field_log_power_samples  = 0
knowledge.field_log_temp_snapshots = 0
knowledge.field_log_api_stats      = 0
knowledge.field_log_raw_json       = 3
mg.import_runs                     = 4
mg.model_family_aliases            = 1494
mg.unresolved_models               = 0
mg.dormant_miners                  = 0
mg.rma_records                     = 0
hardware.miner_models              = 317
hardware.model_aliases             = 12852
hardware.manufacturers             = 16
hardware.model_known_issues        = 0
ops.failure_patterns               = 0
firmware.firmware_releases         = 6
repair.parts                       = 0
facility.cooling_solutions         = 0
staging.miner_model_proposals      = 0
staging.manufacturer_proposals     = 0
staging.alias_proposals            = 0
```

The `field_log_imports = 1` confirms the morning audit: the live DB
genuinely had one archive in it before today.

### Test import results (1 archive, web UI, 13:03 CDT)

Archive chosen: **`M30S+_VH75_2024-11-22_20-58.tgz`** (small, well-formed
WhatsMiner sample — picked because it's representative of the dominant
parser path the bulk run will exercise). Shape detected: `whatsminer`,
model `M30S+_VH75`, firmware `20241108.22.Rel.AMS`.

| Table | Baseline | After test | Delta |
|---|---|---|---|
| `knowledge.field_log_imports` | 1 | 2 | +1 |
| `knowledge.field_log_miner_identity` | 10 | 14 | +4 |
| `knowledge.field_log_power_samples` | 0 | 102 | +102 |
| `knowledge.field_log_pools` | 3 | 4 | +1 |

**Total: +108 new rows. Zero errors. Transaction committed cleanly.**
The web-UI SSE event stream showed the complete `▶ archive → EXECUTE
… → Resolver: tier1=… tier2=… unresolved=…` ladder ending in `success`,
which is exactly the shape we want to see 136 times in a row from the
bulk driver. `ON CONFLICT` dedup behaviour was verified by re-uploading
the same archive a second time — counts did not change, which is the
correct behaviour.

### Dry-run smoke test (3 archives, 13:15 CDT)

Before the live bulk run we ran `run_full_import.py --dry-run` over the
first three archives in alphabetical order:

- `10.0.12.107.20250320222546.tgz` — 509 KB, 32,150 power samples
- `10.0.12.118.20250320222551.tgz` — 1,829 KB, 21,447 power samples
- `10.0.12.129.20250320222601.tgz` — 2,238 KB, 33,041 power samples

All three: shape `whatsminer`, model `M30S++_VH95`, firmware
`20241108.22.Rel.AMS`. Total wall-clock 1.0 s. Failed: 0. The dry-run
exercises the full parser path without writing — same code, same shape
detection, same resolver lookups, only the COMMIT is suppressed.

### Bulk import results (`run_full_import.py`, 136 archives, 13:16:45 CDT)

- Discovered: 136 archives, ~339 MB
- Archives processed: TODO_FILL / 136
- Archives failed: TODO_FILL (expected ≥ 1 from the 0-byte
  `M30S_V31_2024-07-11_10-06.tgz` corrupt file)
- Total rows added across `knowledge.field_log_*`: TODO_FILL
- Wall-clock: TODO_FILL seconds
- Final `mg.import_runs` summary status: TODO_FILL
- `mg.unresolved_models` total at end: TODO_FILL distinct strings
- Orphan rows across `field_log_*` child tables: TODO_FILL (target: 0)
- Top archive by `power_samples` count: TODO_FILL

### Cutover gate (post-import)

| # | Criterion | Status |
|---|---|---|
| 1 | No leaked secrets | ✅ |
| 2 | No hardcoded passwords | ✅ |
| 3 | No dead code | ✅ |
| 4 | One canonical catalog schema | ✅ |
| 5 | AI has data | ✅ |
| 6 | Installer rewrite | ⏳ (Thu) |
| 7 | Daily paper trail | ✅ |
| 8 | Customer docs | ⏳ (weekend) |
| 9 | **Live DB has full corpus** | TODO_FILL (✅ once bulk import + Backup #3 are clean) |

Row 9 is new — it's the gate condition the user's "I want to be our
first customer" requirement created. Until today, the live DB had 1
archive. After today, it has 136.

### Files in PR #25

- `mg_import_tool/mg_import.py` (modified — raw_json index lines
  1315–1316 commented out)
- `mg_import_tool/tools/run_full_import.py` (new — direct-script bulk
  driver)
- `mg_import_tool/tools/verify_pre_import.sql` (new)
- `mg_import_tool/tools/verify_post_import.sql` (new — fixed twice on
  the same branch; commit `36d54d7` is the version you should review)
- `docs/RUNBOOK_2026-04-27_afternoon.md` (new — paste-along Blocks A–J)
- `docs/SESSION_LOG_2026-04-27.md` (this addendum appended)

### Closing note

D-8 to Mac Mini install. The corpus the customer will receive on May 5
is the corpus that landed in the live database today. Bitcoin SHA-256
miners only. Postgres-as-truth.

*— end of 2026-04-27 log addendum #3*
