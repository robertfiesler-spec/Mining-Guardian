#!/usr/bin/env python3
"""
slack_listener.py
Mining Guardian — Slack Approval Listener

Listens for APPROVE / DENY replies in #mining-guardian threads.
When an operator replies, this script:
  1. Identifies which miners/actions are pending
  2. Looks up the operator's Slack display name
  3. Executes the action via AMS (if APPROVED)
  4. Writes to the permanent action audit log
  5. Replies in the thread confirming what was done
  6. Adds ✅ or ❌ reaction to the original message

Usage:
    source venv/bin/activate
    export $(grep -v '^#' .env | xargs)
    python slack_listener.py

Requires:
    - SLACK_BOT_TOKEN in .env (xoxb-...)
    - SLACK_SIGNING_SECRET in .env
    - cloudflared tunnel pointing to port 8686
    - Slack Events API configured with the tunnel URL
"""

import os
import json
import hmac
import hashlib
import logging
import sqlite3
import threading
from datetime import datetime
from flask import Flask, request, jsonify
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app    = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), "guardian.db")

# ── Slack client setup ────────────────────────────────────────
BOT_TOKEN      = os.environ.get("SLACK_BOT_TOKEN", "")
SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")
CHANNEL_ID     = "C0AQ8SE1448"  # #mining-guardian
slack          = WebClient(token=BOT_TOKEN)


# ── Database helpers ──────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_pending_actions(thread_ts: str):
    """Get all pending actions for a given Slack thread timestamp."""
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM pending_approvals
        WHERE thread_ts = ? AND status = 'PENDING'
    """, (thread_ts,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_approval_status(thread_ts: str, status: str):
    """Mark all pending actions in a thread as approved or denied."""
    conn = get_db()
    conn.execute("""
        UPDATE pending_approvals
        SET status = ?, responded_at = ?
        WHERE thread_ts = ? AND status = 'PENDING'
    """, (status, datetime.now().isoformat(), thread_ts))
    conn.commit()
    conn.close()


def log_audit(miner_id, ip, model, problem, action_taken,
              decision, approved_by, slack_user_id, scan_id=None, notes=None):
    """Write to the permanent action audit log."""
    now = datetime.now()
    conn = get_db()
    conn.execute("""
        INSERT INTO action_audit_log
        (timestamp, date, scan_id, miner_id, ip, model,
         problem, action_taken, decision, approved_by,
         slack_user_id, notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (now.isoformat(), now.strftime("%Y-%m-%d"), scan_id,
          miner_id, ip, model, problem, action_taken,
          decision, approved_by, slack_user_id, notes))
    conn.commit()
    conn.close()
    logger.info("Audit: %s %s on %s by %s", decision, action_taken, ip, approved_by)

# ── Slack verification ────────────────────────────────────────
def verify_slack_signature(request) -> bool:
    """Verify the request actually came from Slack."""
    if not SIGNING_SECRET:
        logger.warning("No signing secret — skipping verification (dev mode)")
        return True
    timestamp  = request.headers.get("X-Slack-Request-Timestamp", "")
    signature  = request.headers.get("X-Slack-Signature", "")
    body       = request.get_data(as_text=True)
    base       = f"v0:{timestamp}:{body}"
    expected   = "v0=" + hmac.new(
        SIGNING_SECRET.encode(), base.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def get_user_display_name(user_id: str) -> str:
    """Get a Slack user's display name from their user ID."""
    try:
        resp = slack.users_info(user=user_id)
        profile = resp["user"].get("profile", {})
        return profile.get("display_name") or profile.get("real_name") or user_id
    except SlackApiError as e:
        logger.warning("Could not get user info: %s", e)
        return user_id


# ── Action execution ──────────────────────────────────────────
def execute_actions(actions: list, approved_by: str, slack_user_id: str):
    """Execute approved actions via AMS and log everything."""
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from mining_guardian import AMSClient, GuardianConfig

    try:
        config = GuardianConfig.from_file(
            os.path.join(os.path.dirname(__file__), "config.json"))
        ams    = AMSClient(config)
    except Exception as e:
        logger.error("Could not load AMS client: %s", e)
        return ["❌ Could not connect to AMS — actions not executed"]

    results = []
    for action in actions:
        miner_id     = action.get("miner_id")
        ip           = action.get("ip")
        model        = action.get("model")
        action_type  = action.get("action_type")
        problem      = action.get("problem")
        pdu_id       = action.get("pdu_id")
        outlet       = action.get("outlet")
        scan_id      = action.get("scan_id")

        try:
            if action_type == "PDU_CYCLE" and pdu_id and outlet:
                ams.pdu_power_cycle(int(pdu_id), int(outlet))
                results.append(f"✅ `{ip}` — PDU outlet cycled (PDU {pdu_id} → Outlet {outlet})")
            elif action_type == "RESTART":
                ams.reboot_miner([str(miner_id)])
                results.append(f"✅ `{ip}` — Firmware restart sent")
            else:
                results.append(f"⚠️ `{ip}` — {action_type} requires manual intervention at facility")

            log_audit(miner_id, ip, model, problem, action_type,
                      "APPROVED", approved_by, slack_user_id, scan_id)
        except Exception as e:
            logger.error("Action failed for %s: %s", ip, e)
            results.append(f"❌ `{ip}` — Action failed: {e}")
            log_audit(miner_id, ip, model, problem, action_type,
                      "FAILED", approved_by, slack_user_id, scan_id,
                      notes=str(e))
    return results

# ── Slack Events handler ──────────────────────────────────────
@app.route("/slack/events", methods=["POST"])
def slack_events():
    """Receive and handle Slack Events API payloads."""
    data = request.json or {}

    # URL verification challenge (one-time during setup)
    if data.get("type") == "url_verification":
        return jsonify({"challenge": data["challenge"]})

    # Verify signature
    if not verify_slack_signature(request):
        return jsonify({"error": "Invalid signature"}), 403

    event = data.get("event", {})

    # Only handle messages in our channel that are thread replies
    if (event.get("type") == "message"
            and event.get("channel") == CHANNEL_ID
            and event.get("thread_ts")
            and not event.get("bot_id")):  # ignore bot messages

        text       = (event.get("text") or "").strip().upper()
        thread_ts  = event.get("thread_ts")
        user_id    = event.get("user")
        message_ts = event.get("ts")

        if text in ("APPROVE", "DENY"):
            # Handle in background thread so we can return 200 immediately
            threading.Thread(
                target=handle_approval,
                args=(text, thread_ts, user_id, message_ts),
                daemon=True
            ).start()

    return jsonify({"ok": True})


def handle_approval(decision: str, thread_ts: str,
                    user_id: str, message_ts: str):
    """Process an APPROVE or DENY reply in a Mining Guardian thread."""
    approved_by = get_user_display_name(user_id)
    actions     = get_pending_actions(thread_ts)

    if not actions:
        slack.chat_postMessage(
            channel=CHANNEL_ID,
            thread_ts=thread_ts,
            text=f"⚠️ @{approved_by} — No pending actions found for this scan. "
                 f"Actions may have already been processed or expired."
        )
        return

    if decision == "APPROVE":
        slack.reactions_add(channel=CHANNEL_ID,
                            timestamp=thread_ts, name="white_check_mark")
        results = execute_actions(actions, approved_by, user_id)
        update_approval_status(thread_ts, "APPROVED")
        reply = f"✅ *{approved_by} approved {len(actions)} action(s):*\n" + \
                "\n".join(results)

    else:  # DENY
        slack.reactions_add(channel=CHANNEL_ID,
                            timestamp=thread_ts, name="x")
        update_approval_status(thread_ts, "DENIED")
        # Log all as denied
        for action in actions:
            log_audit(
                action["miner_id"], action["ip"], action["model"],
                action["problem"], action["action_type"],
                "DENIED", approved_by, user_id, action.get("scan_id"))
        reply = f"❌ *{approved_by} denied {len(actions)} action(s).* No changes made."

    slack.chat_postMessage(
        channel=CHANNEL_ID,
        thread_ts=thread_ts,
        text=reply
    )
    logger.info("Processed %s by %s for thread %s", decision, approved_by, thread_ts)


# ── Health check ──────────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "online", "service": "Mining Guardian Slack Listener"})


if __name__ == "__main__":
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Mining Guardian — Slack Listener")
    print("  http://localhost:8686/slack/events")
    print("  Waiting for APPROVE / DENY replies in #mining-guardian...")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    app.run(host="0.0.0.0", port=8686, debug=False)
