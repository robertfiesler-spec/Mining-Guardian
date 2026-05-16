"""
hvac_correlator.py
Mining Guardian — Feature 5: HVAC/Environment Correlation

Correlates BAS/HVAC sensor data to miner behavior. Learns facility-level
patterns that affect the whole fleet simultaneously, distinguishing
facility problems from individual miner problems.

Key questions answered:
  - When supply water temp rises, how many miners flag within 2 scans%s
  - Is this miner flag caused by the facility or its own hardware%s
  - What HVAC thresholds historically precede fleet-wide hashrate drops%s

Runs:
  - After every scan (lightweight check for active facility events)
  - Weekly training includes HVAC correlation patterns

Outputs:
  - Facility event log in knowledge.json under facility_events
  - Per-scan context: "facility_stress_level" (0-100)
  - Slack alerts distinguish "Facility Alert" from "Miner Alert"
"""

import os
import sys
import json
import logging
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List

# Path setup MUST come before `from db_targets import ...` below — if this
# module is ever invoked directly rather than imported by a parent that
# already set sys.path, `core` won't be on sys.path yet. W14a regression
# 2026-05-12.
#
# Path X (2026-05-12): also add `_ROOT` itself (install root) so dotted
# imports like `from core.X import ...` work standalone too.
_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT), str(_ROOT / "core"), str(_ROOT / "ai")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Bare form (not `from core.db_targets`) since `core/` itself is on
# sys.path, not the install root.
from db_targets import operational_target  # noqa: E402

logger = logging.getLogger("hvac_correlator")

def _pg_dsn() -> str:
    """Operational Postgres DSN via core.db_targets.

    W14a (2026-05-12): delegated to the resolver. hvac_correlator reads
    operational hvac_readings + miner_readings + writes hvac_correlations.
    """
    return operational_target().dsn()


class _PgConnWrapper:
    """Thin wrapper over psycopg2 Connection with SQLite-style execute shortcut."""

    def __init__(self, dsn: str):
        self._conn = psycopg2.connect(dsn, cursor_factory=DictCursor)

    def execute(self, sql, params=()):
        cur = self._conn.cursor()
        cur.execute(sql, params)
        return cur

    def executemany(self, sql, seq_of_params):
        cur = self._conn.cursor()
        cur.executemany(sql, seq_of_params)
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
KNOWLEDGE_PATH = str(_ROOT / "knowledge.json")

# ── Thresholds that indicate facility stress ───────────────────────────────────
# Based on observed data: supply ~75°F, return ~87°F, delta-T ~11°F
SUPPLY_TEMP_WARN_F   = 78.0   # above this = cooling degrading
SUPPLY_TEMP_CRIT_F   = 82.0   # above this = serious cooling problem
DELTA_T_LOW_F        = 8.0    # below this = poor heat transfer
DIFF_PRESSURE_LOW    = 8.0    # below this = low flow rate
CWP_BOTH_LOW_PCT     = 30.0   # both pumps below this = reduced cooling

# Minimum miners flagging simultaneously to count as facility event
FLEET_FLAG_THRESHOLD = 3

# ── HVAC System Mapping ────────────────────────────────────────────────────────
# Maps miner model prefixes to their HVAC system
HVAC_SYSTEM_MAP = {
    's19jpro': ['S19JPro'],
    'warehouse': ['S21', 'S21e', 'S21 EXP', 'S21 Imm', 'AH3880'],
}

def get_hvac_system_for_model(model: str) -> str:
    """Return the HVAC system_id for a miner model. Default to warehouse."""
    for sys_id, prefixes in HVAC_SYSTEM_MAP.items():
        for prefix in prefixes:
            if model and model.startswith(prefix):
                return sys_id
    return 'warehouse'  # default

def get_db() -> "_PgConnWrapper":
    conn = _PgConnWrapper(_pg_dsn())
    return conn


def get_facility_stress_level(system_id: str = None, miner_model: str = None) -> tuple:
    """
    Calculate current facility stress level (0-100) from latest HVAC reading.
    Returns (stress_level, reasons_list).

    Args:
        system_id: Explicit HVAC system ('warehouse' or 's19jpro')
        miner_model: If provided, automatically selects the right HVAC system

    0-25  = Normal — no facility issues
    26-50 = Watch  — conditions degrading, monitor closely
    51-75 = Warning — facility stress, expect miner impacts
    76-100 = Critical — facility problem, treat fleet flags as facility-caused
    """
    # Determine which HVAC system to use
    if system_id is None:
        if miner_model:
            system_id = get_hvac_system_for_model(miner_model)
        else:
            system_id = 'warehouse'  # default

    conn = get_db()
    hvac = conn.execute("""
        SELECT * FROM hvac_readings 
        WHERE system_id = %s
        ORDER BY recorded_at DESC LIMIT 1
    """, (system_id,)).fetchone()
    conn.close()

    if not hvac:
        return 0, []

    stress = 0.0
    reasons = []

    supply = hvac["supply_temp_f"] or 0
    delta_t = hvac["delta_t_f"] or 0
    diff_p = hvac["diff_pressure"] or 0
    cwp1 = hvac["cwp1_vfd_pct"] or 0
    cwp2 = hvac["cwp2_vfd_pct"] or 0
    pump_fault = hvac["pump_fault"]
    leak_alarm = hvac["leak_alarm"]

    # Supply water temperature (most important indicator)
    if supply >= SUPPLY_TEMP_CRIT_F:
        stress += 50
        reasons.append(f"supply water CRITICAL {supply:.1f}°F (>{SUPPLY_TEMP_CRIT_F}°F)")
    elif supply >= SUPPLY_TEMP_WARN_F:
        stress += 30
        reasons.append(f"supply water elevated {supply:.1f}°F (>{SUPPLY_TEMP_WARN_F}°F)")

    # Delta-T — difference between return and supply (heat being removed)
    if delta_t < DELTA_T_LOW_F and supply > 70:
        stress += 20
        reasons.append(f"low delta-T {delta_t:.1f}°F (poor heat transfer)")

    # Differential pressure — indicates flow rate
    if diff_p < DIFF_PRESSURE_LOW:
        stress += 15
        reasons.append(f"low diff pressure {diff_p:.1f} PSI (restricted flow)")

    # Pump VFDs — if both pumps are low, cooling capacity is reduced
    max_pump = max(cwp1, cwp2)
    if max_pump < CWP_BOTH_LOW_PCT:
        stress += 15
        reasons.append(f"low pump output CWP1={cwp1:.0f}% CWP2={cwp2:.0f}%")

    # Alarms — hard indicators of facility problems
    if pump_fault:
        stress += 40
        reasons.append("PUMP FAULT alarm active")
    if leak_alarm:
        stress += 60
        reasons.append("LEAK ALARM active")

    stress_level = min(100, round(stress))
    return stress_level, reasons


def check_fleet_correlation(scan_id: int) -> Optional[Dict[str, Any]]:
    """
    After a scan, check if multiple miners flagging simultaneously
    correlates with facility stress. If so, log as a facility event.

    Returns a facility_event dict if detected, None otherwise.
    """
    conn = get_db()

    # Count flagged miners in this scan
    flagged = conn.execute("""
        SELECT COUNT(*) as cnt FROM miner_readings
        WHERE scan_id = %s AND issue IS NOT NULL AND issue != ''
    """, (scan_id,)).fetchone()["cnt"]

    if flagged < FLEET_FLAG_THRESHOLD:
        conn.close()
        return None

    # Get HVAC reading closest to this scan
    scan_time = conn.execute(
        "SELECT scanned_at FROM scans WHERE id = %s", (scan_id,)
    ).fetchone()["scanned_at"]

    hvac = conn.execute("""
        SELECT * FROM hvac_readings
        WHERE recorded_at <= %s
        ORDER BY recorded_at DESC LIMIT 1
    """, (scan_time,)).fetchone()

    if not hvac:
        conn.close()
        return None

    stress_level, reasons = get_facility_stress_level()

    # Only log as facility event if there's actual facility stress
    if stress_level < 26:
        conn.close()
        return None

    # Get previous scan's flagged count to see if this is new
    prev_scan = conn.execute(
        "SELECT id FROM scans WHERE id < %s ORDER BY id DESC LIMIT 1", (scan_id,)
    ).fetchone()
    prev_flagged = 0
    if prev_scan:
        prev_flagged = conn.execute("""
            SELECT COUNT(*) as cnt FROM miner_readings
            WHERE scan_id = %s AND issue IS NOT NULL AND issue != ''
        """, (prev_scan["id"],)).fetchone()["cnt"]

    conn.close()

    event = {
        "scan_id":       scan_id,
        "detected_at":   datetime.now(timezone.utc).isoformat(),
        "stress_level":  stress_level,
        "reasons":       reasons,
        "miners_flagged":flagged,
        "miners_flagged_prev": prev_flagged,
        "supply_temp_f": float(hvac["supply_temp_f"] or 0),
        "return_temp_f": float(hvac["return_temp_f"] or 0),
        "delta_t_f":     float(hvac["delta_t_f"] or 0),
        "diff_pressure": float(hvac["diff_pressure"] or 0),
    }

    _log_facility_event(event)
    logger.info(
        "Facility event detected: stress=%d%% miners_flagged=%d reasons=%s",
        stress_level, flagged, reasons
    )
    return event


def _log_facility_event(event: Dict[str, Any]):
    """Append facility event to knowledge.json."""
    try:
        from core.file_lock import locked_knowledge_update
        with locked_knowledge_update(KNOWLEDGE_PATH) as knowledge:
            events = knowledge.setdefault("facility_events", [])
            events.append(event)
            knowledge["facility_events"] = events[-100:]
    except Exception as e:
        logger.warning("Could not log facility event: %s", e)


def get_hvac_correlation_patterns(lookback_days: int = 30) -> Dict[str, Any]:
    """
    Analyze historical HVAC data vs miner flagging rate.
    Used by weekly training to add HVAC correlation patterns to knowledge.
    """
    conn = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()

    # Join scans with HVAC readings and flagged miner counts
    rows = conn.execute("""
        SELECT
            s.id as scan_id,
            s.scanned_at,
            s.issues as miners_flagged,
            h.supply_temp_f,
            h.return_temp_f,
            h.delta_t_f,
            h.diff_pressure,
            h.cwp2_vfd_pct,
            w.temp_f as outside_temp_f
        FROM scans s
        LEFT JOIN hvac_readings h ON (
            h.recorded_at = (
                SELECT recorded_at FROM hvac_readings
                WHERE recorded_at <= s.scanned_at
                ORDER BY recorded_at DESC LIMIT 1
            )
        )
        LEFT JOIN weather_readings w ON (
            w.recorded_at = (
                SELECT recorded_at FROM weather_readings
                WHERE recorded_at <= s.scanned_at
                ORDER BY recorded_at DESC LIMIT 1
            )
        )
        WHERE s.scanned_at >= %s
        ORDER BY s.scanned_at
    """, (cutoff,)).fetchall()

    conn.close()

    if len(rows) < 10:
        return {"error": "Not enough data for correlation analysis"}

    # Group by supply temp bucket and compute avg flags
    buckets: Dict[str, list] = {}
    for r in rows:
        if r["supply_temp_f"] is None:
            continue
        t = float(r["supply_temp_f"])
        bucket = f"{int(t//2)*2}-{int(t//2)*2+2}°F"
        buckets.setdefault(bucket, []).append(r["miners_flagged"] or 0)

    supply_vs_flags = {
        bucket: round(sum(vals)/len(vals), 1)
        for bucket, vals in sorted(buckets.items()) if len(vals) >= 3
    }

    # Compute overall correlation strength
    supply_temps = [float(r["supply_temp_f"]) for r in rows if r["supply_temp_f"]]
    flag_counts  = [r["miners_flagged"] or 0 for r in rows if r["supply_temp_f"]]

    correlation = _pearson_correlation(supply_temps, flag_counts)

    return {
        "supply_temp_vs_flags": supply_vs_flags,
        "supply_temp_flag_correlation": round(correlation, 3),
        "total_scans_analyzed": len(rows),
        "lookback_days": lookback_days,
        "generated_at": datetime.now(timezone.utc).isoformat()
    }


def _pearson_correlation(x: list, y: list) -> float:
    """Simple Pearson correlation coefficient."""
    n = len(x)
    if n < 2:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    den = (sum((xi - mx)**2 for xi in x) * sum((yi - my)**2 for yi in y)) ** 0.5
    return num / den if den != 0 else 0.0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    stress, reasons = get_facility_stress_level()
    print(f"\nCurrent facility stress: {stress}%")
    if reasons:
        for r in reasons:
            print(f"  - {r}")
    else:
        print("  No facility stress detected")

    print("\nHVAC correlation patterns (last 30 days):")
    patterns = get_hvac_correlation_patterns()
    if "error" not in patterns:
        print(f"  Supply temp vs flags correlation: {patterns['supply_temp_flag_correlation']}")
        print(f"  Supply temp buckets vs avg flags flagged:")
        for bucket, avg in patterns["supply_temp_vs_flags"].items():
            print(f"    {bucket}: {avg} miners avg")
    else:
        print(f"  {patterns['error']}")
