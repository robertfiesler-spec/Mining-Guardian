#!/usr/bin/env python3
"""Verify denial reasons will be in training data — simple DB query test.

Legacy debug script (originally SQLite-era). Kept around for reference;
the scheduled-job path uses `ai/train_comprehensive.py` directly.
"""
import sqlite3
import sys
from pathlib import Path

# P-038 item #5 (2026-05-11): the `[:16]` slices below were caught by
# the cohort-guard regression test as siblings of the
# `train_comprehensive.py` outlier-prompt crash. They only run if
# someone manually drives this debug script against a current Postgres
# (or a backfilled SQLite that returned datetime objects), but the bug
# shape is identical and easy to silence here. See core/dt_format.py.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from core.dt_format import fmt_dt

c = sqlite3.connect("guardian.db", timeout=30)
c.row_factory = sqlite3.Row

# Exact query from train_comprehensive.py lines 621-630
denial_reasons = c.execute("""
    SELECT timestamp, ip, model, action_taken, notes
    FROM action_audit_log
    WHERE decision = 'DENIED'
      AND notes LIKE '%DENIAL_REASON%'
      AND timestamp >= datetime('now', '-30 days')
    ORDER BY timestamp DESC
    LIMIT 20
""").fetchall()

print(f"Denial reasons found: {len(denial_reasons)}")
if denial_reasons:
    print("\nThese will be sent to Claude during training:")
    for r in denial_reasons:
        import re
        match = re.search(r"DENIAL_REASON: (.+?)(?:\||$)", r["notes"])
        reason = match.group(1).strip() if match else "parse failed"
        print(f"  [{fmt_dt(r['timestamp'])}] {r['ip']} {r['action_taken']}")
        print(f"    Operator said: \"{reason[:80]}\"")
        print()
else:
    print("NO DENIAL REASONS FOUND — training will not include operator feedback")

# Also check outcomes
outcomes = c.execute("""
    SELECT outcome, COUNT(*) as cnt 
    FROM miner_restarts 
    WHERE outcome IS NOT NULL 
    GROUP BY outcome
""").fetchall()
print("Restart outcomes that will feed training:")
for o in outcomes:
    print(f"  {o['outcome']}: {o['cnt']}")

# Check restart outcomes per miner (what build_miner_prompt reads)
detailed = c.execute("""
    SELECT mr.miner_id, mr.ip, mr.outcome, mr.hashrate_before, mr.hashrate_after,
           mr.restarted_at
    FROM miner_restarts mr
    WHERE mr.outcome IS NOT NULL
    ORDER BY mr.restarted_at DESC
    LIMIT 10
""").fetchall()
print(f"\nLatest 10 restart outcomes (per-miner training data):")
for d in detailed:
    print(f"  {d['ip']} {d['outcome']} before={d['hashrate_before']} after={d['hashrate_after']} at {fmt_dt(d['restarted_at'])}")

c.close()
