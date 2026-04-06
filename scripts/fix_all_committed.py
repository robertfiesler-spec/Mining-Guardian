#!/usr/bin/env python3
"""
Fix two things in committed code:
1. DENY parsing — handle 'deny.', 'deny,', 'deny!' etc
2. post_to_channel — return message ts (commit this, not just runtime fix)
"""
import re

# Fix 1: Slack listener deny parsing
with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/api/slack_approval_listener.py") as f:
    c = f.read()

old_deny_check = """                if upper in ("DENY", "DENIED", "NO", "N") or upper.startswith("DENY ") or upper.startswith("DENIED "):
                    self.processed.add(msg_key)
                    return "DENY", None, get_user_name(self.client, user_id), user_id"""

new_deny_check = """                # Match DENY in any form: "deny", "deny.", "deny, reason", "denied!", etc
                first_word = upper.split()[0].rstrip(".,!:;") if upper.split() else ""
                if first_word in ("DENY", "DENIED", "NO", "N"):
                    self.processed.add(msg_key)
                    return "DENY", None, get_user_name(self.client, user_id), user_id"""

c = c.replace(old_deny_check, new_deny_check)

with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/api/slack_approval_listener.py", "w") as f:
    f.write(c)
print("Fix 1: DENY parsing now handles punctuation")

# Fix 2: post_to_channel in mining_guardian.py — return ts
with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/core/mining_guardian.py") as f:
    c = f.read()

old_post = '''    def post_to_channel(self, message: str) -> None:
        """Post a plain message to the channel — used for board restart outcome notifications."""
        try:
            if self.bot_token:
                from slack_sdk import WebClient
                WebClient(token=self.bot_token).chat_postMessage(
                    channel=self.channel_id, text=message
                )
            elif self.webhook_url:
                requests.post(self.webhook_url, json={"text": message}, timeout=10)
        except Exception as e:
            logger.warning("post_to_channel failed: %s", e)'''

new_post = '''    def post_to_channel(self, message: str) -> str:
        """Post a plain message to the channel. Returns message ts for threading."""
        try:
            if self.bot_token:
                from slack_sdk import WebClient
                resp = WebClient(token=self.bot_token).chat_postMessage(
                    channel=self.channel_id, text=message
                )
                return resp.get("ts", "")
            elif self.webhook_url:
                requests.post(self.webhook_url, json={"text": message}, timeout=10)
                return ""
        except Exception as e:
            logger.warning("post_to_channel failed: %s", e)
        return ""'''

if old_post in c:
    c = c.replace(old_post, new_post)
    print("Fix 2: post_to_channel now returns ts (committed)")
else:
    print("Fix 2: post_to_channel already fixed or changed")

# Fix 3: Ticket timing — don't ticket miners restarted < 30 min ago
old_ticket = '''            candidates_failures = conn.execute("""
                SELECT miner_id, ip, model,
                       COUNT(*) as failure_count, 'failure_outcomes' as reason
                FROM miner_restarts
                WHERE outcome = 'FAILURE'
                GROUP BY miner_id
                HAVING failure_count >= ?
            """, (FAILURE_THRESHOLD,)).fetchall()'''

new_ticket = '''            # Don't count failures from restarts in the last 30 minutes (miner may still be booting)
            candidates_failures = conn.execute("""
                SELECT miner_id, ip, model,
                       COUNT(*) as failure_count, 'failure_outcomes' as reason
                FROM miner_restarts
                WHERE outcome = 'FAILURE'
                  AND restarted_at < datetime('now', '-30 minutes')
                GROUP BY miner_id
                HAVING failure_count >= ?
            """, (FAILURE_THRESHOLD,)).fetchall()'''

if old_ticket in c:
    c = c.replace(old_ticket, new_ticket)
    print("Fix 3: Ticket 30-min grace period (committed)")
else:
    print("Fix 3: Ticket timing already fixed or changed")

# Fix 4: Action diversity Slack posting — bake into committed code
old_diversity = '''                            # Log to audit trail for tracking
                            try:
                                self.db.log_action(
                                    act["miner_id"], act["ip"],
                                    act["model"],
                                    problem="; ".join(act.get("reasons", [])),
                                    action_taken=act["action"],
                                    decision="PENDING_APPROVAL",
                                    notes=f"confidence={act['confidence']}% data={act.get('data_used',[])}",
                                )
                            except Exception:
                                pass'''

new_diversity = '''                            # Log to audit trail for tracking
                            try:
                                self.db.log_action(
                                    act["miner_id"], act["ip"],
                                    act["model"],
                                    problem="; ".join(act.get("reasons", [])),
                                    action_taken=act["action"],
                                    decision="PENDING_APPROVAL",
                                    notes=f"confidence={act['confidence']}% data={act.get('data_used',[])}",
                                )
                            except Exception:
                                pass
                            # Post to Slack so operator can approve/deny
                            try:
                                reasons_str = ", ".join(act.get("reasons", []))[:100]
                                msg = (
                                    f":crystal_ball: *AI Recommendation — {act['action']}*\\n"
                                    f"Miner: `{act['ip']}` ({act['model']})\\n"
                                    f"Confidence: *{act['confidence']}%*\\n"
                                    f"Reason: {reasons_str}\\n\\n"
                                    f"_Reply `APPROVE` to execute or `DENY` to skip._"
                                )
                                thread = self.slack.post_to_channel(msg)
                                if thread and isinstance(thread, str) and thread:
                                    issue_entry = [{
                                        "id": act["miner_id"],
                                        "ip": act["ip"],
                                        "model": act["model"],
                                        "action": act["action"],
                                        "issues": act.get("reasons", []),
                                    }]
                                    self.db.save_pending_approvals(
                                        thread, latest_scan["id"], issue_entry
                                    )
                            except Exception as ex:
                                logger.debug("Action diversity Slack post failed: %s", ex)'''

if old_diversity in c:
    c = c.replace(old_diversity, new_diversity)
    print("Fix 4: Action diversity Slack posting (committed)")
else:
    print("Fix 4: Action diversity already has Slack posting or changed")

with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/core/mining_guardian.py", "w") as f:
    f.write(c)
print("\nAll fixes applied to committed code")
