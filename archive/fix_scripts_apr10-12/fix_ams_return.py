#!/usr/bin/env python3
"""Add location fields to fingerprint return dict"""

with open("/root/Mining-Gaurdian/ai/fingerprint_builder.py", "r") as f:
    content = f.read()

old_return = '''        "total_scans":            total_scans,
        "total_scans_flagged":    flagged_cnt,
        "known_issues":           known_issues,
        "confidence_modifier":    modifier,
        "last_updated":           datetime.now().isoformat()
    }'''

new_return = '''        "total_scans":            total_scans,
        "total_scans_flagged":    flagged_cnt,
        "known_issues":           known_issues,
        "confidence_modifier":    modifier,
        # Location data from miner_ams_extended
        "map_location_id":        map_location_id,
        "map_position":           map_position,
        "stratum_url":            stratum_url,
        "last_updated":           datetime.now().isoformat()
    }'''

if old_return in content:
    content = content.replace(old_return, new_return)
    with open("/root/Mining-Gaurdian/ai/fingerprint_builder.py", "w") as f:
        f.write(content)
    print("SUCCESS: Added location fields to fingerprint return dict")
else:
    print("ERROR: Could not find return dict")
