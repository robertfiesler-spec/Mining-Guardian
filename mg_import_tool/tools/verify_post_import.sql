-- =============================================================================
-- Mining Guardian — Post-import verification snapshot
-- =============================================================================
-- Purpose: Run AFTER the 131-archive bulk re-import. Same shape as
-- verify_pre_import.sql so the outputs diff cleanly. Adds three extra
-- diagnostic blocks at the bottom:
--   (D1) per-archive import outcome rollup from mg.import_runs
--   (D2) unresolved-model surface (resolver hit-rate sanity check)
--   (D3) staging-proposal surface (PR #15 dual-write evidence)
--   (D4) orphan checks: any field_log_* row whose import_id has no row
--        in field_log_imports? (should be zero)
--
-- Usage (from PowerShell):
--   docker exec -e PGPASSWORD=$env:MG_DB_PASSWORD mining-guardian-db `
--     psql -U guardian_admin -d mining_guardian `
--     -f /tmp/verify_post_import.sql `
--     > D:\MiningGuardian\db-backups\pre-migration\post_import_2026-04-27.txt
--
-- Then to diff:
--   Compare-Object (Get-Content baseline_2026-04-27.txt) `
--                  (Get-Content post_import_2026-04-27.txt)
-- =============================================================================

\echo '=== knowledge.field_log_* (importer write targets — should all GROW) ==='
SELECT 'knowledge.field_log_imports'                AS table_name, COUNT(*) AS rows FROM knowledge.field_log_imports
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
\echo '=== mg.* (resolver/state tables — import_runs MUST grow by ~131) ==='
SELECT 'mg.import_runs'                AS table_name, COUNT(*) AS rows FROM mg.import_runs
UNION ALL SELECT 'mg.unresolved_models',    COUNT(*) FROM mg.unresolved_models
UNION ALL SELECT 'mg.dormant_miners',       COUNT(*) FROM mg.dormant_miners
UNION ALL SELECT 'mg.model_family_aliases', COUNT(*) FROM mg.model_family_aliases
UNION ALL SELECT 'mg.rma_records',          COUNT(*) FROM mg.rma_records
UNION ALL SELECT 'mg.unknown_fields',       COUNT(*) FROM mg.unknown_fields
ORDER BY table_name;

\echo ''
\echo '=== Catalog tables read by catalog-api (must MATCH baseline exactly) ==='
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
\echo '=== D1: import_runs per-archive outcome rollup ==='
SELECT
    status,
    COUNT(*) AS runs,
    SUM(rows_inserted) AS total_rows_inserted,
    SUM(rows_skipped)  AS total_rows_skipped,
    MIN(started_at)    AS first_run,
    MAX(finished_at)   AS last_run
FROM mg.import_runs
GROUP BY status
ORDER BY status;

\echo ''
\echo '=== D2: resolver hit-rate (lower = more unresolved models = manual review) ==='
SELECT
    COUNT(*)                                          AS total_unresolved,
    COUNT(DISTINCT raw_model_text)                    AS distinct_unresolved_strings,
    COUNT(*) FILTER (WHERE proposed_canonical IS NOT NULL) AS auto_proposals
FROM mg.unresolved_models;

-- Top 20 unresolved model strings by occurrence (the manual review queue)
SELECT raw_model_text, COUNT(*) AS occurrences
FROM mg.unresolved_models
GROUP BY raw_model_text
ORDER BY occurrences DESC
LIMIT 20;

\echo ''
\echo '=== D3: staging.* (PR #15 dual-write proposals) ==='
-- Conditional execution: psql does not support "IF EXISTS then SELECT"
-- inline, so we use \gexec to dynamically generate and run the right
-- SELECT only if the schema is present. If staging is missing, this
-- block prints a NOTICE and skips the counts.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name='staging') THEN
        RAISE NOTICE 'staging schema present — counts follow';
    ELSE
        RAISE NOTICE 'staging schema does not exist — PR #15 migration was skipped';
    END IF;
END $$;

-- Real table names in staging (per PR #15): miner_model_proposals (singular),
-- manufacturer_proposals, alias_proposals. The earlier draft used plural
-- names that don't exist in the live schema.
SELECT format(
    'SELECT ''staging.miner_model_proposals''  AS table_name, COUNT(*) AS rows '
    'FROM staging.miner_model_proposals '
    'UNION ALL '
    'SELECT ''staging.manufacturer_proposals'', COUNT(*) FROM staging.manufacturer_proposals '
    'UNION ALL '
    'SELECT ''staging.alias_proposals'',        COUNT(*) FROM staging.alias_proposals'
)
WHERE EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'staging'
      AND table_name IN ('miner_model_proposals', 'manufacturer_proposals', 'alias_proposals')
) \gexec

\echo ''
\echo '=== D4: orphan check — field_log rows pointing at missing import_id ==='
-- Any non-zero result here means the importer wrote child rows whose parent
-- field_log_imports row was rolled back. Should ALWAYS be zero on a clean run.
SELECT 'field_log_antminer_autotune' AS child_table,
       COUNT(*) AS orphan_rows
FROM knowledge.field_log_antminer_autotune c
WHERE NOT EXISTS (
    SELECT 1 FROM knowledge.field_log_imports p WHERE p.id = c.import_id
)
UNION ALL
SELECT 'field_log_antminer_boots',
       COUNT(*)
FROM knowledge.field_log_antminer_boots c
WHERE NOT EXISTS (SELECT 1 FROM knowledge.field_log_imports p WHERE p.id = c.import_id)
UNION ALL
SELECT 'field_log_events',
       COUNT(*)
FROM knowledge.field_log_events c
WHERE NOT EXISTS (SELECT 1 FROM knowledge.field_log_imports p WHERE p.id = c.import_id)
UNION ALL
SELECT 'field_log_pools',
       COUNT(*)
FROM knowledge.field_log_pools c
WHERE NOT EXISTS (SELECT 1 FROM knowledge.field_log_imports p WHERE p.id = c.import_id)
UNION ALL
SELECT 'field_log_power_samples',
       COUNT(*)
FROM knowledge.field_log_power_samples c
WHERE NOT EXISTS (SELECT 1 FROM knowledge.field_log_imports p WHERE p.id = c.import_id)
UNION ALL
SELECT 'field_log_temp_snapshots',
       COUNT(*)
FROM knowledge.field_log_temp_snapshots c
WHERE NOT EXISTS (SELECT 1 FROM knowledge.field_log_imports p WHERE p.id = c.import_id)
UNION ALL
SELECT 'field_log_api_stats',
       COUNT(*)
FROM knowledge.field_log_api_stats c
WHERE NOT EXISTS (SELECT 1 FROM knowledge.field_log_imports p WHERE p.id = c.import_id)
UNION ALL
SELECT 'field_log_miner_identity',
       COUNT(*)
FROM knowledge.field_log_miner_identity c
WHERE NOT EXISTS (SELECT 1 FROM knowledge.field_log_imports p WHERE p.id = c.import_id)
ORDER BY child_table;
