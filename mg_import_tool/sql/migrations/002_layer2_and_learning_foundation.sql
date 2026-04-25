-- =======================================================================
-- Mining Guardian — Migration 002 (CLEAN rewrite)
-- Layer 2 + Learning Foundation
--
-- Designed against the actual DB schema discovered on 2026-04-22:
--   * hardware.miner_models (317 SHA-256 models, catalog_id integer)
--   * hardware.model_aliases (already exists, UNIQUE(alias_normalized))
--   * hardware.manufacturers (brand enum, common_name)
--   * knowledge.unknown_fields (already exists, rich schema)
--   * knowledge.field_registry, knowledge.field_discovery_log (already exist)
--   * knowledge.field_log_* (v2 tables, 0 rows)
--
-- This migration ADDS:
--   * mg schema (if missing)
--   * mg.model_family_aliases     — Tier-2 resolver: alias -> candidate UUIDs
--   * mg.unresolved_models        — queue of aliases that failed Tier-1 + Tier-2
--   * mg.rma_records              — user-reported failure records (supervised label)
--   * mg.dormant_miners           — miners with no new archive for N days
--   * mg.pool_observations        — per-miner pool observations (many pools by design)
--   * knowledge.field_log_raw_json (partitioned by month, 18-month retention)
--   * 2 new columns on knowledge.field_log_miner_identity:
--       - hardware_revision (extracted V-code like V100, VE50, VK10)
--       - resolved_miner_model_id (Tier-1 or Tier-2 resolved UUID, NULL = unresolved)
--
-- This migration DOES NOT touch:
--   * hardware.miner_models (schema stays as-is)
--   * hardware.model_aliases (we seed rows into existing schema)
--   * knowledge.unknown_fields (we INSERT into existing table via Python)
--
-- Transactional: entire migration wraps in BEGIN/COMMIT.
-- Idempotent: all CREATE statements use IF NOT EXISTS.
-- =======================================================================

BEGIN;

-- ---------------------------------------------------------------
-- 1. mg schema
-- ---------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS mg;
COMMENT ON SCHEMA mg IS 'Mining Guardian pipeline layer: ingest normalization, resolution queues, supervised labels.';

-- ---------------------------------------------------------------
-- 2. mg.model_family_aliases — Tier-2 resolver
--    Used when an alias string (e.g. "S19 Pro", "S19 Pro_V100") maps to
--    multiple candidate miner_models (different hashrate bins).
--    The importer reads this row, then uses observed hashrate to pick
--    the best candidate from candidate_model_ids.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mg.model_family_aliases (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alias                TEXT NOT NULL,
    alias_normalized     TEXT NOT NULL UNIQUE,
    family_key           TEXT NOT NULL,   -- e.g. "S19 Pro", "M30S", "A1246"
    candidate_model_ids  UUID[] NOT NULL, -- >= 2 candidates, each in hardware.miner_models
    notes                JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_family_aliases_normalized_trgm
    ON mg.model_family_aliases USING gin (alias_normalized gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_family_aliases_family_key
    ON mg.model_family_aliases (family_key);

COMMENT ON TABLE mg.model_family_aliases IS
    'Tier-2 resolver: bare aliases that map to multiple candidate miner_models. '
    'The importer uses observed hashrate (avg_gh_ideal) to pick the best candidate.';

-- ---------------------------------------------------------------
-- 3. mg.unresolved_models — queue for aliases that miss BOTH tiers
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mg.unresolved_models (
    id                       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_miner_type           TEXT,
    raw_control_board_version TEXT,
    raw_firmware_version     TEXT,
    archive_filename         TEXT NOT NULL,
    observed_hashrate_gh     TEXT,
    sample_mac_address       TEXT,
    first_seen_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    occurrence_count         BIGINT NOT NULL DEFAULT 1,
    status                   TEXT NOT NULL DEFAULT 'new',  -- new / promoted / ignored
    resolved_to_miner_model_id UUID REFERENCES hardware.miner_models(id),
    reviewer_notes           TEXT,
    metadata                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_unresolved_lookup
    ON mg.unresolved_models (raw_miner_type, raw_control_board_version, archive_filename)
    WHERE status = 'new';
CREATE INDEX IF NOT EXISTS idx_unresolved_status
    ON mg.unresolved_models (status);

COMMENT ON TABLE mg.unresolved_models IS
    'Archive identity strings that matched NEITHER Tier-1 (hardware.model_aliases) '
    'nor Tier-2 (mg.model_family_aliases). Human review promotes them to real aliases.';

-- ---------------------------------------------------------------
-- 4. mg.rma_records — user-reported failure records (supervised label)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mg.rma_records (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    reported_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    miner_model_id        UUID REFERENCES hardware.miner_models(id),
    raw_miner_type        TEXT,
    mac_address           TEXT,
    site_label            TEXT,
    rack_position         TEXT,
    failure_category      TEXT NOT NULL,  -- e.g. 'hashboard', 'psu', 'control_board', 'fan', 'other'
    failure_detail        TEXT,
    symptoms_observed     JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_codes_observed  JSONB NOT NULL DEFAULT '[]'::jsonb,
    first_symptom_at      TIMESTAMPTZ,
    taken_offline_at      TIMESTAMPTZ,
    rma_filed_at          TIMESTAMPTZ,
    outcome               TEXT,           -- 'returned', 'repaired', 'scrapped', 'in_warranty', 'oow'
    parts_replaced        JSONB NOT NULL DEFAULT '[]'::jsonb,
    cost_usd              NUMERIC(10,2),
    reporter              TEXT,
    reporter_notes        TEXT,
    linked_field_log_ids  BIGINT[],
    metadata              JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_rma_model      ON mg.rma_records (miner_model_id);
CREATE INDEX IF NOT EXISTS idx_rma_mac        ON mg.rma_records (mac_address);
CREATE INDEX IF NOT EXISTS idx_rma_reported   ON mg.rma_records (reported_at DESC);
CREATE INDEX IF NOT EXISTS idx_rma_category   ON mg.rma_records (failure_category);

COMMENT ON TABLE mg.rma_records IS
    'User-submitted hardware failure records. Provides supervised labels for '
    'failure signature learning loops.';

-- ---------------------------------------------------------------
-- 5. mg.dormant_miners — miners with no archive in N days
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mg.dormant_miners (
    id                        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mac_address               TEXT,
    miner_model_id            UUID REFERENCES hardware.miner_models(id),
    last_seen_at              TIMESTAMPTZ NOT NULL,
    days_dormant              INTEGER NOT NULL,
    prior_archive_count       INTEGER NOT NULL,
    last_archive_filename     TEXT,
    last_hashrate_gh          TEXT,
    last_site_label           TEXT,
    user_disposition          TEXT,        -- 'retired', 'rma', 'sold', 'offline_maintenance', 'unknown'
    disposition_notes         TEXT,
    resolved_at               TIMESTAMPTZ,
    metadata                  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_dormant_mac  ON mg.dormant_miners (mac_address);
CREATE INDEX IF NOT EXISTS idx_dormant_open ON mg.dormant_miners (id) WHERE resolved_at IS NULL;

COMMENT ON TABLE mg.dormant_miners IS
    'Miners that have not appeared in any archive for >= 30 days AND had >= 3 prior archives. '
    'Reviewer assigns a disposition (retired / RMA / sold / offline).';

-- ---------------------------------------------------------------
-- 6. mg.pool_observations — per-miner pool observations
--    Each miner may be on a different pool by operator design. This table
--    normalizes pool strings seen in logs so Field Intelligence can track
--    pool fleet distribution without duplicating pool.mining_pools.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mg.pool_observations (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mac_address       TEXT,
    archive_filename  TEXT,
    pool_url          TEXT NOT NULL,
    pool_url_norm     TEXT NOT NULL,       -- lowercased, stripped of stratum+tcp://, port
    pool_host         TEXT,
    pool_port         INTEGER,
    worker_name       TEXT,
    priority          INTEGER,              -- 0/1/2 per pool config
    status            TEXT,                 -- 'alive', 'dead'
    observed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    linked_pool_id    UUID REFERENCES pool.mining_pools(id),
    metadata          JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_pool_obs_mac      ON mg.pool_observations (mac_address);
CREATE INDEX IF NOT EXISTS idx_pool_obs_norm     ON mg.pool_observations (pool_url_norm);
CREATE INDEX IF NOT EXISTS idx_pool_obs_linked   ON mg.pool_observations (linked_pool_id);

COMMENT ON TABLE mg.pool_observations IS
    'Raw pool URLs observed per miner per archive. Operators intentionally run '
    'different miners on different pools; this captures the spread without '
    'assuming a single canonical pool per fleet.';

-- ---------------------------------------------------------------
-- 7. knowledge.field_log_raw_json — partitioned by month, 18-mo retention
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge.field_log_raw_json (
    id                BIGSERIAL,
    entity_label      TEXT NOT NULL,
    archive_filename  TEXT NOT NULL,
    source_file       TEXT NOT NULL,
    parser            TEXT NOT NULL,         -- 'whatsminer_api', 'antminer_cgi', 'autotune', ...
    raw_payload       JSONB NOT NULL,
    sha256            TEXT NOT NULL,
    ingested_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, ingested_at)
) PARTITION BY RANGE (ingested_at);

-- Quarterly partitions — mirror knowledge.raw_ingestion_log style
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
    'parsers improve. Partitioned quarterly for retention management.';

-- ---------------------------------------------------------------
-- 8. Extend knowledge.field_log_miner_identity with resolution columns
-- ---------------------------------------------------------------
ALTER TABLE knowledge.field_log_miner_identity
    ADD COLUMN IF NOT EXISTS hardware_revision TEXT;
ALTER TABLE knowledge.field_log_miner_identity
    ADD COLUMN IF NOT EXISTS resolved_miner_model_id UUID REFERENCES hardware.miner_models(id);
ALTER TABLE knowledge.field_log_miner_identity
    ADD COLUMN IF NOT EXISTS resolution_tier TEXT;       -- 'tier1' / 'tier2' / 'unresolved'
ALTER TABLE knowledge.field_log_miner_identity
    ADD COLUMN IF NOT EXISTS resolution_alias TEXT;      -- the alias string that matched

CREATE INDEX IF NOT EXISTS idx_field_log_resolved
    ON knowledge.field_log_miner_identity (resolved_miner_model_id);
CREATE INDEX IF NOT EXISTS idx_field_log_unresolved
    ON knowledge.field_log_miner_identity (id) WHERE resolved_miner_model_id IS NULL;

COMMENT ON COLUMN knowledge.field_log_miner_identity.hardware_revision IS
    'Extracted V-code (V100, VE50, VK10, ...) preserved separately from miner_type.';
COMMENT ON COLUMN knowledge.field_log_miner_identity.resolved_miner_model_id IS
    'UUID of matched hardware.miner_models row. NULL => went to mg.unresolved_models.';

-- ---------------------------------------------------------------
-- 9. Updated-at triggers (reuse existing set_updated_at function)
-- ---------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_family_aliases_updated_at') THEN
        CREATE TRIGGER trg_family_aliases_updated_at
            BEFORE UPDATE ON mg.model_family_aliases
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_unresolved_updated_at') THEN
        CREATE TRIGGER trg_unresolved_updated_at
            BEFORE UPDATE ON mg.unresolved_models
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_rma_updated_at') THEN
        CREATE TRIGGER trg_rma_updated_at
            BEFORE UPDATE ON mg.rma_records
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_dormant_updated_at') THEN
        CREATE TRIGGER trg_dormant_updated_at
            BEFORE UPDATE ON mg.dormant_miners
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END $$;

COMMIT;

-- =======================================================================
-- Post-migration sanity check
-- Run: SELECT * FROM information_schema.tables
--      WHERE table_schema = 'mg' ORDER BY table_name;
-- Expect: model_family_aliases, unresolved_models, rma_records,
--         dormant_miners, pool_observations
-- =======================================================================
