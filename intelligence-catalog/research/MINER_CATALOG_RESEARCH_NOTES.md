# Mining Intelligence Catalog — Miner Research Notes

**Date:** April 11, 2026
**Researcher:** Computer (automated), directed by Bobby Fiesler
**Scope:** Every known Bitcoin SHA-256 ASIC miner ever manufactured, with every variant captured as a separate entry.

---

## What Was Done

### Phase 1 — Broad Manufacturer Research
Researched all known Bitcoin SHA-256 ASIC miner manufacturers in parallel:
- Bitmain (Antminer S/T series)
- MicroBT (Whatsminer M series)
- Canaan (Avalon series)
- Auradine (Teraflux series)
- Innosilicon (T2/T3 series)
- Ebang (Ebit E series)
- StrongU (STU-U/Hornbill series)
- Bitfury (B8, Tardis)
- Bitdeer (SealMiner A/DL series)
- Historical/defunct: KnCMiner, Spondoolies-Tech, Butterfly Labs, Halong Mining

### Phase 2 — Deep-Dive Variant Research
For the three major manufacturers (Bitmain, MicroBT, Canaan), ran dedicated deep-dive research that went model by model, series by series, capturing every hashrate bin, cooling variant, and suffix (+, ++, Pro, XP, Hydro, Immersion, 3U) as a separate entry.

Sources consulted per manufacturer:
- Official manufacturer websites and support pages
- ASIC Miner Value (efficiency ranking + manufacturer pages)
- Hashrate Index (machine list + profitability guides)
- D-Central Technologies (repair guides and spec pages)
- BT-Miners, CryptoMinerBros, Apexto Mining, Zeus Mining (reseller listings)
- ASIC Marketplace, Mining Wholesale, Viperatech, X-ON Mining
- Bitcoin Wiki (historical hardware comparison)
- BitcoinTalk forum threads (early model reviews)
- MiningNow, Crazy-Mining, WhatToMine

### Phase 3 — Cross-Reference
Extracted the complete SHA-256 miner list from ASIC Miner Value (203 models across 9 manufacturers). Cross-referenced against all deep-dive files to identify:
- Models present in ASIC Miner Value but missing from deep-dive files
- Additional hashrate bins not captured
- Noise levels (dB) only available from ASIC Miner Value
- New manufacturer discovered: Bitdeer/SealMiner (12 models, all 2025-2026)

### Phase 4 — Compilation
Merged all sources into a unified Python data structure, deduplicated, and generated:
- Master CSV (all_bitcoin_sha256_miners.csv) — 313 rows, 15 columns
- PostgreSQL seed SQL (seed_miner_models.sql) — 313 INSERT statements mapped to hardware.miner_models schema

---

## What Was Found

### Final Count: 313 Distinct Miner Variants

| Manufacturer | Count | Era | Notable |
|---|---|---|---|
| Bitmain | 114 | 2013–2026 | S1 through S23, T9 through T21, R4, S7-LN |
| MicroBT | 78 | 2017–2026 | M1 through M7D series, all cooling variants |
| Canaan | 64 | 2013–2026 | Avalon1 through A16XP, Nano/Mini/Q consumer line |
| Bitdeer | 12 | 2025–2026 | SealMiner DL1 through A4 Ultra, SEAL01/02 chips |
| Innosilicon | 11 | 2018–2021 | T2 Terminator through T3+ 57T |
| Ebang | 10 | 2018–2021 | Ebit E9+ through E12+ |
| StrongU | 9 | 2019–2021 | STU-U1 through U8 Pro, Hornbill H8/H8 Pro |
| Auradine | 3 | 2024–2025 | Teraflux AT2880, AH3880, AI3680 |
| KnCMiner | 3 | 2014–2015 | Neptune, Titan, Solar — defunct 2016 |
| Spondoolies | 3 | 2015–2016 | SP20, SP31, SP35 — defunct 2016 |
| Butterfly Labs | 3 | 2013–2014 | Jalapeno, Single SC, Monarch — FTC shutdown |
| Bitfury | 2 | 2017–2018 | B8, Tardis |
| Halong Mining | 1 | 2018 | DragonMint T1 — company went silent |

### Cooling Breakdown
- Air-cooled: 229 models (73%)
- Hydro-cooled: 58 models (19%)
- Immersion-cooled: 26 models (8%)

### Status
- Currently in production/sold new: 97 models
- Discontinued or end-of-life: 216 models

### Efficiency Range
- Best efficiency: 9.45 J/TH (SealMiner A4 Ultra Hydro, May 2026)
- Worst efficiency: ~9,394 J/TH (Avalon1 Batch 1, 2013)
- Range spans 3 orders of magnitude across 13 years of hardware evolution

### Technology Progression
- 2013: 110nm / 55nm chips, sub-1 TH/s
- 2014–2015: 40nm / 28nm, 1–4 TH/s
- 2016–2018: 16nm, 4–18 TH/s
- 2019–2020: 7nm, 40–112 TH/s
- 2021–2023: 7nm refined / 5nm, 84–260 TH/s
- 2024–2025: 5nm / 4nm / 3nm, 180–860 TH/s
- 2026: ~3nm, up to 1,160 TH/s (S23 Hydro 3U)

---

## Schema Notes

### Enum Updates Required
Before running seed_miner_models.sql, the `manufacturer_brand` enum needs these additions:
- innosilicon
- bitdeer
- kncminer
- spondoolies
- butterfly_labs
- halong

The existing enum already has: bitmain, microbt, auradine, canaan, jasminer, strongu, ebang, bitfury, iceriver, goldshell, other, unknown.

### Metadata Column Usage
Each INSERT populates the JSONB `metadata` column with:
- `asic_chip`: The specific ASIC chip model (e.g., "BM1387", "A3212")
- `process_node`: Fabrication process (e.g., "16nm", "7nm", "5nm")
- `sources`: Array of source URLs used to verify this model's data

### Primary Source Dependency
The `primary_source_id` column (required FK to `knowledge.sources`) is NOT set in the seed SQL because source rows don't exist yet. This column needs to be populated after creating source entries in the `knowledge.sources` table, or the FK constraint needs to be deferred/dropped for initial seeding.

**Workaround options:**
1. Create source entries first, then UPDATE miner_models to set primary_source_id
2. ALTER the constraint to be DEFERRABLE INITIALLY DEFERRED
3. Temporarily drop the NOT NULL constraint, seed, then restore

---

## Known Gaps

1. **Chip details for Gen 7 MicroBT (M70/M73/M76/M78/M79/M7D):** Chip name and process node not yet publicly disclosed by MicroBT. Marked as "—" in data.

2. **Canaan A16 process node:** Samsung foundry confirmed, but exact process node not yet disclosed. Marked as "TBD (Samsung)."

3. **Bitdeer/SealMiner chip details:** SEAL01 and SEAL02 chip names confirmed from press coverage, but process nodes for individual models not fully mapped.

4. **Historical models with approximate specs:** Avalon1 batch variants, Butterfly Labs models, KnCMiner models — specs sourced from Bitcoin Wiki and may have rounding. Marked as confidence 'medium' where applicable.

5. **Bitmain S21 Immersion:** Listed as a range (215–301 TH) because multiple firmware-selectable hashrate modes exist. The ASIC Miner Value listing at 301 TH is the high end.

6. **MicroBT M50S++ release date ambiguity:** Some databases show Dec 2020, but the primary release was 2023. Used 2023 in our data.

7. **Missing from all sources:** Some very early miners (2011–2012 FPGA-to-ASIC transition devices) may exist but are not SHA-256 specific or were never mass-produced. Not included.

8. **StrongU rebranding:** The Hornbill H8 and H8 Pro appear to be rebrands of STU-U2 and STU-U6 respectively (same specs). Both are kept as separate entries since ASIC Miner Value lists them separately and some operators may know them by either name.

9. **Noise levels (dB):** Available from ASIC Miner Value for many models. Included in notes field where available but not a dedicated CSV column. Could be added to metadata JSONB in a future pass.

---

## Files Produced

| File | Description | Rows |
|---|---|---|
| all_bitcoin_sha256_miners.csv | Master CSV with all 313 variants, 15 columns | 313 |
| seed_miner_models.sql | PostgreSQL INSERT statements for hardware.miner_models | 313 |
| compile_all_miners.py | Python script that generates both outputs | — |
| bitmain_all_variants.md | Deep-dive: 94 Bitmain variants | — |
| microbt_all_variants.md | Deep-dive: 86 MicroBT variants (actually 78 after dedup) | — |
| canaan_all_variants.md | Deep-dive: 64 Canaan variants | — |
| asicminervalue_all_sha256.md | Cross-reference: 203 models from ASIC Miner Value | — |
| MINER_CATALOG_RESEARCH_NOTES.md | This document | — |

---

*This research forms the foundation of the Mining Intelligence Catalog seed data for Mining Guardian. The data should be treated as a living dataset — new models are announced quarterly, and existing models receive firmware updates that change performance characteristics.*
