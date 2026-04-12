"""
fingerprint_builder.py — v2
Mining Guardian — Feature 4: Miner Fingerprinting (Full Data)

Uses EVERY available data point:
  miner_readings:       hashrate, temp_chip, temp_board, uptime, error_codes, consumption
  chain_readings:       per-board voltage, freq_mhz, temp_board, hw_errors, consumption_w
  miner_state_readings: hashrate_medium/low, max_temp_board, max_temp_chip
  pool_readings:        rejection rate
  miner_hardware:       chip_bin, bad_chips_count, pcb_version, ideal_hashrate
  ams_notifications:    hashrateDropLevel, hotBoard, consumptionChangeLevel counts
  miner_restarts:       outcome history
  known_dead_boards:    confirmed hardware failures
"""

import sys
import json
import logging
import sqlite3
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT / "core"), str(_ROOT / "ai")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logger = logging.getLogger("fingerprint_builder")

DB_PATH        = str(_ROOT / "guardian.db")
KNOWLEDGE_PATH = str(_ROOT / "knowledge.json")
LOOKBACK_DAYS  = 30
MIN_RESTARTS_FOR_RATE = 2


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def build_all_fingerprints() -> dict:
    conn = get_db()
    miners = conn.execute("""
        SELECT DISTINCT miner_id, ip, model FROM miner_readings
        WHERE miner_id IS NOT NULL ORDER BY ip
    """).fetchall()
    conn.close()

    if not miners:
        return {"built": 0, "miners": []}

    knowledge = _load_knowledge()
    fingerprints = knowledge.setdefault("miner_fingerprints", {})

    built = []
    for m in miners:
        try:
            fp = _build_fingerprint(m["miner_id"], m["ip"], m["model"])
            fingerprints[m["miner_id"]] = fp
            built.append(m["ip"])
        except Exception as e:
            logger.warning("Fingerprint failed for %s: %s", m["ip"], e)

    knowledge["miner_fingerprints"] = fingerprints
    knowledge["fingerprints_updated_at"] = datetime.now().isoformat()
    _save_knowledge(knowledge)
    logger.info("Built %d miner fingerprints", len(built))
    return {"built": len(built), "miners": built}


def _parse_uptime_secs(s: str) -> Optional[int]:
    if not s: return None
    try:
        d = int(re.search(r'(\d+)d', s).group(1)) if 'd' in s else 0
        h = int(re.search(r'(\d+)h', s).group(1)) if 'h' in s else 0
        m = int(re.search(r'(\d+)m', s).group(1)) if 'm' in s else 0
        return d*86400 + h*3600 + m*60
    except Exception:
        return None


def _build_fingerprint(miner_id: str, ip: str, model: str) -> Dict[str, Any]:
    conn = get_db()
    cutoff = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).isoformat()

    # ── 1. Restart outcomes ───────────────────────────────────────────────────
    restarts = conn.execute("""
        SELECT outcome, recovery_time_scans FROM miner_restarts
        WHERE miner_id=? AND restarted_at>=? ORDER BY restarted_at DESC
    """, (miner_id, cutoff)).fetchall()
    total_restarts = len(restarts)
    successes = sum(1 for r in restarts if r["outcome"] == "SUCCESS")
    failures  = sum(1 for r in restarts if r["outcome"] == "FAILURE")
    partials  = sum(1 for r in restarts if r["outcome"] == "PARTIAL")
    completed = successes + failures + partials
    success_rate = round((successes + partials*0.5)/completed, 3) if completed >= MIN_RESTARTS_FOR_RATE else None
    rec_times = [r["recovery_time_scans"] for r in restarts if r["recovery_time_scans"]]
    avg_recovery = round(sum(rec_times)/len(rec_times), 1) if rec_times else None

    # ── 2. Hashrate + temps + uptime + errors (miner_readings) ───────────────
    mr_rows = conn.execute("""
        SELECT hashrate_pct, temp_chip, temp_board, consumption, uptime, error_codes
        FROM miner_readings WHERE miner_id=? AND status='online' AND hashrate_pct>0
          AND scan_id IN (SELECT id FROM scans WHERE scanned_at>=? ORDER BY id DESC LIMIT 100)
        ORDER BY id DESC LIMIT 50
    """, (miner_id, cutoff)).fetchall()

    hashrates   = [float(r["hashrate_pct"]) for r in mr_rows]
    chip_temps  = [float(r["temp_chip"])  for r in mr_rows if r["temp_chip"]  and float(r["temp_chip"])  > 0]
    board_temps = [float(r["temp_board"]) for r in mr_rows if r["temp_board"] and float(r["temp_board"]) > 0]
    consumptions= [float(r["consumption"]) for r in mr_rows if r["consumption"] and float(r["consumption"]) > 0]
    error_codes_seen = [r["error_codes"] for r in mr_rows if r["error_codes"]]

    avg_hr         = round(sum(hashrates)/len(hashrates), 1) if hashrates else None
    avg_chip_temp  = round(sum(chip_temps)/len(chip_temps), 1) if chip_temps else None
    avg_board_temp = round(sum(board_temps)/len(board_temps), 1) if board_temps else None
    avg_consumption= round(sum(consumptions)/len(consumptions), 0) if consumptions else None

    # Hashrate stability (coefficient of variation)
    stability = None
    if len(hashrates) >= 3:
        mean = sum(hashrates)/len(hashrates)
        std  = (sum((h-mean)**2 for h in hashrates)/len(hashrates))**0.5
        cv   = std/mean if mean > 0 else 1.0
        stability = round(max(0.0, min(100.0, (1.0-cv*2.0)*100.0)), 1)

    # Uptime: detect resets (unscheduled reboots)
    uptime_secs = [_parse_uptime_secs(r["uptime"]) for r in mr_rows]
    uptime_secs = [s for s in uptime_secs if s is not None]
    uptime_resets = sum(
        1 for i in range(len(uptime_secs)-1)
        if uptime_secs[i] < uptime_secs[i+1] * 0.3 and uptime_secs[i+1] > 3600
    )
    latest_uptime_h = round(uptime_secs[0]/3600, 1) if uptime_secs else None

    # ── 3. Per-board data (chain_readings) ───────────────────────────────────
    board_rows = conn.execute("""
        SELECT board_index,
               AVG(voltage)      as avg_volt,
               MIN(voltage)      as min_volt,
               AVG(freq_mhz)     as avg_freq,
               AVG(temp_board)   as avg_board_temp,
               MAX(temp_board)   as max_board_temp,
               SUM(hw_errors)    as total_hw,
               AVG(rate_mhs)     as avg_rate,
               AVG(consumption_w)as avg_power_w
        FROM chain_readings WHERE miner_id=? AND scanned_at>=?
        GROUP BY board_index
    """, (miner_id, cutoff)).fetchall()

    board_profiles = {}
    for b in board_rows:
        board_profiles[str(b["board_index"])] = {
            "avg_voltage":     round(float(b["avg_volt"]  or 0), 3),
            "min_voltage":     round(float(b["min_volt"]  or 0), 3),
            "avg_freq_mhz":    round(float(b["avg_freq"]  or 0), 1),
            "avg_temp_board":  round(float(b["avg_board_temp"] or 0), 1),
            "max_temp_board":  round(float(b["max_board_temp"] or 0), 1),
            "total_hw_errors": int(b["total_hw"] or 0),
            "avg_rate_mhs":    round(float(b["avg_rate"] or 0), 0),
            "avg_power_w":     round(float(b["avg_power_w"] or 0), 0),
        }

    total_hw_errors = sum(b["total_hw_errors"] for b in board_profiles.values())
    voltages = [b["min_voltage"] for b in board_profiles.values() if b["min_voltage"] > 0]
    avg_voltage  = round(sum(voltages)/len(voltages), 3) if voltages else None
    min_voltage  = min(voltages) if voltages else None
    voltage_drop = bool(min_voltage and min_voltage < 14.2)

    freqs = [b["avg_freq_mhz"] for b in board_profiles.values() if b["avg_freq_mhz"] > 0]
    avg_freq_mhz = round(sum(freqs)/len(freqs), 1) if freqs else None

    board_max_temps = [b["max_temp_board"] for b in board_profiles.values() if b["max_temp_board"] > 0]
    max_board_temp_ever = max(board_max_temps) if board_max_temps else None

    # ── 4. State readings — hashrate distribution, max temps ─────────────────
    state = conn.execute("""
        SELECT AVG(max_temp_board)  as a_max_bd,
               AVG(max_temp_chip)   as a_max_chip,
               AVG(hashrate_medium) as a_hr_med,
               AVG(hashrate_low)    as a_hr_low
        FROM miner_state_readings WHERE miner_id=? AND scanned_at>=?
    """, (miner_id, cutoff)).fetchone()
    avg_max_board_temp = round(float(state["a_max_bd"]),   1) if state and state["a_max_bd"]   else None
    avg_max_chip_temp  = round(float(state["a_max_chip"]), 1) if state and state["a_max_chip"]  else None
    avg_hr_medium      = round(float(state["a_hr_med"]),   0) if state and state["a_hr_med"]    else None

    # ── 5. Pool rejection rate ────────────────────────────────────────────────
    pool = conn.execute("""
        SELECT SUM(accepted) as acc, SUM(rejected) as rej
        FROM pool_readings WHERE miner_id=? AND scanned_at>=?
    """, (miner_id, cutoff)).fetchone()
    rej_rate = None
    if pool and pool["acc"] is not None:
        total_shares = (pool["acc"] or 0) + (pool["rej"] or 0)
        rej_rate = round(float(pool["rej"] or 0)/total_shares, 5) if total_shares > 0 else 0.0

    # ── 6. AMS notifications ──────────────────────────────────────────────────
    ams = conn.execute("""
        SELECT key, COUNT(*) as cnt FROM ams_notifications
        WHERE miner_ip=? AND recorded_at>=? GROUP BY key
    """, (ip, cutoff)).fetchall()
    ams_counts = {r["key"]: r["cnt"] for r in ams}
    hashrate_drop_alerts = ams_counts.get("hashrateDropLevel", 0)
    hot_board_alerts     = ams_counts.get("hotBoard", 0)
    consumption_alerts   = ams_counts.get("consumptionChangeLevel", 0)
    offline_alerts       = ams_counts.get("workerOffline", 0)

    # ── 7. Hardware identity ──────────────────────────────────────────────────
    hw = conn.execute("""
        SELECT chip_bin, bad_chips_count, pcb_version, ideal_hashrate, asic_count
        FROM miner_hardware WHERE miner_id=? ORDER BY last_updated DESC LIMIT 1
    """, (miner_id,)).fetchone()
    chip_bin       = hw["chip_bin"]             if hw else None
    bad_chips      = int(hw["bad_chips_count"] or 0) if hw and hw["bad_chips_count"] is not None else 0
    ideal_hashrate = float(hw["ideal_hashrate"] or 0) if hw else None

    # ── 8. Flagging frequency ─────────────────────────────────────────────────
    flagged_cnt = conn.execute("""
        SELECT COUNT(*) as c FROM miner_readings WHERE miner_id=? AND issue IS NOT NULL
          AND scan_id IN (SELECT id FROM scans WHERE scanned_at>=?)
    """, (miner_id, cutoff)).fetchone()["c"]
    total_scans = conn.execute("""
        SELECT COUNT(*) as c FROM miner_readings WHERE miner_id=?
          AND scan_id IN (SELECT id FROM scans WHERE scanned_at>=?)
    """, (miner_id, cutoff)).fetchone()["c"]
    flag_freq = round(flagged_cnt/(LOOKBACK_DAYS/7.0), 2)

    # ── 8b. PDU power variance (miner_readings.pdu_power) ────────────────────
    pdu_rows = conn.execute("""
        SELECT pdu_power FROM miner_readings
        WHERE miner_id=? AND pdu_power > 0 AND scanned_at>=?
        ORDER BY id DESC LIMIT 50
    """, (miner_id, cutoff)).fetchall()
    pdu_readings = [float(r["pdu_power"]) for r in pdu_rows]
    avg_pdu_kw  = round(sum(pdu_readings)/len(pdu_readings), 3) if pdu_readings else None
    pdu_variance = None
    if len(pdu_readings) >= 3:
        mean = sum(pdu_readings)/len(pdu_readings)
        pdu_variance = round((sum((p-mean)**2 for p in pdu_readings)/len(pdu_readings))**0.5, 3)

    # ── 8c. Chain events (log_metrics — BiXBiT only) ─────────────────────────
    chain_evt_rows = conn.execute("""
        SELECT text_value as event, COUNT(*) as cnt
        FROM log_metrics WHERE ip=? AND metric_type='chain_event' AND recorded_at>=?
        GROUP BY text_value
    """, (ip, cutoff)).fetchall()
    chain_detaches = sum(r["cnt"] for r in chain_evt_rows if r["event"] == "detached")
    chain_attaches = sum(r["cnt"] for r in chain_evt_rows if r["event"] == "attached")

    # ── 9. Known issues ───────────────────────────────────────────────────────
    known_issues = []
    dead = conn.execute("""
        SELECT board_indices FROM known_dead_boards WHERE miner_id=? AND resolved_at IS NULL
    """, (miner_id,)).fetchone()
    if dead:                              known_issues.append(f"dead_boards:{dead['board_indices']}")
    if bad_chips > 0:                     known_issues.append(f"bad_chips:{bad_chips}")
    if voltage_drop:                      known_issues.append(f"low_voltage:{min_voltage:.3f}V")
    if error_codes_seen:                  known_issues.append("error_codes_present")
    if hot_board_alerts > 5:              known_issues.append(f"hot_board_alerts:{hot_board_alerts}")
    if uptime_resets > 2:                 known_issues.append(f"frequent_reboots:{uptime_resets}")
    if hashrate_drop_alerts > 5:          known_issues.append(f"hashrate_drop_alerts:{hashrate_drop_alerts}")
    if rej_rate and rej_rate > 0.008:     known_issues.append(f"high_rejection:{rej_rate*100:.2f}%")
    if max_board_temp_ever and max_board_temp_ever > 75: known_issues.append(f"high_board_temp:{max_board_temp_ever}C")
    if chain_detaches > 100:              known_issues.append(f"board_cycling:{chain_detaches}_detaches")

    # ── 9b. AMS extended data (location, pool) ───────────────────────────────
    ams_ext = conn.execute("""
        SELECT map_location_id, map_x, map_y, stratum_url
        FROM miner_ams_extended WHERE miner_id=? ORDER BY id DESC LIMIT 1
    """, (miner_id,)).fetchone()
    map_location_id = int(ams_ext["map_location_id"]) if ams_ext and ams_ext["map_location_id"] else None
    map_position = f"{ams_ext['map_x']},{ams_ext['map_y']}" if ams_ext and ams_ext["map_x"] else None
    stratum_url = ams_ext["stratum_url"] if ams_ext else None

    conn.close()

    # ── 10. Confidence modifier ───────────────────────────────────────────────
    modifier = 0.0
    if success_rate is not None:
        modifier += (success_rate - 0.5) * 0.40          # ±20% from restart success rate
    if stability is not None:
        modifier += (stability/100.0 - 0.5) * 0.20       # ±10% from hashrate stability
    if rej_rate is not None:
        modifier -= min(0.10, rej_rate * 12)              # up to -10% for high rejection
    if hashrate_drop_alerts > 0:
        modifier -= min(0.10, hashrate_drop_alerts * 0.01)
    if hot_board_alerts > 0:
        modifier -= min(0.08, hot_board_alerts * 0.008)
    if dead:        modifier -= 0.30
    if bad_chips > 0: modifier -= 0.05 * min(4, bad_chips)
    if uptime_resets > 0: modifier -= 0.05 * min(3, uptime_resets)
    if voltage_drop: modifier -= 0.15
    if chain_detaches > 100: modifier -= min(0.15, chain_detaches * 0.0003)  # up to -15% for board cycling
    modifier = round(max(-0.5, min(0.5, modifier)), 3)

    return {
        "miner_id":               miner_id,
        "ip":                     ip,
        "model":                  model,
        "restart_success_rate":   success_rate,
        "avg_recovery_time_scans":avg_recovery,
        "total_restarts":         total_restarts,
        "avg_hashrate_pct":       avg_hr,
        "hashrate_stability_score":stability,
        "avg_chip_temp_c":        avg_chip_temp,
        "avg_board_temp_c":       avg_board_temp,
        "avg_max_board_temp_c":   avg_max_board_temp,
        "avg_max_chip_temp_c":    avg_max_chip_temp,
        "max_board_temp_ever_c":  max_board_temp_ever,
        "avg_voltage":            avg_voltage,
        "min_voltage":            min_voltage,
        "voltage_drop_detected":  voltage_drop,
        "avg_freq_mhz":           avg_freq_mhz,
        "total_hw_errors":        total_hw_errors,
        "avg_consumption_w":      avg_consumption,
        "board_profiles":         board_profiles,
        "latest_uptime_hours":    latest_uptime_h,
        "uptime_resets_30d":      uptime_resets,
        "rejection_rate":         rej_rate,
        "hashrate_drop_alerts":   hashrate_drop_alerts,
        "hot_board_alerts":       hot_board_alerts,
        "consumption_alerts":     consumption_alerts,
        "offline_alerts":         offline_alerts,
        "chip_bin":               chip_bin,
        "bad_chips_count":        bad_chips,
        "ideal_hashrate":         ideal_hashrate,
        "error_codes_seen":       bool(error_codes_seen),
        "flag_frequency_per_week":flag_freq,
        "total_scans":            total_scans,
        "total_scans_flagged":    flagged_cnt,
        "known_issues":           known_issues,
        "confidence_modifier":    modifier,
        # Location data from miner_ams_extended
        "map_location_id":        map_location_id,
        "map_position":           map_position,
        "stratum_url":            stratum_url,
        # Chain events from log_metrics (board attach/detach cycles)
        "chain_detaches":         chain_detaches,
        "chain_attaches":         chain_attaches,
        "last_updated":           datetime.now().isoformat()
    }


def get_fingerprint(miner_id: str) -> Optional[Dict[str, Any]]:
    return _load_knowledge().get("miner_fingerprints", {}).get(miner_id)


def get_confidence_modifier(miner_id: str) -> float:
    fp = get_fingerprint(miner_id)
    return float(fp.get("confidence_modifier", 0.0)) if fp else 0.0


def print_fleet_fingerprints():
    fps = _load_knowledge().get("miner_fingerprints", {})
    if not fps:
        print("No fingerprints yet.")
        return
    print(f"\n{'='*110}")
    print(f"{'MINER FINGERPRINTS v2':^110}")
    print(f"{'='*110}")
    print(f"{'IP':<20} {'Succ':>5} {'Stab':>5} {'Volt':>6} {'Freq':>5} {'RejR':>6} "
          f"{'HW':>4} {'AMS↓':>4} {'HotBd':>5} {'Uptime':>7} {'Mod':>6}  Issues")
    print(f"{'-'*110}")
    for mid, fp in sorted(fps.items(), key=lambda x: x[1].get("ip", "")):
        rate   = f"{fp['restart_success_rate']*100:.0f}%" if fp.get("restart_success_rate") is not None else "N/A"
        stab   = f"{fp['hashrate_stability_score']:.0f}%" if fp.get("hashrate_stability_score") is not None else "N/A"
        volt   = f"{fp['min_voltage']:.2f}"  if fp.get("min_voltage")  else "N/A"
        freq   = f"{fp['avg_freq_mhz']:.0f}" if fp.get("avg_freq_mhz") else "N/A"
        rej    = f"{fp.get('rejection_rate',0)*100:.2f}%" if fp.get("rejection_rate") is not None else "N/A"
        hw     = str(fp.get("total_hw_errors", 0))
        ams    = str(fp.get("hashrate_drop_alerts", 0))
        hot    = str(fp.get("hot_board_alerts", 0))
        uptime = f"{fp['latest_uptime_hours']:.0f}h" if fp.get("latest_uptime_hours") else "N/A"
        mod    = f"{fp.get('confidence_modifier', 0):+.2f}"
        issues = ", ".join(fp.get("known_issues", [])) or "none"
        print(f"{fp.get('ip','?'):<20} {rate:>5} {stab:>5} {volt:>6} {freq:>5} {rej:>6} "
              f"{hw:>4} {ams:>4} {hot:>5} {uptime:>7} {mod:>6}  {issues[:50]}")
    print(f"{'='*110}\n")


def _load_knowledge() -> dict:
    path = Path(KNOWLEDGE_PATH)
    return json.loads(path.read_text()) if path.exists() else {}


def _save_knowledge(knowledge: dict):
    Path(KNOWLEDGE_PATH).write_text(json.dumps(knowledge, indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info("Building fingerprints v2 — all data points...")
    result = build_all_fingerprints()
    logger.info("Done: %d fingerprints", result["built"])
    print_fleet_fingerprints()
