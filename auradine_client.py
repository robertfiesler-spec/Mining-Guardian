"""
auradine_client.py — Teraflux AH3880 Direct Device API Client
==============================================================
Auradine Teraflux miners expose two API surfaces:

  1. HTTP(S)/REST  -> port 8080 (HTTP) or port 8443 (HTTPS)
     - Requires JWT token auth (POST /token with admin/admin)
     - Full read + write access
     - This is what this client uses

  2. JSON/TCP (CGMiner-compatible) -> port 4028
     - No authentication required
     - Read-only (summary, pools, devs, stats, etc.)
     - Used for quick health checks without token overhead

Default credentials: admin / admin
Default ports:       HTTP=8080, HTTPS=8443, TCP=4028

IMPORTANT OPERATIONAL NOTE:
  Always call standby() before cutting PDU power to an AH3880.
  Disconnecting power or coolant without a graceful standby can
  damage the cooling plate and void warranty.
"""

import json
import socket
import logging
import time
from typing import Any, Dict, Optional

import requests
import urllib3

# Suppress InsecureRequestWarning for self-signed certs on miners
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("mining_guardian")


class AuradineClient:
    """
    Direct HTTP REST client for Teraflux AH3880 miners (Auradine firmware).

    Handles JWT token acquisition and renewal automatically.
    All calls use HTTPS (port 8443) by default with cert verification disabled
    since miners use self-signed certificates.

    Usage:
        client = AuradineClient("192.168.188.X")
        summary = client.get_summary()
        temps   = client.get_temperature()
        client.standby()    # ALWAYS call before PDU cut
        client.reboot()     # full system restart
    """

    DEFAULT_PORT     = 8443
    DEFAULT_USER     = "admin"
    DEFAULT_PASSWORD = "admin"
    TOKEN_TTL        = 3600  # tokens valid ~1 hour; refresh with margin

    def __init__(
        self,
        ip: str,
        port: int = DEFAULT_PORT,
        username: str = DEFAULT_USER,
        password: str = DEFAULT_PASSWORD,
        timeout: int = 10,
        use_https: bool = True,
    ):
        self.ip       = ip
        self.port     = port
        self.username = username
        self.password = password
        self.timeout  = timeout
        scheme        = "https" if use_https else "http"
        self.base_url = f"{scheme}://{ip}:{port}"

        self._token: Optional[str]    = None
        self._token_fetched_at: float = 0.0
        self.session = requests.Session()

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def _fetch_token(self) -> str:
        """Acquire a JWT token from the miner."""
        url  = f"{self.base_url}/token"
        resp = self.session.post(
            url,
            json={"command": "token", "user": self.username, "password": self.password},
            verify=False, timeout=self.timeout,
        )
        resp.raise_for_status()
        token = resp.json()["Token"][0]["Token"]
        logger.debug("AuradineClient [%s]: token acquired", self.ip)
        return token

    def _ensure_token(self) -> str:
        """Return valid token, refreshing if expired or absent."""
        if self._token is None or (time.time() - self._token_fetched_at) > (self.TOKEN_TTL - 60):
            self._token            = self._fetch_token()
            self._token_fetched_at = time.time()
        return self._token

    def _headers(self) -> Dict[str, str]:
        return {"Token": self._ensure_token()}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str) -> Dict[str, Any]:
        url  = f"{self.base_url}{path}"
        resp = self.session.get(url, headers=self._headers(), verify=False, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url  = f"{self.base_url}{path}"
        resp = self.session.post(
            url,
            headers={**self._headers(), "Content-Type": "application/json"},
            json=payload, verify=False, timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Read endpoints — monitoring
    # ------------------------------------------------------------------

    def get_summary(self) -> Dict[str, Any]:
        """
        Fleet-level hashrate snapshot: MHS av/5s/1m/5m/15m,
        Accepted/Rejected shares, Hardware Errors, Best Share.
        Primary monitoring call — also available via TCP port 4028.
        """
        return self._get("/summary")

    def get_temperature(self) -> Dict[str, Any]:
        """
        Per-chip and per-board temps for all 3 hashboards + control board.
        AH3880: 3 boards x 132 chips = 396 chips total.
        ChipTemp is null for boards that are offline.
        """
        return self._get("/temperature")

    def get_mode(self) -> Dict[str, Any]:
        """
        Current mode: eco/normal/turbo/custom, sleep state,
        target TH/s or watt limit, fansInStandby, retuneTime,
        optimizeEco, miningIfNetDown settings.
        """
        return self._get("/mode")

    def get_psu(self) -> Dict[str, Any]:
        """
        PSU status: Vin, Vout, Iout, PowerOut (actual watts),
        PowerIn, 3x temp sensors, 2x fan RPM, model/serial.
        PowerOut is the authoritative power draw for this miner.
        """
        return self._get("/psu")

    def get_fan(self) -> Dict[str, Any]:
        """Fan IDs, Speed, Target, Max RPM. Fans are on PSU for AH3880."""
        return self._get("/fan")

    def get_led(self) -> Dict[str, Any]:
        """
        LED status codes: Code 2=NORMAL, 4=TEMPERATURE, 8=HASH_RATE_LOW,
        10=HASHBOARD_ISSUE, 11=PSU_ISSUE, 13=STANDBY, 19=LOW_COOLANT.
        See LED_CODES dict for full mapping.
        """
        return self._get("/led")

    def get_ipreport(self) -> Dict[str, Any]:
        """
        Network + hardware identity: IP, MAC, model, FluxOS version,
        serial numbers (control board + chassis + each hashboard).
        Use for asset tracking and firmware version detection.
        """
        return self._get("/ipreport")

    def get_devdetails(self) -> Dict[str, Any]:
        """Model and chip count per hashboard (ASICBoard, AI2500 chip model)."""
        return self._get("/devdetails")

    def get_devs(self) -> Dict[str, Any]:
        """Per-board hashrate, share counts, HW errors, elapsed. More granular than summary."""
        return self._get("/devs")

    def get_pools(self) -> Dict[str, Any]:
        """Pool connection status. READ-ONLY — pool management is out of scope."""
        return self._get("/pools")

    def get_version(self) -> Dict[str, Any]:
        """FluxOS version string for firmware drift detection."""
        return self._get("/version")

    def get_frequency(self) -> Dict[str, Any]:
        """Per-ASIC chip frequencies across all hashboards."""
        return self._get("/frequency")

    def get_voltage(self) -> Dict[str, Any]:
        """Per-ASIC chip voltages across all hashboards."""
        return self._get("/voltage")

    def get_network(self) -> Dict[str, Any]:
        """Current network config: protocol, IP, mask, gateway, DNS, hostname."""
        return self._get("/network")

    def get_asc_count(self) -> Dict[str, Any]:
        """Total hashboard count and total ASIC chip count."""
        return self._get("/asccount")

    # ------------------------------------------------------------------
    # Write endpoints — control actions
    # ------------------------------------------------------------------

    def standby(self) -> Dict[str, Any]:
        """
        Place miner in standby (sleep) mode.
        ALWAYS call this before cutting PDU power or disconnecting coolant.
        In standby: mining stops, fans run at 20% (or off if fansInStandby=off).
        This is the required safe shutdown path for AH3880.
        """
        logger.info("AuradineClient [%s]: entering standby", self.ip)
        return self._post("/mode", {"command": "mode", "sleep": "on"})

    def wake(self) -> Dict[str, Any]:
        """Resume mining from standby mode."""
        logger.info("AuradineClient [%s]: waking from standby", self.ip)
        return self._post("/mode", {"command": "mode", "sleep": "off"})

    def reboot(self) -> Dict[str, Any]:
        """Full system reboot (entire miner OS). Use restart_miner() for softer reset."""
        logger.info("AuradineClient [%s]: full reboot", self.ip)
        return self._post("/restart", {"command": "restart"})

    def restart_miner(self) -> Dict[str, Any]:
        """Restart just the mining process (gcminer), not the full OS."""
        logger.info("AuradineClient [%s]: restart miner process", self.ip)
        return self._post("/restart", {"command": "restart", "parameter": "gcminer"})

    def set_mode(self, mode: str) -> Dict[str, Any]:
        """
        Set operating mode: eco, normal, or turbo.
        turbo = maximum hashrate (~600 TH/s on AH3880).
        eco   = optimized for efficiency (lower power).
        """
        valid = {"eco", "normal", "turbo"}
        if mode not in valid:
            raise ValueError(f"Mode must be one of {valid}, got '{mode}'")
        logger.info("AuradineClient [%s]: set mode -> %s", self.ip, mode)
        return self._post("/mode", {"command": "mode", "mode": mode})

    def set_custom_mode_ths(self, target_ths: float) -> Dict[str, Any]:
        """Custom mode: target a specific TH/s output."""
        logger.info("AuradineClient [%s]: custom mode %.1f TH/s", self.ip, target_ths)
        return self._post("/mode", {"command": "mode", "mode": "custom", "tune": "ths", "ths": target_ths})

    def set_custom_mode_power(self, target_watts: int) -> Dict[str, Any]:
        """Custom mode: target a specific watt limit."""
        logger.info("AuradineClient [%s]: custom mode %d W", self.ip, target_watts)
        return self._post("/mode", {"command": "mode", "mode": "custom", "tune": "power", "power": target_watts})

    # ------------------------------------------------------------------
    # Convenience: full health snapshot for Mining Guardian fleet scan
    # ------------------------------------------------------------------

    def get_health_snapshot(self) -> Dict[str, Any]:
        """
        Collect key monitoring data into one normalized dict.
        Called by Mining Guardian during fleet scan for Auradine miners.
        Matches Mining Guardian's miner data model where possible.
        """
        snapshot: Dict[str, Any] = {
            "ip": self.ip, "firmware": "Auradine",
            "api_source": "direct_auradine", "error": None,
        }
        try:
            s = self.get_summary().get("SUMMARY", [{}])[0]
            snapshot["hashrate_ths"]    = round(s.get("MHS av", 0) / 1_000_000, 2)
            snapshot["hashrate_5m_ths"] = round(s.get("MHS 5m", 0) / 1_000_000, 2)
            snapshot["accepted_shares"] = s.get("Accepted", 0)
            snapshot["rejected_shares"] = s.get("Rejected", 0)
            snapshot["hw_errors"]       = s.get("Hardware Errors", 0)
            snapshot["elapsed_seconds"] = s.get("Elapsed", 0)
        except Exception as e:
            snapshot["error"] = f"summary failed: {e}"
            return snapshot

        try:
            p = self.get_psu().get("PSU", [{}])[0]
            power_str               = p.get("PowerOut", "0.00W").replace("W", "").strip()
            snapshot["power_watts"] = float(power_str)
            snapshot["power_kw"]    = round(float(power_str) / 1000, 3)
            snapshot["psu_temp1_c"] = float(p.get("Temp1", "0C").replace("C", "").strip())
            snapshot["psu_temp2_c"] = float(p.get("Temp2", "0C").replace("C", "").strip())
        except Exception as e:
            logger.debug("AuradineClient [%s]: PSU read: %s", self.ip, e)

        try:
            m = self.get_mode().get("Mode", [{}])[0]
            snapshot["mode"]       = m.get("Mode", "unknown")
            snapshot["sleep"]      = m.get("Sleep", "off")
            snapshot["target_ths"] = m.get("Ths", None)
        except Exception as e:
            logger.debug("AuradineClient [%s]: mode read: %s", self.ip, e)

        try:
            l = self.get_led().get("LED", [{}])[0]
            led_code               = l.get("Code", 0)
            snapshot["led_code"]   = led_code
            snapshot["led_status"] = LED_CODES.get(led_code, f"unknown({led_code})")
            snapshot["led_msg"]    = l.get("Msg", "")
        except Exception as e:
            logger.debug("AuradineClient [%s]: LED read: %s", self.ip, e)

        try:
            boards = self.get_temperature().get("Temperature", [])
            chip_temps, board_temps = [], []
            for board in boards:
                chip_temps.extend(
                    t["Temperature"] for t in (board.get("ChipTemp") or [])
                    if t.get("Temperature", 0) > 0
                )
                board_temps.extend(
                    t["Temperature"] for t in (board.get("BoardTemp") or [])
                    if t.get("Temperature", 0) > 0
                )
            if chip_temps:
                snapshot["chip_temp_max_c"] = round(max(chip_temps), 1)
                snapshot["chip_temp_avg_c"] = round(sum(chip_temps) / len(chip_temps), 1)
            if board_temps:
                snapshot["board_temp_max_c"] = round(max(board_temps), 1)
        except Exception as e:
            logger.debug("AuradineClient [%s]: temp read: %s", self.ip, e)

        return snapshot

    # ------------------------------------------------------------------
    # CGMiner TCP fallback (no auth, read-only, port 4028)
    # ------------------------------------------------------------------

    @staticmethod
    def tcp_command(ip: str, command: str, port: int = 4028, timeout: int = 5) -> Dict[str, Any]:
        """Send a CGMiner TCP command and return the JSON response. No auth required."""
        cmd = json.dumps({"command": command}).encode() + b"\n"
        try:
            with socket.create_connection((ip, port), timeout=timeout) as sock:
                sock.sendall(cmd)
                data = b""
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    data += chunk
            return json.loads(data.decode())
        except Exception as e:
            return {"error": str(e)}

    @classmethod
    def tcp_summary(cls, ip: str, port: int = 4028, timeout: int = 5) -> Dict[str, Any]:
        """Quick hashrate check — no token needed."""
        return cls.tcp_command(ip, "summary", port, timeout)

    @classmethod
    def tcp_version(cls, ip: str, port: int = 4028, timeout: int = 5) -> Dict[str, Any]:
        """Get firmware version via TCP — useful for firmware detection without token."""
        return cls.tcp_command(ip, "version", port, timeout)


# ------------------------------------------------------------------
# LED status code mapping (from Auradine API Reference)
# ------------------------------------------------------------------

LED_CODES = {
    1:  "NO_POWER",
    2:  "NORMAL",
    3:  "LOCATE_MINER",
    4:  "TEMPERATURE",
    5:  "POOL_CONFIG",
    6:  "NETWORK",
    7:  "CONTROL_BOARD",
    8:  "HASH_RATE_LOW",
    9:  "FAN_ISSUE",
    10: "HASHBOARD_ISSUE",
    11: "PSU_ISSUE",
    12: "TUNING",
    13: "STANDBY",
    14: "RESETTING",
    15: "WARMING",
    16: "UPGRADING",
    19: "LOW_COOLANT",
}

# OLED fault codes from AH3880 hardware reference
OLED_FAULTS = {
    "NO PWR":        ("Fault",   "No power"),
    "TEMP HIGH":     ("Fault",   "Temperature too high"),
    "LOW FLOW RATE": ("Fault",   "Low coolant flow rate — check hydro system"),
    "POOL CONFIG":   ("Fault",   "Pool configuration invalid"),
    "NET ERR":       ("Fault",   "Network issue"),
    "SD FAULT":      ("Fault",   "SD card faulty"),
    "LOW HASH":      ("Normal",  "Hash rate lower than target"),
    "PSU FAN":       ("Fault",   "Fan malfunction"),
    "PSU ERR":       ("Fault",   "PSU malfunction"),
    "HB ERR":        ("Fault",   "Hash board malfunction"),
    "RST PRESSED":   ("Reset",   "Reset button pressed — factory reset in progress"),
    "HASH RED TEMP": ("Normal",  "Reduced hash rate due to high temp"),
    "PWR LIMIT":     ("Normal",  "Reduced hash rate due to power limit"),
    "LEAK DETECTED": ("Fault",   "LEAK detected in rear liquid fittings — URGENT"),
}

# AH3880 operating modes and their meaning
AH3880_MODES = {
    "turbo":  {"description": "Maximum hashrate",    "approx_ths": 600},
    "normal": {"description": "Balanced default",    "approx_ths": 500},
    "eco":    {"description": "Efficiency optimized","approx_ths": None},
    "custom": {"description": "User-defined target", "approx_ths": None},
}
