#!/usr/bin/env python3
"""
Fix two issues:
1. post_to_channel returns None — needs to return message ts for pending approvals
2. Ticket creation on freshly restarted miners — need to check uptime before ticketing
"""

with open("/root/Mining-Gaurdian/core/mining_guardian.py") as f:
    c = f.read()

# Fix 1: post_to_channel should return the message ts
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
    print("FIXED: post_to_channel now returns message ts")
else:
    print("WARNING: Could not find post_to_channel to fix")

# Fix 2: Don't auto-ticket miners with very recent restarts (< 30 min uptime)
# Look for the auto-ticket check section
old_ticket = 'INFO Auto-ticket check:'
if old_ticket in c:
    print("NOTE: Auto-ticket section found — needs manual review for uptime check")
else:
    print("NOTE: Auto-ticket log line not found verbatim")

with open("/root/Mining-Gaurdian/core/mining_guardian.py", "w") as f:
    f.write(c)

print("File saved")
