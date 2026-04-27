-- =============================================================================
-- Mining Intelligence Catalog — staging schema
-- =============================================================================
-- Purpose
-- -------
-- The staging schema is the watcher / dual-write intake layer. Watchers and the
-- catalog_updater tool write proposals here FIRST. After validation (manual,
-- automatic, or both) proposals are promoted into hardware.*.
--
-- This is the C1 dual-write half of D-12 (Postgres-as-truth):
--   * Watcher / catalog_updater  →  staging.miner_model_proposals
--                                                 ↓ (promote, after validation)
--                                  →  hardware.miner_models  (truth)
--   * unified_miner_index.json   →  becomes a debug / git-tracked export only
--
-- Design choice: a single proposals table keyed by slug, holding the raw
-- payload as JSONB. We do NOT mirror every column in hardware.miner_models —
-- that would be a maintenance nightmare every time the schema changes. Instead
-- the proposal carries the full JSON shape that catalog_updater already uses,
-- plus metadata (source watcher, timestamp, validation status).
--
-- Promotion is implemented in a separate function (intelligence-catalog/db/
-- dual_writer.py :: promote_validated()) that reads validated proposals and
-- builds the proper hardware.* rows.
--
-- Created: 2026-04-27 (PR #15)
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS staging;

COMMENT ON SCHEMA staging IS
    'Watcher / dual-write intake layer. Proposals land here, are validated, '
    'then promoted to hardware.*. See dual_writer.py for the promotion logic.';

-- ── Validation status enum (created idempotently) ────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'staging_validation_status') THEN
        CREATE TYPE staging.staging_validation_status AS ENUM (
            'pending',     -- just landed, awaiting validation
            'validated',   -- passed all checks, ready to promote
            'promoted',    -- already promoted to hardware.*; kept as audit trail
            'rejected',    -- failed validation; reason in validation_notes
            'superseded'   -- replaced by a newer proposal for the same slug
        );
    END IF;
END$$;

-- ── miner model proposals ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS staging.miner_model_proposals (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slug                TEXT NOT NULL,
    payload             JSONB NOT NULL,
    -- Provenance: which watcher / tool produced this row
    source_tool         TEXT NOT NULL,        -- e.g. 'catalog_updater', 'manufacturer_watcher'
    source_url          TEXT,                 -- if scraped, where from
    source_run_id       UUID,                 -- groups proposals from the same watcher run
    -- Validation lifecycle
    status              staging.staging_validation_status NOT NULL DEFAULT 'pending',
    validation_notes    TEXT,
    validated_at        TIMESTAMPTZ,
    promoted_at         TIMESTAMPTZ,
    promoted_to_id      UUID,                 -- the hardware.miner_models.id row this became
    -- Hash for dedup: same slug + same payload should not create duplicate work
    payload_hash        TEXT NOT NULL,
    -- Bookkeeping
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_mmp_slug       ON staging.miner_model_proposals (slug);
CREATE INDEX IF NOT EXISTS idx_mmp_status     ON staging.miner_model_proposals (status);
CREATE INDEX IF NOT EXISTS idx_mmp_source     ON staging.miner_model_proposals (source_tool);
CREATE INDEX IF NOT EXISTS idx_mmp_run        ON staging.miner_model_proposals (source_run_id);
CREATE INDEX IF NOT EXISTS idx_mmp_created    ON staging.miner_model_proposals (created_at DESC);
-- For "do not re-write the same proposal twice"
CREATE UNIQUE INDEX IF NOT EXISTS idx_mmp_slug_hash_pending
    ON staging.miner_model_proposals (slug, payload_hash)
    WHERE status IN ('pending', 'validated');

-- ── manufacturer proposals (smaller, simpler) ────────────────────────────────
CREATE TABLE IF NOT EXISTS staging.manufacturer_proposals (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    brand               TEXT NOT NULL,        -- raw brand string from watcher (case-insensitive matched at promote time)
    payload             JSONB NOT NULL,
    source_tool         TEXT NOT NULL,
    source_url          TEXT,
    source_run_id       UUID,
    status              staging.staging_validation_status NOT NULL DEFAULT 'pending',
    validation_notes    TEXT,
    validated_at        TIMESTAMPTZ,
    promoted_at         TIMESTAMPTZ,
    promoted_to_id      UUID,
    payload_hash        TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mp_brand     ON staging.manufacturer_proposals (brand);
CREATE INDEX IF NOT EXISTS idx_mp_status    ON staging.manufacturer_proposals (status);
CREATE INDEX IF NOT EXISTS idx_mp_source    ON staging.manufacturer_proposals (source_tool);
CREATE INDEX IF NOT EXISTS idx_mp_run       ON staging.manufacturer_proposals (source_run_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_mp_brand_hash_pending
    ON staging.manufacturer_proposals (brand, payload_hash)
    WHERE status IN ('pending', 'validated');

-- ── alias proposals ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS staging.alias_proposals (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    miner_slug          TEXT NOT NULL,        -- resolved to miner_model_id at promote time
    alias               TEXT NOT NULL,
    alias_source        TEXT NOT NULL DEFAULT 'unknown',
    is_common           BOOLEAN NOT NULL DEFAULT FALSE,
    notes               TEXT,
    source_tool         TEXT NOT NULL,
    source_url          TEXT,
    source_run_id       UUID,
    status              staging.staging_validation_status NOT NULL DEFAULT 'pending',
    validation_notes    TEXT,
    validated_at        TIMESTAMPTZ,
    promoted_at         TIMESTAMPTZ,
    promoted_to_id      UUID,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ap_slug      ON staging.alias_proposals (miner_slug);
CREATE INDEX IF NOT EXISTS idx_ap_status    ON staging.alias_proposals (status);
CREATE INDEX IF NOT EXISTS idx_ap_source    ON staging.alias_proposals (source_tool);
CREATE INDEX IF NOT EXISTS idx_ap_run       ON staging.alias_proposals (source_run_id);
-- A given (slug, alias) pair should only be pending once
CREATE UNIQUE INDEX IF NOT EXISTS idx_ap_slug_alias_pending
    ON staging.alias_proposals (miner_slug, alias)
    WHERE status IN ('pending', 'validated');

-- ── updated_at trigger (re-uses public.set_updated_at from the canonical schema) ─
DROP TRIGGER IF EXISTS trg_mmp_updated_at ON staging.miner_model_proposals;
CREATE TRIGGER trg_mmp_updated_at
    BEFORE UPDATE ON staging.miner_model_proposals
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_mp_updated_at ON staging.manufacturer_proposals;
CREATE TRIGGER trg_mp_updated_at
    BEFORE UPDATE ON staging.manufacturer_proposals
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_ap_updated_at ON staging.alias_proposals;
CREATE TRIGGER trg_ap_updated_at
    BEFORE UPDATE ON staging.alias_proposals
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ── Convenience view: pending work queue ─────────────────────────────────────
CREATE OR REPLACE VIEW staging.pending_proposals AS
SELECT
    'miner_model' AS proposal_type,
    id, slug AS key, source_tool, source_url, status, created_at, validation_notes
FROM staging.miner_model_proposals
WHERE status IN ('pending', 'validated')
UNION ALL
SELECT
    'manufacturer' AS proposal_type,
    id, brand AS key, source_tool, source_url, status, created_at, validation_notes
FROM staging.manufacturer_proposals
WHERE status IN ('pending', 'validated')
UNION ALL
SELECT
    'alias' AS proposal_type,
    id, miner_slug || ' → ' || alias AS key, source_tool, source_url, status, created_at, validation_notes
FROM staging.alias_proposals
WHERE status IN ('pending', 'validated')
ORDER BY created_at DESC;

COMMENT ON VIEW staging.pending_proposals IS
    'Unified work queue across miner_model_proposals, manufacturer_proposals, '
    'and alias_proposals. Used by promote_validated() in dual_writer.py.';
