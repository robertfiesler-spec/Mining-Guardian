#!/usr/bin/env python3
"""Add miner_ams_extended data (location, stratum) to fingerprint_builder"""

with open("/root/Mining-Gaurdian/ai/fingerprint_builder.py", "r") as f:
    content = f.read()

# Find where to insert — after chain events, before conn.close()
old_block = '''    if chain_detaches > 100:              known_issues.append(f"board_cycling:{chain_detaches}_detaches")

    conn.close()'''

new_block = '''    if chain_detaches > 100:              known_issues.append(f"board_cycling:{chain_detaches}_detaches")

    # ── 9b. AMS extended data (location, pool) ───────────────────────────────
    ams_ext = conn.execute("""
        SELECT map_location_id, map_x, map_y, stratum_url
        FROM miner_ams_extended WHERE miner_id=? ORDER BY id DESC LIMIT 1
    """, (miner_id,)).fetchone()
    map_location_id = int(ams_ext["map_location_id"]) if ams_ext and ams_ext["map_location_id"] else None
    map_position = f"{ams_ext['map_x']},{ams_ext['map_y']}" if ams_ext and ams_ext["map_x"] else None
    stratum_url = ams_ext["stratum_url"] if ams_ext else None

    conn.close()'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open("/root/Mining-Gaurdian/ai/fingerprint_builder.py", "w") as f:
        f.write(content)
    print("SUCCESS: Added AMS extended data query to fingerprint_builder")
else:
    print("ERROR: Could not find insertion point")
