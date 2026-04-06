"""
slack_actions_handler.py
Mining Guardian — Slack Interactive Actions Handler

Receives interactive payloads from Slack when operators click
buttons, select from dropdowns, or check checkboxes in Block Kit messages.

This is a FastAPI endpoint that Slack's Request URL points to.
It processes the action and calls the approval API internally.

Slack sends POST to: https://slack.fieslerfamily.com/slack/actions
(Cloudflare tunnel → VPS:8686 → this handler)
"""

import json
import hmac
import hashlib
import time
import logging
import os
import requests
from fastapi import FastAPI, Request, Response
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("slack_actions")

SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")
APPROVAL_API = "http://localhost:8686"
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")


def verify_slack_signature(request_body: bytes, timestamp: str,
                           signature: str) -> bool:
    """Verify the request is from Slack using signing secret."""
    if not SLACK_SIGNING_SECRET:
        return True  # Dev mode — accept all
    basestring = f"v0:{timestamp}:{request_body.decode()}"
    my_sig = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode(), basestring.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(my_sig, signature)


async def handle_slack_action(request: Request) -> Response:
    """Process interactive payloads from Slack Block Kit."""
    body = await request.body()
    
    # Verify signature
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    
    if abs(time.time() - float(timestamp or 0)) > 300:
        return Response(status_code=403, content="Stale request")
    
    if not verify_slack_signature(body, timestamp, signature):
        return Response(status_code=403, content="Invalid signature")

    # Parse the payload
    from urllib.parse import parse_qs
    form_data = parse_qs(body.decode())
    payload_str = form_data.get("payload", [""])[0]
    
    if not payload_str:
        return Response(status_code=400, content="No payload")
    
    payload = json.loads(payload_str)
    action_type = payload.get("type")
    user = payload.get("user", {})
    user_id = user.get("id", "")
    user_name = user.get("name", user.get("username", "unknown"))
    channel = payload.get("channel", {}).get("id", "")
    message_ts = payload.get("message", {}).get("ts", "")
    
    # Process actions
    actions = payload.get("actions", [])
    
    for action in actions:
        action_id = action.get("action_id", "")
        value = action.get("value", "")
        
        logger.info("Slack action: %s = %s by %s", action_id, value, user_name)
        
        # ── Single miner approve/deny (overflow menu) ────────
        if action_id.startswith("miner_action_"):
            miner_id = action_id.replace("miner_action_", "")
            if value.startswith("approve_"):
                _approve_miner(miner_id, message_ts, user_name, user_id, channel)
            elif value.startswith("deny_"):
                _deny_miner(miner_id, message_ts, user_name, user_id, channel)
        
        # ── Approve All button ────────────────────────────────
        elif action_id == "approve_all":
            _approve_all(message_ts, user_name, user_id, channel)
        
        # ── Deny All button ───────────────────────────────────
        elif action_id == "deny_all":
            _deny_all(message_ts, user_name, user_id, channel)
        
        # ── Approve Selected recommendations ──────────────────
        elif action_id == "approve_selected_recs":
            # Get selected checkboxes from the same payload
            selected = _get_selected_checkboxes(payload)
            _approve_selected(selected, message_ts, user_name, user_id, channel)
        
        # ── Approve All recommendations ───────────────────────
        elif action_id == "approve_all_recs":
            _approve_all(message_ts, user_name, user_id, channel)
        
        # ── Deny All recommendations ──────────────────────────
        elif action_id == "deny_all_recs":
            _deny_all(message_ts, user_name, user_id, channel)
        
        # ── Denial reason dropdown ────────────────────────────
        elif action_id.startswith("denial_reason_"):
            miner_id = action_id.replace("denial_reason_", "")
            selected_option = action.get("selected_option", {})
            reason_value = selected_option.get("value", "")
            if ":" in reason_value:
                _, reason_text = reason_value.split(":", 1)
                _store_denial_reason(miner_id, reason_text, user_name, channel, message_ts)
        
        # ── Custom denial reason text input ───────────────────
        elif action_id.startswith("denial_custom_"):
            miner_id = action_id.replace("denial_custom_", "")
            reason_text = action.get("value", "")
            if reason_text:
                _store_denial_reason(miner_id, reason_text, user_name, channel, message_ts)

    # Acknowledge immediately (Slack requires 3s response)
    return Response(status_code=200)


def _approve_miner(miner_id: str, thread_ts: str, user: str,
                    user_id: str, channel: str):
    """Approve a single miner action."""
    try:
        requests.post(f"{APPROVAL_API}/approve", json={
            "thread_ts": thread_ts, "user": user, "user_id": user_id,
            "miner_ids": [miner_id],
        }, timeout=15)
        _post_reply(channel, thread_ts, f"✅ *{user}* approved action on miner {miner_id}")
    except Exception as e:
        logger.error("Approve failed: %s", e)


def _deny_miner(miner_id: str, thread_ts: str, user: str,
                 user_id: str, channel: str):
    """Deny a single miner action and post denial reason blocks."""
    try:
        requests.post(f"{APPROVAL_API}/deny", json={
            "thread_ts": thread_ts, "user": user, "user_id": user_id,
            "miner_ids": [miner_id],
        }, timeout=15)
        
        # Post denial reason collection blocks
        from slack_block_kit import build_denial_reason_blocks
        import sqlite3
        from pathlib import Path
        _ROOT = Path(__file__).resolve().parent.parent
        conn = sqlite3.connect(str(_ROOT / "guardian.db"), timeout=30)
        conn.row_factory = sqlite3.Row
        miner = conn.execute(
            "SELECT ip FROM miner_readings WHERE miner_id=? ORDER BY id DESC LIMIT 1",
            (miner_id,)
        ).fetchone()
        conn.close()
        ip = miner["ip"] if miner else miner_id
        
        blocks = build_denial_reason_blocks(ip, "action", miner_id)
        _post_blocks(channel, thread_ts, blocks)
    except Exception as e:
        logger.error("Deny failed: %s", e)


def _approve_all(thread_ts: str, user: str, user_id: str, channel: str):
    """Approve all pending actions in a thread."""
    try:
        resp = requests.post(f"{APPROVAL_API}/approve", json={
            "thread_ts": thread_ts, "user": user, "user_id": user_id,
        }, timeout=30)
        count = resp.json().get("count", 0)
        _post_reply(channel, thread_ts, f"✅ *{user}* approved *{count}* action(s). Executing now.")
    except Exception as e:
        logger.error("Approve all failed: %s", e)


def _deny_all(thread_ts: str, user: str, user_id: str, channel: str):
    """Deny all pending actions in a thread."""
    try:
        resp = requests.post(f"{APPROVAL_API}/deny", json={
            "thread_ts": thread_ts, "user": user, "user_id": user_id,
        }, timeout=15)
        count = resp.json().get("count", 0)
        _post_reply(channel, thread_ts, f"❌ *{user}* denied *{count}* action(s).")
    except Exception as e:
        logger.error("Deny all failed: %s", e)


def _approve_selected(selected: list, thread_ts: str, user: str,
                       user_id: str, channel: str):
    """Approve selected miners from checkboxes."""
    if not selected:
        _post_reply(channel, thread_ts, "⚠️ No miners selected. Check the boxes first.")
        return
    try:
        miner_ids = [s.split(":")[0] for s in selected]
        resp = requests.post(f"{APPROVAL_API}/approve_selected", json={
            "thread_ts": thread_ts, "miner_ids": miner_ids,
            "user": user, "user_id": user_id,
        }, timeout=30)
        count = resp.json().get("approved_count", 0)
        _post_reply(channel, thread_ts, f"✅ *{user}* approved *{count}* selected action(s).")
    except Exception as e:
        logger.error("Approve selected failed: %s", e)


def _store_denial_reason(miner_id: str, reason: str, user: str,
                          channel: str, thread_ts: str):
    """Store denial reason and send to LLM for rule extraction."""
    try:
        import sqlite3
        from pathlib import Path
        _ROOT = Path(__file__).resolve().parent.parent
        conn = sqlite3.connect(str(_ROOT / "guardian.db"), timeout=30)
        conn.execute(
            "UPDATE action_audit_log SET notes = COALESCE(notes,'') || ' | DENIAL_REASON: ' || ? "
            "WHERE timestamp >= datetime('now','-5 minutes') "
            "AND decision='DENIED' AND miner_id=? AND notes NOT LIKE '%DENIAL_REASON%'",
            (reason, miner_id)
        )
        conn.commit()
        conn.close()
        
        _post_reply(channel, thread_ts,
                     f"✅ _Reason logged: \"{reason[:100]}\"_")
        
        # Send to local LLM for immediate rule extraction
        try:
            import sys, threading
            _ai = str(Path(__file__).resolve().parent.parent / "ai")
            if _ai not in sys.path:
                sys.path.insert(0, _ai)
            from llm_scan_hook import run_denial_processing_llm
            
            conn2 = sqlite3.connect(str(_ROOT / "guardian.db"), timeout=30)
            conn2.row_factory = sqlite3.Row
            miner = conn2.execute(
                "SELECT ip, action_taken FROM action_audit_log WHERE miner_id=? ORDER BY id DESC LIMIT 1",
                (miner_id,)
            ).fetchone()
            conn2.close()
            ip = miner["ip"] if miner else miner_id
            action = miner["action_taken"] if miner else "unknown"
            threading.Thread(
                target=run_denial_processing_llm,
                args=(ip, action, reason),
                daemon=True
            ).start()
        except Exception:
            pass
            
    except Exception as e:
        logger.error("Store denial reason failed: %s", e)


def _get_selected_checkboxes(payload: dict) -> list:
    """Extract selected checkbox values from Slack payload."""
    selected = []
    for action in payload.get("actions", []):
        if action.get("type") == "checkboxes":
            for opt in action.get("selected_options", []):
                selected.append(opt.get("value", ""))
    # Also check state values
    state = payload.get("state", {}).get("values", {})
    for block_id, block_actions in state.items():
        for aid, adata in block_actions.items():
            if adata.get("type") == "checkboxes":
                for opt in adata.get("selected_options", []):
                    selected.append(opt.get("value", ""))
    return selected


def _post_reply(channel: str, thread_ts: str, text: str):
    """Post a reply in a thread."""
    try:
        from slack_sdk import WebClient
        client = WebClient(token=SLACK_BOT_TOKEN)
        client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=text)
    except Exception as e:
        logger.warning("Post reply failed: %s", e)


def _post_blocks(channel: str, thread_ts: str, blocks: list):
    """Post Block Kit blocks in a thread."""
    try:
        from slack_sdk import WebClient
        client = WebClient(token=SLACK_BOT_TOKEN)
        client.chat_postMessage(
            channel=channel, thread_ts=thread_ts,
            blocks=blocks, text="Action required"
        )
    except Exception as e:
        logger.warning("Post blocks failed: %s", e)
