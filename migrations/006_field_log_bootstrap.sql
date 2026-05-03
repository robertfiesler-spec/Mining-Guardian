-- ============================================================================
-- Mining Guardian — Migration 006 — Field-log + mg.import_runs bootstrap
-- ============================================================================
-- Relocated 2026-05-04 from `mg_import_tool/sql/migrations/000_bootstrap_field_log_tables.sql`
-- into the canonical repo-root `migrations/` directory as part of the D-20
-- importer-payload reconciliation (P-004, PR `mg/v103-d20-importer-payload-reconciliation`).
--
-- WHY THIS LIVES HERE NOW:
--   D-20 (locked 2026-05-03) — the `mg_import_tool/` importer is operator-only
--   forever and is NOT shipped to customer Minis. v1.0.2's `build_pkg.sh`
--   was bundling `mg_import_tool/***` into the .pkg payload AND copying
--   `mg_import_tool/sql/migrations/*.sql` into `<payload>/migrations/` so
--   postinstall.sh `step_apply_migrations` would apply them. That created
--   a cross-directory dependency that pulled an operator-only path into the
--   customer payload — a live D-20 violation.
--
--   v1.0.3 reconciles the violation by:
--     * dropping `mg_import_tool/***` from the .pkg payload rsync include,
--     * dropping the `mg_import_tool/sql/migrations/` rsync into the payload
--       migrations directory,
--     * relocating the runtime-relevant migrations (this file + 007) into
--       the canonical `migrations/` directory under the next free numeric
--       prefixes (006, 007), so the customer payload's migrations come
--       only from the canonical path,
--     * adding a build-time assertion that the assembled payload contains
--       no `mg_import*` files or directories (build_pkg.sh step 4h, exit 43).
--
--   The operator-side copy in `mg_import_tool/sql/migrations/` is INTENTIONALLY
--   retained as the importer's own source of truth: it is what the importer
--   applies on the operator workstation when it bootstraps the catalog DB
--   from a clean state. The two copies stay byte-identical in content under
--   the canonical-shape rule from B-3 (see docs/LATENT_BUGS.md §B-3); the
--   numeric prefix differs because the canonical `migrations/` directory
--   already had 001/003/004/005 occupied by the operational schema chain.
--
-- IDEMPOTENCY:
--   All CREATEs use IF NOT EXISTS; all ALTERs use IF NOT EXISTS. Safe to
--   apply against a database that already has the tables (no-op). Safe to
--   re-apply across installs/re-installs. This contract is the same as
--   the original importer 000 migration and is preserved verbatim below.
--
-- TARGET DATABASE:
--   `mining_guardian` (the operational DB on the customer Mini's
--   `mining-guardian-db` Colima container). NOT `mining_guardian_catalog`
--   — this is the operational DB chain. See `migrations/001_initial_schema.sql`
--   for the same DB's `public.*` operational tables.
--
-- ORDER:
--   006 must apply BEFORE 007 (the layer-2 resolver layer). Lexical apply
--   order in `installer/macos-pkg/scripts/postinstall.sh::step_apply_migrations`
--   delivers that automatically (006 < 007).
--
-- BODY (verbatim from mg_import_tool/sql/migrations/000_bootstrap_field_log_tables.sql
-- — only the file-level introductory comment was rewritten; SQL content is
-- byte-identical with the importer-side original to preserve idempotency):

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
--
-- ⚠ B-3 FIX (PR — this commit) ⚠
-- Earlier revisions of this migration created a NON-partitioned table with
-- columns (archive_filename, file_path_in_archive, raw_content) and a unique
-- constraint on (archive_filename, file_path_in_archive). That shape
-- DISAGREES with the canonical partitioned shape introduced by
-- 002_layer2_and_learning_foundation.sql, which is what the live PC Docker
-- `mining-guardian-db` Postgres has been running for weeks (see
-- docs/LATENT_BUGS.md B-3 and docs/SESSION_LOG_2026-04-27.md addendum #3).
--
-- Applying the old shape on top of the live DB would either fail outright
-- on column mismatch or — worse — succeed against an empty schema and
-- produce a divergent layout. Either is data-corruption-grade.
--
-- This block is now rebased onto the SAME shape as 002, so any operator
-- running migrations in numerical order on a fresh DB lands on the canonical
-- partitioned shape, and any operator running them against a DB that
-- already has 002 applied gets safe no-ops (CREATE TABLE IF NOT EXISTS,
-- CREATE INDEX IF NOT EXISTS).
--
-- Canonical shape (matches 002_layer2_and_learning_foundation.sql §7):
--   columns      : entity_label, archive_filename, source_file, parser,
--                  raw_payload (JSONB), sha256, ingested_at
--   partitioning : PARTITION BY RANGE (ingested_at), quarterly children
--   primary key  : (id, ingested_at)   -- partition-key must be in PK
--   indexes      : (entity_label), (archive_filename), (sha256)
--
-- Note: there is intentionally NO unique constraint on
-- (archive_filename, file_path_in_archive). file_path_in_archive does NOT
-- exist on the canonical shape — see B-5 in docs/LATENT_BUGS.md for the
-- coupled mg_import.py index that was patched out for the same reason.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge.field_log_raw_json (
    id                BIGSERIAL,
    entity_label      TEXT NOT NULL,
    archive_filename  TEXT NOT NULL,
    source_file       TEXT NOT NULL,
    parser            TEXT NOT NULL,
    raw_payload       JSONB NOT NULL,
    sha256            TEXT NOT NULL,
    ingested_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, ingested_at)
) PARTITION BY RANGE (ingested_at);

-- Quarterly partitions — must match 002. Adding partitions here is
-- idempotent (IF NOT EXISTS) so re-running this migration on a DB that
-- already has 002 applied is a no-op.
CREATE TABLE IF NOT EXISTS knowledge.field_log_raw_json_2026_q2
    PARTITION OF knowledge.field_log_raw_json
    FOR VALUES FROM ('2026-04-01') TO ('2026-07-01');
CREATE TABLE IF NOT EXISTS knowledge.field_log_raw_json_2026_q3
    PARTITION OF knowledge.field_log_raw_json
    FOR VALUES FROM ('2026-07-01') TO ('2026-10-01');
CREATE TABLE IF NOT EXISTS knowledge.field_log_raw_json_2026_q4
    PARTITION OF knowledge.field_log_raw_json
    FOR VALUES FROM ('2026-10-01') TO ('2027-01-01');
CREATE TABLE IF NOT EXISTS knowledge.field_log_raw_json_2027_q1
    PARTITION OF knowledge.field_log_raw_json
    FOR VALUES FROM ('2027-01-01') TO ('2027-04-01');

CREATE INDEX IF NOT EXISTS idx_raw_json_entity
    ON knowledge.field_log_raw_json (entity_label);
CREATE INDEX IF NOT EXISTS idx_raw_json_archive
    ON knowledge.field_log_raw_json (archive_filename);
CREATE INDEX IF NOT EXISTS idx_raw_json_sha
    ON knowledge.field_log_raw_json (sha256);

COMMENT ON TABLE knowledge.field_log_raw_json IS
    'Full raw JSON payload of every parsed log file, for re-extraction when '
    'parsers improve. Partitioned quarterly for retention management. '
    'Shape rebased in B-3 fix to match 002_layer2 — see docs/LATENT_BUGS.md.';

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
-- mg.unknown_fields, mg.field_promotion_queue, and additional indexes /
-- foreign keys against the field_log_raw_json table created above).
--
-- Post B-3 fix: 002 is now strictly additive over 000 for field_log_raw_json
-- — the table+partitions+indexes block above is intentionally identical to
-- the corresponding section of 002 so re-running 002 against a DB built from
-- this migration is a clean no-op.
-- ============================================================================
