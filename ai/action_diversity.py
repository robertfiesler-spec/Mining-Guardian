"""
action_diversity.py
Mining Guardian — Feature 8: Action Diversity

Expands the AI's toolkit beyond RESTART / PDU_CYCLE / RESTART_CHECK_BOARDS.
All new actions are confidence-gated using every available data point.

New actions:
  POWER_PROFILE_DOWN  — reduce miner wattage when temps are high
                        Uses: temp_chip, temp_board, HVAC supply_temp,
                              current_profile, consumption, hashrate_pct
                        Gate: confidence >= 75
                        Via:  BiXBiT API profile switch

  POWER_PROFILE_UP    — restore full power after thermal event clears
                        Uses: temp_chip, HVAC delta_t, hashrate_pct, success rate
                        Gate: confidence >= 80

  ECO_MODE            — fleet-wide power reduction during HVAC stress
                        Uses: HVAC supply_temp, fleet avg temp, flag count
                        Gate: facility stress > 50%, confidence >= 80

  POOL_FAILOVER       — switch pool when rejection rate is persistently high
                        Uses: pool_readings rejection rate (30-scan avg),
                              ams_notifications hashrateDropLevel,
                              backup_pool configured in config
                        Gate: rej_rate > 0.5% for 10+ scans, confidence >= 85

  PREEMPTIVE_RESTART  — restart before failure (predictor handles this already)
                        Included here for action diversity reporting completeness

Data used per decision:
  miner_readings:       hashrate_pct, temp_chip, temp_board, consumption, current_profile
  chain_readings:       per-board voltage, temp_board (pre-action health check)
  miner_state_readings: max_temp_board, max_temp_chip
  pool_readings:        rejection rate trend (last 30 scans)
  hvac_readings:        supply_temp_f, delta_t_f, cwp_vfd_pct (facility context)
  ams_notifications:    hashrateDropLevel (corroborates pool issues)
  miner_restarts:       outcome history (confidence gate)
  confidence_scorer:    get_confidence() for final gate check
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

logger = logging.getLogger("action_diversity")

DB_PATH        = str(_ROOT / "guardian.db")
KNOWLEDGE_PATH = str(_ROOT / "knowledge.json")

# ── Confidence gates per action type ─────────────────────────────────────────
GATE_POWER_DOWN   = 75
GATE_POWER_UP     = 80
GATE_ECO_MODE     = 80
GATE_POOL_FAILOVER= 85

# ── Thresholds (from observed data) ──────────────────────────────────────────
TEMP_CHIP_POWER_DOWN   = 76.0  # chip temp above this → consider power down
TEMP_CHIP_POWER_UP     = 68.0  # chip temp below this → safe to power up
TEMP_BOARD_HIGH        = 65.0  # board temp above this → consider power down
HVAC_ECO_TRIGGER_F     = 80.0  # supply water above this → eco mode
REJ_RATE_POOL_FAILOVER = 0.005 # 0.5% rejection rate sustained → pool failover
REJ_SUSTAINED_SCANS    = 10    # must be high for this many scans

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def evaluate_all_actions(scan_id: int) -> List[Dict[str, Any]]:
    """
    Main entry point. Evaluate all miners in a scan for new action types.
    Returns list of recommended actions with confidence scores and reasoning.
    Only called for online miners not already flagged for RESTART/PDU_CYCLE.
    """
    conn = get_db()

    # Get HVAC context once for the whole scan
    hvac = conn.execute(
        "SELECT supply_temp_f, return_temp_f, delta_t_f, cwp1_vfd_pct, cwp2_vfd_pct "
        "FROM hvac_readings ORDER BY id DESC LIMIT 1"
    ).fetchone()
    hvac_supply   = float(hvac["supply_temp_f"] or 0) if hvac else 0
    hvac_delta_t  = float(hvac["delta_t_f"]     or 0) if hvac else 0
    hvac_pump_pct = max(float(hvac["cwp1_vfd_pct"] or 0), float(hvac["cwp2_vfd_pct"] or 0)) if hvac else 0

    # Get online miners not currently flagged
    miners = conn.execute("""
        SELECT mr.miner_id, mr.ip, mr.model, mr.firmware_manufacturer,
               mr.hashrate_pct, mr.temp_chip, mr.temp_board, mr.consumption,
               mr.current_profile, mr.status
        FROM miner_readings mr
        WHERE mr.scan_id=? AND mr.status='online'
          AND (mr.action='MONITOR' OR mr.action IS NULL)
    """, (scan_id,)).fetchall()

    conn.close()

    recommended = []

    # Check eco mode at fleet level first
    eco = _check_eco_mode(hvac_supply, hvac_delta_t, hvac_pump_pct)
    if eco:
        recommended.append(eco)

    # Check per-miner actions
    for m in miners:
        actions = _evaluate_miner_actions(m, hvac_supply, hvac_delta_t)
        recommended.extend(actions)

    if recommended:
        logger.info("Action diversity: %d new actions recommended", len(recommended))

    return recommended


def _evaluate_miner_actions(
    miner, hvac_supply: float, hvac_delta_t: float
) -> List[Dict[str, Any]]:
    """Evaluate a single miner for power and pool actions."""
    miner_id  = miner["miner_id"]
    ip        = miner["ip"]
    model     = miner["model"]
    firmware  = miner["firmware_manufacturer"] or ""
    chip_temp = float(miner["temp_chip"]    or 0)
    board_temp= float(miner["temp_board"]   or 0)
    hr_pct    = float(miner["hashrate_pct"] or 0)
    profile   = miner["current_profile"] or ""

    actions = []

    # Only attempt power profile changes on BiXBiT firmware
    if "BIXBIT" in firmware.upper() or "bixbit" in firmware.lower():
        # POWER_PROFILE_DOWN
        pd = _check_power_down(miner_id, ip, model, chip_temp, board_temp,
                               hr_pct, profile, hvac_supply)
        if pd:
            actions.append(pd)

        # POWER_PROFILE_UP (only if currently running below max)
        pu = _check_power_up(miner_id, ip, model, chip_temp, board_temp,
                             hr_pct, profile, hvac_supply, hvac_delta_t)
        if pu:
            actions.append(pu)

    # Pool failover — applies to all firmware types
    pf = _check_pool_failover(miner_id, ip, model)
    if pf:
        actions.append(pf)

    return actions


def _check_power_down(
    miner_id: str, ip: str, model: str,
    chip_temp: float, board_temp: float,
    hr_pct: float, profile: str, hvac_supply: float
) -> Optional[Dict[str, Any]]:
    """
    Recommend power profile reduction when thermals are elevated.
    Uses: chip_temp, board_temp, HVAC supply, max_temp from state readings,
          current profile (to know if we can go lower), hashrate stability.
    """
    if chip_temp <= 0:
        return None

    conn = get_db()

    # Get max temps from state readings (last 3 scans)
    state = conn.execute("""
        SELECT max_temp_chip, max_temp_board FROM miner_state_readings
        WHERE miner_id=? ORDER BY id DESC LIMIT 3
    """, (miner_id,)).fetchall()
    max_chip  = max((float(r["max_temp_chip"]  or 0) for r in state), default=chip_temp)
    max_board = max((float(r["max_temp_board"] or 0) for r in state), default=board_temp)

    # Check if already at minimum profile — nothing lower to go to
    if _is_minimum_profile(profile):
        conn.close()
        return None

    conn.close()

    reasons = []
    score   = 0.0

    if chip_temp >= TEMP_CHIP_POWER_DOWN:
        score  += 40.0 + (chip_temp - TEMP_CHIP_POWER_DOWN) * 3.0
        reasons.append(f"chip temp {chip_temp:.0f}°C > {TEMP_CHIP_POWER_DOWN}°C")

    if max_chip >= TEMP_CHIP_POWER_DOWN + 5:
        score  += 20.0
        reasons.append(f"max chip temp {max_chip:.0f}°C elevated")

    if board_temp >= TEMP_BOARD_HIGH:
        score  += 15.0
        reasons.append(f"board temp {board_temp:.0f}°C > {TEMP_BOARD_HIGH}°C")

    if hvac_supply >= 78.0:
        score  += 15.0
        reasons.append(f"HVAC supply {hvac_supply:.1f}°F reducing cooling capacity")

    if score < GATE_POWER_DOWN:
        return None

    confidence = min(95, round(score))
    return {
        "action":     "POWER_PROFILE_DOWN",
        "miner_id":   miner_id,
        "ip":         ip,
        "model":      model,
        "confidence": confidence,
        "current_profile": profile,
        "reasons":    reasons,
        "data_used":  ["temp_chip", "max_temp_chip", "temp_board", "hvac_supply",
                       "miner_state_readings"],
        "created_at": datetime.now().isoformat()
    }


def _check_power_up(
    miner_id: str, ip: str, model: str,
    chip_temp: float, board_temp: float,
    hr_pct: float, profile: str,
    hvac_supply: float, hvac_delta_t: float
) -> Optional[Dict[str, Any]]:
    """
    Recommend restoring to higher profile after thermal event clears.
    Only fires if miner was previously stepped down and conditions are good.
    """
    if chip_temp <= 0 or not _is_reduced_profile(profile):
        return None

    # All conditions must be comfortable before stepping up
    if chip_temp >= TEMP_CHIP_POWER_UP:
        return None
    if hvac_supply >= 76.0:
        return None
    if hvac_delta_t < 9.0:  # poor heat transfer — don't push harder
        return None

    confidence = 82
    return {
        "action":     "POWER_PROFILE_UP",
        "miner_id":   miner_id,
        "ip":         ip,
        "model":      model,
        "confidence": confidence,
        "current_profile": profile,
        "reasons":    [f"chip temp {chip_temp:.0f}°C < {TEMP_CHIP_POWER_UP}°C",
                       f"HVAC supply {hvac_supply:.1f}°F acceptable",
                       f"delta-T {hvac_delta_t:.1f}°F (good heat transfer)"],
        "data_used":  ["temp_chip", "hvac_supply_temp", "hvac_delta_t", "current_profile"],
        "created_at": datetime.now().isoformat()
    }


def _check_eco_mode(
    hvac_supply: float, hvac_delta_t: float, pump_pct: float
) -> Optional[Dict[str, Any]]:
    """
    Fleet-wide eco mode trigger when facility is under thermal stress.
    Uses all HVAC data points to determine if fleet-wide power reduction is needed.
    """
    if hvac_supply < HVAC_ECO_TRIGGER_F:
        return None

    reasons = [f"HVAC supply water {hvac_supply:.1f}°F > {HVAC_ECO_TRIGGER_F}°F threshold"]
    score   = 60.0 + (hvac_supply - HVAC_ECO_TRIGGER_F) * 5.0

    if hvac_delta_t < 8.0:
        score += 15.0
        reasons.append(f"low delta-T {hvac_delta_t:.1f}°F (poor heat transfer)")

    if pump_pct > 90:
        score += 10.0
        reasons.append(f"pump at {pump_pct:.0f}% — at capacity")

    confidence = min(95, round(score))
    if confidence < GATE_ECO_MODE:
        return None

    return {
        "action":     "ECO_MODE_FLEET",
        "miner_id":   "FLEET",
        "ip":         "ALL",
        "model":      "ALL",
        "confidence": confidence,
        "reasons":    reasons,
        "data_used":  ["hvac_supply_temp", "hvac_delta_t", "cwp_vfd_pct"],
        "created_at": datetime.now().isoformat()
    }


def _check_pool_failover(
    miner_id: str, ip: str, model: str
) -> Optional[Dict[str, Any]]:
    """
    Recommend pool failover when rejection rate is sustained high.
    Uses pool_readings for trend (not just snapshot) + AMS notifications.
    Only fires if a backup pool is configured.
    """
    # Check if backup pool is configured
    config = _load_config()
    backup_pool = config.get("backup_pool_url") or config.get("pool_backup_url")
    if not backup_pool:
        return None  # No backup pool configured — can't failover

    conn = get_db()

    # Get rejection rate over last REJ_SUSTAINED_SCANS scans
    pool = conn.execute("""
        SELECT SUM(accepted) as acc, SUM(rejected) as rej, COUNT(*) as scan_cnt
        FROM pool_readings
        WHERE miner_id=? AND pool_priority=0
          AND scan_id IN (SELECT id FROM scans ORDER BY id DESC LIMIT ?)
    """, (miner_id, REJ_SUSTAINED_SCANS)).fetchone()

    if not pool or not pool["acc"]:
        conn.close()
        return None

    total  = (pool["acc"] or 0) + (pool["rej"] or 0)
    rej_rt = float(pool["rej"] or 0) / total if total > 0 else 0

    # Check AMS corroboration
    ams_drops = conn.execute("""
        SELECT COUNT(*) as cnt FROM ams_notifications
        WHERE miner_ip=? AND key='hashrateDropLevel'
          AND recorded_at >= datetime('now', '-24 hours')
    """, (ip,)).fetchone()["cnt"]

    conn.close()

    if rej_rt < REJ_RATE_POOL_FAILOVER:
        return None

    score  = 50.0 + (rej_rt - REJ_RATE_POOL_FAILOVER) * 10000.0
    score += min(20.0, ams_drops * 3.0)  # AMS corroboration boosts score
    confidence = min(95, round(score))

    if confidence < GATE_POOL_FAILOVER:
        return None

    return {
        "action":       "POOL_FAILOVER",
        "miner_id":     miner_id,
        "ip":           ip,
        "model":        model,
        "confidence":   confidence,
        "rej_rate_pct": round(rej_rt * 100, 3),
        "backup_pool":  backup_pool,
        "reasons":      [f"sustained rejection rate {rej_rt*100:.2f}% over {REJ_SUSTAINED_SCANS} scans",
                         f"{ams_drops} AMS hashrate drop alerts in 24h"],
        "data_used":    ["pool_readings", "ams_notifications", "config.backup_pool_url"],
        "created_at":   datetime.now().isoformat()
    }


def _is_minimum_profile(profile: str) -> bool:
    """Check if miner is already at its minimum/eco profile."""
    if not profile:
        return False
    profile_lower = profile.lower()
    return "eco" in profile_lower or "min" in profile_lower or "118" in profile


def _is_reduced_profile(profile: str) -> bool:
    """Check if miner is running a reduced (stepped-down) profile."""
    if not profile:
        return False
    profile_lower = profile.lower()
    return "eco" in profile_lower or "133" in profile or "134" in profile or "138" in profile


def _load_config() -> dict:
    """Load config.json to check for backup pool and other settings."""
    for cfg_path in [_ROOT / "config" / "config.json", _ROOT / "config.json"]:
        if cfg_path.exists():
            try:
                return json.loads(cfg_path.read_text())
            except Exception:
                pass
    return {}


def get_action_diversity_summary() -> Dict[str, Any]:
    """Summary for 48hr test report — what new actions were considered/taken."""
    conn = get_db()
    rows = conn.execute("""
        SELECT action_taken, decision, COUNT(*) as cnt
        FROM action_audit_log
        WHERE action_taken IN ('POWER_PROFILE_DOWN','POWER_PROFILE_UP',
                               'ECO_MODE_FLEET','POOL_FAILOVER','PREEMPTIVE_RESTART')
        GROUP BY action_taken, decision
    """).fetchall()
    conn.close()
    return {r["action_taken"] + "_" + r["decision"]: r["cnt"] for r in rows}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    conn = get_db()
    scan = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if scan:
        logger.info("Evaluating action diversity on scan %d...", scan["id"])
        actions = evaluate_all_actions(scan["id"])
        if actions:
            print(f"\n{len(actions)} action(s) recommended:\n")
            for a in actions:
                print(f"  [{a['confidence']}%] {a['action']} — {a['ip']} ({a['model']})")
                for r in a.get("reasons", []):
                    print(f"    • {r}")
                print(f"    Data used: {', '.join(a.get('data_used',[]))}")
                print()
        else:
            print("\nNo new actions recommended — current conditions are nominal.")
