-- =============================================================================
-- Mining Guardian — Pre-import baseline snapshot
-- =============================================================================
-- Purpose: Capture row counts on every table the importer will touch BEFORE
-- the bulk re-import runs, so we can compare against the post-import counts
-- and confirm: (a) row counts increased where expected, (b) no unrelated
-- tables changed, (c) no orphans were created.
--
-- Usage (from PowerShell):
--   docker exec -e PGPASSWORD=$env:MG_DB_PASSWORD mining-guardian-db `
--     psql -U guardian_admin -d mining_guardian `
--     -f /tmp/verify_pre_import.sql `
--     > D:\MiningGuardian\db-backups\pre-migration\baseline_2026-04-27.txt
-- =============================================================================

\echo '=== knowledge.field_log_* (importer write targets) ==='
SELECT 'knowledge.field_log_imports'           AS table_name, COUNT(*) AS rows FROM knowledge.field_log_imports
UNION ALL SELECT 'knowledge.field_log_miner_identity',           COUNT(*) FROM knowledge.field_log_miner_identity
UNION ALL SELECT 'knowledge.field_log_antminer_autotune',        COUNT(*) FROM knowledge.field_log_antminer_autotune
UNION ALL SELECT 'knowledge.field_log_antminer_boots',           COUNT(*) FROM knowledge.field_log_antminer_boots
UNION ALL SELECT 'knowledge.field_log_events',                   COUNT(*) FROM knowledge.field_log_events
UNION ALL SELECT 'knowledge.field_log_pools',                    COUNT(*) FROM knowledge.field_log_pools
UNION ALL SELECT 'knowledge.field_log_power_samples',            COUNT(*) FROM knowledge.field_log_power_samples
UNION ALL SELECT 'knowledge.field_log_temp_snapshots',           COUNT(*) FROM knowledge.field_log_temp_snapshots
UNION ALL SELECT 'knowledge.field_log_api_stats',                COUNT(*) FROM knowledge.field_log_api_stats
UNION ALL SELECT 'knowledge.field_log_raw_json',                 COUNT(*) FROM knowledge.field_log_raw_json
ORDER BY table_name;

\echo ''
\echo '=== mg.* (resolver/state tables) ==='
SELECT 'mg.import_runs'                AS table_name, COUNT(*) AS rows FROM mg.import_runs
UNION ALL SELECT 'mg.unresolved_models',    COUNT(*) FROM mg.unresolved_models
UNION ALL SELECT 'mg.dormant_miners',       COUNT(*) FROM mg.dormant_miners
UNION ALL SELECT 'mg.model_family_aliases', COUNT(*) FROM mg.model_family_aliases
UNION ALL SELECT 'mg.rma_records',          COUNT(*) FROM mg.rma_records
UNION ALL SELECT 'mg.unknown_fields',       COUNT(*) FROM mg.unknown_fields
ORDER BY table_name;

\echo ''
\echo '=== Catalog tables read by catalog-api (must NOT change during import) ==='
SELECT 'hardware.miner_models'              AS table_name, COUNT(*) AS rows FROM hardware.miner_models
UNION ALL SELECT 'hardware.model_aliases',           COUNT(*) FROM hardware.model_aliases
UNION ALL SELECT 'hardware.manufacturers',           COUNT(*) FROM hardware.manufacturers
UNION ALL SELECT 'hardware.chips',                   COUNT(*) FROM hardware.chips
UNION ALL SELECT 'hardware.psu_models',              COUNT(*) FROM hardware.psu_models
UNION ALL SELECT 'hardware.model_known_issues',      COUNT(*) FROM hardware.model_known_issues
UNION ALL SELECT 'ops.failure_patterns',             COUNT(*) FROM ops.failure_patterns
UNION ALL SELECT 'ops.failure_symptoms',             COUNT(*) FROM ops.failure_symptoms
UNION ALL SELECT 'ops.miner_error_codes',            COUNT(*) FROM ops.miner_error_codes
UNION ALL SELECT 'firmware.firmware_releases',       COUNT(*) FROM firmware.firmware_releases
UNION ALL SELECT 'firmware.firmware_bugs',           COUNT(*) FROM firmware.firmware_bugs
UNION ALL SELECT 'repair.parts',                     COUNT(*) FROM repair.parts
UNION ALL SELECT 'repair.diagnostic_tools',          COUNT(*) FROM repair.diagnostic_tools
UNION ALL SELECT 'facility.cooling_solutions',       COUNT(*) FROM facility.cooling_solutions
ORDER BY table_name;

\echo ''
\echo '=== staging.* (created by migration; should be 0 rows after migration, before import) ==='
-- These will only succeed AFTER staging_schema.sql is applied
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'staging') THEN
        RAISE NOTICE 'staging schema exists';
    ELSE
        RAISE NOTICE 'staging schema does NOT exist yet (migration pending)';
    END IF;
END $$;
