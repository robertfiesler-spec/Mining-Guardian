-- =============================================================================
-- FIX AND SEED — Run after deploy_schema.sql
-- Fixes: unique constraint, missing manufacturers, then seeds 313 miners
-- =============================================================================

-- Step 1: Add unique constraint on manufacturers.brand so ON CONFLICT works
ALTER TABLE hardware.manufacturers 
  DROP CONSTRAINT IF EXISTS manufacturers_brand_unique;
ALTER TABLE hardware.manufacturers 
  ADD CONSTRAINT manufacturers_brand_unique UNIQUE (brand);

-- Step 2: Add missing enum values
ALTER TYPE public.manufacturer_brand ADD VALUE IF NOT EXISTS 'innosilicon';
ALTER TYPE public.manufacturer_brand ADD VALUE IF NOT EXISTS 'bitdeer';
ALTER TYPE public.manufacturer_brand ADD VALUE IF NOT EXISTS 'kncminer';
ALTER TYPE public.manufacturer_brand ADD VALUE IF NOT EXISTS 'spondoolies';
ALTER TYPE public.manufacturer_brand ADD VALUE IF NOT EXISTS 'butterfly_labs';
ALTER TYPE public.manufacturer_brand ADD VALUE IF NOT EXISTS 'halong';

ALTER TYPE public.process_node ADD VALUE IF NOT EXISTS '3nm';
ALTER TYPE public.process_node ADD VALUE IF NOT EXISTS '4nm';
ALTER TYPE public.process_node ADD VALUE IF NOT EXISTS '55nm';
ALTER TYPE public.process_node ADD VALUE IF NOT EXISTS '65nm';
ALTER TYPE public.process_node ADD VALUE IF NOT EXISTS '110nm';

-- Step 3: Seed knowledge sources (if not already there)
INSERT INTO knowledge.sources (id, source_key, display_name, tier, source_url, description, is_active, trust_score)
VALUES
  ('a0000000-0000-0000-0000-000000000001', 'bitmain_official', 'Bitmain Official', 'tier1_manufacturer', 'https://www.bitmain.com', 'Official Bitmain website and product pages', TRUE, 0.95),
  ('a0000000-0000-0000-0000-000000000002', 'microbt_official', 'MicroBT Official', 'tier1_manufacturer', 'https://www.microbt.com', 'Official MicroBT/Whatsminer website', TRUE, 0.95),
  ('a0000000-0000-0000-0000-000000000003', 'canaan_official', 'Canaan Official', 'tier1_manufacturer', 'https://www.canaan.io', 'Official Canaan/Avalon website', TRUE, 0.95),
  ('a0000000-0000-0000-0000-000000000004', 'auradine_official', 'Auradine Official', 'tier1_manufacturer', 'https://www.auradine.com', 'Official Auradine/Teraflux website', TRUE, 0.95),
  ('a0000000-0000-0000-0000-000000000005', 'bitdeer_official', 'Bitdeer Official', 'tier1_manufacturer', 'https://www.bitdeer.com', 'Official Bitdeer/SealMiner website', TRUE, 0.90),
  ('a0000000-0000-0000-0000-000000000006', 'innosilicon_official', 'Innosilicon Official', 'tier1_manufacturer', 'https://www.innosilicon.com', 'Official Innosilicon website', TRUE, 0.85),
  ('a0000000-0000-0000-0000-000000000007', 'ebang_official', 'Ebang Official', 'tier1_manufacturer', 'https://www.ebang.com.cn', 'Official Ebang website', TRUE, 0.80),
  ('a0000000-0000-0000-0000-000000000008', 'strongu_official', 'StrongU Official', 'tier1_manufacturer', 'https://www.strongu.com.cn', 'Official StrongU website', TRUE, 0.80),
  ('a0000000-0000-0000-0000-000000000009', 'bitfury_official', 'Bitfury Official', 'tier1_manufacturer', 'https://bitfury.com', 'Official Bitfury Group website', TRUE, 0.80),
  ('a0000000-0000-0000-0000-00000000000a', 'asicminervalue', 'ASIC Miner Value', 'tier4_community', 'https://www.asicminervalue.com', 'Community miner profitability and specs database', TRUE, 0.75),
  ('a0000000-0000-0000-0000-00000000000b', 'hashrate_index', 'Hashrate Index', 'tier5_market_external', 'https://hashrateindex.com', 'Luxor hashrate index and machine profitability', TRUE, 0.80),
  ('a0000000-0000-0000-0000-00000000000c', 'dcentral_tech', 'D-Central Technologies', 'tier3_repair_shop', 'https://d-central.tech', 'Canadian repair shop - spec pages and guides', TRUE, 0.75),
  ('a0000000-0000-0000-0000-00000000000d', 'bitcoin_wiki_hardware', 'Bitcoin Wiki Hardware', 'tier4_community', 'https://en.bitcoin.it/wiki/Mining_hardware_comparison', 'Historical hardware comparison table', TRUE, 0.65),
  ('a0000000-0000-0000-0000-00000000000e', 'catalog_research_2026', 'Mining Guardian Catalog Research Apr 2026', 'tier4_community', NULL, 'Compiled research from multiple sources for initial catalog seeding', TRUE, 0.70),
  ('a0000000-0000-0000-0000-00000000000f', 'bobby_operational', 'Bobby Operational Data', 'tier2_operational', NULL, 'Bobby Fiesler verified operational data from BiXBiT fleet', TRUE, 0.95)
ON CONFLICT (source_key) DO NOTHING;

-- Step 4: Seed ALL manufacturers
INSERT INTO hardware.manufacturers (brand, legal_name, common_name, country_of_origin, website_url, is_active, primary_source_id, confidence)
VALUES
  ('bitmain', 'Beijing Bitmain Technologies Ltd.', 'Bitmain', 'CN', 'https://www.bitmain.com', TRUE, 'a0000000-0000-0000-0000-000000000001', 'high'),
  ('microbt', 'Shenzhen MicroBT Electronics Technology Co., Ltd.', 'MicroBT', 'CN', 'https://www.microbt.com', TRUE, 'a0000000-0000-0000-0000-000000000002', 'high'),
  ('canaan', 'Canaan Inc.', 'Canaan', 'CN', 'https://www.canaan.io', TRUE, 'a0000000-0000-0000-0000-000000000003', 'high'),
  ('auradine', 'Auradine Inc.', 'Auradine', 'US', 'https://www.auradine.com', TRUE, 'a0000000-0000-0000-0000-000000000004', 'high'),
  ('bitdeer', 'Bitdeer Technologies Group', 'Bitdeer', 'SG', 'https://www.bitdeer.com', TRUE, 'a0000000-0000-0000-0000-000000000005', 'high'),
  ('innosilicon', 'Innosilicon Technology Ltd.', 'Innosilicon', 'CN', 'https://www.innosilicon.com', FALSE, 'a0000000-0000-0000-0000-000000000006', 'high'),
  ('ebang', 'Ebang International Holdings Inc.', 'Ebang', 'CN', 'https://www.ebang.com.cn', FALSE, 'a0000000-0000-0000-0000-000000000007', 'high'),
  ('strongu', 'StrongU Technology Ltd.', 'StrongU', 'CN', 'https://www.strongu.com.cn', FALSE, 'a0000000-0000-0000-0000-000000000008', 'high'),
  ('bitfury', 'Bitfury Group Ltd.', 'Bitfury', 'NL', 'https://bitfury.com', FALSE, 'a0000000-0000-0000-0000-000000000009', 'high'),
  ('kncminer', 'KnCMiner AB', 'KnCMiner', 'SE', NULL, FALSE, 'a0000000-0000-0000-0000-00000000000d', 'medium'),
  ('spondoolies', 'Spondoolies-Tech Ltd.', 'Spondoolies', 'IL', NULL, FALSE, 'a0000000-0000-0000-0000-00000000000d', 'medium'),
  ('butterfly_labs', 'Butterfly Labs LLC', 'Butterfly Labs', 'US', NULL, FALSE, 'a0000000-0000-0000-0000-00000000000d', 'medium'),
  ('halong', 'Halong Mining', 'Halong Mining', 'CN', NULL, FALSE, 'a0000000-0000-0000-0000-00000000000d', 'medium'),
  ('jasminer', 'Shenzhen Jasminer Technology Co., Ltd.', 'Jasminer', 'CN', NULL, TRUE, 'a0000000-0000-0000-0000-00000000000e', 'medium'),
  ('iceriver', 'ICE River Technology', 'IceRiver', 'CN', NULL, TRUE, 'a0000000-0000-0000-0000-00000000000e', 'medium'),
  ('goldshell', 'Goldshell Technology Co., Ltd.', 'Goldshell', 'CN', NULL, TRUE, 'a0000000-0000-0000-0000-00000000000e', 'medium')
ON CONFLICT (brand) DO UPDATE SET
  legal_name = EXCLUDED.legal_name,
  common_name = EXCLUDED.common_name,
  website_url = EXCLUDED.website_url,
  primary_source_id = EXCLUDED.primary_source_id;

-- Step 5: Seed contributor
INSERT INTO knowledge.contributors (handle, display_name, contributor_type, trust_score, affiliation)
VALUES ('bobby_fiesler', 'Bobby Fiesler', 'bobby_operational', 0.95, 'Mining Guardian / BiXBiT USA')
ON CONFLICT (handle) DO NOTHING;

-- Verify before proceeding
SELECT 'Pre-seed check' AS status,
       (SELECT COUNT(*) FROM hardware.manufacturers) AS manufacturers,
       (SELECT COUNT(*) FROM knowledge.sources) AS sources;
