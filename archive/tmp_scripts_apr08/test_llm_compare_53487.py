"""Test the LLM pre/post comparison against the existing 53487 captures.

This runs in the test process (not the daemon) but uses the exact same code
path the daemon's background polling thread will use after every restart.
If this works, the wiring is proven.
"""
import os, sys
os.chdir('/root/Mining-Gaurdian')
sys.path.insert(0, '/root/Mining-Gaurdian/core')
sys.path.insert(0, '/root/Mining-Gaurdian/ai')

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

from mining_guardian import GuardianConfig, MiningGuardian

cfg = GuardianConfig.from_file('/root/Mining-Gaurdian/config.json')
cfg.dry_run = False  # not actually doing anything that touches miners

mg = MiningGuardian(cfg)

print("=" * 70)
print("Testing _run_post_action_log_comparison against existing 53487 logs")
print("=" * 70)

# Call the helper directly with the data already in the DB
mg._run_post_action_log_comparison(
    miner_id="53487",
    ip="192.168.188.57",
    model="Antminer S19JPro",
    action_label="restart",
)

print()
print("=" * 70)
print("DONE — check journal/log for results")
print("=" * 70)
