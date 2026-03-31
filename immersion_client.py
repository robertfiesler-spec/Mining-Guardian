"""
immersion_client.py — Fog Hashing Elite 1 Immersion Tank Client
================================================================
Direct REST API client for the immersion tank controller at 192.168.188.20.

No authentication required — open local network API.
Product: Fog Hashing Elite 1 (alias: B100)

Endpoints:
  GET /api/device-status       — full tank + port readings
  GET /api/device-capabilities — what features are supported
  GET /api/product-type        — product model string
  POST /api/device-control     — control pump, fans, port switches

Key data available:
  tank.in_temp       — fluid inlet temp (°C)
  tank.out_temp      — fluid outlet temp (°C)
  tank.pump_switch   — pump running bool
  tank.fluid_level   — liquid level OK bool
  tank.alarms        — list of active alarm codes
  tank.mining_switch — main mining power switch
  power_ports[n]     — per-port: voltage_a/b/c, current_a/b/c, power_a/b/c, switch, alarm

Alarm codes (from app.js):
  0=None, 1=PhaseLoss, 2=CommError, 3=HighTemp, 4=TempShutdown,
  5=LowLiquid, 6=LowVoltage, 7=HighVoltage, 8=OverCurrent,
  9=PumpPower, 10=FanPower, 11=FanSpeed, 12=FanComm, 13=Smoke,
  14=HighHumidity, 15=LowTemp, 16=LowHumidity, 17=SensorOffline,
  18=LiquidShutdown
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger("mining_guardian")

ALARM_MESSAGES = {
    0: "No Alarm", 1: "Phase Loss", 2: "Communication Error",
    3: "High Temperature", 4: "Over-temperature Shutdown",
    5: "Low Liquid Level", 6: "Low Voltage", 7: "High Voltage",
    8: "Over Current", 9: "Pump Power Error", 10: "Fan Power Error",
    11: "Fan Speed Error", 12: "Fan Communication Error", 13: "Smoke Detected",
    14: "High Humidity", 15: "Low Temperature", 16: "Low Humidity",
    17: "Sensor Offline", 18: "Liquid Level Shutdown",
}

ALARM_LEVELS = {
    0: "info", 1: "warning", 2: "warning", 3: "warning", 4: "critical",
    5: "warning", 6: "warning", 7: "warning", 8: "warning", 9: "critical",
    10: "critical", 11: "warning", 12: "warning", 13: "critical",
    14: "warning", 15: "info", 16: "info", 17: "warning", 18: "critical",
}


@dataclass
class TankPort:
    """Per-port power readings from the immersion tank."""
    index:      int
    on:         bool
    voltage_a:  float
    voltage_b:  float
    voltage_c:  float
    current_a:  float
    current_b:  float
    current_c:  float
    power_a_kw: float
    power_b_kw: float
    power_c_kw: float
    factor_a:   float
    factor_b:   float
    factor_c:   float
    alarm:      int

    @property
    def total_power_kw(self) -> float:
        return round(self.power_a_kw + self.power_b_kw + self.power_c_kw, 3)

    @property
    def avg_voltage(self) -> Optional[float]:
        vals = [v for v in [self.voltage_a, self.voltage_b, self.voltage_c] if v > 0]
        return round(sum(vals) / len(vals), 1) if vals else None

    @property
    def avg_current(self) -> Optional[float]:
        vals = [c for c in [self.current_a, self.current_b, self.current_c] if c > 0]
        return round(sum(vals) / len(vals), 2) if vals else None

    @property
    def alarm_message(self) -> str:
        return ALARM_MESSAGES.get(self.alarm, f"Unknown alarm {self.alarm}")

    @property
    def alarm_level(self) -> str:
        return ALARM_LEVELS.get(self.alarm, "warning")


@dataclass
class TankReading:
    """Full immersion tank status reading."""
    ip:                str
    timestamp:         float
    alias:             str
    product_type:      str

    # Fluid temps
    in_temp_c:         Optional[float]
    out_temp_c:        Optional[float]
    target_temp_c:     Optional[float]
    temp_threshold_c:  Optional[float]
    temp_shutdown_c:   Optional[float]

    # Subsystem status
    pump_on:           bool
    mining_switch_on:  bool
    fluid_level_ok:    bool
    running_miners:    int

    # Fans (immersion may have none or aux fans)
    fan_status:        list   # list of {status, speed, error_code}

    # Alarms
    alarms:            list   # list of alarm codes
    has_critical_alarm: bool

    # Per-port power data
    ports:             list   # List[TankPort]

    @property
    def active_ports(self) -> list:
        return [p for p in self.ports if p.on]

    @property
    def total_power_kw(self) -> float:
        return round(sum(p.total_power_kw for p in self.active_ports), 3)


class ImmersionTankClient:
    """
    REST client for the Fog Hashing Elite 1 immersion tank.

    No authentication required.
    Polls /api/device-status for all data.
    """

    TIMEOUT = 8

    def __init__(self, ip: str = '192.168.188.20'):
        self.ip      = ip
        self._session = requests.Session()

    def _get(self, path: str) -> Optional[dict]:
        try:
            r = self._session.get(
                f'http://{self.ip}{path}',
                timeout=self.TIMEOUT
            )
            if r.status_code == 200:
                return r.json()
            logger.warning("ImmersionTank %s: GET %s returned %s", self.ip, path, r.status_code)
            return None
        except Exception as e:
            logger.warning("ImmersionTank %s: GET %s error: %s", self.ip, path, e)
            return None

    def read(self) -> Optional[TankReading]:
        """Fetch full tank status. Returns TankReading or None on failure."""
        data = self._get('/api/device-status')
        if not data:
            return None

        tank  = data.get('tank', {})
        fans  = data.get('fan', [])
        ports_raw = data.get('power_ports', [])

        # Parse alarms
        alarm_codes = tank.get('alarms', [])
        has_critical = any(ALARM_LEVELS.get(a, 'info') == 'critical' for a in alarm_codes)

        # Parse per-port data
        ports = []
        for i, p in enumerate(ports_raw):
            ports.append(TankPort(
                index      = i + 1,
                on         = bool(p.get('switch', False)),
                voltage_a  = float(p.get('voltage_a', 0)),
                voltage_b  = float(p.get('voltage_b', 0)),
                voltage_c  = float(p.get('voltage_c', 0)),
                current_a  = float(p.get('current_a', 0)),
                current_b  = float(p.get('current_b', 0)),
                current_c  = float(p.get('current_c', 0)),
                power_a_kw = float(p.get('power_a', 0)),
                power_b_kw = float(p.get('power_b', 0)),
                power_c_kw = float(p.get('power_c', 0)),
                factor_a   = float(p.get('factor_a', -1)),
                factor_b   = float(p.get('factor_b', -1)),
                factor_c   = float(p.get('factor_c', -1)),
                alarm      = int(p.get('alarm', 0)),
            ))

        return TankReading(
            ip               = self.ip,
            timestamp        = time.time(),
            alias            = tank.get('alias', 'unknown'),
            product_type     = 'elite_1',
            in_temp_c        = tank.get('in_temp'),
            out_temp_c       = tank.get('out_temp'),
            target_temp_c    = tank.get('target_temp'),
            temp_threshold_c = tank.get('temp_threshold'),
            temp_shutdown_c  = tank.get('temp_shutdown_threshold'),
            pump_on          = bool(tank.get('pump_switch', False)),
            mining_switch_on = bool(tank.get('mining_switch', False)),
            fluid_level_ok   = bool(tank.get('fluid_level', True)),
            running_miners   = int(tank.get('running_miner_count', 0)),
            fan_status       = fans,
            alarms           = alarm_codes,
            has_critical_alarm = has_critical,
            ports            = ports,
        )

    def get_capabilities(self) -> dict:
        return self._get('/api/device-capabilities') or {}

    def control_port(self, port_index: int, on: bool) -> bool:
        """
        Turn a power port on or off.
        port_index: 1-based.
        WARNING: This cuts/restores power to miners. Requires operator approval.
        """
        try:
            r = self._session.post(
                f'http://{self.ip}/api/device-control',
                json={
                    'type': 'power-port',
                    'port': port_index,
                    'action': 'on' if on else 'off',
                },
                timeout=self.TIMEOUT,
            )
            success = r.status_code == 200
            logger.info(
                "ImmersionTank %s port %s -> %s: %s",
                self.ip, port_index, 'ON' if on else 'OFF',
                'OK' if success else f'FAILED {r.status_code}'
            )
            return success
        except Exception as e:
            logger.warning("ImmersionTank %s: control_port error: %s", self.ip, e)
            return False
