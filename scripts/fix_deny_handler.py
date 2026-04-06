#!/usr/bin/env python3
"""Fix: Pass inline denial reason to API and skip the follow-up question if reason already provided."""

with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/api/slack_approval_listener.py") as f:
    c = f.read()

# Fix the deny handler to pass reason and skip follow-up if already provided
old_deny = '''            else:  # DENY
                resp  = requests.post(f"{APPROVAL_API}/deny", json={
                    "thread_ts": thread_ts, "user": user_name, "user_id": user_id
                }, timeout=15)
                count = resp.json().get("count", 0)
                msg   = f"❌ *DENIED* by {user_name} — {count} action(s) cancelled."
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

new_deny = '''            else:  # DENY
                deny_payload = {
                    "thread_ts": thread_ts, "user": user_name, "user_id": user_id
                }
                if selector:  # inline reason from "DENY reason here"
                    deny_payload["reason"] = selector
                resp  = requests.post(f"{APPROVAL_API}/deny", json=deny_payload, timeout=15)
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
                ).start()
            elif action == "DENY" and selector:
                # Inline reason already provided — store it directly
                try:
                    conn = get_db()
                    conn.execute(
                        "UPDATE action_audit_log SET notes = COALESCE(notes,'') || ' | DENIAL_REASON: ' || ? "
                        "WHERE timestamp >= datetime('now','-5 minutes') "
                        "AND decision='DENIED' AND notes NOT LIKE '%DENIAL_REASON%'",
                        (selector,)
                    )
                    conn.commit()
                    conn.close()
                    logger.info("Denial reason stored: %s", selector[:80])
                except Exception as e:
                    logger.warning("Failed to store denial reason: %s", e)'''

if old_deny in c:
    c = c.replace(old_deny, new_deny)
    with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/api/slack_approval_listener.py", "w") as f:
        f.write(c)
    print("FIXED: Inline deny reason now stored + skips follow-up question")
else:
    print("ERROR: Could not find deny block to replace")
