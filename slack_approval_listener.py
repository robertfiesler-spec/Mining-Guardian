"""
slack_approval_listener.py
Mining Guardian — Slack Approval Listener

Two modes:
  1. Block Kit button clicks (approve_selected / deny_all) — from the
     interactive checkbox+button UI posted after each scan.
  2. Text fallback — still accepts plain "APPROVE" / "DENY" replies
     in case Block Kit doesn't render or user prefers text.

Slack requires a public URL to deliver interactive payloads. We receive
them on the approval-api port (8686) at /slack/actions.
"""

import os
import time
import json
import logging
import requests
import sqlite3
import hashlib
import hmac
from datetime import datetime
from slack_sdk import WebClient
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("slack_approval_listener")

load_dotenv()

SLACK_BOT_TOKEN    = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")
CHANNEL_ID         = "C0AQ8SE1448"   # #mining-guardian
APPROVAL_API       = "http://localhost:8686"
DB_PATH            = "guardian.db"
POLL_INTERVAL      = 10  # seconds for text-fallback polling


class ApprovalListener:
    def __init__(self):
        self.client = WebClient(token=SLACK_BOT_TOKEN)
        self.processed_messages = set()
        self._load_processed()

    def _load_processed(self):
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
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT DISTINCT thread_ts FROM pending_approvals WHERE status = 'PENDING'"
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]

    def _get_user_name(self, user_id: str) -> str:
        try:
            info = self.client.users_info(user=user_id)
            profile = info.get("user", {}).get("profile", {})
            return profile.get("display_name") or profile.get("real_name", user_id)
        except Exception:
            return user_id

    # ── Block Kit interaction handler ─────────────────────────────────────────
    # Called by approval_api.py /slack/actions endpoint when Slack sends
    # an interactive payload (button click or checkbox change).

    def handle_block_action(self, payload: dict) -> None:
        """Process a Block Kit button click from Slack."""
        user_id   = payload.get("user", {}).get("id", "")
        user_name = self._get_user_name(user_id)
        actions   = payload.get("actions", [])
        message   = payload.get("message", {})
        thread_ts = message.get("thread_ts") or message.get("ts", "")

        # Extract which checkboxes are currently selected across all checkbox blocks
        # Slack sends the full state of ALL interactive elements in the message
        state_values = payload.get("state", {}).get("values", {})
        selected_ids = []
        for block_state in state_values.values():
            for element_state in block_state.values():
                if element_state.get("type") == "checkboxes":
                    for opt in element_state.get("selected_options", []):
                        selected_ids.append(opt["value"])

        for action in actions:
            action_id = action.get("action_id", "")
            thread_ts = action.get("value", thread_ts)  # value holds the original scan thread_ts

            if action_id == "approve_selected":
                self._handle_approve_selected(thread_ts, selected_ids, user_name, user_id, payload)

            elif action_id == "deny_all":
                self._handle_deny_all(thread_ts, user_name, user_id, payload)

    def _handle_approve_selected(self, thread_ts, selected_ids, user_name, user_id, payload):
        """Call /approve_selected with the checked miner IDs."""
        if not selected_ids:
            # Nothing checked — treat as deny all
            self._handle_deny_all(thread_ts, user_name, user_id, payload)
            return

        resp = requests.post(f"{APPROVAL_API}/approve_selected", json={
            "thread_ts": thread_ts,
            "miner_ids": selected_ids,
            "user":      user_name,
            "user_id":   user_id,
        }, timeout=30)
        result = resp.json()
        approved = result.get("approved_count", 0)
        denied   = result.get("denied_count", 0)

        confirm = f"✅ *{user_name}* approved *{approved}* miner(s)"
        if denied > 0:
            confirm += f", skipped *{denied}*"
        confirm += ". Executing now."

        self.client.chat_postMessage(
            channel=CHANNEL_ID, thread_ts=thread_ts, text=confirm
        )
        # Update the original Block Kit message to remove buttons (prevent double-clicks)
        self._disable_buttons(payload)
        logger.info("approve_selected by %s — %d approved, %d skipped", user_name, approved, denied)

    def _handle_deny_all(self, thread_ts, user_name, user_id, payload):
        """Call /deny for the whole thread."""
        resp = requests.post(f"{APPROVAL_API}/deny", json={
            "thread_ts": thread_ts,
            "user":      user_name,
            "user_id":   user_id,
        }, timeout=15)
        count = resp.json().get("count", 0)
        self.client.chat_postMessage(
            channel=CHANNEL_ID, thread_ts=thread_ts,
            text=f"❌ *{user_name}* denied all {count} action(s). No changes made."
        )
        self._disable_buttons(payload)
        logger.info("deny_all by %s — %d actions denied", user_name, count)

    def _disable_buttons(self, payload: dict) -> None:
        """Replace the interactive Block Kit message with a plain 'responded' message."""
        try:
            channel    = payload.get("channel", {}).get("id", CHANNEL_ID)
            message_ts = payload.get("message", {}).get("ts", "")
            if message_ts:
                self.client.chat_update(
                    channel=channel,
                    ts=message_ts,
                    text="✅ Response recorded — buttons disabled.",
                    blocks=[]   # strip all blocks, leave just the text
                )
        except Exception as e:
            logger.warning("Could not disable buttons: %s", e)

    # ── Text fallback polling ─────────────────────────────────────────────────
    # Still poll for plain "APPROVE" / "DENY" text replies as a fallback.

    def _check_thread_replies(self, thread_ts):
        try:
            resp = self.client.conversations_replies(
                channel=CHANNEL_ID, ts=thread_ts, limit=20
            )
            for msg in resp.get("messages", [])[1:]:
                msg_ts  = msg.get("ts", "")
                msg_key = f"{thread_ts}:{msg_ts}"
                if msg_key in self.processed_messages:
                    continue
                text    = msg.get("text", "").strip().upper()
                user_id = msg.get("user", "")
                user_name = self._get_user_name(user_id)
                if text in ("APPROVE", "APPROVED", "YES", "Y"):
                    self.processed_messages.add(msg_key)
                    return "APPROVE", user_name, user_id
                elif text in ("DENY", "DENIED", "NO", "N"):
                    self.processed_messages.add(msg_key)
                    return "DENY", user_name, user_id
        except Exception as e:
            logger.warning("Error checking thread %s: %s", thread_ts, e)
        return None, None, None

    def _execute_text_approval(self, thread_ts, action, user_name, user_id):
        endpoint = f"{APPROVAL_API}/{action.lower()}"
        try:
            resp   = requests.post(endpoint, json={
                "thread_ts": thread_ts, "user": user_name, "user_id": user_id
            }, timeout=30)
            result = resp.json()
            count  = result.get("count", 0)
            if action == "APPROVE":
                confirm = f"✅ *APPROVED* by {user_name} — {count} action(s) being executed."
            else:
                confirm = f"❌ *DENIED* by {user_name} — {count} action(s) cancelled."
            self.client.chat_postMessage(
                channel=CHANNEL_ID, thread_ts=thread_ts, text=confirm
            )
        except Exception as e:
            logger.error("Approval API call failed: %s", e)

    def run(self):
        logger.info("Slack Approval Listener started — polling + Block Kit ready")
        while True:
            try:
                for thread_ts in self._get_pending_threads():
                    action, user_name, user_id = self._check_thread_replies(thread_ts)
                    if action:
                        self._execute_text_approval(thread_ts, action, user_name, user_id)
            except Exception as e:
                logger.error("Listener loop error: %s", e)
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    print("=" * 55)
    print("  Mining Guardian — Slack Approval Listener")
    print("  Block Kit buttons + text APPROVE/DENY fallback")
    print("=" * 55)
    listener = ApprovalListener()
    listener.run()
