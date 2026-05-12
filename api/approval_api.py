"""
approval_api.py
Mining Guardian — Approval Webhook API

Listens for APPROVE/DENY callbacks from the Slack approval listener.
When the listener sees a reply in #mining-guardian, it calls this API
which processes the pending approvals and executes actions.

Runs on: http://localhost:8686
"""

import sys
import psycopg2
from psycopg2.extras import DictCursor

from core.db_targets import operational_target
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
from fastapi.responses import FileResponse, JSONResponse
import uvicorn

# ── Path setup — add core/ so mining_guardian imports work ───────────────────
_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT / "core"), str(_ROOT / "clients"), str(_ROOT / "monitoring")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logger = logging.getLogger("approval_api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def _pg_dsn() -> str:
    """Operational Postgres DSN via core.db_targets.

    W14a (2026-05-12): delegated to the resolver so this module stays
    on the operational instance after W14 splits catalog onto port
    5433. All tables this module touches (action_audit_log,
    miner_readings, scans, etc.) are operational.
    """
    return operational_target().dsn()


class _PgConnWrapper:
    """psycopg2 Connection wrapper with SQLite-style conn.execute shortcut.

    See core/overnight_automation.py for rationale (Phase 7.2).

    Important: the __exit__ method commits on clean exit, matching the
    SQLite `with sqlite3.connect(...) as conn:` semantics used throughout
    this file.
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


DB_PATH = _pg_dsn()
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
            with open(cfg_path) as f:
                cfg = json.load(f)
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
    conn = _PgConnWrapper(DB_PATH)
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
    Called by the Slack approval listener when operator replies APPROVE in Slack thread.
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

    with _PgConnWrapper(DB_PATH) as conn:
        pending = conn.execute(
            "SELECT * FROM pending_approvals WHERE thread_ts = %s AND status = 'PENDING'",
            (thread_ts,)
        ).fetchall()

        if not pending:
            return {"status": "no_pending", "message": "No pending approvals for this thread"}

        now = datetime.now().isoformat()
        results = []

        for row in pending:
            action = dict(row)
            miner_id = action["miner_id"]
            action_type = action["action_type"]

            # Mark as approved in DB
            conn.execute(
                "UPDATE pending_approvals SET status = 'APPROVED', responded_at = %s WHERE id = %s",
                (now, action["id"])
            )

            # Log to audit trail
            conn.execute("""
                INSERT INTO action_audit_log
                (timestamp, date, scan_id, miner_id, ip, model, problem, action_taken, decision, approved_by, slack_user_id, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (now, now[:10], action["scan_id"], miner_id, action["ip"],
                  action["model"], action["problem"], action_type,
                  "APPROVED", user, user_id, f"Approved via Slack thread {thread_ts}"))

            results.append({"miner_id": miner_id, "ip": action["ip"],
                            "action": action_type, "status": "APPROVED"})
            logger.info("APPROVED: %s for miner %s (%s) by %s",
                         action_type, action["ip"], action["model"], user)

        conn.commit()

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
    Called by the Slack approval listener when operator replies DENY in Slack thread.
    Expects JSON: {"thread_ts": "...", "user": "...", "user_id": "..."}
    """
    if not verify_internal(request):
        return Response(status_code=403, content="Forbidden")
    body = await request.json()
    thread_ts = body.get("thread_ts")
    user = body.get("user", "unknown")
    user_id = body.get("user_id", "")
    denial_reason = body.get("denial_reason", "")

    if not thread_ts:
        return {"error": "thread_ts required"}

    with _PgConnWrapper(DB_PATH) as conn:
        now = datetime.now().isoformat()

        pending = conn.execute(
            "SELECT * FROM pending_approvals WHERE thread_ts = %s AND status = 'PENDING'",
            (thread_ts,)
        ).fetchall()

        for row in pending:
            action = dict(row)
            conn.execute(
                "UPDATE pending_approvals SET status = 'DENIED', responded_at = %s WHERE id = %s",
                (now, action["id"])
            )
            conn.execute("""
                INSERT INTO action_audit_log
                (timestamp, date, scan_id, miner_id, ip, model, problem, action_taken, decision, approved_by, slack_user_id, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (now, now[:10], action["scan_id"], action["miner_id"], action["ip"],
                  action["model"], action["problem"], action["action_type"],
                  "DENIED", user, user_id, f"Denied via Slack thread {thread_ts}: {denial_reason}" if denial_reason else f"Denied via Slack thread {thread_ts}"))

        # DG-2 FIX: Extract rules from denial
        if denial_reason and len(denial_reason.strip()) > 10:
            try:
                from ai.knowledge_manager import KnowledgeManager
                km = KnowledgeManager()
                category = "general"
                dr_lower = denial_reason.lower()
                if "temp" in dr_lower or "heat" in dr_lower:
                    category = "temperature"
                elif "offline" in dr_lower:
                    category = "offline_logic"
                elif "restart" in dr_lower:
                    category = "restart_policy"
                elif "wait" in dr_lower or "time" in dr_lower:
                    category = "timing"
                if any(w in dr_lower for w in ["should", "must", "dont", "never", "always"]):
                    km.store_operator_rule(category, denial_reason, source="operator_denial")
            except Exception as e:
                logger.debug("Rule extraction failed: %s", e)

        conn.commit()
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

    with _PgConnWrapper(DB_PATH) as conn:
        all_pending = conn.execute(
            "SELECT * FROM pending_approvals WHERE thread_ts = %s AND status = 'PENDING'",
            (thread_ts,)
        ).fetchall()

        now = datetime.now().isoformat()
        approved, denied = [], []

        for row in all_pending:
            action = dict(row)
            if str(action["miner_id"]) in miner_ids:
                conn.execute(
                    "UPDATE pending_approvals SET status='APPROVED', responded_at=%s WHERE id=%s",
                    (now, action["id"])
                )
                conn.execute("""
                    INSERT INTO action_audit_log
                    (timestamp, date, scan_id, miner_id, ip, model, problem, action_taken,
                     decision, approved_by, slack_user_id, notes)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (now, now[:10], action["scan_id"], action["miner_id"], action["ip"],
                      action["model"], action["problem"], action["action_type"],
                      "APPROVED", user, user_id, f"Selectively approved via Slack thread {thread_ts}"))
                approved.append({"miner_id": action["miner_id"], "ip": action["ip"],
                                 "action": action["action_type"]})
            else:
                # Not selected — mark as denied
                conn.execute(
                    "UPDATE pending_approvals SET status='DENIED', responded_at=%s WHERE id=%s",
                    (now, action["id"])
                )
                conn.execute("""
                    INSERT INTO action_audit_log
                    (timestamp, date, scan_id, miner_id, ip, model, problem, action_taken,
                     decision, approved_by, slack_user_id, notes)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (now, now[:10], action["scan_id"], action["miner_id"], action["ip"],
                      action["model"], action["problem"], action["action_type"],
                      "DENIED", user, user_id, f"Skipped in selective approval for thread {thread_ts}"))
                denied.append({"miner_id": action["miner_id"], "ip": action["ip"]})

        conn.commit()

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

    with _PgConnWrapper(DB_PATH) as conn:
        try:
            existing = conn.execute(
                "SELECT id FROM pending_approvals WHERE miner_id=%s AND status='PENDING'",
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
                "VALUES (%s, %s, %s, %s, %s, %s, 'PENDING')",
                (now_iso, '', miner_id, ip, action, problem_text)
            )
            conn.commit()

            conn.execute(
                "INSERT INTO action_audit_log (timestamp, date, miner_id, ip, problem, action_taken, decision, approved_by, notes) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'PENDING_URGENT', 'system', %s)",
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
    with _PgConnWrapper(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT * FROM pending_approvals WHERE status = 'PENDING' ORDER BY created_at DESC"
        ).fetchall()
    # Convert datetime fields to ISO strings so JSON serialization is clean for the GUI.
    out = []
    for r in rows:
        row = dict(r)
        for k in ("created_at", "responded_at"):
            if k in row and row[k] is not None and not isinstance(row[k], str):
                row[k] = row[k].isoformat()
        out.append(row)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Bucket 9 §10.1/§10.2 — Web GUI endpoints served from approval_api.py:8686.
#
# Three additions:
#   1. `/ui` — serves api/static/approval_ui.html (single-page operator console)
#   2. `/mode` GET/POST — read and set the global automation_mode setting
#   3. `/gui/approve` and `/gui/deny` — per-miner approve/deny with explanation,
#      consumed by the Web GUI. Mirror the Slack listener endpoints but accept
#      a miner_id scope instead of only thread_ts, and capture the operator's
#      free-form explanation in the audit log.
#
# Auth: all GUI endpoints require X-Internal-Secret. The HTML page itself does
# NOT require auth — it's just a static file — but the browser-side JS sets the
# header from localStorage (`mg_internal_secret`). The operator sets this once
# per browser from devtools console before first use.
# ─────────────────────────────────────────────────────────────────────────────

_STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/ui")
async def web_gui():
    """Serve the single-page operator console HTML."""
    ui_path = _STATIC_DIR / "approval_ui.html"
    if not ui_path.exists():
        return Response(status_code=500,
                        content=f"approval_ui.html missing at {ui_path}")
    return FileResponse(str(ui_path), media_type="text/html")


@app.get("/mode")
async def get_mode(request: Request):
    """Return the current automation_mode record for the Web GUI.
    Response shape: {"key", "value", "updated_at", "updated_by"}."""
    if not verify_internal(request):
        return Response(status_code=403, content="Forbidden")
    try:
        from system_settings import get_setting_record, DEFAULT_AUTOMATION_MODE
    except ImportError:
        from api.system_settings import get_setting_record, DEFAULT_AUTOMATION_MODE  # type: ignore
    rec = get_setting_record("automation_mode")
    if rec is None:
        # Never surface an error here — default to FULL_AUTO so the GUI is usable
        # even before the migration has been applied. The UI shows which mode is
        # in effect right now; `updated_by='system'` signals this is the default.
        return JSONResponse({
            "key": "automation_mode",
            "value": DEFAULT_AUTOMATION_MODE,
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "updated_by": "system",
        })
    if rec.get("updated_at") is not None and not isinstance(rec["updated_at"], str):
        rec["updated_at"] = rec["updated_at"].isoformat()
    return rec


@app.post("/mode")
async def set_mode(request: Request):
    """Set the automation_mode. Body: {"mode": "FULL_AUTO|SEMI_AUTO|MANUAL", "operator": "bobby"}."""
    if not verify_internal(request):
        return Response(status_code=403, content="Forbidden")
    try:
        from system_settings import (
            set_automation_mode, get_setting_record, ALLOWED_AUTOMATION_MODES,
        )
    except ImportError:
        from api.system_settings import (  # type: ignore
            set_automation_mode, get_setting_record, ALLOWED_AUTOMATION_MODES,
        )
    body = await request.json()
    mode = body.get("mode", "")
    operator = body.get("operator", "web_gui")
    if mode not in ALLOWED_AUTOMATION_MODES:
        return JSONResponse(
            status_code=400,
            content={"error": f"mode must be one of {sorted(ALLOWED_AUTOMATION_MODES)}"},
        )
    ok = set_automation_mode(mode, updated_by=f"web_gui:{operator}")
    if not ok:
        return JSONResponse(status_code=500, content={"error": "database write failed"})
    rec = get_setting_record("automation_mode") or {
        "key": "automation_mode", "value": mode,
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "updated_by": f"web_gui:{operator}",
    }
    if rec.get("updated_at") is not None and not isinstance(rec["updated_at"], str):
        rec["updated_at"] = rec["updated_at"].isoformat()
    logger.info("Automation mode set to %s by %s", mode, operator)
    return rec


def _gui_find_pending(conn, miner_id: str, thread_ts: str):
    """Find PENDING approvals for a given miner (preferred) or thread_ts.
    The Web GUI passes miner_id from the per-row card; thread_ts is optional
    fallback for compatibility."""
    if miner_id:
        return conn.execute(
            "SELECT * FROM pending_approvals WHERE miner_id = %s AND status = 'PENDING'",
            (miner_id,),
        ).fetchall()
    if thread_ts:
        return conn.execute(
            "SELECT * FROM pending_approvals WHERE thread_ts = %s AND status = 'PENDING'",
            (thread_ts,),
        ).fetchall()
    return []


@app.post("/gui/approve")
async def gui_approve(request: Request):
    """Per-miner approve from the Web GUI.
    Body: {"miner_id": "...", "user": "...", "user_id": "web_gui", "explanation": "..."}
    """
    if not verify_internal(request):
        return Response(status_code=403, content="Forbidden")
    body = await request.json()
    miner_id   = body.get("miner_id", "")
    thread_ts  = body.get("thread_ts", "") or ""
    user       = body.get("user", "web_gui")
    user_id    = body.get("user_id", "web_gui")
    explanation = (body.get("explanation") or "").strip()

    if not miner_id and not thread_ts:
        return JSONResponse(status_code=400, content={"error": "miner_id or thread_ts required"})

    with _PgConnWrapper(DB_PATH) as conn:
        pending = _gui_find_pending(conn, miner_id, thread_ts)
        if not pending:
            return {"status": "no_pending", "message": "No pending approvals for that miner"}

        now = datetime.now().isoformat()
        results = []
        for row in pending:
            action = dict(row)
            conn.execute(
                "UPDATE pending_approvals SET status = 'APPROVED', responded_at = %s WHERE id = %s",
                (now, action["id"]),
            )
            note = f"Approved via Web GUI by {user}"
            if explanation:
                note += f": {explanation}"
            conn.execute("""
                INSERT INTO action_audit_log
                (timestamp, date, scan_id, miner_id, ip, model, problem, action_taken, decision, approved_by, slack_user_id, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (now, now[:10], action.get("scan_id"), action["miner_id"], action["ip"],
                  action.get("model"), action["problem"], action["action_type"],
                  "APPROVED", user, user_id, note))
            results.append({
                "miner_id": action["miner_id"], "ip": action["ip"],
                "action": action["action_type"], "status": "APPROVED",
            })
            logger.info("APPROVED via Web GUI: %s for miner %s (%s) by %s — explanation=%r",
                        action["action_type"], action["ip"], action.get("model"),
                        user, explanation)
        conn.commit()

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
        logger.error("Error executing Web GUI approved actions: %s", e)
        return {"status": "approved_with_errors", "results": results, "error": str(e), "count": len(results)}

    return {"status": "approved", "count": len(results), "results": results}


@app.post("/gui/deny")
async def gui_deny(request: Request):
    """Per-miner deny from the Web GUI.
    Body: {"miner_id": "...", "user": "...", "user_id": "web_gui", "explanation": "..."}
    The explanation is stored verbatim in the audit log and, when long enough,
    passed through the same knowledge-manager extraction the Slack /deny path uses.
    """
    if not verify_internal(request):
        return Response(status_code=403, content="Forbidden")
    body = await request.json()
    miner_id    = body.get("miner_id", "")
    thread_ts   = body.get("thread_ts", "") or ""
    user        = body.get("user", "web_gui")
    user_id     = body.get("user_id", "web_gui")
    explanation = (body.get("explanation") or "").strip()

    if not miner_id and not thread_ts:
        return JSONResponse(status_code=400, content={"error": "miner_id or thread_ts required"})

    with _PgConnWrapper(DB_PATH) as conn:
        now = datetime.now().isoformat()
        pending = _gui_find_pending(conn, miner_id, thread_ts)
        denied = 0
        for row in pending:
            action = dict(row)
            conn.execute(
                "UPDATE pending_approvals SET status = 'DENIED', responded_at = %s WHERE id = %s",
                (now, action["id"]),
            )
            note = f"Denied via Web GUI by {user}"
            if explanation:
                note += f": {explanation}"
            conn.execute("""
                INSERT INTO action_audit_log
                (timestamp, date, scan_id, miner_id, ip, model, problem, action_taken, decision, approved_by, slack_user_id, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (now, now[:10], action.get("scan_id"), action["miner_id"], action["ip"],
                  action.get("model"), action["problem"], action["action_type"],
                  "DENIED", user, user_id, note))
            denied += 1
            logger.info("DENIED via Web GUI: %s for miner %s (%s) by %s — explanation=%r",
                        action["action_type"], action["ip"], action.get("model"),
                        user, explanation)
        conn.commit()

        # Mirror the Slack /deny path (DG-2 FIX): when the explanation is
        # substantive, feed it to the KnowledgeManager so future decisions
        # learn from it. Same classifier heuristics as the /deny endpoint.
        if explanation and len(explanation) > 10:
            try:
                from ai.knowledge_manager import KnowledgeManager
                km = KnowledgeManager()
                category = "general"
                dr_lower = explanation.lower()
                if "temp" in dr_lower or "heat" in dr_lower:
                    category = "temperature"
                elif "offline" in dr_lower:
                    category = "offline_logic"
                elif "restart" in dr_lower:
                    category = "restart_policy"
                elif "wait" in dr_lower or "time" in dr_lower:
                    category = "timing"
                if any(w in dr_lower for w in ["should", "must", "dont", "never", "always"]):
                    km.store_operator_rule(category, explanation, source="operator_denial_web_gui")
            except Exception as e:
                # Non-fatal — the denial itself has already been recorded.
                logger.debug("Rule extraction failed: %s", e)

    return {"status": "denied", "count": denied}


# ── Bucket 9 §10.7 — schedule endpoints ────────────────────────────────────
# All in-process daemons hot-reload from `system_schedules` so changes
# made via these endpoints take effect within one daemon cycle without
# requiring `launchctl kickstart`.

@app.get("/schedules")
def list_schedules_endpoint(request: Request):
    """Return all schedule rows so the GUI can render them."""
    if not verify_internal(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from api.system_schedules import list_schedules
        return {"schedules": list_schedules()}
    except Exception as e:
        logger.error("list_schedules failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/schedules/{job_key}")
async def update_schedule_endpoint(job_key: str, request: Request):
    """UPSERT a schedule row. Body: {enabled, schedule_type, start_hour,
    start_minute, end_hour, end_minute, interval_seconds, days_of_week}.
    """
    if not verify_internal(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    operator = body.get("operator", "unknown")

    try:
        from api.system_schedules import update_schedule
        row = update_schedule(job_key, body, operator)
        return {"status": "updated", "job_key": job_key, "schedule": row}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        logger.error("update_schedule(%s) failed: %s", job_key, e)
        return JSONResponse({"error": str(e)}, status_code=500)


if __name__ == "__main__":
    print("Mining Guardian Approval API — http://localhost:8686")
    print("Web GUI operator console: http://localhost:8686/ui")
    uvicorn.run(app, host="127.0.0.1", port=8686)
