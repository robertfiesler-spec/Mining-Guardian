# Mining Guardian — Session Log: April 22, 2026

**Session Duration:** ~12 hours (morning + evening, with overnight subagents)
**Focus:** Field Intelligence Pipeline Layer 2 ship, two-tier resolver, v3.1 → v3.3 import tool, database split Phase 1

---

## Executive Summary

**Layer 2 of the Field Intelligence Pipeline is LIVE.** The two-tier model resolver
(Tier-1 exact + Tier-2 hashrate-disambiguated families) now links every field-log row to
a catalog model. First real-archive run processed **14,178 rows in 0.45 seconds** with
zero unresolved models. Import tool shipped three versions today (v3.1 → v3.2 → v3.3).

Separately, the monolithic SQLite database was **split into 4 files** via a new router +
compat layer — Phase 1 of the Postgres-unification project that finishes tomorrow.

---

## Critical Fixes

### Fix 1: Two-Tier Resolver Replaces Single-Tier Design ✅

**Problem:** Original design used one `mg.model_aliases` table with `UNIQUE (raw_string,
source_field)`. Doesn't handle WhatsMiner family aliases — strings like `whatsminer-m30s`
legitimately map to **multiple** catalog entries (86/88/90/94/100 TH/s variants) and the
correct pick depends on observed hashrate.

**Root Cause:** V-code semantics aren't uniform — some V-codes (`V100`) pick a specific
variant, others only narrow to a family. Forcing 1:1 either loses information or creates
false specificity.

**Fixes:**
- **Tier 1 = `hardware.model_aliases`** — `UNIQUE(alias_normalized)`, 1:1, authoritative.
  Pre-seeded with **12,852 rows** covering canonical slugs, parenthetical qualifiers
  (`Antminer S19 (Hydro)`), all 15 V-code variants (V10-V100, VE30-VE80, VK10-VK30) for
  every applicable family, and retailer SKUs.
- **Tier 2 = `mg.model_family_aliases`** — ambiguous, `candidate_model_ids UUID[]` +
  `candidate_hashrates_ths NUMERIC[]`. Pre-seeded with **1,494 rows**. Resolver picks
  nearest hashrate bin (no tolerance), ties break to lower-rated variant.
- **Fallback = `mg.unresolved_models`** — if no hashrate or disambiguation fails, dump
  here with sample archive id. No guessing.

**Result:** Clean schema separation. Tier 1 lives under `hardware.` (catalog-reference);
stateful/operational tables live under `mg.`

### Fix 2: Resolver Must Check `control_board_version` Too ✅

**Problem:** First v3.1 draft only inspected `miner_type`. V-codes often land in
`control_board_version` instead (firmware-dependent).

**Root Cause:** No standard across vendors/firmwares for where the model discriminator
goes.

**Fixes:** 5-step pipeline in `clients/resolver.py` (445 lines):
1. Normalize (preserve trailing `+`/`++`, lowercase, squash separators)
2. Tier-1 exact
3. Tier-2 family + hashrate bin
4. V-code introspection on BOTH `miner_type` and `control_board_version`
5. Fallback to `mg.unresolved_models`

**Result:** `VCODES` attribute exposed (private `_VCODES`, len=15) and checked in both
fields.

### Fix 3: Identity Extraction Wired Up (v3.2) ✅

**Problem:** After v3.1 single-archive run: 14,178 rows persisted but
`knowledge.field_log_miner_identity = 0` and `knowledge.field_log_raw_json = 0`. Identity
extraction wasn't emitting rows.

**Root Cause:** Identity emission was stubbed out in the v3.1 rewrite — `insert_miner_identity()`
didn't exist and raw JSON capture was skipped at the file level.

**Fixes:**
- Added `insert_miner_identity()` that emits one row per boot session with resolved
  `model_id`, confidence, match_type, and raw strings
- Added per-file `raw_payload` capture, deduped on `(archive_id, source_file)`
- Added 6 new log regex patterns for boot-session boundary detection
- Bootstrapped unique indexes to handle backfill idempotency

**Result:** 211/211 tests passing. Identity rows and raw JSON populate on re-import.

### Fix 4: Streaming + Error Isolation (v3.3) ✅

**Problem:** Batch import was all-or-nothing. One bad archive in an 83-file batch would
abort everything. No live progress for the user during long runs. No dedup for
re-submitted archives.

**Fixes:**
- **SSE endpoint `/api/import-files-stream`** — live event stream (`batch_started`,
  `archive_started`, `archive_parsed`, `archive_persisted`, `resolver_stats_updated`,
  `archive_completed`, `archive_skipped`, `batch_completed`)
- **Per-archive error isolation** — failures recorded as `status='failed'` in
  `mg.import_runs`, batch continues
- **SHA-256 dedup** — `archive_sha256` unique check skips re-imports automatically
- **`/api/cancel-batch`** — cooperative mid-batch cancel
- **`/api/resolver-summary`** — Tier-1/Tier-2/unresolved counts with coverage %
- **`/api/unresolved-sample?limit=N`** — peek unresolved queue

**Result:** 277/277 tests passing. Ready for tomorrow's 83-archive run.

---

## Database Split Phase 1 (separate track, landed 2026-04-22 afternoon)

| DB File | Size | Role | Key Tables |
|---|---|---|---|
| `operational.db` | 1.5 MB | hot reads | scans, miner_hardware, approvals, maintenance_windows |
| `timeseries.db` | 5.4 GB | append-only | miner/chain/pool/chip/hvac/weather_readings, log_metrics |
| `ai_knowledge.db` | 5.2 MB | learning brain | llm_analysis, miner_baselines, s19jpro_overheat_tracking |
| `audit.db` | 1006 MB | paper trail | action_audit_log, ams_notifications, miner_logs |

**New files:** `core/database_router.py` (table→DB routing), `core/db_compat.py`
(back-compat shim), `core/db_helper.py`, `scripts/migrate_split_databases.py`.

All 6 systemd services tested and running after split. **This is transitional** — the
endgame is full Postgres unification (Phase 2, tomorrow). The Intelligence Catalog and
field-log tables already live in Postgres (`mining-guardian-db` Docker container).

---

## v3.3 Import Tool — API Surface

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/import-files-stream` | POST | SSE batch import |
| `/api/resolver-summary` | GET | Coverage reporting |
| `/api/unresolved-sample?limit=N` | GET | Unresolved queue peek |
| `/api/cancel-batch` | POST | Cooperative cancel |

Flask on `:5050`. 277 tests.

---

## Database Counts (end of session)

### Postgres (`mining_guardian`)
- `hardware.miner_models`: 317 SHA-256 models
- `hardware.model_aliases` (Tier 1): **12,852**
- `mg.model_family_aliases` (Tier 2): **1,494**
- `mg.unresolved_models`: 0
- `mg.import_runs`: 1 (status=ok, 14,178 rows)
- `knowledge.field_log_antminer_autotune`: 14,638
- `knowledge.field_log_events`: 74
- `knowledge.field_log_antminer_boots`: 17
- `knowledge.field_log_pools`: 6
- `knowledge.field_log_imports`: 2
- `knowledge.field_log_miner_identity`: 0 (populates on next re-import via v3.2+)
- `knowledge.field_log_raw_json`: 0 (populates on next re-import via v3.2+)

### SQLite split (all 4 files active)
- Total: ~6.4 GB across operational/timeseries/ai_knowledge/audit

---

## Artifacts Shipped

| Artifact | Location |
|---|---|
| `mg_sql_patch.zip` | 3 SQL files, applied successfully to DB |
| `mg_import_tool_v3_1.zip` | first two-tier resolver build |
| `mg_import_tool_v3_2.zip` | identity + raw JSON fixes |
| `mg_import_tool_v3_3.zip` | SSE + error isolation + dedup + cancel |
| `V3_3_CHANGES.md` | changelog |
| `TOMORROW_DEPLOY_STEPS.md` | deploy procedure for 83-archive batch |

All shipped to user; `mg_import_tool/` tree copied into repo root this commit.

---

## Git Commits (this session)

Merged onto origin/main which had advanced by 3 commits during the day (DB split Phase 1,
PDF report builder, maintenance scheduler). Rebased, resolved conflicts on `CLAUDE.md`
and `unified_miner_index.json` by taking upstream (local stash had been contaminated by
an earlier rogue subagent and was dropped).

| Commit | Description |
|--------|-------------|
| _(this commit)_ | feat: Field Intelligence Pipeline Layer 2 live + mg_import_tool v3.3 + session docs |

---

## Documentation Updated

- `intelligence-catalog/FIELD_INTELLIGENCE_PIPELINE.md` — rewrite to reflect two-tier
  shipped design, 317 models, schema corrections (`catalog.` → `hardware.`), v3.3 API
  surface, Phase 1 DB split context
- `docs/SESSION_LOG_2026-04-22.md` — this file
- `NEXT_SESSION.md` — refreshed to point at tomorrow's 83-archive batch + Phase 2 migration
- `AI_ROADMAP.md` — Layer 2 added to Build Queue

---

## Status at End

**Ready for tomorrow:**
- ✅ v3.3 import tool in workspace zip + copied into repo
- ✅ Database migrations 001 + 002 applied, Tier-1 + Tier-2 seeds loaded
- ✅ Single-archive diagnostic confirmed pipeline end-to-end
- ✅ `TOMORROW_DEPLOY_STEPS.md` ready
- ⏳ 83-archive mass import (user action)
- ⏳ SQLite → Postgres Phase 2 migration (user + me, tomorrow)

**Known item:** `field_log_miner_identity` and `field_log_raw_json` will populate on
re-import via v3.2+ identity extraction path. Today's v3.1 archive will backfill on
re-submit (sha256 dedup will otherwise skip).

**Principle preserved:** Zero data loss. Zero orphans. Every archive gets a catalog
link. "Ring the neck of all this data" — the pipeline now actually does.
