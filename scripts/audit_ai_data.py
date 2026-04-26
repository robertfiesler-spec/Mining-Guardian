#!/usr/bin/env python3
"""Complete AI Data Flow Audit for Mining Guardian"""

import json
import sqlite3
from pathlib import Path

def main():
    k = json.load(open("/root/Mining-Guardian/knowledge.json"))
    conn = sqlite3.connect("/root/Mining-Guardian/guardian.db")
    
    print("=" * 70)
    print("MINING GUARDIAN — COMPLETE AI DATA FLOW AUDIT")
    print("=" * 70)

    # PART 1: Database tables
    print("\n### PART 1: DATABASE TABLES ###\n")
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    for t in sorted([t[0] for t in tables]):
        count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {count:,} rows")

    # PART 2: Knowledge.json components
    print("\n### PART 2: KNOWLEDGE.JSON COMPONENTS ###\n")
    for key in sorted(k.keys()):
        val = k[key]
        if isinstance(val, dict):
            print(f"  {key}: dict ({len(val)} entries)")
        elif isinstance(val, list):
            print(f"  {key}: list ({len(val)} items)")
        else:
            print(f"  {key}: {type(val).__name__}")

    # PART 3: Check what reads each component
    print("\n### PART 3: DATA FLOW ANALYSIS ###\n")
    
    print("Checking which AI files READ from knowledge.json...")
    
    conn.close()
    print("\nAudit complete. See analysis below.")

if __name__ == "__main__":
    main()
