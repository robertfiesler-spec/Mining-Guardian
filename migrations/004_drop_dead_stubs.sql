-- migrations/004_drop_dead_stubs.sql
-- Bucket 7.2 — Drop empty stub tables that were never wired to writers.
--
-- Audit findings H1 (chip_readings) and H3 (log_collection_failures):
-- both tables show 0 reads and 0 writes across the entire repo's
-- production code (verified by grep on 2026-04-29). They were created
-- in `001_initial_schema.sql` against a planned-but-never-shipped
-- per-chip extraction path and a planned-but-never-shipped log
-- collection failure tracker. The audit recommendation is "drop".
--
-- See:
--   docs/MG_UNIFIED_TODO_LIST.md §8.1 — "Confirmed dead"
--   docs/EMPTY_STUB_TABLES.md
--   docs/RUNBOOK_BUCKET_7.2_DROP_DEAD_STUBS.md (this PR)
--
-- Why a separate migration instead of editing `001_initial_schema.sql`?
-- ---------------------------------------------------------------------
-- 001 has already been applied to every existing deployment (the VPS,
-- developer sandboxes, intelligence-catalog Postgres). Re-running 001
-- is idempotent for CREATEs, but a DROP requires its own forward
-- migration so existing nodes converge to the new desired state. The
-- 001 source file is also patched in the same PR so fresh installs
-- never create the stubs in the first place.
--
-- Idempotency
-- -----------
-- Uses DROP INDEX IF EXISTS / DROP TABLE IF EXISTS throughout. Re-
-- running this migration on a node where the tables have already
-- been dropped is a clean no-op (only NOTICE messages, no errors).
--
-- Safety review
-- -------------
-- 1. No FK dependents. Both tables only reference scans(id) outbound;
--    nothing references them inbound. Verified by:
--      SELECT conname, conrelid::regclass FROM pg_constraint
--       WHERE contype = 'f'
--         AND confrelid IN ('chip_readings'::regclass,
--                           'log_collection_failures'::regclass);
--    Returns 0 rows on the VPS Postgres (2026-04-29).
-- 2. No views or materialized views read from them. Verified by
--    grepping pg_views and pg_matviews for the table names.
-- 3. Both tables empty in production:
--      VPS Postgres on 2026-04-29:
--        chip_readings           = 0 rows
--        log_collection_failures = 0 rows
-- 4. SQLite-era code in `core/database.py` still has CREATE TABLE
--    statements for these — left in place for now per the
--    "NEVER refer to SQLite as live" constraint. SQLite is being
--    retired separately and that block will go with it.

BEGIN;

-- chip_readings (audit finding H1) ------------------------------------
-- Was meant to hold per-chip frequency/voltage/temperature samples
-- pulled from miner direct APIs. Per-chip extraction never shipped;
-- the actually-populated path is `log_metrics` (raw mining log lines).

DROP INDEX IF EXISTS idx_chip_miner;
DROP TABLE IF EXISTS chip_readings;

-- log_collection_failures (audit finding H3) --------------------------
-- Was meant to track which miners we couldn't pull mining logs from.
-- Never wired; failures are surfaced through `discovery_log` and the
-- Slack notifier path instead.

DROP INDEX IF EXISTS idx_log_failures_miner;
DROP INDEX IF EXISTS idx_log_failures_date;
DROP TABLE IF EXISTS log_collection_failures;

COMMIT;

-- Verify (run interactively after migration):
--   \dt chip_readings           -- expect: Did not find any relation
--   \dt log_collection_failures -- expect: Did not find any relation
--   SELECT COUNT(*) FROM information_schema.tables
--    WHERE table_name IN ('chip_readings', 'log_collection_failures');
--   -- expect: 0
