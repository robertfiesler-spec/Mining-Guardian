-- ============================================================================
-- Mining Guardian — Migration 006a — Layer-2 resolver prerequisites (P-023)
-- ============================================================================
-- Created 2026-05-05 to close the v1.0.3 install regression P-023:
-- `MiningGuardian-1.0.3-b66b86440400.pkg` (built from main `b66b864` after
-- P-022) installed cleanly past every prior gate (operator user resolved,
-- Desktop conf read, `.env` exported into postinstall shell, Colima VZ
-- started, postgres image loaded, `mining_guardian` Postgres ready). Then
-- `step_apply_migrations` failed inside `007_layer2_resolver.sql` with:
--
--     ERROR: function uuid_generate_v4() does not exist
--     LINE 2:    id UUID PRIMARY KEY DEFAULT uuid_generate_v4()
--     HINT: No function matches the given name and argument types.
--     [postinstall] FATAL (32) migration 007_layer2_resolver.sql failed
--
-- Root cause: 007 was relocated from `mg_import_tool/sql/migrations/`
-- (P-004, D-20 reconciliation) into the canonical operational migrations
-- chain WITHOUT the prerequisites the importer-side migration depended on.
-- On the importer's catalog DB, those prerequisites are provided by
-- `intelligence-catalog/seed-data/intelligence_catalog_schema.sql`:
--
--   1. `CREATE EXTENSION IF NOT EXISTS "uuid-ossp"` — provides
--      `uuid_generate_v4()` used by every `mg.*` table's PK default.
--   2. `CREATE OR REPLACE FUNCTION public.set_updated_at()` — referenced
--      by 007's section-9 `CREATE TRIGGER ... EXECUTE FUNCTION
--      set_updated_at()` block.
--   3. `hardware.miner_models(id)` — FK target for 007's
--      `mg.unresolved_models.resolved_to_miner_model_id`,
--      `mg.rma_records.miner_model_id`,
--      `mg.dormant_miners.miner_model_id`,
--      `knowledge.field_log_miner_identity.resolved_miner_model_id`.
--   4. `pool.mining_pools(id)` — FK target for
--      `mg.pool_observations.linked_pool_id`.
--
-- The operational DB `mining_guardian` is a SEPARATE database from the
-- catalog DB `mining_guardian_catalog` (the latter is provisioned by
-- `step_provision_catalog_db_and_seed` AFTER `step_apply_migrations`, in a
-- different DB on the same Colima container). The catalog schema bundle
-- only runs against the catalog DB, so none of the four prerequisites
-- above exist in `mining_guardian` when 007 fires.
--
-- Pre-P-023, the importer-side originals at
-- `mg_import_tool/sql/migrations/000_*` and `mg_import_tool/sql/migrations/002_*`
-- ran against the catalog DB where the prereqs already existed. The D-20
-- relocation moved the SQL but not the prereq context; this migration
-- restores that context inside `mining_guardian`.
--
-- WHY 006a (not 008): 007's CREATE TABLE statements reference the prereq
-- objects at apply time (the FK target tables must exist before
-- `REFERENCES hardware.miner_models(id)` is parsed). Lexical apply order in
-- `step_apply_migrations` runs `006a` between 006 and 007, so the prereqs
-- land first. Naming `008_*` would be applied AFTER 007 and not help.
--
-- WHY STUB FK TARGETS LIVE HERE: this is the operational DB, not the
-- catalog DB. The catalog DB has the real `hardware.miner_models` (320
-- seeded rows after `step_provision_catalog_db_and_seed`) and
-- `pool.mining_pools`. The operational DB will never store catalog rows;
-- the FK columns in `mg.*` tables on this side are populated by the
-- application using UUIDs the application itself looks up against the
-- catalog DB and stores back here as opaque pointers. The FK declarations
-- in 007 are a relic of the importer's single-DB layout. We honor them by
-- creating empty target tables here so the FKs compile; the FK constraint
-- itself is harmless because the columns are nullable and the application
-- code never INSERTs a non-NULL value that would need to satisfy the
-- constraint against the empty target.
--
-- IDEMPOTENCY:
--   * `CREATE EXTENSION IF NOT EXISTS` — Postgres-native idempotency.
--   * `CREATE OR REPLACE FUNCTION` — overwrite-in-place idempotency.
--   * `CREATE SCHEMA IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS` — schema
--     idempotency.
--   * Safe to re-apply against a database where 007 has already run
--     (e.g., a Mini that previously had the importer-side 000+002
--     applied via a leaked v1.0.2 .pkg) because every statement is
--     no-op-on-second-apply.
--
-- TARGET DATABASE:
--   `mining_guardian` (the operational DB applied via
--   `installer/macos-pkg/scripts/postinstall.sh::step_apply_migrations`).
--   NOT `mining_guardian_catalog` — the catalog DB has its own canonical
--   `intelligence_catalog_schema.sql` that already provides extensions +
--   `set_updated_at()` + the real seeded tables, and operates on a
--   different `psql -d` target.
--
-- ORDER:
--   006 (field-log bootstrap, creates `knowledge` + `mg` schemas)
--    └─ 006a (this file, adds extensions + function + FK target stubs)
--        └─ 007 (layer-2 resolver, references everything 006 + 006a built)
--
-- This file does NOT modify 006 or 007. Both remain byte-identical to
-- their importer-side originals at `mg_import_tool/sql/migrations/`, so
-- the existing `tests/installer/test_d20_importer_payload_reconciliation.sh`
-- byte-identical assertions (test §8) continue to pass. P-023 is a
-- new-file change only.
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Extensions required by 007
-- ---------------------------------------------------------------------------
-- `uuid-ossp` provides `uuid_generate_v4()`. 001 already creates `pg_trgm`
-- (used by 007's GIN index on alias_normalized); we re-declare it here for
-- defense-in-depth so this migration is self-contained when read in
-- isolation.
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------------------------------------------------------------------------
-- 2. public.set_updated_at() — universal updated_at trigger function
-- ---------------------------------------------------------------------------
-- Mirrors the function defined by `intelligence-catalog/seed-data/
-- intelligence_catalog_schema.sql` so 007's section-9 trigger block resolves
-- against an existing function. `CREATE OR REPLACE` keeps this idempotent
-- across re-applies.
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.set_updated_at() IS
    'Universal updated_at trigger function — mirrors the catalog DB definition.
     Bootstrapped here in the operational DB by migration 006a (P-023) so
     migration 007 layer-2 resolver triggers resolve. See header for context.';

-- ---------------------------------------------------------------------------
-- 3. hardware.miner_models stub — FK target for 007 mg.* tables
-- ---------------------------------------------------------------------------
-- 007's body declares `REFERENCES hardware.miner_models(id)` in three
-- `mg.*` table definitions plus a fourth on `knowledge.field_log_miner_identity.
-- resolved_miner_model_id`. The real `hardware.miner_models` lives in the
-- catalog DB (`mining_guardian_catalog`), seeded with the 320-row Bitcoin
-- SHA-256 baseline by `step_provision_catalog_db_and_seed`. The operational
-- DB only needs the table to exist (any UUID columns the application stores
-- here are opaque pointers into the catalog DB).
--
-- The minimal shape below is a structural subset of the real catalog
-- definition: `id UUID PRIMARY KEY` is the only column 007's FK references
-- look at. Adding more columns here would risk drift between this stub and
-- the real catalog table, which is why we keep it minimal.
CREATE SCHEMA IF NOT EXISTS hardware;
COMMENT ON SCHEMA hardware IS
    'Operational-DB stub schema for 007 layer-2 resolver FK targets (P-023).
     The real catalog hardware.* schema lives in mining_guardian_catalog;
     this side only stores UUID pointers, never authoritative rows.';

CREATE TABLE IF NOT EXISTS hardware.miner_models (
    id UUID PRIMARY KEY
);
COMMENT ON TABLE hardware.miner_models IS
    'Operational-DB stub — FK target for 007 mg.* and knowledge.* columns.
     Authoritative table is in mining_guardian_catalog.hardware.miner_models
     (provisioned by step_provision_catalog_db_and_seed). This stub has the
     id column only; no rows are ever inserted here from the operational
     codepath. Created by migration 006a (P-023).';

-- ---------------------------------------------------------------------------
-- 4. pool.mining_pools stub — FK target for 007 mg.pool_observations
-- ---------------------------------------------------------------------------
-- Same pattern as hardware.miner_models: the operational DB needs the
-- table to exist for 007's `linked_pool_id UUID REFERENCES
-- pool.mining_pools(id)` FK to compile. The real pool.mining_pools lives
-- in the catalog DB.
CREATE SCHEMA IF NOT EXISTS pool;
COMMENT ON SCHEMA pool IS
    'Operational-DB stub schema for 007 layer-2 resolver FK targets (P-023).
     The real catalog pool.* schema lives in mining_guardian_catalog;
     this side only stores UUID pointers, never authoritative rows.';

CREATE TABLE IF NOT EXISTS pool.mining_pools (
    id UUID PRIMARY KEY
);
COMMENT ON TABLE pool.mining_pools IS
    'Operational-DB stub — FK target for 007 mg.pool_observations.linked_pool_id.
     Authoritative table is in mining_guardian_catalog.pool.mining_pools.
     Created by migration 006a (P-023).';

COMMIT;

-- ============================================================================
-- Post-migration sanity check (operator-side):
--
--   docker exec -i mining-guardian-db psql -U mg -d mining_guardian -c "
--     SELECT extname FROM pg_extension WHERE extname IN ('uuid-ossp','pg_trgm');
--     SELECT proname FROM pg_proc WHERE proname='set_updated_at';
--     SELECT to_regclass('hardware.miner_models'), to_regclass('pool.mining_pools');
--   "
--
-- Expected:
--   extname    -> uuid-ossp, pg_trgm (2 rows)
--   proname    -> set_updated_at (1 row)
--   to_regclass -> hardware.miner_models | pool.mining_pools (both non-NULL)
-- ============================================================================
