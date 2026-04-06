#!/usr/bin/env python3
"""Add denial reason + outcome questions to Claude's cross-miner analysis prompt."""
import os

path = "/Users/BigBobby/Documents/GitHub/Mining Gaurdian/ai/train_comprehensive.py"
with open(path) as f:
    c = f.read()

old = '''        "5. What procurement or operational decisions does this data suggest?\\n"
        "Keep response to 15 lines max."'''

new = '''        "5. What procurement or operational decisions does this data suggest?\\n"
        "6. Based on the operator denial reasons above, what rules should the system learn? When should it NOT recommend actions?\\n"
        "7. Which restarts actually improved hashrate vs which were wasted effort? Should any miners stop getting restarted?\\n"
        "Keep response to 20 lines max."'''

if old in c:
    c = c.replace(old, new)
    with open(path, "w") as f:
        f.write(c)
    print("FIXED: Added Q6 (denial rules) + Q7 (restart effectiveness) to Claude analysis prompt")
else:
    print("ERROR: Could not find target text")
