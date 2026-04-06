#!/usr/bin/env python3
"""
Test the local LLM scan analyzer against real fleet data.
Run on VPS: python3 scripts/test_local_llm.py
"""
import sys
import os
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "ai"))
sys.path.insert(0, str(_ROOT / "core"))
os.chdir(str(_ROOT))

import sqlite3
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from local_llm_analyzer import LocalLLMAnalyzer

# Initialize
analyzer = LocalLLMAnalyzer()

# Check availability
print("=" * 60)
print("Local LLM Analyzer — Integration Test")
print("=" * 60)

if not analyzer.is_available():
    print("ERROR: LLM not reachable at", analyzer.llm_url)
    sys.exit(1)
print(f"✅ LLM available at {analyzer.llm_url}")
print(f"   Model: {analyzer.model}")

# Get latest scan
conn = sqlite3.connect("guardian.db", timeout=30)
conn.row_factory = sqlite3.Row
latest = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
scan_id = latest["id"]
conn.close()
print(f"   Latest scan: #{scan_id}")

# Run scan analysis
print(f"\n--- Running scan analysis (this may take 30-60 seconds) ---")
start = time.time()
analysis = analyzer.analyze_scan(scan_id)
elapsed = time.time() - start

if analysis:
    print(f"\n✅ LLM ANALYSIS (in {elapsed:.1f}s):")
    print("-" * 40)
    print(analysis)
    print("-" * 40)
    print(f"\nLength: {len(analysis)} chars, Time: {elapsed:.1f}s")
else:
    print(f"\n❌ No analysis returned (elapsed: {elapsed:.1f}s)")

# Test denial processing
print(f"\n--- Testing denial reason processing ---")
rule = analyzer.process_denial(
    "192.168.188.60",
    "POWER_PROFILE_UP",
    "miner just power cycled, need to wait 20 minutes"
)
if rule:
    print(f"✅ Denial rule: {rule}")
else:
    print("❌ No rule generated")

print("\n✅ Test complete")
