#!/usr/bin/env python3
"""
slack_listener.py
Mining Guardian — Slack Approval Listener (Socket Mode)

Listens for APPROVE / DENY replies in #mining-guardian threads.
Uses Slack Socket Mode — no public URL or tunnel required.

Usage:
    source venv/bin/activate
    export $(grep -v '^#' .env | xargs)
    python slack_listener.py
"""

import os
import sqlite3
import logging
import threading
from datetime import datetime
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN  = os.environ.get("SLACK_BOT_TOKEN", "")
APP_TOKEN  = os.environ.get("SLACK_APP_TOKEN", "")
CHANNEL_ID = "C0AQ8SE1448"
DB_PATH    = os.path.join(os.path.dirname(__file__), "guardian.db")

# Authorized Slack user IDs — only these users can approve/deny actions
AUTHORIZED_USER_IDS_RAW = os.getenv("AUTHORIZED_SLACK_USER_IDS", "")
AUTHORIZED_USER_IDS = set(
    uid.strip() for uid in AUTHORIZED_USER_IDS_RAW.split(",") if uid.strip()
)

app = App(token=BOT_TOKEN)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_pending_actions(thread_ts: str):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM pending_approvals WHERE thread_ts=? AND status='PENDING'",
        (thread_ts,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_approval_status(thread_ts: str, status: str):
    conn = get_db()
    conn.execute(
        "UPDATE pending_approvals SET status=?, responded_at=? WHERE thread_ts=? AND status='PENDING'",
        (status, datetime.now().isoformat(), thread_ts)
    )
    conn.commit()
    conn.close()


def log_audit(miner_id, ip, model, problem, action_taken,
              decision, approved_by, slack_user_id, scan_id=None, notes=None):
    now = datetime.now()
    conn = get_db()
    conn.execute(
        "INSERT INTO action_audit_log "
        "(timestamp, date, scan_id, miner_id, ip, model, problem, "
        " action_taken, decision, approved_by, slack_user_id, notes) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (now.isoformat(), now.strftime("%Y-%m-%d"), scan_id,
         miner_id, ip, model, problem, action_taken,
         decision, approved_by, slack_user_id, notes)
    )
    conn.commit()
    conn.close()
    logger.info("Audit: %s %s on %s by %s", decision, action_taken, ip, approved_by)

def execute_actions(actions, approved_by, slack_user_id):
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from mining_guardian import AMSClient, GuardianConfig
    try:
        config = GuardianConfig.from_file(os.path.join(os.path.dirname(__file__), "config.json"))
        ams    = AMSClient(config)
    except Exception as e:
        logger.error("Could not load AMS client: %s", e)
        return ["❌ Could not connect to AMS"]

    results = []
    for action in actions:
        miner_id    = action.get("miner_id")
        ip          = action.get("ip")
        model       = action.get("model")
        action_type = action.get("action_type")
        problem     = action.get("problem")
        pdu_id      = action.get("pdu_id")
        outlet      = action.get("outlet")
        scan_id     = action.get("scan_id")
        try:
            if action_type == "PDU_CYCLE" and pdu_id and outlet:
                ams.pdu_power_cycle(int(pdu_id), int(outlet))
                results.append(f"✅ `{ip}` — PDU outlet cycled (PDU {pdu_id} → Outlet {outlet})")
            elif action_type == "RESTART":
                ams.reboot_miner([str(miner_id)])
                results.append(f"✅ `{ip}` — Firmware restart sent")
            else:
                results.append(f"⚠️ `{ip}` — {action_type} requires manual visit")
            log_audit(miner_id, ip, model, problem, action_type,
                      "APPROVED", approved_by, slack_user_id, scan_id)
        except Exception as e:
            logger.error("Action failed for %s: %s", ip, e)
            results.append(f"❌ `{ip}` — Failed: {e}")
            log_audit(miner_id, ip, model, problem, action_type,
                      "FAILED", approved_by, slack_user_id, scan_id, notes=str(e))
    return results


@app.event({"type": "message"})
def debug_raw(body, logger):
    logger.info("RAW SOCKET EVENT: %s", str(body)[:400])


@app.event("message")
def handle_message(event, say, client):
    text      = event.get("text", "").strip().upper()
    thread_ts = event.get("thread_ts")
    user_id   = event.get("user")
    channel   = event.get("channel")
    bot_id    = event.get("bot_id")

    logger.info("Message received: text=%s channel=%s thread=%s bot=%s",
                text[:20], channel, thread_ts, bot_id)

    if bot_id or channel != CHANNEL_ID or not thread_ts:
        return

    if text not in ("APPROVE", "DENY"):
        return

    # Authorization check — only allowed users can trigger hardware actions
    if AUTHORIZED_USER_IDS and user_id not in AUTHORIZED_USER_IDS:
        logger.warning("Unauthorized approval attempt from user %s — ignored", user_id)
        return

    logger.info("Processing %s from %s", text, user_id)

    try:
        info        = client.users_info(user=user_id)
        profile     = info["user"].get("profile", {})
        approved_by = profile.get("display_name") or profile.get("real_name") or user_id
    except Exception:
        approved_by = user_id

    actions = get_pending_actions(thread_ts)

    if not actions:
        say(text="⚠️ No pending actions found for this scan.", thread_ts=thread_ts)
        return

    if text == "APPROVE":
        client.reactions_add(channel=CHANNEL_ID, timestamp=thread_ts, name="white_check_mark")
        results = execute_actions(actions, approved_by, user_id)
        update_approval_status(thread_ts, "APPROVED")
        reply = f"✅ *{approved_by} approved {len(actions)} action(s):*\n" + "\n".join(results)
    else:
        client.reactions_add(channel=CHANNEL_ID, timestamp=thread_ts, name="x")
        for action in actions:
            log_audit(action["miner_id"], action["ip"], action["model"],
                      action["problem"], action["action_type"],
                      "DENIED", approved_by, user_id, action.get("scan_id"))
        update_approval_status(thread_ts, "DENIED")
        reply = f"❌ *{approved_by} denied {len(actions)} action(s).* No changes made."

    say(text=reply, thread_ts=thread_ts)
    logger.info("Processed %s by %s", text, approved_by)


# handle_approval removed — was a duplicate of handle_message causing double
# hardware actuation (double restart / double PDU cycle) on every APPROVE message


if __name__ == "__main__":
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Mining Guardian — Slack Listener (Socket Mode)")
    print("  Waiting for APPROVE / DENY in #mining-guardian threads...")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    handler = SocketModeHandler(app, APP_TOKEN)
    handler.start()
