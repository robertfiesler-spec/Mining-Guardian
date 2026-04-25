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

──────────────────────────────────────────────────────────────────────────────
PORT NOTES (CR-3, 2026-04-25):
  This module was originally written against SQLite (`guardian.db`). Per
  Decision 3 (locked) it has been fully rewritten to use the unified
  Postgres backend `core.database_pg.GuardianPGDB`.

  Public API surface is preserved:
    - check_outcomes() -> dict
    - get_outcome_summary() -> dict
    - module-level constants (CHECK_WINDOW, STABILITY_SCANS, thresholds)

  Wire format changes from the SQLite version:
    - `?` placeholders -> `%s`
    - `datetime('now')` -> NOW()
    - sqlite3.Row -> psycopg2.extras.DictRow (same dict-like access)
    - DB connection is the GuardianPGDB._connect() context manager,
      which auto-commits on success and rolls back on exception.

  Behavioral parity tested by:
    1. Running both old and new versions against a frozen seed of
       miner_restarts (rows where outcome IS NULL) and diffing the
       computed outcome strings — see tests/test_outcome_checker_parity.py
       (to be added; does not yet exist).
    2. Observing miner_restarts.outcome populating after first scan cycle
       (was perpetually NULL on the SQLite-vs-Postgres mismatch).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

# ── Path setup — works whether run from repo root or ai/ directory ───────────
_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT / "core"), str(_ROOT / "ai")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Import the unified Postgres backend. Done lazily via try-block so that
# the module is still importable in environments that don't have psycopg2
# installed (e.g. lint-only CI runners) — but check_outcomes() will fail
# loudly if invoked.
try:
    from core.database_pg import GuardianPGDB  # noqa: E402
except Exception as _import_err:  # pragma: no cover - environment-dependent
    GuardianPGDB = None  # type: ignore[assignment]
    _IMPORT_ERROR: Optional[Exception] = _import_err
else:
    _IMPORT_ERROR = None

logger = logging.getLogger("outcome_checker")

# ── Tuning parameters (unchanged from SQLite version) ────────────────────────
CHECK_WINDOW       = 4    # scans after restart to evaluate outcome
STABILITY_SCANS    = 2    # consecutive scans miner must stay recovered
SUCCESS_THRESHOLD  = 80.0  # % of rated hashrate to count as recovered
PARTIAL_THRESHOLD  = 50.0  # % of rated hashrate to count as partial

KNOWLEDGE_PATH = str(_ROOT / "knowledge.json")

# Module-level lazy singleton — one DB handle per process.
_db_singleton: Optional["GuardianPGDB"] = None


# ─────────────────────────────────────────────────────────────────────────────
# Connection helper
# ─────────────────────────────────────────────────────────────────────────────
def get_db() -> "GuardianPGDB":
    """Return the module-level GuardianPGDB instance (lazy init).

    Raises RuntimeError with a clear message if psycopg2 / GuardianPGDB
    is not available in the current environment.
    """
    global _db_singleton
    if GuardianPGDB is None:
        raise RuntimeError(
            "outcome_checker requires core.database_pg.GuardianPGDB but the "
            f"import failed: {_IMPORT_ERROR}. Install psycopg2 and verify the "
            "Postgres backend is reachable."
        )
    if _db_singleton is None:
        _db_singleton = GuardianPGDB()
    return _db_singleton


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
def check_outcomes() -> dict:
    """Find all restarts without outcomes and evaluate them.

    Returns a summary dict for logging:
        {"checked": int, "success": int, "failure": int,
         "partial": int, "pending": int}
    """
    summary = {"checked": 0, "success": 0, "failure": 0, "partial": 0, "pending": 0}
    db = get_db()

    # Phase 1 — read pending restarts. We hold one connection for the read
    # so the snapshot is consistent; per-row writes happen in their own
    # transactions in _evaluate_restart so a single bad row doesn't kill
    # the whole batch.
    with db._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, miner_id, ip, model, restarted_at,
                       restart_type, hashrate_before
                FROM miner_restarts
                WHERE outcome IS NULL OR outcome = 'PENDING'
                ORDER BY restarted_at ASC
                """
            )
            pending_restarts = cur.fetchall()

    # Phase 2 — evaluate each. Each call opens its own short transaction.
    for restart in pending_restarts:
        try:
            outcome = _evaluate_restart(restart)
        except Exception as exc:
            logger.exception(
                "Failed to evaluate restart %s for miner %s: %s",
                restart["id"], restart["miner_id"], exc,
            )
            continue
        summary["checked"] += 1
        bucket = outcome.lower() if outcome in ("SUCCESS", "FAILURE", "PARTIAL", "PENDING") else "pending"
        summary[bucket] += 1

    if summary["checked"] > 0:
        logger.info(
            "Outcome check: %d evaluated — %d success, %d failure, %d partial, %d pending",
            summary["checked"], summary["success"], summary["failure"],
            summary["partial"], summary["pending"],
        )

    return summary


def get_outcome_summary() -> dict:
    """Return fleet-wide outcome stats for reporting/dashboards."""
    db = get_db()
    with db._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT outcome,
                       COUNT(*)                     AS cnt,
                       AVG(recovery_time_scans)     AS avg_recovery
                FROM miner_restarts
                WHERE outcome IS NOT NULL AND outcome != 'PENDING'
                GROUP BY outcome
                """
            )
            rows = cur.fetchall()

    result: dict[str, Any] = {}
    for r in rows:
        avg_recovery = r["avg_recovery"]
        result[r["outcome"]] = {
            "count": int(r["cnt"]),
            "avg_recovery_scans": round(float(avg_recovery), 1) if avg_recovery is not None else None,
        }
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────
def _evaluate_restart(restart: Any) -> str:
    """Evaluate a single restart and write the outcome back to the DB.

    `restart` is a DictRow (from psycopg2 DictCursor) with keys:
        id, miner_id, ip, model, restarted_at, restart_type, hashrate_before
    """
    miner_id     = restart["miner_id"]
    restart_id   = restart["id"]
    restarted_at = restart["restarted_at"]   # datetime object (TIMESTAMP WITH TIME ZONE)
    ip           = restart["ip"]
    model        = restart["model"]

    db = get_db()

    # Fetch hashrate_before (look up if missing) and post-restart scans
    # in a single transaction so we have a consistent view.
    with db._connect() as conn:
        hashrate_before = restart["hashrate_before"]
        if hashrate_before is None:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT mr.hashrate_pct
                    FROM miner_readings mr
                    JOIN scans s ON mr.scan_id = s.id
                    WHERE mr.miner_id = %s AND s.scanned_at <= %s
                    ORDER BY s.scanned_at DESC
                    LIMIT 1
                    """,
                    (miner_id, restarted_at),
                )
                pre = cur.fetchone()
            hashrate_before = float(pre["hashrate_pct"]) if pre and pre["hashrate_pct"] is not None else None

        # Get scans that happened AFTER the restart, in order.
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT mr.hashrate_pct, s.scanned_at, s.id AS scan_id
                FROM miner_readings mr
                JOIN scans s ON mr.scan_id = s.id
                WHERE mr.miner_id = %s AND s.scanned_at > %s
                ORDER BY s.scanned_at ASC
                LIMIT %s
                """,
                (miner_id, restarted_at, CHECK_WINDOW),
            )
            post_scans = cur.fetchall()

    # Defensive: skip post-rows where hashrate_pct is NULL — they can't be
    # part of a recovery determination.
    hashrates = [float(r["hashrate_pct"]) for r in post_scans if r["hashrate_pct"] is not None]

    if len(hashrates) < 2:
        # Not enough scans yet — still pending.
        _write_outcome(restart_id, "PENDING", hashrate_before, None, None)
        return "PENDING"

    latest_hr = hashrates[-1]

    # Count consecutive scans above SUCCESS_THRESHOLD from the end.
    stable_count = 0
    for hr in reversed(hashrates):
        if hr >= SUCCESS_THRESHOLD:
            stable_count += 1
        else:
            break

    # Determine outcome.
    recovery_scans: Optional[int] = None
    if stable_count >= STABILITY_SCANS:
        outcome = "SUCCESS"
        for i, hr in enumerate(hashrates):
            if hr >= SUCCESS_THRESHOLD:
                recovery_scans = i + 1
                break
    elif latest_hr >= PARTIAL_THRESHOLD:
        outcome = "PARTIAL"
    elif len(post_scans) >= CHECK_WINDOW:
        outcome = "FAILURE"
    else:
        outcome = "PENDING"

    _write_outcome(restart_id, outcome, hashrate_before, latest_hr, recovery_scans)

    if outcome != "PENDING":
        _update_knowledge(miner_id, ip, model, outcome, recovery_scans)
        _validate_prediction(miner_id, ip, outcome)

    logger.info(
        "Outcome for %s (restart %d): %s | before=%.1f%% after=%.1f%% recovery_in=%s scans",
        ip, restart_id, outcome,
        hashrate_before or 0.0, latest_hr,
        recovery_scans if recovery_scans is not None else "N/A",
    )

    return outcome


def _write_outcome(
    restart_id: int,
    outcome: str,
    hashrate_before: Optional[float],
    hashrate_after: Optional[float],
    recovery_time_scans: Optional[int],
) -> None:
    """Write the computed outcome back to miner_restarts."""
    db = get_db()
    # outcome_checked_at is a TEXT column in the schema (see
    # migrations/001_initial_schema.sql line ~75). We keep ISO-8601 strings
    # for backwards compatibility with anything reading this field.
    checked_at_iso = datetime.now(timezone.utc).isoformat()
    with db._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE miner_restarts
                SET outcome             = %s,
                    outcome_checked_at  = %s,
                    hashrate_before     = %s,
                    hashrate_after      = %s,
                    recovery_time_scans = %s
                WHERE id = %s
                """,
                (
                    outcome,
                    checked_at_iso,
                    hashrate_before,
                    hashrate_after,
                    recovery_time_scans,
                    restart_id,
                ),
            )
        # GuardianPGDB._connect() auto-commits on context exit.


# ─────────────────────────────────────────────────────────────────────────────
# Knowledge.json writers (unchanged behavior — no DB involved)
# ─────────────────────────────────────────────────────────────────────────────
def _update_knowledge(
    miner_id: str,
    ip: Optional[str],
    model: Optional[str],
    outcome: str,
    recovery_time_scans: Optional[int],
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
            "last_updated": None,
        })

        # Backfill missing key on legacy profiles.
        profile.setdefault("restart_outcomes", [])

        profile["restart_outcomes"].append({
            "outcome": outcome,
            "recovery_time_scans": recovery_time_scans,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        })
        # Keep only the last 50 outcomes per miner to bound growth.
        profile["restart_outcomes"] = profile["restart_outcomes"][-50:]

        if outcome == "SUCCESS":
            profile["success_count"] = profile.get("success_count", 0) + 1
        elif outcome == "FAILURE":
            profile["failure_count"] = profile.get("failure_count", 0) + 1
        elif outcome == "PARTIAL":
            profile["partial_count"] = profile.get("partial_count", 0) + 1

        total = (
            profile.get("success_count", 0)
            + profile.get("failure_count", 0)
            + profile.get("partial_count", 0)
        )
        profile["restart_success_rate"] = (
            round(profile.get("success_count", 0) / total, 3) if total > 0 else None
        )
        profile["last_updated"] = datetime.now(timezone.utc).isoformat()

        # Atomic write — crash-safe.
        tmp = str(KNOWLEDGE_PATH) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(knowledge, f, indent=2)
        os.replace(tmp, str(KNOWLEDGE_PATH))

    except Exception as exc:
        logger.warning("Could not update knowledge.json with outcome: %s", exc)


def _validate_prediction(miner_id: str, ip: Optional[str], outcome: str) -> None:
    """Cross-check this outcome against any stored predictions for the miner.

    Updates prediction_accuracy in knowledge.json with TP/FP/FN/TN counts.
    """
    try:
        knowledge: dict[str, Any] = {}
        if Path(KNOWLEDGE_PATH).exists():
            knowledge = json.loads(Path(KNOWLEDGE_PATH).read_text())

        predictions = knowledge.get("predictions", [])

        cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        relevant_pred: Optional[dict] = None
        for p in predictions:
            if p.get("ip") == ip or p.get("miner_id") == str(miner_id):
                pred_time = p.get("predicted_at", "")
                if pred_time >= cutoff:
                    relevant_pred = p
                    break  # Use most recent.

        accuracy = knowledge.setdefault("prediction_accuracy", {
            "true_positives": 0,
            "false_positives": 0,
            "false_negatives": 0,
            "true_negatives": 0,
            "total_validations": 0,
        })

        predicted_failure = (
            relevant_pred is not None
            and relevant_pred.get("action") == "PREEMPTIVE_RESTART"
        )
        actual_failure = outcome == "FAILURE"

        accuracy["total_validations"] += 1

        if predicted_failure and actual_failure:
            accuracy["true_positives"] += 1
            logger.info("PREDICTION VALIDATED: TRUE POSITIVE for %s — predicted failure and it failed", ip)
        elif predicted_failure and not actual_failure:
            accuracy["false_positives"] += 1
            logger.info("PREDICTION VALIDATED: FALSE POSITIVE for %s — predicted failure but recovered", ip)
        elif not predicted_failure and actual_failure:
            accuracy["false_negatives"] += 1
            logger.info("PREDICTION VALIDATED: FALSE NEGATIVE for %s — missed the failure", ip)
        else:
            accuracy["true_negatives"] += 1
            # Don't log true negatives — too noisy.

        tp = accuracy["true_positives"]
        tn = accuracy["true_negatives"]
        total = accuracy["total_validations"]
        if total > 0:
            accuracy["accuracy_rate"] = round((tp + tn) / total * 100, 1)

        tmp = str(KNOWLEDGE_PATH) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(knowledge, f, indent=2)
        os.replace(tmp, str(KNOWLEDGE_PATH))

    except Exception as exc:
        logger.warning("Could not validate prediction: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point — unchanged
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logger.info("Running outcome checker manually...")
    summary = check_outcomes()
    print(f"\nSummary: {summary}")
    print(f"\nFleet outcome stats: {get_outcome_summary()}")
