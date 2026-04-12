"""Add missing 'import os' to ai/outcome_checker.py.

The os.replace() call on line ~251 in update_miner_profile_outcome was firing
NameError on every scan since yesterday, blocking knowledge.json from being
updated with restart outcome history. Pre-existing bug found while verifying
the channel-routing patch.
"""
from pathlib import Path

PATH = Path("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/ai/outcome_checker.py")
src = PATH.read_text()

OLD = '''import sys
import json
import logging
import sqlite3
from datetime import datetime, timedelta'''

NEW = '''import os
import sys
import json
import logging
import sqlite3
from datetime import datetime, timedelta'''

if "import os\n" in src.split("from datetime")[0]:
    print("ALREADY PATCHED — 'import os' is already in the imports block")
elif OLD not in src:
    print("FAILED: imports block not found verbatim")
    raise SystemExit(1)
else:
    new_src = src.replace(OLD, NEW)
    PATH.write_text(new_src)
    print(f"PATCHED {PATH.name}")
    print(f"  {len(src)} -> {len(new_src)} chars (+{len(new_src)-len(src)})")
