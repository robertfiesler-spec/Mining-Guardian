"""Canaan Avalon parser — Avalon series log parsing.

Handles:
- Avalon system logs
- Hashrate, temps, voltage, nonce rates
- mm_version and module data
"""

import logging
import re
from datetime import datetime
from typing import Any

from models import DetectedMiner, ParsedData
from .base_parser import BaseParser

logger = logging.getLogger("importer.parsers.canaan")

# ─── Avalon-specific regex patterns ───────────────────────────────────────────

# Hashrate: "GHSmm: 12500.00" or "hashrate: 12.5 TH/s"
RE_HASHRATE_GHS = re.compile(r"GHSmm\s*[=:]\s*([\d.]+)", re.I)
RE_HASHRATE_TH = re.compile(
    r"(?:hashrate|hash\s*rate)\s*[=:]\s*([\d.]+)\s*(TH|GH|MH)", re.I
)
RE_HASHRATE_AVG = re.compile(r"GHSavg\s*[=:]\s*([\d.]+)", re.I)

# Temperature: Avalon uses "TMax", "TAvg", per-module temp
RE_TEMP_MAX = re.compile(r"TMax\s*[=:]\s*([\d.]+)", re.I)
RE_TEMP_AVG = re.compile(r"TAvg\s*[=:]\s*([\d.]+)", re.I)
RE_TEMP = re.compile(r"(?:Temperature|Temp)\s*[=:]\s*([\d.]+)", re.I)
RE_MODULE_TEMP = re.compile(
    r"(?:module|MM)\s*(\d+)\s*temp\s*[=:]\s*([\d.]+)", re.I
)

# Voltage: "Voltage: 830 mV" or per-module
RE_VOLTAGE = re.compile(r"(?:Voltage|Vol)\s*[=:]\s*([\d.]+)\s*(?:mV|V)?", re.I)
RE_MODULE_VOLTAGE = re.compile(
    r"(?:module|MM)\s*(\d+)\s*vol(?:tage)?\s*[=:]\s*([\d.]+)", re.I
)

# Frequency
RE_FREQUENCY = re.compile(r"(?:Freq|Frequency)\s*[=:]\s*([\d.]+)\s*(?:MHz)?", re.I)

# Nonce rate
RE_NONCE_RATE = re.compile(r"(?:nonce|Nonce)\s*(?:rate|Rate)\s*[=:]\s*([\d.]+)", re.I)
RE_NONCE_ERR = re.compile(r"(?:nonce|Nonce)\s*(?:err|error)\s*[=:]\s*(\d+)", re.I)

# Fan speeds
RE_FAN = re.compile(r"(?:Fan|fan)\s*(?:Speed\s*)?(?:\d+\s*)?[=:]\s*(\d+)", re.I)

# Power
RE_POWER = re.compile(r"(?:Power|Watt|power)\s*[=:]\s*([\d.]+)\s*W?", re.I)

# Pool
RE_POOL = re.compile(r"(?:Pool|pool)\s*\d*\s*(?:URL\s*)?[=:]\s*(\S+)", re.I)
RE_ACCEPTED = re.compile(r"[Aa]ccepted\s*[=:]\s*(\d+)")
RE_REJECTED = re.compile(r"[Rr]ejected\s*[=:]\s*(\d+)")
RE_HW_ERRORS = re.compile(r"(?:HW|hardware)\s*(?:Errors?)\s*[=:]\s*(\d+)", re.I)

# Uptime
RE_UPTIME = re.compile(r"(?:Elapsed|Uptime)\s*[=:]\s*(\d+)", re.I)

# mm_version (Avalon module manager version)
RE_MM_VERSION = re.compile(r"mm_version\s*[=:]\s*(\S+)", re.I)
RE_MM_DNA = re.compile(r"(?:DNA|dna)\s*[=:]\s*(\S+)", re.I)

# Module count: "Modules: 4"
RE_MODULE_COUNT = re.compile(r"(?:Modules?|MM)\s*(?:count\s*)?[=:]\s*(\d+)", re.I)

# ASIC count per module
RE_ASIC_PER_MODULE = re.compile(
    r"(?:module|MM)\s*(\d+)\s*(?:ASIC|chip)\s*(?:count\s*)?[=:]\s*(\d+)", re.I
)

# Timestamps
RE_TIMESTAMP = re.compile(r"(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2})")

# Error/warn/fatal
RE_ERROR = re.compile(r"\b(?:ERROR|error|Error)\b")
RE_WARN = re.compile(r"\b(?:WARN|warn|Warning|WARNING)\b")
RE_FATAL = re.compile(r"\b(?:FATAL|fatal|Fatal|CRITICAL|critical)\b")
RE_REBOOT = re.compile(r"(?:reboot|restart|power.?cycle|init.*start)", re.I)

# Voltage regulator issues
RE_VREG_ERR = re.compile(
    r"(?:voltage\s*regulator|vreg|VR)\s*(?:error|fail|fault|abnormal)", re.I
)


class CanaanParser(BaseParser):
    """Parser for Canaan Avalon log files."""

    name = "canaan"

    def can_parse(self, content: str, detected: DetectedMiner) -> bool:
        if detected.brand == "canaan":
            return True
        header = content[:4096]
        indicators = [
            "avalon" in header.lower(),
            "canaan" in header.lower(),
            "avalonminer" in header.lower(),
            "GHSmm" in header,
            "mm_version" in header.lower(),
            "MM DNA" in header or "mm_dna" in header.lower(),
        ]
        return sum(indicators) >= 2

    def parse(self, content: str, detected: DetectedMiner) -> ParsedData:
        data = ParsedData(parser_name=self.name)
        raw_fields: dict[str, Any] = {}
        boards: dict[int, dict[str, Any]] = {}

        # ── Hashrate ──────────────────────────────────────────────────────
        m = RE_HASHRATE_TH.search(content)
        if m:
            hr = float(m.group(1))
            unit = m.group(2).upper()
            if unit == "GH":
                hr /= 1000.0
            elif unit == "MH":
                hr /= 1000000.0
            data.hashrate_th = hr

        if not data.hashrate_th:
            m = RE_HASHRATE_GHS.search(content)
            if m:
                data.hashrate_th = float(m.group(1)) / 1000.0

        m = RE_HASHRATE_AVG.search(content)
        if m:
            raw_fields["ghs_avg"] = float(m.group(1))
            if not data.hashrate_th:
                data.hashrate_th = float(m.group(1)) / 1000.0

        # ── Temperatures ──────────────────────────────────────────────────
        m = RE_TEMP_MAX.search(content)
        if m:
            data.chip_temps.append(float(m.group(1)))
            raw_fields["tmax"] = float(m.group(1))

        m = RE_TEMP_AVG.search(content)
        if m:
            raw_fields["tavg"] = float(m.group(1))

        for m in RE_TEMP.finditer(content):
            t = float(m.group(1))
            if t > 0:
                data.chip_temps.append(t)

        for m in RE_MODULE_TEMP.finditer(content):
            mod_id = int(m.group(1))
            temp = float(m.group(2))
            boards.setdefault(mod_id, {})["temp"] = temp
            data.board_temps.append(temp)

        # ── Voltage ───────────────────────────────────────────────────────
        for m in RE_VOLTAGE.finditer(content):
            data.voltages.append(float(m.group(1)))

        for m in RE_MODULE_VOLTAGE.finditer(content):
            mod_id = int(m.group(1))
            v = float(m.group(2))
            boards.setdefault(mod_id, {})["voltage"] = v

        # ── Frequency ─────────────────────────────────────────────────────
        for m in RE_FREQUENCY.finditer(content):
            data.frequencies.append(float(m.group(1)))

        # ── Nonce rate ────────────────────────────────────────────────────
        nonce_rates = []
        for m in RE_NONCE_RATE.finditer(content):
            nonce_rates.append(float(m.group(1)))
        if nonce_rates:
            raw_fields["nonce_rate"] = nonce_rates[-1]
            raw_fields["nonce_rate_min"] = min(nonce_rates)
            raw_fields["nonce_rate_avg"] = sum(nonce_rates) / len(nonce_rates)

        nonce_errs = []
        for m in RE_NONCE_ERR.finditer(content):
            nonce_errs.append(int(m.group(1)))
        if nonce_errs:
            raw_fields["nonce_errors"] = sum(nonce_errs)

        # ── Fan speeds ────────────────────────────────────────────────────
        for m in RE_FAN.finditer(content):
            data.fan_speeds.append(int(m.group(1)))

        # ── Power ─────────────────────────────────────────────────────────
        m = RE_POWER.search(content)
        if m:
            data.power_w = float(m.group(1))

        # ── Pool data ─────────────────────────────────────────────────────
        m = RE_POOL.search(content)
        if m:
            data.pool_url = m.group(1)
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

        # ── mm_version / DNA ──────────────────────────────────────────────
        m = RE_MM_VERSION.search(content)
        if m:
            raw_fields["mm_version"] = m.group(1)
        m = RE_MM_DNA.search(content)
        if m:
            raw_fields["mm_dna"] = m.group(1)

        # ── Module/ASIC count ─────────────────────────────────────────────
        m = RE_MODULE_COUNT.search(content)
        if m:
            raw_fields["module_count"] = int(m.group(1))

        total_asics = 0
        for m in RE_ASIC_PER_MODULE.finditer(content):
            mod_id = int(m.group(1))
            asic_count = int(m.group(2))
            boards.setdefault(mod_id, {})["asic_count"] = asic_count
            total_asics += asic_count
        if total_asics > 0:
            data.total_chips = total_asics

        # ── Voltage regulator errors ──────────────────────────────────────
        vreg_errors = len(RE_VREG_ERR.findall(content))
        if vreg_errors:
            raw_fields["vreg_errors"] = vreg_errors

        # ── Convert boards dict ───────────────────────────────────────────
        for bid in sorted(boards.keys()):
            board_data = {"board_id": bid}
            board_data.update(boards[bid])
            data.boards.append(board_data)

        # ── Error/warn/fatal counting ─────────────────────────────────────
        data.error_count = len(RE_ERROR.findall(content))
        data.warn_count = len(RE_WARN.findall(content))
        data.fatal_count = len(RE_FATAL.findall(content))
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
