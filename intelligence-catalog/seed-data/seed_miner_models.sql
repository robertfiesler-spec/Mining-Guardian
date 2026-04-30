-- Mining Intelligence Catalog — Seed Data: Bitcoin SHA-256 ASIC Miner Models
-- Generated: 2026-04-11
-- Sources: ASIC Miner Value, Hashrate Index, manufacturer pages, D-Central, BT-Miners, etc.
-- Target: PostgreSQL 16 on ROBS-PC (192.168.188.47)
-- Schema: intelligence_catalog_schema.sql (hardware.miner_models table)
--
-- IMPORTANT: This requires the manufacturer_brand enum to be updated first:
-- ALTER TYPE public.manufacturer_brand ADD VALUE IF NOT EXISTS 'innosilicon';
-- ALTER TYPE public.manufacturer_brand ADD VALUE IF NOT EXISTS 'bitdeer';
-- ALTER TYPE public.manufacturer_brand ADD VALUE IF NOT EXISTS 'kncminer';
-- ALTER TYPE public.manufacturer_brand ADD VALUE IF NOT EXISTS 'spondoolies';
-- ALTER TYPE public.manufacturer_brand ADD VALUE IF NOT EXISTS 'butterfly_labs';
-- ALTER TYPE public.manufacturer_brand ADD VALUE IF NOT EXISTS 'halong';
-- ALTER TYPE public.manufacturer_brand ADD VALUE IF NOT EXISTS 'strongu';
-- ALTER TYPE public.manufacturer_brand ADD VALUE IF NOT EXISTS 'auradine';
-- ALTER TYPE public.manufacturer_brand ADD VALUE IF NOT EXISTS 'ebang';
-- ALTER TYPE public.manufacturer_brand ADD VALUE IF NOT EXISTS 'bitfury';
-- ALTER TYPE public.manufacturer_brand ADD VALUE IF NOT EXISTS 'bitaxe';
--
-- Also requires manufacturer rows in hardware.manufacturers for each brand.
-- Run enum updates and manufacturer inserts before this file.

BEGIN;

-- Manufacturer reference inserts (idempotent)
INSERT INTO hardware.manufacturers (brand, full_name, country, website, notes)
VALUES
  ('innosilicon', 'Innosilicon Technology', 'CN', 'https://www.innosilicon.com', 'SHA-256 T2/T3 series'),
  ('bitdeer', 'Bitdeer Technologies Group', 'SG', 'https://www.bitdeer.com', 'SealMiner A-series, SEAL01/SEAL02 chips'),
  ('kncminer', 'KnCMiner AB', 'SE', NULL, 'Defunct 2016 — Neptune, Titan, Solar series'),
  ('spondoolies', 'Spondoolies-Tech', 'IL', NULL, 'Defunct 2016 — SP20, SP31, SP35'),
  ('butterfly_labs', 'Butterfly Labs', 'US', NULL, 'Defunct/sued by FTC — Jalapeno, Monarch'),
  ('halong', 'Halong Mining', 'CN', NULL, 'DragonMint T1 (2018), company went silent'),
  ('strongu', 'StrongU Technologies', 'CN', 'https://www.strongu.com.cn', 'STU-U series, Hornbill H-series'),
  ('auradine', 'Auradine Inc', 'US', 'https://www.auradine.com', 'Teraflux AT/AH/AI series'),
  ('ebang', 'Ebang International Holdings', 'CN', 'https://www.ebang.com.cn', 'Ebit E-series'),
  ('bitfury', 'Bitfury Group', 'NL', 'https://bitfury.com', 'B8 and Tardis enterprise miners'),
  ('bitaxe', 'Open Source Miners United / Bitaxe', 'US', 'https://bitaxe.org', 'Open-source SHA-256 ASIC miner family. BM1366/BM1368/BM1370 chips sourced from Bitmain S19 XP / S21 / S21 Pro hashboards.')
ON CONFLICT (brand) DO NOTHING;

INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S1', 'S1', 'S1-S5 Legacy',
    'air'::public.cooling_type, 4, 0.18, 360, 2000.0,
    'SHA-256', '2013-01-01', FALSE, TRUE,
    'First-gen Antminer. 55nm chip.', '{"asic_chip": "BM1380", "process_node": "55nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S2', 'S2', 'S1-S5 Legacy',
    'air'::public.cooling_type, 3, 1.0, 1000, 1000.0,
    'SHA-256', '2014-01-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1382", "process_node": "55nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S3', 'S3', 'S1-S5 Legacy',
    'air'::public.cooling_type, 3, 0.478, 366, 765.6904,
    'SHA-256', '2014-01-01', FALSE, TRUE,
    '478 GH/s', '{"asic_chip": "BM1382", "process_node": "55nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S4', 'S4', 'S1-S5 Legacy',
    'air'::public.cooling_type, 4, 2.0, 1400, 700.0,
    'SHA-256', '2014-01-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1384", "process_node": "28nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S5', 'S5', 'S1-S5 Legacy',
    'air'::public.cooling_type, 1, 1.155, 590, 510.8225,
    'SHA-256', '2014-12-01', FALSE, TRUE,
    'ASIC Miner Value: 1.2 TH/s @ 590W listed (slight rounding variant). Noise 65dB.', '{"asic_chip": "BM1384", "process_node": "28nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s5"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S5+', 'S5+', 'S1-S5 Legacy',
    'air'::public.cooling_type, 4, 7.722, 3150, 407.9254,
    'SHA-256', '2016-06-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1384", "process_node": "28nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S7', 'S7', 'S7 Series',
    'air'::public.cooling_type, 3, 4.73, 1293, 273.3615,
    'SHA-256', '2015-08-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1385", "process_node": "28nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S7-LN', 'S7-LN', 'S7 Series',
    'air'::public.cooling_type, 3, 2.7, 697, 258.1481,
    'SHA-256', '2016-06-01', FALSE, TRUE,
    'Low-noise variant of S7. Noise 48dB.', '{"asic_chip": "BM1385", "process_node": "28nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s7-ln"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S9 (11.5 TH)', 'S9', 'S9 Series',
    'air'::public.cooling_type, 3, 11.5, 1127, 98.0,
    'SHA-256', '2016-06-01', FALSE, TRUE,
    'Noise 85dB.', '{"asic_chip": "BM1387", "process_node": "16nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s9-11-5th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S9 (12.5 TH)', 'S9', 'S9 Series',
    'air'::public.cooling_type, 3, 12.5, 1225, 98.0,
    'SHA-256', '2017-02-01', FALSE, TRUE,
    'Noise 85dB.', '{"asic_chip": "BM1387", "process_node": "16nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s9-12-5th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S9 (13.0 TH)', 'S9', 'S9 Series',
    'air'::public.cooling_type, 3, 13.0, 1274, 98.0,
    'SHA-256', '2017-08-01', FALSE, TRUE,
    'ASIC Miner Value lists 13TH @ 1300W (100 J/TH) for some batches. Noise 85dB.', '{"asic_chip": "BM1387", "process_node": "16nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s9-13th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S9 (13.5 TH)', 'S9', 'S9 Series',
    'air'::public.cooling_type, 3, 13.5, 1323, 98.0,
    'SHA-256', '2017-09-01', FALSE, TRUE,
    'Noise 85dB.', '{"asic_chip": "BM1387", "process_node": "16nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s9-13-5th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S9 (14.0 TH)', 'S9', 'S9 Series',
    'air'::public.cooling_type, 3, 14.0, 1372, 98.0,
    'SHA-256', '2017-11-01', FALSE, TRUE,
    'Noise 85dB.', '{"asic_chip": "BM1387", "process_node": "16nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s9-14th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S9i (13.0 TH)', 'S9i', 'S9 Series',
    'air'::public.cooling_type, 3, 13.0, 1280, 98.4615,
    'SHA-256', '2018-05-01', FALSE, TRUE,
    'ASIC Miner Value: 13TH @ 1290W listed. Noise 76dB.', '{"asic_chip": "BM1387", "process_node": "16nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/sha-256"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S9i (13.5 TH)', 'S9i', 'S9 Series',
    'air'::public.cooling_type, 3, 13.5, 1310, 97.037,
    'SHA-256', '2018-05-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1387", "process_node": "16nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S9i (14.0 TH)', 'S9i', 'S9 Series',
    'air'::public.cooling_type, 3, 14.0, 1320, 94.2857,
    'SHA-256', '2018-05-01', FALSE, TRUE,
    'ASIC Miner Value: 14TH @ 1320W, 94.29 J/TH. Noise 76dB.', '{"asic_chip": "BM1387", "process_node": "16nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s9i-14th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S9i (14.5 TH)', 'S9i', 'S9 Series',
    'air'::public.cooling_type, 3, 14.5, 1365, 94.1379,
    'SHA-256', '2018-05-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1387", "process_node": "16nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S9j (14.0 TH)', 'S9j', 'S9 Series',
    'air'::public.cooling_type, 3, 14.0, 1314, 93.8571,
    'SHA-256', '2018-08-01', FALSE, TRUE,
    'j = bin-selected variant with BM1387BE/BF chips.', '{"asic_chip": "BM1387BE/BF", "process_node": "16nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S9j (14.5 TH)', 'S9j', 'S9 Series',
    'air'::public.cooling_type, 3, 14.5, 1350, 93.1034,
    'SHA-256', '2018-08-01', FALSE, TRUE,
    'Noise 76dB.', '{"asic_chip": "BM1387BE/BF", "process_node": "16nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s9j-14-5th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S9 Hydro', 'S9 Hydro', 'S9 Series',
    'hydro'::public.cooling_type, 4, 18.0, 1728, 96.0,
    'SHA-256', '2018-08-01', FALSE, TRUE,
    'Water-cooled variant. 4 hashboards.', '{"asic_chip": "BM1387", "process_node": "16nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s9-hydro-18th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S9k (13.5 TH)', 'S9k', 'S9 Series',
    'air'::public.cooling_type, 3, 13.5, 1148, 85.037,
    'SHA-256', '2019-08-01', FALSE, TRUE,
    'ASIC Miner Value: 13.5TH @ 1310W (97.04 J/TH) listed. Noise 76dB.', '{"asic_chip": "BM1393B", "process_node": "16nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s9k-13-5th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S9 SE (16 TH)', 'S9 SE', 'S9 Series',
    'air'::public.cooling_type, 3, 16.0, 1280, 80.0,
    'SHA-256', '2019-07-01', FALSE, TRUE,
    'Noise 76dB.', '{"asic_chip": "BM1393CE", "process_node": "16nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s9-se-16th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer R4', 'R4', 'R4 Series',
    'air'::public.cooling_type, 3, 8.7, 845, 97.1264,
    'SHA-256', '2017-02-01', FALSE, TRUE,
    'Home/quiet miner. Noise 52dB.', '{"asic_chip": "BM1387B/BL", "process_node": "16nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/scc-siaclassic"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S11 (20.5 TH)', 'S11', 'S11 Series',
    'air'::public.cooling_type, 3, 20.5, 1530, 74.6341,
    'SHA-256', '2018-11-01', FALSE, TRUE,
    'Noise 76dB.', '{"asic_chip": "BM1387", "process_node": "16nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s11-20-5th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer T9 (11.5 TH)', 'T9', 'T9 Series',
    'air'::public.cooling_type, 3, 11.5, 1450, 126.087,
    'SHA-256', '2017-04-01', FALSE, TRUE,
    'ASIC Miner Value: 11.5TH @ 1450W (126.09 J/TH). Noise 68dB.', '{"asic_chip": "BM1387", "process_node": "16nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-t9-11-5th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer T9 (12.5 TH)', 'T9', 'T9 Series',
    'air'::public.cooling_type, 3, 12.5, 1576, 126.08,
    'SHA-256', '2017-08-01', FALSE, TRUE,
    'Noise 68dB.', '{"asic_chip": "BM1387", "process_node": "16nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-t9-12-5th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer T9+ (10.5 TH)', 'T9+', 'T9 Series',
    'air'::public.cooling_type, 3, 10.5, 1432, 136.381,
    'SHA-256', '2018-01-01', FALSE, TRUE,
    'Noise 76dB.', '{"asic_chip": "BM1387", "process_node": "16nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-t9-10-5th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S15 (28 TH)', 'S15', 'S15/T15 Series',
    'air'::public.cooling_type, 4, 28.0, 1596, 57.0,
    'SHA-256', '2018-12-01', FALSE, TRUE,
    'HP mode: 28TH/1596W; LP mode: 17TH/850W (50 J/TH). Noise 76dB.', '{"asic_chip": "BM1391AE", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s15-28th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer T15 (23 TH)', 'T15', 'S15/T15 Series',
    'air'::public.cooling_type, 3, 23.0, 1541, 67.0,
    'SHA-256', '2018-12-01', FALSE, TRUE,
    'HP mode: 23TH/1541W; LP mode: 20TH/1200W (60 J/TH). Noise 75dB.', '{"asic_chip": "BM1391AE", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-t15-23th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S17 (53 TH)', 'S17', 'S17/T17 Series',
    'air'::public.cooling_type, 3, 53.0, 2385, 45.0,
    'SHA-256', '2019-04-01', FALSE, TRUE,
    'ASIC Miner Value: 53TH @ 2385W (45 J/TH). Noise 82dB.', '{"asic_chip": "BM1397AD/AI", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s17-53th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S17 (56 TH)', 'S17', 'S17/T17 Series',
    'air'::public.cooling_type, 3, 56.0, 2520, 45.0,
    'SHA-256', '2019-04-01', FALSE, TRUE,
    'ASIC Miner Value: 56TH @ 2520W (45 J/TH). Noise 82dB.', '{"asic_chip": "BM1397AD/AI", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s17-56th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S17 Pro (50 TH)', 'S17 Pro', 'S17/T17 Series',
    'air'::public.cooling_type, 3, 50.0, 1975, 39.5,
    'SHA-256', '2019-04-01', FALSE, TRUE,
    'Noise 82dB.', '{"asic_chip": "BM1397AD/AI", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s17-pro-50th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S17 Pro (53 TH)', 'S17 Pro', 'S17/T17 Series',
    'air'::public.cooling_type, 3, 53.0, 2094, 39.5094,
    'SHA-256', '2019-04-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1397AD/AI", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S17 Pro (56 TH)', 'S17 Pro', 'S17/T17 Series',
    'air'::public.cooling_type, 3, 56.0, 2212, 39.5,
    'SHA-256', '2019-04-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1397AD/AI", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S17e (64 TH)', 'S17e', 'S17/T17 Series',
    'air'::public.cooling_type, 3, 64.0, 2880, 45.0,
    'SHA-256', '2019-11-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "BM1396AB", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s17e-64th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S17+ (73 TH)', 'S17+', 'S17/T17 Series',
    'air'::public.cooling_type, 3, 73.0, 2920, 40.0,
    'SHA-256', '2019-12-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "BM1397AF/AH", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s17-73th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer T17 (40 TH)', 'T17', 'S17/T17 Series',
    'air'::public.cooling_type, 3, 40.0, 2200, 55.0,
    'SHA-256', '2019-04-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "BM1397AD/AI", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-t17-40th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer T17e (53 TH)', 'T17e', 'S17/T17 Series',
    'air'::public.cooling_type, 3, 53.0, 2915, 55.0,
    'SHA-256', '2019-11-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "BM1396AB", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-t17e-53th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer T17+ (58 TH)', 'T17+', 'S17/T17 Series',
    'air'::public.cooling_type, 3, 58.0, 2920, 50.3448,
    'SHA-256', '2019-12-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1397AG/AH", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer T17+ (61 TH)', 'T17+', 'S17/T17 Series',
    'air'::public.cooling_type, 3, 61.0, 3050, 50.0,
    'SHA-256', '2019-12-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1397AG/AH", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer T17+ (64 TH)', 'T17+', 'S17/T17 Series',
    'air'::public.cooling_type, 3, 64.0, 3200, 50.0,
    'SHA-256', '2019-12-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "BM1397AG/AH", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-t17-64th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19 (84 TH)', 'S19', 'S19 Series',
    'air'::public.cooling_type, 3, 84.0, 2478, 29.5,
    'SHA-256', '2020-05-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1398BB", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19 (90 TH)', 'S19', 'S19 Series',
    'air'::public.cooling_type, 3, 90.0, 2655, 29.5,
    'SHA-256', '2020-05-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1398BB", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19 (95 TH)', 'S19', 'S19 Series',
    'air'::public.cooling_type, 3, 95.0, 3250, 34.2105,
    'SHA-256', '2020-05-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "BM1398BB", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s19-95th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19 Pro (100 TH)', 'S19 Pro', 'S19 Series',
    'air'::public.cooling_type, 3, 100.0, 2950, 29.5,
    'SHA-256', '2020-05-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1398BB", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19 Pro (105 TH)', 'S19 Pro', 'S19 Series',
    'air'::public.cooling_type, 3, 105.0, 3098, 29.5048,
    'SHA-256', '2020-05-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1398BB", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19 Pro (110 TH)', 'S19 Pro', 'S19 Series',
    'air'::public.cooling_type, 3, 110.0, 3250, 29.5455,
    'SHA-256', '2020-05-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "BM1398BB", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s19-pro-110th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer T19 (84 TH)', 'T19', 'S19 Series',
    'air'::public.cooling_type, 3, 84.0, 3150, 37.5,
    'SHA-256', '2020-06-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "BM1398BB", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-t19-84th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer T19 (88 TH)', 'T19', 'S19 Series',
    'air'::public.cooling_type, 3, 88.0, 3344, 38.0,
    'SHA-256', '2021-08-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "BM1398BB", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-t19-88th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19j (90 TH)', 'S19j', 'S19 Series',
    'air'::public.cooling_type, 3, 90.0, 3250, 36.1111,
    'SHA-256', '2021-06-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "BM1362AA/AJ", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s19j-90th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19a (90 TH)', 'S19a', 'S19 Series',
    'air'::public.cooling_type, 3, 90.0, 3250, 36.1111,
    'SHA-256', '2021-08-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1398AC", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19j Pro (84 TH)', 'S19j Pro', 'S19 Series',
    'air'::public.cooling_type, 3, 84.0, 2478, 29.5,
    'SHA-256', '2021-08-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1362AA/AJ", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19j Pro (88 TH)', 'S19j Pro', 'S19 Series',
    'air'::public.cooling_type, 3, 88.0, 2596, 29.5,
    'SHA-256', '2021-08-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1362AA/AJ", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19j Pro (92 TH)', 'S19j Pro', 'S19 Series',
    'air'::public.cooling_type, 3, 92.0, 2714, 29.5,
    'SHA-256', '2021-08-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1362AA/AJ", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19j Pro (96 TH)', 'S19j Pro', 'S19 Series',
    'air'::public.cooling_type, 3, 96.0, 2832, 29.5,
    'SHA-256', '2021-08-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "BM1362AA/AJ", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s19j-pro-96th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19j Pro (100 TH)', 'S19j Pro', 'S19 Series',
    'air'::public.cooling_type, 3, 100.0, 3050, 30.5,
    'SHA-256', '2021-06-01', FALSE, TRUE,
    'ASIC Miner Value: 100TH @ 3050W (30.5 J/TH). Noise 75dB.', '{"asic_chip": "BM1362AA/AJ", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s19j-pro-100th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19j Pro (104 TH)', 'S19j Pro', 'S19 Series',
    'air'::public.cooling_type, 3, 104.0, 3068, 29.5,
    'SHA-256', '2021-07-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "BM1362AA/AJ", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s19j-pro-104th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19a Pro (104 TH)', 'S19a Pro', 'S19 Series',
    'air'::public.cooling_type, 3, 104.0, 3068, 29.5,
    'SHA-256', '2021-08-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1398AD", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19al (90 TH)', 'S19al', 'S19 Series',
    'air'::public.cooling_type, 3, 90.0, 3250, 36.1111,
    'SHA-256', '2021-01-01', FALSE, TRUE,
    'al = alternative/low-cost binning.', '{"asic_chip": "BM1362AJ", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19i (90 TH)', 'S19i', 'S19 Series',
    'air'::public.cooling_type, 3, 90.0, 2970, 33.0,
    'SHA-256', '2021-01-01', FALSE, TRUE,
    'i = improved; uses BM1360BB chip.', '{"asic_chip": "BM1360BB", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19 Pro+ (120 TH)', 'S19 Pro+', 'S19 Series',
    'air'::public.cooling_type, 3, 120.0, 3360, 28.0,
    'SHA-256', '2022-04-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1362AK", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19 XP (134 TH)', 'S19 XP', 'S19 XP Series',
    'air'::public.cooling_type, 3, 134.0, 2882, 21.5075,
    'SHA-256', '2022-07-01', FALSE, TRUE,
    'First 5nm air-cooled Antminer.', '{"asic_chip": "BM1366AL/AG", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19 XP (140 TH)', 'S19 XP', 'S19 XP Series',
    'air'::public.cooling_type, 3, 140.0, 3010, 21.5,
    'SHA-256', '2022-07-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "BM1366AL/AG", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s19-xp-140th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19j Pro+ (109 TH)', 'S19j Pro+', 'S19 Series',
    'air'::public.cooling_type, 3, 109.0, 2998, 27.5046,
    'SHA-256', '2022-12-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1362BD", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19j Pro+ (113 TH)', 'S19j Pro+', 'S19 Series',
    'air'::public.cooling_type, 3, 113.0, 3108, 27.5044,
    'SHA-256', '2022-12-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1362BD", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19j Pro+ (117 TH)', 'S19j Pro+', 'S19 Series',
    'air'::public.cooling_type, 3, 117.0, 3218, 27.5043,
    'SHA-256', '2022-12-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1362BD", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19j Pro+ (120 TH)', 'S19j Pro+', 'S19 Series',
    'air'::public.cooling_type, 3, 120.0, 3300, 27.5,
    'SHA-256', '2022-12-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1362BD", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19j Pro++ (122 TH)', 'S19j Pro++', 'S19 Series',
    'air'::public.cooling_type, 3, 122.0, 3355, 27.5,
    'SHA-256', '2022-12-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "BM1362BD", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s19j-pro-122th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19k Pro (120 TH)', 'S19k Pro', 'S19 Series',
    'air'::public.cooling_type, 3, 120.0, 2760, 23.0,
    'SHA-256', '2023-10-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "BM1366BS/BP/AH", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s19k-pro-120th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19j XP (151 TH)', 'S19j XP', 'S19 XP Series',
    'air'::public.cooling_type, 3, 151.0, 3247, 21.5033,
    'SHA-256', '2023-06-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "BM1366AL/AG", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s19j-xp-151th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19 Pro++ (115 TH)', 'S19 Pro++', 'S19 Series',
    'air'::public.cooling_type, 3, 115.0, 2990, 26.0,
    'SHA-256', '2024-08-01', FALSE, TRUE,
    '2024 refresh using BM1366 in older S19 chassis.', '{"asic_chip": "BM1366", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19 Pro++ (120 TH)', 'S19 Pro++', 'S19 Series',
    'air'::public.cooling_type, 3, 120.0, 3120, 26.0,
    'SHA-256', '2024-08-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1366", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19 Pro++ (125 TH)', 'S19 Pro++', 'S19 Series',
    'air'::public.cooling_type, 3, 125.0, 3250, 26.0,
    'SHA-256', '2024-08-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "BM1366", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s19-pro-plus-plus"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19 Pro-A (100 TH)', 'S19 Pro-A', 'S19 Series',
    'air'::public.cooling_type, 3, 100.0, 2950, 29.5,
    'SHA-256', '2024-10-01', FALSE, TRUE,
    'Regional/batch variant.', '{"asic_chip": "BM1398AD", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19 Pro+ Hydro (198 TH)', 'S19 Pro+ Hydro', 'S19 Series',
    'hydro'::public.cooling_type, 3, 198.0, 5445, 27.5,
    'SHA-256', '2022-05-01', FALSE, TRUE,
    'Noise 50dB.', '{"asic_chip": "BM1362AK/AI", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s19-pro-hyd-198th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19 Hydro (158 TH)', 'S19 Hydro', 'S19 Series',
    'hydro'::public.cooling_type, 3, 158.0, 5451, 34.5,
    'SHA-256', '2022-10-01', FALSE, TRUE,
    'Noise 50dB.', '{"asic_chip": "BM1398BB", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s19-hydro-158th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer T19 Hydro (145 TH)', 'T19 Hydro', 'S19 Series',
    'hydro'::public.cooling_type, 3, 145.0, 5438, 37.5034,
    'SHA-256', '2022-10-01', FALSE, TRUE,
    'Noise 50dB.', '{"asic_chip": "BM1398BB", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-t19-hydro-145th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19 XP Hydro (255 TH)', 'S19 XP Hydro', 'S19 XP Series',
    'hydro'::public.cooling_type, 3, 255.0, 5304, 20.8,
    'SHA-256', '2022-10-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1366AL/AG", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19 XP Hydro (257 TH)', 'S19 XP Hydro', 'S19 XP Series',
    'hydro'::public.cooling_type, 3, 257.0, 5346, 20.8016,
    'SHA-256', '2024-01-01', FALSE, TRUE,
    'Noise 50dB.', '{"asic_chip": "BM1366AL/AG", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s19-xp-hyd-257th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19 Pro+ Hyd (191 TH)', 'S19 Pro+ Hyd', 'S19 Series',
    'hydro'::public.cooling_type, 3, 191.0, 5252, 27.4974,
    'SHA-256', '2024-01-01', FALSE, TRUE,
    '', '{"asic_chip": "BM1362AK", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19 XP Hydro (512 TH)', 'S19 XP Hydro', 'S19 XP Series',
    'hydro'::public.cooling_type, 3, 512.0, 10600, 20.7031,
    'SHA-256', '2025-01-01', FALSE, TRUE,
    'Rack-scale dual-unit config. Noise 50dB.', '{"asic_chip": "BM1366AL/AG", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s219-xp-hydro-512th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19 XP+ Hyd (279 TH)', 'S19 XP+ Hyd', 'S19 XP Series',
    'hydro'::public.cooling_type, 3, 279.0, 5301, 19.0,
    'SHA-256', '2025-01-01', FALSE, TRUE,
    'Noise 50dB.', '{"asic_chip": "BM1366AL/AG", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s19-xp-plus-hyd-279th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19 XP+ Hyd (293 TH)', 'S19 XP+ Hyd', 'S19 XP Series',
    'hydro'::public.cooling_type, 3, 293.0, 5567, 19.0,
    'SHA-256', '2025-04-01', FALSE, TRUE,
    'Noise 50dB.', '{"asic_chip": "BM1366AL/AG", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s19-xp-plus-hyd-293th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19 Pro Hyd (177 TH)', 'S19 Pro Hyd', 'S19 Series',
    'hydro'::public.cooling_type, 3, 177.0, 5221, 29.4972,
    'SHA-256', '2023-01-01', FALSE, TRUE,
    'Noise 50dB.', '{"asic_chip": "BM1398BB", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s19-pro-hyd-177th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer T19 Pro Hyd (235 TH)', 'T19 Pro Hyd', 'S19 Series',
    'hydro'::public.cooling_type, 3, 235.0, 5170, 22.0,
    'SHA-256', '2024-02-01', FALSE, TRUE,
    'Noise 30dB.', '{"asic_chip": "BM1398BB", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-t19-pro-hyd-235th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S19 Hydro (158 TH) [T19 variant]', 'T19 Hydro', 'S19 Series',
    'hydro'::public.cooling_type, 3, 158.0, 5451, 34.5,
    'SHA-256', '2022-10-01', FALSE, TRUE,
    'Note: ASIC Miner Value lists T19 Hydro 158TH as separate from S19 Hydro 158TH (different model label, same specs).', '{"asic_chip": "BM1398BB", "process_node": "7nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-t19-hydro-158th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S21 (200 TH)', 'S21', 'S21 Series',
    'air'::public.cooling_type, 3, 200.0, 3550, 17.75,
    'SHA-256', '2024-02-01', TRUE, FALSE,
    'ASIC Miner Value: 200TH @ 3550W (17.75 J/TH). Deep dive: 3500W. Noise 75dB.', '{"asic_chip": "BM1368PA/PB", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s21-200th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S21 Pro (234 TH)', 'S21 Pro', 'S21 Series',
    'air'::public.cooling_type, 3, 234.0, 3510, 15.0,
    'SHA-256', '2024-07-01', TRUE, FALSE,
    'Noise 75dB.', '{"asic_chip": "BM1370BC/AA", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s21-pro-234th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S21 Pro (245 TH)', 'S21 Pro', 'S21 Series',
    'air'::public.cooling_type, 3, 245.0, 3675, 15.0,
    'SHA-256', '2025-11-01', TRUE, FALSE,
    'Noise 75dB.', '{"asic_chip": "BM1370BC/AA", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s21-pro-245th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S21 XP (270 TH)', 'S21 XP', 'S21 Series',
    'air'::public.cooling_type, 3, 270.0, 3645, 13.5,
    'SHA-256', '2024-09-01', TRUE, FALSE,
    'Noise 75dB.', '{"asic_chip": "BM1370BC/AA", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antmine-s21-xp-270th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer T21 (190 TH — NEM)', 'T21', 'S21 Series',
    'air'::public.cooling_type, 3, 190.0, 3610, 19.0,
    'SHA-256', '2024-02-01', TRUE, FALSE,
    'Normal Energy Mode (NEM). Noise 75dB.', '{"asic_chip": "BM1368PA/PB", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-t21-190th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer T21 (180 TH)', 'T21', 'S21 Series',
    'air'::public.cooling_type, 3, 180.0, 3420, 19.0,
    'SHA-256', '2024-04-01', TRUE, FALSE,
    'Noise 55dB.', '{"asic_chip": "BM1368PA/PB", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-t21-180th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer T21 (233 TH — HEM)', 'T21', 'S21 Series',
    'air'::public.cooling_type, 3, 233.0, 5126, 22.0,
    'SHA-256', '2024-02-01', TRUE, FALSE,
    'High Energy Mode (HEM). Same hardware as NEM but different firmware config.', '{"asic_chip": "BM1368PA/PB", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S21+ (216 TH)', 'S21+', 'S21 Series',
    'air'::public.cooling_type, 3, 216.0, 3564, 16.5,
    'SHA-256', '2025-02-01', TRUE, FALSE,
    'Noise 75dB.', '{"asic_chip": "BM1368PA/PB", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s21-plus-216th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S21+ (225 TH)', 'S21+', 'S21 Series',
    'air'::public.cooling_type, 3, 225.0, 3712, 16.4978,
    'SHA-256', '2025-06-01', TRUE, FALSE,
    'Noise 75dB.', '{"asic_chip": "BM1368PA/PB", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s21-plus-225th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S21+ (235 TH)', 'S21+', 'S21 Series',
    'air'::public.cooling_type, 3, 235.0, 3877, 16.4979,
    'SHA-256', '2025-06-01', TRUE, FALSE,
    'Noise 75dB.', '{"asic_chip": "BM1368PA/PB", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s21-plus-235th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S21 XP Immersion (300 TH)', 'S21 XP Immersion', 'S21 Series',
    'immersion'::public.cooling_type, 3, 300.0, 4050, 13.5,
    'SHA-256', '2024-09-01', TRUE, FALSE,
    'Noise 50dB.', '{"asic_chip": "BM1370BC/AA", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s21-xp-immersion-300th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S21 Hyd (335 TH)', 'S21 Hyd', 'S21 Series',
    'hydro'::public.cooling_type, 3, 335.0, 5360, 16.0,
    'SHA-256', '2024-02-01', TRUE, FALSE,
    'Noise 50dB.', '{"asic_chip": "BM1368PA/PB", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s21-hyd-335th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S21+ Hyd (335 TH)', 'S21+ Hyd', 'S21 Series',
    'hydro'::public.cooling_type, 3, 335.0, 5360, 16.0,
    'SHA-256', '2024-03-01', TRUE, FALSE,
    'Revised hydro variant of S21 Hyd.', '{"asic_chip": "BM1368PA/PB", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S21+ Hyd (319 TH)', 'S21+ Hyd', 'S21 Series',
    'hydro'::public.cooling_type, 3, 319.0, 4785, 15.0,
    'SHA-256', '2025-02-01', TRUE, FALSE,
    'Noise 50dB.', '{"asic_chip": "BM1368PA/PB", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s21-plus-hyd-319th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S21+ Hyd (358 TH)', 'S21+ Hyd', 'S21 Series',
    'hydro'::public.cooling_type, 3, 358.0, 5370, 15.0,
    'SHA-256', '2025-08-01', TRUE, FALSE,
    'Noise 50dB.', '{"asic_chip": "BM1368PA/PB", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s21-plus-hyd-358th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S21 XP Hyd (473 TH)', 'S21 XP Hyd', 'S21 Series',
    'hydro'::public.cooling_type, 3, 473.0, 5676, 12.0,
    'SHA-256', '2024-10-01', TRUE, FALSE,
    'Noise 50dB.', '{"asic_chip": "BM1370BC/AA", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s21-xp-hyd-473th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S21 XP+ Hyd (500 TH)', 'S21 XP+ Hyd', 'S21 Series',
    'hydro'::public.cooling_type, 3, 500.0, 5500, 11.0,
    'SHA-256', '2025-07-01', TRUE, FALSE,
    'Noise 50dB.', '{"asic_chip": "BM1370BC/AA", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s21-xp-plus-hyd-500th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S21e XP Hyd (430 TH)', 'S21e XP Hyd', 'S21 Series',
    'hydro'::public.cooling_type, 3, 430.0, 5590, 13.0,
    'SHA-256', '2024-11-01', TRUE, FALSE,
    'Enterprise single-unit hydro. Noise 50dB.', '{"asic_chip": "BM1370BC/AA", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s21e-xp-hyd-430th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S21e XP Hyd 3U (860 TH)', 'S21e XP Hyd 3U', 'S21 Series',
    'hydro'::public.cooling_type, 9, 860.0, 11180, 13.0,
    'SHA-256', '2025-01-01', TRUE, FALSE,
    '3U rack form factor (3 hashboard sets). Noise 50dB.', '{"asic_chip": "BM1370BC/AA", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s21e-xp-hydro-860th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S21e Hyd (288 TH)', 'S21e Hyd', 'S21 Series',
    'hydro'::public.cooling_type, 3, 288.0, 4896, 17.0,
    'SHA-256', '2025-04-01', TRUE, FALSE,
    'Noise 50dB.', '{"asic_chip": "BM1368PA/PB", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s21e-hyd-288th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S21e Hyd (310 TH)', 'S21e Hyd', 'S21 Series',
    'hydro'::public.cooling_type, 3, 310.0, 5270, 17.0,
    'SHA-256', '2025-08-01', TRUE, FALSE,
    'Noise 50dB.', '{"asic_chip": "BM1368PA/PB", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s21e-hyd-310th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S21j XP Hyd (495 TH)', 'S21j XP Hyd', 'S21 Series',
    'hydro'::public.cooling_type, 3, 495.0, 5940, 12.0,
    'SHA-256', '2026-03-01', TRUE, FALSE,
    'j-bin hydro variant. Noise 50dB.', '{"asic_chip": "BM1370BC/AA", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s21j-xp-hyd-495th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S21 Immersion (215-301 TH)', 'S21 Immersion', 'S21 Series',
    'immersion'::public.cooling_type, 3, 258.0, 4650, 18.0233,
    'SHA-256', '2024-10-01', TRUE, FALSE,
    'Range 215-301 TH at 16-18.5 J/TH. Midpoint shown. Nominal listed as 301TH @ 5569W by ASIC Miner Value (18.5 J/TH). Noise 50dB.', '{"asic_chip": "BM1368PM", "process_node": "5nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s21-immersion-301th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S23 (318 TH)', 'S23', 'S23 Series',
    'air'::public.cooling_type, 3, 318.0, 3498, 11.0,
    'SHA-256', '2026-01-01', TRUE, FALSE,
    'Sub-10nm. Noise 75dB.', '{"asic_chip": "BM1370 next-gen", "process_node": "~3nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s23-318th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S23 Immersion (368-442 TH)', 'S23 IMM', 'S23 Series',
    'immersion'::public.cooling_type, 3, 442.0, 5304, 12.0,
    'SHA-256', '2026-01-01', TRUE, FALSE,
    'Purpose-built immersion chassis (no fans). ASIC Miner Value: 442TH @ 5304W (12 J/TH). Range 368-442 TH. Noise 50dB.', '{"asic_chip": "BM1370 next-gen", "process_node": "~3nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s23-immersion-442th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S23 Hydro (580 TH)', 'S23 Hyd', 'S23 Series',
    'hydro'::public.cooling_type, 3, 580.0, 5510, 9.5,
    'SHA-256', '2026-01-01', TRUE, FALSE,
    'Noise 50dB.', '{"asic_chip": "BM1370 next-gen", "process_node": "~3nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s23-hyd-580th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S23 Hydro 3U (1160 TH)', 'S23 Hyd 3U', 'S23 Series',
    'hydro'::public.cooling_type, 9, 1160.0, 11020, 9.5,
    'SHA-256', '2026-01-01', TRUE, FALSE,
    '3U rack form factor. Noise 50dB.', '{"asic_chip": "BM1370 next-gen", "process_node": "~3nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s23-hydro-u3-1160th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitmain'),
    'Antminer S23e Hyd 2U (865 TH)', 'S23e Hyd 2U', 'S23 Series',
    'hydro'::public.cooling_type, 6, 865.0, 8650, 10.0,
    'SHA-256', '2026-04-01', TRUE, FALSE,
    '2U enterprise hydro rack form. Noise 50dB.', '{"asic_chip": "BM1370 next-gen", "process_node": "~3nm", "sources": ["https://support.bitmain.com", "https://www.asicminervalue.com/manufacturers/bitmain", "https://d-central.tech", "https://hashrateindex.com", "https://www.asicminervalue.com/miners/antminer-s23e-hyd-u2h-865th"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M1', 'M1', 'M1/M3 Series',
    'air'::public.cooling_type, 3, 12.0, 2000, 166.6667,
    'SHA-256', '2018-03-01', FALSE, TRUE,
    '', '{"asic_chip": "SMTI 1700", "process_node": "28nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M3', 'M3', 'M1/M3 Series',
    'air'::public.cooling_type, 3, 12.0, 2000, 166.6667,
    'SHA-256', '2018-01-01', FALSE, TRUE,
    'Noise 78dB.', '{"asic_chip": "SMTI 1700", "process_node": "28nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m3"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M3X', 'M3X', 'M1/M3 Series',
    'air'::public.cooling_type, 3, 12.5, 2050, 164.0,
    'SHA-256', '2018-03-01', FALSE, TRUE,
    'Noise 78dB.', '{"asic_chip": "SMTI 1700", "process_node": "28nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m3x"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M10', 'M10', 'M10 Series',
    'air'::public.cooling_type, 3, 33.0, 2145, 65.0,
    'SHA-256', '2018-09-01', FALSE, TRUE,
    'Noise 75dB.', '{"process_node": "16nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m10"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M10S (55 TH)', 'M10S', 'M10 Series',
    'air'::public.cooling_type, 3, 55.0, 3500, 63.6364,
    'SHA-256', '2018-09-01', FALSE, TRUE,
    'Noise 75dB.', '{"process_node": "16nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m10s"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M20S (65 TH)', 'M20S', 'M20 Series',
    'air'::public.cooling_type, 3, 65.0, 3120, 48.0,
    'SHA-256', '2019-08-01', FALSE, TRUE,
    '', '{"asic_chip": "KF1921/Samsung", "process_node": "12nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M20S (68 TH)', 'M20S', 'M20 Series',
    'air'::public.cooling_type, 3, 68.0, 3360, 49.4118,
    'SHA-256', '2019-08-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "KF1921/Samsung", "process_node": "12nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m20s"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M20S (70 TH)', 'M20S', 'M20 Series',
    'air'::public.cooling_type, 3, 70.0, 3360, 48.0,
    'SHA-256', '2019-08-01', FALSE, TRUE,
    '', '{"asic_chip": "KF1921/Samsung", "process_node": "12nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M20S+', 'M20S+', 'M20 Series',
    'air'::public.cooling_type, 3, 72.0, 3360, 46.6667,
    'SHA-256', '2019-01-01', FALSE, TRUE,
    '', '{"asic_chip": "Samsung", "process_node": "10nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M21', 'M21', 'M21 Series',
    'air'::public.cooling_type, 3, 31.0, 1860, 60.0,
    'SHA-256', '2019-08-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "Samsung", "process_node": "12nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m21"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M21S (56 TH)', 'M21S', 'M21 Series',
    'air'::public.cooling_type, 3, 56.0, 3360, 60.0,
    'SHA-256', '2019-06-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "Samsung", "process_node": "10nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m21s"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M21S (58 TH)', 'M21S', 'M21 Series',
    'air'::public.cooling_type, 3, 58.0, 3480, 60.0,
    'SHA-256', '2019-06-01', FALSE, TRUE,
    '', '{"asic_chip": "Samsung", "process_node": "10nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M21S+', 'M21S+', 'M21 Series',
    'air'::public.cooling_type, 3, 58.0, 3480, 60.0,
    'SHA-256', '2020-01-01', FALSE, TRUE,
    '', '{"asic_chip": "Samsung", "process_node": "10nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M30S', 'M30S', 'M30 Series',
    'air'::public.cooling_type, 3, 86.0, 3268, 38.0,
    'SHA-256', '2020-04-01', FALSE, TRUE,
    'Noise 72dB.', '{"asic_chip": "Samsung 8nm", "process_node": "8nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m30s"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M30S+', 'M30S+', 'M30 Series',
    'air'::public.cooling_type, 3, 100.0, 3400, 34.0,
    'SHA-256', '2020-10-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "Samsung 8nm", "process_node": "8nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m30s-1"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M30S++', 'M30S++', 'M30 Series',
    'air'::public.cooling_type, 3, 112.0, 3472, 31.0,
    'SHA-256', '2020-10-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "Samsung 8nm", "process_node": "8nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m30s-2"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M31S', 'M31S', 'M31 Series',
    'air'::public.cooling_type, 3, 74.0, 3220, 43.5135,
    'SHA-256', '2020-07-01', FALSE, TRUE,
    'ASIC Miner Value: 76TH @ 3344W. Noise 75dB.', '{"asic_chip": "Samsung 8nm", "process_node": "8nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m31s"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M31S+', 'M31S+', 'M31 Series',
    'air'::public.cooling_type, 3, 80.0, 3360, 42.0,
    'SHA-256', '2020-07-01', FALSE, TRUE,
    'Noise 70dB.', '{"asic_chip": "Samsung 8nm", "process_node": "8nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m31s-1"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M32 (62 TH)', 'M32', 'M32 Series',
    'air'::public.cooling_type, 3, 62.0, 3348, 54.0,
    'SHA-256', '2020-07-01', FALSE, TRUE,
    'ASIC Miner Value: 62TH @ 3456W. Noise 75dB.', '{"asic_chip": "Samsung 8nm", "process_node": "8nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m32"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M32 (66 TH)', 'M32', 'M32 Series',
    'air'::public.cooling_type, 3, 66.0, 3432, 52.0,
    'SHA-256', '2020-11-01', FALSE, TRUE,
    '', '{"asic_chip": "Samsung 8nm", "process_node": "8nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M32 (68 TH)', 'M32', 'M32 Series',
    'air'::public.cooling_type, 3, 68.0, 3400, 50.0,
    'SHA-256', '2020-11-01', FALSE, TRUE,
    '', '{"asic_chip": "Samsung 8nm", "process_node": "8nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M32S', 'M32S', 'M32 Series',
    'air'::public.cooling_type, 3, 68.0, 3472, 51.0588,
    'SHA-256', '2021-01-01', FALSE, TRUE,
    'ASIC Miner Value: 66TH @ 3432W (52 J/TH). Noise 75dB.', '{"asic_chip": "Samsung 8nm", "process_node": "8nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m32s"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M33S (80 TH)', 'M33S', 'M33 Series',
    'air'::public.cooling_type, 3, 80.0, 3360, 42.0,
    'SHA-256', '2020-12-01', FALSE, TRUE,
    'Noise 75dB. Listed in ASIC Miner Value; air-cooled variant separate from M33S++ hydro.', '{"asic_chip": "Samsung 7nm", "process_node": "7nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m33s"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M33S++', 'M33S++', 'M33 Series',
    'hydro'::public.cooling_type, 4, 242.0, 7260, 30.0,
    'SHA-256', '2022-12-01', FALSE, TRUE,
    '4U Blade; 3-phase AC380V. Hydro-cooled derivative of M30 gen.', '{"asic_chip": "Samsung 7nm", "process_node": "7nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.cryptominerbros.com/product/microbt-whatsminer-m33s-hydro-bitcoin-miner/"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M36S (62 TH)', 'M36S', 'M36 Series',
    'air'::public.cooling_type, 3, 62.0, 3456, 55.7419,
    'SHA-256', '2020-07-01', FALSE, TRUE,
    'Noise 75dB. Listed in ASIC Miner Value as separate from M36S+/++ immersion.', '{"asic_chip": "Samsung 8nm", "process_node": "8nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m36s"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M36S+', 'M36S+', 'M36 Series',
    'immersion'::public.cooling_type, 3, 127.0, 3306, 26.0315,
    'SHA-256', '2022-01-01', FALSE, TRUE,
    'Slim immersion form. Range 124-130 TH at 26-27 J/TH. Midpoint shown.', '{"asic_chip": "Samsung 8nm", "process_node": "8nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M36S++', 'M36S++', 'M36 Series',
    'immersion'::public.cooling_type, 3, 167.0, 5166, 30.9341,
    'SHA-256', '2023-05-01', FALSE, TRUE,
    'Slim immersion. Range 162-172 TH. Midpoint shown.', '{"asic_chip": "Samsung 8nm", "process_node": "8nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M50 (114 TH)', 'M50', 'M50 Series',
    'air'::public.cooling_type, 3, 114.0, 3306, 29.0,
    'SHA-256', '2022-07-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "Samsung 5nm", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m50"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M50S (126 TH)', 'M50S', 'M50 Series',
    'air'::public.cooling_type, 3, 126.0, 3276, 26.0,
    'SHA-256', '2022-07-01', FALSE, TRUE,
    'ASIC Miner Value: 128TH @ 3276W (25.59 J/TH). Noise 75dB.', '{"asic_chip": "Samsung 5nm", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m50s"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M50S+ (136-148 TH)', 'M50S+', 'M50 Series',
    'air'::public.cooling_type, 3, 142.0, 3405, 23.9789,
    'SHA-256', '2023-01-01', FALSE, TRUE,
    'Range 136-148 TH. Midpoint shown.', '{"asic_chip": "Samsung 5nm", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M50S++ (150-162 TH)', 'M50S++', 'M50 Series',
    'air'::public.cooling_type, 3, 156.0, 3265, 20.9295,
    'SHA-256', '2023-01-01', FALSE, TRUE,
    'Range 150-162 TH at 21-23 J/TH. Midpoint shown.', '{"asic_chip": "Samsung 5nm", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M53 (230 TH)', 'M53', 'M53 Series',
    'hydro'::public.cooling_type, 4, 230.0, 6670, 29.0,
    'SHA-256', '2023-05-01', FALSE, TRUE,
    '4U Blade. ASIC Miner Value: 260TH @ 6760W, 26 J/TH (immersion). Hydro per deep dive. Noise 45dB.', '{"asic_chip": "Samsung 5nm", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://asicmarketplace.com/product/microbt-whatsminer-m53-m53s-hydro-btc-miner/"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M53S (260 TH)', 'M53S', 'M53 Series',
    'hydro'::public.cooling_type, 4, 260.0, 6760, 26.0,
    'SHA-256', '2023-05-01', FALSE, TRUE,
    '4U Blade. Noise 45dB.', '{"asic_chip": "Samsung 5nm", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m53s"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M53S++ (320 TH)', 'M53S++', 'M53 Series',
    'hydro'::public.cooling_type, 4, 320.0, 7040, 22.0,
    'SHA-256', '2023-07-01', FALSE, TRUE,
    '4U Blade.', '{"asic_chip": "Samsung 5nm", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M56 (194 TH)', 'M56', 'M56 Series',
    'immersion'::public.cooling_type, 3, 194.0, 5550, 28.6082,
    'SHA-256', '2023-01-01', FALSE, TRUE,
    'Slim immersion. Noise 45dB.', '{"asic_chip": "Samsung 5nm", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m56"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M56S (200 TH)', 'M56S', 'M56 Series',
    'immersion'::public.cooling_type, 3, 200.0, 5200, 26.0,
    'SHA-256', '2023-05-01', FALSE, TRUE,
    'Slim immersion. ASIC Miner Value: 212TH @ 5550W (26.18). Noise 45dB.', '{"asic_chip": "Samsung 5nm", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m56s"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M56S+ (224 TH)', 'M56S+', 'M56 Series',
    'immersion'::public.cooling_type, 3, 224.0, 5376, 24.0,
    'SHA-256', '2023-01-01', FALSE, TRUE,
    'Slim immersion.', '{"asic_chip": "Samsung 5nm", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M56S++ (254 TH)', 'M56S++', 'M56 Series',
    'immersion'::public.cooling_type, 3, 254.0, 5588, 22.0,
    'SHA-256', '2023-05-01', FALSE, TRUE,
    'Slim immersion.', '{"asic_chip": "Samsung 5nm", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M60 (162 TH)', 'M60', 'M60 Series',
    'air'::public.cooling_type, 3, 162.0, 3104, 19.1605,
    'SHA-256', '2023-10-01', TRUE, FALSE,
    'ASIC Miner Value: 172TH @ 3422W (19.9 J/TH). Noise 75dB.', '{"asic_chip": "Samsung 5nm+", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m60"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M60S (186 TH)', 'M60S', 'M60 Series',
    'air'::public.cooling_type, 3, 186.0, 3441, 18.5,
    'SHA-256', '2023-10-01', TRUE, FALSE,
    'Noise 75dB.', '{"asic_chip": "Samsung 5nm+", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m60s"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M60S+ (190-200 TH)', 'M60S+', 'M60 Series',
    'air'::public.cooling_type, 3, 195.0, 3315, 17.0,
    'SHA-256', '2024-07-01', TRUE, FALSE,
    'Range 190-200 TH. ASIC Miner Value: 212TH @ 3600W. Noise 75dB.', '{"asic_chip": "Samsung 5nm+", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m60s-plus"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M60S++ (218-226 TH)', 'M60S++', 'M60 Series',
    'air'::public.cooling_type, 3, 226.0, 3600, 15.9292,
    'SHA-256', '2024-12-01', TRUE, FALSE,
    'Noise 75dB. ASIC Miner Value: 226TH @ 3600W (15.93 J/TH).', '{"asic_chip": "Samsung 5nm+", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m60s-plus-plus"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M61 (202 TH)', 'M61', 'M61 Series',
    'air'::public.cooling_type, 3, 202.0, 4000, 19.802,
    'SHA-256', '2024-12-01', TRUE, FALSE,
    'Larger form factor (430×155×226mm).', '{"asic_chip": "Samsung 5nm+", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M61S (216 TH)', 'M61S', 'M61 Series',
    'air'::public.cooling_type, 3, 216.0, 4320, 20.0,
    'SHA-256', '2024-12-01', TRUE, FALSE,
    '', '{"asic_chip": "Samsung 5nm+", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M61S+ (236 TH)', 'M61S+', 'M61 Series',
    'air'::public.cooling_type, 3, 236.0, 4012, 17.0,
    'SHA-256', '2024-12-01', TRUE, FALSE,
    '', '{"asic_chip": "Samsung 5nm+", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M63 (366-372 TH)', 'M63', 'M63 Series',
    'hydro'::public.cooling_type, 4, 369.0, 7283, 19.7371,
    'SHA-256', '2023-10-01', TRUE, FALSE,
    '4U Blade. Range 366-372 TH. ASIC Miner Value: 334TH @ 6646W. Noise 50dB.', '{"asic_chip": "Samsung 5nm+", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m63"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M63S (390-416 TH)', 'M63S', 'M63 Series',
    'hydro'::public.cooling_type, 4, 390.0, 7215, 18.5,
    'SHA-256', '2023-10-01', TRUE, FALSE,
    '4U Blade. Noise 50dB.', '{"asic_chip": "Samsung 5nm+", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m63s"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M63S+ (450 TH)', 'M63S+', 'M63 Series',
    'hydro'::public.cooling_type, 4, 450.0, 7650, 17.0,
    'SHA-256', '2025-07-01', TRUE, FALSE,
    '4U Blade. ASIC Miner Value: 424TH @ 7208W (17 J/TH). Noise 75dB.', '{"asic_chip": "Samsung 5nm+", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m63s-plus"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M63S++ (464-478 TH)', 'M63S++', 'M63 Series',
    'hydro'::public.cooling_type, 4, 464.0, 7200, 15.5172,
    'SHA-256', '2024-12-01', TRUE, FALSE,
    'Announced at Bitcoin MENA 2024. Range 464-478 TH. ASIC Miner Value: 464TH @ 7200W (15.52 J/TH). Noise 75dB.', '{"asic_chip": "Samsung 5nm+", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m63s-plus-plus"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M64 (202-206 TH)', 'M64', 'M64 Series',
    'hydro'::public.cooling_type, 2, 204.0, 4059, 19.8971,
    'SHA-256', '2024-01-01', TRUE, FALSE,
    '2U Blade; single-phase 220-277V. Home heating variant. Range 202-206 TH.', '{"asic_chip": "Samsung 5nm+", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M64S+ (236 TH)', 'M64S+', 'M64 Series',
    'hydro'::public.cooling_type, 2, 236.0, 4012, 17.0,
    'SHA-256', '2024-12-01', TRUE, FALSE,
    'Max outlet water temp 80°C. Announced at Bitcoin MENA 2024.', '{"asic_chip": "Samsung 5nm+", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M65S (390-412 TH)', 'M65S', 'M65 Series',
    'hydro'::public.cooling_type, 4, 390.0, 7308, 18.7385,
    'SHA-256', '2024-01-01', TRUE, FALSE,
    '4U Blade; 80°C outlet water temp. High-temp hydro variant.', '{"asic_chip": "Samsung 5nm+", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M65S+ (440 TH)', 'M65S+', 'M65 Series',
    'hydro'::public.cooling_type, 4, 440.0, 7480, 17.0,
    'SHA-256', '2024-12-01', TRUE, FALSE,
    'Announced at Bitcoin MENA 2024.', '{"asic_chip": "Samsung 5nm+", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M66 (276 TH)', 'M66', 'M66 Series',
    'immersion'::public.cooling_type, 3, 276.0, 5492, 19.8986,
    'SHA-256', '2023-10-01', TRUE, FALSE,
    'Slim immersion. ASIC Miner Value: 280TH @ 5572W (19.9 J/TH). Noise 50dB.', '{"asic_chip": "Samsung 5nm+", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m66"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M66S (286-298 TH)', 'M66S', 'M66 Series',
    'immersion'::public.cooling_type, 3, 298.0, 5513, 18.5,
    'SHA-256', '2023-11-01', TRUE, FALSE,
    'Slim immersion. Noise 50dB.', '{"asic_chip": "Samsung 5nm+", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m66s"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M66S+ (318 TH)', 'M66S+', 'M66 Series',
    'immersion'::public.cooling_type, 3, 318.0, 5406, 17.0,
    'SHA-256', '2024-08-01', TRUE, FALSE,
    'Slim immersion. Noise 75dB.', '{"asic_chip": "Samsung 5nm+", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m66s-plus"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M66S++ (356-470 TH)', 'M66S++', 'M66 Series',
    'immersion'::public.cooling_type, 3, 470.0, 7200, 15.3191,
    'SHA-256', '2024-12-01', TRUE, FALSE,
    'Announced Bitcoin MENA 2024. ASIC Miner Value: 470TH @ 7200W (15.32 J/TH). Noise 50dB.', '{"asic_chip": "Samsung 5nm+", "process_node": "5nm", "sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m66s-plus-plus"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M6DS+ (504 TH)', 'M6DS+', 'M6DS Series',
    'hydro'::public.cooling_type, 4, 504.0, 8568, 17.0,
    'SHA-256', '2026-03-01', TRUE, FALSE,
    '4U Blade. Next-gen chip. Noise 75dB.', '{"sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M6DS++ (556-592 TH)', 'M6DS++', 'M6DS Series',
    'hydro'::public.cooling_type, 4, 592.0, 9200, 15.5405,
    'SHA-256', '2026-03-01', TRUE, FALSE,
    'Range 556-592 TH. ASIC Miner Value: 592TH @ 9200W. Noise 75dB.', '{"sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m6ds-plus-plus"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M7DS (680 TH)', 'M7DS', 'M7DS Series',
    'hydro'::public.cooling_type, 4, 680.0, 9200, 13.5294,
    'SHA-256', '2026-03-01', TRUE, FALSE,
    'ASIC Miner Value: 680TH @ 9200W (13.53 J/TH). Noise 75dB.', '{"sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m7ds"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M70 (214 TH)', 'M70', 'M70 Series',
    'air'::public.cooling_type, 3, 214.0, 3140, 14.6729,
    'SHA-256', '2025-12-01', TRUE, FALSE,
    'Noise 75dB.', '{"sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m70"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M70S (226 TH)', 'M70S', 'M70 Series',
    'air'::public.cooling_type, 3, 226.0, 3140, 13.8938,
    'SHA-256', '2025-12-01', TRUE, FALSE,
    'Noise 75dB.', '{"sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m70s"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M70S+ (244 TH)', 'M70S+', 'M70 Series',
    'air'::public.cooling_type, 3, 244.0, 3140, 12.8689,
    'SHA-256', '2025-12-01', TRUE, FALSE,
    'Noise 75dB.', '{"sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m70splus"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M72 (246 TH)', 'M72', 'M72 Series',
    'air'::public.cooling_type, 3, 246.0, 4000, 16.2602,
    'SHA-256', '2025-12-01', TRUE, FALSE,
    '', '{"sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M72S (264 TH)', 'M72S', 'M72 Series',
    'air'::public.cooling_type, 3, 264.0, 4000, 15.1515,
    'SHA-256', '2025-12-01', TRUE, FALSE,
    '', '{"sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M72S (920 TH Hydro)', 'M72S', 'M72 Series',
    'hydro'::public.cooling_type, 4, 920.0, 14500, 15.7609,
    'SHA-256', '2026-01-01', TRUE, FALSE,
    'Hydro variant. ASIC Miner Value: 920TH @ 14500W (15.76 J/TH). Noise 50dB.', '{"sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m72s"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M73 (470 TH)', 'M73', 'M73 Series',
    'hydro'::public.cooling_type, 4, 470.0, 7200, 15.3191,
    'SHA-256', '2025-12-01', TRUE, FALSE,
    '4U Blade. Noise 75dB.', '{"sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m73"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M73S (500 TH)', 'M73S', 'M73 Series',
    'hydro'::public.cooling_type, 4, 500.0, 7200, 14.4,
    'SHA-256', '2025-12-01', TRUE, FALSE,
    '4U Blade. Noise 75dB.', '{"sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m73s"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M73S+ (540 TH)', 'M73S+', 'M73 Series',
    'hydro'::public.cooling_type, 4, 540.0, 7200, 13.3333,
    'SHA-256', '2025-12-01', TRUE, FALSE,
    '4U Blade. Noise 75dB.', '{"sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m73s-plus"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M76 (336 TH)', 'M76', 'M76 Series',
    'immersion'::public.cooling_type, 3, 336.0, 5200, 15.4762,
    'SHA-256', '2025-12-01', TRUE, FALSE,
    'Slim immersion. Noise 75dB.', '{"sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m76"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M76S (362 TH)', 'M76S', 'M76 Series',
    'immersion'::public.cooling_type, 3, 362.0, 5200, 14.3646,
    'SHA-256', '2025-12-01', TRUE, FALSE,
    'Slim immersion. Noise 75dB.', '{"sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m76s"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M76S+ (390 TH)', 'M76S+', 'M76 Series',
    'immersion'::public.cooling_type, 3, 390.0, 5200, 13.3333,
    'SHA-256', '2025-12-01', TRUE, FALSE,
    'Slim immersion. Noise 75dB.', '{"sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m76s-plus"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M78 (440 TH)', 'M78', 'M78 Series',
    'immersion'::public.cooling_type, 3, 440.0, 7000, 15.9091,
    'SHA-256', '2025-12-01', TRUE, FALSE,
    'Slim immersion (large).', '{"sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M78S (472 TH)', 'M78S', 'M78 Series',
    'immersion'::public.cooling_type, 3, 472.0, 6550, 13.8771,
    'SHA-256', '2025-12-01', TRUE, FALSE,
    'Slim immersion. ASIC Miner Value: 472TH @ 6550W (13.88 J/TH). Noise 75dB.', '{"sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m78s"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M79 (870 TH)', 'M79', 'M79 Series',
    'hydro'::public.cooling_type, 8, 870.0, 14000, 16.092,
    'SHA-256', '2025-12-01', TRUE, FALSE,
    '8U Dual-Blade (2x M73). ASIC Miner Value: 920TH @ 14500W (15.76). Noise 50dB.', '{"sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m79"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M79S (930 TH)', 'M79S', 'M79 Series',
    'hydro'::public.cooling_type, 8, 930.0, 14000, 15.0538,
    'SHA-256', '2025-12-01', TRUE, FALSE,
    '8U Dual-Blade. ASIC Miner Value: 1350TH @ 20000W. Noise 50dB.', '{"sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m79s"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M7D (594 TH)', 'M7D', 'M7D Series',
    'hydro'::public.cooling_type, 4, 594.0, 8613, 14.5,
    'SHA-256', '2026-03-01', TRUE, FALSE,
    '4U Blade. ASIC Miner Value: 634TH @ 9200W (14.51 J/TH). Noise 75dB.', '{"sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/whatsminer-m7d"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'microbt'),
    'Whatsminer M7DS (638 TH)', 'M7DS', 'M7D Series',
    'hydro'::public.cooling_type, 4, 638.0, 8613, 13.5,
    'SHA-256', '2026-03-01', TRUE, FALSE,
    '4U Blade.', '{"sources": ["https://shop.whatsminer.com", "https://www.asicminervalue.com/manufacturers/microbt", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon1 Batch 1 (66 GH/s)', 'Avalon1 B1', 'Avalon1 Gen1',
    'air'::public.cooling_type, 4, 0.066, 620, 9393.9394,
    'SHA-256', '2013-01-01', FALSE, TRUE,
    'Original open-source miner. 2+2 module config.', '{"asic_chip": "A3256", "process_node": "110nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon1 Batch 2 (82 GH/s)', 'Avalon1 B2', 'Avalon1 Gen1',
    'air'::public.cooling_type, 4, 0.082, 700, 8536.5854,
    'SHA-256', '2013-01-01', FALSE, TRUE,
    '', '{"asic_chip": "A3256", "process_node": "110nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon1 Batch 3 (82 GH/s)', 'Avalon1 B3', 'Avalon1 Gen1',
    'air'::public.cooling_type, 4, 0.082, 700, 8536.5854,
    'SHA-256', '2013-01-01', FALSE, TRUE,
    '', '{"asic_chip": "A3256", "process_node": "110nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon2', 'Avalon2', 'Avalon2 Gen2',
    'air'::public.cooling_type, 3, 0.3, 1020, 3400.0,
    'SHA-256', '2013-01-01', FALSE, TRUE,
    'Normal: 315GH/1020W; ECO: 210GH/420W.', '{"asic_chip": "A3255", "process_node": "55nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon3', 'Avalon3', 'Avalon3 Gen3',
    'air'::public.cooling_type, 3, 0.8, 1500, 1875.0,
    'SHA-256', '2014-01-01', FALSE, TRUE,
    '~800 GH/s.', '{"asic_chip": "A3233", "process_node": "40nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon4 / Avalon4.1 (1.3 TH/s)', 'Avalon4', 'Avalon4 Gen4',
    'air'::public.cooling_type, 3, 1.3, 910, 700.0,
    'SHA-256', '2014-01-01', FALSE, TRUE,
    'A3222 chip, 40nm. 40 chips at 0.7 W/GH.', '{"asic_chip": "A3222", "process_node": "40nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon6', 'Avalon6', 'Avalon6 Gen6',
    'air'::public.cooling_type, 3, 3.5, 1080, 308.5714,
    'SHA-256', '2015-01-01', FALSE, TRUE,
    '0.29 J/GH.', '{"asic_chip": "A3218", "process_node": "28nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 721', 'A721', 'Avalon7 Gen7',
    'air'::public.cooling_type, 1, 6.0, 900, 150.0,
    'SHA-256', '2016-11-01', FALSE, TRUE,
    '', '{"asic_chip": "A3212", "process_node": "16nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 741', 'A741', 'Avalon7 Gen7',
    'air'::public.cooling_type, 1, 7.3, 1150, 157.5342,
    'SHA-256', '2017-04-01', FALSE, TRUE,
    '88 × A3212 chips. Noise 65dB.', '{"asic_chip": "A3212", "process_node": "16nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/avalonminer-741"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 761', 'A761', 'Avalon7 Gen7',
    'air'::public.cooling_type, 1, 8.8, 1320, 150.0,
    'SHA-256', '2017-01-01', FALSE, TRUE,
    '104 × A3212 chips.', '{"asic_chip": "A3212", "process_node": "16nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 821 (11 TH)', 'A821', 'Avalon8 Gen8',
    'air'::public.cooling_type, 4, 11.0, 1200, 109.0909,
    'SHA-256', '2018-02-01', FALSE, TRUE,
    '', '{"asic_chip": "A3210", "process_node": "16nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 821 (11.5 TH)', 'A821', 'Avalon8 Gen8',
    'air'::public.cooling_type, 4, 11.5, 1200, 104.3478,
    'SHA-256', '2018-02-01', FALSE, TRUE,
    'Noise 72dB.', '{"asic_chip": "A3210", "process_node": "16nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/avalonminer-821"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 841', 'A841', 'Avalon8 Gen8',
    'air'::public.cooling_type, 4, 13.0, 1290, 99.2308,
    'SHA-256', '2018-04-01', FALSE, TRUE,
    'ASIC Miner Value: 13.6TH @ 1290W (94.85 J/TH). Noise 65dB.', '{"asic_chip": "A3210HP", "process_node": "16nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/avalonminer-841"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 851', 'A851', 'Avalon8 Gen8',
    'air'::public.cooling_type, 4, 14.5, 1450, 100.0,
    'SHA-256', '2018-01-01', FALSE, TRUE,
    '', '{"asic_chip": "A3210HP", "process_node": "16nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 852', 'A852', 'Avalon8 Gen8',
    'air'::public.cooling_type, 4, 15.0, 1500, 100.0,
    'SHA-256', '2019-01-01', FALSE, TRUE,
    '', '{"asic_chip": "A3210HP", "process_node": "16nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 910', 'A910', 'Avalon9 Gen9',
    'air'::public.cooling_type, 1, 16.0, 1350, 84.375,
    'SHA-256', '2019-01-01', FALSE, TRUE,
    '', '{"asic_chip": "A3207", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 911', 'A911', 'Avalon9 Gen9',
    'air'::public.cooling_type, 1, 18.0, 1440, 80.0,
    'SHA-256', '2019-07-01', FALSE, TRUE,
    '', '{"asic_chip": "A3207", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 920', 'A920', 'Avalon9 Gen9',
    'air'::public.cooling_type, 1, 18.0, 1720, 95.5556,
    'SHA-256', '2019-01-01', FALSE, TRUE,
    '', '{"asic_chip": "A3207", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 921', 'A921', 'Avalon9 Gen9',
    'air'::public.cooling_type, 1, 20.0, 1700, 85.0,
    'SHA-256', '2018-09-01', FALSE, TRUE,
    'Noise 72dB.', '{"asic_chip": "A3207", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/avalonminer-921"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 1026', 'A1026', 'Avalon10 Gen10',
    'air'::public.cooling_type, 2, 30.0, 2070, 69.0,
    'SHA-256', '2019-01-01', FALSE, TRUE,
    '', '{"asic_chip": "A3205", "process_node": "16nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 1041', 'A1041', 'Avalon10 Gen10',
    'air'::public.cooling_type, 2, 31.0, 1736, 56.0,
    'SHA-256', '2019-01-01', FALSE, TRUE,
    '240 × A3205 chips.', '{"asic_chip": "A3205", "process_node": "16nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 1047', 'A1047', 'Avalon10 Gen10',
    'air'::public.cooling_type, 3, 37.0, 2380, 64.3243,
    'SHA-256', '2019-09-01', FALSE, TRUE,
    'Noise 72dB.', '{"asic_chip": "A3205", "process_node": "16nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/avalonminer-1047"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 1066', 'A1066', 'Avalon10 Gen10',
    'air'::public.cooling_type, 3, 50.0, 3250, 65.0,
    'SHA-256', '2019-09-01', FALSE, TRUE,
    '342 × A3205. ASIC Miner Value: 63TH @ 3276W (52 J/TH). Noise 72dB.', '{"asic_chip": "A3205", "process_node": "16nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/avalonminer-1066"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 1066 Pro', 'A1066 Pro', 'Avalon10 Gen10',
    'air'::public.cooling_type, 3, 55.0, 3276, 59.5636,
    'SHA-256', '2020-02-01', FALSE, TRUE,
    '342 × A3205 chips.', '{"asic_chip": "A3205", "process_node": "16nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 1126 Pro (60 TH)', 'A1126 Pro', 'Avalon11 Gen11',
    'air'::public.cooling_type, 3, 60.0, 3420, 57.0,
    'SHA-256', '2021-08-01', FALSE, TRUE,
    '', '{"asic_chip": "A3202", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 1126 Pro (64 TH)', 'A1126 Pro', 'Avalon11 Gen11',
    'air'::public.cooling_type, 3, 64.0, 3420, 53.4375,
    'SHA-256', '2021-08-01', FALSE, TRUE,
    '', '{"asic_chip": "A3202", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 1126 Pro (68 TH)', 'A1126 Pro', 'Avalon11 Gen11',
    'air'::public.cooling_type, 3, 68.0, 3420, 50.2941,
    'SHA-256', '2021-08-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "A3202", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/avalonminer-1126-pro"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 1146', 'A1146', 'Avalon11 Gen11',
    'air'::public.cooling_type, 3, 56.0, 3192, 57.0,
    'SHA-256', '2020-02-01', FALSE, TRUE,
    '', '{"asic_chip": "A3202", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 1146 Pro (63 TH)', 'A1146 Pro', 'Avalon11 Gen11',
    'air'::public.cooling_type, 3, 63.0, 3276, 52.0,
    'SHA-256', '2020-08-01', FALSE, TRUE,
    'ASIC Miner Value: 130TH @ 3250W (25 J/TH) — conflicting entries. Separate model confirmed.', '{"asic_chip": "A3202", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/avalonminer-1146-pro"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 1166', 'A1166', 'Avalon11 Gen11',
    'air'::public.cooling_type, 3, 68.0, 3196, 47.0,
    'SHA-256', '2020-01-01', FALSE, TRUE,
    '', '{"asic_chip": "A3204", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 1166 Pro (72 TH)', 'A1166 Pro', 'Avalon11 Gen11',
    'air'::public.cooling_type, 3, 72.0, 3420, 47.5,
    'SHA-256', '2020-08-01', FALSE, TRUE,
    '', '{"asic_chip": "A3202", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 1166 Pro (75 TH)', 'A1166 Pro', 'Avalon11 Gen11',
    'air'::public.cooling_type, 3, 75.0, 3276, 43.68,
    'SHA-256', '2020-08-01', FALSE, TRUE,
    '', '{"asic_chip": "A3202", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 1166 Pro (78 TH)', 'A1166 Pro', 'Avalon11 Gen11',
    'air'::public.cooling_type, 3, 78.0, 3276, 42.0,
    'SHA-256', '2020-08-01', FALSE, TRUE,
    '', '{"asic_chip": "A3202", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'AvalonMiner 1166 Pro (81 TH)', 'A1166 Pro', 'Avalon11 Gen11',
    'air'::public.cooling_type, 3, 81.0, 3400, 41.9753,
    'SHA-256', '2020-08-01', FALSE, TRUE,
    'Noise 75dB.', '{"asic_chip": "A3202", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/avalonminer-1166-pro"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A1246 (83 TH)', 'A1246', 'Avalon12 Gen12',
    'air'::public.cooling_type, 3, 83.0, 3420, 41.2048,
    'SHA-256', '2021-01-01', FALSE, TRUE,
    '', '{"asic_chip": "A12", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A1246 (85 TH)', 'A1246', 'Avalon12 Gen12',
    'air'::public.cooling_type, 3, 85.0, 3420, 40.2353,
    'SHA-256', '2021-01-01', FALSE, TRUE,
    '', '{"asic_chip": "A12", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A1246 (90 TH)', 'A1246', 'Avalon12 Gen12',
    'air'::public.cooling_type, 3, 90.0, 3420, 38.0,
    'SHA-256', '2021-01-01', FALSE, TRUE,
    'ASIC Miner Value: 90TH @ 3420W (38 J/TH). Noise 75dB.', '{"asic_chip": "A12", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/avalonminer-1246"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A1246 (93 TH)', 'A1246', 'Avalon12 Gen12',
    'air'::public.cooling_type, 3, 93.0, 3420, 36.7742,
    'SHA-256', '2021-01-01', FALSE, TRUE,
    '', '{"asic_chip": "A12", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A1246 (96 TH)', 'A1246', 'Avalon12 Gen12',
    'air'::public.cooling_type, 3, 96.0, 3420, 35.625,
    'SHA-256', '2020-12-01', FALSE, TRUE,
    'First-shipped bin.', '{"asic_chip": "A12", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A1266 (100 TH)', 'A1266', 'Avalon12 Gen12',
    'air'::public.cooling_type, 3, 100.0, 3500, 35.0,
    'SHA-256', '2022-04-01', FALSE, TRUE,
    '', '{"asic_chip": "A12", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A1326 (106-115 TH)', 'A1326', 'Avalon13 Gen13',
    'air'::public.cooling_type, 3, 110.0, 3425, 31.1364,
    'SHA-256', '2022-11-01', FALSE, TRUE,
    'Range 106-115 TH. Midpoint shown.', '{"asic_chip": "A3246", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A1346 (110 TH)', 'A1346', 'Avalon13 Gen13',
    'air'::public.cooling_type, 3, 110.0, 3300, 30.0,
    'SHA-256', '2022-10-01', FALSE, TRUE,
    'ASIC Miner Value: 150TH @ 3230W (21.53). Discrepancy — separate variant listed. Noise 75dB.', '{"asic_chip": "A3246", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/avalon-made-a1346"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A1366 (130 TH)', 'A1366', 'Avalon13 Gen13',
    'air'::public.cooling_type, 3, 130.0, 3250, 25.0,
    'SHA-256', '2022-10-01', FALSE, TRUE,
    'ASIC Miner Value: 135TH @ 3310W (24.52). Noise 75dB.', '{"asic_chip": "A3246", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/avalon-made-a1366"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A1366I (119 TH)', 'A1366I', 'Avalon13 Gen13',
    'immersion'::public.cooling_type, 3, 119.0, 3570, 30.0,
    'SHA-256', '2023-05-01', FALSE, TRUE,
    'ASIC Miner Value: Avalon Miner A1366I at 81TH @ 3400W (41.98 J/TH) — different variant or listing discrepancy.', '{"asic_chip": "A3246", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A1366I (122 TH)', 'A1366I', 'Avalon13 Gen13',
    'immersion'::public.cooling_type, 3, 122.0, 3570, 29.2623,
    'SHA-256', '2023-07-01', FALSE, TRUE,
    '', '{"asic_chip": "A3246", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A1366I (165 TH)', 'A1366I', 'Avalon13 Gen13',
    'immersion'::public.cooling_type, 3, 165.0, 4950, 30.0,
    'SHA-256', '2023-01-01', FALSE, TRUE,
    'High-OC immersion variant.', '{"asic_chip": "A3246", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A1446 (135 TH)', 'A1446', 'Avalon14 Gen14',
    'air'::public.cooling_type, 3, 135.0, 3310, 24.5185,
    'SHA-256', '2023-09-01', FALSE, TRUE,
    'ASIC Miner Value: A1446 @ 119TH/3570W (30 J/TH). Noise 75dB.', '{"asic_chip": "A3246", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/avalon-made-a1446"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A1466 (150 TH)', 'A1466', 'Avalon14 Gen14',
    'air'::public.cooling_type, 3, 150.0, 3230, 21.5333,
    'SHA-256', '2023-09-01', FALSE, TRUE,
    'ASIC Miner Value: Avalon Made A1466 @ 194TH/3647W (18.8). Separate newer batch. Noise 75dB.', '{"asic_chip": "A3246", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/avalon-made-a1466"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A1466I (153 TH)', 'A1466I', 'Avalon14 Gen14',
    'immersion'::public.cooling_type, 3, 153.0, 3320, 21.6993,
    'SHA-256', '2023-09-01', FALSE, TRUE,
    '', '{"asic_chip": "A3246", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A1466I (170 TH)', 'A1466I', 'Avalon14 Gen14',
    'immersion'::public.cooling_type, 3, 170.0, 3317, 19.5118,
    'SHA-256', '2023-09-01', FALSE, TRUE,
    '', '{"asic_chip": "A3246", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A1566 (185 TH)', 'A1566', 'Avalon15 Gen15',
    'air'::public.cooling_type, 3, 185.0, 3420, 18.4865,
    'SHA-256', '2024-10-01', TRUE, FALSE,
    'Noise 75dB.', '{"asic_chip": "A15", "process_node": "4nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/avalon-a1566"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A1566I (249 TH)', 'A1566I', 'Avalon15 Gen15',
    'immersion'::public.cooling_type, 3, 249.0, 4500, 18.0723,
    'SHA-256', '2024-06-01', TRUE, FALSE,
    'ASIC Miner Value: 261TH @ 4500W. Noise 50dB.', '{"asic_chip": "A15", "process_node": "4nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/avalon-a1566i"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A1566I (261 TH)', 'A1566I', 'Avalon15 Gen15',
    'immersion'::public.cooling_type, 3, 261.0, 4500, 17.2414,
    'SHA-256', '2024-07-01', TRUE, FALSE,
    '', '{"asic_chip": "A15", "process_node": "4nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A1566HA 2U (480 TH)', 'A1566HA', 'Avalon15 Gen15',
    'hydro'::public.cooling_type, 6, 480.0, 8064, 16.8,
    'SHA-256', '2025-08-01', TRUE, FALSE,
    '2U rack hydro form factor. 6 hashboards. Noise 40dB.', '{"asic_chip": "A15", "process_node": "4nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/avalon-a1566ha"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A15 (194 TH)', 'A15', 'Avalon15 Gen15',
    'air'::public.cooling_type, 3, 194.0, 3647, 18.799,
    'SHA-256', '2024-12-01', TRUE, FALSE,
    'Noise 75dB.', '{"asic_chip": "A15", "process_node": "4nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/a15-194t"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A15 Pro (218 TH)', 'A15 Pro', 'Avalon15 Gen15',
    'air'::public.cooling_type, 3, 218.0, 3662, 16.7982,
    'SHA-256', '2025-02-01', TRUE, FALSE,
    'Noise 75dB.', '{"asic_chip": "A15", "process_node": "4nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/a15pro-218t"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A15 Pro (221 TH)', 'A15 Pro', 'Avalon15 Gen15',
    'air'::public.cooling_type, 3, 221.0, 3662, 16.5701,
    'SHA-256', '2025-03-01', TRUE, FALSE,
    'Noise 75dB.', '{"asic_chip": "A15", "process_node": "4nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/a15pro-221t"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A15XP (206 TH)', 'A15XP', 'Avalon15 Gen15',
    'air'::public.cooling_type, 3, 206.0, 3667, 17.801,
    'SHA-256', '2024-12-01', TRUE, FALSE,
    'Noise 75dB.', '{"asic_chip": "A15", "process_node": "4nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/a15xp-206t"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A16 (282 TH)', 'A16', 'Avalon16 Gen16',
    'air'::public.cooling_type, 3, 282.0, 3900, 13.8298,
    'SHA-256', '2026-03-01', TRUE, FALSE,
    'Samsung process. Noise 75dB.', '{"asic_chip": "A16", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/a16-282t"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon A16XP (300 TH)', 'A16XP', 'Avalon16 Gen16',
    'air'::public.cooling_type, 3, 300.0, 3850, 12.8333,
    'SHA-256', '2026-04-01', TRUE, FALSE,
    'Noise 75dB.', '{"asic_chip": "A16", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/a16xp-300t"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon Nano 3', 'Nano 3', 'Consumer Line',
    'air'::public.cooling_type, 1, 4.0, 140, 35.0,
    'SHA-256', '2024-02-01', TRUE, FALSE,
    'USB-C, Wi-Fi, 10 integrated chips. Noise 35dB.', '{"asic_chip": "~A12", "process_node": "7nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/avalon-nano-3"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon Nano 3S', 'Nano 3S', 'Consumer Line',
    'air'::public.cooling_type, 1, 6.0, 140, 23.3333,
    'SHA-256', '2025-01-01', TRUE, FALSE,
    '50% more hashrate vs Nano 3. Noise 40dB.', '{"asic_chip": "Next-gen", "process_node": "~4nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/canaan"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon Mini 3', 'Mini 3', 'Consumer Line',
    'air'::public.cooling_type, 2, 37.5, 800, 21.3333,
    'SHA-256', '2025-01-01', TRUE, FALSE,
    '66 chips. Dual-use space heater form factor. Noise 55dB.', '{"asic_chip": "A15", "process_node": "4nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/avalon-mini-3"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'canaan'),
    'Avalon Q', 'Avalon Q', 'Consumer Line',
    'air'::public.cooling_type, 3, 90.0, 1674, 18.6,
    'SHA-256', '2025-04-01', TRUE, FALSE,
    'Rack-style home miner, LCD, app control. Noise 45dB.', '{"asic_chip": "A15", "process_node": "4nm", "sources": ["https://shop.canaan.io", "https://www.asicminervalue.com/manufacturers/canaan", "https://hashrateindex.com", "https://d-central.tech", "https://www.asicminervalue.com/miners/avalon-q"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitdeer'),
    'SealMiner A4 Ultra Hydro (886 TH)', 'A4 Ultra Hydro', 'SealMiner A4 Series',
    'hydro'::public.cooling_type, 4, 886.0, 8372, 9.4492,
    'SHA-256', '2026-05-01', TRUE, FALSE,
    'Noise 50dB.', '{"asic_chip": "SEAL04", "sources": ["https://www.bitdeer.com", "https://www.asicminervalue.com/manufacturers/bitdeer", "https://www.asicminervalue.com/miners/sealminer-a4-ultra-hydro"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitdeer'),
    'SealMiner A4 Pro Air (336 TH)', 'A4 Pro Air', 'SealMiner A4 Series',
    'air'::public.cooling_type, 3, 336.0, 3662, 10.8988,
    'SHA-256', '2026-05-01', TRUE, FALSE,
    'Noise 75dB.', '{"asic_chip": "SEAL04", "sources": ["https://www.bitdeer.com", "https://www.asicminervalue.com/manufacturers/bitdeer", "https://www.asicminervalue.com/miners/sealminer-a4-pro-air"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitdeer'),
    'SealMiner A4 Pro Hydro (680 TH)', 'A4 Pro Hydro', 'SealMiner A4 Series',
    'hydro'::public.cooling_type, 4, 680.0, 7412, 10.9,
    'SHA-256', '2026-05-01', TRUE, FALSE,
    'Noise 50dB.', '{"asic_chip": "SEAL04", "sources": ["https://www.bitdeer.com", "https://www.asicminervalue.com/manufacturers/bitdeer", "https://www.asicminervalue.com/miners/sealminer-a4-pro-hydro"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitdeer'),
    'SealMiner A3 Pro Air (290 TH)', 'A3 Pro Air', 'SealMiner A3 Series',
    'air'::public.cooling_type, 3, 290.0, 3625, 12.5,
    'SHA-256', '2025-09-01', TRUE, FALSE,
    'Noise 75dB.', '{"asic_chip": "SEAL03", "sources": ["https://www.bitdeer.com", "https://www.asicminervalue.com/manufacturers/bitdeer", "https://www.asicminervalue.com/miners/sealminer-a3-pro-air"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitdeer'),
    'SealMiner A3 Pro Hydro (660 TH)', 'A3 Pro Hydro', 'SealMiner A3 Series',
    'hydro'::public.cooling_type, 4, 660.0, 8250, 12.5,
    'SHA-256', '2025-09-01', TRUE, FALSE,
    'Noise 50dB.', '{"asic_chip": "SEAL03", "sources": ["https://www.bitdeer.com", "https://www.asicminervalue.com/manufacturers/bitdeer", "https://www.asicminervalue.com/miners/sealminer-a3-pro-hydro"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitdeer'),
    'SealMiner A3 Hydro (500 TH)', 'A3 Hydro', 'SealMiner A3 Series',
    'hydro'::public.cooling_type, 4, 500.0, 6750, 13.5,
    'SHA-256', '2025-09-01', TRUE, FALSE,
    'Noise 50dB.', '{"asic_chip": "SEAL03", "sources": ["https://www.bitdeer.com", "https://www.asicminervalue.com/manufacturers/bitdeer", "https://www.asicminervalue.com/miners/sealminer-a3-hydro"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitdeer'),
    'SealMiner A3 Air (260 TH)', 'A3 Air', 'SealMiner A3 Series',
    'air'::public.cooling_type, 3, 260.0, 3640, 14.0,
    'SHA-256', '2025-09-01', TRUE, FALSE,
    'Noise 75dB.', '{"asic_chip": "SEAL03", "sources": ["https://www.bitdeer.com", "https://www.asicminervalue.com/manufacturers/bitdeer", "https://www.asicminervalue.com/miners/sealminer-a3-air"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitdeer'),
    'SealMiner A2 Pro Air (255 TH)', 'A2 Pro Air', 'SealMiner A2 Series',
    'air'::public.cooling_type, 3, 255.0, 3790, 14.8627,
    'SHA-256', '2025-03-01', TRUE, FALSE,
    'Noise 75dB.', '{"asic_chip": "SEAL02", "sources": ["https://www.bitdeer.com", "https://www.asicminervalue.com/manufacturers/bitdeer", "https://www.asicminervalue.com/miners/sealminer-a2-pro-air"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitdeer'),
    'SealMiner A2 Pro Hyd (500 TH)', 'A2 Pro Hyd', 'SealMiner A2 Series',
    'hydro'::public.cooling_type, 4, 500.0, 7450, 14.9,
    'SHA-256', '2025-03-01', TRUE, FALSE,
    'Noise 50dB.', '{"asic_chip": "SEAL02", "sources": ["https://www.bitdeer.com", "https://www.asicminervalue.com/manufacturers/bitdeer", "https://www.asicminervalue.com/miners/sealminer-a2-pro-hyd"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitdeer'),
    'SealMiner A2 Hyd (446 TH)', 'A2 Hyd', 'SealMiner A2 Series',
    'hydro'::public.cooling_type, 4, 446.0, 7360, 16.5022,
    'SHA-256', '2025-02-01', TRUE, FALSE,
    'Noise 50dB.', '{"asic_chip": "SEAL02", "sources": ["https://www.bitdeer.com", "https://www.asicminervalue.com/manufacturers/bitdeer", "https://www.asicminervalue.com/miners/sealminer-a2-hyd"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitdeer'),
    'SealMiner A2 (226 TH)', 'A2', 'SealMiner A2 Series',
    'air'::public.cooling_type, 3, 226.0, 3730, 16.5044,
    'SHA-256', '2025-02-01', TRUE, FALSE,
    'Noise 75dB.', '{"asic_chip": "SEAL02", "sources": ["https://www.bitdeer.com", "https://www.asicminervalue.com/manufacturers/bitdeer", "https://www.asicminervalue.com/miners/sealminer-a2"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitdeer'),
    'SealMiner DL1 Air (179 TH)', 'DL1 Air', 'SealMiner DL1 Series',
    'air'::public.cooling_type, 3, 179.0, 3580, 20.0,
    'SHA-256', '2025-01-01', TRUE, FALSE,
    'First-gen SealMiner. Noise 75dB.', '{"asic_chip": "SEAL01", "sources": ["https://www.bitdeer.com", "https://www.asicminervalue.com/manufacturers/bitdeer", "https://www.asicminervalue.com/miners/sealminer-dl1-air"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'auradine'),
    'Auradine Teraflux AT2880 (180 TH)', 'AT2880', 'Teraflux Series',
    'air'::public.cooling_type, 3, 180.0, 2880, 16.0,
    'SHA-256', '2024-11-01', TRUE, FALSE,
    'Noise 70dB.', '{"sources": ["https://www.auradine.com", "https://www.asicminervalue.com/manufacturers/auradine", "https://www.asicminervalue.com/miners/teraflux-at2880"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'auradine'),
    'Auradine Teraflux AH3880 (600 TH)', 'AH3880', 'Teraflux Series',
    'hydro'::public.cooling_type, 2, 600.0, 10740, 17.9,
    'SHA-256', '2025-03-01', TRUE, FALSE,
    'Noise 35dB. Two hashboards confirmed (README.md, CLAUDE.md, miner_specs.json).', '{"sources": ["https://www.auradine.com", "https://www.asicminervalue.com/manufacturers/auradine", "https://www.asicminervalue.com/miners/teraflux-ah3880"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'auradine'),
    'Auradine Teraflux AI3680 (360 TH)', 'AI3680', 'Teraflux Series',
    'immersion'::public.cooling_type, 3, 360.0, 6840, 19.0,
    'SHA-256', '2024-12-01', TRUE, FALSE,
    'Noise 50dB.', '{"sources": ["https://www.auradine.com", "https://www.asicminervalue.com/manufacturers/auradine", "https://www.asicminervalue.com/miners/pascal"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'innosilicon'),
    'Innosilicon T2 Terminator (17.2 TH)', 'T2 Terminator', 'T2 Series',
    'air'::public.cooling_type, 3, 17.2, 1570, 91.2791,
    'SHA-256', '2018-05-01', FALSE, TRUE,
    'Noise 72dB.', '{"sources": ["https://www.innosilicon.com", "https://www.asicminervalue.com/manufacturers/innosilicon", "https://www.asicminervalue.com/miners/t2-terminator"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'innosilicon'),
    'Innosilicon T2 Turbo 25T', 'T2T 25T', 'T2 Turbo Series',
    'air'::public.cooling_type, 3, 25.0, 2100, 84.0,
    'SHA-256', '2019-01-01', FALSE, TRUE,
    'Noise 72dB.', '{"sources": ["https://www.innosilicon.com", "https://www.asicminervalue.com/manufacturers/innosilicon", "https://www.asicminervalue.com/miners/t2-turbo-25t"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'innosilicon'),
    'Innosilicon T2 Turbo 26T', 'T2T 26T', 'T2 Turbo Series',
    'air'::public.cooling_type, 3, 26.0, 2100, 80.7692,
    'SHA-256', '2021-07-01', FALSE, TRUE,
    'Noise 75dB.', '{"sources": ["https://www.innosilicon.com", "https://www.asicminervalue.com/manufacturers/innosilicon", "https://www.asicminervalue.com/miners/t2-turbo-26t"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'innosilicon'),
    'Innosilicon T2 Turbo 29T/30T', 'T2T 29T/30T', 'T2 Turbo Series',
    'air'::public.cooling_type, 3, 30.0, 2400, 80.0,
    'SHA-256', '2021-01-01', FALSE, TRUE,
    'Noise 72dB.', '{"sources": ["https://www.innosilicon.com", "https://www.asicminervalue.com/manufacturers/innosilicon", "https://www.asicminervalue.com/miners/t2-turbo-29t-30t"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'innosilicon'),
    'Innosilicon T2 Turbo+ 32T', 'T2T+ 32T', 'T2 Turbo Series',
    'air'::public.cooling_type, 3, 32.0, 2200, 68.75,
    'SHA-256', '2018-09-01', FALSE, TRUE,
    'Noise 72dB.', '{"sources": ["https://www.innosilicon.com", "https://www.asicminervalue.com/manufacturers/innosilicon", "https://www.asicminervalue.com/miners/t2-turbo-32t"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'innosilicon'),
    'Innosilicon T2 Turbo HF+ (33 TH)', 'T2T HF+', 'T2 Turbo Series',
    'air'::public.cooling_type, 3, 33.0, 2600, 78.7879,
    'SHA-256', '2021-07-01', FALSE, TRUE,
    'HF+ variant. Noise 72dB.', '{"sources": ["https://www.innosilicon.com", "https://www.asicminervalue.com/manufacturers/innosilicon", "https://www.asicminervalue.com/miners/t2-turbo-hf"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'innosilicon'),
    'Innosilicon T3 39T', 'T3 39T', 'T3 Series',
    'air'::public.cooling_type, 3, 39.0, 2150, 55.1282,
    'SHA-256', '2019-07-01', FALSE, TRUE,
    'Noise 75dB.', '{"sources": ["https://www.innosilicon.com", "https://www.asicminervalue.com/manufacturers/innosilicon", "https://www.asicminervalue.com/miners/t3-39t"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'innosilicon'),
    'Innosilicon T3+ 43T', 'T3+ 43T', 'T3 Series',
    'air'::public.cooling_type, 3, 43.0, 2100, 48.8372,
    'SHA-256', '2019-03-01', FALSE, TRUE,
    'Noise 72dB.', '{"sources": ["https://www.innosilicon.com", "https://www.asicminervalue.com/manufacturers/innosilicon", "https://www.asicminervalue.com/miners/t3-43t"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'innosilicon'),
    'Innosilicon T3 50T', 'T3 50T', 'T3 Series',
    'air'::public.cooling_type, 3, 52.0, 2800, 53.8462,
    'SHA-256', '2019-05-01', FALSE, TRUE,
    'AMV listed as 52TH@2800W. Noise 72dB.', '{"sources": ["https://www.innosilicon.com", "https://www.asicminervalue.com/manufacturers/innosilicon", "https://www.asicminervalue.com/miners/t3-50t"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'innosilicon'),
    'Innosilicon T3+ 52T', 'T3+ 52T', 'T3 Series',
    'air'::public.cooling_type, 3, 52.0, 3200, 61.5385,
    'SHA-256', '2018-09-01', FALSE, TRUE,
    'Noise 72dB.', '{"sources": ["https://www.innosilicon.com", "https://www.asicminervalue.com/manufacturers/innosilicon", "https://www.asicminervalue.com/miners/t3-52t"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'innosilicon'),
    'Innosilicon T3+ 57T', 'T3+ 57T', 'T3 Series',
    'air'::public.cooling_type, 3, 57.0, 3300, 57.8947,
    'SHA-256', '2019-07-01', FALSE, TRUE,
    'Noise 75dB.', '{"sources": ["https://www.innosilicon.com", "https://www.asicminervalue.com/manufacturers/innosilicon", "https://www.asicminervalue.com/miners/t3-57t"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'ebang'),
    'Ebang Ebit E9+ (9 TH)', 'E9+', 'Ebit E9 Series',
    'air'::public.cooling_type, 3, 9.0, 1300, 144.4444,
    'SHA-256', '2018-01-01', FALSE, TRUE,
    'Noise 75dB.', '{"sources": ["https://www.ebang.com.cn", "https://www.asicminervalue.com/manufacturers/ebang", "https://www.asicminervalue.com/miners/ebit-e9"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'ebang'),
    'Ebang Ebit E9.2 (12 TH)', 'E9.2', 'Ebit E9 Series',
    'air'::public.cooling_type, 3, 12.0, 1320, 110.0,
    'SHA-256', '2018-09-01', FALSE, TRUE,
    'Noise 75dB.', '{"sources": ["https://www.ebang.com.cn", "https://www.asicminervalue.com/manufacturers/ebang", "https://www.asicminervalue.com/miners/ebit-e9-2"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'ebang'),
    'Ebang Ebit E9.3 (16 TH)', 'E9.3', 'Ebit E9 Series',
    'air'::public.cooling_type, 3, 16.0, 1760, 110.0,
    'SHA-256', '2018-05-01', FALSE, TRUE,
    'Noise 72dB.', '{"sources": ["https://www.ebang.com.cn", "https://www.asicminervalue.com/manufacturers/ebang", "https://www.asicminervalue.com/miners/ebit-e9-3"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'ebang'),
    'Ebang Ebit E9i (13.5 TH)', 'E9i', 'Ebit E9 Series',
    'air'::public.cooling_type, 3, 13.5, 1420, 105.1852,
    'SHA-256', '2018-07-01', FALSE, TRUE,
    'Noise 74dB.', '{"sources": ["https://www.ebang.com.cn", "https://www.asicminervalue.com/manufacturers/ebang", "https://www.asicminervalue.com/miners/ebit-e9i"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'ebang'),
    'Ebang Ebit E10 (18 TH)', 'E10', 'Ebit E10 Series',
    'air'::public.cooling_type, 3, 18.0, 1650, 91.6667,
    'SHA-256', '2018-02-01', FALSE, TRUE,
    'Noise 75dB.', '{"sources": ["https://www.ebang.com.cn", "https://www.asicminervalue.com/manufacturers/ebang", "https://www.asicminervalue.com/miners/ebit-e10"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'ebang'),
    'Ebang Ebit E10D (25 TH)', 'E10D', 'Ebit E10 Series',
    'air'::public.cooling_type, 3, 25.0, 3500, 140.0,
    'SHA-256', '2021-09-01', FALSE, TRUE,
    'Noise 75dB.', '{"sources": ["https://www.ebang.com.cn", "https://www.asicminervalue.com/manufacturers/ebang", "https://www.asicminervalue.com/miners/ebit-e10d"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'ebang'),
    'Ebang Ebit E11 (30 TH)', 'E11', 'Ebit E11 Series',
    'air'::public.cooling_type, 3, 30.0, 1950, 65.0,
    'SHA-256', '2018-10-01', FALSE, TRUE,
    'Noise 75dB.', '{"sources": ["https://www.ebang.com.cn", "https://www.asicminervalue.com/manufacturers/ebang", "https://www.asicminervalue.com/miners/ebit-e11"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'ebang'),
    'Ebang Ebit E11++ (44 TH)', 'E11++', 'Ebit E11 Series',
    'air'::public.cooling_type, 3, 44.0, 1980, 45.0,
    'SHA-256', '2018-10-01', FALSE, TRUE,
    'Noise 75dB.', '{"sources": ["https://www.ebang.com.cn", "https://www.asicminervalue.com/manufacturers/ebang", "https://www.asicminervalue.com/miners/ebit-e11-2"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'ebang'),
    'Ebang Ebit E12 (44 TH)', 'E12', 'Ebit E12 Series',
    'air'::public.cooling_type, 3, 44.0, 2500, 56.8182,
    'SHA-256', '2019-09-01', FALSE, TRUE,
    'Noise 75dB.', '{"sources": ["https://www.ebang.com.cn", "https://www.asicminervalue.com/manufacturers/ebang", "https://www.asicminervalue.com/miners/ebit-e12"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'ebang'),
    'Ebang Ebit E12+ (50 TH)', 'E12+', 'Ebit E12 Series',
    'air'::public.cooling_type, 3, 50.0, 2500, 50.0,
    'SHA-256', '2019-09-01', FALSE, TRUE,
    'Noise 75dB.', '{"sources": ["https://www.ebang.com.cn", "https://www.asicminervalue.com/manufacturers/ebang", "https://www.asicminervalue.com/miners/ebit-e12-1"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'strongu'),
    'StrongU Hornbill H8 Pro (84 TH)', 'H8 Pro', 'Hornbill H8 Series',
    'air'::public.cooling_type, 3, 84.0, 3360, 40.0,
    'SHA-256', '2021-07-01', FALSE, TRUE,
    'Noise 76dB.', '{"sources": ["https://www.strongu.com.cn", "https://www.asicminervalue.com/manufacturers/strongu", "https://www.asicminervalue.com/miners/hornbill-h8-pro"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'strongu'),
    'StrongU Hornbill H8 (74 TH)', 'H8', 'Hornbill H8 Series',
    'air'::public.cooling_type, 3, 74.0, 3330, 45.0,
    'SHA-256', '2020-10-01', FALSE, TRUE,
    'Noise 76dB.', '{"sources": ["https://www.strongu.com.cn", "https://www.asicminervalue.com/manufacturers/strongu", "https://www.asicminervalue.com/miners/hornbill-h8"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'strongu'),
    'StrongU STU-U1 (44 TH)', 'STU-U1', 'STU-U Series',
    'air'::public.cooling_type, 3, 44.0, 2200, 50.0,
    'SHA-256', '2019-10-01', FALSE, TRUE,
    'Noise 76dB.', '{"sources": ["https://www.strongu.com.cn", "https://www.asicminervalue.com/manufacturers/strongu", "https://www.asicminervalue.com/miners/stu-u1"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'strongu'),
    'StrongU STU-U1+ (52 TH)', 'STU-U1+', 'STU-U Series',
    'air'::public.cooling_type, 3, 52.0, 2200, 42.3077,
    'SHA-256', '2019-11-01', FALSE, TRUE,
    'Noise 76dB.', '{"sources": ["https://www.strongu.com.cn", "https://www.asicminervalue.com/manufacturers/strongu", "https://www.asicminervalue.com/miners/stu-u1-1"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'strongu'),
    'StrongU STU-U1++ (60 TH)', 'STU-U1++', 'STU-U Series',
    'air'::public.cooling_type, 3, 60.0, 2800, 46.6667,
    'SHA-256', '2019-07-01', FALSE, TRUE,
    'Noise 76dB.', '{"sources": ["https://www.strongu.com.cn", "https://www.asicminervalue.com/manufacturers/strongu", "https://www.asicminervalue.com/miners/stu-u1-2"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'strongu'),
    'StrongU STU-U2 (74 TH)', 'STU-U2', 'STU-U Series',
    'air'::public.cooling_type, 3, 74.0, 3330, 45.0,
    'SHA-256', '2020-10-01', FALSE, TRUE,
    'Noise 76dB.', '{"sources": ["https://www.strongu.com.cn", "https://www.asicminervalue.com/manufacturers/strongu", "https://www.asicminervalue.com/miners/stu-u2"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'strongu'),
    'StrongU STU-U6 (84 TH)', 'STU-U6', 'STU-U Series',
    'air'::public.cooling_type, 3, 84.0, 3360, 40.0,
    'SHA-256', '2021-07-01', FALSE, TRUE,
    'Noise 76dB.', '{"sources": ["https://www.strongu.com.cn", "https://www.asicminervalue.com/manufacturers/strongu", "https://www.asicminervalue.com/miners/stu-u6"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'strongu'),
    'StrongU STU-U8 (46 TH)', 'STU-U8', 'STU-U Series',
    'air'::public.cooling_type, 3, 46.0, 2100, 45.6522,
    'SHA-256', '2019-07-01', FALSE, TRUE,
    'Noise 76dB.', '{"sources": ["https://www.strongu.com.cn", "https://www.asicminervalue.com/manufacturers/strongu", "https://www.asicminervalue.com/miners/stu-u8"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'strongu'),
    'StrongU STU-U8 Pro (60 TH)', 'STU-U8 Pro', 'STU-U Series',
    'air'::public.cooling_type, 3, 60.0, 2800, 46.6667,
    'SHA-256', '2019-09-01', FALSE, TRUE,
    'Noise 76dB.', '{"sources": ["https://www.strongu.com.cn", "https://www.asicminervalue.com/manufacturers/strongu", "https://www.asicminervalue.com/miners/stu-u8-pro"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitfury'),
    'Bitfury B8 (49 TH)', 'B8', 'Bitfury B-Series',
    'air'::public.cooling_type, 8, 49.0, 6400, 130.6122,
    'SHA-256', '2017-12-01', FALSE, TRUE,
    '8 hashboards, enterprise miner. Noise 85dB.', '{"asic_chip": "BF8301V", "process_node": "16nm", "sources": ["https://bitfury.com", "https://www.asicminervalue.com/manufacturers/bitfury", "https://www.asicminervalue.com/miners/b8"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitfury'),
    'Bitfury Tardis (80 TH)', 'Tardis', 'Bitfury Tardis Series',
    'air'::public.cooling_type, 8, 80.0, 6300, 78.75,
    'SHA-256', '2018-11-01', FALSE, TRUE,
    'Enterprise miner. Noise 75dB.', '{"asic_chip": "BF8301V", "process_node": "16nm", "sources": ["https://bitfury.com", "https://www.asicminervalue.com/manufacturers/bitfury", "https://www.asicminervalue.com/miners/tardis"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'halong'),
    'Halong Mining DragonMint T1 (16 TH)', 'DragonMint T1', 'DragonMint Series',
    'air'::public.cooling_type, 3, 16.0, 1480, 92.5,
    'SHA-256', '2018-03-01', FALSE, TRUE,
    'Company went silent after 2018. First SHA-256 miner to challenge Bitmain directly.', '{"asic_chip": "DM8575", "process_node": "16nm", "sources": ["https://halongmining.com", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'kncminer'),
    'KnCMiner Neptune (3 TH)', 'Neptune', 'KnC Neptune Series',
    'air'::public.cooling_type, 1, 3.0, 2100, 700.0,
    'SHA-256', '2014-01-01', FALSE, TRUE,
    'Defunct company (2016). 28nm chip.', '{"process_node": "28nm", "sources": ["https://en.bitcoin.it/wiki/KnCMiner", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'kncminer'),
    'KnCMiner Titan (300 GH/s)', 'Titan', 'KnC Titan Series',
    'air'::public.cooling_type, 1, 0.3, 250, 833.3333,
    'SHA-256', '2013-01-01', FALSE, TRUE,
    'Defunct company (2016).', '{"process_node": "28nm", "sources": ["https://en.bitcoin.it/wiki/KnCMiner", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'kncminer'),
    'KnCMiner Solar (400 GH/s)', 'Solar', 'KnC Solar Series',
    'air'::public.cooling_type, 1, 0.4, 250, 625.0,
    'SHA-256', '2014-01-01', FALSE, TRUE,
    'Defunct company (2016). Solar series.', '{"process_node": "28nm", "sources": ["https://en.bitcoin.it/wiki/KnCMiner", "https://hashrateindex.com"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'spondoolies'),
    'Spondoolies-Tech SP20 Jackson (1.3 TH)', 'SP20', 'SP Series',
    'air'::public.cooling_type, 2, 1.3, 1100, 846.1538,
    'SHA-256', '2014-01-01', FALSE, TRUE,
    'Defunct company (2016).', '{"process_node": "28nm", "sources": ["https://en.bitcoin.it/wiki/Spondoolies-Tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'spondoolies'),
    'Spondoolies-Tech SP31 Yukon (4.6 TH)', 'SP31', 'SP Series',
    'air'::public.cooling_type, 4, 4.6, 2400, 521.7391,
    'SHA-256', '2015-01-01', FALSE, TRUE,
    'Defunct company (2016).', '{"process_node": "28nm", "sources": ["https://en.bitcoin.it/wiki/Spondoolies-Tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'spondoolies'),
    'Spondoolies-Tech SP35 Yukon (5.5 TH)', 'SP35', 'SP Series',
    'air'::public.cooling_type, 4, 5.5, 3500, 636.3636,
    'SHA-256', '2016-01-01', FALSE, TRUE,
    'Defunct company (2016).', '{"process_node": "28nm", "sources": ["https://en.bitcoin.it/wiki/Spondoolies-Tech"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'butterfly_labs'),
    'Butterfly Labs Jalapeno (7 GH/s)', 'Jalapeno', 'BFL Legacy',
    'air'::public.cooling_type, 1, 0.007, 7, 1000.0,
    'SHA-256', '2013-01-01', FALSE, TRUE,
    'Defunct/sued by FTC. First consumer SHA-256 ASIC.', '{"process_node": "65nm", "sources": ["https://en.bitcoin.it/wiki/Butterfly_Labs"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'butterfly_labs'),
    'Butterfly Labs Single SC (60 GH/s)', 'Single SC', 'BFL Legacy',
    'air'::public.cooling_type, 1, 0.06, 60, 1000.0,
    'SHA-256', '2013-01-01', FALSE, TRUE,
    'Defunct/sued by FTC.', '{"process_node": "65nm", "sources": ["https://en.bitcoin.it/wiki/Butterfly_Labs"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'butterfly_labs'),
    'Butterfly Labs Monarch (700 GH/s)', 'Monarch', 'BFL Monarch',
    'air'::public.cooling_type, 2, 0.7, 350, 500.0,
    'SHA-256', '2014-01-01', FALSE, TRUE,
    'Defunct/sued by FTC. Final BFL product.', '{"process_node": "28nm", "sources": ["https://en.bitcoin.it/wiki/Butterfly_Labs"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitaxe'),
    'Bitaxe Gamma 602 (1.07 TH)', 'Gamma 602', 'Bitaxe Gamma',
    'air'::public.cooling_type, 1, 1.07, 17.8, 16.6355,
    'SHA-256', '2024-08-01', TRUE, FALSE,
    'Single-chip BM1370. Most popular Bitaxe — solo-mining lottery hardware. ESP-Miner firmware.', '{"asic_chip": "BM1370", "process_node": "5nm", "sources": ["https://bitaxe.org", "https://github.com/bitaxeorg", "https://www.solosatoshi.com/bitaxe-overclocking-guide/", "https://www.zeusbtc.com/blog/details/5694-bm1366-vs-bm1370-asic-chips"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitaxe'),
    'Bitaxe Gamma Duo 650 (1.63 TH)', 'Gamma Duo 650', 'Bitaxe Gamma Duo',
    'air'::public.cooling_type, 1, 1.63, 25.8, 15.8282,
    'SHA-256', '2025-09-01', TRUE, FALSE,
    'Dual BM1370 on single PCB. ~16 J/TH — most efficient Bitaxe to date.', '{"asic_chip": "BM1370 (x2)", "process_node": "5nm", "sources": ["https://bitaxe.org", "https://github.com/bitaxeorg", "https://www.solosatoshi.com/bitaxe-overclocking-guide/", "https://www.zeusbtc.com/blog/details/5694-bm1366-vs-bm1370-asic-chips"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitaxe'),
    'Bitaxe GT 801 (2.15 TH)', 'GT 801', 'Bitaxe GT',
    'air'::public.cooling_type, 1, 2.15, 43.0, 20.0,
    'SHA-256', '2025-10-01', TRUE, FALSE,
    'Dual BM1370 high-output variant. 80mm fan + larger heatsink.', '{"asic_chip": "BM1370 (x2)", "process_node": "5nm", "sources": ["https://bitaxe.org", "https://github.com/bitaxeorg", "https://www.solosatoshi.com/bitaxe-overclocking-guide/", "https://www.zeusbtc.com/blog/details/5694-bm1366-vs-bm1370-asic-chips"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitaxe'),
    'Bitaxe Turbo Touch (2.15 TH)', 'Turbo Touch', 'Bitaxe Turbo',
    'air'::public.cooling_type, 1, 2.15, 43.0, 20.0,
    'SHA-256', '2025-10-01', TRUE, FALSE,
    'Dual BM1370 with integrated touchscreen UI. Same hashrate as GT 801.', '{"asic_chip": "BM1370 (x2)", "process_node": "5nm", "sources": ["https://bitaxe.org", "https://github.com/bitaxeorg", "https://www.solosatoshi.com/bitaxe-overclocking-guide/", "https://www.zeusbtc.com/blog/details/5694-bm1366-vs-bm1370-asic-chips"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitaxe'),
    'Bitaxe Supra 400 (0.65 TH)', 'Supra 400', 'Bitaxe Supra',
    'air'::public.cooling_type, 1, 0.65, 12.0, 18.4615,
    'SHA-256', '2024-06-01', FALSE, TRUE,
    'Single BM1368 from S21 hashboards. Superseded by Gamma 602.', '{"asic_chip": "BM1368", "process_node": "5nm", "sources": ["https://bitaxe.org", "https://github.com/bitaxeorg", "https://www.solosatoshi.com/bitaxe-overclocking-guide/", "https://www.zeusbtc.com/blog/details/5694-bm1366-vs-bm1370-asic-chips"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitaxe'),
    'Bitaxe Ultra 200 (0.50 TH)', 'Ultra 200', 'Bitaxe Ultra',
    'air'::public.cooling_type, 1, 0.5, 12.0, 24.0,
    'SHA-256', '2023-08-01', FALSE, TRUE,
    'Single BM1366 from S19 XP hashboards. First widely-cloned Bitaxe design.', '{"asic_chip": "BM1366", "process_node": "5nm", "sources": ["https://bitaxe.org", "https://github.com/bitaxeorg", "https://www.solosatoshi.com/bitaxe-overclocking-guide/", "https://www.zeusbtc.com/blog/details/5694-bm1366-vs-bm1370-asic-chips"]}'::jsonb, 'high'
);
INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = 'bitaxe'),
    'Bitaxe Hex 700 (3.0 TH)', 'Hex 700', 'Bitaxe Hex',
    'air'::public.cooling_type, 1, 3.0, 70.0, 23.3333,
    'SHA-256', '2023-12-01', FALSE, TRUE,
    'Six BM1366 chips on a single PCB — highest-output legacy Bitaxe.', '{"asic_chip": "BM1366 (x6)", "process_node": "5nm", "sources": ["https://bitaxe.org", "https://github.com/bitaxeorg", "https://www.solosatoshi.com/bitaxe-overclocking-guide/", "https://www.zeusbtc.com/blog/details/5694-bm1366-vs-bm1370-asic-chips"]}'::jsonb, 'high'
);

COMMIT;
