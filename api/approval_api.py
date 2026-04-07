"""
approval_api.py
Mining Guardian — Approval Webhook API

Listens for APPROVE/DENY callbacks from OpenClaw.
When OpenClaw sees a reply in #mining-guardian, it calls this API
which processes the pending approvals and executes actions.

Runs on: http://localhost:8686
"""

import sys
import sqlite3
import json
import logging
import hashlib
import hmac
import time
import os
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ── Path setup — add core/ so mining_guardian imports work ───────────────────
_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT / "core"), str(_ROOT / "clients"), str(_ROOT / "monitoring")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logger = logging.getLogger("approval_api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DB_PATH = str(_ROOT / "guardian.db")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")
INTERNAL_API_SECRET  = os.environ.get("INTERNAL_API_SECRET", "")

# Pre-load a single MiningGuardian instance at startup so AMS auth is
# established once and reused for every approval — avoids repeated
# select_workspace calls that intermittently return 400.
_guardian = None
def get_guardian():
    global _guardian
    if _guardian is None:
        try:
            import mining_guardian as mg
            cfg_path = _ROOT / "config" / "config.json"
            if not cfg_path.exists():
                cfg_path = _ROOT / "config.json"
            cfg = json.load(open(cfg_path))
            _guardian = mg.MiningGuardian(
                mg.GuardianConfig(**{
                    k: v for k, v in cfg.items()
                    if k in mg.GuardianConfig.__dataclass_fields__
                })
            )
            logger.info("MiningGuardian instance initialized for approval_api")
        except Exception as e:
            logger.error("Failed to init MiningGuardian: %s", e)
    return _guardian

# Warn loudly if Slack signature secret missing — /slack/actions endpoint will
# reject all requests without it, but the internal endpoints still work.
if not SLACK_SIGNING_SECRET:
    logger.warning("SLACK_SIGNING_SECRET not set — /slack/actions will reject all requests")

if not INTERNAL_API_SECRET:
    logger.warning(
        "INTERNAL_API_SECRET not set — /approve /deny /approve_selected are unauthenticated. "
        "Set this in .env to prevent unauthorized hardware actuation."
    )

app = FastAPI(title="Mining Guardian Approval API", version="1.0.0")

# Restrict CORS to known consumers only — not wildcard
app.add_middleware(CORSMiddleware,
                   allow_origins=["https://slack.fieslerfamily.com",
                                   "https://dashboard.fieslerfamily.com",
                                   "http://localhost:8585",
                                   "http://127.0.0.1:8585"],
                   allow_methods=["POST", "GET"],
                   allow_headers=["*"])


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def verify_internal(request: Request) -> bool:
    """Check X-Internal-Secret header on internal action endpoints.

    Internal callers (slack_approval_listener, overnight_automation) must
    send this header. If INTERNAL_API_SECRET is not configured, all internal
    requests are accepted (backward compatible with existing deployments).
    """
    if not INTERNAL_API_SECRET:
        logger.warning("INTERNAL_API_SECRET not set — rejecting (fail closed)"); return False
    provided = request.headers.get("X-Internal-Secret", "")
    return hmac.compare_digest(provided, INTERNAL_API_SECRET)


@app.post("/approve")
async def approve_actions(request: Request):
    """
    Called by OpenClaw when operator replies APPROVE in Slack thread.
    Expects JSON: {"thread_ts": "...", "user": "...", "user_id": "..."}
    """
    if not verify_internal(request):
        return Response(status_code=403, content="Forbidden")
    body = await request.json()
    thread_ts = body.get("thread_ts")
    user = body.get("user", "unknown")
    user_id = body.get("user_id", "")

    if not thread_ts:
        return {"error": "thread_ts required"}

    conn = get_db()
    pending = conn.execute(
        "SELECT * FROM pending_approvals WHERE thread_ts = ? AND status = 'PENDING'",
        (thread_ts,)
    ).fetchall()

    if not pending:
        conn.close()
        return {"status": "no_pending", "message": "No pending approvals for this thread"}

    now = datetime.now().isoformat()
    results = []

    for row in pending:
        action = dict(row)
        miner_id = action["miner_id"]
        action_type = action["action_type"]

        # Mark as approved in DB
        conn.execute(
            "UPDATE pending_approvals SET status = 'APPROVED', responded_at = ? WHERE id = ?",
            (now, action["id"])
        )

        # Log to audit trail
        conn.execute("""
            INSERT INTO action_audit_log
            (timestamp, date, scan_id, miner_id, ip, model, problem, action_taken, decision, approved_by, slack_user_id, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (now, now[:10], action["scan_id"], miner_id, action["ip"],
              action["model"], action["problem"], action_type,
              "APPROVED", user, user_id, f"Approved via Slack thread {thread_ts}"))

        results.append({"miner_id": miner_id, "ip": action["ip"],
                        "action": action_type, "status": "APPROVED"})
        logger.info("APPROVED: %s for miner %s (%s) by %s",
                     action_type, action["ip"], action["model"], user)

    conn.commit()
    conn.close()

    # Execute the approved actions using the persistent guardian instance
    try:
        g = get_guardian()
        if g is None:
            raise RuntimeError("MiningGuardian failed to initialize — check config.json and AMS credentials")
        for r in results:
            issue = {"id": r["miner_id"], "ip": r["ip"], "model": r.get("model", "")}
            if r["action"] == "RESTART":
                g.execute_restart(issue)
            elif r["action"] == "PDU_CYCLE":
                g.execute_pdu_cycle(issue)
            elif r["action"] == "RESTART_CHECK_BOARDS":
                g.execute_board_restart(issue)
    except Exception as e:
        logger.error("Error executing approved actions: %s", e)
        return {"status": "approved_with_errors", "results": results, "error": str(e)}

    return {"status": "approved", "count": len(results), "results": results}


@app.post("/deny")
async def deny_actions(request: Request):
    """
    Called by OpenClaw when operator replies DENY in Slack thread.
    Expects JSON: {"thread_ts": "...", "user": "...", "user_id": "..."}
    """
    if not verify_internal(request):
        return Response(status_code=403, content="Forbidden")
    body = await request.json()
    thread_ts = body.get("thread_ts")
    user = body.get("user", "unknown")
    user_id = body.get("user_id", "")

    if not thread_ts:
        return {"error": "thread_ts required"}

    conn = get_db()
    now = datetime.now().isoformat()

    pending = conn.execute(
        "SELECT * FROM pending_approvals WHERE thread_ts = ? AND status = 'PENDING'",
        (thread_ts,)
    ).fetchall()

    for row in pending:
        action = dict(row)
        conn.execute(
            "UPDATE pending_approvals SET status = 'DENIED', responded_at = ? WHERE id = ?",
            (now, action["id"])
        )
        conn.execute("""
            INSERT INTO action_audit_log
            (timestamp, date, scan_id, miner_id, ip, model, problem, action_taken, decision, approved_by, slack_user_id, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (now, now[:10], action["scan_id"], action["miner_id"], action["ip"],
              action["model"], action["problem"], action["action_type"],
              "DENIED", user, user_id, f"Denied via Slack thread {thread_ts}"))

    conn.commit()
    conn.close()
    logger.info("DENIED: %d actions for thread %s by %s", len(pending), thread_ts, user)
    return {"status": "denied", "count": len(pending)}


@app.post("/approve_selected")
async def approve_selected_actions(request: Request):
    """
    Called when operator clicks 'Approve Selected' in the Block Kit UI.
    Expects JSON: {"thread_ts": "...", "miner_ids": ["53476", "53477"],
                   "user": "...", "user_id": "..."}
    Only approves the miners in miner_ids — others remain PENDING (effectively denied).
    """
    if not verify_internal(request):
        return Response(status_code=403, content="Forbidden")
    body = await request.json()
    thread_ts  = body.get("thread_ts")
    miner_ids  = [str(m) for m in body.get("miner_ids", [])]
    user       = body.get("user", "unknown")
    user_id    = body.get("user_id", "")

    if not thread_ts:
        return {"error": "thread_ts required"}

    conn = get_db()
    all_pending = conn.execute(
        "SELECT * FROM pending_approvals WHERE thread_ts = ? AND status = 'PENDING'",
        (thread_ts,)
    ).fetchall()

    now = datetime.now().isoformat()
    approved, denied = [], []

    for row in all_pending:
        action = dict(row)
        if str(action["miner_id"]) in miner_ids:
            conn.execute(
                "UPDATE pending_approvals SET status='APPROVED', responded_at=? WHERE id=?",
                (now, action["id"])
            )
            conn.execute("""
                INSERT INTO action_audit_log
                (timestamp, date, scan_id, miner_id, ip, model, problem, action_taken,
                 decision, approved_by, slack_user_id, notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (now, now[:10], action["scan_id"], action["miner_id"], action["ip"],
                  action["model"], action["problem"], action["action_type"],
                  "APPROVED", user, user_id, f"Selectively approved via Slack thread {thread_ts}"))
            approved.append({"miner_id": action["miner_id"], "ip": action["ip"],
                             "action": action["action_type"]})
        else:
            # Not selected — mark as denied
            conn.execute(
                "UPDATE pending_approvals SET status='DENIED', responded_at=? WHERE id=?",
                (now, action["id"])
            )
            conn.execute("""
                INSERT INTO action_audit_log
                (timestamp, date, scan_id, miner_id, ip, model, problem, action_taken,
                 decision, approved_by, slack_user_id, notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (now, now[:10], action["scan_id"], action["miner_id"], action["ip"],
                  action["model"], action["problem"], action["action_type"],
                  "DENIED", user, user_id, f"Skipped in selective approval for thread {thread_ts}"))
            denied.append({"miner_id": action["miner_id"], "ip": action["ip"]})

    conn.commit()
    conn.close()

    # Execute only the approved ones
    if approved:
        try:
            g = get_guardian()
            if g is None:
                raise RuntimeError("MiningGuardian singleton unavailable")
            for r in approved:
                issue = {"id": r["miner_id"], "ip": r["ip"], "model": ""}
                if r["action"] == "RESTART":
                    g.execute_restart(issue)
                elif r["action"] == "PDU_CYCLE":
                    g.execute_pdu_cycle(issue)
                elif r["action"] == "RESTART_CHECK_BOARDS":
                    g.execute_board_restart(issue)
        except Exception as e:
            logger.error("Error executing selected approvals: %s", e)
            return {"status": "approved_with_errors", "approved": approved,
                    "denied": denied, "error": str(e)}

    logger.info("Selective approve by %s — %d approved, %d skipped (thread %s)",
                user, len(approved), len(denied), thread_ts)
    return {"status": "ok", "approved_count": len(approved),
            "denied_count": len(denied), "approved": approved, "denied": denied}



@app.post("/internal/urgent_action")
async def urgent_action(request: Request):
    """Called by ams_alert_listener when an urgent issue needs immediate action.

    These actions skip normal scan-cycle queueing because something is happening
    RIGHT NOW (miner offline, severe hashrate drop). Inserts into pending_approvals
    so the main daemon picks them up on its next loop iteration, OR overnight
    automation executes them directly during quiet hours.

    Expects JSON: {miner_id, ip, action, source, notification_id, urgent}
    """
    if not verify_internal(request):
        return Response(status_code=403, content="Forbidden")

    body = await request.json()
    miner_id = str(body.get("miner_id", ""))
    ip = body.get("ip", "")
    action = body.get("action", "")
    source = body.get("source", "unknown")
    notif_id = body.get("notification_id")

    if not miner_id or not action:
        return {"status": "error", "reason": "miner_id and action required"}

    ALLOWED = {"RESTART", "PDU_CYCLE", "RESTART_CHECK_BOARDS"}
    if action not in ALLOWED:
        return {"status": "error", "reason": f"action must be one of {ALLOWED}"}

    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT id FROM pending_approvals WHERE miner_id=? AND status='pending'",
            (miner_id,)
        ).fetchone()
        if existing:
            return {"status": "already_pending", "miner_id": miner_id}

        from datetime import datetime as _dt
        now = _dt.utcnow()
        now_iso = now.isoformat()
        today = now.strftime("%Y-%m-%d")
        problem_text = f"URGENT alert from {source} (notification_id={notif_id})"

        # thread_ts is set by the main daemon when it posts to Slack — use placeholder for now
        conn.execute(
            "INSERT INTO pending_approvals (created_at, thread_ts, miner_id, ip, action_type, problem, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'PENDING')",
            (now_iso, '', miner_id, ip, action, problem_text)
        )
        conn.commit()

        conn.execute(
            "INSERT INTO action_audit_log (timestamp, date, miner_id, ip, problem, action_taken, decision, approved_by, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, 'PENDING_URGENT', 'system', ?)",
            (now_iso, today, miner_id, ip, problem_text, action,
             f"Urgent action queued by {source}, notification_id={notif_id}")
        )
        conn.commit()

        logger.info("Urgent action queued: miner=%s ip=%s action=%s source=%s",
                    miner_id, ip, action, source)
        return {"status": "queued", "miner_id": miner_id, "action": action}
    except Exception as e:
        logger.exception("urgent_action failed: %s", e)
        return {"status": "error", "reason": str(e)}
    finally:
        conn.close()


@app.post("/slack/actions")
async def slack_interactive(request: Request):
    """
    Receives interactive Block Kit payloads from Slack (button clicks).
    Publicly routed via Cloudflare tunnel: slack.fieslerfamily.com/slack/actions
    Must respond within 3 seconds — dispatches to background thread.
    """
    body_bytes = await request.body()
    body_str   = body_bytes.decode("utf-8")

    # Verify Slack signature — required when SLACK_SIGNING_SECRET is configured
    if not SLACK_SIGNING_SECRET:
        logger.warning("SLACK_SIGNING_SECRET not set — rejecting /slack/actions request")
        return Response(status_code=403)

    ts  = request.headers.get("X-Slack-Request-Timestamp", "")
    sig = request.headers.get("X-Slack-Signature", "")

    # Replay attack protection — reject requests older than 5 minutes
    try:
        if abs(time.time() - int(ts)) > 300:
            logger.warning("Slack request timestamp too old — possible replay attack")
            return Response(status_code=403)
    except (ValueError, TypeError):
        return Response(status_code=403)

    base     = f"v0:{ts}:{body_str}"
    expected = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode(), base.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, sig):
        logger.warning("Invalid Slack signature on /slack/actions")
        return Response(status_code=403)

    from urllib.parse import parse_qs
    parsed      = parse_qs(body_str)
    payload_str = parsed.get("payload", ["{}"])[0]
    payload     = json.loads(payload_str)

    import threading
    def dispatch():
        try:
            from slack_approval_listener import ApprovalListener
            ApprovalListener().handle_block_action(payload)
        except Exception as e:
            logger.error("Block action dispatch error: %s", e)

    threading.Thread(target=dispatch, daemon=True).start()
    return Response(status_code=200)


@app.get("/pending")
async def list_pending(request: Request):
    """List all pending approvals."""
    if not verify_internal(request):
        return Response(status_code=403, content="Forbidden")
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM pending_approvals WHERE status = 'PENDING' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    print("Mining Guardian Approval API — http://localhost:8686")
    uvicorn.run(app, host="127.0.0.1", port=8686)
