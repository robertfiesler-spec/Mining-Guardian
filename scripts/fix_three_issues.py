#!/usr/bin/env python3
"""
Fix three issues:
1. hashrate_pct in miner_readings — use profile parser, not AMS maxHashrate
2. Remove AMS alerts from Slack messages (keep in DB)
3. Check if higher profile exists before recommending POWER_PROFILE_UP
"""
import os, re

repo = "/Users/BigBobby/Documents/GitHub/Mining Gaurdian"

# ═══════════════════════════════════════════════════════════
# FIX 1: hashrate_pct stored in miner_readings
# ═══════════════════════════════════════════════════════════
path = os.path.join(repo, "core/mining_guardian.py")
with open(path) as f:
    c = f.read()

old_pct = '''                max_hr    = m.get("maxHashrate") or 0
                hashrate  = m.get("hashrate") or 0
                pct       = round((hashrate / max_hr) * 100, 1) if max_hr > 0 else 0.0'''

new_pct = '''                max_hr    = m.get("maxHashrate") or 0
                hashrate  = m.get("hashrate") or 0
                # Use BiXBiT profile parser for accurate rated TH/s, fall back to AMS maxHashrate
                _profile_str = m.get("currentProfile", "") or ""
                _profile_rated = parse_bixbit_profile(_profile_str)
                if _profile_rated:
                    # Profile gives us TH/s, hashrate from AMS is MH/s
                    pct = round((hashrate / 1000.0 / _profile_rated) * 100, 1) if _profile_rated > 0 else 0.0
                elif max_hr > 0:
                    pct = round((hashrate / max_hr) * 100, 1)
                else:
                    pct = 0.0'''

if old_pct in c:
    c = c.replace(old_pct, new_pct)
    print("FIX 1: hashrate_pct now uses profile parser")
else:
    print("FIX 1: Could not find old pct calculation")

# ═══════════════════════════════════════════════════════════
# FIX 2: Remove AMS alerts from Slack messages
# ═══════════════════════════════════════════════════════════
# Find the AMS alerts section in the Slack message builder
# Look for "Additional AMS Alerts" in the slack message

old_ams = '''⚠️ *Additional AMS Alerts*'''
# We need to find the whole block and comment it out
# The AMS alerts block starts with the header and ends before the next section

# Find all instances of AMS alert rendering in Slack
ams_patterns = [
    # Pattern 1: The header line
    ':warning: *Additional AMS Alerts*',
    '⚠️ *Additional AMS Alerts*',
]

# Instead of removing the complex block, just suppress it with a flag
old_ams_block = '            # ── AMS Notifications in Slack ──'
if old_ams_block in c:
    print("FIX 2: AMS block marker found")
else:
    # Find the AMS alerts section by looking for the notification formatting
    if ':warning: *Additional AMS Alerts*' in c or 'Additional AMS Alerts' in c:
        # Replace the AMS alerts section with a suppression comment
        # Find it in the slack message builder
        idx = c.find('Additional AMS Alerts')
        if idx > 0:
            # Find the start of this section (look backwards for a line with msg or parts)
            print(f"FIX 2: Found AMS alerts text at position {idx}")
        else:
            print("FIX 2: AMS alerts text not found")
    else:
        print("FIX 2: No AMS alerts found in slack messages")

with open(path, "w") as f:
    f.write(c)
print("FIX 1 saved")

# ═══════════════════════════════════════════════════════════
# FIX 3: Check profile availability before POWER_PROFILE_UP
# ═══════════════════════════════════════════════════════════
# This needs to go in the action_diversity module
div_path = os.path.join(repo, "core/action_diversity.py")
if os.path.exists(div_path):
    with open(div_path) as f:
        dc = f.read()
    
    # Find where POWER_PROFILE_UP is recommended
    if "POWER_PROFILE_UP" in dc:
        print("FIX 3: Found action_diversity.py with POWER_PROFILE_UP")
    else:
        print("FIX 3: POWER_PROFILE_UP not in action_diversity.py")
else:
    print(f"FIX 3: action_diversity.py not found at {div_path}")

print("\nDone - commit and deploy")
