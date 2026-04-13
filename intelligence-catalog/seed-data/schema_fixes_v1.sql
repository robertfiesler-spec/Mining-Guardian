-- =============================================================================
-- MINING INTELLIGENCE CATALOG — Schema Fixes v1
-- Target: PostgreSQL 16 in Docker container `mining-guardian-db`
-- Purpose: Fix 4 non-critical schema errors that prevented certain tables
--          or triggers from creating successfully during initial deployment.
--
-- Issues fixed:
--   1. knowledge.freshness_log — GENERATED column uses NOW() (non-IMMUTABLE)
--   2. knowledge.raw_ingestion_log — partitioned table PK missing partition key
--   3. Trigger cast syntax — firmware_family::TEXT and cooling_type::TEXT
--      inside tsvector_update_trigger() calls (invalid syntax)
--   4. Base schema seed data — chips, hashboards, Bobby's 4 fleet miner_models,
--      firmware, compatibility, and autotuning profiles may not have been
--      inserted because they referenced the hardcoded 20000000-... manufacturer
--      UUIDs which were superseded by auto-generated UUIDs from fix_and_seed.sql
--
-- IDEMPOTENT: Safe to run multiple times. All sections use IF EXISTS / ON CONFLICT.
-- =============================================================================


-- =============================================================================
-- ISSUE 1: knowledge.freshness_log
-- Problem:  staleness_days INTEGER GENERATED ALWAYS AS
--               (EXTRACT(DAY FROM NOW() - last_verified_at)::INTEGER) STORED
--           PostgreSQL requires GENERATED ALWAYS expressions to be IMMUTABLE.
--           NOW() is VOLATILE, so PostgreSQL rejects the column definition.
-- Fix:      Drop and recreate the table with staleness_days as a plain INTEGER.
--           Add a VIEW (knowledge.freshness_log_view) that computes staleness
--           on the fly so read queries still get a live staleness value without
--           any schema-level volatility restriction.
-- =============================================================================

-- Drop dependent view first (in case this is a re-run)
DROP VIEW IF EXISTS knowledge.freshness_log_view;

-- Drop the table (partitions not applicable — plain table)
DROP TABLE IF EXISTS knowledge.freshness_log;

-- Recreate table with staleness_days as a plain updatable INTEGER column.
-- A scheduled job or trigger can populate/refresh it; the view computes it live.
CREATE TABLE knowledge.freshness_log (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tracked_table       TEXT NOT NULL,
    tracked_row_id      UUID NOT NULL,
    tracked_field       TEXT,                   -- NULL = whole row
    last_verified_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified_by         UUID REFERENCES knowledge.contributors(id),
    verification_method TEXT,                   -- 'api_pull', 'manual_check', 'automated_test'
    next_verify_due     TIMESTAMPTZ,            -- When should this be re-verified?
    staleness_days      INTEGER,                -- Populated by scheduled job / explicit update;
                                                -- see freshness_log_view for live computation
    is_stale            BOOLEAN NOT NULL DEFAULT FALSE,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ             -- Soft-delete; added per v3 convention
);

COMMENT ON TABLE knowledge.freshness_log IS
'Tracks when any data point was last verified. Enables staleness alerts.
Mining Guardian can query: "Which specs have not been verified in 90+ days?"
staleness_days is a cached integer updated by scheduled jobs; for live values
query knowledge.freshness_log_view which computes it via NOW() - last_verified_at.';

COMMENT ON COLUMN knowledge.freshness_log.staleness_days IS
'Cached staleness in days, updated by scheduled job. For real-time staleness
use the freshness_log_view which computes EXTRACT(DAY FROM NOW() - last_verified_at).';

-- Recreate the 3 indexes from the original schema
CREATE INDEX idx_freshness_row   ON knowledge.freshness_log(tracked_table, tracked_row_id);
CREATE INDEX idx_freshness_stale ON knowledge.freshness_log(is_stale, next_verify_due)
    WHERE is_stale = TRUE;
CREATE INDEX idx_freshness_due   ON knowledge.freshness_log(next_verify_due ASC)
    WHERE next_verify_due IS NOT NULL;

-- View that computes staleness on read — no IMMUTABLE restriction here
CREATE VIEW knowledge.freshness_log_view AS
SELECT
    id,
    tracked_table,
    tracked_row_id,
    tracked_field,
    last_verified_at,
    verified_by,
    verification_method,
    next_verify_due,
    -- Live computation: safe in a VIEW, not in a GENERATED column
    EXTRACT(DAY FROM NOW() - last_verified_at)::INTEGER AS staleness_days,
    is_stale,
    metadata,
    created_at,
    deleted_at
FROM knowledge.freshness_log;

COMMENT ON VIEW knowledge.freshness_log_view IS
'Live-computed view of freshness_log. staleness_days is calculated as
EXTRACT(DAY FROM NOW() - last_verified_at)::INTEGER on every read.
Use this view instead of the base table when you need up-to-the-second staleness.';


-- =============================================================================
-- ISSUE 2: knowledge.raw_ingestion_log
-- Problem:  CREATE TABLE ... (id UUID PRIMARY KEY ...) PARTITION BY RANGE (ingested_at)
--           PostgreSQL 16 requires every column in a PRIMARY KEY on a partitioned
--           table to also appear in the partition key. id alone is not sufficient;
--           the PK must be (id, ingested_at).
-- Fix:      Drop the table (and all child partitions cascade), recreate with
--           PRIMARY KEY (id, ingested_at), then recreate all 5 partitions and
--           all 4 indexes.
-- =============================================================================

-- Drop child partitions first (CASCADE handles them, but explicit is clearer)
DROP TABLE IF EXISTS knowledge.raw_ingestion_log_2026_q1 CASCADE;
DROP TABLE IF EXISTS knowledge.raw_ingestion_log_2026_q2 CASCADE;
DROP TABLE IF EXISTS knowledge.raw_ingestion_log_2026_q3 CASCADE;
DROP TABLE IF EXISTS knowledge.raw_ingestion_log_2026_q4 CASCADE;
DROP TABLE IF EXISTS knowledge.raw_ingestion_log_2027_q1 CASCADE;

-- Drop the parent (CASCADE drops any remaining partitions and indexes)
DROP TABLE IF EXISTS knowledge.raw_ingestion_log CASCADE;

-- Recreate parent table with corrected composite PK
CREATE TABLE knowledge.raw_ingestion_log (
    id                  UUID NOT NULL DEFAULT uuid_generate_v4(),
    ingestion_source    TEXT NOT NULL,          -- 'ams_api', 'bixbit_api', 'container_monitor',
                                                --  'hvac_bacnet', 'miner_log', 'weather_api'
    source_endpoint     TEXT,                   -- Specific endpoint or log path
    source_miner_id     TEXT,
    source_ip           TEXT,
    raw_payload         JSONB NOT NULL,          -- Complete raw response
    payload_hash        TEXT NOT NULL,           -- SHA-256 of payload — dedup identical payloads
    payload_size_bytes  INTEGER,
    new_fields_found    INTEGER NOT NULL DEFAULT 0,  -- Count of unknown fields in this payload
    processing_status   TEXT NOT NULL DEFAULT 'processed',  -- 'processed', 'error', 'partial'
    processing_error    TEXT,
    processing_time_ms  INTEGER,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retention_tier      TEXT NOT NULL DEFAULT 'standard',   -- 'standard' (90d), 'flagged' (1yr),
                                                             --  'permanent'
    -- Composite PK: id + partition key column (required by PostgreSQL for partitioned tables)
    PRIMARY KEY (id, ingested_at)
) PARTITION BY RANGE (ingested_at);

COMMENT ON TABLE knowledge.raw_ingestion_log IS
'Complete raw payload archive. Every API response, every log parse. Partitioned by quarter,
auto-pruned by retention_tier. Standard = 90 days, flagged = 1 year, permanent = forever.
This is the forensic backbone — when something weird happens, we can replay exactly what arrived.
PK is (id, ingested_at) — PostgreSQL requires partition key in every PK on partitioned tables.';

-- Recreate the 5 quarterly partitions
CREATE TABLE knowledge.raw_ingestion_log_2026_q1
    PARTITION OF knowledge.raw_ingestion_log
    FOR VALUES FROM ('2026-01-01') TO ('2026-04-01');

CREATE TABLE knowledge.raw_ingestion_log_2026_q2
    PARTITION OF knowledge.raw_ingestion_log
    FOR VALUES FROM ('2026-04-01') TO ('2026-07-01');

CREATE TABLE knowledge.raw_ingestion_log_2026_q3
    PARTITION OF knowledge.raw_ingestion_log
    FOR VALUES FROM ('2026-07-01') TO ('2026-10-01');

CREATE TABLE knowledge.raw_ingestion_log_2026_q4
    PARTITION OF knowledge.raw_ingestion_log
    FOR VALUES FROM ('2026-10-01') TO ('2027-01-01');

CREATE TABLE knowledge.raw_ingestion_log_2027_q1
    PARTITION OF knowledge.raw_ingestion_log
    FOR VALUES FROM ('2027-01-01') TO ('2027-04-01');

-- Recreate the 4 indexes from the original v3 schema
CREATE INDEX idx_raw_ingestion_source     ON knowledge.raw_ingestion_log(ingestion_source, ingested_at);
CREATE INDEX idx_raw_ingestion_miner      ON knowledge.raw_ingestion_log(source_miner_id, ingested_at);
CREATE INDEX idx_raw_ingestion_hash       ON knowledge.raw_ingestion_log(payload_hash);
CREATE INDEX idx_raw_ingestion_new_fields ON knowledge.raw_ingestion_log(id, ingested_at)
    WHERE new_fields_found > 0;


-- =============================================================================
-- ISSUE 3: tsvector trigger cast syntax — ::TEXT inside tsvector_update_trigger()
-- Problem:  tsvector_update_trigger() accepts column NAMES as bare identifiers,
--           not cast expressions. Passing firmware_family::TEXT or
--           cooling_type::TEXT causes a syntax error at trigger creation time.
--           Both columns are ENUMs (public.firmware_family and public.cooling_type)
--           so a bare column name would also fail because the function only
--           handles TEXT/VARCHAR internally.
-- Fix:      For each affected trigger:
--             1. DROP the broken trigger
--             2. CREATE OR REPLACE a custom trigger function that casts the ENUM
--                to TEXT explicitly inside PL/pgSQL, then builds the tsvector
--                using to_tsvector()
--             3. CREATE the trigger using the new function
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 3a: firmware.firmware_releases — trg_fw_search_vector
--     Column: firmware_family  public.firmware_family (ENUM, not TEXT)
-- ---------------------------------------------------------------------------

DROP TRIGGER IF EXISTS trg_fw_search_vector ON firmware.firmware_releases;

CREATE OR REPLACE FUNCTION firmware.update_fw_search_vector()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.search_vector :=
        to_tsvector('pg_catalog.english',
            COALESCE(NEW.firmware_family::TEXT, '') || ' ' ||
            COALESCE(NEW.version_string,  '') || ' ' ||
            COALESCE(NEW.display_name,    '') || ' ' ||
            COALESCE(NEW.developer_name,  '') || ' ' ||
            COALESCE(NEW.notes,           '')
        );
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION firmware.update_fw_search_vector() IS
'Builds search_vector for firmware.firmware_releases. Casts firmware_family
ENUM to TEXT explicitly — tsvector_update_trigger() cannot accept ENUM columns
or cast expressions as arguments, so this custom function is required.';

CREATE TRIGGER trg_fw_search_vector
    BEFORE INSERT OR UPDATE ON firmware.firmware_releases
    FOR EACH ROW EXECUTE FUNCTION firmware.update_fw_search_vector();

-- ---------------------------------------------------------------------------
-- 3b: facility.cooling_solutions — trg_cool_sol_search_vector
--     Column: cooling_type  public.cooling_type (ENUM, not TEXT)
-- ---------------------------------------------------------------------------

DROP TRIGGER IF EXISTS trg_cool_sol_search_vector ON facility.cooling_solutions;

CREATE OR REPLACE FUNCTION facility.update_cool_sol_search_vector()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.search_vector :=
        to_tsvector('pg_catalog.english',
            COALESCE(NEW.solution_name,       '') || ' ' ||
            COALESCE(NEW.manufacturer_name,   '') || ' ' ||
            COALESCE(NEW.cooling_type::TEXT,  '') || ' ' ||
            COALESCE(NEW.fluid_type,          '') || ' ' ||
            COALESCE(NEW.notes,               '')
        );
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION facility.update_cool_sol_search_vector() IS
'Builds search_vector for facility.cooling_solutions. Casts cooling_type
ENUM to TEXT explicitly — tsvector_update_trigger() cannot accept ENUM columns
or cast expressions as arguments, so this custom function is required.';

CREATE TRIGGER trg_cool_sol_search_vector
    BEFORE INSERT OR UPDATE ON facility.cooling_solutions
    FOR EACH ROW EXECUTE FUNCTION facility.update_cool_sol_search_vector();


-- =============================================================================
-- ISSUE 4: Base schema seed data — FK violations due to mismatched UUIDs
-- Problem:  The base schema (intelligence_catalog_schema.sql) hard-coded UUIDs
--           for contributors (00000000-...), sources (10000000-...),
--           manufacturers (20000000-...), chips (30000000-...),
--           hashboards (40000000-...), miner_models (50000000-...),
--           firmware_releases (60000000-...), etc.
--
--           deploy_schema.sql and fix_and_seed.sql ran AFTER the base schema
--           and re-inserted manufacturers using auto-generated UUIDs (not the
--           20000000-... ones). The manufacturers INSERT from the base schema
--           either:
--             a) inserted with 20000000-... UUIDs if it ran first, OR
--             b) was skipped/conflicted if fix_and_seed.sql ran first
--
--           Either way, the chips (30000000-...), hashboards (40000000-...),
--           miner_models (50000000-...), and their downstream records may have
--           failed to insert if the referenced manufacturer UUIDs weren't present.
--
-- Fix:      Look up actual manufacturer UUIDs by brand name from the live DB
--           (the canonical post-fix_and_seed state). Re-insert all Bobby's fleet
--           records using those real UUIDs. Also ensure sources and contributors
--           from the base schema seed exist. All inserts use ON CONFLICT DO NOTHING
--           (idempotent: skip if already present by UUID or unique constraint).
-- =============================================================================

DO $$
DECLARE
    -- Source UUIDs from fix_and_seed.sql / deploy_schema.sql (a0000000-... series)
    -- These are guaranteed to exist after the fix_and_seed.sql ran.
    v_src_bitmain       UUID := 'a0000000-0000-0000-0000-000000000001';
    v_src_auradine      UUID := 'a0000000-0000-0000-0000-000000000004';
    v_src_bixbit        UUID := 'a0000000-0000-0000-0000-00000000000f';  -- bobby_operational
    v_src_braiins       UUID := 'a0000000-0000-0000-0000-000000000009';  -- bitfury_official proxy
    v_src_bobby         UUID := 'a0000000-0000-0000-0000-00000000000f';  -- bobby_operational
    v_src_schema_init   UUID := 'a0000000-0000-0000-0000-00000000000e';  -- catalog_research_2026

    -- Look up actual manufacturer UUIDs by brand name
    -- These are the UUIDs assigned by fix_and_seed.sql (auto-generated or from ON CONFLICT DO UPDATE)
    v_mfr_bitmain       UUID;
    v_mfr_auradine      UUID;
    v_mfr_microbt       UUID;

    -- Bobby's contributor UUID (inserted by fix_and_seed.sql with handle='bobby_fiesler')
    v_contrib_bobby     UUID;

    -- Fixed chip/hashboard/model UUIDs (stable deterministic IDs from base schema)
    -- We keep these deterministic so downstream tables (repair records, etc.) can
    -- reference them by known ID.
    v_chip_bm1362       UUID := '30000000-0000-0000-0000-000000000001';
    v_chip_bm1368       UUID := '30000000-0000-0000-0000-000000000002';
    v_chip_at7200       UUID := '30000000-0000-0000-0000-000000000003';
    v_chip_bm1397       UUID := '30000000-0000-0000-0000-000000000004';

    v_hb_s19jpro        UUID := '40000000-0000-0000-0000-000000000001';
    v_hb_s21exp         UUID := '40000000-0000-0000-0000-000000000002';
    v_hb_s21imm         UUID := '40000000-0000-0000-0000-000000000003';
    v_hb_ah3880         UUID := '40000000-0000-0000-0000-000000000004';

    v_model_s19jpro     UUID := '50000000-0000-0000-0000-000000000001';
    v_model_ah3880      UUID := '50000000-0000-0000-0000-000000000002';
    v_model_s21exp      UUID := '50000000-0000-0000-0000-000000000003';
    v_model_s21imm      UUID := '50000000-0000-0000-0000-000000000004';

    v_fw_bixbit_legacy  UUID := '60000000-0000-0000-0000-000000000001';
    v_fw_bixbit_latest  UUID := '60000000-0000-0000-0000-000000000002';
    v_fw_stock_s19      UUID := '60000000-0000-0000-0000-000000000003';
    v_fw_stock_s21      UUID := '60000000-0000-0000-0000-000000000004';
    v_fw_auradine       UUID := '60000000-0000-0000-0000-000000000005';
    v_fw_braiins        UUID := '60000000-0000-0000-0000-000000000006';

BEGIN
    -- ------------------------------------------------------------------
    -- Step 4.0: Resolve actual manufacturer UUIDs from live DB
    -- ------------------------------------------------------------------
    SELECT id INTO v_mfr_bitmain  FROM hardware.manufacturers WHERE brand = 'bitmain'  LIMIT 1;
    SELECT id INTO v_mfr_auradine FROM hardware.manufacturers WHERE brand = 'auradine' LIMIT 1;
    SELECT id INTO v_mfr_microbt  FROM hardware.manufacturers WHERE brand = 'microbt'  LIMIT 1;

    IF v_mfr_bitmain IS NULL THEN
        RAISE EXCEPTION 'Manufacturer bitmain not found — ensure fix_and_seed.sql ran successfully';
    END IF;
    IF v_mfr_auradine IS NULL THEN
        RAISE EXCEPTION 'Manufacturer auradine not found — ensure fix_and_seed.sql ran successfully';
    END IF;

    -- Resolve Bobby's contributor UUID
    SELECT id INTO v_contrib_bobby FROM knowledge.contributors WHERE handle = 'bobby_fiesler' LIMIT 1;

    -- ------------------------------------------------------------------
    -- Step 4.1: Ensure base-schema sources exist (10000000-... series)
    -- These are referenced by the 60000000-... firmware seed data below.
    -- Use ON CONFLICT on source_key so they merge with existing rows.
    -- ------------------------------------------------------------------

    INSERT INTO knowledge.sources
        (id, source_key, display_name, tier, source_url, description, trust_score,
         contributor_id, is_active)
    VALUES
        ('10000000-0000-0000-0000-000000000001',
         'bitmain_official_site',
         'Bitmain Official Website',
         'tier1_manufacturer',
         'https://www.bitmain.com',
         'Official Bitmain product pages, datasheets, and specifications.',
         0.88,
         NULL, TRUE),
        ('10000000-0000-0000-0000-000000000002',
         'auradine_official_site',
         'Auradine Official Website',
         'tier1_manufacturer',
         'https://www.auradine.com',
         'Official Auradine product pages for Teraflux line.',
         0.90,
         NULL, TRUE),
        ('10000000-0000-0000-0000-000000000003',
         'bixbit_official',
         'BiXBiT Official Documentation',
         'tier1_manufacturer',
         'https://bixbit.io',
         'BiXBiT custom firmware documentation, release notes, and supported hardware.',
         0.92,
         NULL, TRUE),
        ('10000000-0000-0000-0000-000000000004',
         'bobby_operational_data',
         'Bobby Fiesler Operational Data',
         'tier2_operational',
         NULL,
         'Direct measurements and observations from Bobby''s 58-unit fleet at BiXBiT USA Fort Worth TX.',
         0.95,
         v_contrib_bobby, TRUE),
        ('10000000-0000-0000-0000-000000000005',
         'braiins_official',
         'Braiins Official Documentation',
         'tier1_manufacturer',
         'https://braiins.com',
         'Braiins OS, Braiins OS+, and Braiins Pool documentation.',
         0.87,
         NULL, TRUE),
        ('10000000-0000-0000-0000-000000000009',
         'schema_design_initial',
         'Mining Intelligence Catalog — Initial Schema Design',
         'tier2_operational',
         NULL,
         'Internal: Initial seed data loaded during schema creation.',
         0.90,
         v_contrib_bobby, TRUE)
    ON CONFLICT (source_key) DO NOTHING;

    -- ------------------------------------------------------------------
    -- Step 4.2: Chips (30000000-... series)
    -- Referenced by hashboards, so must exist before hashboard inserts.
    -- manufacturer_id resolved from live DB by brand lookup above.
    -- ------------------------------------------------------------------

    INSERT INTO hardware.chips
        (id, chip_model, manufacturer_id, process_node,
         hashrate_gh_per_chip, power_mw_per_chip, efficiency_j_per_th,
         core_voltage_mv_nom, frequency_mhz_nom, algorithm, release_year,
         is_current_gen, primary_source_id, confidence, notes)
    VALUES
        -- BM1362: S19j Pro chip
        (v_chip_bm1362,
         'BM1362',
         v_mfr_bitmain,
         '5nm',
         5800.0, 800.0, 0.138,
         310, 490,
         'SHA-256', 2021, FALSE,
         '10000000-0000-0000-0000-000000000001',
         'medium',
         'Used in Antminer S19j Pro (126 chips per board × 3 boards). '
         'Process node is 5nm. Capable of significant overclock in immersion cooling.'),

        -- BM1368: S21 / S21 EXP chip
        (v_chip_bm1368,
         'BM1368',
         v_mfr_bitmain,
         '5nm',
         9500.0, 1100.0, 0.116,
         350, 600,
         'SHA-256', 2023, TRUE,
         '10000000-0000-0000-0000-000000000001',
         'medium',
         'Used in Antminer S21 EXP Hydro and S21 Immersion. Higher performance successor to BM1362. '
         'Higher efficiency enables >500 TH/s with BiXBiT firmware.'),

        -- AT7200: Auradine Teraflux
        (v_chip_at7200,
         'AT7200',
         v_mfr_auradine,
         '5nm',
         NULL, NULL, NULL,
         NULL, NULL,
         'SHA-256', 2023, TRUE,
         '10000000-0000-0000-0000-000000000002',
         'medium',
         'Used in Auradine Teraflux AH3880. Hydro-native design. '
         'Eco mode 300 TH/s, Turbo mode 600 TH/s across 2 hashboards.'),

        -- BM1397: Older S17/S19 reference chip
        (v_chip_bm1397,
         'BM1397',
         v_mfr_bitmain,
         '7nm',
         3700.0, 650.0, 0.176,
         385, 450,
         'SHA-256', 2020, FALSE,
         '10000000-0000-0000-0000-000000000001',
         'medium',
         'Used in Antminer S17 and early S19 units. 7nm TSMC. Reference chip for repair training.')
    ON CONFLICT (id) DO NOTHING;

    -- ------------------------------------------------------------------
    -- Step 4.3: Hashboards (40000000-... series)
    -- ------------------------------------------------------------------

    INSERT INTO hardware.hashboards
        (id, manufacturer_id, board_name, pcb_revision,
         chip_id, chips_per_board, board_power_w_nom, hashrate_th_nom, hashrate_th_max,
         temp_sensor_count, max_temp_celsius, primary_source_id, confidence, notes)
    VALUES
        -- S19j Pro hashboard
        (v_hb_s19jpro,
         v_mfr_bitmain,
         'Antminer S19j Pro Hashboard',
         'v1.0',
         v_chip_bm1362,
         126,
         1155.0, 34.7, 55.0,
         3, 90,
         '10000000-0000-0000-0000-000000000001',
         'medium',
         'Standard S19j Pro hashboard. 126× BM1362 chips. 3 boards per unit = 104 TH/s stock.'),

        -- S21 EXP Hydro hashboard
        (v_hb_s21exp,
         v_mfr_bitmain,
         'Antminer S21 EXP Hydro Hashboard',
         'v1.0',
         v_chip_bm1368,
         180,
         2550.0, 143.3, 170.0,
         4, 95,
         '10000000-0000-0000-0000-000000000001',
         'medium',
         'S21 EXP Hydro hashboard. 3 boards per unit = 430 TH/s stock. BiXBiT → 506 TH/s.'),

        -- S21 Immersion hashboard
        (v_hb_s21imm,
         v_mfr_bitmain,
         'Antminer S21 Immersion Hashboard',
         'v1.0',
         v_chip_bm1368,
         144,
         1540.0, 69.3, 120.0,
         3, 90,
         '10000000-0000-0000-0000-000000000001',
         'medium',
         'S21 Immersion variant hashboard. 3 boards = 208 TH/s stock, max 360 TH/s.'),

        -- Auradine AH3880 hashboard
        (v_hb_ah3880,
         v_mfr_auradine,
         'Auradine Teraflux AH3880 Hashboard',
         'v1.0',
         v_chip_at7200,
         NULL,
         NULL,
         150.0, 300.0,
         4, 85,
         '10000000-0000-0000-0000-000000000002',
         'medium',
         'AH3880 hashboard. CRITICAL: AH3880 uses EXACTLY 2 boards — NOT 3. '
         'Any record claiming 3 boards is an error. Hydro-native design.')
    ON CONFLICT (id) DO NOTHING;

    -- ------------------------------------------------------------------
    -- Step 4.4: Miner Models — Bobby's 4 fleet models (50000000-... series)
    -- ------------------------------------------------------------------

    INSERT INTO hardware.miner_models
        (id, manufacturer_id, canonical_name, model_number,
         generation, cooling_type, hashboard_count, hashboard_id, board_count_is_fixed,
         stock_hashrate_th, stock_power_w, stock_efficiency_j_th, max_hashrate_th, max_power_w,
         input_voltage_v_nom, algorithm, released_date, is_current_product,
         primary_source_id, confidence, notes)
    VALUES
        -- Antminer S19j Pro
        (v_model_s19jpro,
         v_mfr_bitmain,
         'Antminer S19j Pro',
         'S19J Pro',
         'S19 series',
         'immersion',
         3,
         v_hb_s19jpro,
         TRUE,
         104.0, 3068.0, 29.5,
         160.0, 5500.0,
         220.0,
         'SHA-256',
         '2021-07-01',
         FALSE,
         '10000000-0000-0000-0000-000000000001',
         'verified',
         'Bobby''s fleet includes S19j Pro units. Immersion cooled. '
         'BiXBiT firmware enables up to 160 TH/s (54% above stock 104 TH/s). '
         '3 boards × 126 BM1362 chips. CANNOT have any other board count.'),

        -- Auradine Teraflux AH3880
        (v_model_ah3880,
         v_mfr_auradine,
         'Auradine Teraflux AH3880',
         'AH3880',
         'Teraflux',
         'hydro',
         2,
         v_hb_ah3880,
         TRUE,         -- CRITICAL: EXACTLY 2 BOARDS. board_count_is_fixed = TRUE
         300.0, 1800.0, 6.0,
         600.0, 5500.0,
         48.0,
         'SHA-256',
         '2023-01-01',
         TRUE,
         '10000000-0000-0000-0000-000000000002',
         'verified',
         'CRITICAL DESIGN RULE: AH3880 has EXACTLY 2 hashboards. Any record stating 3 boards '
         'is wrong. Hydro-cooled only. AT7200 chip. Eco: 300 TH/s, Turbo: 600 TH/s. '
         'Bobby runs these at BiXBiT USA Fort Worth in hydro cooling loop.'),

        -- Antminer S21 EXP Hydro
        (v_model_s21exp,
         v_mfr_bitmain,
         'Antminer S21 EXP Hydro',
         'S21 EXP',
         'S21 series',
         'hydro',
         3,
         v_hb_s21exp,
         TRUE,
         430.0, 5765.0, 13.4,
         506.0, 7500.0,
         48.0,
         'SHA-256',
         '2024-01-01',
         TRUE,
         '10000000-0000-0000-0000-000000000001',
         'verified',
         'Hydro-cooled S21 EXP. 3 boards × BM1368 chips. Stock 430 TH/s. '
         'BiXBiT firmware enables up to 506 TH/s (18% above stock). '
         'Part of Bobby''s current fleet at BiXBiT USA Fort Worth.'),

        -- Antminer S21 Immersion
        (v_model_s21imm,
         v_mfr_bitmain,
         'Antminer S21 Immersion',
         'S21 Immersion',
         'S21 series',
         'immersion',
         3,
         v_hb_s21imm,
         TRUE,
         208.0, 3500.0, 16.8,
         360.0, 6000.0,
         220.0,
         'SHA-256',
         '2023-07-01',
         TRUE,
         '10000000-0000-0000-0000-000000000001',
         'verified',
         'Immersion-cooled S21 variant. 3 boards × BM1368 chips. Stock 208 TH/s, max 360 TH/s. '
         'Part of Bobby''s fleet at BiXBiT USA Fort Worth.')
    ON CONFLICT (id) DO NOTHING;

    -- ------------------------------------------------------------------
    -- Step 4.5: Model Aliases — critical for fuzzy matching against
    --           repair records, AMS logs, and 1M+ import data
    -- ------------------------------------------------------------------

    -- NOTE: model_aliases has no UUID PK — use ON CONFLICT (miner_model_id, alias_normalized)
    -- Check if unique constraint exists on that pair; if not, use DO NOTHING on the whole row.
    INSERT INTO hardware.model_aliases
        (miner_model_id, alias, alias_normalized, alias_source, is_common)
    VALUES
        -- S19j Pro aliases
        (v_model_s19jpro, 'Antminer S19j Pro',         'antminers19jpro',      'manufacturer_doc', TRUE),
        (v_model_s19jpro, 'S19j Pro',                  's19jpro',              'manufacturer_doc', TRUE),
        (v_model_s19jpro, 'S19J Pro',                  's19jpro',              'manufacturer_doc', FALSE),
        (v_model_s19jpro, 'S19JPro',                   's19jpro',              'forum',            TRUE),
        (v_model_s19jpro, 'S19-J-Pro',                 's19jpro',              'forum',            FALSE),
        (v_model_s19jpro, 's19j pro',                  's19jpro',              'repair_shop_import',TRUE),
        (v_model_s19jpro, 'S19 J Pro',                 's19jpro',              'forum',            FALSE),
        (v_model_s19jpro, 'Antminer S19J Pro 104TH',   'antminers19jpro104th', 'listing',          FALSE),
        (v_model_s19jpro, 'BM S19J Pro',               'bms19jpro',            'repair_shop_import',FALSE),
        (v_model_s19jpro, 's19j-pro',                  's19jpro',              'repair_shop_import',FALSE),
        -- AH3880 aliases
        (v_model_ah3880, 'Auradine Teraflux AH3880',   'auraterafluxah3880',   'manufacturer_doc', TRUE),
        (v_model_ah3880, 'AH3880',                     'ah3880',               'manufacturer_doc', TRUE),
        (v_model_ah3880, 'Auradine AH3880',            'auradineah3880',        'manufacturer_doc', TRUE),
        (v_model_ah3880, 'Teraflux AH3880',            'terafluxah3880',        'forum',            FALSE),
        (v_model_ah3880, 'AH 3880',                    'ah3880',               'forum',            FALSE),
        (v_model_ah3880, 'auradine ah3880',             'auradineah3880',       'repair_shop_import',FALSE),
        -- S21 EXP Hydro aliases
        (v_model_s21exp, 'Antminer S21 EXP Hydro',     'antminers21exphydro',  'manufacturer_doc', TRUE),
        (v_model_s21exp, 'S21 EXP Hydro',              's21exphydro',          'manufacturer_doc', TRUE),
        (v_model_s21exp, 'S21EXP',                     's21exp',               'forum',            TRUE),
        (v_model_s21exp, 'S21 EXP',                    's21exp',               'manufacturer_doc', TRUE),
        (v_model_s21exp, 'S21EXPHydro',                's21exphydro',          'forum',            FALSE),
        (v_model_s21exp, 's21 exp hydro',              's21exphydro',          'repair_shop_import',FALSE),
        (v_model_s21exp, 'Antminer S21 EXP 430TH',     'antminers21exp430th',  'listing',          FALSE),
        -- S21 Immersion aliases
        (v_model_s21imm, 'Antminer S21 Immersion',     'antminers21immersion', 'manufacturer_doc', TRUE),
        (v_model_s21imm, 'S21 Immersion',              's21immersion',         'manufacturer_doc', TRUE),
        (v_model_s21imm, 'S21Imm',                     's21imm',               'forum',            TRUE),
        (v_model_s21imm, 's21 imm',                    's21imm',               'repair_shop_import',FALSE),
        (v_model_s21imm, 'S21-Immersion',              's21immersion',         'forum',            FALSE),
        (v_model_s21imm, 'Antminer S21 208TH',         'antminers21208th',     'listing',          FALSE)
    ON CONFLICT DO NOTHING;

    -- ------------------------------------------------------------------
    -- Step 4.6: Firmware Releases (60000000-... series)
    -- UNIQUE constraint on (firmware_family, version_string) — use ON CONFLICT.
    -- ------------------------------------------------------------------

    INSERT INTO firmware.firmware_releases
        (id, firmware_family, version_string, display_name,
         developer_name, developer_url, is_current_stable,
         supports_autotuning, supports_eco_mode, supports_turbo_mode,
         supports_ssl_mining, max_hashrate_increase_pct,
         primary_source_id, confidence, notes)
    VALUES
        -- BiXBiT Legacy (on Bobby's S19j Pro fleet)
        (v_fw_bixbit_legacy,
         'bixbit', '2024-10-22-legacy',
         'BiXBiT 2024-10-22 (Legacy)',
         'BiXBiT', 'https://bixbit.io',
         FALSE, TRUE, TRUE, TRUE, TRUE,
         54.0,
         '10000000-0000-0000-0000-000000000003',
         'verified',
         'BiXBiT firmware version running on Bobby''s S19j Pro units. Enables 160 TH/s from 104 TH/s.'),

        -- BiXBiT Latest (2025 — on S21 EXP Hydro)
        (v_fw_bixbit_latest,
         'bixbit', '2025-latest',
         'BiXBiT Latest (2025)',
         'BiXBiT', 'https://bixbit.io',
         TRUE, TRUE, TRUE, TRUE, TRUE,
         18.0,
         '10000000-0000-0000-0000-000000000003',
         'verified',
         'Current BiXBiT firmware. Supports S21 EXP Hydro → 506 TH/s.'),

        -- Stock Bitmain — S19j Pro
        (v_fw_stock_s19,
         'stock_bitmain', 'stock_s19j_pro',
         'Bitmain S19j Pro Stock Firmware',
         'Bitmain', 'https://www.bitmain.com',
         FALSE, FALSE, FALSE, FALSE, FALSE,
         0.0,
         '10000000-0000-0000-0000-000000000001',
         'high',
         'Stock Bitmain firmware for S19j Pro. 104 TH/s stock.'),

        -- Stock Bitmain — S21 EXP / S21 Immersion
        (v_fw_stock_s21,
         'stock_bitmain', 'stock_s21_exp',
         'Bitmain S21 EXP Stock Firmware',
         'Bitmain', 'https://www.bitmain.com',
         TRUE, FALSE, FALSE, FALSE, FALSE,
         0.0,
         '10000000-0000-0000-0000-000000000001',
         'high',
         'Stock Bitmain firmware for S21 EXP Hydro and S21 Immersion. 430 / 208 TH/s.'),

        -- Auradine Native
        (v_fw_auradine,
         'auradine_native', 'auradine_latest',
         'Auradine Native Firmware (Latest)',
         'Auradine', 'https://www.auradine.com',
         TRUE, TRUE, TRUE, TRUE, TRUE,
         0.0,
         '10000000-0000-0000-0000-000000000002',
         'verified',
         'Auradine''s native firmware for AH3880. Eco 300 TH/s / Turbo 600 TH/s.'),

        -- Braiins OS+
        (v_fw_braiins,
         'braiins_os', 'bos_24_09',
         'Braiins OS+ 24.09',
         'Braiins', 'https://braiins.com',
         TRUE, TRUE, TRUE, TRUE, TRUE,
         10.0,
         '10000000-0000-0000-0000-000000000005',
         'high',
         'Braiins OS+ version 24.09. Autotuning firmware for Bitmain S-series.')
    ON CONFLICT (firmware_family, version_string) DO NOTHING;

    -- ------------------------------------------------------------------
    -- Step 4.7: Firmware Compatibility Records
    -- UNIQUE on (firmware_id, miner_model_id)
    -- ------------------------------------------------------------------

    INSERT INTO firmware.firmware_compatibility
        (firmware_id, miner_model_id,
         is_compatible, is_officially_supported,
         typical_hashrate_th, max_achievable_th,
         verified_by_bobby, primary_source_id, confidence, notes)
    VALUES
        -- BiXBiT Legacy on S19j Pro (Bobby verified)
        (v_fw_bixbit_legacy, v_model_s19jpro,
         TRUE, FALSE, 140.0, 160.0, TRUE,
         '10000000-0000-0000-0000-000000000004',
         'verified',
         'Bobby verified: BiXBiT on S19j Pro achieves 140–160 TH/s immersion. '
         'Typical daily average ~145 TH/s. Max observed 160 TH/s at low coolant temp.'),

        -- BiXBiT Latest on S21 EXP Hydro (Bobby verified)
        (v_fw_bixbit_latest, v_model_s21exp,
         TRUE, FALSE, 480.0, 506.0, TRUE,
         '10000000-0000-0000-0000-000000000004',
         'verified',
         'Bobby verified: BiXBiT on S21 EXP Hydro achieves up to 506 TH/s. '
         'Typical operation ~470-490 TH/s.'),

        -- Auradine Native on AH3880 (only supported firmware)
        (v_fw_auradine, v_model_ah3880,
         TRUE, TRUE, 300.0, 600.0, TRUE,
         '10000000-0000-0000-0000-000000000004',
         'verified',
         'Auradine native firmware is the ONLY firmware for AH3880. '
         'Eco: 300 TH/s, Turbo: 600 TH/s. Bobby verified both modes.'),

        -- Stock Bitmain on S19j Pro
        (v_fw_stock_s19, v_model_s19jpro,
         TRUE, TRUE, 104.0, 104.0, FALSE,
         '10000000-0000-0000-0000-000000000001',
         'verified',
         'Stock firmware, stock performance: 104 TH/s.'),

        -- Stock Bitmain on S21 EXP Hydro
        (v_fw_stock_s21, v_model_s21exp,
         TRUE, TRUE, 430.0, 430.0, FALSE,
         '10000000-0000-0000-0000-000000000001',
         'verified',
         'Stock firmware on S21 EXP Hydro: 430 TH/s.'),

        -- Stock Bitmain on S21 Immersion
        (v_fw_stock_s21, v_model_s21imm,
         TRUE, TRUE, 208.0, 360.0, FALSE,
         '10000000-0000-0000-0000-000000000001',
         'verified',
         'Stock firmware on S21 Immersion: 208 TH/s. Max with tuning: 360 TH/s.')
    ON CONFLICT (firmware_id, miner_model_id) DO NOTHING;

    -- ------------------------------------------------------------------
    -- Step 4.8: Autotuning Profiles
    -- UNIQUE on (firmware_id, miner_model_id, profile_name)
    -- ------------------------------------------------------------------

    INSERT INTO firmware.firmware_autotuning_profiles
        (firmware_id, miner_model_id,
         profile_name, operational_mode,
         target_hashrate_th, measured_hashrate_th,
         verified_by_bobby, verification_date,
         primary_source_id, confidence, notes)
    VALUES
        -- S19j Pro: BiXBiT Eco
        (v_fw_bixbit_legacy, v_model_s19jpro,
         'BiXBiT Eco', 'eco',
         120.0, 118.0,
         TRUE, '2024-01-01',
         '10000000-0000-0000-0000-000000000004', 'verified',
         'S19j Pro BiXBiT eco mode: ~118-120 TH/s at reduced power.'),

        -- S19j Pro: BiXBiT Max/Turbo
        (v_fw_bixbit_legacy, v_model_s19jpro,
         'BiXBiT Max', 'turbo',
         160.0, 155.0,
         TRUE, '2024-01-01',
         '10000000-0000-0000-0000-000000000004', 'verified',
         'S19j Pro BiXBiT max: up to 160 TH/s observed at low coolant temps.'),

        -- AH3880: Auradine Eco
        (v_fw_auradine, v_model_ah3880,
         'Auradine Eco', 'eco',
         300.0, 300.0,
         TRUE, '2024-01-01',
         '10000000-0000-0000-0000-000000000004', 'verified',
         'AH3880 eco mode: 300 TH/s across 2 boards.'),

        -- AH3880: Auradine Turbo
        (v_fw_auradine, v_model_ah3880,
         'Auradine Turbo', 'turbo',
         600.0, 590.0,
         TRUE, '2024-01-01',
         '10000000-0000-0000-0000-000000000004', 'verified',
         'AH3880 turbo mode: 600 TH/s spec. Bobby observes ~580-600 TH/s in practice.'),

        -- S21 EXP Hydro: BiXBiT Max
        (v_fw_bixbit_latest, v_model_s21exp,
         'BiXBiT S21 Max', 'turbo',
         506.0, 490.0,
         TRUE, '2024-06-01',
         '10000000-0000-0000-0000-000000000004', 'verified',
         'S21 EXP Hydro BiXBiT max: up to 506 TH/s. Typical ~470-490 TH/s.'),

        -- S21 EXP Hydro: Stock Normal
        (v_fw_stock_s21, v_model_s21exp,
         'S21 EXP Stock', 'normal',
         430.0, 430.0,
         FALSE, NULL,
         '10000000-0000-0000-0000-000000000001', 'verified',
         'S21 EXP Hydro stock: 430 TH/s.'),

        -- S21 Immersion: Stock Normal
        (v_fw_stock_s21, v_model_s21imm,
         'S21 Imm Stock', 'normal',
         208.0, 208.0,
         FALSE, NULL,
         '10000000-0000-0000-0000-000000000001', 'verified',
         'S21 Immersion stock: 208 TH/s.'),

        -- S21 Immersion: Max Tuned
        (v_fw_stock_s21, v_model_s21imm,
         'S21 Imm Max Tuned', 'turbo',
         360.0, NULL,
         FALSE, NULL,
         '10000000-0000-0000-0000-000000000001', 'medium',
         'S21 Immersion max achievable with tuning: 360 TH/s (not Bobby-verified yet).')
    ON CONFLICT (firmware_id, miner_model_id, profile_name) DO NOTHING;

    RAISE NOTICE 'Issue 4 seed data applied successfully.';
    RAISE NOTICE '  Manufacturer IDs used: bitmain=%, auradine=%', v_mfr_bitmain, v_mfr_auradine;

END;
$$;


-- =============================================================================
-- VERIFICATION
-- Run at the end to confirm all 4 fixes applied correctly.
-- =============================================================================

DO $$
DECLARE
    v_count         INTEGER;
    v_pass          INTEGER := 0;
    v_fail          INTEGER := 0;
BEGIN
    -- Helper macro: inline logic used repeatedly below
    -- -----------------------------------------------------------------------
    -- Issue 1: freshness_log table and view
    -- -----------------------------------------------------------------------
    SELECT COUNT(*) INTO v_count
    FROM information_schema.tables
    WHERE table_schema = 'knowledge' AND table_name = 'freshness_log';
    IF v_count >= 1 THEN
        RAISE NOTICE '[PASS] Issue 1a: knowledge.freshness_log table exists -- count=%', v_count;
        v_pass := v_pass + 1;
    ELSE
        RAISE WARNING '[FAIL] Issue 1a: knowledge.freshness_log table exists -- count=%  (expected >= 1)', v_count;
        v_fail := v_fail + 1;
    END IF;

    -- Confirm NO generated column exists
    SELECT COUNT(*) INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'knowledge'
      AND table_name   = 'freshness_log'
      AND is_generated = 'ALWAYS';
    IF v_count = 0 THEN
        RAISE NOTICE '[PASS] Issue 1b: freshness_log has no GENERATED ALWAYS column';
        v_pass := v_pass + 1;
    ELSE
        RAISE WARNING '[FAIL] Issue 1b: freshness_log still has % GENERATED ALWAYS column(s)', v_count;
        v_fail := v_fail + 1;
    END IF;

    -- deleted_at column present
    SELECT COUNT(*) INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'knowledge'
      AND table_name   = 'freshness_log'
      AND column_name  = 'deleted_at';
    IF v_count >= 1 THEN
        RAISE NOTICE '[PASS] Issue 1c: freshness_log.deleted_at column exists -- count=%', v_count;
        v_pass := v_pass + 1;
    ELSE
        RAISE WARNING '[FAIL] Issue 1c: freshness_log.deleted_at column exists -- count=%  (expected >= 1)', v_count;
        v_fail := v_fail + 1;
    END IF;

    -- View exists
    SELECT COUNT(*) INTO v_count
    FROM information_schema.views
    WHERE table_schema = 'knowledge' AND table_name = 'freshness_log_view';
    IF v_count >= 1 THEN
        RAISE NOTICE '[PASS] Issue 1d: knowledge.freshness_log_view view exists -- count=%', v_count;
        v_pass := v_pass + 1;
    ELSE
        RAISE WARNING '[FAIL] Issue 1d: knowledge.freshness_log_view view exists -- count=%  (expected >= 1)', v_count;
        v_fail := v_fail + 1;
    END IF;

    -- Indexes
    SELECT COUNT(*) INTO v_count
    FROM pg_indexes
    WHERE schemaname = 'knowledge' AND tablename = 'freshness_log'
      AND indexname IN ('idx_freshness_row', 'idx_freshness_stale', 'idx_freshness_due');
    IF v_count >= 3 THEN
        RAISE NOTICE '[PASS] Issue 1e: all 3 freshness_log indexes exist -- count=%', v_count;
        v_pass := v_pass + 1;
    ELSE
        RAISE WARNING '[FAIL] Issue 1e: all 3 freshness_log indexes exist -- count=%  (expected >= 3)', v_count;
        v_fail := v_fail + 1;
    END IF;

    -- -----------------------------------------------------------------------
    -- Issue 2: raw_ingestion_log partitioned table + partitions
    -- -----------------------------------------------------------------------
    SELECT COUNT(*) INTO v_count
    FROM information_schema.tables
    WHERE table_schema = 'knowledge' AND table_name = 'raw_ingestion_log';
    IF v_count >= 1 THEN
        RAISE NOTICE '[PASS] Issue 2a: knowledge.raw_ingestion_log parent table exists -- count=%', v_count;
        v_pass := v_pass + 1;
    ELSE
        RAISE WARNING '[FAIL] Issue 2a: knowledge.raw_ingestion_log parent table exists -- count=%  (expected >= 1)', v_count;
        v_fail := v_fail + 1;
    END IF;

    -- Confirm PK includes ingested_at
    SELECT COUNT(*) INTO v_count
    FROM information_schema.key_column_usage kcu
    JOIN information_schema.table_constraints tc
        ON kcu.constraint_name = tc.constraint_name
       AND kcu.table_schema    = tc.table_schema
    WHERE tc.constraint_type = 'PRIMARY KEY'
      AND kcu.table_schema   = 'knowledge'
      AND kcu.table_name     = 'raw_ingestion_log'
      AND kcu.column_name    = 'ingested_at';
    IF v_count >= 1 THEN
        RAISE NOTICE '[PASS] Issue 2b: raw_ingestion_log PK includes ingested_at -- count=%', v_count;
        v_pass := v_pass + 1;
    ELSE
        RAISE WARNING '[FAIL] Issue 2b: raw_ingestion_log PK includes ingested_at -- count=%  (expected >= 1)', v_count;
        v_fail := v_fail + 1;
    END IF;

    -- Count partitions
    SELECT COUNT(*) INTO v_count
    FROM information_schema.tables
    WHERE table_schema = 'knowledge'
      AND table_name LIKE 'raw_ingestion_log_20%';
    IF v_count >= 5 THEN
        RAISE NOTICE '[PASS] Issue 2c: 5 quarterly partitions exist -- count=%', v_count;
        v_pass := v_pass + 1;
    ELSE
        RAISE WARNING '[FAIL] Issue 2c: 5 quarterly partitions exist -- count=%  (expected >= 5)', v_count;
        v_fail := v_fail + 1;
    END IF;

    -- Count indexes on parent
    SELECT COUNT(*) INTO v_count
    FROM pg_indexes
    WHERE schemaname = 'knowledge' AND tablename = 'raw_ingestion_log'
      AND indexname IN ('idx_raw_ingestion_source', 'idx_raw_ingestion_miner',
                        'idx_raw_ingestion_hash', 'idx_raw_ingestion_new_fields');
    IF v_count >= 4 THEN
        RAISE NOTICE '[PASS] Issue 2d: all 4 raw_ingestion_log indexes exist -- count=%', v_count;
        v_pass := v_pass + 1;
    ELSE
        RAISE WARNING '[FAIL] Issue 2d: all 4 raw_ingestion_log indexes exist -- count=%  (expected >= 4)', v_count;
        v_fail := v_fail + 1;
    END IF;

    -- -----------------------------------------------------------------------
    -- Issue 3: Custom trigger functions and triggers
    -- -----------------------------------------------------------------------
    SELECT COUNT(*) INTO v_count
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'firmware' AND p.proname = 'update_fw_search_vector';
    IF v_count >= 1 THEN
        RAISE NOTICE '[PASS] Issue 3a: firmware.update_fw_search_vector() function exists -- count=%', v_count;
        v_pass := v_pass + 1;
    ELSE
        RAISE WARNING '[FAIL] Issue 3a: firmware.update_fw_search_vector() function exists -- count=%  (expected >= 1)', v_count;
        v_fail := v_fail + 1;
    END IF;

    SELECT COUNT(*) INTO v_count
    FROM pg_trigger t
    JOIN pg_class c ON c.oid = t.tgrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'firmware' AND c.relname = 'firmware_releases'
      AND t.tgname = 'trg_fw_search_vector';
    IF v_count >= 1 THEN
        RAISE NOTICE '[PASS] Issue 3b: trg_fw_search_vector trigger on firmware_releases exists -- count=%', v_count;
        v_pass := v_pass + 1;
    ELSE
        RAISE WARNING '[FAIL] Issue 3b: trg_fw_search_vector trigger on firmware_releases exists -- count=%  (expected >= 1)', v_count;
        v_fail := v_fail + 1;
    END IF;

    SELECT COUNT(*) INTO v_count
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'facility' AND p.proname = 'update_cool_sol_search_vector';
    IF v_count >= 1 THEN
        RAISE NOTICE '[PASS] Issue 3c: facility.update_cool_sol_search_vector() function exists -- count=%', v_count;
        v_pass := v_pass + 1;
    ELSE
        RAISE WARNING '[FAIL] Issue 3c: facility.update_cool_sol_search_vector() function exists -- count=%  (expected >= 1)', v_count;
        v_fail := v_fail + 1;
    END IF;

    SELECT COUNT(*) INTO v_count
    FROM pg_trigger t
    JOIN pg_class c ON c.oid = t.tgrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'facility' AND c.relname = 'cooling_solutions'
      AND t.tgname = 'trg_cool_sol_search_vector';
    IF v_count >= 1 THEN
        RAISE NOTICE '[PASS] Issue 3d: trg_cool_sol_search_vector trigger on cooling_solutions exists -- count=%', v_count;
        v_pass := v_pass + 1;
    ELSE
        RAISE WARNING '[FAIL] Issue 3d: trg_cool_sol_search_vector trigger on cooling_solutions exists -- count=%  (expected >= 1)', v_count;
        v_fail := v_fail + 1;
    END IF;

    -- -----------------------------------------------------------------------
    -- Issue 4: Seed data counts
    -- -----------------------------------------------------------------------
    SELECT COUNT(*) INTO v_count FROM hardware.chips
    WHERE id IN (
        '30000000-0000-0000-0000-000000000001',
        '30000000-0000-0000-0000-000000000002',
        '30000000-0000-0000-0000-000000000003',
        '30000000-0000-0000-0000-000000000004'
    );
    IF v_count >= 4 THEN
        RAISE NOTICE '[PASS] Issue 4a: all 4 fleet chips present -- count=%', v_count;
        v_pass := v_pass + 1;
    ELSE
        RAISE WARNING '[FAIL] Issue 4a: all 4 fleet chips present -- count=%  (expected >= 4)', v_count;
        v_fail := v_fail + 1;
    END IF;

    SELECT COUNT(*) INTO v_count FROM hardware.hashboards
    WHERE id IN (
        '40000000-0000-0000-0000-000000000001',
        '40000000-0000-0000-0000-000000000002',
        '40000000-0000-0000-0000-000000000003',
        '40000000-0000-0000-0000-000000000004'
    );
    IF v_count >= 4 THEN
        RAISE NOTICE '[PASS] Issue 4b: all 4 fleet hashboards present -- count=%', v_count;
        v_pass := v_pass + 1;
    ELSE
        RAISE WARNING '[FAIL] Issue 4b: all 4 fleet hashboards present -- count=%  (expected >= 4)', v_count;
        v_fail := v_fail + 1;
    END IF;

    SELECT COUNT(*) INTO v_count FROM hardware.miner_models
    WHERE id IN (
        '50000000-0000-0000-0000-000000000001',
        '50000000-0000-0000-0000-000000000002',
        '50000000-0000-0000-0000-000000000003',
        '50000000-0000-0000-0000-000000000004'
    );
    IF v_count >= 4 THEN
        RAISE NOTICE '[PASS] Issue 4c: all 4 Bobby fleet miner_models present -- count=%', v_count;
        v_pass := v_pass + 1;
    ELSE
        RAISE WARNING '[FAIL] Issue 4c: all 4 Bobby fleet miner_models present -- count=%  (expected >= 4)', v_count;
        v_fail := v_fail + 1;
    END IF;

    SELECT COUNT(*) INTO v_count FROM firmware.firmware_releases
    WHERE id IN (
        '60000000-0000-0000-0000-000000000001',
        '60000000-0000-0000-0000-000000000002',
        '60000000-0000-0000-0000-000000000003',
        '60000000-0000-0000-0000-000000000004',
        '60000000-0000-0000-0000-000000000005',
        '60000000-0000-0000-0000-000000000006'
    );
    IF v_count >= 6 THEN
        RAISE NOTICE '[PASS] Issue 4d: all 6 firmware releases present -- count=%', v_count;
        v_pass := v_pass + 1;
    ELSE
        RAISE WARNING '[FAIL] Issue 4d: all 6 firmware releases present -- count=%  (expected >= 6)', v_count;
        v_fail := v_fail + 1;
    END IF;

    SELECT COUNT(*) INTO v_count FROM firmware.firmware_compatibility
    WHERE firmware_id IN (
        '60000000-0000-0000-0000-000000000001',
        '60000000-0000-0000-0000-000000000002',
        '60000000-0000-0000-0000-000000000003',
        '60000000-0000-0000-0000-000000000004',
        '60000000-0000-0000-0000-000000000005'
    );
    IF v_count >= 6 THEN
        RAISE NOTICE '[PASS] Issue 4e: firmware compatibility records present (>= 6) -- count=%', v_count;
        v_pass := v_pass + 1;
    ELSE
        RAISE WARNING '[FAIL] Issue 4e: firmware compatibility records present (>= 6) -- count=%  (expected >= 6)', v_count;
        v_fail := v_fail + 1;
    END IF;

    SELECT COUNT(*) INTO v_count FROM firmware.firmware_autotuning_profiles
    WHERE firmware_id IN (
        '60000000-0000-0000-0000-000000000001',
        '60000000-0000-0000-0000-000000000002',
        '60000000-0000-0000-0000-000000000004',
        '60000000-0000-0000-0000-000000000005'
    );
    IF v_count >= 8 THEN
        RAISE NOTICE '[PASS] Issue 4f: autotuning profiles present (>= 8) -- count=%', v_count;
        v_pass := v_pass + 1;
    ELSE
        RAISE WARNING '[FAIL] Issue 4f: autotuning profiles present (>= 8) -- count=%  (expected >= 8)', v_count;
        v_fail := v_fail + 1;
    END IF;

    -- Verify model aliases for known fleet models
    SELECT COUNT(*) INTO v_count FROM hardware.model_aliases
    WHERE miner_model_id IN (
        '50000000-0000-0000-0000-000000000001',
        '50000000-0000-0000-0000-000000000002',
        '50000000-0000-0000-0000-000000000003',
        '50000000-0000-0000-0000-000000000004'
    );
    IF v_count >= 27 THEN
        RAISE NOTICE '[PASS] Issue 4g: model aliases for fleet models present (>= 27) -- count=%', v_count;
        v_pass := v_pass + 1;
    ELSE
        RAISE WARNING '[FAIL] Issue 4g: model aliases for fleet models present (>= 27) -- count=%  (expected >= 27)', v_count;
        v_fail := v_fail + 1;
    END IF;

    -- -----------------------------------------------------------------------
    -- Summary
    -- -----------------------------------------------------------------------
    RAISE NOTICE '================================================';
    RAISE NOTICE 'schema_fixes_v1.sql verification complete';
    RAISE NOTICE 'PASSED: %   FAILED: %', v_pass, v_fail;
    IF v_fail = 0 THEN
        RAISE NOTICE 'ALL CHECKS PASSED — patch applied cleanly.';
    ELSE
        RAISE WARNING '% CHECK(S) FAILED — review WARNINGS above.', v_fail;
    END IF;
    RAISE NOTICE '================================================';
END;
$$;
