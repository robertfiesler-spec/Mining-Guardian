"""
predictor.py — v2
Mining Guardian — Feature 6: Pre-Failure Prediction (Full Data)

11 signals using every available data point:
  1.  Hashrate trend decline       (miner_readings.hashrate_pct)
  2.  Volatility spike             (miner_readings.hashrate_pct)
  3.  Board rate imbalance         (chain_readings.rate_mhs)
  4.  Chip temp creep              (miner_readings.temp_chip)
  5.  Historical pattern match     (miner_restarts pre-failure shape)
  6.  Board voltage drop           (chain_readings.voltage)
  7.  Board temp elevated          (chain_readings.temp_board)
  8.  Pool rejection rate spike    (pool_readings)
  9.  AMS alert spike              (ams_notifications)
  10. Uptime reset / reboot        (miner_readings.uptime)
  11. Max temp trending high       (miner_state_readings.max_temp_board/chip)
"""

import sys
import json
import logging
import sqlite3
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent

def _load_knowledge() -> Dict:
    """Load knowledge.json for fingerprints."""
    try:
        return json.loads(Path(KNOWLEDGE_PATH).read_text())
    except:
        return {}

def _get_fingerprint_risk_modifier(miner_id: str, ip: str) -> float:
    """
    Get risk modifier from fingerprint.
    Returns 0 to +20 points based on behavioral history.
    Miners with poor restart success or frequent issues get boosted risk.
    """
    knowledge = _load_knowledge()
    fps = knowledge.get("miner_fingerprints", {})
    
    # Try to find fingerprint by miner_id or ip
    fp = fps.get(miner_id) or fps.get(str(miner_id))
    if not fp:
        for fid, fdata in fps.items():
            if fdata.get("ip") == ip:
                fp = fdata
                break
    
    if not fp:
        return 0.0  # No fingerprint = no modifier
    
    modifier = 0.0
    
    # Low restart success rate = higher risk
    success_rate = fp.get("restart_success_rate", 100)
    if success_rate is not None and success_rate < 50:
        modifier += 15.0  # Very unreliable miner
    elif success_rate is not None and success_rate < 70:
        modifier += 8.0   # Somewhat unreliable
    
    # Many known issues = higher risk
    issues = fp.get("known_issues", [])
    if isinstance(issues, list) and len(issues) >= 3:
        modifier += 5.0
    
    # Frequent reboots = higher risk
    if isinstance(issues, list):
        for issue in issues:
            if "frequent_reboots" in str(issue):
                modifier += 5.0
                break
    
    return min(modifier, 20.0)  # Cap at +20
for _p in [str(_ROOT / "core"), str(_ROOT / "ai")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logger = logging.getLogger("predictor")

DB_PATH        = str(_ROOT / "guardian.db")
KNOWLEDGE_PATH = str(_ROOT / "knowledge.json")

TREND_WINDOW        = 5
TREND_DROP_PCT      = 15.0
VOLATILITY_WINDOW   = 10
VOLATILITY_SPIKE    = 2.5
TEMP_CREEP_C        = 4.0
BOARD_IMBALANCE_PCT = 30.0
MIN_SCANS_FOR_PRED  = 5
PRED_CONFIDENCE_MIN = 60
PRED_CONFIDENCE_ACT = 80
VOLTAGE_DROP_V      = 14.2
BOARD_TEMP_WARN_C   = 70.0
REJ_RATE_HIGH       = 0.005
AMS_ALERT_WINDOW_H  = 24
MAX_BOARD_TEMP_WARN = 80.0


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def run_predictions(scan_id: int) -> List[Dict[str, Any]]:
    conn = get_db()
    miners = conn.execute("""
        SELECT mr.miner_id, mr.ip, mr.model, mr.hashrate_pct,
               mr.temp_chip, mr.temp_board, mr.uptime, mr.status,
               mr.action, mr.firmware_manufacturer
        FROM miner_readings mr
        WHERE mr.scan_id=? AND mr.status='online'
          AND (mr.action='MONITOR' OR mr.action IS NULL)
    """, (scan_id,)).fetchall()

    # Get ticketed miners to suppress
    ticketed = {str(r[0]) for r in conn.execute(
        "SELECT miner_id FROM known_dead_boards WHERE resolved_at IS NULL"
    ).fetchall()}
    conn.close()

    predictions = []
    for m in miners:
        # Skip ticketed miners
        if str(m["miner_id"]) in ticketed:
            continue
        try:
            pred = _predict_miner(
                m["miner_id"], m["ip"], m["model"],
                float(m["hashrate_pct"] or 0),
                float(m["temp_chip"] or 0),
                float(m["temp_board"] or 0),
                firmware=m["firmware_manufacturer"] or ""
            )
            if pred:
                predictions.append(pred)
        except Exception as e:
            logger.debug("Prediction error for %s: %s", m["ip"], e)

    if predictions:
        logger.info("Predictions: %d miners showing pre-failure signals", len(predictions))
        _save_predictions(predictions)
    return predictions


def _predict_miner(miner_id: str, ip: str, model: str,
                   current_hr: float, current_chip_temp: float,
                   current_board_temp: float,
                   firmware: str = "") -> Optional[Dict[str, Any]]:
    conn = get_db()

    # Hashrate + chip temp history
    history = conn.execute("""
        SELECT mr.hashrate_pct, mr.temp_chip, mr.temp_board, mr.uptime
        FROM miner_readings mr
        JOIN scans s ON mr.scan_id=s.id
        WHERE mr.miner_id=? AND mr.status='online' AND mr.hashrate_pct IS NOT NULL
        ORDER BY s.scanned_at DESC LIMIT ?
    """, (miner_id, max(TREND_WINDOW, VOLATILITY_WINDOW)+5)).fetchall()

    if len(history) < MIN_SCANS_FOR_PRED:
        conn.close()
        return None

    # Latest board readings (voltage, freq, temp_board, hw_errors per board)
    boards = conn.execute("""
        SELECT c.board_index, c.rate_mhs, c.voltage, c.freq_mhz,
               c.temp_board, c.hw_errors
        FROM chain_readings c
        WHERE c.ip=? AND c.scan_id=(
            SELECT MAX(scan_id) FROM chain_readings WHERE ip=?
        )
    """, (ip, ip)).fetchall()

    # Pool rejection rate (last 10 scans)
    pool = conn.execute("""
        SELECT SUM(accepted) as acc, SUM(rejected) as rej
        FROM pool_readings WHERE miner_id=?
          AND scan_id IN (SELECT id FROM scans ORDER BY id DESC LIMIT 10)
    """, (miner_id,)).fetchone()

    # AMS alerts in last 24h
    ams_cutoff = (datetime.now() - timedelta(hours=AMS_ALERT_WINDOW_H)).isoformat()
    ams = conn.execute("""
        SELECT key, COUNT(*) as cnt FROM ams_notifications
        WHERE miner_ip=? AND recorded_at>=? GROUP BY key
    """, (ip, ams_cutoff)).fetchall()
    ams_counts = {r["key"]: r["cnt"] for r in ams}

    # State readings for max temps
    state_rows = conn.execute("""
        SELECT max_temp_board, max_temp_chip FROM miner_state_readings
        WHERE miner_id=? ORDER BY id DESC LIMIT 3
    """, (miner_id,)).fetchall()

    # HVAC context — is facility stressed?
    # Use the correct HVAC system based on miner model
    hvac_system = 's19jpro' if model and model.startswith('S19JPro') else 'warehouse'
    hvac = conn.execute("""
        SELECT supply_temp_f FROM hvac_readings WHERE system_id = ? ORDER BY recorded_at DESC LIMIT 1
    """, (hvac_system,)).fetchone()
    supply_temp = float(hvac["supply_temp_f"] or 0) if hvac else 0
    
    # Load hvac_correlation to check if facility stress actually correlates with flags
    hvac_corr = _load_knowledge().get("hvac_correlation", {})
    corr_value = hvac_corr.get("supply_temp_flag_correlation", 0)
    
    # Only consider facility stressed if:
    # 1. Supply temp is actually high (>80F), AND
    # 2. Historical correlation shows facility stress matters (>0.3)
    # If correlation is near zero or negative, HVAC stress doesn't cause flags
    facility_stressed = bool(supply_temp > 80.0 and corr_value > 0.3)

    conn.close()

    hashrates = [float(r["hashrate_pct"]) for r in history]
    chip_temps = [float(r["temp_chip"]) if r["temp_chip"] else None for r in history]
    uptimes    = [r["uptime"] for r in history]

    signals = []
    scores  = []

    # ── Signal 1: Hashrate trend decline ─────────────────────────────────────
    s, sig = _check_hashrate_trend(hashrates[:TREND_WINDOW])
    if sig: signals.append(sig); scores.append(s)

    # ── Signal 2: Volatility spike ────────────────────────────────────────────
    s, sig = _check_volatility(hashrates)
    if sig: signals.append(sig); scores.append(s)

    # ── Signal 3: Board rate imbalance ────────────────────────────────────────
    if boards:
        s, sig = _check_board_rate_imbalance(boards)
        if sig: signals.append(sig); scores.append(s)

    # ── Signal 4: Chip temp creep ─────────────────────────────────────────────
    valid_ct = [t for t in chip_temps[:TREND_WINDOW] if t and t > 0]
    if len(valid_ct) >= 3:
        s, sig = _check_temp_creep(valid_ct, facility_stressed)
        if sig: signals.append(sig); scores.append(s)

    # ── Signal 5: Historical pre-failure pattern match ────────────────────────
    s, sig = _check_pattern_match(miner_id, hashrates[:TREND_WINDOW])
    if sig: signals.append(sig); scores.append(s)

    is_auradine = "AURADINE" in firmware.upper()

    # ── Signal 6: Board voltage drop ─────────────────────────────────────────
    # Skip Auradine — they report ~0.29V which is firmware format, not real voltage
    if boards and not is_auradine:
        s, sig = _check_voltage_drop(boards)
        if sig: signals.append(sig); scores.append(s)

    # ── Signal 7: Board temp elevated ────────────────────────────────────────
    if boards:
        s, sig = _check_board_temps(boards, facility_stressed)
        if sig: signals.append(sig); scores.append(s)

    # ── Signal 8: Pool rejection rate spike ───────────────────────────────────
    if pool and pool["acc"] is not None:
        total_sh = (pool["acc"] or 0) + (pool["rej"] or 0)
        if total_sh > 0:
            rej_rate = float(pool["rej"] or 0) / total_sh
            s, sig = _check_rejection_rate(rej_rate)
            if sig: signals.append(sig); scores.append(s)

    # ── Signal 9: AMS alert spike ────────────────────────────────────────────
    s, sig = _check_ams_alerts(ams_counts)
    if sig: signals.append(sig); scores.append(s)

    # ── Signal 10: Uptime reset ───────────────────────────────────────────────
    s, sig = _check_uptime_reset(uptimes)
    if sig: signals.append(sig); scores.append(s)

    # ── Signal 11: Max temp trending high ────────────────────────────────────
    if state_rows:
        s, sig = _check_max_temp_trend(state_rows, facility_stressed)
        if sig: signals.append(sig); scores.append(s)

    # ── Signal 12: Board attach/detach events (chain_events in log_metrics) ──
    # Board cycling on/off is a strong pre-failure signal — only for BiXBiT miners
    s, sig = _check_chain_events(miner_id, ip)
    if sig: signals.append(sig); scores.append(s)

    if not signals:
        return None

    # Combine scores — each additional signal amplifies the base
    base = max(scores)
    bonus = sum(s * 0.10 for s in scores[1:])
    
    # Add fingerprint risk modifier (poor history = higher risk)
    fp_modifier = _get_fingerprint_risk_modifier(miner_id, ip)
    if fp_modifier > 0:
        signals.append(f"behavioral_risk: +{fp_modifier:.0f}pts from poor restart history")
    
    confidence = min(100, round(base + bonus + fp_modifier))

    if confidence < PRED_CONFIDENCE_MIN:
        return None

    action = "PREEMPTIVE_RESTART" if confidence >= PRED_CONFIDENCE_ACT else "MONITOR_CLOSE"

    return {
        "miner_id":     miner_id,
        "ip":           ip,
        "model":        model,
        "action":       action,
        "confidence":   confidence,
        "signals":      signals,
        "current_hr":   current_hr,
        "current_chip_temp":  current_chip_temp,
        "current_board_temp": current_board_temp,
        "predicted_at": datetime.now().isoformat()
    }


# ── Signal implementations ────────────────────────────────────────────────────

def _check_hashrate_trend(hrs: List[float]) -> Tuple[float, Optional[str]]:
    if len(hrs) < 3 or hrs[-1] <= 0: return 0.0, None
    drop = ((hrs[-1] - hrs[0]) / hrs[-1]) * 100
    if drop >= TREND_DROP_PCT:
        score = min(90.0, 50.0 + (drop - TREND_DROP_PCT) * 2.0)
        return score, f"hashrate declining {drop:.1f}% over {len(hrs)} scans ({hrs[-1]:.0f}%→{hrs[0]:.0f}%)"
    return 0.0, None


def _check_volatility(hrs: List[float]) -> Tuple[float, Optional[str]]:
    if len(hrs) < VOLATILITY_WINDOW + 2: return 0.0, None
    def cv(vals):
        m = sum(vals)/len(vals) if vals else 0
        return ((sum((v-m)**2 for v in vals)/len(vals))**0.5)/m if m > 0 else 0
    recent_cv   = cv(hrs[:3])
    baseline_cv = cv(hrs[3:VOLATILITY_WINDOW])
    if baseline_cv > 0 and recent_cv > baseline_cv * VOLATILITY_SPIKE:
        ratio = recent_cv / baseline_cv
        score = min(75.0, 40.0 + (ratio - VOLATILITY_SPIKE) * 10.0)
        return score, f"volatility {ratio:.1f}x above baseline (unstable hashrate)"
    return 0.0, None


def _check_board_rate_imbalance(boards) -> Tuple[float, Optional[str]]:
    rates = [(r["board_index"], float(r["rate_mhs"] or 0)) for r in boards if float(r["rate_mhs"] or 0) > 0]
    if len(rates) < 2: return 0.0, None
    mean = sum(r for _, r in rates) / len(rates)
    for bidx, rate in rates:
        dev = abs(rate - mean) / mean * 100
        if dev >= BOARD_IMBALANCE_PCT:
            score = min(80.0, 50.0 + (dev - BOARD_IMBALANCE_PCT))
            return score, f"board {bidx} rate {dev:.0f}% {'low' if rate<mean else 'high'} vs others"
    return 0.0, None


def _check_temp_creep(temps: List[float], facility_stressed: bool) -> Tuple[float, Optional[str]]:
    if len(temps) < 3 or facility_stressed: return 0.0, None  # skip if facility is causing it
    rise = temps[0] - temps[-1]
    if rise >= TEMP_CREEP_C:
        score = min(70.0, 40.0 + (rise - TEMP_CREEP_C) * 5.0)
        return score, f"chip temp creeping +{rise:.1f}°C over {len(temps)} scans ({temps[-1]:.0f}→{temps[0]:.0f}°C)"
    return 0.0, None


def _check_pattern_match(miner_id: str, recent_hrs: List[float]) -> Tuple[float, Optional[str]]:
    conn = get_db()
    failures = conn.execute("""
        SELECT restarted_at FROM miner_restarts
        WHERE miner_id=? AND outcome='FAILURE' ORDER BY restarted_at DESC LIMIT 5
    """, (miner_id,)).fetchall()
    if not failures:
        conn.close()
        return 0.0, None
    best = 0.0
    for f in failures:
        pre = conn.execute("""
            SELECT mr.hashrate_pct FROM miner_readings mr
            JOIN scans s ON mr.scan_id=s.id
            WHERE mr.miner_id=? AND s.scanned_at<? AND mr.hashrate_pct IS NOT NULL
            ORDER BY s.scanned_at DESC LIMIT 5
        """, (miner_id, f["restarted_at"])).fetchall()
        if len(pre) >= 3:
            pattern = [float(r["hashrate_pct"]) for r in pre]
            best = max(best, _trend_similarity(recent_hrs[:len(pattern)], pattern))
    conn.close()
    if best >= 0.75:
        return min(85.0, best*85.0), f"matches pre-failure pattern ({best:.0%} similarity)"
    return 0.0, None


def _check_voltage_drop(boards) -> Tuple[float, Optional[str]]:
    low = [(r["board_index"], float(r["voltage"])) for r in boards
           if r["voltage"] and 0 < float(r["voltage"]) < VOLTAGE_DROP_V]
    if low:
        score = min(85.0, 60.0 + len(low) * 10.0)
        detail = ", ".join(f"board {b}={v:.3f}V" for b, v in low)
        return score, f"low board voltage ({detail} < {VOLTAGE_DROP_V}V)"
    return 0.0, None


def _check_board_temps(boards, facility_stressed: bool) -> Tuple[float, Optional[str]]:
    if facility_stressed: return 0.0, None
    hot = [(r["board_index"], float(r["temp_board"])) for r in boards
           if r["temp_board"] and float(r["temp_board"]) > BOARD_TEMP_WARN_C]
    if hot:
        max_t = max(t for _, t in hot)
        score = min(75.0, 40.0 + (max_t - BOARD_TEMP_WARN_C) * 2.0)
        detail = ", ".join(f"board {b}={t:.0f}°C" for b, t in hot)
        return score, f"elevated board temps ({detail})"
    return 0.0, None


def _check_rejection_rate(rej_rate: float) -> Tuple[float, Optional[str]]:
    if rej_rate >= REJ_RATE_HIGH:
        score = min(65.0, 40.0 + (rej_rate - REJ_RATE_HIGH) * 5000.0)
        return score, f"high pool rejection rate {rej_rate*100:.2f}% (>{REJ_RATE_HIGH*100:.1f}% threshold)"
    return 0.0, None


def _check_ams_alerts(ams_counts: dict) -> Tuple[float, Optional[str]]:
    hr_drops = ams_counts.get("hashrateDropLevel", 0)
    hot_bds  = ams_counts.get("hotBoard", 0)
    offlines = ams_counts.get("workerOffline", 0)
    alerts, score = [], 0.0
    if hr_drops >= 2:
        score += min(40.0, hr_drops * 10.0)
        alerts.append(f"{hr_drops}x hashrate drop alerts")
    if hot_bds >= 2:
        score += min(35.0, hot_bds * 8.0)
        alerts.append(f"{hot_bds}x hot board alerts")
    if offlines >= 3:
        score += min(30.0, offlines * 5.0)
        alerts.append(f"{offlines}x offline alerts")
    if alerts:
        return min(80.0, score), f"AMS alert spike 24h: {', '.join(alerts)}"
    return 0.0, None


def _check_uptime_reset(uptimes: List[str]) -> Tuple[float, Optional[str]]:
    def parse(s):
        if not s: return None
        try:
            d = int(re.search(r'(\d+)d', s).group(1)) if 'd' in s else 0
            h = int(re.search(r'(\d+)h', s).group(1)) if 'h' in s else 0
            m = int(re.search(r'(\d+)m', s).group(1)) if 'm' in s else 0
            return d*86400 + h*3600 + m*60
        except Exception: return None
    secs = [parse(u) for u in uptimes if u]
    secs = [s for s in secs if s is not None]
    if len(secs) < 2: return 0.0, None
    if secs[0] < secs[1] * 0.3 and secs[1] > 3600:
        return 60.0, f"unscheduled reboot (uptime reset {secs[1]//3600}h→{secs[0]//60}m)"
    return 0.0, None


def _check_max_temp_trend(state_rows, facility_stressed: bool) -> Tuple[float, Optional[str]]:
    if facility_stressed: return 0.0, None
    max_bds = [float(r["max_temp_board"]) for r in state_rows if r["max_temp_board"]]
    if max_bds and max_bds[0] > MAX_BOARD_TEMP_WARN:
        score = min(70.0, 40.0 + (max_bds[0] - MAX_BOARD_TEMP_WARN) * 3.0)
        return score, f"max board temp {max_bds[0]:.0f}°C approaching thermal limit"
    return 0.0, None


def _check_chain_events(miner_id: str, ip: str) -> Tuple[float, Optional[str]]:
    """
    Signal 12: Detect board attach/detach cycling in log_metrics.
    Board detach events = boards going offline temporarily — strong pre-failure signal.
    Only available for BiXBiT firmware miners that export log data.
    Checks last 24 hours of chain_events.
    """
    conn = get_db()
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    rows = conn.execute("""
        SELECT text_value as event, board_index, COUNT(*) as cnt
        FROM log_metrics
        WHERE ip=? AND metric_type='chain_event' AND recorded_at>=?
        GROUP BY text_value, board_index
        ORDER BY cnt DESC
    """, (ip, cutoff)).fetchall()
    conn.close()

    if not rows:
        return 0.0, None

    detach_counts = {r["board_index"]: r["cnt"] for r in rows if r["event"] == "detached"}
    total_detaches = sum(detach_counts.values())

    if total_detaches >= 50:
        # High detach rate — boards cycling rapidly
        score = min(85.0, 50.0 + (total_detaches - 50) * 0.3)
        worst_board = max(detach_counts, key=detach_counts.get)
        return score, (f"board cycling: {total_detaches} detach events in 24h "
                      f"(board {worst_board}: {detach_counts[worst_board]}x)")
    elif total_detaches >= 10:
        score = min(65.0, 40.0 + total_detaches * 0.5)
        return score, f"board instability: {total_detaches} detach events in 24h"
    return 0.0, None


def _trend_similarity(a: List[float], b: List[float]) -> float:
    n = min(len(a), len(b))
    if n < 2: return 0.0
    def norm(s): m=sum(s)/len(s); return [v/m for v in s] if m else s
    def deltas(s): return [s[i]-s[i+1] for i in range(len(s)-1)]
    ad, bd = deltas(norm(a[:n])), deltas(norm(b[:n]))
    agreed = sum(1 for x,y in zip(ad,bd) if (x>=0)==(y>=0))
    return agreed/len(ad) if ad else 0.0


def _save_predictions(predictions: List[Dict[str, Any]]):
    try:
        path = Path(KNOWLEDGE_PATH)
        knowledge = json.loads(path.read_text()) if path.exists() else {}
        preds = knowledge.setdefault("predictions", [])
        for p in predictions:
            preds.append({**p, "outcome": None, "accurate": None})
        knowledge["predictions"] = preds[-200:]
        path.write_text(json.dumps(knowledge, indent=2))
    except Exception as e:
        logger.warning("Could not save predictions: %s", e)


def get_prediction_accuracy() -> Dict[str, Any]:
    try:
        path = Path(KNOWLEDGE_PATH)
        if not path.exists(): return {"error": "No knowledge.json"}
        preds = json.loads(path.read_text()).get("predictions", [])
        total    = len(preds)
        accurate = sum(1 for p in preds if p.get("accurate") is True)
        pending  = sum(1 for p in preds if p.get("accurate") is None)
        scored   = total - pending
        return {
            "total": total, "accurate": accurate, "pending": pending,
            "accuracy_pct": round(accurate/scored*100, 1) if scored > 0 else None
        }
    except Exception as e:
        return {"error": str(e)}


def format_prediction_alert(pred: Dict[str, Any]) -> str:
    label = {"MONITOR_CLOSE": "👁️ *WATCH CLOSELY*",
             "PREEMPTIVE_RESTART": "⚡ *PREEMPTIVE RESTART RECOMMENDED*"}.get(pred["action"], pred["action"])
    lines = [
        f"{label} — `{pred['ip']}` ({pred['model']})",
        f"  Confidence: *{pred['confidence']}%* | HR: {pred['current_hr']:.1f}% | "
        f"Chip: {pred['current_chip_temp']:.0f}°C | Board: {pred['current_board_temp']:.0f}°C",
        f"  Signals:"
    ]
    for sig in pred["signals"]:
        lines.append(f"    • {sig}")
    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    conn = get_db()
    scan = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if scan:
        logger.info("Running predictions on scan %d (all 11 signals)...", scan["id"])
        preds = run_predictions(scan["id"])
        if preds:
            print(f"\n{len(preds)} prediction(s):\n")
            for p in preds:
                print(format_prediction_alert(p))
                print()
        else:
            print("\nNo pre-failure signals — fleet looks healthy.")
    print(f"Accuracy: {get_prediction_accuracy()}")
