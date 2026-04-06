#!/usr/bin/env python3
"""
Simplify deny flow: 
- APPROVE or DENY only (no inline reasons)
- If DENY, always immediately ask "Why?" as a follow-up
- Wait for response, store it
- Clean and separate — never forgotten
"""

with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/api/slack_approval_listener.py") as f:
    c = f.read()

# 1. Remove the inline DENY reason parsing — just APPROVE or DENY
old_inline = '''                if upper in ("DENY", "DENIED", "NO", "N"):
                    self.processed.add(msg_key)
                    return "DENY", None, get_user_name(self.client, user_id), user_id

                # DENY with inline reason: "DENY we just restarted, need to wait 15 min"
                if upper.startswith("DENY ") or upper.startswith("DENIED "):
                    self.processed.add(msg_key)
                    # Extract everything after DENY/DENIED as the reason
                    reason = text.split(" ", 1)[1].strip() if " " in text else None
                    return "DENY", reason, get_user_name(self.client, user_id), user_id'''

new_inline = '''                if upper in ("DENY", "DENIED", "NO", "N") or upper.startswith("DENY ") or upper.startswith("DENIED "):
                    self.processed.add(msg_key)
                    return "DENY", None, get_user_name(self.client, user_id), user_id'''

c = c.replace(old_inline, new_inline)

# 2. Simplify the deny execution — always ask why, never skip
old_deny_exec = '''            else:  # DENY
                deny_payload = {
                    "thread_ts": thread_ts, "user": user_name, "user_id": user_id
                }
                if selector:  # inline reason from 'DENY reason here'
                    deny_payload["reason"] = selector
                resp = requests.post(f"{APPROVAL_API}/deny", json=deny_payload, timeout=15)
                count = resp.json().get("count", 0)
                if selector:
                    msg = f"❌ *DENIED* by {user_name} — {count} action(s) cancelled.\\n💬 Reason: _{selector}_"
                else:
                    msg = f"❌ *DENIED* by {user_name} — {count} action(s) cancelled."
            self.client.chat_postMessage(
                channel=CHANNEL_ID, thread_ts=thread_ts, text=msg
            )
            logger.info("%s by %s — thread %s", action, user_name, thread_ts)

            # Feature 3: Denial Reason Capture
            # After a DENY, ask for a reason — but only if no inline reason was given
            if action == "DENY" and not selector:
                threading.Thread(
                    target=self._capture_denial_reason,
                    args=(thread_ts, user_id, user_name),
                    daemon=True
                ).start()'''

# Check if the old text exists exactly
if old_deny_exec not in c:
    # Try the original version without the inline reason changes
    old_deny_exec = '''            else:  # DENY
                deny_payload = {
                    "thread_ts": thread_ts, "user": user_name, "user_id": user_id
                }
                if selector:  # inline reason from 'DENY reason here'
                    deny_payload["reason"] = selector
                resp = requests.post(f"{APPROVAL_API}/deny", json=deny_payload, timeout=15)
                count = resp.json().get("count", 0)
                if selector:
                    msg = f"❌ *DENIED* by {user_name} — {count} action(s) cancelled.\\n💬 Reason: _{selector}_"
                else:
                    msg = f"❌ *DENIED* by {user_name} — {count} action(s) cancelled."
            self.client.chat_postMessage(
                channel=CHANNEL_ID, thread_ts=thread_ts, text=msg
            )
            logger.info("%s by %s — thread %s", action, user_name, thread_ts)

            # Feature 3: Denial Reason Capture
            # After a DENY, ask for a reason — this is gold for AI training
            if action == "DENY":
                threading.Thread(
                    target=self._capture_denial_reason,
                    args=(thread_ts, user_id, user_name),
                    daemon=True
                ).start()'''

new_deny_exec = '''            else:  # DENY
                resp = requests.post(f"{APPROVAL_API}/deny", json={
                    "thread_ts": thread_ts, "user": user_name, "user_id": user_id
                }, timeout=15)
                count = resp.json().get("count", 0)
                msg = f"❌ *DENIED* by {user_name} — {count} action(s) cancelled."
            self.client.chat_postMessage(
                channel=CHANNEL_ID, thread_ts=thread_ts, text=msg
            )
            logger.info("%s by %s — thread %s", action, user_name, thread_ts)

            # Feature 3: Denial Reason Capture
            # ALWAYS ask why after a deny — clean, separate, never forgotten
            if action == "DENY":
                threading.Thread(
                    target=self._capture_denial_reason,
                    args=(thread_ts, user_id, user_name),
                    daemon=True
                ).start()'''

if old_deny_exec in c:
    c = c.replace(old_deny_exec, new_deny_exec)
    print("FIXED: Deny execution simplified — always asks why")
else:
    print("WARNING: Could not find deny execution block — checking alternative...")
    # Last resort: find it by the key marker
    if "deny_payload" in c:
        print("Found deny_payload — needs manual fix")
    else:
        print("deny_payload not found either")

with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/api/slack_approval_listener.py", "w") as f:
    f.write(c)

print("File saved")
