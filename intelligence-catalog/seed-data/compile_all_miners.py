#!/usr/bin/env python3
"""
Mining Intelligence Catalog — Compile All Bitcoin SHA-256 ASIC Miners
Author: Mining Guardian
Date: 2026-04-11
Sources: bitmain_all_variants.md, microbt_all_variants.md, canaan_all_variants.md,
         asicminervalue_all_sha256.md
"""

import csv
import io
import uuid
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# MASTER DATA STRUCTURE
# Each dict represents one distinct miner variant row.
# Fields: manufacturer, canonical_name, model_number, generation, cooling_type,
#         hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
#         asic_chip, process_node, release_date, is_current_product, notes, source_urls
# ─────────────────────────────────────────────────────────────────────────────

def eff(hashrate, power):
    """Calculate efficiency J/TH, return None if inputs are None/0."""
    if hashrate and power and hashrate > 0:
        return round(power / hashrate, 2)
    return None

ALL_MINERS = []

# ═══════════════════════════════════════════════════════════════════════════════
# BITMAIN — ~107 variants (deep-dive 94 + ASIC Miner Value extras)
# ═══════════════════════════════════════════════════════════════════════════════

BITMAIN_SOURCES = "https://support.bitmain.com,https://www.asicminervalue.com/manufacturers/bitmain,https://d-central.tech,https://hashrateindex.com"

# ── Generation 1: Legacy S1–S9 series ─────────────────────────────────────────

ALL_MINERS += [
    # S1
    dict(manufacturer="bitmain", canonical_name="Antminer S1", model_number="S1",
         generation="S1-S5 Legacy", cooling_type="air", hashboard_count=4,
         stock_hashrate_th=0.18, stock_power_w=360, stock_efficiency_j_th=eff(0.18, 360),
         asic_chip="BM1380", process_node="55nm", release_date="2013-01-01",
         is_current_product=False, notes="First-gen Antminer. 55nm chip.", source_urls=BITMAIN_SOURCES),
    # S2
    dict(manufacturer="bitmain", canonical_name="Antminer S2", model_number="S2",
         generation="S1-S5 Legacy", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=1.00, stock_power_w=1000, stock_efficiency_j_th=eff(1.0, 1000),
         asic_chip="BM1382", process_node="55nm", release_date="2014-01-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    # S3
    dict(manufacturer="bitmain", canonical_name="Antminer S3", model_number="S3",
         generation="S1-S5 Legacy", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=0.478, stock_power_w=366, stock_efficiency_j_th=eff(0.478, 366),
         asic_chip="BM1382", process_node="55nm", release_date="2014-01-01",
         is_current_product=False, notes="478 GH/s", source_urls=BITMAIN_SOURCES),
    # S4
    dict(manufacturer="bitmain", canonical_name="Antminer S4", model_number="S4",
         generation="S1-S5 Legacy", cooling_type="air", hashboard_count=4,
         stock_hashrate_th=2.00, stock_power_w=1400, stock_efficiency_j_th=eff(2.0, 1400),
         asic_chip="BM1384", process_node="28nm", release_date="2014-01-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    # S5
    dict(manufacturer="bitmain", canonical_name="Antminer S5", model_number="S5",
         generation="S1-S5 Legacy", cooling_type="air", hashboard_count=1,
         stock_hashrate_th=1.155, stock_power_w=590, stock_efficiency_j_th=eff(1.155, 590),
         asic_chip="BM1384", process_node="28nm", release_date="2014-12-01",
         is_current_product=False, notes="ASIC Miner Value: 1.2 TH/s @ 590W listed (slight rounding variant). Noise 65dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s5"),
    # S5+
    dict(manufacturer="bitmain", canonical_name="Antminer S5+", model_number="S5+",
         generation="S1-S5 Legacy", cooling_type="air", hashboard_count=4,
         stock_hashrate_th=7.722, stock_power_w=3150, stock_efficiency_j_th=eff(7.722, 3150),
         asic_chip="BM1384", process_node="28nm", release_date="2016-06-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    # S7
    dict(manufacturer="bitmain", canonical_name="Antminer S7", model_number="S7",
         generation="S7 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=4.73, stock_power_w=1293, stock_efficiency_j_th=eff(4.73, 1293),
         asic_chip="BM1385", process_node="28nm", release_date="2015-08-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    # S7-LN (Low Noise variant — from ASIC Miner Value)
    dict(manufacturer="bitmain", canonical_name="Antminer S7-LN", model_number="S7-LN",
         generation="S7 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=2.7, stock_power_w=697, stock_efficiency_j_th=eff(2.7, 697),
         asic_chip="BM1385", process_node="28nm", release_date="2016-06-01",
         is_current_product=False, notes="Low-noise variant of S7. Noise 48dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s7-ln"),
    # S9 11.5 TH
    dict(manufacturer="bitmain", canonical_name="Antminer S9 (11.5 TH)", model_number="S9",
         generation="S9 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=11.5, stock_power_w=1127, stock_efficiency_j_th=98.0,
         asic_chip="BM1387", process_node="16nm", release_date="2016-06-01",
         is_current_product=False, notes="Noise 85dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s9-11-5th"),
    # S9 12.5 TH
    dict(manufacturer="bitmain", canonical_name="Antminer S9 (12.5 TH)", model_number="S9",
         generation="S9 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=12.5, stock_power_w=1225, stock_efficiency_j_th=98.0,
         asic_chip="BM1387", process_node="16nm", release_date="2017-02-01",
         is_current_product=False, notes="Noise 85dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s9-12-5th"),
    # S9 13.0 TH
    dict(manufacturer="bitmain", canonical_name="Antminer S9 (13.0 TH)", model_number="S9",
         generation="S9 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=13.0, stock_power_w=1274, stock_efficiency_j_th=98.0,
         asic_chip="BM1387", process_node="16nm", release_date="2017-08-01",
         is_current_product=False, notes="ASIC Miner Value lists 13TH @ 1300W (100 J/TH) for some batches. Noise 85dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s9-13th"),
    # S9 13.5 TH
    dict(manufacturer="bitmain", canonical_name="Antminer S9 (13.5 TH)", model_number="S9",
         generation="S9 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=13.5, stock_power_w=1323, stock_efficiency_j_th=98.0,
         asic_chip="BM1387", process_node="16nm", release_date="2017-09-01",
         is_current_product=False, notes="Noise 85dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s9-13-5th"),
    # S9 14.0 TH
    dict(manufacturer="bitmain", canonical_name="Antminer S9 (14.0 TH)", model_number="S9",
         generation="S9 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=14.0, stock_power_w=1372, stock_efficiency_j_th=98.0,
         asic_chip="BM1387", process_node="16nm", release_date="2017-11-01",
         is_current_product=False, notes="Noise 85dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s9-14th"),
    # S9i 13.0 TH
    dict(manufacturer="bitmain", canonical_name="Antminer S9i (13.0 TH)", model_number="S9i",
         generation="S9 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=13.0, stock_power_w=1280, stock_efficiency_j_th=eff(13.0, 1280),
         asic_chip="BM1387", process_node="16nm", release_date="2018-05-01",
         is_current_product=False, notes="ASIC Miner Value: 13TH @ 1290W listed. Noise 76dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/sha-256"),
    # S9i 13.5 TH
    dict(manufacturer="bitmain", canonical_name="Antminer S9i (13.5 TH)", model_number="S9i",
         generation="S9 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=13.5, stock_power_w=1310, stock_efficiency_j_th=eff(13.5, 1310),
         asic_chip="BM1387", process_node="16nm", release_date="2018-05-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    # S9i 14.0 TH
    dict(manufacturer="bitmain", canonical_name="Antminer S9i (14.0 TH)", model_number="S9i",
         generation="S9 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=14.0, stock_power_w=1320, stock_efficiency_j_th=eff(14.0, 1320),
         asic_chip="BM1387", process_node="16nm", release_date="2018-05-01",
         is_current_product=False, notes="ASIC Miner Value: 14TH @ 1320W, 94.29 J/TH. Noise 76dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s9i-14th"),
    # S9i 14.5 TH
    dict(manufacturer="bitmain", canonical_name="Antminer S9i (14.5 TH)", model_number="S9i",
         generation="S9 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=14.5, stock_power_w=1365, stock_efficiency_j_th=eff(14.5, 1365),
         asic_chip="BM1387", process_node="16nm", release_date="2018-05-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    # S9j 14.0 TH
    dict(manufacturer="bitmain", canonical_name="Antminer S9j (14.0 TH)", model_number="S9j",
         generation="S9 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=14.0, stock_power_w=1314, stock_efficiency_j_th=eff(14.0, 1314),
         asic_chip="BM1387BE/BF", process_node="16nm", release_date="2018-08-01",
         is_current_product=False, notes="j = bin-selected variant with BM1387BE/BF chips.", source_urls=BITMAIN_SOURCES),
    # S9j 14.5 TH
    dict(manufacturer="bitmain", canonical_name="Antminer S9j (14.5 TH)", model_number="S9j",
         generation="S9 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=14.5, stock_power_w=1350, stock_efficiency_j_th=eff(14.5, 1350),
         asic_chip="BM1387BE/BF", process_node="16nm", release_date="2018-08-01",
         is_current_product=False, notes="Noise 76dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s9j-14-5th"),
    # S9 Hydro
    dict(manufacturer="bitmain", canonical_name="Antminer S9 Hydro", model_number="S9 Hydro",
         generation="S9 Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=18.0, stock_power_w=1728, stock_efficiency_j_th=96.0,
         asic_chip="BM1387", process_node="16nm", release_date="2018-08-01",
         is_current_product=False, notes="Water-cooled variant. 4 hashboards.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s9-hydro-18th"),
    # S9k 13.5 TH
    dict(manufacturer="bitmain", canonical_name="Antminer S9k (13.5 TH)", model_number="S9k",
         generation="S9 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=13.5, stock_power_w=1148, stock_efficiency_j_th=eff(13.5, 1148),
         asic_chip="BM1393B", process_node="16nm", release_date="2019-08-01",
         is_current_product=False, notes="ASIC Miner Value: 13.5TH @ 1310W (97.04 J/TH) listed. Noise 76dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s9k-13-5th"),
    # S9 SE 16 TH
    dict(manufacturer="bitmain", canonical_name="Antminer S9 SE (16 TH)", model_number="S9 SE",
         generation="S9 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=16.0, stock_power_w=1280, stock_efficiency_j_th=80.0,
         asic_chip="BM1393CE", process_node="16nm", release_date="2019-07-01",
         is_current_product=False, notes="Noise 76dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s9-se-16th"),
]

# ── R4 ──────────────────────────────────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="bitmain", canonical_name="Antminer R4", model_number="R4",
         generation="R4 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=8.7, stock_power_w=845, stock_efficiency_j_th=eff(8.7, 845),
         asic_chip="BM1387B/BL", process_node="16nm", release_date="2017-02-01",
         is_current_product=False, notes="Home/quiet miner. Noise 52dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/scc-siaclassic"),
]

# ── S11 ──────────────────────────────────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="bitmain", canonical_name="Antminer S11 (20.5 TH)", model_number="S11",
         generation="S11 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=20.5, stock_power_w=1530, stock_efficiency_j_th=eff(20.5, 1530),
         asic_chip="BM1387", process_node="16nm", release_date="2018-11-01",
         is_current_product=False, notes="Noise 76dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s11-20-5th"),
]

# ── T9 / T9+ ────────────────────────────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="bitmain", canonical_name="Antminer T9 (11.5 TH)", model_number="T9",
         generation="T9 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=11.5, stock_power_w=1450, stock_efficiency_j_th=eff(11.5, 1450),
         asic_chip="BM1387", process_node="16nm", release_date="2017-04-01",
         is_current_product=False, notes="ASIC Miner Value: 11.5TH @ 1450W (126.09 J/TH). Noise 68dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-t9-11-5th"),
    dict(manufacturer="bitmain", canonical_name="Antminer T9 (12.5 TH)", model_number="T9",
         generation="T9 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=12.5, stock_power_w=1576, stock_efficiency_j_th=eff(12.5, 1576),
         asic_chip="BM1387", process_node="16nm", release_date="2017-08-01",
         is_current_product=False, notes="Noise 68dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-t9-12-5th"),
    dict(manufacturer="bitmain", canonical_name="Antminer T9+ (10.5 TH)", model_number="T9+",
         generation="T9 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=10.5, stock_power_w=1432, stock_efficiency_j_th=eff(10.5, 1432),
         asic_chip="BM1387", process_node="16nm", release_date="2018-01-01",
         is_current_product=False, notes="Noise 76dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-t9-10-5th"),
]

# ── S15 / T15 Series ─────────────────────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="bitmain", canonical_name="Antminer S15 (28 TH)", model_number="S15",
         generation="S15/T15 Series", cooling_type="air", hashboard_count=4,
         stock_hashrate_th=28.0, stock_power_w=1596, stock_efficiency_j_th=57.0,
         asic_chip="BM1391AE", process_node="7nm", release_date="2018-12-01",
         is_current_product=False, notes="HP mode: 28TH/1596W; LP mode: 17TH/850W (50 J/TH). Noise 76dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s15-28th"),
    dict(manufacturer="bitmain", canonical_name="Antminer T15 (23 TH)", model_number="T15",
         generation="S15/T15 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=23.0, stock_power_w=1541, stock_efficiency_j_th=67.0,
         asic_chip="BM1391AE", process_node="7nm", release_date="2018-12-01",
         is_current_product=False, notes="HP mode: 23TH/1541W; LP mode: 20TH/1200W (60 J/TH). Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-t15-23th"),
]

# ── S17 / T17 Series ─────────────────────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="bitmain", canonical_name="Antminer S17 (53 TH)", model_number="S17",
         generation="S17/T17 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=53.0, stock_power_w=2385, stock_efficiency_j_th=eff(53.0, 2385),
         asic_chip="BM1397AD/AI", process_node="7nm", release_date="2019-04-01",
         is_current_product=False, notes="ASIC Miner Value: 53TH @ 2385W (45 J/TH). Noise 82dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s17-53th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S17 (56 TH)", model_number="S17",
         generation="S17/T17 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=56.0, stock_power_w=2520, stock_efficiency_j_th=eff(56.0, 2520),
         asic_chip="BM1397AD/AI", process_node="7nm", release_date="2019-04-01",
         is_current_product=False, notes="ASIC Miner Value: 56TH @ 2520W (45 J/TH). Noise 82dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s17-56th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S17 Pro (50 TH)", model_number="S17 Pro",
         generation="S17/T17 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=50.0, stock_power_w=1975, stock_efficiency_j_th=39.5,
         asic_chip="BM1397AD/AI", process_node="7nm", release_date="2019-04-01",
         is_current_product=False, notes="Noise 82dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s17-pro-50th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S17 Pro (53 TH)", model_number="S17 Pro",
         generation="S17/T17 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=53.0, stock_power_w=2094, stock_efficiency_j_th=39.5,
         asic_chip="BM1397AD/AI", process_node="7nm", release_date="2019-04-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer S17 Pro (56 TH)", model_number="S17 Pro",
         generation="S17/T17 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=56.0, stock_power_w=2212, stock_efficiency_j_th=39.5,
         asic_chip="BM1397AD/AI", process_node="7nm", release_date="2019-04-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer S17e (64 TH)", model_number="S17e",
         generation="S17/T17 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=64.0, stock_power_w=2880, stock_efficiency_j_th=45.0,
         asic_chip="BM1396AB", process_node="7nm", release_date="2019-11-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s17e-64th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S17+ (73 TH)", model_number="S17+",
         generation="S17/T17 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=73.0, stock_power_w=2920, stock_efficiency_j_th=40.0,
         asic_chip="BM1397AF/AH", process_node="7nm", release_date="2019-12-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s17-73th"),
    dict(manufacturer="bitmain", canonical_name="Antminer T17 (40 TH)", model_number="T17",
         generation="S17/T17 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=40.0, stock_power_w=2200, stock_efficiency_j_th=55.0,
         asic_chip="BM1397AD/AI", process_node="7nm", release_date="2019-04-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-t17-40th"),
    dict(manufacturer="bitmain", canonical_name="Antminer T17e (53 TH)", model_number="T17e",
         generation="S17/T17 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=53.0, stock_power_w=2915, stock_efficiency_j_th=55.0,
         asic_chip="BM1396AB", process_node="7nm", release_date="2019-11-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-t17e-53th"),
    dict(manufacturer="bitmain", canonical_name="Antminer T17+ (58 TH)", model_number="T17+",
         generation="S17/T17 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=58.0, stock_power_w=2920, stock_efficiency_j_th=50.0,
         asic_chip="BM1397AG/AH", process_node="7nm", release_date="2019-12-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer T17+ (61 TH)", model_number="T17+",
         generation="S17/T17 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=61.0, stock_power_w=3050, stock_efficiency_j_th=50.0,
         asic_chip="BM1397AG/AH", process_node="7nm", release_date="2019-12-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer T17+ (64 TH)", model_number="T17+",
         generation="S17/T17 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=64.0, stock_power_w=3200, stock_efficiency_j_th=50.0,
         asic_chip="BM1397AG/AH", process_node="7nm", release_date="2019-12-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-t17-64th"),
]

# ── S19 / T19 Air-Cooled ──────────────────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="bitmain", canonical_name="Antminer S19 (84 TH)", model_number="S19",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=84.0, stock_power_w=2478, stock_efficiency_j_th=29.5,
         asic_chip="BM1398BB", process_node="7nm", release_date="2020-05-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer S19 (90 TH)", model_number="S19",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=90.0, stock_power_w=2655, stock_efficiency_j_th=29.5,
         asic_chip="BM1398BB", process_node="7nm", release_date="2020-05-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer S19 (95 TH)", model_number="S19",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=95.0, stock_power_w=3250, stock_efficiency_j_th=eff(95.0, 3250),
         asic_chip="BM1398BB", process_node="7nm", release_date="2020-05-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s19-95th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S19 Pro (100 TH)", model_number="S19 Pro",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=100.0, stock_power_w=2950, stock_efficiency_j_th=29.5,
         asic_chip="BM1398BB", process_node="7nm", release_date="2020-05-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer S19 Pro (105 TH)", model_number="S19 Pro",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=105.0, stock_power_w=3098, stock_efficiency_j_th=29.5,
         asic_chip="BM1398BB", process_node="7nm", release_date="2020-05-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer S19 Pro (110 TH)", model_number="S19 Pro",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=110.0, stock_power_w=3250, stock_efficiency_j_th=eff(110.0, 3250),
         asic_chip="BM1398BB", process_node="7nm", release_date="2020-05-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s19-pro-110th"),
    dict(manufacturer="bitmain", canonical_name="Antminer T19 (84 TH)", model_number="T19",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=84.0, stock_power_w=3150, stock_efficiency_j_th=37.5,
         asic_chip="BM1398BB", process_node="7nm", release_date="2020-06-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-t19-84th"),
    dict(manufacturer="bitmain", canonical_name="Antminer T19 (88 TH)", model_number="T19",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=88.0, stock_power_w=3344, stock_efficiency_j_th=eff(88.0, 3344),
         asic_chip="BM1398BB", process_node="7nm", release_date="2021-08-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-t19-88th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S19j (90 TH)", model_number="S19j",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=90.0, stock_power_w=3250, stock_efficiency_j_th=eff(90.0, 3250),
         asic_chip="BM1362AA/AJ", process_node="7nm", release_date="2021-06-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s19j-90th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S19a (90 TH)", model_number="S19a",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=90.0, stock_power_w=3250, stock_efficiency_j_th=36.1,
         asic_chip="BM1398AC", process_node="7nm", release_date="2021-08-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer S19j Pro (84 TH)", model_number="S19j Pro",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=84.0, stock_power_w=2478, stock_efficiency_j_th=29.5,
         asic_chip="BM1362AA/AJ", process_node="7nm", release_date="2021-08-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer S19j Pro (88 TH)", model_number="S19j Pro",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=88.0, stock_power_w=2596, stock_efficiency_j_th=29.5,
         asic_chip="BM1362AA/AJ", process_node="7nm", release_date="2021-08-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer S19j Pro (92 TH)", model_number="S19j Pro",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=92.0, stock_power_w=2714, stock_efficiency_j_th=29.5,
         asic_chip="BM1362AA/AJ", process_node="7nm", release_date="2021-08-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer S19j Pro (96 TH)", model_number="S19j Pro",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=96.0, stock_power_w=2832, stock_efficiency_j_th=29.5,
         asic_chip="BM1362AA/AJ", process_node="7nm", release_date="2021-08-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s19j-pro-96th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S19j Pro (100 TH)", model_number="S19j Pro",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=100.0, stock_power_w=3050, stock_efficiency_j_th=eff(100.0, 3050),
         asic_chip="BM1362AA/AJ", process_node="7nm", release_date="2021-06-01",
         is_current_product=False, notes="ASIC Miner Value: 100TH @ 3050W (30.5 J/TH). Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s19j-pro-100th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S19j Pro (104 TH)", model_number="S19j Pro",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=104.0, stock_power_w=3068, stock_efficiency_j_th=29.5,
         asic_chip="BM1362AA/AJ", process_node="7nm", release_date="2021-07-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s19j-pro-104th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S19a Pro (104 TH)", model_number="S19a Pro",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=104.0, stock_power_w=3068, stock_efficiency_j_th=29.5,
         asic_chip="BM1398AD", process_node="7nm", release_date="2021-08-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer S19al (90 TH)", model_number="S19al",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=90.0, stock_power_w=3250, stock_efficiency_j_th=36.1,
         asic_chip="BM1362AJ", process_node="7nm", release_date="2021-01-01",
         is_current_product=False, notes="al = alternative/low-cost binning.", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer S19i (90 TH)", model_number="S19i",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=90.0, stock_power_w=2970, stock_efficiency_j_th=33.0,
         asic_chip="BM1360BB", process_node="7nm", release_date="2021-01-01",
         is_current_product=False, notes="i = improved; uses BM1360BB chip.", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer S19 Pro+ (120 TH)", model_number="S19 Pro+",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=120.0, stock_power_w=3360, stock_efficiency_j_th=28.0,
         asic_chip="BM1362AK", process_node="7nm", release_date="2022-04-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer S19 XP (134 TH)", model_number="S19 XP",
         generation="S19 XP Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=134.0, stock_power_w=2882, stock_efficiency_j_th=21.5,
         asic_chip="BM1366AL/AG", process_node="5nm", release_date="2022-07-01",
         is_current_product=False, notes="First 5nm air-cooled Antminer.", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer S19 XP (140 TH)", model_number="S19 XP",
         generation="S19 XP Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=140.0, stock_power_w=3010, stock_efficiency_j_th=21.5,
         asic_chip="BM1366AL/AG", process_node="5nm", release_date="2022-07-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s19-xp-140th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S19j Pro+ (109 TH)", model_number="S19j Pro+",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=109.0, stock_power_w=2998, stock_efficiency_j_th=27.5,
         asic_chip="BM1362BD", process_node="7nm", release_date="2022-12-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer S19j Pro+ (113 TH)", model_number="S19j Pro+",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=113.0, stock_power_w=3108, stock_efficiency_j_th=27.5,
         asic_chip="BM1362BD", process_node="7nm", release_date="2022-12-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer S19j Pro+ (117 TH)", model_number="S19j Pro+",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=117.0, stock_power_w=3218, stock_efficiency_j_th=27.5,
         asic_chip="BM1362BD", process_node="7nm", release_date="2022-12-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer S19j Pro+ (120 TH)", model_number="S19j Pro+",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=120.0, stock_power_w=3300, stock_efficiency_j_th=27.5,
         asic_chip="BM1362BD", process_node="7nm", release_date="2022-12-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer S19j Pro++ (122 TH)", model_number="S19j Pro++",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=122.0, stock_power_w=3355, stock_efficiency_j_th=27.5,
         asic_chip="BM1362BD", process_node="7nm", release_date="2022-12-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s19j-pro-122th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S19k Pro (120 TH)", model_number="S19k Pro",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=120.0, stock_power_w=2760, stock_efficiency_j_th=23.0,
         asic_chip="BM1366BS/BP/AH", process_node="5nm", release_date="2023-10-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s19k-pro-120th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S19j XP (151 TH)", model_number="S19j XP",
         generation="S19 XP Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=151.0, stock_power_w=3247, stock_efficiency_j_th=21.5,
         asic_chip="BM1366AL/AG", process_node="5nm", release_date="2023-06-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s19j-xp-151th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S19 Pro++ (115 TH)", model_number="S19 Pro++",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=115.0, stock_power_w=2990, stock_efficiency_j_th=26.0,
         asic_chip="BM1366", process_node="5nm", release_date="2024-08-01",
         is_current_product=False, notes="2024 refresh using BM1366 in older S19 chassis.", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer S19 Pro++ (120 TH)", model_number="S19 Pro++",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=120.0, stock_power_w=3120, stock_efficiency_j_th=26.0,
         asic_chip="BM1366", process_node="5nm", release_date="2024-08-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer S19 Pro++ (125 TH)", model_number="S19 Pro++",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=125.0, stock_power_w=3250, stock_efficiency_j_th=26.0,
         asic_chip="BM1366", process_node="5nm", release_date="2024-08-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s19-pro-plus-plus"),
    dict(manufacturer="bitmain", canonical_name="Antminer S19 Pro-A (100 TH)", model_number="S19 Pro-A",
         generation="S19 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=100.0, stock_power_w=2950, stock_efficiency_j_th=29.5,
         asic_chip="BM1398AD", process_node="7nm", release_date="2024-10-01",
         is_current_product=False, notes="Regional/batch variant.", source_urls=BITMAIN_SOURCES),
]

# ── S19 Hydro/Immersion ───────────────────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="bitmain", canonical_name="Antminer S19 Pro+ Hydro (198 TH)", model_number="S19 Pro+ Hydro",
         generation="S19 Series", cooling_type="hydro", hashboard_count=3,
         stock_hashrate_th=198.0, stock_power_w=5445, stock_efficiency_j_th=27.5,
         asic_chip="BM1362AK/AI", process_node="7nm", release_date="2022-05-01",
         is_current_product=False, notes="Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s19-pro-hyd-198th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S19 Hydro (158 TH)", model_number="S19 Hydro",
         generation="S19 Series", cooling_type="hydro", hashboard_count=3,
         stock_hashrate_th=158.0, stock_power_w=5451, stock_efficiency_j_th=34.5,
         asic_chip="BM1398BB", process_node="7nm", release_date="2022-10-01",
         is_current_product=False, notes="Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s19-hydro-158th"),
    dict(manufacturer="bitmain", canonical_name="Antminer T19 Hydro (145 TH)", model_number="T19 Hydro",
         generation="S19 Series", cooling_type="hydro", hashboard_count=3,
         stock_hashrate_th=145.0, stock_power_w=5438, stock_efficiency_j_th=37.5,
         asic_chip="BM1398BB", process_node="7nm", release_date="2022-10-01",
         is_current_product=False, notes="Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-t19-hydro-145th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S19 XP Hydro (255 TH)", model_number="S19 XP Hydro",
         generation="S19 XP Series", cooling_type="hydro", hashboard_count=3,
         stock_hashrate_th=255.0, stock_power_w=5304, stock_efficiency_j_th=20.8,
         asic_chip="BM1366AL/AG", process_node="5nm", release_date="2022-10-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer S19 XP Hydro (257 TH)", model_number="S19 XP Hydro",
         generation="S19 XP Series", cooling_type="hydro", hashboard_count=3,
         stock_hashrate_th=257.0, stock_power_w=5346, stock_efficiency_j_th=20.8,
         asic_chip="BM1366AL/AG", process_node="5nm", release_date="2024-01-01",
         is_current_product=False, notes="Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s19-xp-hyd-257th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S19 Pro+ Hyd (191 TH)", model_number="S19 Pro+ Hyd",
         generation="S19 Series", cooling_type="hydro", hashboard_count=3,
         stock_hashrate_th=191.0, stock_power_w=5252, stock_efficiency_j_th=27.5,
         asic_chip="BM1362AK", process_node="7nm", release_date="2024-01-01",
         is_current_product=False, notes="", source_urls=BITMAIN_SOURCES),
    # ASIC Miner Value extras for S19 series
    dict(manufacturer="bitmain", canonical_name="Antminer S19 XP Hydro (512 TH)", model_number="S19 XP Hydro",
         generation="S19 XP Series", cooling_type="hydro", hashboard_count=3,
         stock_hashrate_th=512.0, stock_power_w=10600, stock_efficiency_j_th=eff(512, 10600),
         asic_chip="BM1366AL/AG", process_node="5nm", release_date="2025-01-01",
         is_current_product=False, notes="Rack-scale dual-unit config. Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s219-xp-hydro-512th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S19 XP+ Hyd (279 TH)", model_number="S19 XP+ Hyd",
         generation="S19 XP Series", cooling_type="hydro", hashboard_count=3,
         stock_hashrate_th=279.0, stock_power_w=5301, stock_efficiency_j_th=19.0,
         asic_chip="BM1366AL/AG", process_node="5nm", release_date="2025-01-01",
         is_current_product=False, notes="Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s19-xp-plus-hyd-279th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S19 XP+ Hyd (293 TH)", model_number="S19 XP+ Hyd",
         generation="S19 XP Series", cooling_type="hydro", hashboard_count=3,
         stock_hashrate_th=293.0, stock_power_w=5567, stock_efficiency_j_th=19.0,
         asic_chip="BM1366AL/AG", process_node="5nm", release_date="2025-04-01",
         is_current_product=False, notes="Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s19-xp-plus-hyd-293th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S19 Pro Hyd (177 TH)", model_number="S19 Pro Hyd",
         generation="S19 Series", cooling_type="hydro", hashboard_count=3,
         stock_hashrate_th=177.0, stock_power_w=5221, stock_efficiency_j_th=29.5,
         asic_chip="BM1398BB", process_node="7nm", release_date="2023-01-01",
         is_current_product=False, notes="Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s19-pro-hyd-177th"),
    dict(manufacturer="bitmain", canonical_name="Antminer T19 Pro Hyd (235 TH)", model_number="T19 Pro Hyd",
         generation="S19 Series", cooling_type="hydro", hashboard_count=3,
         stock_hashrate_th=235.0, stock_power_w=5170, stock_efficiency_j_th=22.0,
         asic_chip="BM1398BB", process_node="7nm", release_date="2024-02-01",
         is_current_product=False, notes="Noise 30dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-t19-pro-hyd-235th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S19 Hydro (158 TH) [T19 variant]", model_number="T19 Hydro",
         generation="S19 Series", cooling_type="hydro", hashboard_count=3,
         stock_hashrate_th=158.0, stock_power_w=5451, stock_efficiency_j_th=34.5,
         asic_chip="BM1398BB", process_node="7nm", release_date="2022-10-01",
         is_current_product=False, notes="Note: ASIC Miner Value lists T19 Hydro 158TH as separate from S19 Hydro 158TH (different model label, same specs).",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-t19-hydro-158th"),
]

# ── S21 / T21 Air-Cooled ──────────────────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="bitmain", canonical_name="Antminer S21 (200 TH)", model_number="S21",
         generation="S21 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=200.0, stock_power_w=3550, stock_efficiency_j_th=eff(200.0, 3550),
         asic_chip="BM1368PA/PB", process_node="5nm", release_date="2024-02-01",
         is_current_product=True, notes="ASIC Miner Value: 200TH @ 3550W (17.75 J/TH). Deep dive: 3500W. Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s21-200th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S21 Pro (234 TH)", model_number="S21 Pro",
         generation="S21 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=234.0, stock_power_w=3510, stock_efficiency_j_th=15.0,
         asic_chip="BM1370BC/AA", process_node="5nm", release_date="2024-07-01",
         is_current_product=True, notes="Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s21-pro-234th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S21 Pro (245 TH)", model_number="S21 Pro",
         generation="S21 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=245.0, stock_power_w=3675, stock_efficiency_j_th=15.0,
         asic_chip="BM1370BC/AA", process_node="5nm", release_date="2025-11-01",
         is_current_product=True, notes="Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s21-pro-245th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S21 XP (270 TH)", model_number="S21 XP",
         generation="S21 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=270.0, stock_power_w=3645, stock_efficiency_j_th=13.5,
         asic_chip="BM1370BC/AA", process_node="5nm", release_date="2024-09-01",
         is_current_product=True, notes="Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antmine-s21-xp-270th"),
    dict(manufacturer="bitmain", canonical_name="Antminer T21 (190 TH — NEM)", model_number="T21",
         generation="S21 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=190.0, stock_power_w=3610, stock_efficiency_j_th=19.0,
         asic_chip="BM1368PA/PB", process_node="5nm", release_date="2024-02-01",
         is_current_product=True, notes="Normal Energy Mode (NEM). Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-t21-190th"),
    dict(manufacturer="bitmain", canonical_name="Antminer T21 (180 TH)", model_number="T21",
         generation="S21 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=180.0, stock_power_w=3420, stock_efficiency_j_th=19.0,
         asic_chip="BM1368PA/PB", process_node="5nm", release_date="2024-04-01",
         is_current_product=True, notes="Noise 55dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-t21-180th"),
    dict(manufacturer="bitmain", canonical_name="Antminer T21 (233 TH — HEM)", model_number="T21",
         generation="S21 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=233.0, stock_power_w=5126, stock_efficiency_j_th=22.0,
         asic_chip="BM1368PA/PB", process_node="5nm", release_date="2024-02-01",
         is_current_product=True, notes="High Energy Mode (HEM). Same hardware as NEM but different firmware config.", source_urls=BITMAIN_SOURCES),
    # S21+ Air variants (ASIC Miner Value extra)
    dict(manufacturer="bitmain", canonical_name="Antminer S21+ (216 TH)", model_number="S21+",
         generation="S21 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=216.0, stock_power_w=3564, stock_efficiency_j_th=16.5,
         asic_chip="BM1368PA/PB", process_node="5nm", release_date="2025-02-01",
         is_current_product=True, notes="Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s21-plus-216th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S21+ (225 TH)", model_number="S21+",
         generation="S21 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=225.0, stock_power_w=3712, stock_efficiency_j_th=16.5,
         asic_chip="BM1368PA/PB", process_node="5nm", release_date="2025-06-01",
         is_current_product=True, notes="Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s21-plus-225th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S21+ (235 TH)", model_number="S21+",
         generation="S21 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=235.0, stock_power_w=3877, stock_efficiency_j_th=16.5,
         asic_chip="BM1368PA/PB", process_node="5nm", release_date="2025-06-01",
         is_current_product=True, notes="Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s21-plus-235th"),
    # S21 XP Immersion
    dict(manufacturer="bitmain", canonical_name="Antminer S21 XP Immersion (300 TH)", model_number="S21 XP Immersion",
         generation="S21 Series", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=300.0, stock_power_w=4050, stock_efficiency_j_th=13.5,
         asic_chip="BM1370BC/AA", process_node="5nm", release_date="2024-09-01",
         is_current_product=True, notes="Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s21-xp-immersion-300th"),
]

# ── S21 Hydro-Cooled ──────────────────────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="bitmain", canonical_name="Antminer S21 Hyd (335 TH)", model_number="S21 Hyd",
         generation="S21 Series", cooling_type="hydro", hashboard_count=3,
         stock_hashrate_th=335.0, stock_power_w=5360, stock_efficiency_j_th=16.0,
         asic_chip="BM1368PA/PB", process_node="5nm", release_date="2024-02-01",
         is_current_product=True, notes="Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s21-hyd-335th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S21+ Hyd (335 TH)", model_number="S21+ Hyd",
         generation="S21 Series", cooling_type="hydro", hashboard_count=3,
         stock_hashrate_th=335.0, stock_power_w=5360, stock_efficiency_j_th=16.0,
         asic_chip="BM1368PA/PB", process_node="5nm", release_date="2024-03-01",
         is_current_product=True, notes="Revised hydro variant of S21 Hyd.", source_urls=BITMAIN_SOURCES),
    dict(manufacturer="bitmain", canonical_name="Antminer S21+ Hyd (319 TH)", model_number="S21+ Hyd",
         generation="S21 Series", cooling_type="hydro", hashboard_count=3,
         stock_hashrate_th=319.0, stock_power_w=4785, stock_efficiency_j_th=15.0,
         asic_chip="BM1368PA/PB", process_node="5nm", release_date="2025-02-01",
         is_current_product=True, notes="Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s21-plus-hyd-319th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S21+ Hyd (358 TH)", model_number="S21+ Hyd",
         generation="S21 Series", cooling_type="hydro", hashboard_count=3,
         stock_hashrate_th=358.0, stock_power_w=5370, stock_efficiency_j_th=15.0,
         asic_chip="BM1368PA/PB", process_node="5nm", release_date="2025-08-01",
         is_current_product=True, notes="Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s21-plus-hyd-358th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S21 XP Hyd (473 TH)", model_number="S21 XP Hyd",
         generation="S21 Series", cooling_type="hydro", hashboard_count=3,
         stock_hashrate_th=473.0, stock_power_w=5676, stock_efficiency_j_th=12.0,
         asic_chip="BM1370BC/AA", process_node="5nm", release_date="2024-10-01",
         is_current_product=True, notes="Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s21-xp-hyd-473th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S21 XP+ Hyd (500 TH)", model_number="S21 XP+ Hyd",
         generation="S21 Series", cooling_type="hydro", hashboard_count=3,
         stock_hashrate_th=500.0, stock_power_w=5500, stock_efficiency_j_th=11.0,
         asic_chip="BM1370BC/AA", process_node="5nm", release_date="2025-07-01",
         is_current_product=True, notes="Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s21-xp-plus-hyd-500th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S21e XP Hyd (430 TH)", model_number="S21e XP Hyd",
         generation="S21 Series", cooling_type="hydro", hashboard_count=3,
         stock_hashrate_th=430.0, stock_power_w=5590, stock_efficiency_j_th=13.0,
         asic_chip="BM1370BC/AA", process_node="5nm", release_date="2024-11-01",
         is_current_product=True, notes="Enterprise single-unit hydro. Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s21e-xp-hyd-430th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S21e XP Hyd 3U (860 TH)", model_number="S21e XP Hyd 3U",
         generation="S21 Series", cooling_type="hydro", hashboard_count=9,
         stock_hashrate_th=860.0, stock_power_w=11180, stock_efficiency_j_th=13.0,
         asic_chip="BM1370BC/AA", process_node="5nm", release_date="2025-01-01",
         is_current_product=True, notes="3U rack form factor (3 hashboard sets). Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s21e-xp-hydro-860th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S21e Hyd (288 TH)", model_number="S21e Hyd",
         generation="S21 Series", cooling_type="hydro", hashboard_count=3,
         stock_hashrate_th=288.0, stock_power_w=4896, stock_efficiency_j_th=17.0,
         asic_chip="BM1368PA/PB", process_node="5nm", release_date="2025-04-01",
         is_current_product=True, notes="Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s21e-hyd-288th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S21e Hyd (310 TH)", model_number="S21e Hyd",
         generation="S21 Series", cooling_type="hydro", hashboard_count=3,
         stock_hashrate_th=310.0, stock_power_w=5270, stock_efficiency_j_th=17.0,
         asic_chip="BM1368PA/PB", process_node="5nm", release_date="2025-08-01",
         is_current_product=True, notes="Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s21e-hyd-310th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S21j XP Hyd (495 TH)", model_number="S21j XP Hyd",
         generation="S21 Series", cooling_type="hydro", hashboard_count=3,
         stock_hashrate_th=495.0, stock_power_w=5940, stock_efficiency_j_th=12.0,
         asic_chip="BM1370BC/AA", process_node="5nm", release_date="2026-03-01",
         is_current_product=True, notes="j-bin hydro variant. Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s21j-xp-hyd-495th"),
]

# ── S21 Immersion ─────────────────────────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="bitmain", canonical_name="Antminer S21 Immersion (215-301 TH)", model_number="S21 Immersion",
         generation="S21 Series", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=258.0, stock_power_w=4650, stock_efficiency_j_th=18.0,
         asic_chip="BM1368PM", process_node="5nm", release_date="2024-10-01",
         is_current_product=True, notes="Range 215-301 TH at 16-18.5 J/TH. Midpoint shown. Nominal listed as 301TH @ 5569W by ASIC Miner Value (18.5 J/TH). Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s21-immersion-301th"),
]

# ── S23 Series ────────────────────────────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="bitmain", canonical_name="Antminer S23 (318 TH)", model_number="S23",
         generation="S23 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=318.0, stock_power_w=3498, stock_efficiency_j_th=11.0,
         asic_chip="BM1370 next-gen", process_node="~3nm", release_date="2026-01-01",
         is_current_product=True, notes="Sub-10nm. Noise 75dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s23-318th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S23 Immersion (368-442 TH)", model_number="S23 IMM",
         generation="S23 Series", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=442.0, stock_power_w=5304, stock_efficiency_j_th=12.0,
         asic_chip="BM1370 next-gen", process_node="~3nm", release_date="2026-01-01",
         is_current_product=True, notes="Purpose-built immersion chassis (no fans). ASIC Miner Value: 442TH @ 5304W (12 J/TH). Range 368-442 TH. Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s23-immersion-442th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S23 Hydro (580 TH)", model_number="S23 Hyd",
         generation="S23 Series", cooling_type="hydro", hashboard_count=3,
         stock_hashrate_th=580.0, stock_power_w=5510, stock_efficiency_j_th=9.5,
         asic_chip="BM1370 next-gen", process_node="~3nm", release_date="2026-01-01",
         is_current_product=True, notes="Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s23-hyd-580th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S23 Hydro 3U (1160 TH)", model_number="S23 Hyd 3U",
         generation="S23 Series", cooling_type="hydro", hashboard_count=9,
         stock_hashrate_th=1160.0, stock_power_w=11020, stock_efficiency_j_th=9.5,
         asic_chip="BM1370 next-gen", process_node="~3nm", release_date="2026-01-01",
         is_current_product=True, notes="3U rack form factor. Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s23-hydro-u3-1160th"),
    dict(manufacturer="bitmain", canonical_name="Antminer S23e Hyd 2U (865 TH)", model_number="S23e Hyd 2U",
         generation="S23 Series", cooling_type="hydro", hashboard_count=6,
         stock_hashrate_th=865.0, stock_power_w=8650, stock_efficiency_j_th=10.0,
         asic_chip="BM1370 next-gen", process_node="~3nm", release_date="2026-04-01",
         is_current_product=True, notes="2U enterprise hydro rack form. Noise 50dB.",
         source_urls=BITMAIN_SOURCES + ",https://www.asicminervalue.com/miners/antminer-s23e-hyd-u2h-865th"),
]

# ═══════════════════════════════════════════════════════════════════════════════
# MICROBT WHATSMINER — ~96 variants
# ═══════════════════════════════════════════════════════════════════════════════

MICROBT_SOURCES = "https://shop.whatsminer.com,https://www.asicminervalue.com/manufacturers/microbt,https://hashrateindex.com,https://d-central.tech"

# ── Gen 1: M1 / M3 Series ────────────────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="microbt", canonical_name="Whatsminer M1", model_number="M1",
         generation="M1/M3 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=12.0, stock_power_w=2000, stock_efficiency_j_th=eff(12.0, 2000),
         asic_chip="SMTI 1700", process_node="28nm", release_date="2018-03-01",
         is_current_product=False, notes="", source_urls=MICROBT_SOURCES),
    dict(manufacturer="microbt", canonical_name="Whatsminer M3", model_number="M3",
         generation="M1/M3 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=12.0, stock_power_w=2000, stock_efficiency_j_th=eff(12.0, 2000),
         asic_chip="SMTI 1700", process_node="28nm", release_date="2018-01-01",
         is_current_product=False, notes="Noise 78dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m3"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M3X", model_number="M3X",
         generation="M1/M3 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=12.5, stock_power_w=2050, stock_efficiency_j_th=eff(12.5, 2050),
         asic_chip="SMTI 1700", process_node="28nm", release_date="2018-03-01",
         is_current_product=False, notes="Noise 78dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m3x"),
]

# ── Gen 2: M10 Series ─────────────────────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="microbt", canonical_name="Whatsminer M10", model_number="M10",
         generation="M10 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=33.0, stock_power_w=2145, stock_efficiency_j_th=eff(33.0, 2145),
         asic_chip="—", process_node="16nm", release_date="2018-09-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m10"),
    # M10S — from ASIC Miner Value extra
    dict(manufacturer="microbt", canonical_name="Whatsminer M10S (55 TH)", model_number="M10S",
         generation="M10 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=55.0, stock_power_w=3500, stock_efficiency_j_th=eff(55.0, 3500),
         asic_chip="—", process_node="16nm", release_date="2018-09-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m10s"),
]

# ── Gen 2: M20 Series ────────────────────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="microbt", canonical_name="Whatsminer M20S (65 TH)", model_number="M20S",
         generation="M20 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=65.0, stock_power_w=3120, stock_efficiency_j_th=eff(65.0, 3120),
         asic_chip="KF1921/Samsung", process_node="12nm", release_date="2019-08-01",
         is_current_product=False, notes="", source_urls=MICROBT_SOURCES),
    dict(manufacturer="microbt", canonical_name="Whatsminer M20S (68 TH)", model_number="M20S",
         generation="M20 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=68.0, stock_power_w=3360, stock_efficiency_j_th=eff(68.0, 3360),
         asic_chip="KF1921/Samsung", process_node="12nm", release_date="2019-08-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m20s"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M20S (70 TH)", model_number="M20S",
         generation="M20 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=70.0, stock_power_w=3360, stock_efficiency_j_th=eff(70.0, 3360),
         asic_chip="KF1921/Samsung", process_node="12nm", release_date="2019-08-01",
         is_current_product=False, notes="", source_urls=MICROBT_SOURCES),
    dict(manufacturer="microbt", canonical_name="Whatsminer M20S+", model_number="M20S+",
         generation="M20 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=72.0, stock_power_w=3360, stock_efficiency_j_th=eff(72.0, 3360),
         asic_chip="Samsung", process_node="10nm", release_date="2019-01-01",
         is_current_product=False, notes="", source_urls=MICROBT_SOURCES),
]

# ── Gen 2: M21 Series ────────────────────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="microbt", canonical_name="Whatsminer M21", model_number="M21",
         generation="M21 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=31.0, stock_power_w=1860, stock_efficiency_j_th=eff(31.0, 1860),
         asic_chip="Samsung", process_node="12nm", release_date="2019-08-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m21"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M21S (56 TH)", model_number="M21S",
         generation="M21 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=56.0, stock_power_w=3360, stock_efficiency_j_th=eff(56.0, 3360),
         asic_chip="Samsung", process_node="10nm", release_date="2019-06-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m21s"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M21S (58 TH)", model_number="M21S",
         generation="M21 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=58.0, stock_power_w=3480, stock_efficiency_j_th=eff(58.0, 3480),
         asic_chip="Samsung", process_node="10nm", release_date="2019-06-01",
         is_current_product=False, notes="", source_urls=MICROBT_SOURCES),
    dict(manufacturer="microbt", canonical_name="Whatsminer M21S+", model_number="M21S+",
         generation="M21 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=58.0, stock_power_w=3480, stock_efficiency_j_th=eff(58.0, 3480),
         asic_chip="Samsung", process_node="10nm", release_date="2020-01-01",
         is_current_product=False, notes="", source_urls=MICROBT_SOURCES),
]

# ── Gen 3: M30 / M31 / M32 Series ────────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="microbt", canonical_name="Whatsminer M30S", model_number="M30S",
         generation="M30 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=86.0, stock_power_w=3268, stock_efficiency_j_th=eff(86.0, 3268),
         asic_chip="Samsung 8nm", process_node="8nm", release_date="2020-04-01",
         is_current_product=False, notes="Noise 72dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m30s"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M30S+", model_number="M30S+",
         generation="M30 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=100.0, stock_power_w=3400, stock_efficiency_j_th=34.0,
         asic_chip="Samsung 8nm", process_node="8nm", release_date="2020-10-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m30s-1"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M30S++", model_number="M30S++",
         generation="M30 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=112.0, stock_power_w=3472, stock_efficiency_j_th=31.0,
         asic_chip="Samsung 8nm", process_node="8nm", release_date="2020-10-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m30s-2"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M31S", model_number="M31S",
         generation="M31 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=74.0, stock_power_w=3220, stock_efficiency_j_th=eff(74.0, 3220),
         asic_chip="Samsung 8nm", process_node="8nm", release_date="2020-07-01",
         is_current_product=False, notes="ASIC Miner Value: 76TH @ 3344W. Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m31s"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M31S+", model_number="M31S+",
         generation="M31 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=80.0, stock_power_w=3360, stock_efficiency_j_th=42.0,
         asic_chip="Samsung 8nm", process_node="8nm", release_date="2020-07-01",
         is_current_product=False, notes="Noise 70dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m31s-1"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M32 (62 TH)", model_number="M32",
         generation="M32 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=62.0, stock_power_w=3348, stock_efficiency_j_th=eff(62.0, 3348),
         asic_chip="Samsung 8nm", process_node="8nm", release_date="2020-07-01",
         is_current_product=False, notes="ASIC Miner Value: 62TH @ 3456W. Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m32"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M32 (66 TH)", model_number="M32",
         generation="M32 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=66.0, stock_power_w=3432, stock_efficiency_j_th=eff(66.0, 3432),
         asic_chip="Samsung 8nm", process_node="8nm", release_date="2020-11-01",
         is_current_product=False, notes="", source_urls=MICROBT_SOURCES),
    dict(manufacturer="microbt", canonical_name="Whatsminer M32 (68 TH)", model_number="M32",
         generation="M32 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=68.0, stock_power_w=3400, stock_efficiency_j_th=eff(68.0, 3400),
         asic_chip="Samsung 8nm", process_node="8nm", release_date="2020-11-01",
         is_current_product=False, notes="", source_urls=MICROBT_SOURCES),
    dict(manufacturer="microbt", canonical_name="Whatsminer M32S", model_number="M32S",
         generation="M32 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=68.0, stock_power_w=3472, stock_efficiency_j_th=eff(68.0, 3472),
         asic_chip="Samsung 8nm", process_node="8nm", release_date="2021-01-01",
         is_current_product=False, notes="ASIC Miner Value: 66TH @ 3432W (52 J/TH). Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m32s"),
]

# ── M33 / M36 Series ─────────────────────────────────────────────────────────
ALL_MINERS += [
    # M33S from ASIC Miner Value extra
    dict(manufacturer="microbt", canonical_name="Whatsminer M33S (80 TH)", model_number="M33S",
         generation="M33 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=80.0, stock_power_w=3360, stock_efficiency_j_th=42.0,
         asic_chip="Samsung 7nm", process_node="7nm", release_date="2020-12-01",
         is_current_product=False, notes="Noise 75dB. Listed in ASIC Miner Value; air-cooled variant separate from M33S++ hydro.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m33s"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M33S++", model_number="M33S++",
         generation="M33 Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=242.0, stock_power_w=7260, stock_efficiency_j_th=eff(242.0, 7260),
         asic_chip="Samsung 7nm", process_node="7nm", release_date="2022-12-01",
         is_current_product=False, notes="4U Blade; 3-phase AC380V. Hydro-cooled derivative of M30 gen.",
         source_urls=MICROBT_SOURCES + ",https://www.cryptominerbros.com/product/microbt-whatsminer-m33s-hydro-bitcoin-miner/"),
    # M36S from ASIC Miner Value extra
    dict(manufacturer="microbt", canonical_name="Whatsminer M36S (62 TH)", model_number="M36S",
         generation="M36 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=62.0, stock_power_w=3456, stock_efficiency_j_th=eff(62.0, 3456),
         asic_chip="Samsung 8nm", process_node="8nm", release_date="2020-07-01",
         is_current_product=False, notes="Noise 75dB. Listed in ASIC Miner Value as separate from M36S+/++ immersion.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m36s"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M36S+", model_number="M36S+",
         generation="M36 Series", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=127.0, stock_power_w=3306, stock_efficiency_j_th=eff(127.0, 3306),
         asic_chip="Samsung 8nm", process_node="8nm", release_date="2022-01-01",
         is_current_product=False, notes="Slim immersion form. Range 124-130 TH at 26-27 J/TH. Midpoint shown.",
         source_urls=MICROBT_SOURCES),
    dict(manufacturer="microbt", canonical_name="Whatsminer M36S++", model_number="M36S++",
         generation="M36 Series", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=167.0, stock_power_w=5166, stock_efficiency_j_th=eff(167.0, 5166),
         asic_chip="Samsung 8nm", process_node="8nm", release_date="2023-05-01",
         is_current_product=False, notes="Slim immersion. Range 162-172 TH. Midpoint shown.",
         source_urls=MICROBT_SOURCES),
]

# ── Gen 5: M50 Series ─────────────────────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="microbt", canonical_name="Whatsminer M50 (114 TH)", model_number="M50",
         generation="M50 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=114.0, stock_power_w=3306, stock_efficiency_j_th=29.0,
         asic_chip="Samsung 5nm", process_node="5nm", release_date="2022-07-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m50"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M50S (126 TH)", model_number="M50S",
         generation="M50 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=126.0, stock_power_w=3276, stock_efficiency_j_th=26.0,
         asic_chip="Samsung 5nm", process_node="5nm", release_date="2022-07-01",
         is_current_product=False, notes="ASIC Miner Value: 128TH @ 3276W (25.59 J/TH). Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m50s"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M50S+ (136-148 TH)", model_number="M50S+",
         generation="M50 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=142.0, stock_power_w=3405, stock_efficiency_j_th=eff(142.0, 3405),
         asic_chip="Samsung 5nm", process_node="5nm", release_date="2023-01-01",
         is_current_product=False, notes="Range 136-148 TH. Midpoint shown.", source_urls=MICROBT_SOURCES),
    dict(manufacturer="microbt", canonical_name="Whatsminer M50S++ (150-162 TH)", model_number="M50S++",
         generation="M50 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=156.0, stock_power_w=3265, stock_efficiency_j_th=eff(156.0, 3265),
         asic_chip="Samsung 5nm", process_node="5nm", release_date="2023-01-01",
         is_current_product=False, notes="Range 150-162 TH at 21-23 J/TH. Midpoint shown.", source_urls=MICROBT_SOURCES),
]

# ── Gen 5: M53 / M56 Series ─────────────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="microbt", canonical_name="Whatsminer M53 (230 TH)", model_number="M53",
         generation="M53 Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=230.0, stock_power_w=6670, stock_efficiency_j_th=29.0,
         asic_chip="Samsung 5nm", process_node="5nm", release_date="2023-05-01",
         is_current_product=False, notes="4U Blade. ASIC Miner Value: 260TH @ 6760W, 26 J/TH (immersion). Hydro per deep dive. Noise 45dB.",
         source_urls=MICROBT_SOURCES + ",https://asicmarketplace.com/product/microbt-whatsminer-m53-m53s-hydro-btc-miner/"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M53S (260 TH)", model_number="M53S",
         generation="M53 Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=260.0, stock_power_w=6760, stock_efficiency_j_th=26.0,
         asic_chip="Samsung 5nm", process_node="5nm", release_date="2023-05-01",
         is_current_product=False, notes="4U Blade. Noise 45dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m53s"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M53S++ (320 TH)", model_number="M53S++",
         generation="M53 Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=320.0, stock_power_w=7040, stock_efficiency_j_th=22.0,
         asic_chip="Samsung 5nm", process_node="5nm", release_date="2023-07-01",
         is_current_product=False, notes="4U Blade.", source_urls=MICROBT_SOURCES),
    dict(manufacturer="microbt", canonical_name="Whatsminer M56 (194 TH)", model_number="M56",
         generation="M56 Series", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=194.0, stock_power_w=5550, stock_efficiency_j_th=eff(194.0, 5550),
         asic_chip="Samsung 5nm", process_node="5nm", release_date="2023-01-01",
         is_current_product=False, notes="Slim immersion. Noise 45dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m56"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M56S (200 TH)", model_number="M56S",
         generation="M56 Series", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=200.0, stock_power_w=5200, stock_efficiency_j_th=26.0,
         asic_chip="Samsung 5nm", process_node="5nm", release_date="2023-05-01",
         is_current_product=False, notes="Slim immersion. ASIC Miner Value: 212TH @ 5550W (26.18). Noise 45dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m56s"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M56S+ (224 TH)", model_number="M56S+",
         generation="M56 Series", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=224.0, stock_power_w=5376, stock_efficiency_j_th=24.0,
         asic_chip="Samsung 5nm", process_node="5nm", release_date="2023-01-01",
         is_current_product=False, notes="Slim immersion.", source_urls=MICROBT_SOURCES),
    dict(manufacturer="microbt", canonical_name="Whatsminer M56S++ (254 TH)", model_number="M56S++",
         generation="M56 Series", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=254.0, stock_power_w=5588, stock_efficiency_j_th=22.0,
         asic_chip="Samsung 5nm", process_node="5nm", release_date="2023-05-01",
         is_current_product=False, notes="Slim immersion.", source_urls=MICROBT_SOURCES),
]

# ── Gen 6: M60 / M61 Series ──────────────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="microbt", canonical_name="Whatsminer M60 (162 TH)", model_number="M60",
         generation="M60 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=162.0, stock_power_w=3104, stock_efficiency_j_th=eff(162.0, 3104),
         asic_chip="Samsung 5nm+", process_node="5nm", release_date="2023-10-01",
         is_current_product=True, notes="ASIC Miner Value: 172TH @ 3422W (19.9 J/TH). Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m60"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M60S (186 TH)", model_number="M60S",
         generation="M60 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=186.0, stock_power_w=3441, stock_efficiency_j_th=eff(186.0, 3441),
         asic_chip="Samsung 5nm+", process_node="5nm", release_date="2023-10-01",
         is_current_product=True, notes="Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m60s"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M60S+ (190-200 TH)", model_number="M60S+",
         generation="M60 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=195.0, stock_power_w=3315, stock_efficiency_j_th=17.0,
         asic_chip="Samsung 5nm+", process_node="5nm", release_date="2024-07-01",
         is_current_product=True, notes="Range 190-200 TH. ASIC Miner Value: 212TH @ 3600W. Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m60s-plus"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M60S++ (218-226 TH)", model_number="M60S++",
         generation="M60 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=226.0, stock_power_w=3600, stock_efficiency_j_th=eff(226.0, 3600),
         asic_chip="Samsung 5nm+", process_node="5nm", release_date="2024-12-01",
         is_current_product=True, notes="Noise 75dB. ASIC Miner Value: 226TH @ 3600W (15.93 J/TH).",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m60s-plus-plus"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M61 (202 TH)", model_number="M61",
         generation="M61 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=202.0, stock_power_w=4000, stock_efficiency_j_th=eff(202.0, 4000),
         asic_chip="Samsung 5nm+", process_node="5nm", release_date="2024-12-01",
         is_current_product=True, notes="Larger form factor (430×155×226mm).", source_urls=MICROBT_SOURCES),
    dict(manufacturer="microbt", canonical_name="Whatsminer M61S (216 TH)", model_number="M61S",
         generation="M61 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=216.0, stock_power_w=4320, stock_efficiency_j_th=eff(216.0, 4320),
         asic_chip="Samsung 5nm+", process_node="5nm", release_date="2024-12-01",
         is_current_product=True, notes="", source_urls=MICROBT_SOURCES),
    dict(manufacturer="microbt", canonical_name="Whatsminer M61S+ (236 TH)", model_number="M61S+",
         generation="M61 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=236.0, stock_power_w=4012, stock_efficiency_j_th=17.0,
         asic_chip="Samsung 5nm+", process_node="5nm", release_date="2024-12-01",
         is_current_product=True, notes="", source_urls=MICROBT_SOURCES),
]

# ── Gen 6: M63 / M64 / M65 Series (Hydro) ──────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="microbt", canonical_name="Whatsminer M63 (366-372 TH)", model_number="M63",
         generation="M63 Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=369.0, stock_power_w=7283, stock_efficiency_j_th=eff(369.0, 7283),
         asic_chip="Samsung 5nm+", process_node="5nm", release_date="2023-10-01",
         is_current_product=True, notes="4U Blade. Range 366-372 TH. ASIC Miner Value: 334TH @ 6646W. Noise 50dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m63"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M63S (390-416 TH)", model_number="M63S",
         generation="M63 Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=390.0, stock_power_w=7215, stock_efficiency_j_th=eff(390.0, 7215),
         asic_chip="Samsung 5nm+", process_node="5nm", release_date="2023-10-01",
         is_current_product=True, notes="4U Blade. Noise 50dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m63s"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M63S+ (450 TH)", model_number="M63S+",
         generation="M63 Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=450.0, stock_power_w=7650, stock_efficiency_j_th=17.0,
         asic_chip="Samsung 5nm+", process_node="5nm", release_date="2025-07-01",
         is_current_product=True, notes="4U Blade. ASIC Miner Value: 424TH @ 7208W (17 J/TH). Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m63s-plus"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M63S++ (464-478 TH)", model_number="M63S++",
         generation="M63 Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=464.0, stock_power_w=7200, stock_efficiency_j_th=eff(464.0, 7200),
         asic_chip="Samsung 5nm+", process_node="5nm", release_date="2024-12-01",
         is_current_product=True, notes="Announced at Bitcoin MENA 2024. Range 464-478 TH. ASIC Miner Value: 464TH @ 7200W (15.52 J/TH). Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m63s-plus-plus"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M64 (202-206 TH)", model_number="M64",
         generation="M64 Series", cooling_type="hydro", hashboard_count=2,
         stock_hashrate_th=204.0, stock_power_w=4059, stock_efficiency_j_th=eff(204.0, 4059),
         asic_chip="Samsung 5nm+", process_node="5nm", release_date="2024-01-01",
         is_current_product=True, notes="2U Blade; single-phase 220-277V. Home heating variant. Range 202-206 TH.", source_urls=MICROBT_SOURCES),
    dict(manufacturer="microbt", canonical_name="Whatsminer M64S+ (236 TH)", model_number="M64S+",
         generation="M64 Series", cooling_type="hydro", hashboard_count=2,
         stock_hashrate_th=236.0, stock_power_w=4012, stock_efficiency_j_th=17.0,
         asic_chip="Samsung 5nm+", process_node="5nm", release_date="2024-12-01",
         is_current_product=True, notes="Max outlet water temp 80°C. Announced at Bitcoin MENA 2024.", source_urls=MICROBT_SOURCES),
    dict(manufacturer="microbt", canonical_name="Whatsminer M65S (390-412 TH)", model_number="M65S",
         generation="M65 Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=390.0, stock_power_w=7308, stock_efficiency_j_th=eff(390.0, 7308),
         asic_chip="Samsung 5nm+", process_node="5nm", release_date="2024-01-01",
         is_current_product=True, notes="4U Blade; 80°C outlet water temp. High-temp hydro variant.", source_urls=MICROBT_SOURCES),
    dict(manufacturer="microbt", canonical_name="Whatsminer M65S+ (440 TH)", model_number="M65S+",
         generation="M65 Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=440.0, stock_power_w=7480, stock_efficiency_j_th=17.0,
         asic_chip="Samsung 5nm+", process_node="5nm", release_date="2024-12-01",
         is_current_product=True, notes="Announced at Bitcoin MENA 2024.", source_urls=MICROBT_SOURCES),
]

# ── Gen 6: M66 Series (Immersion) ────────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="microbt", canonical_name="Whatsminer M66 (276 TH)", model_number="M66",
         generation="M66 Series", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=276.0, stock_power_w=5492, stock_efficiency_j_th=eff(276.0, 5492),
         asic_chip="Samsung 5nm+", process_node="5nm", release_date="2023-10-01",
         is_current_product=True, notes="Slim immersion. ASIC Miner Value: 280TH @ 5572W (19.9 J/TH). Noise 50dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m66"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M66S (286-298 TH)", model_number="M66S",
         generation="M66 Series", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=298.0, stock_power_w=5513, stock_efficiency_j_th=eff(298.0, 5513),
         asic_chip="Samsung 5nm+", process_node="5nm", release_date="2023-11-01",
         is_current_product=True, notes="Slim immersion. Noise 50dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m66s"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M66S+ (318 TH)", model_number="M66S+",
         generation="M66 Series", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=318.0, stock_power_w=5406, stock_efficiency_j_th=17.0,
         asic_chip="Samsung 5nm+", process_node="5nm", release_date="2024-08-01",
         is_current_product=True, notes="Slim immersion. Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m66s-plus"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M66S++ (356-470 TH)", model_number="M66S++",
         generation="M66 Series", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=470.0, stock_power_w=7200, stock_efficiency_j_th=eff(470.0, 7200),
         asic_chip="Samsung 5nm+", process_node="5nm", release_date="2024-12-01",
         is_current_product=True, notes="Announced Bitcoin MENA 2024. ASIC Miner Value: 470TH @ 7200W (15.32 J/TH). Noise 50dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m66s-plus-plus"),
]

# ── Gen 6: M6DS Series (2026, Hydro) ────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="microbt", canonical_name="Whatsminer M6DS+ (504 TH)", model_number="M6DS+",
         generation="M6DS Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=504.0, stock_power_w=8568, stock_efficiency_j_th=17.0,
         asic_chip="—", process_node="—", release_date="2026-03-01",
         is_current_product=True, notes="4U Blade. Next-gen chip. Noise 75dB.", source_urls=MICROBT_SOURCES),
    dict(manufacturer="microbt", canonical_name="Whatsminer M6DS++ (556-592 TH)", model_number="M6DS++",
         generation="M6DS Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=592.0, stock_power_w=9200, stock_efficiency_j_th=eff(592.0, 9200),
         asic_chip="—", process_node="—", release_date="2026-03-01",
         is_current_product=True, notes="Range 556-592 TH. ASIC Miner Value: 592TH @ 9200W. Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m6ds-plus-plus"),
    # M7DS (from ASIC Miner Value)
    dict(manufacturer="microbt", canonical_name="Whatsminer M7DS (680 TH)", model_number="M7DS",
         generation="M7DS Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=680.0, stock_power_w=9200, stock_efficiency_j_th=eff(680.0, 9200),
         asic_chip="—", process_node="—", release_date="2026-03-01",
         is_current_product=True, notes="ASIC Miner Value: 680TH @ 9200W (13.53 J/TH). Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m7ds"),
]

# ── Gen 7: M70 / M72 Series (Air) ────────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="microbt", canonical_name="Whatsminer M70 (214 TH)", model_number="M70",
         generation="M70 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=214.0, stock_power_w=3140, stock_efficiency_j_th=eff(214.0, 3140),
         asic_chip="—", process_node="—", release_date="2025-12-01",
         is_current_product=True, notes="Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m70"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M70S (226 TH)", model_number="M70S",
         generation="M70 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=226.0, stock_power_w=3140, stock_efficiency_j_th=eff(226.0, 3140),
         asic_chip="—", process_node="—", release_date="2025-12-01",
         is_current_product=True, notes="Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m70s"),
    # M70S+ — from ASIC Miner Value
    dict(manufacturer="microbt", canonical_name="Whatsminer M70S+ (244 TH)", model_number="M70S+",
         generation="M70 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=244.0, stock_power_w=3140, stock_efficiency_j_th=eff(244.0, 3140),
         asic_chip="—", process_node="—", release_date="2025-12-01",
         is_current_product=True, notes="Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m70splus"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M72 (246 TH)", model_number="M72",
         generation="M72 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=246.0, stock_power_w=4000, stock_efficiency_j_th=eff(246.0, 4000),
         asic_chip="—", process_node="—", release_date="2025-12-01",
         is_current_product=True, notes="", source_urls=MICROBT_SOURCES),
    dict(manufacturer="microbt", canonical_name="Whatsminer M72S (264 TH)", model_number="M72S",
         generation="M72 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=264.0, stock_power_w=4000, stock_efficiency_j_th=eff(264.0, 4000),
         asic_chip="—", process_node="—", release_date="2025-12-01",
         is_current_product=True, notes="", source_urls=MICROBT_SOURCES),
    # M72S hydro from ASIC Miner Value
    dict(manufacturer="microbt", canonical_name="Whatsminer M72S (920 TH Hydro)", model_number="M72S",
         generation="M72 Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=920.0, stock_power_w=14500, stock_efficiency_j_th=eff(920.0, 14500),
         asic_chip="—", process_node="—", release_date="2026-01-01",
         is_current_product=True, notes="Hydro variant. ASIC Miner Value: 920TH @ 14500W (15.76 J/TH). Noise 50dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m72s"),
]

# ── Gen 7: M73 / M79 Series (Hydro) ────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="microbt", canonical_name="Whatsminer M73 (470 TH)", model_number="M73",
         generation="M73 Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=470.0, stock_power_w=7200, stock_efficiency_j_th=eff(470.0, 7200),
         asic_chip="—", process_node="—", release_date="2025-12-01",
         is_current_product=True, notes="4U Blade. Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m73"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M73S (500 TH)", model_number="M73S",
         generation="M73 Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=500.0, stock_power_w=7200, stock_efficiency_j_th=eff(500.0, 7200),
         asic_chip="—", process_node="—", release_date="2025-12-01",
         is_current_product=True, notes="4U Blade. Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m73s"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M73S+ (540 TH)", model_number="M73S+",
         generation="M73 Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=540.0, stock_power_w=7200, stock_efficiency_j_th=eff(540.0, 7200),
         asic_chip="—", process_node="—", release_date="2025-12-01",
         is_current_product=True, notes="4U Blade. Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m73s-plus"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M76 (336 TH)", model_number="M76",
         generation="M76 Series", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=336.0, stock_power_w=5200, stock_efficiency_j_th=eff(336.0, 5200),
         asic_chip="—", process_node="—", release_date="2025-12-01",
         is_current_product=True, notes="Slim immersion. Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m76"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M76S (362 TH)", model_number="M76S",
         generation="M76 Series", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=362.0, stock_power_w=5200, stock_efficiency_j_th=eff(362.0, 5200),
         asic_chip="—", process_node="—", release_date="2025-12-01",
         is_current_product=True, notes="Slim immersion. Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m76s"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M76S+ (390 TH)", model_number="M76S+",
         generation="M76 Series", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=390.0, stock_power_w=5200, stock_efficiency_j_th=eff(390.0, 5200),
         asic_chip="—", process_node="—", release_date="2025-12-01",
         is_current_product=True, notes="Slim immersion. Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m76s-plus"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M78 (440 TH)", model_number="M78",
         generation="M78 Series", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=440.0, stock_power_w=7000, stock_efficiency_j_th=eff(440.0, 7000),
         asic_chip="—", process_node="—", release_date="2025-12-01",
         is_current_product=True, notes="Slim immersion (large).", source_urls=MICROBT_SOURCES),
    dict(manufacturer="microbt", canonical_name="Whatsminer M78S (472 TH)", model_number="M78S",
         generation="M78 Series", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=472.0, stock_power_w=6550, stock_efficiency_j_th=eff(472.0, 6550),
         asic_chip="—", process_node="—", release_date="2025-12-01",
         is_current_product=True, notes="Slim immersion. ASIC Miner Value: 472TH @ 6550W (13.88 J/TH). Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m78s"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M79 (870 TH)", model_number="M79",
         generation="M79 Series", cooling_type="hydro", hashboard_count=8,
         stock_hashrate_th=870.0, stock_power_w=14000, stock_efficiency_j_th=eff(870.0, 14000),
         asic_chip="—", process_node="—", release_date="2025-12-01",
         is_current_product=True, notes="8U Dual-Blade (2x M73). ASIC Miner Value: 920TH @ 14500W (15.76). Noise 50dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m79"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M79S (930 TH)", model_number="M79S",
         generation="M79 Series", cooling_type="hydro", hashboard_count=8,
         stock_hashrate_th=930.0, stock_power_w=14000, stock_efficiency_j_th=eff(930.0, 14000),
         asic_chip="—", process_node="—", release_date="2025-12-01",
         is_current_product=True, notes="8U Dual-Blade. ASIC Miner Value: 1350TH @ 20000W. Noise 50dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m79s"),
]

# ── Gen 7: M7D Series ─────────────────────────────────────────────────────────
ALL_MINERS += [
    dict(manufacturer="microbt", canonical_name="Whatsminer M7D (594 TH)", model_number="M7D",
         generation="M7D Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=594.0, stock_power_w=8613, stock_efficiency_j_th=eff(594.0, 8613),
         asic_chip="—", process_node="—", release_date="2026-03-01",
         is_current_product=True, notes="4U Blade. ASIC Miner Value: 634TH @ 9200W (14.51 J/TH). Noise 75dB.",
         source_urls=MICROBT_SOURCES + ",https://www.asicminervalue.com/miners/whatsminer-m7d"),
    dict(manufacturer="microbt", canonical_name="Whatsminer M7DS (638 TH)", model_number="M7DS",
         generation="M7D Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=638.0, stock_power_w=8613, stock_efficiency_j_th=eff(638.0, 8613),
         asic_chip="—", process_node="—", release_date="2026-03-01",
         is_current_product=True, notes="4U Blade.", source_urls=MICROBT_SOURCES),
]

# ═══════════════════════════════════════════════════════════════════════════════
# CANAAN — 64 variants from deep dive
# ═══════════════════════════════════════════════════════════════════════════════

CANAAN_SOURCES = "https://shop.canaan.io,https://www.asicminervalue.com/manufacturers/canaan,https://hashrateindex.com,https://d-central.tech"

ALL_MINERS += [
    # Gen 1 — Avalon1
    dict(manufacturer="canaan", canonical_name="Avalon1 Batch 1 (66 GH/s)", model_number="Avalon1 B1",
         generation="Avalon1 Gen1", cooling_type="air", hashboard_count=4,
         stock_hashrate_th=0.066, stock_power_w=620, stock_efficiency_j_th=eff(0.066, 620),
         asic_chip="A3256", process_node="110nm", release_date="2013-01-01",
         is_current_product=False, notes="Original open-source miner. 2+2 module config.", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="Avalon1 Batch 2 (82 GH/s)", model_number="Avalon1 B2",
         generation="Avalon1 Gen1", cooling_type="air", hashboard_count=4,
         stock_hashrate_th=0.082, stock_power_w=700, stock_efficiency_j_th=eff(0.082, 700),
         asic_chip="A3256", process_node="110nm", release_date="2013-01-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="Avalon1 Batch 3 (82 GH/s)", model_number="Avalon1 B3",
         generation="Avalon1 Gen1", cooling_type="air", hashboard_count=4,
         stock_hashrate_th=0.082, stock_power_w=700, stock_efficiency_j_th=eff(0.082, 700),
         asic_chip="A3256", process_node="110nm", release_date="2013-01-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    # Gen 2 — Avalon2
    dict(manufacturer="canaan", canonical_name="Avalon2", model_number="Avalon2",
         generation="Avalon2 Gen2", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=0.300, stock_power_w=1020, stock_efficiency_j_th=3400.0,
         asic_chip="A3255", process_node="55nm", release_date="2013-01-01",
         is_current_product=False, notes="Normal: 315GH/1020W; ECO: 210GH/420W.", source_urls=CANAAN_SOURCES),
    # Gen 3 — Avalon3
    dict(manufacturer="canaan", canonical_name="Avalon3", model_number="Avalon3",
         generation="Avalon3 Gen3", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=0.800, stock_power_w=1500, stock_efficiency_j_th=eff(0.800, 1500),
         asic_chip="A3233", process_node="40nm", release_date="2014-01-01",
         is_current_product=False, notes="~800 GH/s.", source_urls=CANAAN_SOURCES),
    # Gen 4 — Avalon4
    dict(manufacturer="canaan", canonical_name="Avalon4 / Avalon4.1 (1.3 TH/s)", model_number="Avalon4",
         generation="Avalon4 Gen4", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=1.3, stock_power_w=910, stock_efficiency_j_th=eff(1.3, 910),
         asic_chip="A3222", process_node="40nm", release_date="2014-01-01",
         is_current_product=False, notes="A3222 chip, 40nm. 40 chips at 0.7 W/GH.", source_urls=CANAAN_SOURCES),
    # Gen 6 — Avalon6
    dict(manufacturer="canaan", canonical_name="Avalon6", model_number="Avalon6",
         generation="Avalon6 Gen6", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=3.5, stock_power_w=1080, stock_efficiency_j_th=eff(3.5, 1080),
         asic_chip="A3218", process_node="28nm", release_date="2015-01-01",
         is_current_product=False, notes="0.29 J/GH.", source_urls=CANAAN_SOURCES),
    # Gen 7 — Avalon 721 / 741 / 761
    dict(manufacturer="canaan", canonical_name="AvalonMiner 721", model_number="A721",
         generation="Avalon7 Gen7", cooling_type="air", hashboard_count=1,
         stock_hashrate_th=6.0, stock_power_w=900, stock_efficiency_j_th=150.0,
         asic_chip="A3212", process_node="16nm", release_date="2016-11-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="AvalonMiner 741", model_number="A741",
         generation="Avalon7 Gen7", cooling_type="air", hashboard_count=1,
         stock_hashrate_th=7.3, stock_power_w=1150, stock_efficiency_j_th=eff(7.3, 1150),
         asic_chip="A3212", process_node="16nm", release_date="2017-04-01",
         is_current_product=False, notes="88 × A3212 chips. Noise 65dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/avalonminer-741"),
    dict(manufacturer="canaan", canonical_name="AvalonMiner 761", model_number="A761",
         generation="Avalon7 Gen7", cooling_type="air", hashboard_count=1,
         stock_hashrate_th=8.8, stock_power_w=1320, stock_efficiency_j_th=150.0,
         asic_chip="A3212", process_node="16nm", release_date="2017-01-01",
         is_current_product=False, notes="104 × A3212 chips.", source_urls=CANAAN_SOURCES),
    # Gen 8 — Avalon 821 / 841 / 851 / 852
    dict(manufacturer="canaan", canonical_name="AvalonMiner 821 (11 TH)", model_number="A821",
         generation="Avalon8 Gen8", cooling_type="air", hashboard_count=4,
         stock_hashrate_th=11.0, stock_power_w=1200, stock_efficiency_j_th=eff(11.0, 1200),
         asic_chip="A3210", process_node="16nm", release_date="2018-02-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="AvalonMiner 821 (11.5 TH)", model_number="A821",
         generation="Avalon8 Gen8", cooling_type="air", hashboard_count=4,
         stock_hashrate_th=11.5, stock_power_w=1200, stock_efficiency_j_th=eff(11.5, 1200),
         asic_chip="A3210", process_node="16nm", release_date="2018-02-01",
         is_current_product=False, notes="Noise 72dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/avalonminer-821"),
    dict(manufacturer="canaan", canonical_name="AvalonMiner 841", model_number="A841",
         generation="Avalon8 Gen8", cooling_type="air", hashboard_count=4,
         stock_hashrate_th=13.0, stock_power_w=1290, stock_efficiency_j_th=eff(13.0, 1290),
         asic_chip="A3210HP", process_node="16nm", release_date="2018-04-01",
         is_current_product=False, notes="ASIC Miner Value: 13.6TH @ 1290W (94.85 J/TH). Noise 65dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/avalonminer-841"),
    dict(manufacturer="canaan", canonical_name="AvalonMiner 851", model_number="A851",
         generation="Avalon8 Gen8", cooling_type="air", hashboard_count=4,
         stock_hashrate_th=14.5, stock_power_w=1450, stock_efficiency_j_th=100.0,
         asic_chip="A3210HP", process_node="16nm", release_date="2018-01-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="AvalonMiner 852", model_number="A852",
         generation="Avalon8 Gen8", cooling_type="air", hashboard_count=4,
         stock_hashrate_th=15.0, stock_power_w=1500, stock_efficiency_j_th=100.0,
         asic_chip="A3210HP", process_node="16nm", release_date="2019-01-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    # Gen 9 — Avalon 910 / 911 / 920 / 921
    dict(manufacturer="canaan", canonical_name="AvalonMiner 910", model_number="A910",
         generation="Avalon9 Gen9", cooling_type="air", hashboard_count=1,
         stock_hashrate_th=16.0, stock_power_w=1350, stock_efficiency_j_th=84.0,
         asic_chip="A3207", process_node="7nm", release_date="2019-01-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="AvalonMiner 911", model_number="A911",
         generation="Avalon9 Gen9", cooling_type="air", hashboard_count=1,
         stock_hashrate_th=18.0, stock_power_w=1440, stock_efficiency_j_th=80.0,
         asic_chip="A3207", process_node="7nm", release_date="2019-07-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="AvalonMiner 920", model_number="A920",
         generation="Avalon9 Gen9", cooling_type="air", hashboard_count=1,
         stock_hashrate_th=18.0, stock_power_w=1720, stock_efficiency_j_th=96.0,
         asic_chip="A3207", process_node="7nm", release_date="2019-01-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="AvalonMiner 921", model_number="A921",
         generation="Avalon9 Gen9", cooling_type="air", hashboard_count=1,
         stock_hashrate_th=20.0, stock_power_w=1700, stock_efficiency_j_th=85.0,
         asic_chip="A3207", process_node="7nm", release_date="2018-09-01",
         is_current_product=False, notes="Noise 72dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/avalonminer-921"),
    # Gen 10 — Avalon 1026 / 1041 / 1047 / 1066 / 1066 Pro
    dict(manufacturer="canaan", canonical_name="AvalonMiner 1026", model_number="A1026",
         generation="Avalon10 Gen10", cooling_type="air", hashboard_count=2,
         stock_hashrate_th=30.0, stock_power_w=2070, stock_efficiency_j_th=69.0,
         asic_chip="A3205", process_node="16nm", release_date="2019-01-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="AvalonMiner 1041", model_number="A1041",
         generation="Avalon10 Gen10", cooling_type="air", hashboard_count=2,
         stock_hashrate_th=31.0, stock_power_w=1736, stock_efficiency_j_th=56.0,
         asic_chip="A3205", process_node="16nm", release_date="2019-01-01",
         is_current_product=False, notes="240 × A3205 chips.", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="AvalonMiner 1047", model_number="A1047",
         generation="Avalon10 Gen10", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=37.0, stock_power_w=2380, stock_efficiency_j_th=eff(37.0, 2380),
         asic_chip="A3205", process_node="16nm", release_date="2019-09-01",
         is_current_product=False, notes="Noise 72dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/avalonminer-1047"),
    dict(manufacturer="canaan", canonical_name="AvalonMiner 1066", model_number="A1066",
         generation="Avalon10 Gen10", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=50.0, stock_power_w=3250, stock_efficiency_j_th=65.0,
         asic_chip="A3205", process_node="16nm", release_date="2019-09-01",
         is_current_product=False, notes="342 × A3205. ASIC Miner Value: 63TH @ 3276W (52 J/TH). Noise 72dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/avalonminer-1066"),
    dict(manufacturer="canaan", canonical_name="AvalonMiner 1066 Pro", model_number="A1066 Pro",
         generation="Avalon10 Gen10", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=55.0, stock_power_w=3276, stock_efficiency_j_th=60.0,
         asic_chip="A3205", process_node="16nm", release_date="2020-02-01",
         is_current_product=False, notes="342 × A3205 chips.", source_urls=CANAAN_SOURCES),
    # Gen 11 — Avalon 1126 Pro / 1146 / 1146 Pro / 1166 / 1166 Pro
    dict(manufacturer="canaan", canonical_name="AvalonMiner 1126 Pro (60 TH)", model_number="A1126 Pro",
         generation="Avalon11 Gen11", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=60.0, stock_power_w=3420, stock_efficiency_j_th=57.0,
         asic_chip="A3202", process_node="7nm", release_date="2021-08-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="AvalonMiner 1126 Pro (64 TH)", model_number="A1126 Pro",
         generation="Avalon11 Gen11", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=64.0, stock_power_w=3420, stock_efficiency_j_th=53.0,
         asic_chip="A3202", process_node="7nm", release_date="2021-08-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="AvalonMiner 1126 Pro (68 TH)", model_number="A1126 Pro",
         generation="Avalon11 Gen11", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=68.0, stock_power_w=3420, stock_efficiency_j_th=50.0,
         asic_chip="A3202", process_node="7nm", release_date="2021-08-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/avalonminer-1126-pro"),
    dict(manufacturer="canaan", canonical_name="AvalonMiner 1146", model_number="A1146",
         generation="Avalon11 Gen11", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=56.0, stock_power_w=3192, stock_efficiency_j_th=57.0,
         asic_chip="A3202", process_node="7nm", release_date="2020-02-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="AvalonMiner 1146 Pro (63 TH)", model_number="A1146 Pro",
         generation="Avalon11 Gen11", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=63.0, stock_power_w=3276, stock_efficiency_j_th=52.0,
         asic_chip="A3202", process_node="7nm", release_date="2020-08-01",
         is_current_product=False, notes="ASIC Miner Value: 130TH @ 3250W (25 J/TH) — conflicting entries. Separate model confirmed.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/avalonminer-1146-pro"),
    dict(manufacturer="canaan", canonical_name="AvalonMiner 1166", model_number="A1166",
         generation="Avalon11 Gen11", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=68.0, stock_power_w=3196, stock_efficiency_j_th=47.0,
         asic_chip="A3204", process_node="7nm", release_date="2020-01-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="AvalonMiner 1166 Pro (72 TH)", model_number="A1166 Pro",
         generation="Avalon11 Gen11", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=72.0, stock_power_w=3420, stock_efficiency_j_th=48.0,
         asic_chip="A3202", process_node="7nm", release_date="2020-08-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="AvalonMiner 1166 Pro (75 TH)", model_number="A1166 Pro",
         generation="Avalon11 Gen11", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=75.0, stock_power_w=3276, stock_efficiency_j_th=44.0,
         asic_chip="A3202", process_node="7nm", release_date="2020-08-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="AvalonMiner 1166 Pro (78 TH)", model_number="A1166 Pro",
         generation="Avalon11 Gen11", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=78.0, stock_power_w=3276, stock_efficiency_j_th=42.0,
         asic_chip="A3202", process_node="7nm", release_date="2020-08-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="AvalonMiner 1166 Pro (81 TH)", model_number="A1166 Pro",
         generation="Avalon11 Gen11", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=81.0, stock_power_w=3400, stock_efficiency_j_th=eff(81.0, 3400),
         asic_chip="A3202", process_node="7nm", release_date="2020-08-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/avalonminer-1166-pro"),
    # Gen 12 — Avalon A1246 / A1266
    dict(manufacturer="canaan", canonical_name="Avalon A1246 (83 TH)", model_number="A1246",
         generation="Avalon12 Gen12", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=83.0, stock_power_w=3420, stock_efficiency_j_th=41.0,
         asic_chip="A12", process_node="7nm", release_date="2021-01-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="Avalon A1246 (85 TH)", model_number="A1246",
         generation="Avalon12 Gen12", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=85.0, stock_power_w=3420, stock_efficiency_j_th=40.0,
         asic_chip="A12", process_node="7nm", release_date="2021-01-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="Avalon A1246 (90 TH)", model_number="A1246",
         generation="Avalon12 Gen12", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=90.0, stock_power_w=3420, stock_efficiency_j_th=38.0,
         asic_chip="A12", process_node="7nm", release_date="2021-01-01",
         is_current_product=False, notes="ASIC Miner Value: 90TH @ 3420W (38 J/TH). Noise 75dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/avalonminer-1246"),
    dict(manufacturer="canaan", canonical_name="Avalon A1246 (93 TH)", model_number="A1246",
         generation="Avalon12 Gen12", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=93.0, stock_power_w=3420, stock_efficiency_j_th=37.0,
         asic_chip="A12", process_node="7nm", release_date="2021-01-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="Avalon A1246 (96 TH)", model_number="A1246",
         generation="Avalon12 Gen12", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=96.0, stock_power_w=3420, stock_efficiency_j_th=36.0,
         asic_chip="A12", process_node="7nm", release_date="2020-12-01",
         is_current_product=False, notes="First-shipped bin.", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="Avalon A1266 (100 TH)", model_number="A1266",
         generation="Avalon12 Gen12", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=100.0, stock_power_w=3500, stock_efficiency_j_th=35.0,
         asic_chip="A12", process_node="7nm", release_date="2022-04-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    # Gen 13 — Avalon A1326 / A1346 / A1366 / A1366I
    dict(manufacturer="canaan", canonical_name="Avalon A1326 (106-115 TH)", model_number="A1326",
         generation="Avalon13 Gen13", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=110.0, stock_power_w=3425, stock_efficiency_j_th=31.0,
         asic_chip="A3246", process_node="7nm", release_date="2022-11-01",
         is_current_product=False, notes="Range 106-115 TH. Midpoint shown.", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="Avalon A1346 (110 TH)", model_number="A1346",
         generation="Avalon13 Gen13", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=110.0, stock_power_w=3300, stock_efficiency_j_th=30.0,
         asic_chip="A3246", process_node="7nm", release_date="2022-10-01",
         is_current_product=False, notes="ASIC Miner Value: 150TH @ 3230W (21.53). Discrepancy — separate variant listed. Noise 75dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/avalon-made-a1346"),
    dict(manufacturer="canaan", canonical_name="Avalon A1366 (130 TH)", model_number="A1366",
         generation="Avalon13 Gen13", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=130.0, stock_power_w=3250, stock_efficiency_j_th=25.0,
         asic_chip="A3246", process_node="7nm", release_date="2022-10-01",
         is_current_product=False, notes="ASIC Miner Value: 135TH @ 3310W (24.52). Noise 75dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/avalon-made-a1366"),
    dict(manufacturer="canaan", canonical_name="Avalon A1366I (119 TH)", model_number="A1366I",
         generation="Avalon13 Gen13", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=119.0, stock_power_w=3570, stock_efficiency_j_th=30.0,
         asic_chip="A3246", process_node="7nm", release_date="2023-05-01",
         is_current_product=False, notes="ASIC Miner Value: Avalon Miner A1366I at 81TH @ 3400W (41.98 J/TH) — different variant or listing discrepancy.", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="Avalon A1366I (122 TH)", model_number="A1366I",
         generation="Avalon13 Gen13", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=122.0, stock_power_w=3570, stock_efficiency_j_th=29.0,
         asic_chip="A3246", process_node="7nm", release_date="2023-07-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="Avalon A1366I (165 TH)", model_number="A1366I",
         generation="Avalon13 Gen13", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=165.0, stock_power_w=4950, stock_efficiency_j_th=30.0,
         asic_chip="A3246", process_node="7nm", release_date="2023-01-01",
         is_current_product=False, notes="High-OC immersion variant.", source_urls=CANAAN_SOURCES),
    # Gen 14 — Avalon A1446 / A1466 / A1466I
    dict(manufacturer="canaan", canonical_name="Avalon A1446 (135 TH)", model_number="A1446",
         generation="Avalon14 Gen14", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=135.0, stock_power_w=3310, stock_efficiency_j_th=24.5,
         asic_chip="A3246", process_node="7nm", release_date="2023-09-01",
         is_current_product=False, notes="ASIC Miner Value: A1446 @ 119TH/3570W (30 J/TH). Noise 75dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/avalon-made-a1446"),
    dict(manufacturer="canaan", canonical_name="Avalon A1466 (150 TH)", model_number="A1466",
         generation="Avalon14 Gen14", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=150.0, stock_power_w=3230, stock_efficiency_j_th=21.5,
         asic_chip="A3246", process_node="7nm", release_date="2023-09-01",
         is_current_product=False, notes="ASIC Miner Value: Avalon Made A1466 @ 194TH/3647W (18.8). Separate newer batch. Noise 75dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/avalon-made-a1466"),
    dict(manufacturer="canaan", canonical_name="Avalon A1466I (153 TH)", model_number="A1466I",
         generation="Avalon14 Gen14", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=153.0, stock_power_w=3320, stock_efficiency_j_th=22.0,
         asic_chip="A3246", process_node="7nm", release_date="2023-09-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="Avalon A1466I (170 TH)", model_number="A1466I",
         generation="Avalon14 Gen14", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=170.0, stock_power_w=3317, stock_efficiency_j_th=20.0,
         asic_chip="A3246", process_node="7nm", release_date="2023-09-01",
         is_current_product=False, notes="", source_urls=CANAAN_SOURCES),
    # Gen 15 — Avalon A1566 / A1566I / A1566HA / A15 / A15 Pro / A15XP
    dict(manufacturer="canaan", canonical_name="Avalon A1566 (185 TH)", model_number="A1566",
         generation="Avalon15 Gen15", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=185.0, stock_power_w=3420, stock_efficiency_j_th=eff(185.0, 3420),
         asic_chip="A15", process_node="4nm", release_date="2024-10-01",
         is_current_product=True, notes="Noise 75dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/avalon-a1566"),
    dict(manufacturer="canaan", canonical_name="Avalon A1566I (249 TH)", model_number="A1566I",
         generation="Avalon15 Gen15", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=249.0, stock_power_w=4500, stock_efficiency_j_th=eff(249.0, 4500),
         asic_chip="A15", process_node="4nm", release_date="2024-06-01",
         is_current_product=True, notes="ASIC Miner Value: 261TH @ 4500W. Noise 50dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/avalon-a1566i"),
    dict(manufacturer="canaan", canonical_name="Avalon A1566I (261 TH)", model_number="A1566I",
         generation="Avalon15 Gen15", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=261.0, stock_power_w=4500, stock_efficiency_j_th=eff(261.0, 4500),
         asic_chip="A15", process_node="4nm", release_date="2024-07-01",
         is_current_product=True, notes="", source_urls=CANAAN_SOURCES),
    dict(manufacturer="canaan", canonical_name="Avalon A1566HA 2U (480 TH)", model_number="A1566HA",
         generation="Avalon15 Gen15", cooling_type="hydro", hashboard_count=6,
         stock_hashrate_th=480.0, stock_power_w=8064, stock_efficiency_j_th=eff(480.0, 8064),
         asic_chip="A15", process_node="4nm", release_date="2025-08-01",
         is_current_product=True, notes="2U rack hydro form factor. 6 hashboards. Noise 40dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/avalon-a1566ha"),
    dict(manufacturer="canaan", canonical_name="Avalon A15 (194 TH)", model_number="A15",
         generation="Avalon15 Gen15", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=194.0, stock_power_w=3647, stock_efficiency_j_th=eff(194.0, 3647),
         asic_chip="A15", process_node="4nm", release_date="2024-12-01",
         is_current_product=True, notes="Noise 75dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/a15-194t"),
    dict(manufacturer="canaan", canonical_name="Avalon A15 Pro (218 TH)", model_number="A15 Pro",
         generation="Avalon15 Gen15", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=218.0, stock_power_w=3662, stock_efficiency_j_th=eff(218.0, 3662),
         asic_chip="A15", process_node="4nm", release_date="2025-02-01",
         is_current_product=True, notes="Noise 75dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/a15pro-218t"),
    dict(manufacturer="canaan", canonical_name="Avalon A15 Pro (221 TH)", model_number="A15 Pro",
         generation="Avalon15 Gen15", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=221.0, stock_power_w=3662, stock_efficiency_j_th=eff(221.0, 3662),
         asic_chip="A15", process_node="4nm", release_date="2025-03-01",
         is_current_product=True, notes="Noise 75dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/a15pro-221t"),
    dict(manufacturer="canaan", canonical_name="Avalon A15XP (206 TH)", model_number="A15XP",
         generation="Avalon15 Gen15", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=206.0, stock_power_w=3667, stock_efficiency_j_th=eff(206.0, 3667),
         asic_chip="A15", process_node="4nm", release_date="2024-12-01",
         is_current_product=True, notes="Noise 75dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/a15xp-206t"),
    # Gen 16 — Avalon A16 / A16XP
    dict(manufacturer="canaan", canonical_name="Avalon A16 (282 TH)", model_number="A16",
         generation="Avalon16 Gen16", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=282.0, stock_power_w=3900, stock_efficiency_j_th=eff(282.0, 3900),
         asic_chip="A16", process_node="TBD (Samsung)", release_date="2026-03-01",
         is_current_product=True, notes="Samsung process. Noise 75dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/a16-282t"),
    dict(manufacturer="canaan", canonical_name="Avalon A16XP (300 TH)", model_number="A16XP",
         generation="Avalon16 Gen16", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=300.0, stock_power_w=3850, stock_efficiency_j_th=eff(300.0, 3850),
         asic_chip="A16", process_node="TBD (Samsung)", release_date="2026-04-01",
         is_current_product=True, notes="Noise 75dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/a16xp-300t"),
    # Consumer Line
    dict(manufacturer="canaan", canonical_name="Avalon Nano 3", model_number="Nano 3",
         generation="Consumer Line", cooling_type="air", hashboard_count=1,
         stock_hashrate_th=4.0, stock_power_w=140, stock_efficiency_j_th=35.0,
         asic_chip="~A12", process_node="7nm", release_date="2024-02-01",
         is_current_product=True, notes="USB-C, Wi-Fi, 10 integrated chips. Noise 35dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/avalon-nano-3"),
    dict(manufacturer="canaan", canonical_name="Avalon Nano 3S", model_number="Nano 3S",
         generation="Consumer Line", cooling_type="air", hashboard_count=1,
         stock_hashrate_th=6.0, stock_power_w=140, stock_efficiency_j_th=eff(6.0, 140),
         asic_chip="Next-gen", process_node="~4nm", release_date="2025-01-01",
         is_current_product=True, notes="50% more hashrate vs Nano 3. Noise 40dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/canaan"),    # Mini 3
    dict(manufacturer="canaan", canonical_name="Avalon Mini 3", model_number="Mini 3",
         generation="Consumer Line", cooling_type="air", hashboard_count=2,
         stock_hashrate_th=37.5, stock_power_w=800, stock_efficiency_j_th=eff(37.5, 800),
         asic_chip="A15", process_node="4nm", release_date="2025-01-01",
         is_current_product=True, notes="66 chips. Dual-use space heater form factor. Noise 55dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/avalon-mini-3"),
    # Avalon Q
    dict(manufacturer="canaan", canonical_name="Avalon Q", model_number="Avalon Q",
         generation="Consumer Line", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=90.0, stock_power_w=1674, stock_efficiency_j_th=eff(90.0, 1674),
         asic_chip="A15", process_node="4nm", release_date="2025-04-01",
         is_current_product=True, notes="Rack-style home miner, LCD, app control. Noise 45dB.",
         source_urls=CANAAN_SOURCES + ",https://www.asicminervalue.com/miners/avalon-q"),
]

# ═══════════════════════════════════════════════════════════════════════════════
# BITDEER / SEALMINER — 12 variants
# ═══════════════════════════════════════════════════════════════════════════════

BITDEER_SOURCES = "https://www.bitdeer.com,https://www.asicminervalue.com/manufacturers/bitdeer"

ALL_MINERS += [
    dict(manufacturer="bitdeer", canonical_name="SealMiner A4 Ultra Hydro (886 TH)", model_number="A4 Ultra Hydro",
         generation="SealMiner A4 Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=886.0, stock_power_w=8372, stock_efficiency_j_th=eff(886.0, 8372),
         asic_chip="SEAL04", process_node="—", release_date="2026-05-01",
         is_current_product=True, notes="Noise 50dB.",
         source_urls=BITDEER_SOURCES + ",https://www.asicminervalue.com/miners/sealminer-a4-ultra-hydro"),
    dict(manufacturer="bitdeer", canonical_name="SealMiner A4 Pro Air (336 TH)", model_number="A4 Pro Air",
         generation="SealMiner A4 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=336.0, stock_power_w=3662, stock_efficiency_j_th=eff(336.0, 3662),
         asic_chip="SEAL04", process_node="—", release_date="2026-05-01",
         is_current_product=True, notes="Noise 75dB.",
         source_urls=BITDEER_SOURCES + ",https://www.asicminervalue.com/miners/sealminer-a4-pro-air"),
    dict(manufacturer="bitdeer", canonical_name="SealMiner A4 Pro Hydro (680 TH)", model_number="A4 Pro Hydro",
         generation="SealMiner A4 Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=680.0, stock_power_w=7412, stock_efficiency_j_th=eff(680.0, 7412),
         asic_chip="SEAL04", process_node="—", release_date="2026-05-01",
         is_current_product=True, notes="Noise 50dB.",
         source_urls=BITDEER_SOURCES + ",https://www.asicminervalue.com/miners/sealminer-a4-pro-hydro"),
    dict(manufacturer="bitdeer", canonical_name="SealMiner A3 Pro Air (290 TH)", model_number="A3 Pro Air",
         generation="SealMiner A3 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=290.0, stock_power_w=3625, stock_efficiency_j_th=eff(290.0, 3625),
         asic_chip="SEAL03", process_node="—", release_date="2025-09-01",
         is_current_product=True, notes="Noise 75dB.",
         source_urls=BITDEER_SOURCES + ",https://www.asicminervalue.com/miners/sealminer-a3-pro-air"),
    dict(manufacturer="bitdeer", canonical_name="SealMiner A3 Pro Hydro (660 TH)", model_number="A3 Pro Hydro",
         generation="SealMiner A3 Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=660.0, stock_power_w=8250, stock_efficiency_j_th=eff(660.0, 8250),
         asic_chip="SEAL03", process_node="—", release_date="2025-09-01",
         is_current_product=True, notes="Noise 50dB.",
         source_urls=BITDEER_SOURCES + ",https://www.asicminervalue.com/miners/sealminer-a3-pro-hydro"),
    dict(manufacturer="bitdeer", canonical_name="SealMiner A3 Hydro (500 TH)", model_number="A3 Hydro",
         generation="SealMiner A3 Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=500.0, stock_power_w=6750, stock_efficiency_j_th=eff(500.0, 6750),
         asic_chip="SEAL03", process_node="—", release_date="2025-09-01",
         is_current_product=True, notes="Noise 50dB.",
         source_urls=BITDEER_SOURCES + ",https://www.asicminervalue.com/miners/sealminer-a3-hydro"),
    dict(manufacturer="bitdeer", canonical_name="SealMiner A3 Air (260 TH)", model_number="A3 Air",
         generation="SealMiner A3 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=260.0, stock_power_w=3640, stock_efficiency_j_th=eff(260.0, 3640),
         asic_chip="SEAL03", process_node="—", release_date="2025-09-01",
         is_current_product=True, notes="Noise 75dB.",
         source_urls=BITDEER_SOURCES + ",https://www.asicminervalue.com/miners/sealminer-a3-air"),
    dict(manufacturer="bitdeer", canonical_name="SealMiner A2 Pro Air (255 TH)", model_number="A2 Pro Air",
         generation="SealMiner A2 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=255.0, stock_power_w=3790, stock_efficiency_j_th=eff(255.0, 3790),
         asic_chip="SEAL02", process_node="—", release_date="2025-03-01",
         is_current_product=True, notes="Noise 75dB.",
         source_urls=BITDEER_SOURCES + ",https://www.asicminervalue.com/miners/sealminer-a2-pro-air"),
    dict(manufacturer="bitdeer", canonical_name="SealMiner A2 Pro Hyd (500 TH)", model_number="A2 Pro Hyd",
         generation="SealMiner A2 Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=500.0, stock_power_w=7450, stock_efficiency_j_th=eff(500.0, 7450),
         asic_chip="SEAL02", process_node="—", release_date="2025-03-01",
         is_current_product=True, notes="Noise 50dB.",
         source_urls=BITDEER_SOURCES + ",https://www.asicminervalue.com/miners/sealminer-a2-pro-hyd"),
    dict(manufacturer="bitdeer", canonical_name="SealMiner A2 Hyd (446 TH)", model_number="A2 Hyd",
         generation="SealMiner A2 Series", cooling_type="hydro", hashboard_count=4,
         stock_hashrate_th=446.0, stock_power_w=7360, stock_efficiency_j_th=eff(446.0, 7360),
         asic_chip="SEAL02", process_node="—", release_date="2025-02-01",
         is_current_product=True, notes="Noise 50dB.",
         source_urls=BITDEER_SOURCES + ",https://www.asicminervalue.com/miners/sealminer-a2-hyd"),
    dict(manufacturer="bitdeer", canonical_name="SealMiner A2 (226 TH)", model_number="A2",
         generation="SealMiner A2 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=226.0, stock_power_w=3730, stock_efficiency_j_th=eff(226.0, 3730),
         asic_chip="SEAL02", process_node="—", release_date="2025-02-01",
         is_current_product=True, notes="Noise 75dB.",
         source_urls=BITDEER_SOURCES + ",https://www.asicminervalue.com/miners/sealminer-a2"),
    dict(manufacturer="bitdeer", canonical_name="SealMiner DL1 Air (179 TH)", model_number="DL1 Air",
         generation="SealMiner DL1 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=179.0, stock_power_w=3580, stock_efficiency_j_th=eff(179.0, 3580),
         asic_chip="SEAL01", process_node="—", release_date="2025-01-01",
         is_current_product=True, notes="First-gen SealMiner. Noise 75dB.",
         source_urls=BITDEER_SOURCES + ",https://www.asicminervalue.com/miners/sealminer-dl1-air"),
]

# ═══════════════════════════════════════════════════════════════════════════════
# AURADINE — 3 variants
# ═══════════════════════════════════════════════════════════════════════════════

AURADINE_SOURCES = "https://www.auradine.com,https://www.asicminervalue.com/manufacturers/auradine"

ALL_MINERS += [
    dict(manufacturer="auradine", canonical_name="Auradine Teraflux AT2880 (180 TH)", model_number="AT2880",
         generation="Teraflux Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=180.0, stock_power_w=2880, stock_efficiency_j_th=16.0,
         asic_chip="—", process_node="—", release_date="2024-11-01",
         is_current_product=True, notes="Noise 70dB.",
         source_urls=AURADINE_SOURCES + ",https://www.asicminervalue.com/miners/teraflux-at2880"),
    dict(manufacturer="auradine", canonical_name="Auradine Teraflux AH3880 (600 TH)", model_number="AH3880",
         generation="Teraflux Series", cooling_type="hydro", hashboard_count=2,
         stock_hashrate_th=600.0, stock_power_w=10740, stock_efficiency_j_th=eff(600.0, 10740),
         asic_chip="—", process_node="—", release_date="2025-03-01",
         is_current_product=True, notes="Noise 35dB. Two hashboards confirmed (README.md, CLAUDE.md, miner_specs.json).",
         source_urls=AURADINE_SOURCES + ",https://www.asicminervalue.com/miners/teraflux-ah3880"),
    dict(manufacturer="auradine", canonical_name="Auradine Teraflux AI3680 (360 TH)", model_number="AI3680",
         generation="Teraflux Series", cooling_type="immersion", hashboard_count=3,
         stock_hashrate_th=360.0, stock_power_w=6840, stock_efficiency_j_th=19.0,
         asic_chip="—", process_node="—", release_date="2024-12-01",
         is_current_product=True, notes="Noise 50dB.",
         source_urls=AURADINE_SOURCES + ",https://www.asicminervalue.com/miners/pascal"),
]

# ═══════════════════════════════════════════════════════════════════════════════
# INNOSILICON — 11 variants
# ═══════════════════════════════════════════════════════════════════════════════

INNOSILICON_SOURCES = "https://www.innosilicon.com,https://www.asicminervalue.com/manufacturers/innosilicon"

ALL_MINERS += [
    dict(manufacturer="innosilicon", canonical_name="Innosilicon T2 Terminator (17.2 TH)", model_number="T2 Terminator",
         generation="T2 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=17.2, stock_power_w=1570, stock_efficiency_j_th=eff(17.2, 1570),
         asic_chip="—", process_node="—", release_date="2018-05-01",
         is_current_product=False, notes="Noise 72dB.",
         source_urls=INNOSILICON_SOURCES + ",https://www.asicminervalue.com/miners/t2-terminator"),
    dict(manufacturer="innosilicon", canonical_name="Innosilicon T2 Turbo 25T", model_number="T2T 25T",
         generation="T2 Turbo Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=25.0, stock_power_w=2100, stock_efficiency_j_th=84.0,
         asic_chip="—", process_node="—", release_date="2019-01-01",
         is_current_product=False, notes="Noise 72dB.",
         source_urls=INNOSILICON_SOURCES + ",https://www.asicminervalue.com/miners/t2-turbo-25t"),
    dict(manufacturer="innosilicon", canonical_name="Innosilicon T2 Turbo 26T", model_number="T2T 26T",
         generation="T2 Turbo Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=26.0, stock_power_w=2100, stock_efficiency_j_th=eff(26.0, 2100),
         asic_chip="—", process_node="—", release_date="2021-07-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=INNOSILICON_SOURCES + ",https://www.asicminervalue.com/miners/t2-turbo-26t"),
    dict(manufacturer="innosilicon", canonical_name="Innosilicon T2 Turbo 29T/30T", model_number="T2T 29T/30T",
         generation="T2 Turbo Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=30.0, stock_power_w=2400, stock_efficiency_j_th=80.0,
         asic_chip="—", process_node="—", release_date="2021-01-01",
         is_current_product=False, notes="Noise 72dB.",
         source_urls=INNOSILICON_SOURCES + ",https://www.asicminervalue.com/miners/t2-turbo-29t-30t"),
    dict(manufacturer="innosilicon", canonical_name="Innosilicon T2 Turbo+ 32T", model_number="T2T+ 32T",
         generation="T2 Turbo Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=32.0, stock_power_w=2200, stock_efficiency_j_th=eff(32.0, 2200),
         asic_chip="—", process_node="—", release_date="2018-09-01",
         is_current_product=False, notes="Noise 72dB.",
         source_urls=INNOSILICON_SOURCES + ",https://www.asicminervalue.com/miners/t2-turbo-32t"),
    dict(manufacturer="innosilicon", canonical_name="Innosilicon T2 Turbo HF+ (33 TH)", model_number="T2T HF+",
         generation="T2 Turbo Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=33.0, stock_power_w=2600, stock_efficiency_j_th=eff(33.0, 2600),
         asic_chip="—", process_node="—", release_date="2021-07-01",
         is_current_product=False, notes="HF+ variant. Noise 72dB.",
         source_urls=INNOSILICON_SOURCES + ",https://www.asicminervalue.com/miners/t2-turbo-hf"),
    dict(manufacturer="innosilicon", canonical_name="Innosilicon T3 39T", model_number="T3 39T",
         generation="T3 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=39.0, stock_power_w=2150, stock_efficiency_j_th=eff(39.0, 2150),
         asic_chip="—", process_node="—", release_date="2019-07-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=INNOSILICON_SOURCES + ",https://www.asicminervalue.com/miners/t3-39t"),
    dict(manufacturer="innosilicon", canonical_name="Innosilicon T3+ 43T", model_number="T3+ 43T",
         generation="T3 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=43.0, stock_power_w=2100, stock_efficiency_j_th=eff(43.0, 2100),
         asic_chip="—", process_node="—", release_date="2019-03-01",
         is_current_product=False, notes="Noise 72dB.",
         source_urls=INNOSILICON_SOURCES + ",https://www.asicminervalue.com/miners/t3-43t"),
    dict(manufacturer="innosilicon", canonical_name="Innosilicon T3 50T", model_number="T3 50T",
         generation="T3 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=52.0, stock_power_w=2800, stock_efficiency_j_th=eff(52.0, 2800),
         asic_chip="—", process_node="—", release_date="2019-05-01",
         is_current_product=False, notes="AMV listed as 52TH@2800W. Noise 72dB.",
         source_urls=INNOSILICON_SOURCES + ",https://www.asicminervalue.com/miners/t3-50t"),
    dict(manufacturer="innosilicon", canonical_name="Innosilicon T3+ 52T", model_number="T3+ 52T",
         generation="T3 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=52.0, stock_power_w=3200, stock_efficiency_j_th=eff(52.0, 3200),
         asic_chip="—", process_node="—", release_date="2018-09-01",
         is_current_product=False, notes="Noise 72dB.",
         source_urls=INNOSILICON_SOURCES + ",https://www.asicminervalue.com/miners/t3-52t"),
    dict(manufacturer="innosilicon", canonical_name="Innosilicon T3+ 57T", model_number="T3+ 57T",
         generation="T3 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=57.0, stock_power_w=3300, stock_efficiency_j_th=eff(57.0, 3300),
         asic_chip="—", process_node="—", release_date="2019-07-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=INNOSILICON_SOURCES + ",https://www.asicminervalue.com/miners/t3-57t"),
]

# ═══════════════════════════════════════════════════════════════════════════════
# EBANG — 10 variants
# ═══════════════════════════════════════════════════════════════════════════════

EBANG_SOURCES = "https://www.ebang.com.cn,https://www.asicminervalue.com/manufacturers/ebang"

ALL_MINERS += [
    dict(manufacturer="ebang", canonical_name="Ebang Ebit E9+ (9 TH)", model_number="E9+",
         generation="Ebit E9 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=9.0, stock_power_w=1300, stock_efficiency_j_th=eff(9.0, 1300),
         asic_chip="—", process_node="—", release_date="2018-01-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=EBANG_SOURCES + ",https://www.asicminervalue.com/miners/ebit-e9"),
    dict(manufacturer="ebang", canonical_name="Ebang Ebit E9.2 (12 TH)", model_number="E9.2",
         generation="Ebit E9 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=12.0, stock_power_w=1320, stock_efficiency_j_th=110.0,
         asic_chip="—", process_node="—", release_date="2018-09-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=EBANG_SOURCES + ",https://www.asicminervalue.com/miners/ebit-e9-2"),
    dict(manufacturer="ebang", canonical_name="Ebang Ebit E9.3 (16 TH)", model_number="E9.3",
         generation="Ebit E9 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=16.0, stock_power_w=1760, stock_efficiency_j_th=110.0,
         asic_chip="—", process_node="—", release_date="2018-05-01",
         is_current_product=False, notes="Noise 72dB.",
         source_urls=EBANG_SOURCES + ",https://www.asicminervalue.com/miners/ebit-e9-3"),
    dict(manufacturer="ebang", canonical_name="Ebang Ebit E9i (13.5 TH)", model_number="E9i",
         generation="Ebit E9 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=13.5, stock_power_w=1420, stock_efficiency_j_th=eff(13.5, 1420),
         asic_chip="—", process_node="—", release_date="2018-07-01",
         is_current_product=False, notes="Noise 74dB.",
         source_urls=EBANG_SOURCES + ",https://www.asicminervalue.com/miners/ebit-e9i"),
    dict(manufacturer="ebang", canonical_name="Ebang Ebit E10 (18 TH)", model_number="E10",
         generation="Ebit E10 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=18.0, stock_power_w=1650, stock_efficiency_j_th=eff(18.0, 1650),
         asic_chip="—", process_node="—", release_date="2018-02-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=EBANG_SOURCES + ",https://www.asicminervalue.com/miners/ebit-e10"),
    dict(manufacturer="ebang", canonical_name="Ebang Ebit E10D (25 TH)", model_number="E10D",
         generation="Ebit E10 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=25.0, stock_power_w=3500, stock_efficiency_j_th=140.0,
         asic_chip="—", process_node="—", release_date="2021-09-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=EBANG_SOURCES + ",https://www.asicminervalue.com/miners/ebit-e10d"),
    dict(manufacturer="ebang", canonical_name="Ebang Ebit E11 (30 TH)", model_number="E11",
         generation="Ebit E11 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=30.0, stock_power_w=1950, stock_efficiency_j_th=65.0,
         asic_chip="—", process_node="—", release_date="2018-10-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=EBANG_SOURCES + ",https://www.asicminervalue.com/miners/ebit-e11"),
    dict(manufacturer="ebang", canonical_name="Ebang Ebit E11++ (44 TH)", model_number="E11++",
         generation="Ebit E11 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=44.0, stock_power_w=1980, stock_efficiency_j_th=45.0,
         asic_chip="—", process_node="—", release_date="2018-10-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=EBANG_SOURCES + ",https://www.asicminervalue.com/miners/ebit-e11-2"),
    dict(manufacturer="ebang", canonical_name="Ebang Ebit E12 (44 TH)", model_number="E12",
         generation="Ebit E12 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=44.0, stock_power_w=2500, stock_efficiency_j_th=eff(44.0, 2500),
         asic_chip="—", process_node="—", release_date="2019-09-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=EBANG_SOURCES + ",https://www.asicminervalue.com/miners/ebit-e12"),
    dict(manufacturer="ebang", canonical_name="Ebang Ebit E12+ (50 TH)", model_number="E12+",
         generation="Ebit E12 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=50.0, stock_power_w=2500, stock_efficiency_j_th=50.0,
         asic_chip="—", process_node="—", release_date="2019-09-01",
         is_current_product=False, notes="Noise 75dB.",
         source_urls=EBANG_SOURCES + ",https://www.asicminervalue.com/miners/ebit-e12-1"),
]

# ═══════════════════════════════════════════════════════════════════════════════
# STRONGU — 9 variants
# ═══════════════════════════════════════════════════════════════════════════════

STRONGU_SOURCES = "https://www.strongu.com.cn,https://www.asicminervalue.com/manufacturers/strongu"

ALL_MINERS += [
    dict(manufacturer="strongu", canonical_name="StrongU Hornbill H8 Pro (84 TH)", model_number="H8 Pro",
         generation="Hornbill H8 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=84.0, stock_power_w=3360, stock_efficiency_j_th=40.0,
         asic_chip="—", process_node="—", release_date="2021-07-01",
         is_current_product=False, notes="Noise 76dB.",
         source_urls=STRONGU_SOURCES + ",https://www.asicminervalue.com/miners/hornbill-h8-pro"),
    dict(manufacturer="strongu", canonical_name="StrongU Hornbill H8 (74 TH)", model_number="H8",
         generation="Hornbill H8 Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=74.0, stock_power_w=3330, stock_efficiency_j_th=45.0,
         asic_chip="—", process_node="—", release_date="2020-10-01",
         is_current_product=False, notes="Noise 76dB.",
         source_urls=STRONGU_SOURCES + ",https://www.asicminervalue.com/miners/hornbill-h8"),
    dict(manufacturer="strongu", canonical_name="StrongU STU-U1 (44 TH)", model_number="STU-U1",
         generation="STU-U Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=44.0, stock_power_w=2200, stock_efficiency_j_th=50.0,
         asic_chip="—", process_node="—", release_date="2019-10-01",
         is_current_product=False, notes="Noise 76dB.",
         source_urls=STRONGU_SOURCES + ",https://www.asicminervalue.com/miners/stu-u1"),
    dict(manufacturer="strongu", canonical_name="StrongU STU-U1+ (52 TH)", model_number="STU-U1+",
         generation="STU-U Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=52.0, stock_power_w=2200, stock_efficiency_j_th=eff(52.0, 2200),
         asic_chip="—", process_node="—", release_date="2019-11-01",
         is_current_product=False, notes="Noise 76dB.",
         source_urls=STRONGU_SOURCES + ",https://www.asicminervalue.com/miners/stu-u1-1"),
    dict(manufacturer="strongu", canonical_name="StrongU STU-U1++ (60 TH)", model_number="STU-U1++",
         generation="STU-U Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=60.0, stock_power_w=2800, stock_efficiency_j_th=eff(60.0, 2800),
         asic_chip="—", process_node="—", release_date="2019-07-01",
         is_current_product=False, notes="Noise 76dB.",
         source_urls=STRONGU_SOURCES + ",https://www.asicminervalue.com/miners/stu-u1-2"),
    dict(manufacturer="strongu", canonical_name="StrongU STU-U2 (74 TH)", model_number="STU-U2",
         generation="STU-U Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=74.0, stock_power_w=3330, stock_efficiency_j_th=45.0,
         asic_chip="—", process_node="—", release_date="2020-10-01",
         is_current_product=False, notes="Noise 76dB.",
         source_urls=STRONGU_SOURCES + ",https://www.asicminervalue.com/miners/stu-u2"),
    dict(manufacturer="strongu", canonical_name="StrongU STU-U6 (84 TH)", model_number="STU-U6",
         generation="STU-U Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=84.0, stock_power_w=3360, stock_efficiency_j_th=40.0,
         asic_chip="—", process_node="—", release_date="2021-07-01",
         is_current_product=False, notes="Noise 76dB.",
         source_urls=STRONGU_SOURCES + ",https://www.asicminervalue.com/miners/stu-u6"),
    dict(manufacturer="strongu", canonical_name="StrongU STU-U8 (46 TH)", model_number="STU-U8",
         generation="STU-U Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=46.0, stock_power_w=2100, stock_efficiency_j_th=eff(46.0, 2100),
         asic_chip="—", process_node="—", release_date="2019-07-01",
         is_current_product=False, notes="Noise 76dB.",
         source_urls=STRONGU_SOURCES + ",https://www.asicminervalue.com/miners/stu-u8"),
    dict(manufacturer="strongu", canonical_name="StrongU STU-U8 Pro (60 TH)", model_number="STU-U8 Pro",
         generation="STU-U Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=60.0, stock_power_w=2800, stock_efficiency_j_th=eff(60.0, 2800),
         asic_chip="—", process_node="—", release_date="2019-09-01",
         is_current_product=False, notes="Noise 76dB.",
         source_urls=STRONGU_SOURCES + ",https://www.asicminervalue.com/miners/stu-u8-pro"),
]

# ═══════════════════════════════════════════════════════════════════════════════
# BITFURY — 2 variants
# ═══════════════════════════════════════════════════════════════════════════════

BITFURY_SOURCES = "https://bitfury.com,https://www.asicminervalue.com/manufacturers/bitfury"

ALL_MINERS += [
    dict(manufacturer="bitfury", canonical_name="Bitfury B8 (49 TH)", model_number="B8",
         generation="Bitfury B-Series", cooling_type="air", hashboard_count=8,
         stock_hashrate_th=49.0, stock_power_w=6400, stock_efficiency_j_th=eff(49.0, 6400),
         asic_chip="BF8301V", process_node="16nm", release_date="2017-12-01",
         is_current_product=False, notes="8 hashboards, enterprise miner. Noise 85dB.",
         source_urls=BITFURY_SOURCES + ",https://www.asicminervalue.com/miners/b8"),
    dict(manufacturer="bitfury", canonical_name="Bitfury Tardis (80 TH)", model_number="Tardis",
         generation="Bitfury Tardis Series", cooling_type="air", hashboard_count=8,
         stock_hashrate_th=80.0, stock_power_w=6300, stock_efficiency_j_th=eff(80.0, 6300),
         asic_chip="BF8301V", process_node="16nm", release_date="2018-11-01",
         is_current_product=False, notes="Enterprise miner. Noise 75dB.",
         source_urls=BITFURY_SOURCES + ",https://www.asicminervalue.com/miners/tardis"),
]

# ═══════════════════════════════════════════════════════════════════════════════
# HALONG MINING — 1 variant
# ═══════════════════════════════════════════════════════════════════════════════

HALONG_SOURCES = "https://halongmining.com,https://hashrateindex.com"

ALL_MINERS += [
    dict(manufacturer="halong", canonical_name="Halong Mining DragonMint T1 (16 TH)", model_number="DragonMint T1",
         generation="DragonMint Series", cooling_type="air", hashboard_count=3,
         stock_hashrate_th=16.0, stock_power_w=1480, stock_efficiency_j_th=eff(16.0, 1480),
         asic_chip="DM8575", process_node="16nm", release_date="2018-03-01",
         is_current_product=False, notes="Company went silent after 2018. First SHA-256 miner to challenge Bitmain directly.",
         source_urls=HALONG_SOURCES),
]

# ═══════════════════════════════════════════════════════════════════════════════
# KNCMINER — 3 variants (historical)
# ═══════════════════════════════════════════════════════════════════════════════

KNC_SOURCES = "https://en.bitcoin.it/wiki/KnCMiner,https://hashrateindex.com"

ALL_MINERS += [
    dict(manufacturer="kncminer", canonical_name="KnCMiner Neptune (3 TH)", model_number="Neptune",
         generation="KnC Neptune Series", cooling_type="air", hashboard_count=1,
         stock_hashrate_th=3.0, stock_power_w=2100, stock_efficiency_j_th=eff(3.0, 2100),
         asic_chip="—", process_node="28nm", release_date="2014-01-01",
         is_current_product=False, notes="Defunct company (2016). 28nm chip.",
         source_urls=KNC_SOURCES),
    dict(manufacturer="kncminer", canonical_name="KnCMiner Titan (300 GH/s)", model_number="Titan",
         generation="KnC Titan Series", cooling_type="air", hashboard_count=1,
         stock_hashrate_th=0.3, stock_power_w=250, stock_efficiency_j_th=eff(0.3, 250),
         asic_chip="—", process_node="28nm", release_date="2013-01-01",
         is_current_product=False, notes="Defunct company (2016).",
         source_urls=KNC_SOURCES),
    dict(manufacturer="kncminer", canonical_name="KnCMiner Solar (400 GH/s)", model_number="Solar",
         generation="KnC Solar Series", cooling_type="air", hashboard_count=1,
         stock_hashrate_th=0.4, stock_power_w=250, stock_efficiency_j_th=eff(0.4, 250),
         asic_chip="—", process_node="28nm", release_date="2014-01-01",
         is_current_product=False, notes="Defunct company (2016). Solar series.",
         source_urls=KNC_SOURCES),
]

# ═══════════════════════════════════════════════════════════════════════════════
# SPONDOOLIES-TECH — 3 variants (historical)
# ═══════════════════════════════════════════════════════════════════════════════

SPONDOOLIES_SOURCES = "https://en.bitcoin.it/wiki/Spondoolies-Tech"

ALL_MINERS += [
    dict(manufacturer="spondoolies", canonical_name="Spondoolies-Tech SP20 Jackson (1.3 TH)", model_number="SP20",
         generation="SP Series", cooling_type="air", hashboard_count=2,
         stock_hashrate_th=1.3, stock_power_w=1100, stock_efficiency_j_th=eff(1.3, 1100),
         asic_chip="—", process_node="28nm", release_date="2014-01-01",
         is_current_product=False, notes="Defunct company (2016).",
         source_urls=SPONDOOLIES_SOURCES),
    dict(manufacturer="spondoolies", canonical_name="Spondoolies-Tech SP31 Yukon (4.6 TH)", model_number="SP31",
         generation="SP Series", cooling_type="air", hashboard_count=4,
         stock_hashrate_th=4.6, stock_power_w=2400, stock_efficiency_j_th=eff(4.6, 2400),
         asic_chip="—", process_node="28nm", release_date="2015-01-01",
         is_current_product=False, notes="Defunct company (2016).",
         source_urls=SPONDOOLIES_SOURCES),
    dict(manufacturer="spondoolies", canonical_name="Spondoolies-Tech SP35 Yukon (5.5 TH)", model_number="SP35",
         generation="SP Series", cooling_type="air", hashboard_count=4,
         stock_hashrate_th=5.5, stock_power_w=3500, stock_efficiency_j_th=eff(5.5, 3500),
         asic_chip="—", process_node="28nm", release_date="2016-01-01",
         is_current_product=False, notes="Defunct company (2016).",
         source_urls=SPONDOOLIES_SOURCES),
]

# ═══════════════════════════════════════════════════════════════════════════════
# BUTTERFLY LABS — 3 variants (historical)
# ═══════════════════════════════════════════════════════════════════════════════

BFL_SOURCES = "https://en.bitcoin.it/wiki/Butterfly_Labs"

ALL_MINERS += [
    dict(manufacturer="butterfly_labs", canonical_name="Butterfly Labs Jalapeno (7 GH/s)", model_number="Jalapeno",
         generation="BFL Legacy", cooling_type="air", hashboard_count=1,
         stock_hashrate_th=0.007, stock_power_w=7, stock_efficiency_j_th=1000.0,
         asic_chip="—", process_node="65nm", release_date="2013-01-01",
         is_current_product=False, notes="Defunct/sued by FTC. First consumer SHA-256 ASIC.",
         source_urls=BFL_SOURCES),
    dict(manufacturer="butterfly_labs", canonical_name="Butterfly Labs Single SC (60 GH/s)", model_number="Single SC",
         generation="BFL Legacy", cooling_type="air", hashboard_count=1,
         stock_hashrate_th=0.060, stock_power_w=60, stock_efficiency_j_th=1000.0,
         asic_chip="—", process_node="65nm", release_date="2013-01-01",
         is_current_product=False, notes="Defunct/sued by FTC.",
         source_urls=BFL_SOURCES),
    dict(manufacturer="butterfly_labs", canonical_name="Butterfly Labs Monarch (700 GH/s)", model_number="Monarch",
         generation="BFL Monarch", cooling_type="air", hashboard_count=2,
         stock_hashrate_th=0.700, stock_power_w=350, stock_efficiency_j_th=500.0,
         asic_chip="—", process_node="28nm", release_date="2014-01-01",
         is_current_product=False, notes="Defunct/sued by FTC. Final BFL product.",
         source_urls=BFL_SOURCES),
]

# ═══════════════════════════════════════════════════════════════════════════════
# BITAXE — 7 variants (open-source SHA-256 miners by Open Source Miners United)
# ═══════════════════════════════════════════════════════════════════════════════
# Bitaxe is an open-source single-board ASIC miner family designed by skot9000
# and the Open Source Miners United (OSMU) community. Hardware schematics, KiCad
# files, and ESP-Miner firmware are public on GitHub. Chips (BM1366, BM1368,
# BM1370) are sourced from Bitmain Antminer S19 XP / S21 / S21 Pro hashboards.
# All units are SHA-256 / Bitcoin. Single-PCB design (hashboard_count=1)
# regardless of chip count.

BITAXE_SOURCES = "https://bitaxe.org,https://github.com/bitaxeorg,https://www.solosatoshi.com/bitaxe-overclocking-guide/,https://www.zeusbtc.com/blog/details/5694-bm1366-vs-bm1370-asic-chips"

ALL_MINERS += [
    # Current production — BM1370 chip (from Antminer S21 Pro)
    dict(manufacturer="bitaxe", canonical_name="Bitaxe Gamma 602 (1.07 TH)", model_number="Gamma 602",
         generation="Bitaxe Gamma", cooling_type="air", hashboard_count=1,
         stock_hashrate_th=1.07, stock_power_w=17.8, stock_efficiency_j_th=eff(1.07, 17.8),
         asic_chip="BM1370", process_node="5nm", release_date="2024-08-01",
         is_current_product=True, notes="Single-chip BM1370. Most popular Bitaxe — solo-mining lottery hardware. ESP-Miner firmware.",
         source_urls=BITAXE_SOURCES),
    dict(manufacturer="bitaxe", canonical_name="Bitaxe Gamma Duo 650 (1.63 TH)", model_number="Gamma Duo 650",
         generation="Bitaxe Gamma Duo", cooling_type="air", hashboard_count=1,
         stock_hashrate_th=1.63, stock_power_w=25.8, stock_efficiency_j_th=eff(1.63, 25.8),
         asic_chip="BM1370 (x2)", process_node="5nm", release_date="2025-09-01",
         is_current_product=True, notes="Dual BM1370 on single PCB. ~16 J/TH — most efficient Bitaxe to date.",
         source_urls=BITAXE_SOURCES),
    dict(manufacturer="bitaxe", canonical_name="Bitaxe GT 801 (2.15 TH)", model_number="GT 801",
         generation="Bitaxe GT", cooling_type="air", hashboard_count=1,
         stock_hashrate_th=2.15, stock_power_w=43.0, stock_efficiency_j_th=eff(2.15, 43.0),
         asic_chip="BM1370 (x2)", process_node="5nm", release_date="2025-10-01",
         is_current_product=True, notes="Dual BM1370 high-output variant. 80mm fan + larger heatsink.",
         source_urls=BITAXE_SOURCES),
    dict(manufacturer="bitaxe", canonical_name="Bitaxe Turbo Touch (2.15 TH)", model_number="Turbo Touch",
         generation="Bitaxe Turbo", cooling_type="air", hashboard_count=1,
         stock_hashrate_th=2.15, stock_power_w=43.0, stock_efficiency_j_th=eff(2.15, 43.0),
         asic_chip="BM1370 (x2)", process_node="5nm", release_date="2025-10-01",
         is_current_product=True, notes="Dual BM1370 with integrated touchscreen UI. Same hashrate as GT 801.",
         source_urls=BITAXE_SOURCES),
    # Legacy — BM1368 chip (from Antminer S21)
    dict(manufacturer="bitaxe", canonical_name="Bitaxe Supra 400 (0.65 TH)", model_number="Supra 400",
         generation="Bitaxe Supra", cooling_type="air", hashboard_count=1,
         stock_hashrate_th=0.65, stock_power_w=12.0, stock_efficiency_j_th=eff(0.65, 12.0),
         asic_chip="BM1368", process_node="5nm", release_date="2024-06-01",
         is_current_product=False, notes="Single BM1368 from S21 hashboards. Superseded by Gamma 602.",
         source_urls=BITAXE_SOURCES),
    # Legacy — BM1366 chip (from Antminer S19 XP)
    dict(manufacturer="bitaxe", canonical_name="Bitaxe Ultra 200 (0.50 TH)", model_number="Ultra 200",
         generation="Bitaxe Ultra", cooling_type="air", hashboard_count=1,
         stock_hashrate_th=0.50, stock_power_w=12.0, stock_efficiency_j_th=eff(0.50, 12.0),
         asic_chip="BM1366", process_node="5nm", release_date="2023-08-01",
         is_current_product=False, notes="Single BM1366 from S19 XP hashboards. First widely-cloned Bitaxe design.",
         source_urls=BITAXE_SOURCES),
    dict(manufacturer="bitaxe", canonical_name="Bitaxe Hex 700 (3.0 TH)", model_number="Hex 700",
         generation="Bitaxe Hex", cooling_type="air", hashboard_count=1,
         stock_hashrate_th=3.0, stock_power_w=70.0, stock_efficiency_j_th=eff(3.0, 70.0),
         asic_chip="BM1366 (x6)", process_node="5nm", release_date="2023-12-01",
         is_current_product=False, notes="Six BM1366 chips on a single PCB — highest-output legacy Bitaxe.",
         source_urls=BITAXE_SOURCES),
]

# ═══════════════════════════════════════════════════════════════════════════════
# OUTPUT: CSV + SQL
# ═══════════════════════════════════════════════════════════════════════════════

CSV_COLUMNS = [
    "manufacturer", "canonical_name", "model_number", "generation", "cooling_type",
    "hashboard_count", "stock_hashrate_th", "stock_power_w", "stock_efficiency_j_th",
    "asic_chip", "process_node", "release_date", "is_current_product", "notes", "source_urls"
]

import json
import os

def write_csv(miners, path):
    import csv
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for m in miners:
            row = {k: m.get(k, "") for k in CSV_COLUMNS}
            writer.writerow(row)
    print(f"CSV written: {path} ({len(miners)} rows)")


def sql_val(v):
    """Convert Python value to SQL literal."""
    if v is None or v == "" or v == "—":
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    # String — escape single quotes
    return "'" + str(v).replace("'", "''") + "'"


def write_sql(miners, path):
    preamble = """-- Mining Intelligence Catalog — Seed Data: Bitcoin SHA-256 ASIC Miner Models
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

"""

    cooling_map = {
        "air": "air",
        "hydro": "hydro",
        "immersion": "immersion",
        "unknown": "unknown",
    }

    lines = [preamble]
    for i, m in enumerate(miners, 1):
        mfr = m["manufacturer"]
        canonical = m["canonical_name"].replace("'", "''")
        model_number = (m.get("model_number") or "").replace("'", "''")
        generation = (m.get("generation") or "").replace("'", "''")
        cooling = cooling_map.get(m.get("cooling_type", "air"), "unknown")
        hashboard_count = m.get("hashboard_count") or 3
        hashrate = m.get("stock_hashrate_th")
        power = m.get("stock_power_w")
        # Recalculate efficiency if we have both
        if hashrate and power and hashrate > 0:
            efficiency = round(power / hashrate, 4)
        else:
            efficiency = m.get("stock_efficiency_j_th")
        asic_chip = (m.get("asic_chip") or "").replace("'", "''")
        process_node = (m.get("process_node") or "").replace("'", "''")
        release_date = m.get("release_date")
        is_current = m.get("is_current_product", False)
        end_of_life = not is_current
        notes = (m.get("notes") or "").replace("'", "''")
        source_urls = m.get("source_urls") or ""
        
        # Build metadata JSONB
        metadata = {}
        if asic_chip and asic_chip not in ("—", ""):
            metadata["asic_chip"] = m.get("asic_chip")
        if process_node and process_node not in ("—", "TBD (Samsung)", ""):
            metadata["process_node"] = m.get("process_node")
        if source_urls:
            metadata["sources"] = [s.strip() for s in source_urls.split(",") if s.strip()]
        metadata_json = json.dumps(metadata).replace("'", "''")
        
        # Confidence: high if we have hashrate + power + release date, medium otherwise
        confidence = "high" if (hashrate and power and release_date) else "medium"
        
        # Format values
        hr_sql = str(hashrate) if hashrate is not None else "NULL"
        pw_sql = str(power) if power is not None else "NULL"
        eff_sql = str(efficiency) if efficiency is not None else "NULL"
        rd_sql = f"'{release_date}'" if release_date else "NULL"
        
        sql = f"""INSERT INTO hardware.miner_models (
    id, manufacturer_id, canonical_name, model_number, generation,
    cooling_type, hashboard_count, stock_hashrate_th, stock_power_w, stock_efficiency_j_th,
    algorithm, released_date, is_current_product, end_of_life, notes, metadata, confidence
) VALUES (
    uuid_generate_v4(),
    (SELECT id FROM hardware.manufacturers WHERE brand = '{mfr}'),
    '{canonical}', '{model_number}', '{generation}',
    '{cooling}'::public.cooling_type, {hashboard_count}, {hr_sql}, {pw_sql}, {eff_sql},
    'SHA-256', {rd_sql}, {'TRUE' if is_current else 'FALSE'}, {'TRUE' if end_of_life else 'FALSE'},
    '{notes}', '{metadata_json}'::jsonb, '{confidence}'
);
"""
        lines.append(sql)

    lines.append("\nCOMMIT;\n")

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"SQL written: {path} ({len(miners)} INSERT statements)")


def print_summary(miners):
    from collections import Counter
    counts = Counter(m["manufacturer"] for m in miners)
    print("\n" + "="*60)
    print("MINING INTELLIGENCE CATALOG — SUMMARY")
    print("="*60)
    total = 0
    for mfr, count in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {mfr:<20} {count:>4} variants")
        total += count
    print("-"*60)
    print(f"  {'TOTAL':<20} {total:>4} variants")
    print("="*60)
    
    # Cooling breakdown
    cooling_counts = Counter(m["cooling_type"] for m in miners)
    print("\nCooling type breakdown:")
    for c, n in sorted(cooling_counts.items()):
        print(f"  {c:<15} {n:>4}")
    
    # Current vs EOL
    current = sum(1 for m in miners if m.get("is_current_product"))
    print(f"\nCurrent products:    {current}")
    print(f"Discontinued/EOL:    {total - current}")


if __name__ == "__main__":
    CSV_PATH = "/home/user/workspace/all_bitcoin_sha256_miners.csv"
    SQL_PATH = "/home/user/workspace/seed_miner_models.sql"
    
    write_csv(ALL_MINERS, CSV_PATH)
    write_sql(ALL_MINERS, SQL_PATH)
    print_summary(ALL_MINERS)
