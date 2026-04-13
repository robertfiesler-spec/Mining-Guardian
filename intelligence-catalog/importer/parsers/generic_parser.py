"""Generic fallback parser — extracts what it can from unrecognized formats.

This parser always accepts any file and does its best to extract:
- Timestamps
- IP addresses
- Temperature values
- Error/warning keywords
- Key-value pairs
- Numeric patterns

Everything is flagged as needs_review.
"""

import logging
import re
from datetime import datetime
from typing import Any

from models import DetectedMiner, ParsedData
from .base_parser import BaseParser

logger = logging.getLogger("importer.parsers.generic")

# ─── Generic extraction patterns ──────────────────────────────────────────────

RE_TIMESTAMP = re.compile(r"(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2})")
RE_IP_ADDR = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")
RE_MAC_ADDR = re.compile(r"\b([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})\b")

# Temperature-like values: "75°C", "temp: 65", "temperature = 80.5"
RE_TEMP_VALUE = re.compile(
    r"(?:temp(?:erature)?)\s*[=:]\s*([\d.]+)\s*°?[CcFf]?", re.I
)
RE_TEMP_CELSIUS = re.compile(r"([\d.]+)\s*°C", re.I)

# Hashrate-like values
RE_HASHRATE = re.compile(
    r"(?:hashrate|hash\s*rate|MHS|GHS|THS)\s*[=:]\s*([\d.]+)", re.I
)

# Key-value pairs: "key = value" or "key: value"
RE_KV = re.compile(r"^([A-Za-z_][\w.]{1,50})\s*[=:]\s*(.{1,200})$", re.MULTILINE)

# Error/warning keywords
RE_ERROR = re.compile(r"\b(?:ERROR|error|Error)\b")
RE_WARN = re.compile(r"\b(?:WARN|warn|Warning|WARNING)\b")
RE_FATAL = re.compile(r"\b(?:FATAL|fatal|Fatal|CRITICAL|critical)\b")
RE_REBOOT = re.compile(r"(?:reboot|restart|power.?cycle)", re.I)

# Voltage-like values
RE_VOLTAGE = re.compile(r"(?:volt(?:age)?)\s*[=:]\s*([\d.]+)\s*(?:mV|V)?", re.I)

# Frequency-like values
RE_FREQUENCY = re.compile(r"(?:freq(?:uency)?)\s*[=:]\s*([\d.]+)\s*(?:MHz|GHz)?", re.I)

# Fan-like values
RE_FAN = re.compile(r"(?:fan)\s*(?:speed\s*)?(?:\d+\s*)?[=:]\s*(\d+)", re.I)

# Power-like values
RE_POWER = re.compile(r"(?:power|watt)\s*[=:]\s*([\d.]+)\s*W?", re.I)


class GenericParser(BaseParser):
    """Fallback parser for unrecognized file formats."""

    name = "generic"

    def can_parse(self, content: str, detected: DetectedMiner) -> bool:
        # Generic parser always accepts — it's the fallback
        return True

    def parse(self, content: str, detected: DetectedMiner) -> ParsedData:
        data = ParsedData(parser_name=self.name)
        raw_fields: dict[str, Any] = {}

        # Limit content scan for performance
        scan_content = content[:100000]

        # ── Timestamps ────────────────────────────────────────────────────
        timestamps = RE_TIMESTAMP.findall(scan_content)
        if timestamps:
            try:
                data.log_start = datetime.strptime(timestamps[0], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    data.log_start = datetime.strptime(timestamps[0], "%Y/%m/%d %H:%M:%S")
                except ValueError:
                    pass
            try:
                data.log_end = datetime.strptime(timestamps[-1], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    data.log_end = datetime.strptime(timestamps[-1], "%Y/%m/%d %H:%M:%S")
                except ValueError:
                    pass
            raw_fields["timestamp_count"] = len(timestamps)

        # ── IP addresses ──────────────────────────────────────────────────
        ips = list(set(RE_IP_ADDR.findall(scan_content[:10000])))
        if ips:
            raw_fields["ip_addresses"] = ips[:20]  # cap at 20

        # ── MAC addresses ─────────────────────────────────────────────────
        macs = list(set(RE_MAC_ADDR.findall(scan_content[:10000])))
        if macs:
            raw_fields["mac_addresses"] = macs[:20]

        # ── Temperature values ────────────────────────────────────────────
        for m in RE_TEMP_VALUE.finditer(scan_content):
            t = float(m.group(1))
            if 0 < t < 200:  # sanity check
                data.chip_temps.append(t)

        for m in RE_TEMP_CELSIUS.finditer(scan_content):
            t = float(m.group(1))
            if 0 < t < 200:
                data.chip_temps.append(t)

        # Deduplicate temps
        data.chip_temps = sorted(set(data.chip_temps))

        # ── Hashrate ──────────────────────────────────────────────────────
        for m in RE_HASHRATE.finditer(scan_content):
            val = float(m.group(1))
            if val > 0:
                data.hashrate_th = val  # take last match
                raw_fields["hashrate_raw"] = val

        # ── Voltage ───────────────────────────────────────────────────────
        for m in RE_VOLTAGE.finditer(scan_content):
            data.voltages.append(float(m.group(1)))

        # ── Frequency ─────────────────────────────────────────────────────
        for m in RE_FREQUENCY.finditer(scan_content):
            data.frequencies.append(float(m.group(1)))

        # ── Fan speeds ────────────────────────────────────────────────────
        for m in RE_FAN.finditer(scan_content):
            data.fan_speeds.append(int(m.group(1)))

        # ── Power ─────────────────────────────────────────────────────────
        m = RE_POWER.search(scan_content)
        if m:
            data.power_w = float(m.group(1))

        # ── Error/warn/fatal counting ─────────────────────────────────────
        data.error_count = len(RE_ERROR.findall(scan_content))
        data.warn_count = len(RE_WARN.findall(scan_content))
        data.fatal_count = len(RE_FATAL.findall(scan_content))
        data.reboot_count = len(RE_REBOOT.findall(scan_content))

        # ── Key-value pairs ───────────────────────────────────────────────
        kv_count = 0
        for m in RE_KV.finditer(scan_content[:50000]):
            key = m.group(1).strip()
            val = m.group(2).strip()
            if key not in raw_fields:
                raw_fields[key] = val
                kv_count += 1
            if kv_count >= 200:  # cap to avoid bloat
                break

        # ── Content stats ─────────────────────────────────────────────────
        raw_fields["line_count"] = content.count("\n") + 1
        raw_fields["char_count"] = len(content)
        raw_fields["parser_note"] = "Generic fallback — manual review recommended"

        data.raw_fields = raw_fields
        data.data_points_count = self._count_data_points(data)
        return data
