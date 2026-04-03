"""
slack_approval_listener.py
Mining Guardian — Slack Approval Listener (Bolt + Socket Mode)

Since the app uses Socket Mode, interactive Block Kit payloads
(button clicks, checkbox changes) are delivered via the existing
WebSocket connection — no public URL needed.

Two interaction types handled:
  1. Block Kit button clicks (approve_selected / deny_all)
     via Bolt action handlers over Socket Mode.
  2. Text fallback — APPROVE / DENY replies in threads
     via a background polling thread.
"""

import os
import time
import json
import logging
import sqlite3
import requests
import threading
from datetime import datetime
from slack_sdk import WebClient
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("slack_approval_listener")

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")   # xapp-... for Socket Mode
CHANNEL_ID      = "C0AQ8SE1448"
APPROVAL_API    = "http://localhost:8686"
DB_PATH         = "guardian.db"
POLL_INTERVAL   = 10

app = App(token=SLACK_BOT_TOKEN)

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_user_name(client, user_id: str) -> str:
    try:
        info    = client.users_info(user=user_id)
        profile = info.get("user", {}).get("profile", {})
        return profile.get("display_name") or profile.get("real_name", user_id)
    except Exception:
        return user_id


def build_miner_context(miner_ids: list) -> str:
    """Pull 7-day history for selected miners to show before approving."""
    lines = []
    try:
        conn = get_db()
        for mid in miner_ids[:8]:
            flags = conn.execute("""
                SELECT COUNT(*) as cnt, AVG(temp_chip) as avg_temp,
                       AVG(hashrate_pct) as avg_hr
                FROM miner_readings
                WHERE miner_id=? AND action IS NOT NULL AND action!='MONITOR'
                  AND scanned_at >= datetime('now','-7 days')
            """, (mid,)).fetchone()

            last_action = conn.execute("""
                SELECT action_taken, decision, timestamp
                FROM action_audit_log WHERE miner_id=?
                ORDER BY timestamp DESC LIMIT 1
            """, (mid,)).fetchone()

            current = conn.execute("""
                SELECT ip, model FROM miner_readings WHERE miner_id=?
                ORDER BY id DESC LIMIT 1
            """, (mid,)).fetchone()

            if current:
                cnt  = flags["cnt"] if flags else 0
                line = f"  • `{current['ip']}` ({current['model'] or '?'}) — flagged *{cnt}x* in 7 days"
                if flags and flags["avg_hr"]:
                    line += f" | avg HR: {flags['avg_hr']:.0f}%"
                if flags and flags["avg_temp"]:
                    line += f" | avg temp: {flags['avg_temp']:.0f}°C"
                if last_action:
                    line += f" | last: {last_action['action_taken']} {last_action['decision']} ({last_action['timestamp'][:10]})"
                lines.append(line)
        conn.close()
    except Exception as e:
        logger.warning("Could not build miner context: %s", e)
    return "\n".join(lines)


# ── Bolt action handlers (Socket Mode — no URL needed) ────────────────────────

@app.action("approve_selected")
def handle_approve_selected(ack, body, client):
    """Fires when operator clicks ✅ Approve Selected button."""
    ack()  # Must acknowledge within 3 seconds

    user_id   = body.get("user", {}).get("id", "")
    user_name = get_user_name(client, user_id)
    thread_ts = body.get("actions", [{}])[0].get("value", "")

    # Extract which checkboxes are checked from the full state
    selected_ids = []
    state_values = body.get("state", {}).get("values", {})
    for block_state in state_values.values():
        for element_state in block_state.values():
            if element_state.get("type") == "checkboxes":
                for opt in element_state.get("selected_options", []):
                    selected_ids.append(opt["value"])

    if not selected_ids:
        # Nothing checked — deny all
        _do_deny_all(client, thread_ts, user_name, user_id, body)
        return

    # Post pre-approval context
    context = build_miner_context(selected_ids)
    if context:
        client.chat_postMessage(
            channel=CHANNEL_ID, thread_ts=thread_ts,
            text=f"*📋 Pre-Approval Context*\n{context}"
        )

    # Call approval API
    try:
        resp   = requests.post(f"{APPROVAL_API}/approve_selected", json={
            "thread_ts": thread_ts, "miner_ids": selected_ids,
            "user": user_name, "user_id": user_id,
        }, timeout=30)
        result = resp.json()
        approved = result.get("approved_count", 0)
        denied   = result.get("denied_count", 0)
        confirm  = f"✅ *{user_name}* approved *{approved}* miner(s)"
        if denied:
            confirm += f", skipped *{denied}*"
        confirm += ". Executing now."
    except Exception as e:
        confirm = f"❌ Approval API error: {e}"

    client.chat_postMessage(channel=CHANNEL_ID, thread_ts=thread_ts, text=confirm)
    _disable_buttons(client, body)
    logger.info("approve_selected by %s — ids: %s", user_name, selected_ids)


@app.action("deny_all")
def handle_deny_all(ack, body, client):
    """Fires when operator clicks ❌ Deny All button."""
    ack()
    user_id   = body.get("user", {}).get("id", "")
    user_name = get_user_name(client, user_id)
    thread_ts = body.get("actions", [{}])[0].get("value", "")
    _do_deny_all(client, thread_ts, user_name, user_id, body)


@app.action({"action_id": lambda aid: aid.startswith("miner_select_")})
def handle_checkbox_change(ack, body):
    """Acknowledge checkbox state changes silently — no action needed."""
    ack()


def _do_deny_all(client, thread_ts, user_name, user_id, body):
    try:
        resp  = requests.post(f"{APPROVAL_API}/deny", json={
            "thread_ts": thread_ts, "user": user_name, "user_id": user_id,
        }, timeout=15)
        count = resp.json().get("count", 0)
        client.chat_postMessage(
            channel=CHANNEL_ID, thread_ts=thread_ts,
            text=f"❌ *{user_name}* denied all {count} action(s). No changes made."
        )
    except Exception as e:
        logger.error("deny_all failed: %s", e)
    _disable_buttons(client, body)


def _disable_buttons(client, body):
    """Replace the interactive Block Kit message with plain text."""
    try:
        channel    = body.get("channel", {}).get("id", CHANNEL_ID)
        message_ts = body.get("message", {}).get("ts", "")
        if message_ts:
            client.chat_update(channel=channel, ts=message_ts,
                               text="✅ Response recorded.", blocks=[])
    except Exception as e:
        logger.warning("Could not disable buttons: %s", e)

# ── Text fallback + escalation (background polling thread) ───────────────────

processed_messages = set()


def _load_processed():
    try:
        conn = get_db()
        rows = conn.execute(
            "SELECT DISTINCT thread_ts FROM pending_approvals WHERE status != 'PENDING'"
        ).fetchall()
        processed_messages.update(r[0] for r in rows)
        conn.close()
    except Exception:
        pass


def _get_pending_threads():
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT thread_ts FROM pending_approvals WHERE status = 'PENDING'"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def _check_thread_replies(client, thread_ts):
    try:
        resp = client.conversations_replies(channel=CHANNEL_ID, ts=thread_ts, limit=20)
        for msg in resp.get("messages", [])[1:]:
            msg_key = f"{thread_ts}:{msg.get('ts','')}"
            if msg_key in processed_messages:
                continue
            text    = msg.get("text", "").strip().upper()
            user_id = msg.get("user", "")
            if text in ("APPROVE", "APPROVED", "YES", "Y"):
                processed_messages.add(msg_key)
                return "APPROVE", get_user_name(client, user_id), user_id
            elif text in ("DENY", "DENIED", "NO", "N"):
                processed_messages.add(msg_key)
                return "DENY", get_user_name(client, user_id), user_id
    except Exception as e:
        logger.warning("Error checking thread %s: %s", thread_ts, e)
    return None, None, None


def _execute_text_approval(client, thread_ts, action, user_name, user_id):
    try:
        resp  = requests.post(f"{APPROVAL_API}/{action.lower()}", json={
            "thread_ts": thread_ts, "user": user_name, "user_id": user_id,
        }, timeout=30)
        count = resp.json().get("count", 0)
        if action == "APPROVE":
            msg = f"✅ *APPROVED* by {user_name} — {count} action(s) executing."
        else:
            msg = f"❌ *DENIED* by {user_name} — {count} action(s) cancelled."
        client.chat_postMessage(channel=CHANNEL_ID, thread_ts=thread_ts, text=msg)
    except Exception as e:
        logger.error("Text approval API failed: %s", e)


def _check_escalation(client):
    """Alert if any miner has been flagged in 3+ consecutive scans."""
    try:
        conn      = get_db()
        scan_ids  = [str(r["id"]) for r in conn.execute(
            "SELECT id FROM scans ORDER BY id DESC LIMIT 3").fetchall()]
        if len(scan_ids) < 3:
            conn.close(); return
        ph = ",".join("?" * len(scan_ids))
        persistent = conn.execute(f"""
            SELECT miner_id, ip, model, COUNT(DISTINCT scan_id) as consecutive,
                   AVG(hashrate_pct) as avg_hr, AVG(temp_chip) as avg_temp,
                   GROUP_CONCAT(DISTINCT action) as actions
            FROM miner_readings
            WHERE scan_id IN ({ph}) AND action IS NOT NULL AND action!='MONITOR'
            GROUP BY miner_id HAVING consecutive=3
        """, scan_ids).fetchall()
        conn.close()
        for m in persistent:
            key = f"escalated:{m['miner_id']}"
            if key in processed_messages: continue
            client.chat_postMessage(channel=CHANNEL_ID, text=(
                f"🚨 *Persistent Issue — `{m['ip']}`* ({m['model']})\n"
                f"Flagged 3 consecutive scans — avg HR: {m['avg_hr']:.0f}% | "
                f"avg temp: {m['avg_temp']:.0f}°C | actions: {m['actions']}\n"
                f"Check pending approvals in <#{CHANNEL_ID}>"
            ))
            processed_messages.add(key)
            logger.info("Escalation posted for %s", m["ip"])
    except Exception as e:
        logger.warning("Escalation check failed: %s", e)


def _poll_loop():
    """Background thread — text fallback + escalation checks."""
    client    = WebClient(token=SLACK_BOT_TOKEN)
    _load_processed()
    count = 0
    while True:
        try:
            for ts in _get_pending_threads():
                action, user_name, user_id = _check_thread_replies(client, ts)
                if action:
                    _execute_text_approval(client, ts, action, user_name, user_id)
            count += 1
            if count % 6 == 0:
                _check_escalation(client)
        except Exception as e:
            logger.error("Poll loop error: %s", e)
        time.sleep(POLL_INTERVAL)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  Mining Guardian — Slack Approval Listener")
    print("  Bolt Socket Mode: buttons + checkbox approval")
    print("  Background: text APPROVE/DENY + escalation")
    print("=" * 55)

    # Start text-fallback + escalation in background thread
    threading.Thread(target=_poll_loop, daemon=True).start()

    # Start Bolt Socket Mode handler (blocks main thread)
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
