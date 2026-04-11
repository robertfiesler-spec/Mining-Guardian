"""
outcome_checker.py
Mining Guardian — Feature 1: Outcome Feedback Loop

After every scan, checks restarts that don't yet have an outcome and evaluates
whether the miner recovered. Writes SUCCESS / FAILURE / PARTIAL back to the
miner_restarts table, creating labeled training data for every action taken.

Definition of outcomes:
  SUCCESS — hashrate returned to >= 80% of rated within CHECK_WINDOW scans
            AND stayed there for at least STABILITY_SCANS consecutive scans
  PARTIAL — hashrate returned but is between 50-80% of rated
  FAILURE — hashrate did not recover within CHECK_WINDOW scans
  PENDING — not enough scans have passed yet to evaluate

This module is called by mining_guardian.py after each scan completes.
It also updates miner profiles in knowledge.json with outcome history.
"""

import os
import sys
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT / "core"), str(_ROOT / "ai")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logger = logging.getLogger("outcome_checker")

# ── Tuning parameters ─────────────────────────────────────────────────────────
CHECK_WINDOW    = 4    # scans after restart to evaluate outcome
STABILITY_SCANS = 2    # consecutive scans miner must stay recovered
SUCCESS_THRESHOLD = 80.0  # % of rated hashrate to count as recovered
PARTIAL_THRESHOLD = 50.0  # % of rated hashrate to count as partial

DB_PATH           = str(_ROOT / "guardian.db")
KNOWLEDGE_PATH    = str(_ROOT / "knowledge.json")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def check_outcomes() -> dict:
    """
    Main entry point. Finds all restarts without outcomes and evaluates them.
    Returns a summary dict for logging.
    """
    conn = get_db()
    summary = {"checked": 0, "success": 0, "failure": 0, "partial": 0, "pending": 0}

    # Find restarts that need outcome evaluation
    pending_restarts = conn.execute("""
        SELECT id, miner_id, ip, model, restarted_at, restart_type, hashrate_before
        FROM miner_restarts
        WHERE outcome IS NULL OR outcome = 'PENDING'
        ORDER BY restarted_at ASC
    """).fetchall()

    for restart in pending_restarts:
        outcome = _evaluate_restart(conn, restart)
        summary["checked"] += 1
        summary[outcome.lower() if outcome in ("SUCCESS","FAILURE","PARTIAL","PENDING") else "pending"] += 1

    conn.close()

    if summary["checked"] > 0:
        logger.info(
            "Outcome check: %d evaluated — %d success, %d failure, %d partial, %d pending",
            summary["checked"], summary["success"], summary["failure"],
            summary["partial"], summary["pending"]
        )

    return summary


def _evaluate_restart(conn: sqlite3.Connection, restart: sqlite3.Row) -> str:
    """Evaluate a single restart and write the outcome back to the DB."""
    miner_id     = restart["miner_id"]
    restart_id   = restart["id"]
    restarted_at = restart["restarted_at"]
    ip           = restart["ip"]

    # Get hashrate_before from the restart record itself, or look it up
    hashrate_before = restart["hashrate_before"]
    if hashrate_before is None:
        # Look up hashrate from the scan just before the restart
        pre = conn.execute("""
            SELECT mr.hashrate_pct FROM miner_readings mr
            JOIN scans s ON mr.scan_id = s.id
            WHERE mr.miner_id = ? AND s.scanned_at <= ?
            ORDER BY s.scanned_at DESC LIMIT 1
        """, (miner_id, restarted_at)).fetchone()
        hashrate_before = float(pre["hashrate_pct"]) if pre else None

    # Get scans that happened AFTER the restart, in order
    post_scans = conn.execute("""
        SELECT mr.hashrate_pct, s.scanned_at, s.id as scan_id
        FROM miner_readings mr
        JOIN scans s ON mr.scan_id = s.id
        WHERE mr.miner_id = ? AND s.scanned_at > ?
        ORDER BY s.scanned_at ASC
        LIMIT ?
    """, (miner_id, restarted_at, CHECK_WINDOW)).fetchall()

    if len(post_scans) < 2:
        # Not enough scans yet — still pending
        _write_outcome(conn, restart_id, "PENDING", hashrate_before, None, None)
        return "PENDING"

    # Evaluate recovery
    hashrates = [float(r["hashrate_pct"]) for r in post_scans]
    latest_hr = hashrates[-1]

    # Count consecutive scans above SUCCESS_THRESHOLD from the end
    stable_count = 0
    for hr in reversed(hashrates):
        if hr >= SUCCESS_THRESHOLD:
            stable_count += 1
        else:
            break

    # Determine outcome
    if stable_count >= STABILITY_SCANS:
        outcome = "SUCCESS"
        # Find how many scans until first recovery
        recovery_scans = None
        for i, hr in enumerate(hashrates):
            if hr >= SUCCESS_THRESHOLD:
                recovery_scans = i + 1
                break
    elif latest_hr >= PARTIAL_THRESHOLD:
        outcome = "PARTIAL"
        recovery_scans = None
    elif len(post_scans) >= CHECK_WINDOW:
        # Enough scans have passed and no recovery
        outcome = "FAILURE"
        recovery_scans = None
    else:
        outcome = "PENDING"
        recovery_scans = None

    _write_outcome(conn, restart_id, outcome, hashrate_before, latest_hr, recovery_scans)

    # Update knowledge.json miner profile with outcome
    if outcome != "PENDING":
        _update_knowledge(miner_id, ip, restart["model"], outcome, recovery_scans)
        # Validate any predictions we made for this miner
        _validate_prediction(miner_id, ip, outcome)

    logger.info(
        "Outcome for %s (restart %d): %s | before=%.1f%% after=%.1f%% recovery_in=%s scans",
        ip, restart_id, outcome,
        hashrate_before or 0, latest_hr,
        recovery_scans or "N/A"
    )

    return outcome


def _write_outcome(
    conn: sqlite3.Connection,
    restart_id: int,
    outcome: str,
    hashrate_before: Optional[float],
    hashrate_after: Optional[float],
    recovery_time_scans: Optional[int]
) -> None:
    conn.execute("""
        UPDATE miner_restarts
        SET outcome = ?,
            outcome_checked_at = ?,
            hashrate_before = ?,
            hashrate_after = ?,
            recovery_time_scans = ?
        WHERE id = ?
    """, (
        outcome,
        datetime.now().isoformat(),
        hashrate_before,
        hashrate_after,
        recovery_time_scans,
        restart_id
    ))
    conn.commit()


def _update_knowledge(
    miner_id: str,
    ip: str,
    model: str,
    outcome: str,
    recovery_time_scans: Optional[int]
) -> None:
    """Update the miner's profile in knowledge.json with this outcome."""
    try:
        if not Path(KNOWLEDGE_PATH).exists():
            return
        with open(KNOWLEDGE_PATH) as f:
            knowledge = json.load(f)

        profiles = knowledge.setdefault("miner_profiles", {})
        profile  = profiles.setdefault(miner_id, {
            "ip": ip, "model": model,
            "restart_outcomes": [],
            "success_count": 0,
            "failure_count": 0,
            "partial_count": 0,
            "last_updated": None
        })

        # Ensure restart_outcomes key exists on old profiles
        if "restart_outcomes" not in profile:
            profile["restart_outcomes"] = []

        # Append this outcome
        profile["restart_outcomes"].append({
            "outcome": outcome,
            "recovery_time_scans": recovery_time_scans,
            "recorded_at": datetime.now().isoformat()
        })
        # Keep only last 50 outcomes per miner to avoid unbounded growth
        profile["restart_outcomes"] = profile["restart_outcomes"][-50:]

        # Update counters
        if outcome == "SUCCESS":
            profile["success_count"] = profile.get("success_count", 0) + 1
        elif outcome == "FAILURE":
            profile["failure_count"] = profile.get("failure_count", 0) + 1
        elif outcome == "PARTIAL":
            profile["partial_count"] = profile.get("partial_count", 0) + 1

        # Compute success rate
        total = (profile.get("success_count", 0) +
                 profile.get("failure_count", 0) +
                 profile.get("partial_count", 0))
        profile["restart_success_rate"] = round(
            profile.get("success_count", 0) / total, 3) if total > 0 else None

        profile["last_updated"] = datetime.now().isoformat()

        # Atomic write — crash-safe
        _tmp = str(KNOWLEDGE_PATH) + ".tmp"
        with open(_tmp, "w") as f:
            json.dump(knowledge, f, indent=2)
        os.replace(_tmp, str(KNOWLEDGE_PATH))

    except Exception as e:
        logger.warning("Could not update knowledge.json with outcome: %s", e)


def _validate_prediction(miner_id: str, ip: str, outcome: str) -> None:
    """
    Check if there was a prediction for this miner and validate it.
    Updates prediction_accuracy in knowledge.json.
    
    Prediction validation rules:
    - If we predicted failure (PREEMPTIVE_RESTART) and miner failed = TRUE POSITIVE
    - If we predicted failure but miner recovered = FALSE POSITIVE  
    - If we did not predict and miner failed = FALSE NEGATIVE (missed)
    - If we did not predict and miner recovered = TRUE NEGATIVE
    """
    try:
        knowledge = {}
        if Path(KNOWLEDGE_PATH).exists():
            knowledge = json.loads(Path(KNOWLEDGE_PATH).read_text())
        
        predictions = knowledge.get("predictions", [])
        
        # Find prediction for this miner (within last 48 hours)
        cutoff = (datetime.now() - timedelta(hours=48)).isoformat()
        relevant_pred = None
        for p in predictions:
            if (p.get("ip") == ip or p.get("miner_id") == str(miner_id)):
                pred_time = p.get("predicted_at", "")
                if pred_time >= cutoff:
                    relevant_pred = p
                    break  # Use most recent
        
        # Initialize prediction_accuracy if not present
        accuracy = knowledge.setdefault("prediction_accuracy", {
            "true_positives": 0,
            "false_positives": 0,
            "false_negatives": 0,
            "true_negatives": 0,
            "total_validations": 0
        })
        
        predicted_failure = (relevant_pred is not None and 
                            relevant_pred.get("action") == "PREEMPTIVE_RESTART")
        actual_failure = outcome == "FAILURE"
        
        accuracy["total_validations"] += 1
        
        if predicted_failure and actual_failure:
            accuracy["true_positives"] += 1
            logger.info("PREDICTION VALIDATED: TRUE POSITIVE for %s - predicted failure and it failed", ip)
        elif predicted_failure and not actual_failure:
            accuracy["false_positives"] += 1
            logger.info("PREDICTION VALIDATED: FALSE POSITIVE for %s - predicted failure but recovered", ip)
        elif not predicted_failure and actual_failure:
            accuracy["false_negatives"] += 1
            logger.info("PREDICTION VALIDATED: FALSE NEGATIVE for %s - missed the failure", ip)
        else:
            accuracy["true_negatives"] += 1
            # Do not log true negatives (too noisy)
        
        # Calculate accuracy rate
        tp = accuracy["true_positives"]
        tn = accuracy["true_negatives"]
        total = accuracy["total_validations"]
        if total > 0:
            accuracy["accuracy_rate"] = round((tp + tn) / total * 100, 1)
        
        # Atomic write
        tmp = str(KNOWLEDGE_PATH) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(knowledge, f, indent=2)
        import os
        os.replace(tmp, str(KNOWLEDGE_PATH))
        
    except Exception as e:
        logger.warning("Could not validate prediction: %s", e)


def get_outcome_summary() -> dict:
    """Return fleet-wide outcome stats for reporting/dashboards."""
    conn = get_db()
    rows = conn.execute("""
        SELECT outcome, COUNT(*) as cnt,
               AVG(recovery_time_scans) as avg_recovery
        FROM miner_restarts
        WHERE outcome IS NOT NULL AND outcome != 'PENDING'
        GROUP BY outcome
    """).fetchall()
    conn.close()

    result = {}
    for r in rows:
        result[r["outcome"]] = {
            "count": r["cnt"],
            "avg_recovery_scans": round(r["avg_recovery"], 1) if r["avg_recovery"] else None
        }
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    logger.info("Running outcome checker manually...")
    summary = check_outcomes()
    print(f"\nSummary: {summary}")
    print(f"\nFleet outcome stats: {get_outcome_summary()}")
