"""
overnight_automation.py
Mining Guardian — Autonomous Overnight Action Engine

Runs as a service. During the defined overnight window (default 10pm–6am),
automatically executes LOW-RISK actions without operator approval.

Risk levels:
  AUTO  — executes immediately: firmware restart (first attempt), PDU cycle (first attempt)
  HOLD  — skips overnight: repeated restarts, miners with recent failures
  MANUAL — never auto: dead board restart, physical cycle, no PDU assigned

Every action is logged to the audit trail with decision='AUTO_OVERNIGHT'.
Morning briefing picks up these entries and summarizes what happened.

OpenClaw integration: Posts an overnight summary via the webhook so the LLM
can provide a narrative summary to Slack when the window closes.
"""

import sys
import os
import json
import time
import logging
import sqlite3
import requests
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# ── Path setup ────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT / "core"), str(_ROOT / "clients"), str(_ROOT / "monitoring")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

load_dotenv()
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("overnight")

DB_PATH          = str(_ROOT / "guardian.db")
APPROVAL_API     = "http://localhost:8686"
OPENCLAW_WEBHOOK = os.getenv("OPENCLAW_WEBHOOK_URL", "http://localhost:18789/hooks")
OPENCLAW_TOKEN   = os.getenv("OPENCLAW_TOKEN", "")

# ── Overnight window (24h clock) ──────────────────────────────────────────────
# Set to 0 / 24 to run ALL DAY — full autonomous mode
WINDOW_START_HOUR = 0    # midnight (start of day)
WINDOW_END_HOUR   = 24   # end of day — effectively always active

# ── How many times a miner can be auto-restarted in one overnight window ──────
MAX_AUTO_RESTARTS_PER_NIGHT = 2  # increased from 1 for full-day mode


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def is_overnight_window() -> bool:
    """Returns True if current time is inside the automation window.
    When WINDOW_END_HOUR=24, always returns True (full-day autonomous mode).
    """
    if WINDOW_END_HOUR >= 24:
        return True  # full-day mode
    hour = datetime.now().hour
    if WINDOW_START_HOUR > WINDOW_END_HOUR:
        # Spans midnight: e.g. 22 → 6
        return hour >= WINDOW_START_HOUR or hour < WINDOW_END_HOUR
    else:
        return WINDOW_START_HOUR <= hour < WINDOW_END_HOUR


def get_pending_actions() -> list:
    """Get all PENDING approvals that haven't been touched yet."""
    conn = get_db()
    rows = conn.execute("""
        SELECT p.*, r.temp_chip, r.hashrate_pct, r.firmware_manufacturer,
               r.current_profile, r.map_location
        FROM pending_approvals p
        LEFT JOIN miner_readings r ON p.miner_id = r.miner_id
            AND r.id = (SELECT MAX(id) FROM miner_readings WHERE miner_id = p.miner_id)
        WHERE p.status = 'PENDING'
        ORDER BY p.created_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_restart_count_tonight(miner_id: str) -> int:
    """How many times has this miner been auto-restarted since the window opened."""
    now = datetime.now()
    if now.hour < WINDOW_END_HOUR:
        window_start = now.replace(hour=WINDOW_START_HOUR, minute=0,
                                   second=0) - timedelta(days=1)
    else:
        window_start = now.replace(hour=WINDOW_START_HOUR, minute=0, second=0)

    conn = get_db()
    # Bug fix: overnight actions are logged with decision='AUTO_OVERNIGHT',
    # not 'APPROVED'. Match what execute_auto_action actually writes.
    row = conn.execute("""
        SELECT COUNT(*) as cnt FROM action_audit_log
        WHERE miner_id=?
          AND approved_by='Mining Guardian (Overnight Auto)'
          AND decision='AUTO_OVERNIGHT'
          AND action_taken IN ('RESTART', 'PDU_CYCLE')
          AND timestamp >= ?
    """, (miner_id, window_start.isoformat())).fetchone()
    conn.close()
    return row["cnt"] if row else 0


def has_recent_failure(miner_id: str, hours: int = 6) -> bool:
    """
    True if this miner should be blocked from auto-restart.
    Checks both:
    1. outcome=FAILURE in miner_restarts (Feature 1 outcome feedback)
    2. Multiple consecutive failures — if 3+ FAILURE outcomes, block permanently
       until a human reviews it
    """
    conn = get_db()

    # Primary check: outcome-labeled failures from Feature 1
    failures = conn.execute("""
        SELECT COUNT(*) as cnt FROM miner_restarts
        WHERE miner_id=? AND outcome='FAILURE'
    """, (miner_id,)).fetchone()
    failure_count = failures["cnt"] if failures else 0

    # If 3+ labeled failures — hard block, don't auto-restart
    if failure_count >= 3:
        logger.info(
            "Auto-restart blocked for %s — %d FAILURE outcomes recorded",
            miner_id, failure_count
        )
        conn.close()
        return True

    # Secondary check: recent failure within the time window
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    recent = conn.execute("""
        SELECT COUNT(*) as cnt FROM miner_restarts
        WHERE miner_id=? AND outcome='FAILURE' AND restarted_at >= ?
    """, (miner_id, cutoff)).fetchone()
    conn.close()
    return (recent["cnt"] if recent else 0) > 0


def classify_risk(action: dict) -> str:
    """
    Classify an action as AUTO, HOLD, or MANUAL.

    AUTO   — safe to execute overnight without approval
    HOLD   — skip for now, flag for morning review
    MANUAL — always requires human, never auto
    """
    action_type = action.get("action_type", "")
    miner_id    = str(action.get("miner_id", ""))

    # Dead board restarts and physical cycles — always manual
    if action_type in ("RESTART_CHECK_BOARDS", "PHYSICAL_CYCLE"):
        return "MANUAL"

    # No PDU info for a PDU_CYCLE means we can't do it
    if action_type == "PDU_CYCLE" and not action.get("pdu_id"):
        return "MANUAL"

    # Already auto-restarted this miner tonight
    if get_restart_count_tonight(miner_id) >= MAX_AUTO_RESTARTS_PER_NIGHT:
        return "HOLD"

    # Recent failure — back off
    if has_recent_failure(miner_id):
        return "HOLD"

    # RESTART and PDU_CYCLE first attempts are AUTO
    if action_type in ("RESTART", "PDU_CYCLE"):
        return "AUTO"

    return "HOLD"


def execute_auto_action(action: dict) -> dict:
    """Execute an AUTO action directly via AMS — bypasses approval API to avoid
    creating spurious DENIED entries for other miners in the same thread."""
    try:
        import mining_guardian
        cfg_path = _ROOT / "config" / "config.json"
        if not cfg_path.exists():
            cfg_path = _ROOT / "config.json"
        cfg = json.load(open(cfg_path))
        g = mining_guardian.MiningGuardian(
            mining_guardian.GuardianConfig(**{
                k: v for k, v in cfg.items()
                if k in mining_guardian.GuardianConfig.__dataclass_fields__
            })
        )
        issue = {
            "id":    action["miner_id"],
            "ip":    action["ip"],
            "model": action.get("model", ""),
            # Bug fix: pass PDU metadata so execute_pdu_cycle doesn't
            # silently no-op due to missing pdu_id/outlet fields
            "pdu_id":  action.get("pdu_id"),
            "outlet":  action.get("outlet"),
        }
        success = False
        if action["action_type"] == "RESTART":
            g.execute_restart(issue)
            success = True
        elif action["action_type"] == "PDU_CYCLE":
            if not action.get("pdu_id") or not action.get("outlet"):
                raise ValueError(
                    f"PDU_CYCLE missing pdu_id/outlet for miner {action['miner_id']}"
                )
            g.execute_pdu_cycle(issue)
            success = True

        # Only log to audit trail if the action actually executed
        if success:
            now = datetime.now()

            # Record in miner_restarts so the escalation counter works —
            # without this, get_failed_restart_count() never sees overnight
            # restarts and miners never escalate to tickets
            g.db.record_restart(
                action["miner_id"], action["ip"], action.get("model", ""),
                restart_type=f"AUTO_OVERNIGHT_{action['action_type']}",
                hashrate_before=float(action.get("hashrate_pct") or 0)
            )
            conn = get_db()
            conn.execute("""
                INSERT INTO action_audit_log
                (timestamp, date, scan_id, miner_id, ip, model, problem,
                 action_taken, decision, approved_by, slack_user_id, notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (now.isoformat(), now.strftime("%Y-%m-%d"), action.get("scan_id"),
                  action["miner_id"], action["ip"], action.get("model"),
                  action.get("problem"), action["action_type"],
                  "AUTO_OVERNIGHT", "Mining Guardian (Overnight Auto)", "AUTO_OVERNIGHT",
                  "Auto-executed during overnight window"))
            conn.execute(
                "UPDATE pending_approvals SET status='APPROVED', responded_at=? WHERE id=?",
                (now.isoformat(), action["id"])
            )
            conn.commit()
            conn.close()

        logger.info("AUTO executed: %s for miner %s (%s)",
                    action["action_type"], action["miner_id"], action["ip"])
        return {"status": "executed"}
    except Exception as e:
        logger.error("AUTO execution failed for miner %s: %s", action["miner_id"], e)
        return {"status": "failed", "error": str(e)}


def log_skip(action: dict, reason: str) -> None:
    """Log a HOLD decision once per overnight window — leave pending approval as
    PENDING for morning queue. Deduplicates so the same hold isn't written
    repeatedly every 5-minute poll cycle."""
    conn = get_db()

    # Bug fix: only insert if we haven't already logged a HELD_OVERNIGHT row
    # for this miner+action in the current overnight window
    now = datetime.now()
    if now.hour < WINDOW_END_HOUR:
        window_start = now.replace(hour=WINDOW_START_HOUR, minute=0,
                                   second=0) - timedelta(days=1)
    else:
        window_start = now.replace(hour=WINDOW_START_HOUR, minute=0, second=0)

    existing = conn.execute("""
        SELECT id FROM action_audit_log
        WHERE miner_id=? AND decision='HELD_OVERNIGHT'
          AND action_taken=? AND timestamp >= ?
        LIMIT 1
    """, (action["miner_id"], action["action_type"],
          window_start.isoformat())).fetchone()

    if existing:
        conn.close()
        return  # Already logged this hold tonight — skip

    conn.execute("""
        INSERT INTO action_audit_log
        (timestamp, date, scan_id, miner_id, ip, model, problem,
         action_taken, decision, approved_by, slack_user_id, notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (now.isoformat(), now.strftime("%Y-%m-%d"), action.get("scan_id"),
          action["miner_id"], action.get("ip"), action.get("model"),
          action.get("problem"), action["action_type"],
          "HELD_OVERNIGHT", "Mining Guardian (Overnight Auto)", "AUTO_OVERNIGHT",
          f"Held overnight: {reason}"))
    conn.commit()
    conn.close()


def notify_openclaw(summary: dict) -> None:
    """Send overnight summary to OpenClaw for LLM narrative + Slack post."""
    executed = summary.get("executed", [])
    held     = summary.get("held", [])
    manual   = summary.get("manual", [])

    if not executed and not held:
        return  # Nothing happened — no need to post

    payload = {
        "source":      "mining_guardian_overnight",
        "window":      f"{WINDOW_START_HOUR:02d}:00 – {WINDOW_END_HOUR:02d}:00",
        "executed":    executed,
        "held":        held,
        "manual":      manual,
        "instructions": (
            "You are Mining Guardian AI. The overnight automation window just closed. "
            "Post a brief summary to #mining-guardian covering: what was auto-executed, "
            "what was held back and why, and what still needs operator attention. "
            "Be concise — 3-5 lines max. Include miner IPs where relevant."
        )
    }
    try:
        requests.post(
            OPENCLAW_WEBHOOK, json=payload,
            headers={"Authorization": f"Bearer {OPENCLAW_TOKEN}"},
            timeout=10
        )
        logger.info("OpenClaw notified with overnight summary")
    except Exception as e:
        logger.warning("OpenClaw notify failed: %s", e)


def run_overnight_cycle() -> dict:
    """
    Process all pending approvals and execute AUTO ones.
    Returns a summary dict for reporting.
    """
    pending  = get_pending_actions()
    executed = []
    held     = []
    manual   = []

    for action in pending:
        risk = classify_risk(action)
        ip   = action.get("ip", "?")
        atype = action.get("action_type", "?")

        if risk == "AUTO":
            logger.info("AUTO: %s → %s for %s", risk, atype, ip)
            result = execute_auto_action(action)
            executed.append({
                "ip": ip, "model": action.get("model"),
                "action": atype, "result": result["status"],
                "map_location": action.get("map_location"),
            })

        elif risk == "HOLD":
            reason = "already restarted tonight" if get_restart_count_tonight(
                str(action["miner_id"])) >= MAX_AUTO_RESTARTS_PER_NIGHT \
                else "recent failure"
            logger.info("HOLD: %s for %s — %s", atype, ip, reason)
            log_skip(action, reason)
            held.append({"ip": ip, "action": atype, "reason": reason})

        else:  # MANUAL
            logger.info("MANUAL (skip): %s for %s", atype, ip)
            manual.append({"ip": ip, "action": atype})

    return {"executed": executed, "held": held, "manual": manual}


def main():
    """Main loop — checks pending approvals every 5 minutes during overnight window."""
    logger.info("Overnight Automation started")
    logger.info("Window: %02d:00 – %02d:00", WINDOW_START_HOUR, WINDOW_END_HOUR)

    window_was_active  = False
    summary_for_report = {"executed": [], "held": [], "manual": []}

    while True:
        try:
            now_in_window = is_overnight_window()

            if now_in_window:
                if not window_was_active:
                    logger.info("Overnight window OPENED — autonomous mode active")
                    window_was_active = True
                    summary_for_report = {"executed": [], "held": [], "manual": []}

                # Run a cycle
                result = run_overnight_cycle()

                # Accumulate into nightly summary
                summary_for_report["executed"].extend(result["executed"])
                summary_for_report["held"].extend(result["held"])
                summary_for_report["manual"].extend(result["manual"])

            else:
                if window_was_active:
                    # Window just closed — send OpenClaw summary
                    logger.info("Overnight window CLOSED — sending summary")
                    notify_openclaw(summary_for_report)
                    ex = len(summary_for_report["executed"])
                    hd = len(summary_for_report["held"])
                    mn = len(summary_for_report["manual"])
                    logger.info("Overnight summary: %d executed, %d held, %d manual", ex, hd, mn)
                    window_was_active = False

        except Exception as e:
            logger.error("Overnight loop error: %s", e)

        time.sleep(300)  # check every 5 minutes


if __name__ == "__main__":
    main()
