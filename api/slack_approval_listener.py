"""
slack_approval_listener.py
Mining Guardian — Slack Approval Listener

Polls #mining-guardian for APPROVE/DENY replies in scan threads.
Also handles text responses like "approve 1,2,3" to select specific miners.

Uses Slack's REST API with polling (not Bolt/Socket Mode). Block Kit
buttons post a text reply that we detect here. Switching to Bolt/Socket Mode
is a possible follow-up enhancement.
"""

import sys
import os
import time
import json
import logging
import psycopg2
from psycopg2.extras import DictCursor
import requests
import threading
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from slack_sdk import WebClient
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("slack_approval_listener")

# Path setup MUST come before `from db_targets import ...` below — the
# launcher runs us via direct script path (not python -m) so `core`
# isn't auto-discovered. W14a regression 2026-05-12.
_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT / "core"), str(_ROOT / "clients"), str(_ROOT / "monitoring")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Bare form (not `from core.db_targets`) since `core/` itself is on
# sys.path, not the install root.
from db_targets import operational_target  # noqa: E402

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
CHANNEL_ID      = "C0AQ8SE1448"
APPROVAL_API    = "http://localhost:8686"
def _pg_dsn() -> str:
    """Operational Postgres DSN via core.db_targets.

    W14a (2026-05-12): delegated to the resolver so this module stays
    on the operational instance after W14 splits catalog onto port
    5433. This listener reads the operational action_audit_log to
    poll for newly-queued approvals.
    """
    return operational_target().dsn()
POLL_INTERVAL   = 15

# Authorized Slack user IDs — only these users can approve/deny actions.
# Add user IDs from your Slack workspace (Settings → Members → click member → copy member ID).
# Empty string = allow any workspace member (less secure but backward compatible).
AUTHORIZED_USER_IDS_RAW = os.getenv("AUTHORIZED_SLACK_USER_IDS", "")
AUTHORIZED_USER_IDS = set(
    uid.strip() for uid in AUTHORIZED_USER_IDS_RAW.split(",") if uid.strip()
)


class _PgConnWrapper:
    """Thin wrapper over psycopg2 Connection that provides SQLite-style
    conn.execute(sql, params).fetchone() shortcut. See core/overnight_automation.py
    for the rationale — psycopg2 Connection has no .execute() method.
    """

    def __init__(self, dsn: str):
        self._conn = psycopg2.connect(dsn, cursor_factory=DictCursor)

    def execute(self, sql, params=()):
        cur = self._conn.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()
        return False


def get_db():
    """Return a psycopg2-backed connection wrapper with SQLite-style shortcut."""
    return _PgConnWrapper(_pg_dsn())


def get_user_name(client, user_id: str) -> str:
    try:
        info    = client.users_info(user=user_id)
        profile = info.get("user", {}).get("profile", {})
        return profile.get("display_name") or profile.get("real_name", user_id)
    except Exception:
        return user_id


def build_miner_context(miner_ids: list) -> str:
    """Pull 7-day history for selected miners."""
    lines = []
    try:
        conn = get_db()
        for mid in miner_ids[:8]:
            flags = conn.execute("""
                SELECT COUNT(*) as cnt, AVG(temp_chip) as avg_temp,
                       AVG(hashrate_pct) as avg_hr
                FROM miner_readings
                WHERE miner_id=%s AND action IS NOT NULL AND action!='MONITOR'
                  AND scanned_at >= datetime('now','-7 days')
            """, (mid,)).fetchone()
            last = conn.execute("""
                SELECT action_taken, decision, timestamp
                FROM action_audit_log WHERE miner_id=%s
                ORDER BY timestamp DESC LIMIT 1
            """, (mid,)).fetchone()
            cur = conn.execute("""
                SELECT ip, model FROM miner_readings WHERE miner_id=%s
                ORDER BY id DESC LIMIT 1
            """, (mid,)).fetchone()
            if cur:
                cnt  = flags["cnt"] if flags else 0
                line = f"  • `{cur['ip']}` ({cur['model'] or '%s'}) — flagged *{cnt}x* in 7 days"
                if flags and flags["avg_hr"]:
                    line += f" | avg HR: {flags['avg_hr']:.0f}%"
                if last:
                    line += f" | last: {last['action_taken']} {last['decision']} ({last['timestamp'][:10]})"
                lines.append(line)
        conn.close()
    except Exception as e:
        logger.warning("miner context failed: %s", e)
    return "\n".join(lines)


def cleanup_stale_pending():
    """Mark old PENDING approvals (>24h) as EXPIRED so we stop polling them."""
    try:
        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
        conn = get_db()
        try:
            cur  = conn.execute(
                "UPDATE pending_approvals SET status='EXPIRED' WHERE status='PENDING' AND created_at < %s",
                (cutoff,)
            )
            if cur.rowcount:
                logger.info("Cleaned up %d stale pending approvals", cur.rowcount)
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.warning("cleanup failed: %s", e)


_PROCESSED_MAX = 10000  # Cap to prevent unbounded memory growth

class ApprovalListener:
    def __init__(self):
        self.client = WebClient(token=SLACK_BOT_TOKEN)
        self.processed = OrderedDict()  # bounded set — keys only, values unused
        self._load_processed()
        cleanup_stale_pending()

    def _load_processed(self):
        try:
            conn = get_db()
            rows = conn.execute(
                "SELECT DISTINCT thread_ts FROM pending_approvals WHERE status != 'PENDING'"
            ).fetchall()
            self.processed = OrderedDict.fromkeys(r[0] for r in rows)
            conn.close()
        except Exception:
            pass

    def _mark_processed(self, key: str):
        """Add key to bounded processed set, evicting oldest if over limit."""
        self.processed[key] = None
        while len(self.processed) > _PROCESSED_MAX:
            self.processed.popitem(last=False)

    def _get_pending_threads(self):
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT DISTINCT thread_ts FROM pending_approvals WHERE status='PENDING'"
            ).fetchall()
        finally:
            conn.close()
        return [r[0] for r in rows]

    def _check_thread(self, thread_ts):
        """Check for APPROVE/DENY or 'approve 1,2,3' style replies."""
        try:
            resp = self.client.conversations_replies(
                channel=CHANNEL_ID, ts=thread_ts, limit=20
            )
            for msg in resp.get("messages", [])[1:]:
                msg_key = f"{thread_ts}:{msg.get('ts','')}"
                if msg_key in self.processed:
                    continue
                text    = msg.get("text", "").strip()
                user_id = msg.get("user", "")
                upper   = text.upper()

                # Authorization check — skip if user not in allowlist
                if AUTHORIZED_USER_IDS and user_id not in AUTHORIZED_USER_IDS:
                    logger.debug("Ignoring approval attempt from unauthorized user %s", user_id)
                    continue

                # Full approve/deny
                if upper in ("APPROVE", "APPROVED", "YES", "Y"):
                    self._mark_processed(msg_key)
                    return "APPROVE", None, get_user_name(self.client, user_id), user_id

                # Match DENY in any form: "deny", "deny.", "deny, reason", "denied!", etc
                first_word = upper.split()[0].rstrip(".,!:;") if upper.split() else ""
                if first_word in ("DENY", "DENIED", "NO", "N"):
                    self._mark_processed(msg_key)
                    return "DENY", None, get_user_name(self.client, user_id), user_id

                # Selective: "approve 1,2,3" or "approve .36,.46"
                import re
                m = re.match(r'^approve\s+(.+)$', text, re.IGNORECASE)
                if m:
                    self._mark_processed(msg_key)
                    return "APPROVE_SELECTED", m.group(1).strip(), get_user_name(self.client, user_id), user_id

        except Exception as e:
            if "ratelimited" not in str(e).lower():
                logger.warning("Thread check %s: %s", thread_ts, e)
        return None, None, None, None

    def _resolve_selected(self, thread_ts: str, selector: str) -> list:
        """Turn '1,2,3' or '.36,.46' into miner_ids from pending approvals."""
        conn     = get_db()
        pending  = conn.execute(
            "SELECT miner_id, ip FROM pending_approvals WHERE thread_ts=%s AND status='PENDING'",
            (thread_ts,)
        ).fetchall()
        conn.close()

        # If selector looks like IPs (contains dots)
        if "." in selector:
            parts   = [p.strip().lstrip(".") for p in selector.split(",")]
            matched = [str(r["miner_id"]) for r in pending
                       if any(r["ip"].endswith(p) for p in parts)]
            return matched

        # Otherwise treat as 1-based index numbers
        try:
            indices = [int(x.strip()) - 1 for x in selector.split(",")]
            pending_list = list(pending)
            return [str(pending_list[i]["miner_id"]) for i in indices
                    if 0 <= i < len(pending_list)]
        except Exception:
            return []

    def _execute(self, thread_ts, action, selector, user_name, user_id):
        """Call the approval API and post confirmation."""
        try:
            if action == "APPROVE":
                resp  = requests.post(f"{APPROVAL_API}/approve", json={
                    "thread_ts": thread_ts, "user": user_name, "user_id": user_id
                }, timeout=30)
                count = resp.json().get("count", 0)
                msg   = f"✅ *APPROVED* by {user_name} — {count} action(s) executing."

            elif action == "APPROVE_SELECTED":
                miner_ids = self._resolve_selected(thread_ts, selector)
                if not miner_ids:
                    self.client.chat_postMessage(
                        channel=CHANNEL_ID, thread_ts=thread_ts,
                        text=f"⚠️ Couldn't match '{selector}' to any pending miners. Reply APPROVE to approve all."
                    )
                    return
                # Post pre-approval context
                ctx = build_miner_context(miner_ids)
                if ctx:
                    self.client.chat_postMessage(
                        channel=CHANNEL_ID, thread_ts=thread_ts,
                        text=f"*📋 Pre-Approval Context*\n{ctx}"
                    )
                resp    = requests.post(f"{APPROVAL_API}/approve_selected", json={
                    "thread_ts": thread_ts, "miner_ids": miner_ids,
                    "user": user_name, "user_id": user_id
                }, timeout=30)
                result  = resp.json()
                approved = result.get("approved_count", 0)
                denied   = result.get("denied_count", 0)
                msg = f"✅ *{user_name}* approved *{approved}* miner(s)"
                if denied:
                    msg += f", skipped *{denied}*"
                msg += ". Executing now."

            else:  # DENY
                resp = requests.post(f"{APPROVAL_API}/deny", json={
                    "thread_ts": thread_ts, "user": user_name, "user_id": user_id
                }, timeout=15)
                count = resp.json().get("count", 0)
                msg = f"❌ *DENIED* by {user_name} — {count} action(s) cancelled."
            self.client.chat_postMessage(
                channel=CHANNEL_ID, thread_ts=thread_ts, text=msg
            )
            logger.info("%s by %s — thread %s", action, user_name, thread_ts)

            # Feature 3: Denial Reason Capture
            # ALWAYS ask why after a deny — clean, separate, never forgotten
            if action == "DENY":
                threading.Thread(
                    target=self._capture_denial_reason,
                    args=(thread_ts, user_id, user_name),
                    daemon=True
                ).start()

        except Exception as e:
            logger.error("Execution failed: %s", e)

    def _capture_denial_reason(self, thread_ts: str, user_id: str, user_name: str):
        """
        Feature 3: Denial Reason Capture.
        After a DENY, post a follow-up in the thread asking why.
        Wait up to 5 minutes for a reply. Store the reason in action_audit_log.notes
        so the AI can learn from operator decisions over time.
        """
        try:
            # Post the follow-up prompt
            prompt_resp = self.client.chat_postMessage(
                channel=CHANNEL_ID,
                thread_ts=thread_ts,
                text="💬 _Why did you deny%s (optional — reply here within 5 min to help the AI learn)_"
            )
            prompt_ts = prompt_resp["ts"]

            # Poll the thread for a reply from the same user for up to 5 minutes
            deadline = datetime.now().timestamp() + 300  # 5 minutes
            seen_ts  = set()
            reason   = None

            while datetime.now().timestamp() < deadline:
                time.sleep(15)
                try:
                    replies = self.client.conversations_replies(
                        channel=CHANNEL_ID,
                        ts=thread_ts,
                        oldest=prompt_ts,
                        limit=10
                    )
                    for msg in replies.get("messages", []):
                        msg_ts = msg.get("ts", "")
                        if msg_ts == prompt_ts:
                            continue  # skip the bot's own prompt
                        if msg_ts in seen_ts:
                            continue
                        # Only capture from the user who denied
                        if msg.get("user") == user_id:
                            text = msg.get("text", "").strip()
                            if text and len(text) > 2:
                                reason = text
                                seen_ts.add(msg_ts)
                                break
                    if reason:
                        break
                except Exception:
                    pass

            if reason:
                # Store reason in action_audit_log for recent DENY entries in this thread
                conn = get_db()
                try:
                    conn.execute("""
                        UPDATE action_audit_log
                        SET notes = COALESCE(notes || ' | ', '') || 'DENIAL_REASON: ' || %s
                        WHERE decision = 'DENIED'
                          AND approved_by = %s
                          AND date = date('now')
                          AND (notes IS NULL OR notes NOT LIKE '%%DENIAL_REASON%%')
                        ORDER BY timestamp DESC
                        LIMIT 5
                    """, (reason, user_name))
                    conn.commit()
                finally:
                    conn.close()

                # Acknowledge receipt
                self.client.chat_postMessage(
                    channel=CHANNEL_ID,
                    thread_ts=thread_ts,
                    text=f"✅ _Got it — reason logged for AI training: \"{reason[:100]}\"_"
                )
                logger.info("Denial reason captured from %s: %s", user_name, reason[:80])
                # Send to local LLM for immediate rule extraction
                try:
                    import sys
                    from pathlib import Path
                    _ai = str(Path(__file__).resolve().parent.parent / "ai")
                    if _ai not in sys.path:
                        sys.path.insert(0, _ai)
                    from llm_scan_hook import run_denial_processing_llm
                    # Get miner IP from the pending approval
                    conn_d = get_db()
                    denied_miner = conn_d.execute(
                        "SELECT ip, action_type FROM pending_approvals WHERE thread_ts=%s LIMIT 1",
                        (thread_ts,)
                    ).fetchone()
                    conn_d.close()
                    if denied_miner:
                        import threading
                        threading.Thread(
                            target=run_denial_processing_llm,
                            args=(denied_miner["ip"], denied_miner["action_type"], reason),
                            daemon=True
                        ).start()
                except Exception as ex:
                    logger.debug("LLM denial processing failed: %s", ex)
            else:
                # No reply — silently remove the prompt (or just leave it)
                logger.info("No denial reason provided for thread %s", thread_ts)

        except Exception as e:
            logger.warning("Denial reason capture failed: %s", e)

    def _check_escalation(self):
        """Alert if any miner flagged in 3+ consecutive scans — skip known dead boards."""
        try:
            conn     = get_db()
            scan_ids = [str(r["id"]) for r in conn.execute(
                "SELECT id FROM scans ORDER BY id DESC LIMIT 3").fetchall()]
            if len(scan_ids) < 3:
                conn.close(); return

            # Miners with tickets already created — suppress from escalation alerts
            dead_miner_ids = {str(r["miner_id"]) for r in conn.execute(
                "SELECT miner_id FROM known_dead_boards WHERE resolved_at IS NULL AND ticket_created IS NOT NULL"
            ).fetchall()}

            ph = ",".join(["%s"] * len(scan_ids))
            persistent = conn.execute(f"""
                SELECT miner_id,
                       MIN(ip) as ip,
                       MIN(model) as model,
                       COUNT(DISTINCT scan_id) as consecutive,
                       AVG(hashrate_pct) as avg_hr,
                       AVG(temp_chip) as avg_temp,
                       string_agg(DISTINCT action, ',') as actions
                FROM miner_readings
                WHERE scan_id IN ({ph}) AND action IS NOT NULL AND action!='MONITOR'
                GROUP BY miner_id
                HAVING COUNT(DISTINCT scan_id)=3
            """, scan_ids).fetchall()
            conn.close()
            for m in persistent:
                # Skip miners with AMS tickets — they're suppressed
                if str(m['miner_id']) in dead_miner_ids:
                    continue
                key = f"escalated:{m['miner_id']}"
                if key in self.processed: continue
                self.client.chat_postMessage(channel=CHANNEL_ID, text=(
                    f"🚨 *Persistent Issue — `{m['ip']}`* ({m['model']})\n"
                    f"Flagged 3 consecutive scans | avg HR: {m['avg_hr'] or 0:.0f}% "
                    f"| avg temp: {m['avg_temp'] or 0:.0f}°C | actions: {m['actions']}"
                ))
                self._mark_processed(key)
                logger.info("Escalation: %s", m["ip"])
        except Exception as e:
            logger.warning("Escalation check failed: %s", e)

    def run(self):
        logger.info("Slack Approval Listener started — polling every %ds", POLL_INTERVAL)
        logger.info("Use APPROVE, DENY, or 'approve .36,.46' or 'approve 1,3' in thread")
        count = 0
        while True:
            try:
                threads = self._get_pending_threads()
                for ts in threads:
                    action, selector, user_name, user_id = self._check_thread(ts)
                    if action:
                        self._execute(ts, action, selector, user_name, user_id)
                    time.sleep(0.5)  # small gap between thread checks

                count += 1
                if count % 8 == 0:   # every ~2 min
                    self._check_escalation()
                if count % 240 == 0:  # every hour
                    cleanup_stale_pending()

            except Exception as e:
                logger.error("Run loop error: %s", e)
            # Bucket 9 §10.7: hot-reload poll interval from system_schedules
            # each cycle so operators can retime from the Web GUI.
            try:
                from api.system_schedules import get_interval_seconds
                _interval = get_interval_seconds("slack_listener_poll")
            except Exception:
                _interval = POLL_INTERVAL
            time.sleep(_interval)


if __name__ == "__main__":
    print("=" * 55)
    print("  Mining Guardian — Slack Approval Listener")
    print("  Reply APPROVE, DENY, or 'approve .36,.46'")
    print("=" * 55)
    ApprovalListener().run()
