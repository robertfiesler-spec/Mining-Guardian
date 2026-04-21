"""
hvac_client.py — Multi-System HVAC/BAS Integration
Supports multiple Distech Controls Eclypse controllers:
  - Warehouse: 192.168.188.235 (Hydros, S21 Immersion)
  - S19J Pro:  192.168.189.235 (S19J Pro container)

NOTE: This is a one-off integration for the BiXBiT USA Fort Worth warehouse facility.
      It is NOT part of the standard Mining Guardian deployment template.
      Future deployments will pull equivalent data from the AMS container tab.

Updated: April 13, 2026 — Added S19J Pro system support
"""

import json
import os
import logging
import requests
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Credentials from .env
ECLYPSE_USER = os.getenv("ECLYPSE_USER")
ECLYPSE_PASS = os.getenv("ECLYPSE_PASS")
if not ECLYPSE_USER or not ECLYPSE_PASS:
    logger.warning("ECLYPSE_USER / ECLYPSE_PASS not set — HVAC client will fail to authenticate")


@dataclass
class HVACSnapshot:
    """Common snapshot for any HVAC system."""
    system_id: str = ""
    system_name: str = ""
    
    # Water temps
    supply_temp_f:   Optional[float] = None
    return_temp_f:   Optional[float] = None
    delta_t_f:       Optional[float] = None
    diff_pressure_psi: Optional[float] = None
    
    # S19J Pro specific
    outside_air_f:   Optional[float] = None
    container_temp_f: Optional[float] = None

    # Equipment status (binary)
    spray_pump_on:   Optional[bool]  = None
    ct_fan1_on:      Optional[bool]  = None
    ct_fan2_on:      Optional[bool]  = None
    fans_active:     int = 0

    # VFD actual speeds (analog outputs) - %
    cwp1_vfd_pct:    Optional[float] = None
    cwp2_vfd_pct:    Optional[float] = None
    ct1_vfd_pct:     Optional[float] = None
    ct2_vfd_pct:     Optional[float] = None

    # Alarms
    system_enabled:  Optional[bool]  = None
    leak_alarm:      Optional[bool]  = None
    tower_vibration: Optional[bool]  = None
    basin_level_ok:  Optional[bool]  = None
    ct1_fault:       Optional[bool]  = None
    ct2_fault:       Optional[bool]  = None
    pump_fault:      Optional[bool]  = None
    cwp1_trip:       Optional[bool]  = None
    cwp2_trip:       Optional[bool]  = None
    ct_trip:         Optional[bool]  = None

    error: Optional[str] = None


# Point definitions for each system
WAREHOUSE_POINTS = {
    "supply_temp":    ("analog-input",  "101", "present-value"),
    "return_temp":    ("analog-input",  "102", "present-value"),
    "diff_pressure":  ("analog-input",  "103", "present-value"),
    "spray_pump":     ("binary-input",  "208", "present-value"),
    "ct1_status":     ("binary-input",  "201", "present-value"),
    "ct2_status":     ("binary-input",  "202", "present-value"),
    "ct1_fault":      ("binary-input",  "203", "present-value"),
    "ct2_fault":      ("binary-input",  "204", "present-value"),
    "tower_vibration":("binary-input",  "303", "present-value"),
    "basin_level":    ("binary-input",  "302", "present-value"),
    "pump_fault":     ("binary-value",  "10",  "present-value"),
    "system_enable":  ("binary-value",  "1",   "present-value"),
    "leak_alarm":     ("binary-value",  "22",  "present-value"),
    "cwp1_vfd":       ("analog-output", "101", "present-value"),
    "cwp2_vfd":       ("analog-output", "102", "present-value"),
    "ct1_vfd":        ("analog-output", "103", "present-value"),
    "ct2_vfd":        ("analog-output", "104", "present-value"),
}

S19JPRO_POINTS = {
    "supply_temp":    ("analog-input",  "105", "present-value"),  # CDWST
    "return_temp":    ("analog-input",  "106", "present-value"),  # CDWRT
    "outside_air":    ("analog-input",  "107", "present-value"),  # OAT
    "container_temp": ("analog-input",  "108", "present-value"),  # ContainerSpaceTemp
    "cwp1_fdbk":      ("analog-input",  "102", "present-value"),  # CWP1_Fdbk
    "cwp2_fdbk":      ("analog-input",  "103", "present-value"),  # CWP2_Fdbk
    "ct1_vfd":        ("analog-output", "101", "present-value"),  # CT1_VFD
    "ct2_vfd":        ("analog-output", "102", "present-value"),  # CT2_VFD
    "leak_alarm":     ("binary-input",  "301", "present-value"),  # LeakDetectionAlarm
    "basin_level":    ("binary-input",  "302", "present-value"),  # BasinLevelSwitch
    "cwp1_trip":      ("binary-input",  "201", "present-value"),  # CWP1_Trip
    "cwp2_trip":      ("binary-input",  "202", "present-value"),  # CWP2_Trip
    "ct_trip":        ("binary-input",  "205", "present-value"),  # CT_Trip
    "spray_pump":     ("binary-input",  "303", "present-value"),  # SprayPumpStatus
}

SYSTEMS = {
    "warehouse": {
        "ip": "192.168.188.235",
        "name": "Warehouse HVAC",
        "points": WAREHOUSE_POINTS,
        "miners": ["S21", "S21e", "S21 EXP", "S21 Imm"],  # model prefixes
    },
    "s19jpro": {
        "ip": "192.168.189.235",
        "name": "S19J Pro Container",
        "points": S19JPRO_POINTS,
        "miners": ["S19JPro"],
    }
}


class HVACClient:
    """
    Polls Eclypse BAS controllers for environmental data.
    Supports multiple systems (warehouse, s19jpro).
    """
    
    def __init__(self, system_id: str = "warehouse"):
        if system_id not in SYSTEMS:
            raise ValueError(f"Unknown HVAC system: {system_id}. Valid: {list(SYSTEMS.keys())}")
        self.system_id = system_id
        self.system = SYSTEMS[system_id]
        self.base_url = f"https://{self.system['ip']}/api/rest/v1/protocols/bacnet/local/objects"

    def _curl(self, url: str) -> Optional[dict]:
        """Fetch a BACnet property from the Eclypse controller."""
        try:
            r = requests.get(
                url,
                auth=(ECLYPSE_USER, ECLYPSE_PASS),
                verify=False,
                timeout=6
            )
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            logger.debug("HVAC request failed for %s: %s", url, e)
            return None
        except ValueError:
            logger.debug("HVAC bad JSON from %s", url)
            return None

    def _get_prop(self, obj_type: str, oid: str, prop: str) -> Optional[str]:
        d = self._curl(f"{self.base_url}/{obj_type}/{oid}/properties/{prop}")
        if d and "value" in d:
            return d["value"]
        return None

    def _to_float(self, v) -> Optional[float]:
        try:
            f = float(v)
            return None if f != f else round(f, 2)  # NaN check
        except (TypeError, ValueError):
            return None

    def _is_active(self, v) -> Optional[bool]:
        if v is None:
            return None
        return str(v).strip().lower() == "active"

    def poll(self) -> HVACSnapshot:
        snap = HVACSnapshot(system_id=self.system_id, system_name=self.system["name"])
        try:
            vals = {}
            for key, (obj_type, oid, prop) in self.system["points"].items():
                vals[key] = self._get_prop(obj_type, oid, prop)

            snap.supply_temp_f    = self._to_float(vals.get("supply_temp"))
            snap.return_temp_f    = self._to_float(vals.get("return_temp"))
            snap.diff_pressure_psi= self._to_float(vals.get("diff_pressure"))
            snap.outside_air_f    = self._to_float(vals.get("outside_air"))
            snap.container_temp_f = self._to_float(vals.get("container_temp"))
            
            snap.spray_pump_on    = self._is_active(vals.get("spray_pump"))
            snap.ct_fan1_on       = self._is_active(vals.get("ct1_status"))
            snap.ct_fan2_on       = self._is_active(vals.get("ct2_status"))
            snap.system_enabled   = self._is_active(vals.get("system_enable"))
            snap.leak_alarm       = self._is_active(vals.get("leak_alarm"))
            snap.tower_vibration  = self._is_active(vals.get("tower_vibration"))
            snap.basin_level_ok   = self._is_active(vals.get("basin_level"))
            snap.ct1_fault        = self._is_active(vals.get("ct1_fault"))
            snap.ct2_fault        = self._is_active(vals.get("ct2_fault"))
            snap.pump_fault       = self._is_active(vals.get("pump_fault"))
            snap.cwp1_trip        = self._is_active(vals.get("cwp1_trip"))
            snap.cwp2_trip        = self._is_active(vals.get("cwp2_trip"))
            snap.ct_trip          = self._is_active(vals.get("ct_trip"))

            # VFD actual speeds - different field names per system
            if self.system_id == "warehouse":
                snap.cwp1_vfd_pct = self._to_float(vals.get("cwp1_vfd"))
                snap.cwp2_vfd_pct = self._to_float(vals.get("cwp2_vfd"))
            else:  # s19jpro uses feedback readings
                snap.cwp1_vfd_pct = self._to_float(vals.get("cwp1_fdbk"))
                snap.cwp2_vfd_pct = self._to_float(vals.get("cwp2_fdbk"))
            
            snap.ct1_vfd_pct  = self._to_float(vals.get("ct1_vfd"))
            snap.ct2_vfd_pct  = self._to_float(vals.get("ct2_vfd"))

            # Delta T
            if snap.supply_temp_f is not None and snap.return_temp_f is not None:
                snap.delta_t_f = round(snap.return_temp_f - snap.supply_temp_f, 2)

            # Fan count
            snap.fans_active = sum([
                1 for x in [snap.ct_fan1_on, snap.ct_fan2_on] if x is True
            ])

        except Exception as e:
            snap.error = str(e)
            logger.warning("HVACClient poll error [%s]: %s", self.system_id, e)

        return snap


def get_hvac_system_for_miner(model: str) -> Optional[str]:
    """Return the HVAC system_id that corresponds to a miner model."""
    for sys_id, sys_cfg in SYSTEMS.items():
        for prefix in sys_cfg["miners"]:
            if model.startswith(prefix):
                return sys_id
    return None


def poll_all_systems() -> Dict[str, HVACSnapshot]:
    """Poll all configured HVAC systems and return snapshots."""
    results = {}
    for sys_id in SYSTEMS:
        try:
            client = HVACClient(sys_id)
            results[sys_id] = client.poll()
        except Exception as e:
            logger.error("Failed to poll HVAC system %s: %s", sys_id, e)
            snap = HVACSnapshot(system_id=sys_id, system_name=SYSTEMS[sys_id]["name"])
            snap.error = str(e)
            results[sys_id] = snap
    return results


def format_hvac_report(snap: HVACSnapshot) -> str:
    """Format an HVAC snapshot for the scan report."""
    if snap.error and snap.supply_temp_f is None:
        return f"⚠️  {snap.system_name} — unavailable ({snap.error})"

    lines = ["━" * 60,
             f"🏭  {snap.system_name.upper()}  ({snap.system_id})",
             "━" * 60]

    # Water temps
    sup = f"{snap.supply_temp_f:.1f}°F" if snap.supply_temp_f is not None else "N/A"
    ret = f"{snap.return_temp_f:.1f}°F" if snap.return_temp_f is not None else "N/A"
    dlt = f"{snap.delta_t_f:+.1f}°F"   if snap.delta_t_f     is not None else "N/A"

    lines.append(f"  Supply Water Temp :  {sup}")
    lines.append(f"  Return Water Temp :  {ret}   (ΔT {dlt})")

    # S19J Pro specific: outside air and container temp
    if snap.outside_air_f is not None:
        lines.append(f"  Outside Air Temp  :  {snap.outside_air_f:.1f}°F")
    if snap.container_temp_f is not None:
        lines.append(f"  Container Temp    :  {snap.container_temp_f:.1f}°F")
    
    # Diff pressure (warehouse only)
    if snap.diff_pressure_psi is not None:
        lines.append(f"  Differential Press:  {snap.diff_pressure_psi:.1f} PSI")
    
    lines.append("")

    # Equipment - pumps
    cwp1_pct = f"{snap.cwp1_vfd_pct:.0f}%" if snap.cwp1_vfd_pct is not None else "?"
    cwp2_pct = f"{snap.cwp2_vfd_pct:.0f}%" if snap.cwp2_vfd_pct is not None else "?"
    cwp1_icon = "🟢" if snap.cwp1_vfd_pct and snap.cwp1_vfd_pct > 0 else "⚫"
    cwp2_icon = "🟢" if snap.cwp2_vfd_pct and snap.cwp2_vfd_pct > 0 else "⚫"
    lines.append(f"  CW Pump 1         :  {cwp1_icon} {cwp1_pct}")
    lines.append(f"  CW Pump 2         :  {cwp2_icon} {cwp2_pct}")

    # Cooling tower fans
    ct1_pct = f"{snap.ct1_vfd_pct:.0f}%" if snap.ct1_vfd_pct is not None else "?"
    ct2_pct = f"{snap.ct2_vfd_pct:.0f}%" if snap.ct2_vfd_pct is not None else "?"
    ct1_icon = "🟢" if snap.ct1_vfd_pct and snap.ct1_vfd_pct > 0 else "⚫"
    ct2_icon = "🟢" if snap.ct2_vfd_pct and snap.ct2_vfd_pct > 0 else "⚫"
    lines.append(f"  CT Fan 1          :  {ct1_icon} {ct1_pct}")
    lines.append(f"  CT Fan 2          :  {ct2_icon} {ct2_pct}")

    # Spray pump if available
    if snap.spray_pump_on is not None:
        pump_str = "🟢 ON" if snap.spray_pump_on else "🔴 OFF"
        lines.append(f"  Spray Pump        :  {pump_str}")

    # Alarms section
    alarms = []
    if snap.leak_alarm:       alarms.append("🔴 LEAK DETECTED")
    if snap.tower_vibration:  alarms.append("🔴 TOWER VIBRATION ALARM")
    if snap.ct1_fault:        alarms.append("🔴 CT Fan 1 FAULT")
    if snap.ct2_fault:        alarms.append("🔴 CT Fan 2 FAULT")
    if snap.pump_fault:       alarms.append("🔴 Spray Pump FAULT")
    if snap.cwp1_trip:        alarms.append("🔴 CW Pump 1 TRIP")
    if snap.cwp2_trip:        alarms.append("🔴 CW Pump 2 TRIP")
    if snap.ct_trip:          alarms.append("🔴 CT TRIP")

    lines.append("")
    if alarms:
        lines.append("  ⚠️  ALARMS:")
        for a in alarms:
            lines.append(f"     {a}")
    else:
        lines.append("  ✅  All alarms clear — system normal")

    return "\n".join(lines)


def format_all_hvac_reports() -> str:
    """Poll all systems and return combined report."""
    snaps = poll_all_systems()
    reports = []
    for sys_id in ["warehouse", "s19jpro"]:  # fixed order
        if sys_id in snaps:
            reports.append(format_hvac_report(snaps[sys_id]))
    return "\n\n".join(reports)


def get_latest_hvac_from_db(system_id: str) -> Optional[HVACSnapshot]:
    """Get the latest HVAC reading from the database (populated by Mac collector)."""
    import sqlite3
    from pathlib import Path
    
    db_path = Path(__file__).resolve().parent.parent / "guardian.db"
    if not db_path.exists():
        return None
    
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.execute("""
            SELECT * FROM hvac_readings 
            WHERE system_id = ? 
            ORDER BY recorded_at DESC 
            LIMIT 1
        """, (system_id,))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            return None
        
        # Check if data is recent (within 10 minutes)
        from datetime import datetime, timedelta
        recorded_at = datetime.fromisoformat(row["recorded_at"].replace("Z", "+00:00") if row["recorded_at"].endswith("Z") else row["recorded_at"])
        if datetime.utcnow() - recorded_at.replace(tzinfo=None) > timedelta(minutes=30):
            logger.warning("HVAC data for %s is stale (recorded at %s)", system_id, row["recorded_at"])
            return None
        
        system_name = SYSTEMS.get(system_id, {}).get("name", system_id)
        snap = HVACSnapshot(system_id=system_id, system_name=system_name)
        snap.supply_temp_f = row["supply_temp_f"]
        snap.return_temp_f = row["return_temp_f"]
        snap.delta_t_f = row["delta_t_f"]
        snap.diff_pressure_psi = row["diff_pressure"]
        snap.outside_air_f = row["outside_air_f"]
        snap.container_temp_f = row["container_temp_f"]
        snap.cwp1_vfd_pct = row["cwp1_vfd_pct"]
        snap.cwp2_vfd_pct = row["cwp2_vfd_pct"]
        snap.ct1_vfd_pct = row["ct1_vfd_pct"]
        snap.ct2_vfd_pct = row["ct2_vfd_pct"]
        snap.leak_alarm = bool(row["leak_alarm"]) if row["leak_alarm"] is not None else False
        
        return snap
    except Exception as e:
        logger.error("Failed to read HVAC from DB for %s: %s", system_id, e)
        return None


def poll_all_systems_with_db_fallback() -> Dict[str, HVACSnapshot]:
    """
    Poll all HVAC systems with database fallback.
    First tries direct polling, then falls back to DB (populated by Mac collector).
    """
    results = {}
    for sys_id in SYSTEMS:
        # First try DB (faster and more reliable from VPS)
        snap = get_latest_hvac_from_db(sys_id)
        if snap and snap.supply_temp_f is not None:
            logger.info("HVAC %s: using DB cache (supply=%.1f°F)", sys_id, snap.supply_temp_f)
            results[sys_id] = snap
            continue
        
        # Fallback to direct poll (works if on local network)
        try:
            client = HVACClient(sys_id)
            results[sys_id] = client.poll()
        except Exception as e:
            logger.error("Failed to poll HVAC system %s: %s", sys_id, e)
            snap = HVACSnapshot(system_id=sys_id, system_name=SYSTEMS[sys_id]["name"])
            snap.error = str(e)
            results[sys_id] = snap
    return results
