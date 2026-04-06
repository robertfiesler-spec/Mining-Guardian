"""
confidence_scorer.py
Mining Guardian — Feature 2: Confidence Scoring

Before acting, the AI rates its own confidence (0-100) based on:
  - Historical success rate for this miner + action type (from outcome feedback)
  - How much history exists (more data = more confident in the score)
  - Miner's recent stability (volatile miners get lower confidence)
  - Fleet-wide success rate for this action type (fallback when no miner history)

Confidence gates autonomy:
  >= 80  → Execute automatically (AUTO)
  50-79  → Send to Slack for approval, show confidence score
  < 50   → HOLD — do not act, alert only

This module is called by mining_guardian.py before any action is taken.
"""

import sys
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT / "core"), str(_ROOT / "ai")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logger = logging.getLogger("confidence_scorer")

# ── Confidence thresholds ─────────────────────────────────────────────────────
THRESHOLD_AUTO    = 80   # >= this → execute without approval
THRESHOLD_ASK     = 50   # >= this → ask for approval (show score)
                         # <  this → HOLD, do not act

# ── Scoring weights ───────────────────────────────────────────────────────────
WEIGHT_MINER_HISTORY   = 0.60  # per-miner success rate (most important)
WEIGHT_FLEET_HISTORY   = 0.25  # fleet-wide success rate (fallback signal)
WEIGHT_STABILITY       = 0.15  # miner stability score

# Minimum outcomes needed before trusting miner-specific rate
MIN_OUTCOMES_FOR_MINER_SCORE = 3

# Lookback window for recent outcomes
HISTORY_DAYS = 30

DB_PATH        = str(_ROOT / "guardian.db")
KNOWLEDGE_PATH = str(_ROOT / "knowledge.json")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def get_confidence(miner_id: str, ip: str, action_type: str,
                   hashrate_pct: float = None) -> Tuple[int, str]:
    """
    Main entry point. Returns (confidence_score, reason_string).

    confidence_score: 0-100
    reason_string: human-readable explanation shown in Slack approval messages
    """
    conn = get_db()

    # 1. Per-miner success rate for this action type
    miner_score, miner_count = _miner_success_rate(conn, miner_id, action_type)

    # 2. Fleet-wide success rate for this action type (fallback)
    fleet_score, fleet_count = _fleet_success_rate(conn, action_type)

    # 3. Miner stability score (how consistent has this miner been lately)
    stability_score = _stability_score(conn, miner_id)

    conn.close()

    # Feature 4: Apply per-miner fingerprint confidence modifier
    try:
        from fingerprint_builder import get_confidence_modifier
        modifier = get_confidence_modifier(miner_id)
        # Modifier is -0.5 to +0.5, scale to point adjustment
        fingerprint_adjustment = modifier * 30  # max ±15 points
    except Exception:
        fingerprint_adjustment = 0.0

    # Blend scores — weight miner history more when we have enough data
    if miner_count >= MIN_OUTCOMES_FOR_MINER_SCORE:
        # Enough miner-specific data to weight heavily
        history_score = (
            miner_score  * WEIGHT_MINER_HISTORY +
            fleet_score  * WEIGHT_FLEET_HISTORY
        ) / (WEIGHT_MINER_HISTORY + WEIGHT_FLEET_HISTORY)
    elif miner_count > 0:
        # Some miner data — blend proportionally
        blend = miner_count / MIN_OUTCOMES_FOR_MINER_SCORE
        history_score = (
            miner_score  * blend * WEIGHT_MINER_HISTORY +
            fleet_score  * (1 - blend) * WEIGHT_FLEET_HISTORY
        ) / (WEIGHT_MINER_HISTORY + WEIGHT_FLEET_HISTORY)
    else:
        # No miner-specific data yet — use fleet rate only
        history_score = fleet_score

    # Final weighted score with fingerprint modifier
    raw_confidence = (
        history_score   * (WEIGHT_MINER_HISTORY + WEIGHT_FLEET_HISTORY) +
        stability_score * WEIGHT_STABILITY
    )
    confidence = max(0, min(100, round(raw_confidence + fingerprint_adjustment)))

    # Build human-readable reason
    parts = []
    if miner_count >= MIN_OUTCOMES_FOR_MINER_SCORE:
        parts.append(f"this miner: {miner_score:.0f}% success ({miner_count} outcomes)")
    elif miner_count > 0:
        parts.append(f"this miner: {miner_score:.0f}% success ({miner_count} outcomes, partial)")
    else:
        parts.append("this miner: no history yet")

    parts.append(f"fleet: {fleet_score:.0f}% success ({fleet_count} outcomes)")
    parts.append(f"stability: {stability_score:.0f}%")

    gate = "AUTO" if confidence >= THRESHOLD_AUTO else \
           "ASK"  if confidence >= THRESHOLD_ASK  else "HOLD"

    reason = f"Confidence {confidence}% [{gate}] — " + " | ".join(parts)

    logger.info("[%s] %s confidence=%d gate=%s", ip, action_type, confidence, gate)

    return confidence, reason


def get_gate(confidence: int) -> str:
    """Return the autonomy gate for a given confidence score."""
    if confidence >= THRESHOLD_AUTO:
        return "AUTO"
    elif confidence >= THRESHOLD_ASK:
        return "ASK"
    else:
        return "HOLD"


def _miner_success_rate(conn: sqlite3.Connection, miner_id: str,
                        action_type: str) -> Tuple[float, int]:
    """
    Per-miner success rate for a specific action type over HISTORY_DAYS.
    Returns (success_rate_0_to_100, outcome_count).
    """
    cutoff = (datetime.now() - timedelta(days=HISTORY_DAYS)).isoformat()

    # Map action_type to restart_type patterns
    type_filter = _action_to_restart_type(action_type)

    rows = conn.execute("""
        SELECT outcome, COUNT(*) as cnt
        FROM miner_restarts
        WHERE miner_id = ?
          AND restarted_at >= ?
          AND outcome IN ('SUCCESS', 'FAILURE', 'PARTIAL')
          AND (? IS NULL OR restart_type LIKE ?)
        GROUP BY outcome
    """, (miner_id, cutoff, type_filter, f"%{type_filter}%" if type_filter else None)
    ).fetchall()

    return _calc_rate(rows)


def _fleet_success_rate(conn: sqlite3.Connection,
                        action_type: str) -> Tuple[float, int]:
    """
    Fleet-wide success rate for this action type over HISTORY_DAYS.
    Returns (success_rate_0_to_100, outcome_count).
    """
    cutoff = (datetime.now() - timedelta(days=HISTORY_DAYS)).isoformat()
    type_filter = _action_to_restart_type(action_type)

    rows = conn.execute("""
        SELECT outcome, COUNT(*) as cnt
        FROM miner_restarts
        WHERE restarted_at >= ?
          AND outcome IN ('SUCCESS', 'FAILURE', 'PARTIAL')
          AND (? IS NULL OR restart_type LIKE ?)
        GROUP BY outcome
    """, (cutoff, type_filter, f"%{type_filter}%" if type_filter else None)
    ).fetchall()

    return _calc_rate(rows)


def _stability_score(conn: sqlite3.Connection, miner_id: str) -> float:
    """
    How stable has this miner been recently?
    Uses hashrate variance over the last 10 scans.
    High variance = low stability = lower confidence.
    Returns 0-100.
    """
    rows = conn.execute("""
        SELECT hashrate_pct FROM miner_readings
        WHERE miner_id = ? AND hashrate_pct IS NOT NULL AND status = 'online'
        ORDER BY id DESC LIMIT 10
    """, (miner_id,)).fetchall()

    if len(rows) < 3:
        return 50.0  # not enough data — neutral

    rates = [float(r["hashrate_pct"]) for r in rows]
    mean  = sum(rates) / len(rates)
    if mean == 0:
        return 20.0  # miner has been at 0% — low confidence

    # Coefficient of variation (lower = more stable)
    variance = sum((r - mean) ** 2 for r in rates) / len(rates)
    std_dev  = variance ** 0.5
    cv       = std_dev / mean  # 0 = perfectly stable, higher = volatile

    # Convert to 0-100 score: cv of 0 = 100, cv of 0.5+ = 0
    stability = max(0.0, min(100.0, (1.0 - cv * 2.0) * 100.0))
    return round(stability, 1)


def _calc_rate(rows) -> Tuple[float, int]:
    """Calculate success rate from outcome rows. PARTIAL counts as 0.5."""
    counts = {r["outcome"]: r["cnt"] for r in rows}
    success = counts.get("SUCCESS", 0)
    partial = counts.get("PARTIAL", 0)
    failure = counts.get("FAILURE", 0)
    total   = success + partial + failure

    if total == 0:
        return 50.0, 0  # no data — assume 50%

    # Partial counts as half a success
    effective_success = success + (partial * 0.5)
    rate = (effective_success / total) * 100.0
    return round(rate, 1), total


def _action_to_restart_type(action_type: str) -> Optional[str]:
    """Map action type strings to restart_type patterns in the DB."""
    mapping = {
        "RESTART":             "MANUAL_APPROVED",
        "AUTO_OVERNIGHT":      "AUTO_OVERNIGHT",
        "RESTART_CHECK_BOARDS":"Dead board",
        "PDU_CYCLE":           "PDU",
    }
    return mapping.get(action_type)


def get_fleet_confidence_summary() -> dict:
    """
    Return fleet-wide confidence stats for reporting and dashboards.
    Useful for the 48hr test report.
    """
    conn = get_db()
    rows = conn.execute("""
        SELECT miner_id, ip, model,
               SUM(CASE WHEN outcome='SUCCESS' THEN 1 ELSE 0 END) as successes,
               SUM(CASE WHEN outcome='FAILURE' THEN 1 ELSE 0 END) as failures,
               SUM(CASE WHEN outcome='PARTIAL' THEN 1 ELSE 0 END) as partials,
               COUNT(*) as total
        FROM miner_restarts
        WHERE outcome IN ('SUCCESS','FAILURE','PARTIAL')
        GROUP BY miner_id
        ORDER BY total DESC
    """).fetchall()
    conn.close()

    summary = []
    for r in rows:
        total = r["total"]
        if total == 0:
            continue
        rate = round(((r["successes"] + r["partials"] * 0.5) / total) * 100, 1)
        summary.append({
            "ip": r["ip"],
            "model": r["model"],
            "success_rate": rate,
            "successes": r["successes"],
            "failures": r["failures"],
            "partials": r["partials"],
            "total": total
        })
    return {"miners": summary, "generated_at": datetime.now().isoformat()}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    # Test against real miners
    test_cases = [
        ("53477", "192.168.188.36",  "RESTART"),   # dead board — should be low
        ("53499", "192.168.188.125", "RESTART"),   # healthy miner — should be high
        ("64483", "192.168.188.56",  "RESTART"),   # should be high (succeeded)
        ("53477", "192.168.188.36",  "AUTO_OVERNIGHT"),
    ]

    print("\n=== Confidence Scorer Test ===\n")
    for miner_id, ip, action in test_cases:
        score, reason = get_confidence(miner_id, ip, action)
        gate = get_gate(score)
        print(f"{ip} {action}: {score}% [{gate}]")
        print(f"  {reason}\n")

    print("\n=== Fleet Summary ===")
    summary = get_fleet_confidence_summary()
    for m in summary["miners"]:
        print(f"  {m['ip']}: {m['success_rate']}% ({m['total']} outcomes)")
