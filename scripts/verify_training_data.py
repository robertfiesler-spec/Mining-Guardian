#!/usr/bin/env python3
"""Verify denial reasons will be in training data — simple DB query test."""
import sqlite3

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
        print(f"  [{r['timestamp'][:16]}] {r['ip']} {r['action_taken']}")
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
    print(f"  {d['ip']} {d['outcome']} before={d['hashrate_before']} after={d['hashrate_after']} at {d['restarted_at'][:16]}")

c.close()
