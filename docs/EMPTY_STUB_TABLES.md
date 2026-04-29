# Empty Stub Tables in guardian.db

> **Status (2026-04-29 sweep):** Historical record. This file documents stub-table decisions made on the **VPS-era `guardian.db` SQLite snapshot**. As of the 2026-04-30 cutover, Mining Guardian runs on the Mac Mini against PostgreSQL `mining_guardian`; SQLite is **not live**. The activation plans below described future SQLite work that will not happen — the equivalent PostgreSQL tables (`chip_readings_partitioned`, `miner_baselines`, `s19jpro_overheat_tracking`) are tracked separately in MG_UNIFIED_TODO_LIST.md. The body below is preserved for historical context.

**Created:** April 13, 2026  
**Purpose (historical):** Document the 3 empty tables in the SQLite snapshot schema and their future activation plans (as understood pre-Mac-Mini cutover).

## Summary

| Table | Rows | Status | Future Plan |
|-------|------|--------|-------------|
| chip_readings | 0 | STUB | Activate when direct-API per-chip data ingestion is built |
| miner_baselines | 0 | STUB | Activate when Tier 3 hashrate baseline learning is needed (unknown miner models) |
| s19jpro_overheat_tracking | 0 | ACTIVE | Created April 13 for Operator Rule #6, will populate when S19J Pro overheats |

## Details

### chip_readings
**Purpose:** Store per-chip hashrate data from direct device APIs (port 4028/4029/8443).  
**Schema:** Created in GuardianDB._init_db(), designed for chip-level failure prediction.  
**Activation Trigger:** When Open Log Uploader (Phase 3) begins ingesting direct-API data OR when chip-level correlation is prioritized in AI roadmap.  
**Until Then:** Table remains empty. No data loss — per-chip data is in log_metrics.chip_hashrate (2.6M rows) as JSON.

### miner_baselines
**Purpose:** Store learned hashrate baselines for miner models NOT in miner_specs.json (Tier 3 fallback).  
**Schema:** Created for the 3-tier hashrate evaluation system (BiXBiT profile parse → specs lookup → baseline learning).  
**Activation Trigger:** When a miner model is encountered that has no BiXBiT profile AND no miner_specs.json entry. Currently all 58 miners resolve via Tier 1 or Tier 2.  
**Until Then:** Table remains empty. Tier 3 code exists but is never reached.

### s19jpro_overheat_tracking
**Purpose:** Track S19J Pro miners that have exceeded 84°C, enforce Operator Rule #6 (one restart attempt, then aging hardware).  
**Schema:** Created April 13, 2026 (commit 7e7c6d8). Fields: miner_id, ip, first_seen, restart_attempted, restart_helped, marked_aging.  
**Activation Trigger:** When any S19J Pro reaches chip_temp ≥ 84°C.  
**Current State:** ACTIVE but not yet triggered. All S19J Pros currently running below 84°C.  
**Phase 1 handler archived 2026-04-29:** The original SQLite-coupled handler `core/s19jpro_overheat_handler.py` was orphan code (zero callers, see `docs/POSTGRES_MIGRATION_STATUS_2026-04-24.md`). It has been moved to `archive/sqlite_phase1/s19jpro_overheat_handler.py` for reference (Bucket 7.3, PR #84). When Operator Rule #6 is wired into the live Postgres-backed code path, use `psycopg2` against this table — do NOT revive the archived SQLite handler. See `archive/sqlite_phase1/README.md` for state-machine semantics.

## Recommendation

**Keep all 3 tables.** They are:
1. Small (empty = 0 bytes)
2. Part of designed architecture (not accidental)
3. Will activate naturally when conditions are met

Do NOT remove them to "clean up the schema." They are not orphans — they are waiting.

---

*See REPAIR_LOG.md entry "2026-04-13 Comprehensive Audit" for context.*
