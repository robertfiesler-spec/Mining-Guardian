-- 003_live_short_name_aliases.sql — Tier-1 supplement (P-021, 2026-05-07)
--
-- Adds the short model names AMS reports for the BiXBiT USA fleet so the
-- importer's Tier-1 resolver hits on every scan, regardless of whether the
-- frozen-UUID Tier-1 seed (`001_hardware_model_aliases_tier1.sql`) survives
-- the FK gate (which it mostly does not — see B-24 / B-29 / P-019B).
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
-- How this differs from the frozen Tier-1 seed:
--   Tier-1 seed (12,840 rows) ships with hard-coded UUIDs in every INSERT
--   and is wrapped in a pg_temp staging shim by postinstall (P-019B).
--   This file is a tiny INSERT … SELECT … FROM hardware.miner_models that
--   resolves IDs at apply time. It's safe to rerun (ON CONFLICT DO
--   NOTHING) and it cannot drift from the live seed because it never
--   bakes in a UUID.
--
-- Scope:
--   Only the BiXBiT USA production fleet's four short names. Other short
--   names a future customer's AMS may emit can be added by appending more
--   rows here, OR by running `catalog_updater.py --add-from-csv` to push
--   the alias into `hardware.model_aliases` directly.
--
-- Idempotent: ON CONFLICT (miner_model_id, alias) DO NOTHING. Re-running
-- against the same DB is a no-op.

-- Each block:
--   - Looks up the live miner_model_id by canonical_name ILIKE pattern
--   - Adds the short alias the scanner sees from AMS
--   - alias_kind=textual_short — distinguishes from full canonical aliases

INSERT INTO hardware.model_aliases (miner_model_id, alias, alias_kind, source, confidence, notes)
SELECT id, 'S19JPro', 'textual_short', 'P-021_live_short_name', 'high',
       'AMS short name for Antminer S19J Pro (BiXBiT USA fleet)'
FROM hardware.miner_models
WHERE canonical_name ILIKE 'antminer s19j pro%'
   OR canonical_name ILIKE 'antminer s19jpro%'
ON CONFLICT (miner_model_id, alias) DO NOTHING;

INSERT INTO hardware.model_aliases (miner_model_id, alias, alias_kind, source, confidence, notes)
SELECT id, 'S21EXPHyd', 'textual_short', 'P-021_live_short_name', 'high',
       'AMS short name for Antminer S21 EXP Hydro (BiXBiT USA fleet)'
FROM hardware.miner_models
WHERE canonical_name ILIKE 'antminer s21 exp hydro%'
   OR canonical_name ILIKE 'antminer s21e xp hydro%'
   OR canonical_name ILIKE 'antminer s21e-xp-hydro%'
ON CONFLICT (miner_model_id, alias) DO NOTHING;

INSERT INTO hardware.model_aliases (miner_model_id, alias, alias_kind, source, confidence, notes)
SELECT id, 'S21Imm', 'textual_short', 'P-021_live_short_name', 'high',
       'AMS short name for Antminer S21 Immersion (BiXBiT USA fleet)'
FROM hardware.miner_models
WHERE canonical_name ILIKE 'antminer s21 imm%'
   OR canonical_name ILIKE 'antminer s21-imm%'
   OR canonical_name ILIKE 'antminer s21 immersion%'
ON CONFLICT (miner_model_id, alias) DO NOTHING;

INSERT INTO hardware.model_aliases (miner_model_id, alias, alias_kind, source, confidence, notes)
SELECT id, 'AH3880', 'textual_short', 'P-021_live_short_name', 'high',
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
    WHERE source = 'P-021_live_short_name';
    RAISE NOTICE 'P-021 live short-name aliases present: %', short_count;
END$$;
