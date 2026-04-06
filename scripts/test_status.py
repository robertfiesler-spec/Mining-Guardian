#!/usr/bin/env python3
"""48hr test status report."""
import sqlite3, json

c = sqlite3.connect("guardian.db", timeout=30)

scans = c.execute("SELECT COUNT(*) FROM scans WHERE scanned_at >= '2026-04-06'").fetchone()[0]
last = c.execute("SELECT online, offline, issues FROM scans ORDER BY id DESC LIMIT 1").fetchone()

data = {}
for tbl in ["miner_readings", "chain_readings", "miner_logs", "miner_hardware", "log_metrics"]:
    data[tbl] = c.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]

outcomes = dict(c.execute("SELECT outcome, COUNT(*) FROM miner_restarts WHERE outcome IS NOT NULL GROUP BY outcome").fetchall())
denials = c.execute("SELECT COUNT(*) FROM action_audit_log WHERE notes LIKE '%DENIAL_REASON%'").fetchone()[0]
actions = dict(c.execute("SELECT decision, COUNT(*) FROM action_audit_log WHERE date='2026-04-06' GROUP BY decision").fetchall())
auto = c.execute("SELECT COUNT(*) FROM action_audit_log WHERE decision LIKE '%AUTO%'").fetchone()[0]
pending = c.execute("SELECT COUNT(*) FROM pending_approvals WHERE status='PENDING'").fetchone()[0]
total_approved = c.execute("SELECT COUNT(*) FROM pending_approvals WHERE status='APPROVED'").fetchone()[0]
total_denied = c.execute("SELECT COUNT(*) FROM pending_approvals WHERE status='DENIED'").fetchone()[0]

# Knowledge
know = json.load(open("knowledge.json")) if __import__("os").path.exists("knowledge.json") else {}
issues_count = len(know.get("known_issues", []))
patterns = len(know.get("patterns", []))
profiles = len(know.get("miner_profiles", {}))

print("=" * 50)
print("  48-HOUR TEST STATUS REPORT")
print("=" * 50)
print(f"Fleet: {last[0]} online | {last[1]} offline | {last[2]} issues")
print(f"Scans today: {scans}")
print()
print("DATA INGESTED:")
print(f"  Miner readings:  {data['miner_readings']:,}")
print(f"  Chain readings:  {data['chain_readings']:,}")
print(f"  Miner logs:      {data['miner_logs']:,}")
print(f"  Hardware records: {data['miner_hardware']:,}")
print(f"  Log metrics:     {data['log_metrics']:,}")
total = sum(data.values())
print(f"  TOTAL:           {total:,}")
print()
print("OUTCOMES:")
for k, v in outcomes.items():
    print(f"  {k}: {v}")
print()
print("ACTIONS TODAY:")
for k, v in actions.items():
    print(f"  {k}: {v}")
print(f"  Autonomous: {auto}")
print(f"  Pending now: {pending}")
print(f"  Total approved: {total_approved}")
print(f"  Total denied: {total_denied}")
print()
print("AI LEARNING:")
print(f"  Denial reasons captured: {denials}")
print(f"  Known issues: {issues_count}")
print(f"  Patterns: {patterns}")
print(f"  Miner profiles: {profiles}")
c.close()
