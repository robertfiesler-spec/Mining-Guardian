"""
container_monitor.py — BiXBiT AMS Container Infrastructure Monitor
===================================================================
Monitors BiXBiT container infrastructure via AMS API:
  - Hydraulics: supply/return temp & pressure, flow rate, conductivity
  - Cooling: dry cooler, fans, pump frequency
  - Power: PMM1 (racks 1-3), PMM2 (racks 4-6), PMM3 (infrastructure), PUE
  - Room: inside temps, cabinet temps, outside temp & humidity
  - Safety: tank level, leakage, smoke detector
  - Farm: rack layout with per-miner position, temp, hashrate, power

Data is pulled via the AMS API using the same auth as the miner endpoints.
Container ID and workspace ID come from config.

Sensor Reference:
  TT01  — Supply line temperature (°C)
  TT02  — Return line temperature (°C)
  PT01  — Supply line pressure (MPa)
  PT02  — Return line pressure (MPa)
  PT03  — Before filter pressure (MPa)
  PT04  — After filter pressure (MPa)
  PT05  — High pressure (MPa)
  FT01  — Flow on feed (m³/h)
  ET01  — Electrical conductivity (µS/cm)
  P01   — Main pump frequency (Hz)
  P11   — Filling pump (on/off)
  TT21  — Inside room temperature 1 (°C)
  TT22  — Inside room temperature 2 (°C)
  TT41  — Distribution cabinet temperature (°C)
  TT43  — Control cabinet temperature (°C)
  TRT01 — Outside temperature (°C)
  PMM1  — Power racks 1-3 (kW)
  PMM2  — Power racks 4-6 (kW)
  PMM3  — Infrastructure power (kW)
"""

import logging
import json
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any

logger = logging.getLogger("mining_guardian")


@dataclass
class ContainerHydraulics:
    """Hydraulic system readings."""
    supply_temp_c: Optional[float] = None      # TT01
    supply_pressure_mpa: Optional[float] = None # PT01
    return_temp_c: Optional[float] = None       # TT02
    return_pressure_mpa: Optional[float] = None # PT02
    filter_before_mpa: Optional[float] = None   # PT03
    filter_after_mpa: Optional[float] = None    # PT04
    high_pressure_mpa: Optional[float] = None   # PT05
    flow_rate_m3h: Optional[float] = None       # FT01
    conductivity_us: Optional[float] = None     # ET01
    delta_t_c: Optional[float] = None           # TT02 - TT01

    @property
    def supply_temp_f(self):
        return self.supply_temp_c * 9/5 + 32 if self.supply_temp_c else None

    @property
    def return_temp_f(self):
        return self.return_temp_c * 9/5 + 32 if self.return_temp_c else None


@dataclass
class ContainerCooling:
    """Cooling equipment status."""
    dry_cooler_freq_hz: Optional[float] = None
    dry_cooler_on: bool = False
    fan_g21_on: bool = False
    fan_g22_on: bool = False
    pump_p01_freq_hz: Optional[float] = None
    pump_p01_on: bool = False
    filling_pump_p11_on: bool = False


@dataclass
class ContainerPower:
    """Power consumption by zone."""
    pmm1_kw: Optional[float] = None    # Racks 1-3
    pmm2_kw: Optional[float] = None    # Racks 4-6
    pmm3_kw: Optional[float] = None    # Infrastructure
    asic_total_kw: Optional[float] = None
    infra_kw: Optional[float] = None
    total_kw: Optional[float] = None
    pue: Optional[float] = None


@dataclass
class ContainerEnvironment:
    """Room and outside conditions."""
    inside_temp1_c: Optional[float] = None    # TT21
    inside_temp2_c: Optional[float] = None    # TT22
    dist_cabinet_temp_c: Optional[float] = None  # TT41
    ctrl_cabinet_temp_c: Optional[float] = None  # TT43
    outside_temp_c: Optional[float] = None    # TRT01
    outside_humidity_pct: Optional[float] = None


@dataclass
class ContainerSafety:
    """Safety system status."""
    tank_level_ok: bool = True
    leakage_detected: bool = False
    smoke_detected: bool = False
    emergency_alarms: List[str] = field(default_factory=list)
    warning_alarms: List[str] = field(default_factory=list)


@dataclass
class ContainerFarm:
    """Farm/rack layout summary."""
    total_miners: int = 0
    miners_on: int = 0
    miners_off: int = 0
    total_hashrate_ths: float = 0.0
    total_hashrate_phs: float = 0.0
    avg_board_temp_c: Optional[float] = None
    avg_chip_temp_c: Optional[float] = None
    total_consumption_kw: float = 0.0
    racks: Dict[str, Dict] = field(default_factory=dict)


@dataclass
class ContainerSnapshot:
    """Complete container state from a single poll."""
    container_id: int = 0
    container_name: str = ""
    ip: str = ""
    status: str = "unknown"
    mode: str = "unknown"
    hydraulics: ContainerHydraulics = field(default_factory=ContainerHydraulics)
    cooling: ContainerCooling = field(default_factory=ContainerCooling)
    power: ContainerPower = field(default_factory=ContainerPower)
    environment: ContainerEnvironment = field(default_factory=ContainerEnvironment)
    safety: ContainerSafety = field(default_factory=ContainerSafety)
    farm: ContainerFarm = field(default_factory=ContainerFarm)
    config: Dict = field(default_factory=dict)
    raw: Dict = field(default_factory=dict)


class ContainerMonitor:
    """Polls BiXBiT AMS container endpoints for infrastructure data."""

    def __init__(self, ams_client):
        """
        Args:
            ams_client: Authenticated AMSClient instance (same one used for miners)
        """
        self.ams = ams_client

    def get_containers(self) -> List[Dict]:
        """Fetch list of containers from AMS."""
        token = self.ams._ensure_token()
        resp = self.ams.session.get(
            f"{self.ams.base_url}/containers",
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.ams.timeout,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, list) else data.get("containers", [])
        logger.warning("get_containers returned %s", resp.status_code)
        return []

    def get_container_detail(self, container_id: int) -> Dict:
        """Fetch detailed container data including all sensors."""
        token = self.ams._ensure_token()
        resp = self.ams.session.get(
            f"{self.ams.base_url}/containers/{container_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.ams.timeout,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning("get_container_detail(%s) returned %s", container_id, resp.status_code)
        return {}

    def get_container_config(self, container_id: int) -> Dict:
        """Fetch container configuration (auto/manual/alert settings)."""
        token = self.ams._ensure_token()
        resp = self.ams.session.get(
            f"{self.ams.base_url}/containers/{container_id}/config",
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.ams.timeout,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning("get_container_config(%s) returned %s", container_id, resp.status_code)
        return {}

    def get_container_health(self, container_id: int) -> Dict:
        """Fetch container health check data."""
        token = self.ams._ensure_token()
        resp = self.ams.session.get(
            f"{self.ams.base_url}/containers/{container_id}/health-check",
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.ams.timeout,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning("get_container_health(%s) returned %s", container_id, resp.status_code)
        return {}

    def get_container_groups(self, container_id: int) -> Dict:
        """Fetch container rack/group structure (farm layout)."""
        token = self.ams._ensure_token()
        resp = self.ams.session.get(
            f"{self.ams.base_url}/containers/{container_id}/groups",
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.ams.timeout,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning("get_container_groups(%s) returned %s", container_id, resp.status_code)
        return {}

    def _parse_snapshot(self, detail: Dict, config: Dict,
                        health: Dict, groups: Dict) -> ContainerSnapshot:
        """Parse raw API responses into a ContainerSnapshot."""
        snap = ContainerSnapshot()
        snap.raw = detail

        # Basic info
        snap.container_id = detail.get("id", 0)
        snap.container_name = detail.get("name", "")
        snap.ip = detail.get("ip", "")
        snap.status = detail.get("status", "unknown")
        snap.mode = detail.get("mode", "unknown")

        # Hydraulics
        h = snap.hydraulics
        h.supply_temp_c = detail.get("TT01") or detail.get("supplyTemperature")
        h.supply_pressure_mpa = detail.get("PT01") or detail.get("supplyPressure")
        h.return_temp_c = detail.get("TT02") or detail.get("returnTemperature")
        h.return_pressure_mpa = detail.get("PT02") or detail.get("returnPressure")
        h.filter_before_mpa = detail.get("PT03")
        h.filter_after_mpa = detail.get("PT04")
        h.high_pressure_mpa = detail.get("PT05")
        h.flow_rate_m3h = detail.get("FT01") or detail.get("flowRate")
        h.conductivity_us = detail.get("ET01") or detail.get("conductivity")
        if h.supply_temp_c and h.return_temp_c:
            h.delta_t_c = h.return_temp_c - h.supply_temp_c

        # Cooling
        c = snap.cooling
        c.dry_cooler_freq_hz = detail.get("dryCoolerFrequency")
        c.dry_cooler_on = detail.get("dryCoolerOn", False)
        c.fan_g21_on = detail.get("fanG21On", False)
        c.fan_g22_on = detail.get("fanG22On", False)
        c.pump_p01_freq_hz = detail.get("pumpP01Frequency") or detail.get("mainPumpFrequency")
        c.pump_p01_on = detail.get("pumpP01On", False)
        c.filling_pump_p11_on = detail.get("fillingPumpOn", False)

        # Power
        p = snap.power
        p.pmm1_kw = detail.get("PMM1") or detail.get("pmm1Power")
        p.pmm2_kw = detail.get("PMM2") or detail.get("pmm2Power")
        p.pmm3_kw = detail.get("PMM3") or detail.get("pmm3Power")
        p.asic_total_kw = detail.get("asicConsumption")
        p.infra_kw = detail.get("infrastructureConsumption")
        p.total_kw = detail.get("totalPower")
        p.pue = detail.get("pue")

        # Environment
        e = snap.environment
        e.inside_temp1_c = detail.get("TT21")
        e.inside_temp2_c = detail.get("TT22")
        e.dist_cabinet_temp_c = detail.get("TT41")
        e.ctrl_cabinet_temp_c = detail.get("TT43")
        e.outside_temp_c = detail.get("TRT01") or detail.get("outsideTemperature")
        e.outside_humidity_pct = detail.get("outsideHumidity")

        # Safety
        s = snap.safety
        s.tank_level_ok = detail.get("tankLevelNormal", True)
        s.leakage_detected = detail.get("leakageDetected", False)
        s.smoke_detected = detail.get("smokeDetected", False)
        if health:
            s.emergency_alarms = health.get("emergencyAlarms", [])
            s.warning_alarms = health.get("warningAlarms", [])

        # Farm/rack summary
        f = snap.farm
        f.total_miners = detail.get("totalMiners", 0)
        f.miners_on = detail.get("minersOn", 0)
        f.miners_off = detail.get("minersOff", 0)
        f.total_hashrate_phs = detail.get("hashrate", 0)
        f.total_hashrate_ths = f.total_hashrate_phs * 1000
        f.total_consumption_kw = detail.get("consumption", 0)
        f.avg_board_temp_c = detail.get("boardTemperature")
        f.avg_chip_temp_c = detail.get("chipTemperature")

        # Rack groups
        if groups:
            racks = groups if isinstance(groups, list) else groups.get("groups", [])
            for rack in racks:
                rack_name = rack.get("name", f"R{rack.get('id', '?')}")
                f.racks[rack_name] = {
                    "miners": rack.get("minerCount", 0),
                    "hashrate": rack.get("hashrate", 0),
                    "power": rack.get("consumption", 0),
                }

        # Config
        snap.config = config

        return snap

    def poll(self, container_id: int) -> Optional[ContainerSnapshot]:
        """Poll a single container and return a complete snapshot."""
        try:
            detail = self.get_container_detail(container_id)
            if not detail:
                logger.warning("Container %s: no data returned", container_id)
                return None
            config = self.get_container_config(container_id)
            health = self.get_container_health(container_id)
            groups = self.get_container_groups(container_id)
            snap = self._parse_snapshot(detail, config, health, groups)
            logger.info(
                "Container %s (%s): %s | %.1f kW | %.2f PH/s | %d/%d miners | "
                "Supply %.1f°C | Return %.1f°C | Flow %.1f m³/h",
                snap.container_id, snap.container_name, snap.status,
                snap.power.total_kw or 0,
                snap.farm.total_hashrate_phs,
                snap.farm.miners_on, snap.farm.total_miners,
                snap.hydraulics.supply_temp_c or 0,
                snap.hydraulics.return_temp_c or 0,
                snap.hydraulics.flow_rate_m3h or 0,
            )
            return snap
        except Exception as e:
            logger.error("Container %s poll failed: %s", container_id, e)
            return None

    def poll_all(self) -> List[ContainerSnapshot]:
        """Poll all containers in the workspace."""
        containers = self.get_containers()
        snapshots = []
        for c in containers:
            cid = c.get("id")
            if cid:
                snap = self.poll(cid)
                if snap:
                    snapshots.append(snap)
        return snapshots

    def check_alerts(self, snap: ContainerSnapshot) -> List[Dict]:
        """Evaluate container readings against thresholds and return alerts."""
        alerts = []
        config = snap.config.get("containerConfig", snap.config)
        alert_cfg = config.get("alert", {})

        h = snap.hydraulics
        c = snap.cooling
        p = snap.power
        e = snap.environment
        s = snap.safety

        # Supply temperature alerts
        if h.supply_temp_c:
            ultra_high = alert_cfg.get("supplyTemperatureTT01UltraHighSetpoint", 50)
            high = alert_cfg.get("supplyTemperatureTT01HighSetpoint", 45)
            low = alert_cfg.get("supplyTemperatureTT01LowSetpoint", 20)
            if h.supply_temp_c >= ultra_high:
                alerts.append({"level": "CRITICAL", "sensor": "TT01",
                    "msg": f"Supply temp {h.supply_temp_c}°C ULTRA-HIGH (limit {ultra_high}°C)"})
            elif h.supply_temp_c >= high:
                alerts.append({"level": "WARNING", "sensor": "TT01",
                    "msg": f"Supply temp {h.supply_temp_c}°C HIGH (limit {high}°C)"})
            elif h.supply_temp_c <= low:
                alerts.append({"level": "WARNING", "sensor": "TT01",
                    "msg": f"Supply temp {h.supply_temp_c}°C LOW (limit {low}°C)"})

        # Return pressure alerts
        if h.return_pressure_mpa:
            ultra_low = alert_cfg.get("returnPressurePT02UltraLowSetpoint", 0.01)
            low_p = alert_cfg.get("returnPressurePT02LowSetpoint", 0.02)
            if h.return_pressure_mpa <= ultra_low:
                alerts.append({"level": "CRITICAL", "sensor": "PT02",
                    "msg": f"Return pressure {h.return_pressure_mpa} MPa ULTRA-LOW"})
            elif h.return_pressure_mpa <= low_p:
                alerts.append({"level": "WARNING", "sensor": "PT02",
                    "msg": f"Return pressure {h.return_pressure_mpa} MPa LOW"})

        # Flow rate alerts
        if h.flow_rate_m3h:
            ultra_low_flow = alert_cfg.get("industrialFlowFT01UltraLowSetpoint", 10)
            low_flow = alert_cfg.get("industrialFlowFT01LowSetpoint", 50)
            if h.flow_rate_m3h <= ultra_low_flow:
                alerts.append({"level": "CRITICAL", "sensor": "FT01",
                    "msg": f"Flow rate {h.flow_rate_m3h} m³/h ULTRA-LOW (limit {ultra_low_flow})"})
            elif h.flow_rate_m3h <= low_flow:
                alerts.append({"level": "WARNING", "sensor": "FT01",
                    "msg": f"Flow rate {h.flow_rate_m3h} m³/h LOW (limit {low_flow})"})

        # Conductivity alerts
        if h.conductivity_us:
            high_cond = alert_cfg.get("ET01OverHighValue", 2400)
            if h.conductivity_us >= high_cond:
                alerts.append({"level": "CRITICAL", "sensor": "ET01",
                    "msg": f"Conductivity {h.conductivity_us} µS/cm HIGH — fluid replacement needed"})

        # Supply pressure alerts
        if h.supply_pressure_mpa:
            ultra_high_p = alert_cfg.get("supplyPressurePT01UltraHighSetpoint", 0.7)
            high_p = alert_cfg.get("supplyPressurePT01HighSetpoint", 0.4)
            if h.supply_pressure_mpa >= ultra_high_p:
                alerts.append({"level": "CRITICAL", "sensor": "PT01",
                    "msg": f"Supply pressure {h.supply_pressure_mpa} MPa ULTRA-HIGH"})
            elif h.supply_pressure_mpa >= high_p:
                alerts.append({"level": "WARNING", "sensor": "PT01",
                    "msg": f"Supply pressure {h.supply_pressure_mpa} MPa HIGH"})

        # Safety alerts — always critical
        if s.leakage_detected:
            alerts.append({"level": "CRITICAL", "sensor": "LEAK",
                "msg": "🔴 LEAKAGE DETECTED — immediate inspection required"})
        if s.smoke_detected:
            alerts.append({"level": "CRITICAL", "sensor": "SMOKE",
                "msg": "🔴 SMOKE DETECTED — immediate inspection required"})
        if not s.tank_level_ok:
            alerts.append({"level": "CRITICAL", "sensor": "TANK_LEVEL",
                "msg": "🔴 Tank level abnormal — check fluid level"})
        for alarm in s.emergency_alarms:
            alerts.append({"level": "CRITICAL", "sensor": "EMERGENCY",
                "msg": f"🔴 EMERGENCY: {alarm}"})
        for alarm in s.warning_alarms:
            alerts.append({"level": "WARNING", "sensor": "WARNING",
                "msg": f"⚠️ {alarm}"})

        return alerts


def format_container_report(snap: ContainerSnapshot, alerts: List[Dict] = None) -> str:
    """Format a container snapshot for Slack posting."""
    h = snap.hydraulics
    c = snap.cooling
    p = snap.power
    e = snap.environment
    f = snap.farm

    lines = [
        f"*📦 Container: {snap.container_name}* ({snap.status})",
        f"  Miners: *{f.miners_on}* ON / {f.miners_off} OFF | "
        f"Hashrate: *{f.total_hashrate_phs:.2f} PH/s* | "
        f"Power: *{p.total_kw or 0:.1f} kW* | PUE: {p.pue or 'N/A'}",
    ]

    # Hydraulics
    sup_f = f"{h.supply_temp_f:.1f}°F" if h.supply_temp_f else "N/A"
    ret_f = f"{h.return_temp_f:.1f}°F" if h.return_temp_f else "N/A"
    dt = f"{h.delta_t_c:.1f}°C" if h.delta_t_c else "N/A"
    flow = f"{h.flow_rate_m3h:.1f} m³/h" if h.flow_rate_m3h else "N/A"
    cond = f"{h.conductivity_us:.0f} µS/cm" if h.conductivity_us else "N/A"
    lines.append(f"  Supply: *{sup_f}* | Return: *{ret_f}* | ΔT: *{dt}* | Flow: *{flow}* | Cond: {cond}")

    # Cooling
    dc = f"{c.dry_cooler_freq_hz}Hz" if c.dry_cooler_on else "OFF"
    pump = f"{c.pump_p01_freq_hz}Hz" if c.pump_p01_on else "OFF"
    fans = []
    if c.fan_g21_on: fans.append("G21 ON")
    if c.fan_g22_on: fans.append("G22 ON")
    fan_str = ", ".join(fans) if fans else "OFF"
    lines.append(f"  Pump: *{pump}* | Dry Cooler: *{dc}* | Fans: {fan_str}")

    # Power by zone
    if p.pmm1_kw or p.pmm2_kw:
        lines.append(f"  Power: PMM1={p.pmm1_kw or 0:.0f}kW | PMM2={p.pmm2_kw or 0:.0f}kW | PMM3={p.pmm3_kw or 0:.0f}kW")

    # Alerts
    if alerts:
        critical = [a for a in alerts if a["level"] == "CRITICAL"]
        warnings = [a for a in alerts if a["level"] == "WARNING"]
        if critical:
            lines.append(f"  🔴 *{len(critical)} CRITICAL ALERTS:*")
            for a in critical:
                lines.append(f"    • {a['msg']}")
        if warnings:
            lines.append(f"  🟡 *{len(warnings)} warnings*")

    return "\n".join(lines)
