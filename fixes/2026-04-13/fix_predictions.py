#!/usr/bin/env python3
"""Fix the Pre-Failure Predictions panel to use REAL confidence from knowledge.json"""
import re

with open('/root/Mining-Gaurdian/api/ai_dashboard_api.py', 'r') as f:
    content = f.read()

# Fix 1: Replace get_prediction_status() to pull from knowledge.json
old_func = '''def get_prediction_status():
    conn = _db()
    preds = conn.execute("""
        SELECT timestamp, ip, model, action_taken, problem, notes
        FROM action_audit_log
        WHERE action_taken LIKE '%PREEMPTIVE%' OR action_taken LIKE '%POWER_PROFILE%'
        ORDER BY timestamp DESC LIMIT 15
    """).fetchall()
    conn.close()
    return [dict(r) for r in preds]'''

new_func = '''def get_prediction_status():
    """Get pre-failure predictions from knowledge.json with REAL confidence values."""
    try:
        with open(KNOWLEDGE_PATH) as f:
            knowledge = json.load(f)
        preds = knowledge.get("predictions", [])
        # Sort by predicted_at descending, take last 15
        preds = sorted(preds, key=lambda x: x.get("predicted_at", ""), reverse=True)[:15]
        # Transform to expected format
        result = []
        for p in preds:
            result.append({
                "timestamp": p.get("predicted_at", ""),
                "ip": p.get("ip", ""),
                "model": p.get("model", ""),
                "action_taken": p.get("action", ""),
                "confidence": p.get("confidence", 0),  # REAL confidence value!
                "problem": ", ".join(p.get("signals", [])[:2]),
            })
        return result
    except Exception as e:
        return []'''

if old_func in content:
    content = content.replace(old_func, new_func)
    print('Replaced get_prediction_status()')
else:
    print('Function pattern not found')

# Save
with open('/root/Mining-Gaurdian/api/ai_dashboard_api.py', 'w') as f:
    f.write(content)

print('Saved!')
