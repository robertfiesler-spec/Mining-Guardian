"""
pdu_client.py — BiXBiT 2U+PDU Client (firmware 1.0.90)
========================================================
Direct HTTP client for the BiXBiT smart PDU used in USA 188.

Auth:  HMAC-SHA1 login — HmacSHA1(nonce, sha1(password))
       Session tracked server-side via requests.Session()

Endpoints:
  Home_Upload.cgi              — facility-level power (L1/L2/L3, total kW, kWh)
  switch_control_Upload.cgi    — per-outlet live readings (voltage, amps, kW, on/off)
  switch_data_Onceload.cgi     — outlet config (names, thresholds)
  switch_control.cgi (POST)    — outlet on/off control

PDU layout (8 outlets per unit):
  Two PDUs in facility:
    orient_RPDU 163 @ 192.168.188.15
    orient_RPDU 164 @ 192.168.188.16
"""

import hashlib
import hmac as hmac_lib
import logging
import random
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger("mining_guardian")

# Charset used by PDU firmware for nonce generation
_NONCE_CHARS = 'ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678'

# Outlet block stride in switch_control_Upload.cgi response
_OUTLET_STRIDE = 21
_OUTLET_OFFSET = 4   # first outlet block starts at field 4

# Fields within each outlet block
_F_V1   = 0   # L1 voltage
_F_V2   = 2   # L2 voltage
_F_V3   = 4   # L3 voltage
_F_A1   = 6   # L1 current
_F_A2   = 8   # L2 current
_F_A3   = 10  # L3 current
_F_KW   = 12  # active power kW
_F_PF   = 13  # power factor
_F_KWH  = 14  # energy kWh
_F_HZ   = 15  # frequency
_F_STAT = 16  # status (OK/Alarm)
_F_OON  = 18  # on/off (ON/OFF)
_F_WIRE = 19  # wiring (3P3W etc)


@dataclass
class OutletReading:
    """Live per-outlet readings from switch_control_Upload.cgi."""
    index:        int
    name:         str
    on:           bool
    voltage_l1_v: Optional[float]
    voltage_l2_v: Optional[float]
    voltage_l3_v: Optional[float]
    current_l1_a: Optional[float]
    current_l2_a: Optional[float]
    current_l3_a: Optional[float]
    power_kw:     Optional[float]
    power_factor: Optional[float]
    energy_kwh:   Optional[float]
    frequency_hz: Optional[float]
    status:       str   # OK / Alarm / --

    @property
    def avg_voltage_v(self) -> Optional[float]:
        vals = [v for v in [self.voltage_l1_v, self.voltage_l2_v, self.voltage_l3_v] if v]
        return round(sum(vals) / len(vals), 1) if vals else None

    @property
    def avg_current_a(self) -> Optional[float]:
        vals = [v for v in [self.current_l1_a, self.current_l2_a, self.current_l3_a] if v]
        return round(sum(vals) / len(vals), 2) if vals else None


@dataclass
class PDUReading:
    """Facility-level PDU reading from Home_Upload.cgi."""
    ip:              str
    timestamp:       str
    model:           str
    firmware:        str
    l1_voltage_v:    Optional[float]
    l1_current_a:    Optional[float]
    l1_power_kw:     Optional[float]
    l1_power_factor: Optional[float]
    l1_energy_kwh:   Optional[float]
    l2_voltage_v:    Optional[float]
    l2_current_a:    Optional[float]
    l2_power_kw:     Optional[float]
    l3_voltage_v:    Optional[float]
    l3_current_a:    Optional[float]
    l3_power_kw:     Optional[float]
    total_power_kw:  Optional[float]
    total_energy_kwh: Optional[float]
    frequency_hz:    Optional[float]
    alarm_status:    str
    outlets:         list = field(default_factory=list)  # List[OutletReading]


def _parse_float(s: str) -> Optional[float]:
    """Strip unit suffixes and parse to float. Returns None for '-' or '0.0V'='0.0' etc."""
    if not s or s in ('-', '--'):
        return None
    cleaned = re.sub(r'[A-Za-z%]', '', s).strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _rand_nonce(n: int = 20) -> str:
    return ''.join(random.choices(_NONCE_CHARS, k=n))


def _sha1_hex(s: str) -> str:
    return hashlib.sha1(s.encode('utf-8')).hexdigest()


def _hmac_sha1_hex(message: str, key: str) -> str:
    return hmac_lib.new(key.encode('utf-8'), message.encode('utf-8'), hashlib.sha1).hexdigest()


class PDUClient:
    """
    HTTP client for one BiXBiT 2U+PDU unit.

    Usage:
        pdu = PDUClient('192.168.188.15')
        pdu.login()
        reading = pdu.read()
        print(reading.total_power_kw)

    Session auto-renews if it expires (re-login on next read attempt).
    """

    SESSION_TTL = 280   # re-login after this many seconds (PDU times out at ~300s)
    TIMEOUT     = 8

    def __init__(self, ip: str, user: str = 'admin', password: str = 'admin',
                 outlet_names: Optional[dict] = None):
        self.ip           = ip
        self.user         = user
        self.password     = password
        self.outlet_names = outlet_names or {}   # {outlet_index: "friendly name"}
        self._session:    Optional[requests.Session] = None
        self._logged_in:  float = 0.0            # epoch when last login succeeded

    def _base(self, path: str) -> str:
        return f'http://{self.ip}/{path.lstrip("/")}'

    def login(self) -> bool:
        """Authenticate and establish session. Returns True on success."""
        s = requests.Session()
        try:
            s.get(self._base('/'), timeout=self.TIMEOUT)
            nonce = _rand_nonce(20)
            port  = _hmac_sha1_hex(nonce, _sha1_hex(self.password))
            r = s.post(
                self._base('/login.cgi'),
                data={'ip': self.user, 'port': port, 'radom': nonce, 'login': 'Log On'},
                timeout=self.TIMEOUT,
                allow_redirects=True,
            )
            # Success = response contains meta-refresh to home0.html
            # (PDU uses HTML meta-refresh, not HTTP 302)
            if 'home0.html' in r.text or 'meta' in r.text.lower()[:200]:
                self._session   = s
                self._logged_in = time.time()
                logger.info("PDU %s: login OK", self.ip)
                return True
            logger.warning("PDU %s: login failed (still on login page)", self.ip)
            return False
        except Exception as e:
            logger.warning("PDU %s: login error: %s", self.ip, e)
            return False

    def _ensure_session(self) -> bool:
        """Re-login if session is expired or missing."""
        if self._session is None or (time.time() - self._logged_in) > self.SESSION_TTL:
            return self.login()
        return True

    def _get(self, path: str) -> Optional[str]:
        """GET with auto session renewal. Returns raw text or None."""
        if not self._ensure_session():
            return None
        try:
            r = self._session.get(self._base(path), timeout=self.TIMEOUT)
            if r.status_code == 200:
                return r.text
            logger.warning("PDU %s: GET %s returned %s", self.ip, path, r.status_code)
            return None
        except Exception as e:
            logger.warning("PDU %s: GET %s error: %s", self.ip, path, e)
            self._session = None  # force re-login next time
            return None

    def read_facility(self) -> Optional[PDUReading]:
        """Read facility-level power from Home_Upload.cgi."""
        raw = self._get(f'/Home_Upload.cgi?t={time.time()}')
        if not raw:
            return None
        f = raw.strip().split(';')
        if len(f) < 40:
            return None
        try:
            return PDUReading(
                ip              = self.ip,
                timestamp       = f[90] if len(f) > 90 else '',
                model           = f[1],
                firmware        = f[2],
                l1_voltage_v    = _parse_float(f[3]),
                l1_current_a    = _parse_float(f[4]),
                l1_power_kw     = _parse_float(f[7]),
                l1_power_factor = _parse_float(f[10]),
                l1_energy_kwh   = _parse_float(f[11]),
                l2_voltage_v    = _parse_float(f[13]),
                l2_current_a    = _parse_float(f[14]),
                l2_power_kw     = _parse_float(f[17]),
                l3_voltage_v    = _parse_float(f[23]),
                l3_current_a    = _parse_float(f[24]),
                l3_power_kw     = _parse_float(f[27]),
                total_power_kw  = _parse_float(f[33]),
                total_energy_kwh= _parse_float(f[37]),
                frequency_hz    = _parse_float(f[39]),
                alarm_status    = f[91] if len(f) > 91 else 'unknown',
            )
        except Exception as e:
            logger.warning("PDU %s: parse Home_Upload failed: %s", self.ip, e)
            return None

    def read_outlets(self) -> list:
        """Read per-outlet live data from switch_control_Upload.cgi.
        Returns list of OutletReading (8 outlets)."""
        raw = self._get(f'/switch_control_Upload.cgi?t={time.time()}')
        if not raw:
            return []
        f = raw.strip().split(';')

        # Get outlet names from Onceload
        names = self._outlet_names_from_onceload()

        outlets = []
        for idx in range(8):
            base = _OUTLET_OFFSET + (idx * _OUTLET_STRIDE)
            if base + _OUTLET_STRIDE > len(f):
                break
            b = f[base:]
            name = names.get(idx + 1) or self.outlet_names.get(idx + 1) or f'Outlet{idx+1}'
            on   = b[_F_OON].strip().upper() == 'ON' if len(b) > _F_OON else False
            outlets.append(OutletReading(
                index        = idx + 1,
                name         = name,
                on           = on,
                voltage_l1_v = _parse_float(b[_F_V1])  if len(b) > _F_V1  else None,
                voltage_l2_v = _parse_float(b[_F_V2])  if len(b) > _F_V2  else None,
                voltage_l3_v = _parse_float(b[_F_V3])  if len(b) > _F_V3  else None,
                current_l1_a = _parse_float(b[_F_A1])  if len(b) > _F_A1  else None,
                current_l2_a = _parse_float(b[_F_A2])  if len(b) > _F_A2  else None,
                current_l3_a = _parse_float(b[_F_A3])  if len(b) > _F_A3  else None,
                power_kw     = _parse_float(b[_F_KW])  if len(b) > _F_KW  else None,
                power_factor = _parse_float(b[_F_PF])  if len(b) > _F_PF  else None,
                energy_kwh   = _parse_float(b[_F_KWH]) if len(b) > _F_KWH else None,
                frequency_hz = _parse_float(b[_F_HZ])  if len(b) > _F_HZ  else None,
                status       = b[_F_STAT].strip()      if len(b) > _F_STAT else '--',
            ))
        return outlets

    def _outlet_names_from_onceload(self) -> dict:
        """Parse outlet names from switch_data_Onceload.cgi. Returns {outlet_num: name}."""
        raw = self._get('/switch_data_Onceload.cgi')
        if not raw:
            return {}
        f   = raw.strip().split(';')
        names = {}
        # Each block is 13 fields. Format per block:
        # [outlet_num, name, state, on_off, current, max_current, ...]
        # First block starts at index 2 in the raw fields.
        # The Onceload has a 2-field header before the outlets.
        i = 2
        outlet_num = 1
        while i < len(f) and outlet_num <= 8:
            # Try to read outlet number from this position
            try:
                candidate = int(f[i])
                if 1 <= candidate <= 8:
                    name = f[i + 1].strip() if i + 1 < len(f) else f'Outlet{candidate}'
                    if name and name not in ('-', ''):
                        names[candidate] = name
                    i += 13
                    outlet_num += 1
                    continue
            except (ValueError, IndexError):
                pass
            i += 1
        return names

    def read(self) -> Optional[PDUReading]:
        """Read facility + outlet data and return combined PDUReading."""
        facility = self.read_facility()
        if not facility:
            return None
        facility.outlets = self.read_outlets()
        return facility

    def set_outlet(self, outlet_index: int, on: bool) -> bool:
        """
        Turn an outlet on or off via switch_control.cgi.
        outlet_index: 1-8
        on: True = ON, False = OFF
        Returns True on success.
        WARNING: Turning off an outlet cuts power to the miner immediately.
        This should only be called after explicit operator approval.
        """
        if not self._ensure_session():
            return False
        action = 'on' if on else 'off'
        try:
            r = self._session.post(
                self._base('/switch_control.cgi'),
                data={
                    'outlet': str(outlet_index),
                    'action': action,
                    'delay':  '0',
                },
                timeout=self.TIMEOUT,
            )
            success = r.status_code == 200
            logger.info(
                "PDU %s outlet %s -> %s: %s",
                self.ip, outlet_index, action.upper(), "OK" if success else f"FAILED {r.status_code}"
            )
            return success
        except Exception as e:
            logger.warning("PDU %s: set_outlet %s error: %s", self.ip, outlet_index, e)
            return False
