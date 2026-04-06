#!/usr/bin/env python3
"""Fix: DENY with inline reason — 'DENY reason here' should work, not just bare 'DENY'."""

with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/api/slack_approval_listener.py") as f:
    c = f.read()

# Replace the deny check to also handle inline reasons
old = '''                if upper in ("DENY", "DENIED", "NO", "N"):
                    self.processed.add(msg_key)
                    return "DENY", None, get_user_name(self.client, user_id), user_id'''

new = '''                if upper in ("DENY", "DENIED", "NO", "N"):
                    self.processed.add(msg_key)
                    return "DENY", None, get_user_name(self.client, user_id), user_id

                # DENY with inline reason: "DENY we just restarted, need to wait 15 min"
                if upper.startswith("DENY ") or upper.startswith("DENIED "):
                    self.processed.add(msg_key)
                    # Extract everything after DENY/DENIED as the reason
                    reason = text.split(" ", 1)[1].strip() if " " in text else None
                    return "DENY", reason, get_user_name(self.client, user_id), user_id'''

if old in c:
    c = c.replace(old, new)
    with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/api/slack_approval_listener.py", "w") as f:
        f.write(c)
    print("FIXED: DENY with inline reason now works")
else:
    print("ERROR: Could not find deny block")
