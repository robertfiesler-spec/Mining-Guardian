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

When the overnight window closes, a summary line is logged for the morning
briefing to pick up.
"""

import sys
import os
import json
import time
import logging
import psycopg2
from psycopg2.extras import DictCursor
import requests
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# ── Path setup ────────────────────────────────────────────────────────────────
# MUST come before `from db_targets import ...` below — the launcher
# runs us via direct script path (not python -m). When the script
# itself lives under core/, Python sets sys.path[0] to core/ — so
# `from core.db_targets import ...` would fail (looking for
# core/core/db_targets.py), but `from db_targets import ...` resolves
# because we explicitly add core/ to sys.path here. W14a regression
# 2026-05-12.
#
# Path X (2026-05-12): also add `_ROOT` itself (install root) so that
# any module loaded via the install-tree paths that uses dotted imports
# (`from core.X import ...`) can still resolve them. Even though THIS
# file uses the bare form for db_targets, modules it imports may not.
_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT), str(_ROOT / "core"), str(_ROOT / "clients"), str(_ROOT / "monitoring"), str(_ROOT / "ai")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Bare form (not `from core.db_targets`) since `core/` itself is on
# sys.path, not the install root — and this file lives inside core/
# so the `core.` prefix wouldn't resolve regardless.
from db_targets import operational_target  # noqa: E402

# Import confidence scorer for audit logging
try:
    from confidence_scorer import get_confidence as _get_confidence
    _has_confidence_scorer = True
except ImportError:
    _has_confidence_scorer = False


def _calc_conf(action):
    """Calculate confidence for audit logging."""
    if not _has_confidence_scorer:
        return 75
    try:
        conf, _ = _get_confidence(
            str(action.get("miner_id", "")),
            action.get("ip", ""),
            action.get("action_type", "RESTART")
        )
        return conf
    except Exception as e:
        logger.warning("Confidence calculation failed for %s: %s", action.get("ip"), e)
        return 75

load_dotenv()
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("overnight")

def _pg_dsn() -> str:
    """Operational Postgres DSN via core.db_targets.

    W14a (2026-05-12): delegated to the resolver so this module stays
    on the operational instance after W14 splits catalog onto port
    5433. overnight_automation reads and writes operational
    action_audit_log and miner_readings during the autonomous window.
    """
    return operational_target().dsn()
APPROVAL_API     = "http://localhost:8686"

# ── Overnight window (24h clock) ──────────────────────────────────────────────
# Set to 0 / 24 to run ALL DAY — full autonomous mode
WINDOW_START_HOUR = 0    # midnight (start of day)
WINDOW_END_HOUR   = 24   # end of day — effectively always active

# ── How many times a miner can be auto-restarted in one overnight window ──────
MAX_AUTO_RESTARTS_PER_NIGHT = 2  # increased from 1 for full-day mode


class _PgConnWrapper:
    """Thin wrapper over a psycopg2 Connection that adds SQLite-style
    conn.execute(sql, params).fetchone() / fetchall() shortcuts.

    The underlying psycopg2 Connection has no .execute() method; all SQL
    must go through a cursor. Rather than rewrite every call site in
    overnight_automation.py, this wrapper provides the SQLite-like shortcut
    while keeping commit(), close(), and the with-statement protocol
    delegating to the real connection.
    """

    def __init__(self, dsn: str):
        self._conn = psycopg2.connect(dsn, cursor_factory=DictCursor)

    def execute(self, sql, params=()):
        cur = self._conn.cursor()
        cur.execute(sql, params)
        return cur  # cursor has .fetchone(), .fetchall(), .rowcount, etc.

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
    """Return a psycopg2-backed connection wrapper with SQLite-style .execute shortcut.

    Callers can continue to write `conn.execute(sql, params).fetchone()`.
    """
    return _PgConnWrapper(_pg_dsn())


def is_overnight_window() -> bool:
    """Returns True if current time is inside the automation window.

    Bucket 9 §10.7: consults `system_schedules.overnight_window` first so
    operators can change the window from the Web GUI without touching
    code. Falls back to the WINDOW_START_HOUR / WINDOW_END_HOUR constants
    if the schedule helpers are unavailable (import error or DB down).
    """
    try:
        from api.system_schedules import is_in_window as _is_in_window
        return _is_in_window("overnight_window")
    except Exception as e:
        logger.warning("system_schedules unavailable, using constants: %s", e)

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
        WHERE miner_id=%s
          AND approved_by='Mining Guardian (Overnight Auto)'
          AND decision='AUTO_OVERNIGHT'
          AND action_taken IN ('RESTART', 'PDU_CYCLE')
          AND timestamp >= %s
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
        WHERE miner_id=%s AND outcome='FAILURE'
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
        WHERE miner_id=%s AND outcome='FAILURE' AND restarted_at >= %s
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
        with open(cfg_path) as f:
            cfg = json.load(f)
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
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (now.isoformat(), now.strftime("%Y-%m-%d"), action.get("scan_id"),
                  action["miner_id"], action["ip"], action.get("model"),
                  action.get("problem"), action["action_type"],
                  "AUTO_OVERNIGHT", "Mining Guardian (Overnight Auto)", "AUTO_OVERNIGHT",
                  f"Auto-executed during overnight window | Conf:{_calc_conf(action)}%"))
            conn.execute(
                "UPDATE pending_approvals SET status='APPROVED', responded_at=%s WHERE id=%s",
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
        WHERE miner_id=%s AND decision='HELD_OVERNIGHT'
          AND action_taken=%s AND timestamp >= %s
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
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (now.isoformat(), now.strftime("%Y-%m-%d"), action.get("scan_id"),
          action["miner_id"], action.get("ip"), action.get("model"),
          action.get("problem"), action["action_type"],
          "HELD_OVERNIGHT", "Mining Guardian (Overnight Auto)", "AUTO_OVERNIGHT",
          f"Held overnight: {reason}"))
    conn.commit()
    conn.close()


def _get_automation_mode_safe() -> str:
    """Read the current automation_mode from system_settings, defaulting to
    FULL_AUTO on any failure so we never silently halt automation.

    Bucket 9 §10.2 — the Web GUI lets the operator toggle FULL_AUTO / SEMI_AUTO /
    MANUAL at runtime. We read it fresh each cycle (cycles are 5 min apart, and
    operator mode changes should take effect within one cycle).
    """
    try:
        # Add api/ to sys.path so we can import system_settings without installing.
        api_dir = str(_ROOT / "api")
        if api_dir not in sys.path:
            sys.path.insert(0, api_dir)
        from system_settings import get_automation_mode  # type: ignore
        return get_automation_mode()
    except Exception as exc:
        logger.warning("Could not read automation_mode (defaulting to FULL_AUTO): %s", exc)
        return "FULL_AUTO"


def run_overnight_cycle() -> dict:
    """
    Process all pending approvals and execute AUTO ones — gated by the global
    automation_mode setting from the Web GUI (Bucket 9 §10.2):

      FULL_AUTO  — current behavior: AUTO classified actions auto-execute
      SEMI_AUTO  — AUTO actions are downgraded to HOLD (queue for approval)
      MANUAL     — every action is treated as MANUAL (queue for approval), no
                   auto-execution at all

    The per-action AUTO/HOLD/MANUAL classifier is still the source of truth for
    RISK; mode is an operator-facing ceiling on top of it.

    Returns a summary dict for reporting, including the mode that governed
    this cycle so morning briefings can explain behavior changes.
    """
    mode = _get_automation_mode_safe()
    pending  = get_pending_actions()
    executed = []
    held     = []
    manual   = []

    if mode != "FULL_AUTO":
        logger.info("Automation mode=%s — auto-execution %s",
                    mode,
                    "held for GUI approval" if mode == "SEMI_AUTO" else "disabled; all actions require manual approval")

    for action in pending:
        risk = classify_risk(action)
        ip   = action.get("ip", "%s")
        atype = action.get("action_type", "%s")

        # Mode override: MANUAL forces everything to MANUAL; SEMI_AUTO demotes
        # AUTO to HOLD (leaving HOLD and MANUAL untouched).
        if mode == "MANUAL":
            effective_risk = "MANUAL"
        elif mode == "SEMI_AUTO" and risk == "AUTO":
            effective_risk = "HOLD"
        else:
            effective_risk = risk

        if effective_risk == "AUTO":
            logger.info("AUTO: %s → %s for %s", effective_risk, atype, ip)
            result = execute_auto_action(action)
            executed.append({
                "ip": ip, "model": action.get("model"),
                "action": atype, "result": result["status"],
                "map_location": action.get("map_location"),
            })

        elif effective_risk == "HOLD":
            if mode == "SEMI_AUTO" and risk == "AUTO":
                reason = "semi-auto mode — queued for approval"
            else:
                reason = "already restarted tonight" if get_restart_count_tonight(
                    str(action["miner_id"])) >= MAX_AUTO_RESTARTS_PER_NIGHT \
                    else "recent failure"
            logger.info("HOLD: %s for %s — %s", atype, ip, reason)
            log_skip(action, reason)
            held.append({"ip": ip, "action": atype, "reason": reason})

        else:  # MANUAL
            reason = "manual mode" if mode == "MANUAL" else "classifier MANUAL"
            logger.info("MANUAL (skip): %s for %s — %s", atype, ip, reason)
            manual.append({"ip": ip, "action": atype, "reason": reason})

    return {"executed": executed, "held": held, "manual": manual, "mode": mode}


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
                    # Window just closed — log summary for morning briefing
                    logger.info("Overnight window CLOSED")
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
