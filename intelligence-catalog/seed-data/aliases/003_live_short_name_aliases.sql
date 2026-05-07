-- 003_live_short_name_aliases.sql — Tier-1 supplement (P-021, 2026-05-07)
--
-- Adds the short model names AMS reports for the BiXBiT USA fleet so the
-- importer's Tier-1 resolver hits on every scan, regardless of whether the
-- frozen-UUID Tier-1 seed (`001_hardware_model_aliases_tier1.sql`) survives
-- the FK gate (which it mostly does not — see B-24 / B-29 / P-019B).
--
-- ============================================================================
-- P-021-fix (2026-05-08) — column-name correction
-- ============================================================================
-- The first P-021 install on the Mini surfaced a schema mismatch: this file
-- was originally written against an imagined schema with `alias_kind` and
-- `source` columns, but the canonical
-- `intelligence-catalog/seed-data/intelligence_catalog_schema.sql:871-898`
-- defines `hardware.model_aliases` with these columns ONLY:
--
--     id, miner_model_id, alias, alias_normalized (NOT NULL),
--     alias_source (NOT NULL DEFAULT 'unknown'), is_common, notes,
--     primary_source_id, created_at, updated_at
--
-- Postinstall logged:
--   psql:.../003_live_short_name_aliases.sql:48: ERROR: column "alias_kind"
--       of relation "model_aliases" does not exist
--   ERROR Tier-1 alias seed supplement failed against
--       mining_guardian_catalog (P-021)
--
-- The whole INSERT failed; zero short-name aliases landed. This rewrite uses
-- only columns that the canonical schema actually defines.
-- ============================================================================
--
-- Why this exists:
--   The 2026-05-07 P-019E install on the Mini surfaced four model names
--   the scanner couldn't resolve via the catalog: `S19JPro`, `S21EXPHyd`,
--   `AH3880`, `S21Imm`. AMS reports these short forms; the catalog stores
--   canonical names like `Antminer S19j Pro`, `Antminer S21 EXP Hydro`,
--   etc. The frozen-UUID Tier-1 seed dropped all of these because its
--   miner_model_id values were generated from a different
--   `seed_miner_models.sql` snapshot than the live install. This file
--   joins on `canonical_name`/`model_number` ILIKE patterns at apply
--   time, so it resolves to whatever UUIDs the live `hardware.miner_models`
--   actually has — no frozen UUIDs, no FK drift.
--
-- Idempotent: ON CONFLICT (miner_model_id, alias) DO NOTHING. Re-running
-- against the same DB is a no-op.
--
-- Each block:
--   - Looks up the live miner_model_id by canonical_name ILIKE pattern
--   - Adds the short alias the scanner sees from AMS
--   - alias_normalized is the lowercased no-spaces form (schema NOT NULL)
--   - alias_source = 'P-021_live_short_name' so this provenance is
--     greppable + the row count is the verification query (see below).

INSERT INTO hardware.model_aliases (miner_model_id, alias, alias_normalized, alias_source, is_common, notes)
SELECT id, 'S19JPro', 's19jpro', 'P-021_live_short_name', TRUE,
       'AMS short name for Antminer S19J Pro (BiXBiT USA fleet)'
FROM hardware.miner_models
WHERE canonical_name ILIKE 'antminer s19j pro%'
   OR canonical_name ILIKE 'antminer s19jpro%'
ON CONFLICT (miner_model_id, alias) DO NOTHING;

INSERT INTO hardware.model_aliases (miner_model_id, alias, alias_normalized, alias_source, is_common, notes)
SELECT id, 'S21EXPHyd', 's21exphyd', 'P-021_live_short_name', TRUE,
       'AMS short name for Antminer S21 EXP Hydro (BiXBiT USA fleet)'
FROM hardware.miner_models
WHERE canonical_name ILIKE 'antminer s21 exp hydro%'
   OR canonical_name ILIKE 'antminer s21e xp hydro%'
   OR canonical_name ILIKE 'antminer s21e-xp-hydro%'
ON CONFLICT (miner_model_id, alias) DO NOTHING;

INSERT INTO hardware.model_aliases (miner_model_id, alias, alias_normalized, alias_source, is_common, notes)
SELECT id, 'S21Imm', 's21imm', 'P-021_live_short_name', TRUE,
       'AMS short name for Antminer S21 Immersion (BiXBiT USA fleet)'
FROM hardware.miner_models
WHERE canonical_name ILIKE 'antminer s21 imm%'
   OR canonical_name ILIKE 'antminer s21-imm%'
   OR canonical_name ILIKE 'antminer s21 immersion%'
ON CONFLICT (miner_model_id, alias) DO NOTHING;

INSERT INTO hardware.model_aliases (miner_model_id, alias, alias_normalized, alias_source, is_common, notes)
SELECT id, 'AH3880', 'ah3880', 'P-021_live_short_name', TRUE,
       'AMS short name for Auradine Teraflux AH3880 (BiXBiT USA fleet)'
FROM hardware.miner_models
WHERE canonical_name ILIKE 'auradine%ah3880%'
   OR canonical_name ILIKE 'teraflux%ah3880%'
   OR canonical_name ILIKE '%ah3880%'
ON CONFLICT (miner_model_id, alias) DO NOTHING;

-- Diagnostic — counts how many short-name aliases this file landed.
DO $$
DECLARE
    short_count INT;
BEGIN
    SELECT COUNT(*) INTO short_count
    FROM hardware.model_aliases
    WHERE alias_source = 'P-021_live_short_name';
    RAISE NOTICE 'P-021 live short-name aliases present: %', short_count;
END$$;
