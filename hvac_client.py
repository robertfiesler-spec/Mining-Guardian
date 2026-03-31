"""
hvac_client.py — Warehouse Mechanical / BAS Integration
Distech Controls Eclypse @ 192.168.188.235

NOTE: This is a one-off integration for the BiXBiT USA Fort Worth warehouse facility.
      It is NOT part of the standard Mining Guardian deployment template.
      Future deployments will pull equivalent data from the AMS container tab.

Architecture rule: This runs alongside AMS — not instead of it.
"""

import ssl
import json
import base64
import subprocess
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

ECLYPSE_URL  = "https://192.168.188.235"
ECLYPSE_USER = "BigStar"
ECLYPSE_PASS = "BigSt@r2020"
BASE         = f"{ECLYPSE_URL}/api/rest/v1/protocols/bacnet/local/objects"


@dataclass
class HVACSnapshot:
    # Water temps
    supply_temp_f:   Optional[float] = None   # AI-101 CWS_T
    return_temp_f:   Optional[float] = None   # AI-102 CWR_T
    delta_t_f:       Optional[float] = None   # calculated: return - supply
    diff_pressure_psi: Optional[float] = None # AI-103 CW_DP

    # Equipment status
    spray_pump_on:   Optional[bool]  = None   # BI-208 SprayPump_Status
    ct_fan1_on:      Optional[bool]  = None   # BI-201 CT1_Status
    ct_fan2_on:      Optional[bool]  = None   # BI-202 CT2_Status
    fans_active:     int = 0                   # count of active fans

    # Fan speed % (analog values — NaN when PID not running)
    ct_fan_pct:      Optional[float] = None   # AV-10013 CWDP_PID Output or AV-10023
    pump_pct:        Optional[float] = None   # AV-10013 CWDP_PID Output

    # Alarms
    system_enabled:  Optional[bool]  = None   # BV-1 SystemEnable
    leak_alarm:      Optional[bool]  = None   # BV-22 LeakDetection_Alarm (True = alarm)
    tower_vibration: Optional[bool]  = None   # BI-303 TowerVibrationSwitch
    basin_level_ok:  Optional[bool]  = None   # BI-302 BasinLevel (True = Normal)
    ct1_fault:       Optional[bool]  = None   # BI-203 CT1_Fault
    ct2_fault:       Optional[bool]  = None   # BI-204 CT2_Fault
    pump_fault:      Optional[bool]  = None   # BV-10 SprayPumpFail_Alm

    error: Optional[str] = None


class HVACClient:
    """
    Polls the Eclypse BAS controller for warehouse mechanical data.
    Uses subprocess curl for auth — basic auth with redirect following.
    """

    POINTS = {
        # (object_type, instance, property, target_field, transform)
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
        "dp_pid_out":     ("analog-value",  "10013", "present-value"),
        "pid4_out":       ("analog-value",  "10023", "present-value"),
    }

    def _curl(self, url: str) -> Optional[dict]:
        try:
            r = subprocess.run(
                ["curl", "-sk", url, "-u", f"{ECLYPSE_USER}:{ECLYPSE_PASS}",
                 "-L", "--max-time", "6"],
                capture_output=True, text=True, timeout=8
            )
            return json.loads(r.stdout)
        except Exception:
            return None

    def _get_prop(self, obj_type: str, oid: str, prop: str) -> Optional[str]:
        d = self._curl(f"{BASE}/{obj_type}/{oid}/properties/{prop}")
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
        snap = HVACSnapshot()
        try:
            vals = {}
            for key, (obj_type, oid, prop) in self.POINTS.items():
                vals[key] = self._get_prop(obj_type, oid, prop)

            snap.supply_temp_f    = self._to_float(vals.get("supply_temp"))
            snap.return_temp_f    = self._to_float(vals.get("return_temp"))
            snap.diff_pressure_psi= self._to_float(vals.get("diff_pressure"))
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

            # Fan % — try DP PID output first, fall back to PID4
            fan_pct = self._to_float(vals.get("dp_pid_out"))
            if fan_pct is None:
                fan_pct = self._to_float(vals.get("pid4_out"))
            snap.ct_fan_pct = fan_pct

            # Delta T
            if snap.supply_temp_f is not None and snap.return_temp_f is not None:
                snap.delta_t_f = round(snap.return_temp_f - snap.supply_temp_f, 2)

            # Fan count
            snap.fans_active = sum([
                1 for x in [snap.ct_fan1_on, snap.ct_fan2_on] if x is True
            ])

        except Exception as e:
            snap.error = str(e)
            logger.warning("HVACClient poll error: %s", e)

        return snap


def format_hvac_report(snap: HVACSnapshot) -> str:
    """Format the HVAC snapshot for the scan report — sits between weather and miner sections."""
    if snap.error and snap.supply_temp_f is None:
        return f"⚠️  Warehouse Mechanical — unavailable ({snap.error})"

    lines = ["━" * 60,
             "🏭  WAREHOUSE MECHANICAL  (Eclypse BAS @ .235)",
             "━" * 60]

    # Water temps
    sup = f"{snap.supply_temp_f:.1f}°F" if snap.supply_temp_f is not None else "N/A"
    ret = f"{snap.return_temp_f:.1f}°F" if snap.return_temp_f is not None else "N/A"
    dlt = f"{snap.delta_t_f:+.1f}°F"   if snap.delta_t_f     is not None else "N/A"
    dp  = f"{snap.diff_pressure_psi:.1f} PSI" if snap.diff_pressure_psi is not None else "N/A"

    lines.append(f"  Supply Water Temp :  {sup}")
    lines.append(f"  Return Water Temp :  {ret}   (ΔT {dlt})")
    lines.append(f"  Differential Press:  {dp}")
    lines.append("")

    # Equipment
    pump_str = "🟢 ON" if snap.spray_pump_on else ("🔴 OFF" if snap.spray_pump_on is False else "?")
    lines.append(f"  Spray Pump        :  {pump_str}")

    fan_count = snap.fans_active
    if snap.ct_fan1_on is not None or snap.ct_fan2_on is not None:
        f1 = "ON" if snap.ct_fan1_on  else "off"
        f2 = "ON" if snap.ct_fan2_on  else "off"
        fan_icon = "🟢" if fan_count > 0 else "🔴"
        pct_str = f"  @ {snap.ct_fan_pct:.0f}%" if snap.ct_fan_pct is not None else ""
        lines.append(f"  Cooling Tower Fans:  {fan_icon} {fan_count} active  "
                     f"(Fan1={f1}, Fan2={f2}){pct_str}")
    else:
        lines.append(f"  Cooling Tower Fans:  ?")

    # Alarms section — only show if something is wrong
    alarms = []
    if snap.leak_alarm:       alarms.append("🔴 LEAK DETECTED")
    if snap.tower_vibration:  alarms.append("🔴 TOWER VIBRATION ALARM")
    if snap.ct1_fault:        alarms.append("🔴 CT Fan 1 FAULT")
    if snap.ct2_fault:        alarms.append("🔴 CT Fan 2 FAULT")
    if snap.pump_fault:       alarms.append("🔴 Spray Pump FAULT")
    if snap.basin_level_ok is False: alarms.append("🔴 BASIN LEVEL LOW")

    lines.append("")
    if alarms:
        lines.append("  ⚠️  ALARMS:")
        for a in alarms:
            lines.append(f"     {a}")
    else:
        lines.append("  ✅  All alarms clear — system normal")

    return "\n".join(lines)
