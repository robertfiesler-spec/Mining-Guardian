#!/usr/bin/env python3
"""
Fix hashrate % inflation: when BiXBiT miner has empty currentProfile,
check previous scans for the last known profile instead of falling to stock spec.
"""
import os

repo = "/Users/BigBobby/Documents/GitHub/Mining Gaurdian"
path = os.path.join(repo, "core/hashrate_evaluation.py")

with open(path) as f:
    c = f.read()

# In the resolve() method, after Tier 1b (empty firmware but parseable profile),
# add a DB lookup for the last known profile before falling to Tier 2.
# Find the Tier 1c Auradine block and insert before it.

old = '''        # ── TIER 1c: Auradine mode-based ─────────────────────────────────
        if firmware.upper() == "AURADINE":'''

new = '''        # ── TIER 1d: BiXBiT firmware but empty profile — check last known ──
        # AMS sometimes returns empty currentProfile for miners that ARE on
        # BiXBiT firmware. Check the DB for the last non-empty profile.
        if firmware.upper() == "BIXBIT" and not profile:
            try:
                import sqlite3
                from pathlib import Path
                _db = str(Path(__file__).resolve().parent.parent / "guardian.db")
                conn = sqlite3.connect(_db, timeout=30)
                row = conn.execute(
                    "SELECT current_profile FROM miner_readings "
                    "WHERE miner_id=? AND current_profile IS NOT NULL AND current_profile != '' "
                    "ORDER BY id DESC LIMIT 1",
                    (miner_id,)
                ).fetchone()
                conn.close()
                if row and row[0]:
                    rated = parse_bixbit_profile(row[0])
                    if rated:
                        return (
                            rated,
                            "1_bixbit_profile_cached",
                            f"BiXBiT firmware — last known profile '{row[0]}' → {rated} TH/s"
                        )
            except Exception:
                pass

        # ── TIER 1c: Auradine mode-based ─────────────────────────────────
        if firmware.upper() == "AURADINE":'''

if old in c:
    c = c.replace(old, new)
    with open(path, "w") as f:
        f.write(c)
    print("FIXED: BiXBiT empty profile now falls back to last known profile from DB")
else:
    if "1_bixbit_profile_cached" in c:
        print("Already applied")
    else:
        print("ERROR: Could not find Tier 1c block")
