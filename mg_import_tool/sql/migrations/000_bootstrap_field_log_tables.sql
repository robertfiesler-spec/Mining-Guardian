-- ============================================================================
-- Mining Guardian — Field Log Bootstrap Migration
-- ============================================================================
-- Creates the `knowledge.field_log_*` v2 tables and `mg.import_runs`.
-- These tables are currently bootstrapped at runtime by mg_import.py
-- (lines 941-1112 of mg_import_tool/mg_import.py) on first connection.
-- This file captures that DDL as a formal migration so a fresh database can
-- be stood up from repo artifacts alone without running the import tool.
--
-- Ordering: apply this migration BEFORE 002_layer2_and_learning_foundation.sql.
-- Proposed numbering in the repo: 000_bootstrap_field_log_tables.sql
--   (000 because 001_initial_schema.sql is the VPS `public.*` schema, and 002
--    is the Layer 2 additions that depend on these tables existing.)
--
-- Target database: `mining_guardian` on the PC Docker container
--                  `mining-guardian-db` (NOT the VPS Postgres).
--                  When the catalog moves to Mac Mini or VPS, this migration
--                  is applied there.
--
-- Idempotent: all CREATEs use IF NOT EXISTS; all ALTERs use IF NOT EXISTS.
-- Safe to run against a database that already has these tables (no-op).
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Schemas
-- ---------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS knowledge;
CREATE SCHEMA IF NOT EXISTS mg;

-- ---------------------------------------------------------------------------
-- knowledge.field_log_imports — one row per ingested archive
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge.field_log_imports (
    id                   BIGSERIAL PRIMARY KEY,
    entity_label         TEXT NOT NULL UNIQUE,
    sha256               TEXT NOT NULL,
    file_size_bytes      BIGINT,
    detected_shape       TEXT NOT NULL,      -- 'whatsminer' | 'antminer' | ...
    miner_ip             TEXT,
    miner_model          TEXT,
    firmware_version     TEXT,
    mac_address          TEXT,
    control_board        TEXT,
    kernel_version       TEXT,
    archive_timestamp    TIMESTAMP,
    files_in_archive     INTEGER,
    parse_warnings       TEXT,
    ingested_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- knowledge.field_log_miner_identity — one row per boot session per archive
-- Populated by v3.2+ identity extraction. Includes resolver stamp columns.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge.field_log_miner_identity (
    id                      BIGSERIAL PRIMARY KEY,
    entity_label            TEXT NOT NULL UNIQUE,
    archive_filename        TEXT NOT NULL,
    miner_type              TEXT,
    firmware_version        TEXT,
    btminer_md5             TEXT,
    mac_address             TEXT,
    control_board_version   TEXT,
    kernel_version          TEXT,
    cool_mode               TEXT,
    slot                    INTEGER,
    pcb_serial              TEXT,
    chip_data               TEXT,
    hashrate_gh             TEXT,
    ingested_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Resolver stamp columns (added by v3.2; idempotent here so a fresh DB gets them directly)
ALTER TABLE knowledge.field_log_miner_identity
    ADD COLUMN IF NOT EXISTS hardware_revision       TEXT;
ALTER TABLE knowledge.field_log_miner_identity
    ADD COLUMN IF NOT EXISTS resolved_miner_model_id UUID;
ALTER TABLE knowledge.field_log_miner_identity
    ADD COLUMN IF NOT EXISTS resolution_tier         TEXT;
ALTER TABLE knowledge.field_log_miner_identity
    ADD COLUMN IF NOT EXISTS resolution_alias        TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS field_log_miner_identity_archive_entity_idx
    ON knowledge.field_log_miner_identity (archive_filename, entity_label);

-- ---------------------------------------------------------------------------
-- knowledge.field_log_power_samples — WhatsMiner power detail per sample
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge.field_log_power_samples (
    id               BIGSERIAL PRIMARY KEY,
    archive_filename TEXT NOT NULL,
    sample_source    TEXT NOT NULL,
    sample_idx       INTEGER,
    en_eset          TEXT,
    iout_a           NUMERIC,
    vout_v           NUMERIC,
    vset_v           NUMERIC,
    iin0_a           NUMERIC,  iin1_a NUMERIC,  iin2_a NUMERIC,
    vin0_v           NUMERIC,  vin1_v NUMERIC,  vin2_v NUMERIC,
    pin_w            NUMERIC,
    t0_c             NUMERIC,  t1_c   NUMERIC,  t2_c   NUMERIC,
    stat_code        TEXT,
    raw_line         TEXT,
    UNIQUE (archive_filename, sample_source, sample_idx)
);

-- ---------------------------------------------------------------------------
-- knowledge.field_log_temp_snapshots — per-chain / per-board temp snapshots
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge.field_log_temp_snapshots (
    id                BIGSERIAL PRIMARY KEY,
    archive_filename  TEXT NOT NULL,
    snapshot_type     TEXT NOT NULL,
    slot              INTEGER,
    snapshot_temp_c   NUMERIC,
    board_serial      TEXT,
    raw_content       TEXT,
    UNIQUE (archive_filename, snapshot_type, slot, board_serial)
);

-- ---------------------------------------------------------------------------
-- knowledge.field_log_pools — raw pool configuration per archive
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge.field_log_pools (
    id                BIGSERIAL PRIMARY KEY,
    archive_filename  TEXT NOT NULL,
    pool_idx          INTEGER,
    url               TEXT,
    user_name         TEXT,
    priority          TEXT,
    raw_block         TEXT,
    UNIQUE (archive_filename, pool_idx)
);

-- ---------------------------------------------------------------------------
-- knowledge.field_log_api_stats — WhatsMiner API stats blocks
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge.field_log_api_stats (
    id                BIGSERIAL PRIMARY KEY,
    archive_filename  TEXT NOT NULL,
    stats_section     TEXT NOT NULL,
    slot              INTEGER,
    elapsed_s         BIGINT,
    chip_num          INTEGER,
    freqs_avg         NUMERIC,
    temp_c            NUMERIC,
    chip_verify_diff  TEXT,
    work_count        BIGINT,
    nonce_count       BIGINT,
    nonce_before      BIGINT,
    nonce_err_count   BIGINT,
    raw_block         TEXT,
    UNIQUE (archive_filename, stats_section)
);

-- ---------------------------------------------------------------------------
-- knowledge.field_log_antminer_boots — one row per Antminer boot session
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge.field_log_antminer_boots (
    id                BIGSERIAL PRIMARY KEY,
    entity_label      TEXT NOT NULL UNIQUE,
    archive_filename  TEXT NOT NULL,
    boot_timestamp    TIMESTAMP,
    session_folder    TEXT NOT NULL,
    files_present     TEXT[],
    ingested_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- knowledge.field_log_antminer_autotune — the big table, one row per event
-- First real run: 14,178 rows from a single archive (Antminer_S19_2024-06-27)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge.field_log_antminer_autotune (
    id                BIGSERIAL PRIMARY KEY,
    archive_filename  TEXT NOT NULL,
    boot_session      TEXT NOT NULL,
    event_idx         INTEGER,
    event_timestamp   TIMESTAMP,
    event_type        TEXT,
    chain             INTEGER,
    frequency_mhz     INTEGER,
    voltage_v         NUMERIC,
    temp_max_c        NUMERIC,
    raw_line          TEXT,
    UNIQUE (archive_filename, boot_session, event_idx)
);

-- ---------------------------------------------------------------------------
-- knowledge.field_log_events — generic parsed event log
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge.field_log_events (
    id                BIGSERIAL PRIMARY KEY,
    archive_filename  TEXT NOT NULL,
    source_file       TEXT NOT NULL,
    event_idx         INTEGER,
    event_timestamp   TIMESTAMP,
    severity          TEXT,
    message           TEXT,
    raw_line          TEXT,
    UNIQUE (archive_filename, source_file, event_idx)
);

-- ---------------------------------------------------------------------------
-- knowledge.field_log_raw_json — raw JSON blob capture (insurance policy)
-- Dedup key: (archive_filename, file_path_in_archive)
-- Note: 002_layer2_and_learning_foundation.sql creates a partitioned variant
--       of this table. Keep these definitions in sync when upgrading.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge.field_log_raw_json (
    id                     BIGSERIAL PRIMARY KEY,
    archive_filename       TEXT NOT NULL,
    file_path_in_archive   TEXT NOT NULL DEFAULT '',
    raw_content            JSONB NOT NULL,
    ingested_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (archive_filename, file_path_in_archive)
);

CREATE UNIQUE INDEX IF NOT EXISTS field_log_raw_json_archive_path_idx
    ON knowledge.field_log_raw_json (archive_filename, file_path_in_archive);

-- ---------------------------------------------------------------------------
-- mg.import_runs — per-batch run tracker (not per-archive; for that use
-- mg.import_runs in 002, which is the richer schema). This is the v2 shape
-- that mg_import.py bootstraps. 002 extends it with per-archive columns.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mg.import_runs (
    id              BIGSERIAL PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    archive_count   INTEGER,
    row_counts      JSONB,
    errors          TEXT[],
    status          TEXT
);

-- ============================================================================
-- End of bootstrap migration.
-- Next: apply 002_layer2_and_learning_foundation.sql for the Layer 2 resolver
-- tables (hardware.model_aliases, mg.model_family_aliases, mg.unresolved_models,
-- mg.unknown_fields, mg.field_promotion_queue, and the partitioned raw_json
-- variants).
-- ============================================================================
