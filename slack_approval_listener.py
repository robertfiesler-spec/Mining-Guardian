"""
slack_approval_listener.py
Mining Guardian — Slack Approval Listener

Watches #mining-guardian for APPROVE/DENY replies in scan threads.
When detected, calls the Approval API to execute or deny pending actions.

Runs as a standalone service alongside Mining Guardian.
Uses Slack's conversations.history to poll for new thread replies.
"""

import os
import time
import json
import logging
import requests
import sqlite3
from datetime import datetime
from slack_sdk import WebClient

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("slack_approval_listener")

# Load config
from dotenv import load_dotenv
load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
CHANNEL_ID = "C0AQ8SE1448"  # #mining-guardian
APPROVAL_API = "http://localhost:8686"
DB_PATH = "guardian.db"
POLL_INTERVAL = 10  # check every 10 seconds


class ApprovalListener:
    def __init__(self):
        self.client = WebClient(token=SLACK_BOT_TOKEN)
        self.processed_messages = set()  # track messages we've already handled
        self._load_processed()

    def _load_processed(self):
        """Load already-processed message timestamps from DB to avoid re-processing on restart."""
        try:
            conn = sqlite3.connect(DB_PATH)
            rows = conn.execute(
                "SELECT DISTINCT thread_ts FROM pending_approvals WHERE status != 'PENDING'"
            ).fetchall()
            self.processed_messages = {r[0] for r in rows}
            conn.close()
            logger.info("Loaded %d already-processed threads", len(self.processed_messages))
        except Exception:
            pass

    def _get_pending_threads(self):
        """Get thread_ts values that have pending approvals."""
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT DISTINCT thread_ts FROM pending_approvals WHERE status = 'PENDING'"
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]

    def _check_thread_replies(self, thread_ts):
        """Check if someone replied APPROVE or DENY in a thread."""
        try:
            resp = self.client.conversations_replies(
                channel=CHANNEL_ID,
                ts=thread_ts,
                limit=20
            )
            messages = resp.get("messages", [])

            # Skip the first message (that's the scan report itself)
            for msg in messages[1:]:
                msg_ts = msg.get("ts", "")
                msg_key = f"{thread_ts}:{msg_ts}"

                if msg_key in self.processed_messages:
                    continue

                text = msg.get("text", "").strip().upper()
                user_id = msg.get("user", "")

                # Get user's display name
                user_name = "unknown"
                try:
                    user_info = self.client.users_info(user=user_id)
                    profile = user_info.get("user", {}).get("profile", {})
                    user_name = profile.get("display_name") or profile.get("real_name", "unknown")
                except Exception:
                    pass

                if text in ("APPROVE", "APPROVED", "YES", "Y"):
                    self.processed_messages.add(msg_key)
                    return "APPROVE", user_name, user_id
                elif text in ("DENY", "DENIED", "NO", "N"):
                    self.processed_messages.add(msg_key)
                    return "DENY", user_name, user_id

        except Exception as e:
            logger.warning("Error checking thread %s: %s", thread_ts, e)

        return None, None, None

    def _execute_approval(self, thread_ts, action, user_name, user_id):
        """Call the Approval API to approve or deny pending actions."""
        endpoint = f"{APPROVAL_API}/{action.lower()}"
        payload = {
            "thread_ts": thread_ts,
            "user": user_name,
            "user_id": user_id
        }
        try:
            resp = requests.post(endpoint, json=payload, timeout=30)
            result = resp.json()
            count = result.get("count", 0)
            logger.info("%s by %s — %d miners — thread %s",
                        action, user_name, count, thread_ts)

            # Post confirmation in the Slack thread
            if action == "APPROVE":
                confirm_msg = f"✅ *APPROVED* by {user_name} — {count} action(s) being executed."
            else:
                confirm_msg = f"❌ *DENIED* by {user_name} — {count} action(s) cancelled."

            self.client.chat_postMessage(
                channel=CHANNEL_ID,
                thread_ts=thread_ts,
                text=confirm_msg
            )
        except Exception as e:
            logger.error("Approval API call failed: %s", e)

    def run(self):
        """Main loop — poll pending threads for APPROVE/DENY replies."""
        logger.info("Slack Approval Listener started — watching #mining-guardian")
        logger.info("Polling every %ds for APPROVE/DENY replies", POLL_INTERVAL)

        while True:
            try:
                pending_threads = self._get_pending_threads()
                if pending_threads:
                    for thread_ts in pending_threads:
                        action, user_name, user_id = self._check_thread_replies(thread_ts)
                        if action:
                            self._execute_approval(thread_ts, action, user_name, user_id)
            except Exception as e:
                logger.error("Listener loop error: %s", e)

            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    print("=" * 50)
    print("Mining Guardian — Slack Approval Listener")
    print("Watching #mining-guardian for APPROVE/DENY")
    print("=" * 50)
    listener = ApprovalListener()
    listener.run()
