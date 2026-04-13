"""Bitmain Antminer parser — S-series, T-series log parsing.

Handles:
- cglog_init_* files (BiXBiT firmware format)
- miner.log format (stock cgminer/bmminer)
- Chain[N] data extraction
- BiXBiT autotune data
"""

import logging
import re
from datetime import datetime
from typing import Any

from models import DetectedMiner, ParsedData
from .base_parser import BaseParser

logger = logging.getLogger("importer.parsers.bitmain")

# ─── Regex patterns for Bitmain log parsing ───────────────────────────────────

# Chain data: "Chain[0] hashrate: 35.12 TH/s"
RE_CHAIN_HASHRATE = re.compile(
    r"Chain\[(\d+)\]\s*(?:real\s+)?hashrate\s*[=:]\s*([\d.]+)\s*(?:TH|GH|MH)", re.I
)
RE_CHAIN_TEMP_CHIP = re.compile(
    r"Chain\[(\d+)\]\s*(?:chip\s+)?temp\s*[=:]\s*([\d.]+)", re.I
)
RE_CHAIN_TEMP_PCB = re.compile(
    r"Chain\[(\d+)\]\s*pcb\s*temp\s*[=:]\s*([\d.]+)", re.I
)
RE_CHAIN_VOLTAGE = re.compile(
    r"Chain\[(\d+)\]\s*(?:vol|voltage)\s*[=:]\s*([\d.]+)", re.I
)
RE_CHAIN_FREQ = re.compile(
    r"Chain\[(\d+)\]\s*(?:freq|frequency)\s*[=:]\s*([\d.]+)", re.I
)
RE_CHAIN_HW = re.compile(
    r"Chain\[(\d+)\]\s*(?:hw|HW)\s*[=:]\s*(\d+)", re.I
)
RE_CHAIN_ACN = re.compile(
    r"Chain\[(\d+)\]\s*(?:acn|ASIC)\s*[=:]\s*(\d+)", re.I
)

# Summary hashrate: "total hashrate = 110.5 TH/s"
RE_TOTAL_HASHRATE = re.compile(
    r"(?:total|summary|avg)\s*hashrate\s*[=:]\s*([\d.]+)\s*(TH|GH|MH)", re.I
)

# 5s/1m/15m hashrate: "GHS 5s: 110500.12"
RE_GHS_5S = re.compile(r"GHS\s*5s\s*[=:]\s*([\d.]+)", re.I)
RE_GHS_AVG = re.compile(r"GHS\s*av\s*[=:]\s*([\d.]+)", re.I)

# Power: "power = 3250 W"
RE_POWER = re.compile(r"(?:power|watt)\s*[=:]\s*([\d.]+)\s*W?", re.I)

# PSU voltage: "PSU voltage: 12.1V"
RE_PSU_VOLTAGE = re.compile(r"PSU\s*(?:vol|voltage)\s*[=:]\s*([\d.]+)", re.I)

# Fan speeds: "fan1: 4200" or "Fan Speed In: 4200"
RE_FAN = re.compile(r"fan\s*(?:speed\s*)?(?:in|out)?\s*\d*\s*[=:]\s*(\d+)", re.I)

# Pool info
RE_POOL_URL = re.compile(r"(?:pool|stratum)\s*(?:url|1|2|3)\s*[=:]\s*(\S+)", re.I)
RE_POOL_USER = re.compile(r"(?:pool|worker)\s*user\s*[=:]\s*(\S+)", re.I)

# Accepted/rejected
RE_ACCEPTED = re.compile(r"[Aa]ccepted\s*[=:]\s*(\d+)")
RE_REJECTED = re.compile(r"[Rr]ejected\s*[=:]\s*(\d+)")
RE_HW_ERRORS = re.compile(r"(?:HW|hardware)\s*(?:errors?)\s*[=:]\s*(\d+)", re.I)

# Uptime: "Elapsed: 345600" (seconds)
RE_ELAPSED = re.compile(r"[Ee]lapsed\s*[=:]\s*(\d+)")

# ASIC status: "chain_acn1=126"
RE_ASIC_COUNT = re.compile(r"chain_acn\d+\s*[=:]\s*(\d+)", re.I)

# Dead ASIC: look for "x" in ASIC status strings like "oooooooxooooo"
RE_ASIC_STATUS = re.compile(r"chain_acs\d+\s*[=:]\s*([ox ]+)", re.I)

# BiXBiT autotune
RE_AUTOTUNE = re.compile(r"autotune\s*[=:]\s*(\S+)", re.I)
RE_AUTOTUNE_PROFILE = re.compile(r"profile\s*[=:]\s*(\S+)", re.I)

# Timestamps in logs
RE_TIMESTAMP = re.compile(
    r"(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2})"
)

# Error/warn/fatal counting
RE_ERROR = re.compile(r"\b(?:ERROR|error|Error)\b")
RE_WARN = re.compile(r"\b(?:WARN|warn|Warning|WARNING)\b")
RE_FATAL = re.compile(r"\b(?:FATAL|fatal|Fatal|CRITICAL|critical)\b")

# Reboot/restart detection
RE_REBOOT = re.compile(
    r"(?:reboot|restart|power.?cycle|init.*start|cgminer.*start|bmminer.*start)", re.I
)


class BitmainParser(BaseParser):
    """Parser for Bitmain Antminer log files."""

    name = "bitmain"

    def can_parse(self, content: str, detected: DetectedMiner) -> bool:
        if detected.brand == "bitmain":
            return True
        # Content-based detection
        header = content[:4096]
        indicators = [
            "Chain[" in header,
            "cgminer" in header.lower(),
            "bmminer" in header.lower(),
            "Antminer" in header,
            "bitmain" in header.lower(),
            "cglog" in header.lower(),
            "chain_acn" in header.lower(),
        ]
        return sum(indicators) >= 2

    def parse(self, content: str, detected: DetectedMiner) -> ParsedData:
        data = ParsedData(parser_name=self.name)
        raw_fields: dict[str, Any] = {}
        chains: dict[int, dict[str, Any]] = {}

        # ── Chain-level data ──────────────────────────────────────────────
        for m in RE_CHAIN_HASHRATE.finditer(content):
            cid = int(m.group(1))
            chains.setdefault(cid, {})["hashrate"] = float(m.group(2))

        for m in RE_CHAIN_TEMP_CHIP.finditer(content):
            cid = int(m.group(1))
            temp = float(m.group(2))
            chains.setdefault(cid, {})["chip_temp"] = temp
            data.chip_temps.append(temp)

        for m in RE_CHAIN_TEMP_PCB.finditer(content):
            cid = int(m.group(1))
            temp = float(m.group(2))
            chains.setdefault(cid, {})["pcb_temp"] = temp
            data.board_temps.append(temp)

        for m in RE_CHAIN_VOLTAGE.finditer(content):
            cid = int(m.group(1))
            v = float(m.group(2))
            chains.setdefault(cid, {})["voltage"] = v
            data.voltages.append(v)

        for m in RE_CHAIN_FREQ.finditer(content):
            cid = int(m.group(1))
            f = float(m.group(2))
            chains.setdefault(cid, {})["frequency"] = f
            data.frequencies.append(f)

        for m in RE_CHAIN_HW.finditer(content):
            cid = int(m.group(1))
            chains.setdefault(cid, {})["hw_errors"] = int(m.group(2))

        for m in RE_CHAIN_ACN.finditer(content):
            cid = int(m.group(1))
            chains.setdefault(cid, {})["asic_count"] = int(m.group(2))

        # Convert chains dict to list
        for cid in sorted(chains.keys()):
            chain_data = {"chain_id": cid}
            chain_data.update(chains[cid])
            data.chains.append(chain_data)

        # ── Summary hashrate ──────────────────────────────────────────────
        m = RE_TOTAL_HASHRATE.search(content)
        if m:
            hr = float(m.group(1))
            unit = m.group(2).upper()
            if unit == "GH":
                hr /= 1000.0
            elif unit == "MH":
                hr /= 1000000.0
            data.hashrate_th = hr
        elif not data.hashrate_th:
            # Try GHS 5s
            m = RE_GHS_5S.search(content)
            if m:
                data.hashrate_th = float(m.group(1)) / 1000.0
                raw_fields["ghs_5s"] = float(m.group(1))

        m = RE_GHS_AVG.search(content)
        if m:
            raw_fields["ghs_avg"] = float(m.group(1))
            if not data.hashrate_th:
                data.hashrate_th = float(m.group(1)) / 1000.0

        # Sum chain hashrates if no total found
        if not data.hashrate_th and chains:
            chain_hrs = [c.get("hashrate", 0) for c in chains.values()]
            if any(chain_hrs):
                data.hashrate_th = sum(chain_hrs)

        # ── Power ─────────────────────────────────────────────────────────
        m = RE_POWER.search(content)
        if m:
            data.power_w = float(m.group(1))

        # ── PSU voltage ───────────────────────────────────────────────────
        m = RE_PSU_VOLTAGE.search(content)
        if m:
            data.psu_voltage = float(m.group(1))
            raw_fields["psu_voltage"] = data.psu_voltage

        # ── Fan speeds ────────────────────────────────────────────────────
        for m in RE_FAN.finditer(content):
            data.fan_speeds.append(int(m.group(1)))

        # ── Pool data ─────────────────────────────────────────────────────
        m = RE_POOL_URL.search(content)
        if m:
            data.pool_url = m.group(1)

        m = RE_POOL_USER.search(content)
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
        m = RE_ELAPSED.search(content)
        if m:
            data.uptime_seconds = int(m.group(1))

        # ── ASIC chip counting ────────────────────────────────────────────
        total_asics = 0
        for m in RE_ASIC_COUNT.finditer(content):
            total_asics += int(m.group(1))
        if total_asics > 0:
            data.total_chips = total_asics

        # Dead chip detection from ASIC status strings
        dead = 0
        total_from_status = 0
        for m in RE_ASIC_STATUS.finditer(content):
            status = m.group(1).replace(" ", "")
            total_from_status += len(status)
            dead += status.count("x")
        if dead > 0:
            data.dead_chips = dead
        if total_from_status > 0 and data.total_chips is None:
            data.total_chips = total_from_status

        # ── Error/warn/fatal counting ─────────────────────────────────────
        data.error_count = len(RE_ERROR.findall(content))
        data.warn_count = len(RE_WARN.findall(content))
        data.fatal_count = len(RE_FATAL.findall(content))
        data.reboot_count = len(RE_REBOOT.findall(content))

        # ── BiXBiT autotune ───────────────────────────────────────────────
        m = RE_AUTOTUNE.search(content)
        if m:
            raw_fields["autotune"] = m.group(1)

        m = RE_AUTOTUNE_PROFILE.search(content)
        if m:
            raw_fields["autotune_profile"] = m.group(1)

        # ── Timestamps ────────────────────────────────────────────────────
        timestamps = RE_TIMESTAMP.findall(content)
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

        # ── Efficiency ────────────────────────────────────────────────────
        if data.hashrate_th and data.power_w and data.hashrate_th > 0:
            data.efficiency_j_th = round(data.power_w / data.hashrate_th, 2)

        # ── Collect raw fields ────────────────────────────────────────────
        # Capture anything that looks like key=value or key: value not already parsed
        kv_pattern = re.compile(r"^([A-Za-z_][\w.]+)\s*[=:]\s*(.+)$", re.MULTILINE)
        for m in kv_pattern.finditer(content[:50000]):  # limit scan for performance
            key = m.group(1).strip()
            val = m.group(2).strip()
            if key not in raw_fields:
                raw_fields[key] = val

        data.raw_fields = raw_fields
        data.data_points_count = self._count_data_points(data)
        return data
