#!/usr/bin/env python3
"""Debug hashrate calculation for a specific miner."""
import sqlite3, sys
sys.path.insert(0, "core")
from hashrate_evaluation import parse_bixbit_profile, HashrateTierResolver, MinerSpecsLoader, BaselineManager

c = sqlite3.connect("guardian.db", timeout=30)
c.row_factory = sqlite3.Row

scan = c.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()

# Check a miner showing >100%
row = c.execute(
    "SELECT miner_id, ip, model, hashrate, hashrate_pct, current_profile, "
    "firmware_manufacturer, max_hashrate "
    "FROM miner_readings WHERE scan_id=? AND ip='192.168.188.36'", 
    (scan["id"],)
).fetchone()

if row:
    print(f"IP: {row['ip']}")
    print(f"Model: {row['model']}")
    print(f"Firmware: {row['firmware_manufacturer']}")
    print(f"Profile: {row['current_profile']}")
    print(f"Hashrate (MH/s from AMS): {row['hashrate']}")
    print(f"Max hashrate (from AMS): {row['max_hashrate']}")
    print(f"Stored hashrate_pct: {row['hashrate_pct']}")
    
    # What parse_bixbit_profile returns
    rated = parse_bixbit_profile(row['current_profile'])
    print(f"\nparse_bixbit_profile result: {rated} TH/s")
    
    # What the hashrate should be
    hashrate_ths = row['hashrate'] / 1000.0
    print(f"Actual hashrate TH/s: {hashrate_ths}")
    
    if rated:
        correct_pct = (hashrate_ths / rated) * 100
        print(f"Correct pct: {hashrate_ths} / {rated} * 100 = {correct_pct:.1f}%")
    
    # What AMS max_hashrate suggests
    if row['max_hashrate']:
        ams_pct = (row['hashrate'] / row['max_hashrate']) * 100
        print(f"AMS max-based pct: {row['hashrate']} / {row['max_hashrate']} * 100 = {ams_pct:.1f}%")

c.close()
