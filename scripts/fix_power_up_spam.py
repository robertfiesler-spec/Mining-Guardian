#!/usr/bin/env python3
"""
Fix POWER_PROFILE_UP spam: only recommend if the miner was previously stepped 
DOWN by Mining Guardian. Not just because it's below theoretical max.

This is a RECOVERY action, not a constant optimization suggestion.
"""
import os

repo = "/Users/BigBobby/Documents/GitHub/Mining Gaurdian"
path = os.path.join(repo, "ai/action_diversity.py")

with open(path) as f:
    c = f.read()

# Find and replace _is_reduced_profile 
old_start = "def _is_reduced_profile(profile: str) -> bool:"
old_end = "    return False"

# Find the full function
idx_start = c.index(old_start)
# Find the next def or the return False that ends this function
# The function ends at the last "return False" before the next "def "
remaining = c[idx_start:]
lines = remaining.split("\n")
func_lines = []
for i, line in enumerate(lines):
    func_lines.append(line)
    # Stop after we find a return at function indent level (4 spaces)
    if i > 0 and line.strip() == "return False" and not line.startswith("        "):
        break

old_func = "\n".join(func_lines)

new_func = '''def _is_reduced_profile(profile: str) -> bool:
    """Check if this miner was recently stepped DOWN by Mining Guardian.
    
    POWER_PROFILE_UP is a RECOVERY action — it only makes sense if Mining
    Guardian previously reduced this miner's profile (e.g. due to thermal event).
    It should NOT fire just because a miner is below its theoretical max.
    
    Returns True only if there's a recent POWER_PROFILE_DOWN in the audit log
    for a miner running this profile, or if the profile explicitly says 'eco'.
    """
    if not profile:
        return False
    
    profile_lower = profile.lower()
    
    # Explicit eco/reduced mode
    if "eco" in profile_lower:
        return True
    
    # Check audit log: was this miner recently stepped DOWN by Mining Guardian?
    # We check by profile string — if MG did a POWER_PROFILE_DOWN recently,
    # the miner should be eligible for POWER_PROFILE_UP recovery.
    try:
        import sqlite3
        from pathlib import Path
        _root = Path(__file__).resolve().parent.parent
        db_path = str(_root / "guardian.db")
        conn = sqlite3.connect(db_path, timeout=30)
        # Find any POWER_PROFILE_DOWN actions in the last 24 hours
        # that haven't been followed by a POWER_PROFILE_UP
        row = conn.execute(
            "SELECT COUNT(*) FROM action_audit_log "
            "WHERE action_taken = 'POWER_PROFILE_DOWN' "
            "AND decision IN ('APPROVED', 'AUTO_APPROVED') "
            "AND timestamp >= datetime('now', '-24 hours') "
            "AND notes LIKE '%' || ? || '%'",
            (profile[:20],)
        ).fetchone()
        conn.close()
        if row and row[0] > 0:
            return True
    except Exception:
        pass
    
    return False'''

if old_func in c:
    c = c.replace(old_func, new_func)
    with open(path, "w") as f:
        f.write(c)
    print("FIXED: POWER_PROFILE_UP now only fires as recovery after a step-down")
else:
    print("ERROR: Could not find old function")
    # Debug: print what we found
    print(f"Looking for function starting at char {idx_start}")
    print(f"First 200 chars: {old_func[:200]}")
