-- =============================================================================
-- Mining Guardian — Post-import verification snapshot
-- =============================================================================
-- Purpose: Run AFTER the 136-archive bulk re-import. Same shape as
-- verify_pre_import.sql so the outputs diff cleanly. Adds four extra
-- diagnostic blocks at the bottom:
--   (D1) per-run rollup from mg.import_runs (status + archive_count)
--   (D2) unresolved-model surface (resolver hit-rate sanity check)
--   (D3) staging-proposal surface (PR #15 dual-write evidence)
--   (D4) orphan checks: any field_log_* child whose archive_filename has no
--        matching row in field_log_imports? (should always be zero — child
--        tables link to imports via archive_filename, NOT import_id)
--
-- Usage (from PowerShell):
--   docker cp tools\verify_post_import.sql `
--       mining-guardian-db:/tmp/verify_post_import.sql
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
\echo '=== mg.* (resolver/state tables — import_runs MUST grow by exactly 1) ==='
SELECT 'mg.import_runs'                AS table_name, COUNT(*) AS rows FROM mg.import_runs
UNION ALL SELECT 'mg.unresolved_models',    COUNT(*) FROM mg.unresolved_models
UNION ALL SELECT 'mg.dormant_miners',       COUNT(*) FROM mg.dormant_miners
UNION ALL SELECT 'mg.model_family_aliases', COUNT(*) FROM mg.model_family_aliases
UNION ALL SELECT 'mg.rma_records',          COUNT(*) FROM mg.rma_records
UNION ALL SELECT 'knowledge.unknown_fields', COUNT(*) FROM knowledge.unknown_fields
ORDER BY table_name;

\echo ''
\echo '=== Catalog tables read by catalog-api (must MATCH baseline exactly) ==='
SELECT 'hardware.miner_models'              AS table_name, COUNT(*) AS rows FROM hardware.miner_models
UNION ALL SELECT 'hardware.model_aliases',           COUNT(*) FROM hardware.model_aliases
UNION ALL SELECT 'hardware.manufacturers',           COUNT(*) FROM hardware.manufacturers
UNION ALL SELECT 'hardware.model_known_issues',      COUNT(*) FROM hardware.model_known_issues
UNION ALL SELECT 'ops.failure_patterns',             COUNT(*) FROM ops.failure_patterns
UNION ALL SELECT 'firmware.firmware_releases',       COUNT(*) FROM firmware.firmware_releases
UNION ALL SELECT 'repair.parts',                     COUNT(*) FROM repair.parts
UNION ALL SELECT 'facility.cooling_solutions',       COUNT(*) FROM facility.cooling_solutions
ORDER BY table_name;

\echo ''
\echo '=== D1: mg.import_runs rollup (one row per script invocation) ==='
-- Schema: id, started_at, finished_at, archive_count, row_counts JSONB,
--         errors TEXT[], status. There is NO rows_inserted or rows_skipped
--         column — those values live inside row_counts JSONB.
SELECT
    id,
    started_at,
    finished_at,
    archive_count,
    status,
    array_length(errors, 1) AS error_count,
    row_counts->>'total_rows'  AS total_rows,
    row_counts->>'statements'  AS statements,
    row_counts->>'errors'      AS errors_in_counts
FROM mg.import_runs
ORDER BY id DESC
LIMIT 5;

\echo ''
\echo '=== D2: resolver hit-rate (lower = more unresolved models = manual review) ==='
-- mg.unresolved_models has NO raw_model_text column — the real identity
-- strings are split across raw_miner_type + raw_control_board_version (per
-- migration 002_layer2). We treat the (miner_type, control_board) tuple as
-- the logical "unresolved string" for distinct/group-by purposes.
SELECT
    COUNT(*)                                                                AS total_unresolved,
    COUNT(DISTINCT (raw_miner_type, raw_control_board_version))             AS distinct_unresolved_strings
FROM mg.unresolved_models;

-- Top 20 unresolved model tuples by occurrence (the manual review queue)
SELECT
    raw_miner_type,
    raw_control_board_version,
    COUNT(*) AS occurrences
FROM mg.unresolved_models
GROUP BY raw_miner_type, raw_control_board_version
ORDER BY occurrences DESC
LIMIT 20;

\echo ''
\echo '=== D3: staging.* (PR #15 dual-write proposals) ==='
-- Real table names in staging (per PR #15): miner_model_proposals (singular),
-- manufacturer_proposals, alias_proposals.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name='staging') THEN
        RAISE NOTICE 'staging schema does not exist — PR #15 migration was skipped';
    END IF;
END $$;

SELECT 'staging.miner_model_proposals' AS table_name, COUNT(*) AS rows FROM staging.miner_model_proposals
UNION ALL SELECT 'staging.manufacturer_proposals', COUNT(*) FROM staging.manufacturer_proposals
UNION ALL SELECT 'staging.alias_proposals',        COUNT(*) FROM staging.alias_proposals
ORDER BY table_name;

\echo ''
\echo '=== D4: orphan check — child rows whose archive_filename has no parent ==='
-- Children link to knowledge.field_log_imports via archive_filename (TEXT),
-- NOT via a numeric import_id foreign key. Any non-zero result here means
-- the importer wrote child rows whose parent imports row was rolled back
-- or never inserted. Should ALWAYS be zero on a clean run.
SELECT 'field_log_antminer_autotune' AS child_table,
       COUNT(*) AS orphan_rows
FROM knowledge.field_log_antminer_autotune c
WHERE NOT EXISTS (
    SELECT 1 FROM knowledge.field_log_imports p
    WHERE p.entity_label = c.archive_filename
       OR p.entity_label = regexp_replace(c.archive_filename, '\.(tar\.gz|tgz|tar|rar)$', '')
)
UNION ALL
SELECT 'field_log_antminer_boots',
       COUNT(*)
FROM knowledge.field_log_antminer_boots c
WHERE NOT EXISTS (
    SELECT 1 FROM knowledge.field_log_imports p
    WHERE p.entity_label = c.archive_filename
       OR p.entity_label = regexp_replace(c.archive_filename, '\.(tar\.gz|tgz|tar|rar)$', '')
)
UNION ALL
SELECT 'field_log_events',
       COUNT(*)
FROM knowledge.field_log_events c
WHERE NOT EXISTS (
    SELECT 1 FROM knowledge.field_log_imports p
    WHERE p.entity_label = c.archive_filename
       OR p.entity_label = regexp_replace(c.archive_filename, '\.(tar\.gz|tgz|tar|rar)$', '')
)
UNION ALL
SELECT 'field_log_pools',
       COUNT(*)
FROM knowledge.field_log_pools c
WHERE NOT EXISTS (
    SELECT 1 FROM knowledge.field_log_imports p
    WHERE p.entity_label = c.archive_filename
       OR p.entity_label = regexp_replace(c.archive_filename, '\.(tar\.gz|tgz|tar|rar)$', '')
)
UNION ALL
SELECT 'field_log_power_samples',
       COUNT(*)
FROM knowledge.field_log_power_samples c
WHERE NOT EXISTS (
    SELECT 1 FROM knowledge.field_log_imports p
    WHERE p.entity_label = c.archive_filename
       OR p.entity_label = regexp_replace(c.archive_filename, '\.(tar\.gz|tgz|tar|rar)$', '')
)
UNION ALL
SELECT 'field_log_temp_snapshots',
       COUNT(*)
FROM knowledge.field_log_temp_snapshots c
WHERE NOT EXISTS (
    SELECT 1 FROM knowledge.field_log_imports p
    WHERE p.entity_label = c.archive_filename
       OR p.entity_label = regexp_replace(c.archive_filename, '\.(tar\.gz|tgz|tar|rar)$', '')
)
UNION ALL
SELECT 'field_log_api_stats',
       COUNT(*)
FROM knowledge.field_log_api_stats c
WHERE NOT EXISTS (
    SELECT 1 FROM knowledge.field_log_imports p
    WHERE p.entity_label = c.archive_filename
       OR p.entity_label = regexp_replace(c.archive_filename, '\.(tar\.gz|tgz|tar|rar)$', '')
)
UNION ALL
SELECT 'field_log_miner_identity',
       COUNT(*)
FROM knowledge.field_log_miner_identity c
WHERE NOT EXISTS (
    SELECT 1 FROM knowledge.field_log_imports p
    WHERE p.entity_label = c.archive_filename
       OR p.entity_label = regexp_replace(c.archive_filename, '\.(tar\.gz|tgz|tar|rar)$', '')
)
ORDER BY child_table;

\echo ''
\echo '=== D5: top-10 archives by power_samples (most data-rich) ==='
SELECT archive_filename, COUNT(*) AS power_samples
FROM knowledge.field_log_power_samples
GROUP BY archive_filename
ORDER BY power_samples DESC
LIMIT 10;
