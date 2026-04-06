#!/usr/bin/env python3
"""Quick data inventory — shows all table row counts and key metrics."""
import sqlite3, json
c = sqlite3.connect("guardian.db", timeout=30)
c.row_factory = sqlite3.Row

print("=== RAW DATA COUNTS ===")
tables = ["scans","miner_readings","chain_readings","pool_readings","miner_state_readings",
          "miner_ams_extended","miner_hardware","miner_logs","log_metrics","ams_notifications",
          "hvac_readings","weather_readings","action_audit_log","miner_restarts",
          "known_dead_boards","llm_analysis","pending_approvals"]
for t in tables:
    try:
        cnt = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {cnt:,}")
    except:
        print(f"  {t}: N/A")

print("\n=== AI FEATURE METRICS ===")
# Outcomes
outcomes = c.execute("SELECT outcome, COUNT(*) FROM miner_restarts WHERE outcome IS NOT NULL GROUP BY outcome").fetchall()
for r in outcomes: print(f"  Outcome {r[0]}: {r[1]}")

# Actions by type
actions = c.execute("SELECT decision, COUNT(*) FROM action_audit_log GROUP BY decision").fetchall()
for r in actions: print(f"  Decision {r[0]}: {r[1]}")

# Fingerprints
try:
    d = json.load(open("knowledge.json"))
    fps = d.get("miner_profiles", {})
    rich = sum(1 for p in fps.values() if p.get("issue_history"))
    print(f"  Fingerprints total: {len(fps)}, with history: {rich}")
    print(f"  Cross-miner analysis: {'YES' if d.get('cross_miner_analysis') else 'NO'}")
    print(f"  Patterns: {len(d.get('patterns',[]))}")
    print(f"  Known issues: {len(d.get('known_issues',[]))}")
except: pass

# Predictions
try:
    preds = c.execute("SELECT COUNT(*) FROM action_audit_log WHERE action_taken LIKE '%PREEMPTIVE%'").fetchone()[0]
    print(f"  Predictions fired: {preds}")
except: pass

# Denial reasons
dr = c.execute("SELECT COUNT(*) FROM action_audit_log WHERE notes LIKE '%DENIAL_REASON%'").fetchone()[0]
print(f"  Denial reasons captured: {dr}")

# Auto actions  
auto = c.execute("SELECT COUNT(*) FROM action_audit_log WHERE decision='AUTO_OVERNIGHT'").fetchone()[0]
print(f"  Autonomous actions: {auto}")

# Tickets
tickets = c.execute("SELECT COUNT(*) FROM known_dead_boards WHERE ticket_created IS NOT NULL").fetchone()[0]
print(f"  Tickets auto-created: {tickets}")

# Total data points
total = sum(c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables if t != "pending_approvals")
print(f"\n  TOTAL DATA POINTS: {total:,}")

c.close()
