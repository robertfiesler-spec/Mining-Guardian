"""MicroBT WhatsMiner parser — M-series log parsing.

Handles:
- WhatsMiner system logs (btminer format)
- Hashrate, temps, fan speeds, error codes, pool status
- eeprom version data
"""

import logging
import re
from datetime import datetime
from typing import Any

from models import DetectedMiner, ParsedData
from .base_parser import BaseParser

logger = logging.getLogger("importer.parsers.microbt")

# ─── WhatsMiner-specific regex patterns ───────────────────────────────────────

# Hashrate: various formats
RE_HASHRATE_TH = re.compile(
    r"(?:hashrate|hash\s*rate|MHS\s*\d+s)\s*[=:]\s*([\d.]+)\s*(TH|GH|MH|MHS)", re.I
)
RE_HASHRATE_SUMMARY = re.compile(
    r"(?:Summary|total)\s*.*?(?:MHS|hashrate)\s*[=:]\s*([\d.]+)", re.I
)
RE_HASHRATE_RT = re.compile(r"HS RT\s*[=:]\s*([\d.]+)", re.I)

# Temperature: "Temperature: 65" or "Temp: 65C"
RE_TEMP = re.compile(r"(?:Temperature|Temp)\s*[=:]\s*([\d.]+)\s*C?", re.I)
RE_TEMP_ENV = re.compile(r"(?:Env|Environment|Ambient)\s*[Tt]emp\s*[=:]\s*([\d.]+)", re.I)
RE_CHIP_TEMP = re.compile(r"(?:Chip|ASIC)\s*[Tt]emp\s*[=:]\s*([\d.]+)", re.I)

# Board temps (per-board)
RE_BOARD_TEMP = re.compile(
    r"(?:SM|board|hashboard)\s*(\d+)\s*temp\s*[=:]\s*([\d.]+)", re.I
)

# Fan speeds: "Fan Speed In: 4500" or "fan1: 5200"
RE_FAN_SPEED = re.compile(
    r"(?:Fan|fan)\s*(?:Speed\s*)?(?:In|Out|1|2|3|4)?\s*[=:]\s*(\d+)", re.I
)

# Power consumption
RE_POWER = re.compile(r"(?:Power|Watt|power_consumption)\s*[=:]\s*([\d.]+)\s*W?", re.I)

# Pool data
RE_POOL = re.compile(r"(?:Pool|pool)\s*\d*\s*URL?\s*[=:]\s*(\S+)", re.I)
RE_WORKER = re.compile(r"(?:Worker|User)\s*[=:]\s*(\S+)", re.I)
RE_ACCEPTED = re.compile(r"[Aa]ccepted\s*[=:]\s*(\d+)")
RE_REJECTED = re.compile(r"[Rr]ejected\s*[=:]\s*(\d+)")

# HW errors
RE_HW_ERRORS = re.compile(r"(?:HW|hardware)\s*(?:Errors?)\s*[=:]\s*(\d+)", re.I)

# Error codes — WhatsMiner has numeric error codes
RE_ERROR_CODE = re.compile(r"(?:Error|Err)\s*[Cc]ode\s*[=:]\s*(\d+)", re.I)

# Uptime / elapsed
RE_UPTIME = re.compile(r"(?:Elapsed|Uptime|Run\s*Time)\s*[=:]\s*(\d+)", re.I)

# Voltage
RE_VOLTAGE = re.compile(r"(?:Voltage|Vol)\s*[=:]\s*([\d.]+)\s*(?:mV|V)?", re.I)

# Frequency
RE_FREQUENCY = re.compile(r"(?:Freq|Frequency)\s*[=:]\s*([\d.]+)\s*(?:MHz|GHz)?", re.I)

# eeprom hardware/firmware version
RE_EEPROM_HW = re.compile(r"eeprom_hw_ver\s*[=:]\s*(\S+)", re.I)
RE_EEPROM_FW = re.compile(r"eeprom_fw_ver\s*[=:]\s*(\S+)", re.I)

# MAC/IP/Serial
RE_MAC = re.compile(r"[Mm][Aa][Cc]\s*[=:]\s*([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})")
RE_IP = re.compile(r"[Ii][Pp]\s*[=:]\s*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})")

# Timestamps
RE_TIMESTAMP = re.compile(r"(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2})")

# Error/warn lines
RE_ERROR_LINE = re.compile(r"\b(?:ERROR|error|Error)\b")
RE_WARN_LINE = re.compile(r"\b(?:WARN|warn|Warning|WARNING)\b")
RE_FATAL_LINE = re.compile(r"\b(?:FATAL|fatal|Fatal|CRITICAL|critical)\b")

# Reboot/restart
RE_REBOOT = re.compile(
    r"(?:reboot|restart|power.?cycle|btminer.*start|init.*start)", re.I
)

# Fan failure patterns
RE_FAN_FAIL = re.compile(r"fan\s*(?:\d+\s*)?(?:fail|error|stop|stuck|abnormal)", re.I)

# Temp sensor error
RE_TEMP_SENSOR_ERR = re.compile(r"temp(?:erature)?\s*sensor\s*(?:error|fail|abnormal)", re.I)


class MicroBTParser(BaseParser):
    """Parser for MicroBT WhatsMiner log files."""

    name = "microbt"

    def can_parse(self, content: str, detected: DetectedMiner) -> bool:
        if detected.brand == "microbt":
            return True
        header = content[:4096]
        indicators = [
            "whatsminer" in header.lower(),
            "btminer" in header.lower(),
            "microbt" in header.lower(),
            "eeprom_hw_ver" in header.lower(),
            bool(RE_HASHRATE_RT.search(header)),
        ]
        return sum(indicators) >= 2

    def parse(self, content: str, detected: DetectedMiner) -> ParsedData:
        data = ParsedData(parser_name=self.name)
        raw_fields: dict[str, Any] = {}

        # ── Hashrate ──────────────────────────────────────────────────────
        m = RE_HASHRATE_TH.search(content)
        if m:
            hr = float(m.group(1))
            unit = m.group(2).upper()
            if unit in ("GH", "GHS"):
                hr /= 1000.0
            elif unit in ("MH", "MHS"):
                hr /= 1000000.0
            data.hashrate_th = hr
        if not data.hashrate_th:
            m = RE_HASHRATE_RT.search(content)
            if m:
                # HS RT is usually in GH/s
                data.hashrate_th = float(m.group(1)) / 1000.0
        if not data.hashrate_th:
            m = RE_HASHRATE_SUMMARY.search(content)
            if m:
                data.hashrate_th = float(m.group(1)) / 1000.0

        # ── Temperatures ──────────────────────────────────────────────────
        for m in RE_CHIP_TEMP.finditer(content):
            data.chip_temps.append(float(m.group(1)))

        for m in RE_BOARD_TEMP.finditer(content):
            board_id = int(m.group(1))
            temp = float(m.group(2))
            data.board_temps.append(temp)
            data.boards.append({"board_id": board_id, "temp": temp})

        # General temps
        for m in RE_TEMP.finditer(content):
            t = float(m.group(1))
            if t > 0:
                data.chip_temps.append(t)

        m = RE_TEMP_ENV.search(content)
        if m:
            data.inlet_temp = float(m.group(1))
            raw_fields["env_temp"] = data.inlet_temp

        # ── Fan speeds ────────────────────────────────────────────────────
        for m in RE_FAN_SPEED.finditer(content):
            data.fan_speeds.append(int(m.group(1)))

        # ── Power ─────────────────────────────────────────────────────────
        m = RE_POWER.search(content)
        if m:
            data.power_w = float(m.group(1))

        # ── Pool data ─────────────────────────────────────────────────────
        m = RE_POOL.search(content)
        if m:
            data.pool_url = m.group(1)
        m = RE_WORKER.search(content)
        if m:
            data.pool_user = m.group(1)
        m = RE_ACCEPTED.search(content)
        if m:
            data.accepted_shares = int(m.group(1))
        m = RE_REJECTED.search(content)
        if m:
            data.rejected_shares = int(m.group(1))
        m = RE_HW_ERRORS.search(content)
        if m:
            data.hw_errors = int(m.group(1))

        # ── Uptime ────────────────────────────────────────────────────────
        m = RE_UPTIME.search(content)
        if m:
            data.uptime_seconds = int(m.group(1))

        # ── Voltage / Frequency ───────────────────────────────────────────
        for m in RE_VOLTAGE.finditer(content):
            data.voltages.append(float(m.group(1)))
        for m in RE_FREQUENCY.finditer(content):
            data.frequencies.append(float(m.group(1)))

        # ── eeprom versions ───────────────────────────────────────────────
        m = RE_EEPROM_HW.search(content)
        if m:
            raw_fields["eeprom_hw_ver"] = m.group(1)
        m = RE_EEPROM_FW.search(content)
        if m:
            raw_fields["eeprom_fw_ver"] = m.group(1)

        # ── Error codes ───────────────────────────────────────────────────
        error_codes = []
        for m in RE_ERROR_CODE.finditer(content):
            error_codes.append(int(m.group(1)))
        if error_codes:
            raw_fields["error_codes"] = error_codes

        # ── Fan failures ──────────────────────────────────────────────────
        fan_fails = len(RE_FAN_FAIL.findall(content))
        if fan_fails:
            raw_fields["fan_failures"] = fan_fails

        # Temp sensor errors
        temp_errs = len(RE_TEMP_SENSOR_ERR.findall(content))
        if temp_errs:
            raw_fields["temp_sensor_errors"] = temp_errs

        # ── Error/warn/fatal counting ─────────────────────────────────────
        data.error_count = len(RE_ERROR_LINE.findall(content))
        data.warn_count = len(RE_WARN_LINE.findall(content))
        data.fatal_count = len(RE_FATAL_LINE.findall(content))
        data.reboot_count = len(RE_REBOOT.findall(content))

        # ── Timestamps ────────────────────────────────────────────────────
        timestamps = RE_TIMESTAMP.findall(content)
        if timestamps:
            try:
                data.log_start = datetime.strptime(timestamps[0], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
            try:
                data.log_end = datetime.strptime(timestamps[-1], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass

        # ── Efficiency ────────────────────────────────────────────────────
        if data.hashrate_th and data.power_w and data.hashrate_th > 0:
            data.efficiency_j_th = round(data.power_w / data.hashrate_th, 2)

        # ── Raw key=value capture ─────────────────────────────────────────
        kv_pattern = re.compile(r"^([A-Za-z_][\w.]+)\s*[=:]\s*(.+)$", re.MULTILINE)
        for m in kv_pattern.finditer(content[:50000]):
            key = m.group(1).strip()
            val = m.group(2).strip()
            if key not in raw_fields:
                raw_fields[key] = val

        data.raw_fields = raw_fields
        data.data_points_count = self._count_data_points(data)
        return data
