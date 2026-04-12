#!/usr/bin/env python3
"""Route AMS-down notifications to the alerts channel.

For the initial deployment of #mining-guardian-alerts, we want to avoid
disrupting the proven scan-summary + approval-card flow which lives in
#mining-guardian. Instead, route the simpler read-only notifications to the
alerts channel:

  - send_ams_down: posts to alerts channel (it's a status alert, not an
    operator interaction)

The full scan summary stays in the main channel because it includes the
approval card and operators need to act on it from there.

Future migrations (after the demo):
  - Periodic AI insights → alerts channel
  - Fleet health hourly snapshot → alerts channel
  - Predictive warnings → alerts channel
"""

PATH = '/Users/BigBobby/Documents/GitHub/Mining Gaurdian/core/mining_guardian.py'

with open(PATH) as f:
    src = f.read()

# Find the send_ams_down method's chat_postMessage call and route it to alerts
old_amsdown = '''        try:
            if self.bot_token:
                from slack_sdk import WebClient
                client = WebClient(token=self.bot_token)
                client.chat_postMessage(channel=self.channel_id, text=payload["text"])
            else:
                requests.post(self.webhook_url, json=payload, timeout=10)
            logger.info("AMS-down notification sent to Slack")
        except Exception as e:
            logger.warning("Slack AMS-down notification failed: %s", e)'''

new_amsdown = '''        try:
            if self.bot_token:
                from slack_sdk import WebClient
                client = WebClient(token=self.bot_token)
                # AMS-down notifications go to the #mining-guardian-alerts feed
                # channel, NOT the main channel. They are read-only status alerts
                # that don't require operator interaction (no approval, no
                # button click, no thread reply needed).
                client.chat_postMessage(channel=self.alerts_channel_id, text=payload["text"])
            else:
                requests.post(self.webhook_url, json=payload, timeout=10)
            logger.info("AMS-down notification sent to #mining-guardian-alerts")
        except Exception as e:
            logger.warning("Slack AMS-down notification failed: %s", e)'''

if old_amsdown not in src:
    print("ERROR: send_ams_down POST block not found exactly")
    exit(1)

src = src.replace(old_amsdown, new_amsdown)
with open(PATH, 'w') as f:
    f.write(src)

print("PATCHED: AMS-down notifications now route to #mining-guardian-alerts")
