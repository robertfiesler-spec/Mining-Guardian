"""auradine_client.py — Teraflux AH3880 / AT2880 Direct Device API Client
==============================================================
SECONDARY PATH — AMS IS PRIMARY for fleet remediation.

Architecture rule for Mining Guardian:
  ALL miner commands (reboot, standby, profile changes, PDU control, etc.)
  go through AMS first. AMS provides the audit log, handles auth, and the
  Mac Mini only needs LAN access to AMS — not direct access to each miner.

This client is used for:
  1. Reading telemetry the AMS doesn't expose (per-chip temps, PSU details,
     DVFS state, leak detection)
  2. Fetching logs directly from the miner for the manual_log_upload pipeline
     when AMS doesn't have a fresh copy yet
  3. Future fallback if AMS is down

Do NOT use this client to issue write commands (reboot, standby, profile
changes) in normal flows — always go through AMSClient first.

------------------------------------------------------------------
Auradine API discovery (Apr 8 2026)
------------------------------------------------------------------
Tested live against AH3880 at 192.168.188.28 with admin/admin.

LOGIN:
  POST https://<ip>:8443/token
  Content-Type: application/json
  Body: {"command":"token","user":"admin","password":"admin"}
  Returns: {"STATUS":[{"STATUS":"S",...}], "Token":[{"Token":"<JWT>"}]}
  Token lifetime: 1 hour

READ COMMANDS (GET on /<command>, Authorization: Bearer <JWT>):
  /summary       — fleet stats, MHS averages, wattage, throttle
  /devs          — per-board stats (temperature, MHS, hardware errors)
  /devdetails    — board model, chip count
  /version       — GCMiner + API version
  /stats         — pool/board call counters
  /pools         — pool config + accept/reject
  /psu           — PSU voltages, temps, model, serial, firmware revs
  /temperature   — board temps + per-chip temperatures (~432 chips per board)
  /mode          — operating mode (custom/eco/turbo), tune target Ths,
                   leak detection state, sleep state
  /network       — network config (DHCP, hostname, DNS)

LOG COMMANDS (different header — capital T "Token", NOT "Bearer"):
  POST /log
    Headers:  Token: <JWT>
    Body:     {"command":"getLog",
               "daemon":["gcminer"],
               "level":["alarms","log","crash","audit"],
               "filters":[]}
    Returns:  log content as text in the response body
    Notes:    daemons available — monitord, osutil, kernel, webui-server,
              gcminer, api-server, etc-files, factory-files
              etc-files and factory-files do NOT take a level array

  GET /techsupport
    Headers:  Token: <JWT>
    Returns:  {"STATUS":[{"STATUS":"S",...}], "TECHSUPPORT":[{"jobid":"<id>"}]}
    Then poll: GET /techsupport?command=status&jobid=<id>
               until STATUS becomes "done"
    Then download the resulting tar.gz file

WRITE COMMANDS (do NOT use unless explicitly authorized — go through AMS first):
  POST /restart           — reboot the miner
  POST /factory-reset     — wipe to factory defaults
  POST /reimage           — re-flash firmware
  POST /firmware-upgrade  — upgrade firmware
  POST /led               — flash chassis LED for physical identification

PSU SAFETY NOTE:
  Always call standby BEFORE cutting PDU power to an AH3880. Disconnecting
  power or coolant without a graceful standby can damage the cooling plate
  and void warranty. AMS handles this correctly when commands go through it.
  This client deliberately does NOT expose a power-off method.
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests
import urllib3

# Disable the InsecureRequestWarning for the self-signed cert on miners
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("mining_guardian")


# S-9 hardening (2026-04-29): the Auradine factory default is literally
# admin/admin and previously this client silently used those values when
# AURADINE_USER / AURADINE_PASS were unset. That meant a misconfigured
# install would happily try to log into every miner with the factory
# default — and on a fleet where the operator has rotated the password,
# this generates spurious auth-failure noise that masks real issues.
#
# New behavior:
#   - DEFAULT_USER / DEFAULT_PASS read from env exactly as before.
#   - If env is unset, _FACTORY_DEFAULT is used (admin/admin) but a single
#     WARNING is emitted at module import so operators can see it.
#   - When MG_REQUIRE_AURADINE_AUTH=1 is set, the import raises
#     RuntimeError instead of warning. Production installs (Mac Mini and
#     beyond) should set this so a missing env var is a hard failure, not
#     a silent fallback.
_FACTORY_DEFAULT_USER = "admin"
_FACTORY_DEFAULT_PASS = "admin"
_AURADINE_USER_ENV = os.environ.get("AURADINE_USER")
_AURADINE_PASS_ENV = os.environ.get("AURADINE_PASS")
_REQUIRE_AURADINE_AUTH = os.environ.get("MG_REQUIRE_AURADINE_AUTH", "0") == "1"

if _AURADINE_USER_ENV is None or _AURADINE_PASS_ENV is None:
    _msg = (
        "AURADINE_USER and/or AURADINE_PASS not set in the environment; "
        "falling back to factory default (admin/admin). Set these in the "
        "installer-managed .env to silence this warning."
    )
    if _REQUIRE_AURADINE_AUTH:
        raise RuntimeError(
            _msg + " MG_REQUIRE_AURADINE_AUTH=1 is set, so this is a hard "
            "failure rather than a fallback."
        )
    logger = logging.getLogger("mining_guardian")
    logger.warning("[auradine_client] %s", _msg)


class AuradineClient:
    """Direct API client for Auradine Teraflux miners (AH3880, AT2880, etc.)."""

    DEFAULT_PORT_HTTPS = 8443
    DEFAULT_USER       = _AURADINE_USER_ENV or _FACTORY_DEFAULT_USER
    DEFAULT_PASS       = _AURADINE_PASS_ENV or _FACTORY_DEFAULT_PASS
    TOKEN_LIFETIME_SEC = 3600  # JWT is valid for 1 hour

    # Daemons available via the /log endpoint
    DAEMONS = (
        "monitord", "osutil", "kernel", "webui-server",
        "gcminer", "api-server", "etc-files", "factory-files",
    )
    # File types per daemon (etc-files and factory-files don't take levels)
    LOG_LEVELS = ("alarms", "log", "crash", "audit")

    def __init__(self, ip: str, user: str = DEFAULT_USER,
                 password: str = DEFAULT_PASS, port: int = DEFAULT_PORT_HTTPS,
                 timeout: int = 15):
        self.ip       = ip
        self.user     = user
        self.password = password
        self.port     = port
        self.timeout  = timeout
        self.base_url = f"https://{ip}:{port}"
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

    # ─────────────────────────────────────────────────────────────────
    # Authentication
    # ─────────────────────────────────────────────────────────────────

    def login(self) -> bool:
        """Acquire a new JWT token. Returns True on success."""
        try:
            resp = requests.post(
                f"{self.base_url}/token",
                json={"command": "token", "user": self.user, "password": self.password},
                verify=False,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            status = data.get("STATUS", [{}])[0]
            if status.get("STATUS") != "S":
                logger.warning("Auradine login failed for %s: %s", self.ip, status.get("Msg"))
                return False
            tokens = data.get("Token", [])
            if not tokens:
                logger.warning("Auradine login returned no token for %s", self.ip)
                return False
            self._token = tokens[0].get("Token")
            self._token_expires_at = time.time() + self.TOKEN_LIFETIME_SEC - 60  # 60s buffer
            logger.info("Auradine login OK for %s", self.ip)
            return True
        except Exception as e:
            logger.warning("Auradine login error for %s: %s", self.ip, e)
            return False

    def _ensure_token(self) -> bool:
        """Login if no token or token has expired."""
        if not self._token or time.time() >= self._token_expires_at:
            return self.login()
        return True

    # ─────────────────────────────────────────────────────────────────
    # Read commands (GET on /<command> with Bearer token)
    # ─────────────────────────────────────────────────────────────────

    def _get(self, path: str) -> Optional[Dict[str, Any]]:
        """Issue a GET to a read endpoint and return parsed JSON, or None on error."""
        if not self._ensure_token():
            return None
        try:
            resp = requests.get(
                f"{self.base_url}{path}",
                headers={"Authorization": f"Bearer {self._token}"},
                verify=False,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("Auradine GET %s on %s failed: %s", path, self.ip, e)
            return None

    def summary(self) -> Optional[Dict[str, Any]]:
        """Return the fleet summary stats (MHS rates, wattage, throttle, accept/reject)."""
        data = self._get("/summary")
        if data and data.get("SUMMARY"):
            return data["SUMMARY"][0]
        return None

    def devs(self) -> Optional[List[Dict[str, Any]]]:
        """Return per-board stats."""
        data = self._get("/devs")
        return data.get("DEVS") if data else None

    def devdetails(self) -> Optional[List[Dict[str, Any]]]:
        """Return board model + chip count for each board."""
        data = self._get("/devdetails")
        return data.get("DEVDETAILS") if data else None

    def version(self) -> Optional[Dict[str, Any]]:
        """Return GCMiner + API version."""
        data = self._get("/version")
        if data and data.get("VERSION"):
            return data["VERSION"][0]
        return None

    def pools(self) -> Optional[List[Dict[str, Any]]]:
        """Return pool config + accept/reject counts."""
        data = self._get("/pools")
        return data.get("POOLS") if data else None

    def psu(self) -> Optional[Dict[str, Any]]:
        """Return PSU state — voltages, temps, model, serial, firmware revs."""
        data = self._get("/psu")
        if data and data.get("PSU"):
            return data["PSU"][0]
        return None

    def temperature(self) -> Optional[List[Dict[str, Any]]]:
        """Return board + per-chip temperatures.

        Returns a list of dicts, one per board, each with:
          - ID, Name, BoardTemp[], ChipTemp[]
        Plus a Control Board entry with InletTemp, OutletTemp, FlowRate.
        """
        data = self._get("/temperature")
        return data.get("Temperature") if data else None

    def mode(self) -> Optional[Dict[str, Any]]:
        """Return operating mode, tune target Ths, leak detection, sleep state."""
        data = self._get("/mode")
        if data and data.get("Mode"):
            return data["Mode"][0]
        return None

    def network(self) -> Optional[Dict[str, Any]]:
        """Return network configuration."""
        data = self._get("/network")
        if data and data.get("Network"):
            return data["Network"][0]
        return None

    # ─────────────────────────────────────────────────────────────────
    # Log fetch (POST /log with Token: header, NOT Bearer)
    # ─────────────────────────────────────────────────────────────────

    def get_log(self, daemon: str, levels: Optional[List[str]] = None,
                filters: Optional[List[str]] = None) -> Optional[str]:
        """Fetch log content for a specific daemon.

        daemon: one of the values in DAEMONS
        levels: list of file types — alarms, log, crash, audit. Ignored for
                etc-files and factory-files.
        filters: optional text filters to apply server-side
        Returns the raw log text body, or None on error.
        """
        if daemon not in self.DAEMONS:
            logger.warning("Unknown Auradine daemon %r", daemon)
            return None
        if not self._ensure_token():
            return None

        # etc-files and factory-files don't take a level array
        if daemon in ("etc-files", "factory-files"):
            level = []
        else:
            level = levels or list(self.LOG_LEVELS)

        body = {
            "command": "getLog",
            "daemon":  [daemon],
            "level":   level,
            "filters": filters or [],
        }
        try:
            # Auradine /log uses "Token" header (capital T), NOT Bearer
            resp = requests.post(
                f"{self.base_url}/log",
                headers={"Token": self._token, "Content-Type": "application/json"},
                json=body,
                verify=False,
                timeout=60,  # log fetch can be slow on a busy miner
            )
            resp.raise_for_status()
            # Response may be JSON-wrapped or raw text depending on the daemon
            # Try JSON first; fall back to raw text
            try:
                data = resp.json()
                # If the response is the standard envelope, extract the content
                if isinstance(data, dict):
                    if data.get("STATUS", [{}])[0].get("STATUS") == "E":
                        logger.warning("Auradine /log returned error: %s",
                                       data["STATUS"][0].get("Msg"))
                        return None
                    # Various response shapes — pick whichever holds content
                    for key in ("LOG", "Log", "log", "content", "data"):
                        if key in data:
                            v = data[key]
                            if isinstance(v, list):
                                return "\n".join(str(x) for x in v)
                            return str(v)
                    # Fall through to returning the whole dict as a string
                    return json.dumps(data, indent=2)
                return resp.text
            except ValueError:
                # Not JSON — return raw text
                return resp.text
        except Exception as e:
            logger.warning("Auradine /log fetch failed for %s/%s: %s", self.ip, daemon, e)
            return None

    def get_all_logs(self) -> Dict[str, str]:
        """Fetch logs for every daemon. Returns {daemon: content}.

        Used by the manual_log_upload script when invoked with --auto-fetch.
        Skips daemons that return errors. Each daemon's content is labeled
        with its daemon name so the parser knows what it's looking at.
        """
        out: Dict[str, str] = {}
        for daemon in self.DAEMONS:
            content = self.get_log(daemon)
            if content:
                out[f"{daemon}.log"] = content
                logger.info("Auradine %s: fetched %s, %d bytes",
                            self.ip, daemon, len(content))
        return out

    # ─────────────────────────────────────────────────────────────────
    # Tech support file (GET /techsupport with poll)
    # ─────────────────────────────────────────────────────────────────

    def request_techsupport(self) -> Optional[str]:
        """Kick off tech support file generation. Returns the job ID, or None."""
        if not self._ensure_token():
            return None
        try:
            resp = requests.get(
                f"{self.base_url}/techsupport",
                headers={"Token": self._token},
                verify=False,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            ts = data.get("TECHSUPPORT") or data.get("Techsupport") or []
            if ts and isinstance(ts, list):
                return ts[0].get("jobid") or ts[0].get("JobId")
            return None
        except Exception as e:
            logger.warning("Auradine techsupport request failed for %s: %s", self.ip, e)
            return None

    def techsupport_status(self, job_id: str) -> Optional[str]:
        """Poll tech support job status. Returns 'done' / 'in_progress' / None."""
        if not self._ensure_token():
            return None
        try:
            resp = requests.get(
                f"{self.base_url}/techsupport?command=status&jobid={job_id}",
                headers={"Token": self._token},
                verify=False,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            ts = data.get("TECHSUPPORT") or data.get("Techsupport") or []
            if ts and isinstance(ts, list):
                return ts[0].get("status")
            return None
        except Exception as e:
            logger.warning("Auradine techsupport status failed for %s: %s", self.ip, e)
            return None

    def fetch_techsupport(self, max_wait_seconds: int = 300) -> Optional[bytes]:
        """Generate and download a tech support file. Returns the raw bytes.

        Polls the job status until 'done' or timeout, then downloads the
        resulting file. The exact download URL is documented in Auradine's
        firmware notes — this method handles both common patterns.
        """
        job_id = self.request_techsupport()
        if not job_id:
            return None
        logger.info("Auradine %s: techsupport job %s started", self.ip, job_id)

        deadline = time.time() + max_wait_seconds
        while time.time() < deadline:
            status = self.techsupport_status(job_id)
            if status == "done":
                logger.info("Auradine %s: techsupport job %s ready", self.ip, job_id)
                break
            time.sleep(5)
        else:
            logger.warning("Auradine %s: techsupport job %s did not complete in %ss",
                           self.ip, job_id, max_wait_seconds)
            return None

        # Download — try the most common path patterns
        for path in (f"/techsupport?command=download&jobid={job_id}",
                     f"/techsupport/{job_id}",
                     f"/techsupport/download/{job_id}"):
            try:
                resp = requests.get(
                    f"{self.base_url}{path}",
                    headers={"Token": self._token},
                    verify=False,
                    timeout=120,
                    stream=True,
                )
                if resp.status_code == 200 and resp.content:
                    return resp.content
            except Exception as e:
                logger.debug("Auradine techsupport download path %s failed: %s", path, e)
        logger.warning("Auradine %s: could not find techsupport download URL", self.ip)
        return None

    # ─────────────────────────────────────────────────────────────────
    # Convenience health check
    # ─────────────────────────────────────────────────────────────────

    def health_snapshot(self) -> Dict[str, Any]:
        """Pull a comprehensive health snapshot for diagnostic purposes.

        Combines summary, devs, psu, temperature, mode into one dict.
        Used by the manual_log_upload script and ad-hoc /miner Slack queries
        to give the LLM a complete picture of the miner's state alongside
        the log content.
        """
        return {
            "ip":            self.ip,
            "summary":       self.summary(),
            "devs":          self.devs(),
            "devdetails":    self.devdetails(),
            "psu":           self.psu(),
            "temperature":   self.temperature(),
            "mode":          self.mode(),
            "version":       self.version(),
            "pools":         self.pools(),
            "fetched_at":    time.time(),
        }


# ─────────────────────────────────────────────────────────────────────────
# Auradine log parser — extracts DVFS alarms, power reductions, voltage
# clips, crashes from log content. Used by manual_log_upload to summarize
# Auradine logs into structured findings.
# ─────────────────────────────────────────────────────────────────────────

import re
from collections import defaultdict


# Auradine log line patterns
AUR_DVFS_VOLTAGE_RE = re.compile(
    r'(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?):\s*DVFS ALARM:\s*Voltage for chip\s+(?P<chip>\d+/\d+)\s+is\s+(?P<v>[\d.]+)V;\s*out of range\s+(?P<lo>[\d.]+)V\s*-\s*(?P<hi>[\d.]+)V'
)
AUR_DVFS_POWER_RE = re.compile(
    r'(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?):\s*DVFS ALARM:\s*power is\s+(?P<p>[\d.]+);\s*reducing hash rate'
)
AUR_POWERSTATE_RE = re.compile(
    r'(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?):\s*PowerState ALARM:\s*voltage\s+(?P<v>[\d.]+)\s+is above Vmax,\s*clipped to\s+(?P<clip>[\d.]+)'
)
AUR_CRASH_RE = re.compile(
    r'(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?):\s*(crash|panic|fatal|core dumped|segfault)',
    re.IGNORECASE
)


def parse_auradine_log_text(text: str) -> Dict[str, Any]:
    """Parse Auradine log text and return structured findings.

    Output keys:
      - dvfs_chip_voltage_events: per-chip voltage out-of-range events
      - dvfs_power_reductions:    DVFS power reduction events
      - powerstate_clips:         PowerState voltage clip events
      - crashes:                  crash/panic/fatal events
      - alarm_count:              total alarm lines seen
      - earliest_ts / latest_ts:  ISO time range
      - chips_seen:               {chain: set(chip)} of chips that fired alarms
      - dead_chips_summary:       {chain: list of chip ids reading near zero}
    """
    findings = {
        "dvfs_chip_voltage_events": [],
        "dvfs_power_reductions":    [],
        "powerstate_clips":         [],
        "crashes":                  [],
        "alarm_count":              0,
        "earliest_ts":              None,
        "latest_ts":                None,
        "chips_seen":               defaultdict(set),
        "dead_chips_summary":       defaultdict(list),
    }
    if not text:
        return findings

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        m = AUR_DVFS_VOLTAGE_RE.search(line)
        if m:
            findings["alarm_count"] += 1
            ts    = m.group("ts")
            chip  = m.group("chip")
            v     = float(m.group("v"))
            lo    = float(m.group("lo"))
            hi    = float(m.group("hi"))
            chain, chip_id = chip.split("/")
            findings["dvfs_chip_voltage_events"].append({
                "ts": ts, "chip": chip, "voltage": v,
                "expected_lo": lo, "expected_hi": hi,
            })
            findings["chips_seen"][chain].add(chip_id)
            if v < 0.05:  # essentially zero — chip is dead or disconnected
                if chip_id not in findings["dead_chips_summary"][chain]:
                    findings["dead_chips_summary"][chain].append(chip_id)
            _track_ts(findings, ts)
            continue

        m = AUR_DVFS_POWER_RE.search(line)
        if m:
            findings["alarm_count"] += 1
            findings["dvfs_power_reductions"].append({
                "ts": m.group("ts"),
                "power": float(m.group("p")),
            })
            _track_ts(findings, m.group("ts"))
            continue

        m = AUR_POWERSTATE_RE.search(line)
        if m:
            findings["alarm_count"] += 1
            findings["powerstate_clips"].append({
                "ts": m.group("ts"),
                "voltage": float(m.group("v")),
                "clipped_to": float(m.group("clip")),
            })
            _track_ts(findings, m.group("ts"))
            continue

        m = AUR_CRASH_RE.search(line)
        if m:
            findings["crashes"].append({
                "ts": m.group("ts"),
                "line": line[:200],
            })
            _track_ts(findings, m.group("ts"))

    # Convert sets/defaultdicts to plain dicts for JSON serialization
    findings["chips_seen"] = {
        k: sorted(v, key=lambda x: int(x))
        for k, v in findings["chips_seen"].items()
    }
    findings["dead_chips_summary"] = {
        k: sorted(v, key=lambda x: int(x))
        for k, v in findings["dead_chips_summary"].items()
    }

    return findings


def _track_ts(findings: Dict, ts: str) -> None:
    if not findings["earliest_ts"] or ts < findings["earliest_ts"]:
        findings["earliest_ts"] = ts
    if not findings["latest_ts"] or ts > findings["latest_ts"]:
        findings["latest_ts"] = ts


def render_auradine_findings(findings: Dict[str, Any]) -> str:
    """Render structured findings as a human-readable summary."""
    lines = []
    lines.append(f"Auradine log analysis ({findings['alarm_count']} total alarms)")
    if findings["earliest_ts"]:
        lines.append(f"  Time range: {findings['earliest_ts']} → {findings['latest_ts']}")
    lines.append("")

    if findings["dead_chips_summary"]:
        lines.append("⚠️ Chips reading near-zero voltage (likely dead or disconnected):")
        for chain, chips in sorted(findings["dead_chips_summary"].items()):
            short = ", ".join(chips[:15])
            more = f" ...+{len(chips) - 15} more" if len(chips) > 15 else ""
            lines.append(f"   board {chain}: {len(chips)} chips — {short}{more}")
    elif findings["dvfs_chip_voltage_events"]:
        lines.append(f"⚠️ DVFS voltage alarms fired: {len(findings['dvfs_chip_voltage_events'])} events")
        for chain, chips in sorted(findings["chips_seen"].items()):
            lines.append(f"   board {chain}: {len(chips)} unique chips affected")

    if findings["dvfs_power_reductions"]:
        powers = [e["power"] for e in findings["dvfs_power_reductions"]]
        lines.append(f"⚡ DVFS power reductions: {len(powers)} events, "
                     f"range {min(powers):.0f}W → {max(powers):.0f}W")

    if findings["powerstate_clips"]:
        lines.append(f"⚡ PowerState voltage clips: {len(findings['powerstate_clips'])} events "
                     f"(driver clipping voltage above Vmax)")

    if findings["crashes"]:
        lines.append(f"💥 Crashes/panics: {len(findings['crashes'])} events")
        for c in findings["crashes"][:3]:
            lines.append(f"   {c['ts']}: {c['line'][:150]}")

    if not (findings["dead_chips_summary"] or findings["dvfs_chip_voltage_events"] or
            findings["dvfs_power_reductions"] or findings["powerstate_clips"] or findings["crashes"]):
        lines.append("✅ No obvious hardware alarms found in the log content")

    return "\n".join(lines)
