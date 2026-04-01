"""
approval_api.py
Mining Guardian — Approval Webhook API

Listens for APPROVE/DENY callbacks from OpenClaw.
When OpenClaw sees a reply in #mining-guardian, it calls this API
which processes the pending approvals and executes actions.

Runs on: http://localhost:8686
"""

import sqlite3
import json
import logging
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

logger = logging.getLogger("approval_api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DB_PATH = "guardian.db"
app = FastAPI(title="Mining Guardian Approval API", version="1.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.post("/approve")
async def approve_actions(request: Request):
    """
    Called by OpenClaw when operator replies APPROVE in Slack thread.
    Expects JSON: {"thread_ts": "...", "user": "...", "user_id": "..."}
    """
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
        logger.info("APPROVED: %s %s for miner %s (%s) by %s",
                     action_type, miner_id, action["ip"], user)

    conn.commit()
    conn.close()

    # Execute the approved actions via AMS
    try:
        import mining_guardian
        cfg = json.load(open("config.json"))
        g = mining_guardian.MiningGuardian(
            mining_guardian.GuardianConfig(**{
                k: v for k, v in cfg.items()
                if k in mining_guardian.GuardianConfig.__dataclass_fields__
            })
        )
        for r in results:
            issue = {"id": r["miner_id"], "ip": r["ip"], "model": ""}
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


@app.get("/pending")
async def list_pending():
    """List all pending approvals."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM pending_approvals WHERE status = 'PENDING' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    print("Mining Guardian Approval API — http://localhost:8686")
    uvicorn.run(app, host="0.0.0.0", port=8686)
