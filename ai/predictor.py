"""
predictor.py
Mining Guardian — Feature 6: Pre-Failure Prediction

Instead of reacting when a miner breaks, predict it 2-3 scans before it happens.
Detects patterns that historically precede failures for specific miners and flags
them proactively before anything is actually wrong.

Prediction signals (evaluated per miner every scan):
  1. Hashrate trend   — sustained decline over last N scans
  2. Volatility spike — hashrate variance suddenly much higher than baseline
  3. Board imbalance  — one board diverging significantly from others
  4. Temp creep       — chip temps rising without facility cause
  5. Pattern match    — current trend matches miner's historical pre-failure pattern

Actions generated:
  MONITOR_CLOSE — Watch carefully, no restart yet. Logged, shown in Slack.
  PREEMPTIVE_RESTART — High confidence prediction, restart now before failure.

Prediction accuracy is tracked in knowledge.json and fed back into training.
"""

import sys
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT / "core"), str(_ROOT / "ai")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logger = logging.getLogger("predictor")

DB_PATH        = str(_ROOT / "guardian.db")
KNOWLEDGE_PATH = str(_ROOT / "knowledge.json")

# ── Tuning ────────────────────────────────────────────────────────────────────
TREND_WINDOW        = 5     # scans to look back for trend detection
TREND_DROP_PCT      = 15.0  # % drop over window that triggers prediction
VOLATILITY_WINDOW   = 10    # scans for baseline volatility calculation
VOLATILITY_SPIKE    = 2.5   # multiplier: current CV vs baseline CV
TEMP_CREEP_C        = 4.0   # °C rise over window that triggers prediction
BOARD_IMBALANCE_PCT = 30.0  # % difference between boards that triggers flag
MIN_SCANS_FOR_PRED  = 5     # minimum scan history before predicting
PRED_CONFIDENCE_MIN = 60    # minimum confidence to emit MONITOR_CLOSE
PRED_CONFIDENCE_ACT = 80    # minimum confidence to emit PREEMPTIVE_RESTART

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def run_predictions(scan_id: int) -> List[Dict[str, Any]]:
    """
    Main entry point. Run predictions for all online miners in this scan.
    Returns list of prediction dicts for miners showing pre-failure signals.
    """
    conn = get_db()

    # Get all online miners from this scan
    miners = conn.execute("""
        SELECT mr.miner_id, mr.ip, mr.model, mr.hashrate_pct,
               mr.temp_chip, mr.status, mr.action
        FROM miner_readings mr
        WHERE mr.scan_id = ? AND mr.status = 'online'
        AND (mr.action = 'MONITOR' OR mr.action IS NULL)
    """, (scan_id,)).fetchall()

    conn.close()

    predictions = []
    for m in miners:
        try:
            pred = _predict_miner(m["miner_id"], m["ip"], m["model"],
                                  float(m["hashrate_pct"] or 0),
                                  float(m["temp_chip"] or 0))
            if pred:
                predictions.append(pred)
        except Exception as e:
            logger.debug("Prediction error for %s: %s", m["ip"], e)

    if predictions:
        logger.info("Predictions: %d miners showing pre-failure signals", len(predictions))
        _save_predictions(predictions)

    return predictions


def _predict_miner(miner_id: str, ip: str, model: str,
                   current_hr: float, current_temp: float) -> Optional[Dict[str, Any]]:
    """
    Evaluate a single miner for pre-failure signals.
    Returns prediction dict if signals found, None otherwise.
    """
    conn = get_db()

    # Get recent scan history for this miner
    history = conn.execute("""
        SELECT mr.hashrate_pct, mr.temp_chip, s.scanned_at
        FROM miner_readings mr
        JOIN scans s ON mr.scan_id = s.id
        WHERE mr.miner_id = ? AND mr.status = 'online'
          AND mr.hashrate_pct IS NOT NULL
        ORDER BY s.scanned_at DESC
        LIMIT ?
    """, (miner_id, max(TREND_WINDOW, VOLATILITY_WINDOW) + 5)).fetchall()

    if len(history) < MIN_SCANS_FOR_PRED:
        conn.close()
        return None

    # Get recent board hashrates for imbalance detection
    boards = conn.execute("""
        SELECT c.board_index, c.rate_mhs
        FROM chain_readings c
        JOIN (SELECT MAX(scan_id) as sid FROM chain_readings WHERE ip=?) t ON c.scan_id=t.sid
        WHERE c.ip = ?
    """, (ip, ip)).fetchall()

    conn.close()

    hashrates = [float(r["hashrate_pct"]) for r in history]
    temps     = [float(r["temp_chip"]) if r["temp_chip"] else None for r in history]

    signals   = []
    scores    = []

    # ── Signal 1: Sustained hashrate decline ─────────────────────────────────
    trend_score, trend_signal = _check_hashrate_trend(hashrates[:TREND_WINDOW])
    if trend_signal:
        signals.append(trend_signal)
        scores.append(trend_score)

    # ── Signal 2: Volatility spike ───────────────────────────────────────────
    vol_score, vol_signal = _check_volatility(hashrates)
    if vol_signal:
        signals.append(vol_signal)
        scores.append(vol_score)

    # ── Signal 3: Board imbalance ─────────────────────────────────────────────
    if boards:
        bal_score, bal_signal = _check_board_balance(boards)
        if bal_signal:
            signals.append(bal_signal)
            scores.append(bal_score)

    # ── Signal 4: Temperature creep ───────────────────────────────────────────
    valid_temps = [t for t in temps[:TREND_WINDOW] if t is not None and t > 0]
    if len(valid_temps) >= 3:
        temp_score, temp_signal = _check_temp_creep(valid_temps)
        if temp_signal:
            signals.append(temp_signal)
            scores.append(temp_score)

    # ── Signal 5: Historical pre-failure pattern match ────────────────────────
    pattern_score, pattern_signal = _check_pattern_match(miner_id, hashrates[:TREND_WINDOW])
    if pattern_signal:
        signals.append(pattern_signal)
        scores.append(pattern_score)

    if not signals:
        return None

    # Combine signal scores — multiple signals amplify each other
    base_confidence = max(scores)
    bonus = sum(s * 0.1 for s in scores[1:])  # each additional signal adds 10% of its score
    confidence = min(100, round(base_confidence + bonus))

    if confidence < PRED_CONFIDENCE_MIN:
        return None

    action = "PREEMPTIVE_RESTART" if confidence >= PRED_CONFIDENCE_ACT else "MONITOR_CLOSE"

    return {
        "miner_id":   miner_id,
        "ip":         ip,
        "model":      model,
        "action":     action,
        "confidence": confidence,
        "signals":    signals,
        "current_hr": current_hr,
        "current_temp": current_temp,
        "predicted_at": datetime.now().isoformat()
    }


def _check_hashrate_trend(hashrates: List[float]) -> Tuple[float, Optional[str]]:
    """Detect sustained hashrate decline over the trend window."""
    if len(hashrates) < 3:
        return 0.0, None
    # hashrates[0] is most recent, hashrates[-1] is oldest
    oldest = hashrates[-1]
    newest = hashrates[0]
    if oldest <= 0:
        return 0.0, None
    drop_pct = ((oldest - newest) / oldest) * 100
    if drop_pct >= TREND_DROP_PCT:
        # Score scales with severity of drop
        score = min(90.0, 50.0 + (drop_pct - TREND_DROP_PCT) * 2.0)
        return score, f"hashrate declining {drop_pct:.1f}% over {len(hashrates)} scans ({oldest:.0f}% → {newest:.0f}%)"
    return 0.0, None


def _check_volatility(hashrates: List[float]) -> Tuple[float, Optional[str]]:
    """Detect sudden spike in hashrate volatility compared to baseline."""
    if len(hashrates) < VOLATILITY_WINDOW + 2:
        return 0.0, None

    recent   = hashrates[:3]
    baseline = hashrates[3:VOLATILITY_WINDOW]

    def cv(vals):
        if not vals: return 0
        m = sum(vals) / len(vals)
        if m == 0: return 0
        var = sum((v - m)**2 for v in vals) / len(vals)
        return (var**0.5) / m

    recent_cv   = cv(recent)
    baseline_cv = cv(baseline)

    if baseline_cv > 0 and recent_cv > baseline_cv * VOLATILITY_SPIKE:
        ratio = recent_cv / baseline_cv
        score = min(75.0, 40.0 + (ratio - VOLATILITY_SPIKE) * 10.0)
        return score, f"volatility {ratio:.1f}x above baseline (unstable hashrate pattern)"
    return 0.0, None


def _check_board_balance(boards) -> Tuple[float, Optional[str]]:
    """Detect one board diverging significantly from the others."""
    rates = [(r["board_index"], float(r["rate_mhs"] or 0)) for r in boards]
    rates = [(b, r) for b, r in rates if r > 0]
    if len(rates) < 2:
        return 0.0, None

    values = [r for _, r in rates]
    mean_rate = sum(values) / len(values)
    if mean_rate == 0:
        return 0.0, None

    for board_idx, rate in rates:
        deviation = abs(rate - mean_rate) / mean_rate * 100
        if deviation >= BOARD_IMBALANCE_PCT:
            score = min(80.0, 50.0 + (deviation - BOARD_IMBALANCE_PCT) * 1.0)
            direction = "low" if rate < mean_rate else "high"
            return score, f"board {board_idx} running {deviation:.0f}% {direction} vs fleet avg"
    return 0.0, None


def _check_temp_creep(temps: List[float]) -> Tuple[float, Optional[str]]:
    """Detect temperature creeping up without environmental cause."""
    if len(temps) < 3:
        return 0.0, None
    oldest = temps[-1]
    newest = temps[0]
    rise = newest - oldest
    if rise >= TEMP_CREEP_C:
        score = min(70.0, 40.0 + (rise - TEMP_CREEP_C) * 5.0)
        return score, f"temp creeping up {rise:.1f}°C over {len(temps)} scans ({oldest:.0f} → {newest:.0f}°C)"
    return 0.0, None


def _check_pattern_match(miner_id: str, recent_hrs: List[float]) -> Tuple[float, Optional[str]]:
    """
    Compare current hashrate trend to historical pre-failure patterns.
    Uses outcomes from miner_restarts — what did hashrate look like
    in the 5 scans before each FAILURE outcome?
    """
    conn = get_db()

    # Get historical FAILURE restarts with hashrate_before
    failures = conn.execute("""
        SELECT miner_id, restarted_at, hashrate_before FROM miner_restarts
        WHERE miner_id = ? AND outcome = 'FAILURE' AND hashrate_before IS NOT NULL
        ORDER BY restarted_at DESC LIMIT 5
    """, (miner_id,)).fetchall()

    if not failures:
        conn.close()
        return 0.0, None

    # For each failure, get the 5 scans before it
    pre_failure_patterns = []
    for f in failures:
        pre = conn.execute("""
            SELECT mr.hashrate_pct FROM miner_readings mr
            JOIN scans s ON mr.scan_id = s.id
            WHERE mr.miner_id = ? AND s.scanned_at < ?
              AND mr.hashrate_pct IS NOT NULL
            ORDER BY s.scanned_at DESC LIMIT 5
        """, (miner_id, f["restarted_at"])).fetchall()
        if len(pre) >= 3:
            pre_failure_patterns.append([float(r["hashrate_pct"]) for r in pre])

    conn.close()

    if not pre_failure_patterns or len(recent_hrs) < 3:
        return 0.0, None

    # Compute similarity: does current trend shape match any pre-failure pattern?
    best_similarity = 0.0
    for pattern in pre_failure_patterns:
        similarity = _trend_similarity(recent_hrs[:len(pattern)], pattern)
        best_similarity = max(best_similarity, similarity)

    if best_similarity >= 0.75:
        score = min(85.0, best_similarity * 85.0)
        return score, f"current trend matches pre-failure pattern ({best_similarity:.0%} similarity)"
    return 0.0, None


def _trend_similarity(a: List[float], b: List[float]) -> float:
    """
    Compute normalized similarity between two hashrate trend sequences.
    Both are normalized to their own mean so absolute levels don't matter —
    only the shape (direction and relative magnitude of changes).
    """
    n = min(len(a), len(b))
    if n < 2:
        return 0.0

    def normalize(seq):
        m = sum(seq) / len(seq)
        if m == 0: return seq
        return [v / m for v in seq]

    an = normalize(a[:n])
    bn = normalize(b[:n])

    # Compute deltas (direction of change between consecutive scans)
    def deltas(seq):
        return [seq[i] - seq[i+1] for i in range(len(seq)-1)]

    ad = deltas(an)
    bd = deltas(bn)

    # Direction agreement: do deltas have the same sign?
    agreements = sum(1 for x, y in zip(ad, bd) if (x >= 0) == (y >= 0))
    return agreements / len(ad) if ad else 0.0


def _save_predictions(predictions: List[Dict[str, Any]]):
    """Save predictions to knowledge.json for tracking accuracy."""
    try:
        path = Path(KNOWLEDGE_PATH)
        knowledge = json.loads(path.read_text()) if path.exists() else {}
        preds = knowledge.setdefault("predictions", [])
        for p in predictions:
            preds.append({
                **p,
                "outcome": None,  # filled in by outcome_checker if restart occurs
                "accurate": None  # filled in after outcome is known
            })
        # Keep last 200 predictions
        knowledge["predictions"] = preds[-200:]
        path.write_text(json.dumps(knowledge, indent=2))
    except Exception as e:
        logger.warning("Could not save predictions: %s", e)


def get_prediction_accuracy() -> Dict[str, Any]:
    """
    Return prediction accuracy stats for the 48hr test report.
    Matches predictions to subsequent restarts to see if the prediction was correct.
    """
    try:
        path = Path(KNOWLEDGE_PATH)
        if not path.exists():
            return {"error": "No knowledge.json"}
        knowledge = json.loads(path.read_text())
        preds = knowledge.get("predictions", [])
        if not preds:
            return {"total": 0, "accurate": 0, "accuracy_pct": None}

        total    = len(preds)
        accurate = sum(1 for p in preds if p.get("accurate") is True)
        pending  = sum(1 for p in preds if p.get("accurate") is None)

        return {
            "total": total,
            "accurate": accurate,
            "pending": pending,
            "accuracy_pct": round(accurate / (total - pending) * 100, 1)
                            if (total - pending) > 0 else None
        }
    except Exception as e:
        return {"error": str(e)}


def format_prediction_alert(pred: Dict[str, Any]) -> str:
    """Format a prediction as a Slack message."""
    action_label = {
        "MONITOR_CLOSE":     "👁️ *WATCH CLOSELY*",
        "PREEMPTIVE_RESTART":"⚡ *PREEMPTIVE RESTART RECOMMENDED*"
    }.get(pred["action"], pred["action"])

    lines = [
        f"{action_label} — `{pred['ip']}` ({pred['model']})",
        f"  Confidence: *{pred['confidence']}%* | Current HR: {pred['current_hr']:.1f}%",
        f"  Signals detected:"
    ]
    for signal in pred["signals"]:
        lines.append(f"    • {signal}")
    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    conn = get_db()
    scan = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()

    if scan:
        logger.info("Running predictions on latest scan (id=%d)...", scan["id"])
        predictions = run_predictions(scan["id"])
        if predictions:
            print(f"\n{len(predictions)} pre-failure prediction(s):\n")
            for p in predictions:
                print(format_prediction_alert(p))
                print()
        else:
            print("\nNo pre-failure signals detected — fleet looks healthy.")
    else:
        print("No scans found.")

    print(f"\nPrediction accuracy: {get_prediction_accuracy()}")
