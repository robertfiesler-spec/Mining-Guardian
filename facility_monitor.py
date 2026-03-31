"""
facility_monitor.py — Facility Infrastructure Monitor
======================================================
Polls all physical infrastructure in the BiXBiT USA warehouse:
  PDU 163 @ 192.168.188.15  — 2U rack (Auradines)
  PDU 164 @ 192.168.188.16  — Bitmain shoebox (S21 EXP Hydro)
  Tank B100 @ 192.168.188.20 — Fog Hashing Elite 1 immersion tank (S21 Imm)

NOTE: S19JPros are in an outside container on their own power —
no PDU access, AMS is the only data source for those miners.

Known PDU outlet assignments (warehouse miners only):
  PDU 163 outlet 3 → AH3880 #54504 @ 192.168.188.27
  PDU 163 outlet 4 → AH3880 #63940 @ 192.168.188.28
  PDU 164 outlet 3 → S21EXPHyd #53529 @ 192.168.188.25
  PDU 164 outlet 4 → S21EXPHyd (second unit — not yet in AMS)
  Tank port 19     → S21Imm #64345 @ 192.168.188.22
  Tank port 20     → S21Imm #64346 @ 192.168.188.23
  Tank port 22     → S21Imm (third unit — not yet in AMS)
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from pdu_client import PDUClient, PDUReading
from immersion_client import ImmersionTankClient, TankReading

logger = logging.getLogger("mining_guardian")

# ── PDU outlet → miner ID mapping ────────────────────────────────────────────
# Update when new miners are added to AMS
PDU_OUTLET_MAP = {
    # (pdu_ip, outlet_index): miner_id
    ('192.168.188.15', 3): '54504',   # AH3880 #1
    ('192.168.188.15', 4): '63940',   # AH3880 #2
    ('192.168.188.16', 3): '53529',   # S21EXPHyd #1
    ('192.168.188.16', 4): None,      # S21EXPHyd #2 — not yet in AMS
}

# Tank port → miner ID mapping
TANK_PORT_MAP = {
    19: '64345',   # S21Imm #1
    20: '64346',   # S21Imm #2
    22: None,      # S21Imm #3 — not yet in AMS
}


@dataclass
class FacilitySnapshot:
    """Combined snapshot of all facility infrastructure."""
    timestamp:      float
    pdu_163:        Optional[PDUReading]   # 2U rack PDU
    pdu_164:        Optional[PDUReading]   # Bitmain shoebox PDU
    tank_b100:      Optional[TankReading]  # Immersion tank
    errors:         list = field(default_factory=list)

    @property
    def total_warehouse_kw(self) -> float:
        """Total power draw across all warehouse infrastructure."""
        total = 0.0
        if self.pdu_163 and self.pdu_163.total_power_kw:
            total += self.pdu_163.total_power_kw
        if self.pdu_164 and self.pdu_164.total_power_kw:
            total += self.pdu_164.total_power_kw
        if self.tank_b100:
            total += self.tank_b100.total_power_kw
        return round(total, 3)

    @property
    def has_critical_alarm(self) -> bool:
        if self.tank_b100 and self.tank_b100.has_critical_alarm:
            return True
        return False

    def get_outlet_power_for_miner(self, miner_id: str) -> Optional[float]:
        """Look up direct PDU/tank power reading for a given miner ID."""
        # Check rack PDUs
        for (pdu_ip, outlet_idx), mid in PDU_OUTLET_MAP.items():
            if mid == miner_id:
                pdu = self.pdu_163 if pdu_ip == '192.168.188.15' else self.pdu_164
                if pdu and pdu.outlets:
                    outlet = next((o for o in pdu.outlets if o.index == outlet_idx), None)
                    if outlet and outlet.power_kw:
                        return outlet.power_kw
        # Check immersion tank
        for port_idx, mid in TANK_PORT_MAP.items():
            if mid == miner_id:
                if self.tank_b100:
                    port = next((p for p in self.tank_b100.ports if p.index == port_idx), None)
                    if port and port.total_power_kw > 0:
                        return port.total_power_kw
        return None


class FacilityMonitor:
    """
    Polls all warehouse infrastructure on each scan cycle.
    Provides enriched power data to Mining Guardian.

    S19JPros (outside container) have no PDU — skip silently.
    """

    def __init__(self):
        self.pdu_163  = PDUClient('192.168.188.15', user='admin', password='admin')
        self.pdu_164  = PDUClient('192.168.188.16', user='admin', password='admin')
        self.tank     = ImmersionTankClient('192.168.188.20')
        self._last_snapshot: Optional[FacilitySnapshot] = None

    def poll(self) -> FacilitySnapshot:
        """Poll all infrastructure and return combined snapshot."""
        errors  = []
        ts      = time.time()

        # PDU 163 — 2U rack (Auradines)
        try:
            r163 = self.pdu_163.read()
            if not r163:
                errors.append("PDU 163 (192.168.188.15): no response")
        except Exception as e:
            r163 = None
            errors.append(f"PDU 163 error: {e}")

        # PDU 164 — Bitmain shoebox (S21 EXP Hydro)
        try:
            r164 = self.pdu_164.read()
            if not r164:
                errors.append("PDU 164 (192.168.188.16): no response")
        except Exception as e:
            r164 = None
            errors.append(f"PDU 164 error: {e}")

        # Immersion tank B100
        try:
            rtank = self.tank.read()
            if not rtank:
                errors.append("Tank B100 (192.168.188.20): no response")
        except Exception as e:
            rtank = None
            errors.append(f"Tank B100 error: {e}")

        if errors:
            for err in errors:
                logger.warning("FacilityMonitor: %s", err)

        snapshot = FacilitySnapshot(
            timestamp  = ts,
            pdu_163    = r163,
            pdu_164    = r164,
            tank_b100  = rtank,
            errors     = errors,
        )
        self._last_snapshot = snapshot

        logger.info(
            "FacilityMonitor: polled — warehouse total %.2f kW "
            "(PDU163=%.2f kW, PDU164=%.2f kW, Tank=%.2f kW)",
            snapshot.total_warehouse_kw,
            r163.total_power_kw if r163 else 0,
            r164.total_power_kw if r164 else 0,
            rtank.total_power_kw if rtank else 0,
        )

        return snapshot

    @property
    def last_snapshot(self) -> Optional[FacilitySnapshot]:
        return self._last_snapshot

    def format_report_section(self, snapshot: FacilitySnapshot) -> str:
        """Format a facility infrastructure section for the scan report."""
        lines = []
        lines.append("\n  ── WAREHOUSE INFRASTRUCTURE ──────────────────────────────")
        lines.append(f"  Total warehouse power: {snapshot.total_warehouse_kw:.2f} kW")

        if snapshot.tank_b100:
            t = snapshot.tank_b100
            pump_str  = "🟢 running" if t.pump_on else "🔴 STOPPED"
            fluid_str = "🟢 OK" if t.fluid_level_ok else "🔴 LOW"
            alarm_str = "🔴 " + ", ".join(str(a) for a in t.alarms) if t.alarms else "✅ none"
            lines.append(
                f"\n  Immersion Tank B100 ({snapshot.tank_b100.ip}):"
            )
            lines.append(
                f"    Fluid: in={t.in_temp_c}°C  out={t.out_temp_c}°C  "
                f"target={t.target_temp_c}°C  shutdown@{t.temp_shutdown_c}°C"
            )
            lines.append(
                f"    Pump: {pump_str}  Fluid level: {fluid_str}  Alarms: {alarm_str}"
            )
            lines.append(
                f"    Total tank power: {t.total_power_kw:.2f} kW  "
                f"Active ports: {len(t.active_ports)}"
            )
            for p in t.active_ports:
                miner_id = TANK_PORT_MAP.get(p.index, 'unknown')
                lines.append(
                    f"    Port {p.index:02d}: {p.total_power_kw:.2f} kW  "
                    f"{p.avg_voltage}V  {p.avg_current}A  "
                    f"→ miner {miner_id or 'not in AMS'}"
                )

        for label, pdu, port_map_filter in [
            ("PDU 163 — 2U Rack (Auradines)", snapshot.pdu_163, '192.168.188.15'),
            ("PDU 164 — Bitmain Shoebox (S21 EXP Hydro)", snapshot.pdu_164, '192.168.188.16'),
        ]:
            if pdu:
                lines.append(f"\n  {label} ({pdu.ip}):")
                lines.append(
                    f"    L1: {pdu.l1_voltage_v}V {pdu.l1_current_a}A  "
                    f"Total: {pdu.total_power_kw:.3f} kW  "
                    f"Energy: {pdu.total_energy_kwh:.1f} kWh  "
                    f"Alarm: {pdu.alarm_status}"
                )
                for o in pdu.outlets:
                    if o.on:
                        miner_id = PDU_OUTLET_MAP.get((pdu.ip, o.index))
                        lines.append(
                            f"    Outlet {o.index}: {o.power_kw:.3f} kW  "
                            f"{o.avg_voltage_v}V  {o.avg_current_a}A  "
                            f"→ miner {miner_id or 'not in AMS'}"
                        )

        if snapshot.errors:
            lines.append(f"\n  ⚠️  Infrastructure errors: {'; '.join(snapshot.errors)}")

        return "\n".join(lines)


def format_facility_report(snapshot: "FacilitySnapshot") -> str:
    """Standalone function to format facility section for _print_report."""
    lines = []
    lines.append("\n  ── WAREHOUSE INFRASTRUCTURE ──────────────────────────────")
    lines.append(f"  Total warehouse power: {snapshot.total_warehouse_kw:.2f} kW")

    if snapshot.tank_b100:
        t = snapshot.tank_b100
        pump_str  = "🟢 running" if t.pump_on else "🔴 STOPPED"
        fluid_str = "🟢 OK" if t.fluid_level_ok else "🔴 LOW"
        alarm_str = "🔴 " + ", ".join(str(a) for a in t.alarms) if t.alarms else "✅ none"
        lines.append(f"\n  Immersion Tank B100 ({t.ip}):")
        lines.append(
            f"    Fluid: in={t.in_temp_c}°C  out={t.out_temp_c}°C  "
            f"target={t.target_temp_c}°C  shutdown@{t.temp_shutdown_c}°C"
        )
        lines.append(
            f"    Pump: {pump_str}  Fluid level: {fluid_str}  Alarms: {alarm_str}"
        )
        lines.append(
            f"    Total tank power: {t.total_power_kw:.2f} kW  "
            f"Active ports: {len(t.active_ports)}"
        )
        for p in t.active_ports:
            miner_id = TANK_PORT_MAP.get(p.index)
            lines.append(
                f"    Port {p.index:02d}: {p.total_power_kw:.2f} kW  "
                f"{p.avg_voltage}V  {p.avg_current}A  "
                f"→ miner {miner_id or 'not in AMS'}"
            )

    for label, pdu in [
        ("PDU 163 — 2U Rack (Auradines)", snapshot.pdu_163),
        ("PDU 164 — Bitmain Shoebox (S21 EXP Hydro)", snapshot.pdu_164),
    ]:
        if pdu:
            lines.append(f"\n  {label} ({pdu.ip}):")
            lines.append(
                f"    L1: {pdu.l1_voltage_v}V  {pdu.l1_current_a}A  "
                f"Total: {pdu.total_power_kw:.3f} kW  "
                f"Alarm: {pdu.alarm_status}"
            )
            for o in pdu.outlets:
                if o.on:
                    miner_id = PDU_OUTLET_MAP.get((pdu.ip, o.index))
                    lines.append(
                        f"    Outlet {o.index}: {o.power_kw:.3f} kW  "
                        f"{o.avg_voltage_v}V  {o.avg_current_a}A  "
                        f"→ miner {miner_id or 'not in AMS'}"
                    )

    if snapshot.errors:
        lines.append(f"\n  ⚠️  Infrastructure errors: {'; '.join(snapshot.errors)}")

    return "\n".join(lines)
