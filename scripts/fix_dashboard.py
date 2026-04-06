#!/usr/bin/env python3
"""Fix column names in ai_dashboard_api.py"""
with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/api/ai_dashboard_api.py") as f:
    c = f.read()

# Fix SQL column names
c = c.replace("pa.action, pa.issue,", "pa.action_type, pa.problem,")

# Fix Python dict access - single quotes
c = c.replace("q.get('action','')", "q.get('action_type','')")
c = c.replace("q.get('issue','')", "q.get('problem','')")

# Fix Python dict access - double quotes
c = c.replace('q.get("action","")', 'q.get("action_type","")')
c = c.replace('q.get("issue","")', 'q.get("problem","")')

with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/api/ai_dashboard_api.py", "w") as f:
    f.write(c)
print("Fixed column names: action->action_type, issue->problem")
