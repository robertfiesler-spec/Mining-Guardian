#!/usr/bin/env python3
"""Deep status check — denial reasons, patterns, training integration."""
import sqlite3, json, os

c = sqlite3.connect("guardian.db", timeout=30)

# Denial reasons captured
print("DENIAL REASONS CAPTURED:")
reasons = c.execute(
    "SELECT notes FROM action_audit_log WHERE notes LIKE '%DENIAL_REASON%' ORDER BY id DESC"
).fetchall()
for r in reasons:
    if "DENIAL_REASON:" in r[0]:
        text = r[0].split("DENIAL_REASON:")[1].strip()[:100]
        print("  -", text)
    
print("\nTotal denial reasons:", len(reasons))

# Knowledge patterns
print("\nKNOWLEDGE PATTERNS:")
k = json.load(open("knowledge.json"))
for p in k.get("patterns", []):
    if isinstance(p, dict):
        print("  -", str(p.get("pattern", p))[:100])
    else:
        print("  -", str(p)[:100])

# Cross-miner analysis
xm = k.get("cross_miner_analysis")
print("\nCross-miner analysis present:", bool(xm))

# Fingerprints
fps = k.get("miner_profiles", {})
print("Miner fingerprints:", len(fps))

# Is denial data feeding into weekly training?
print("\nWEEKLY TRAINING — DENIAL REASON INTEGRATION:")
for tp in ["ai/weekly_train.py", "ai/train_comprehensive.py"]:
    if os.path.exists(tp):
        with open(tp) as f:
            tc = f.read()
        has_denial = "DENIAL_REASON" in tc or "denial_reason" in tc
        has_outcome = "outcome" in tc.lower() and "miner_restarts" in tc
        has_fingerprint = "fingerprint" in tc.lower() or "miner_profiles" in tc
        print(f"  {tp}:")
        print(f"    Reads denial reasons: {'YES' if has_denial else 'NO'}")
        print(f"    Reads outcomes: {'YES' if has_outcome else 'NO'}")
        print(f"    Reads fingerprints: {'YES' if has_fingerprint else 'NO'}")

# Are denial reasons in knowledge.json yet?
print("\nDENIAL REASONS IN KNOWLEDGE:")
denial_in_k = False
for issue in k.get("known_issues", []):
    s = str(issue).lower()
    if "denial" in s or "operator" in s or "reason" in s:
        denial_in_k = True
        print("  Found:", str(issue)[:100])
if not denial_in_k:
    print("  NOT YET — will appear after next weekly training (Sunday 3am)")

c.close()
