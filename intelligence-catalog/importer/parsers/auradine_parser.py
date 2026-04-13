"""Auradine Teraflux parser — DVFS, PowerState, FluxOS log parsing.

Handles:
- DVFS voltage/frequency logs
- PowerState logs and power reduction events
- FluxOS system logs (gcminer, monitord)
- Per-chip voltage (avg_volt N: format)
- PSU IOUT, hitrate, inlet/outlet temps
"""

import logging
import re
from datetime import datetime
from typing import Any

from models import DetectedMiner, ParsedData
from .base_parser import BaseParser

logger = logging.getLogger("importer.parsers.auradine")

# ─── Auradine/FluxOS-specific regex patterns ─────────────────────────────────

# Per-chip data: "chip 0/128 volt=350 freq=500"
RE_CHIP_DATA = re.compile(
    r"chip\s+(\d+)/(\d+)\s+(?:.*?)volt\s*[=:]\s*(\d+)(?:.*?)freq\s*[=:]\s*(\d+)", re.I
)

# avg_volt format: "avg_volt 0: 345 1: 350 2: 348"
RE_AVG_VOLT = re.compile(r"avg_volt\s+(\d+)\s*:\s*(\d+)", re.I)

# Board-level avg voltage: "Board 0 avg_volt: 345"
RE_BOARD_AVG_VOLT = re.compile(
    r"(?:Board|board)\s*(\d+)\s*avg_volt\s*[=:]\s*(\d+)", re.I
)

# DVFS voltage/frequency adjustment
RE_DVFS_ADJUST = re.compile(
    r"DVFS\s*.*?(?:volt|voltage)\s*[=:]\s*(\d+).*?(?:freq|frequency)\s*[=:]\s*(\d+)", re.I
)

# PowerState events
RE_POWER_STATE = re.compile(
    r"PowerState\s*[=:]\s*(\S+)", re.I
)
RE_POWER_REDUCTION = re.compile(
    r"(?:power\s*reduction|power\s*limit|throttle|clip)", re.I
)
RE_POWER_STATE_CLIP = re.compile(
    r"PowerState.*(?:clip|limit|reduce|throttle)", re.I
)

# Hashrate
RE_HASHRATE = re.compile(
    r"(?:hashrate|hash\s*rate)\s*[=:]\s*([\d.]+)\s*(TH|GH|MH)", re.I
)
RE_GH_TOTAL = re.compile(r"(?:total|avg)\s*(?:hashrate|hash)\s*[=:]\s*([\d.]+)", re.I)

# Hitrate (Auradine-specific quality metric)
RE_HITRATE = re.compile(r"hitrate\s*[=:]\s*([\d.]+)", re.I)

# PSU IOUT (current output)
RE_PSU_IOUT = re.compile(r"(?:PSU\s*)?IOUT\s*[=:]\s*([\d.]+)", re.I)
RE_PSU_VOUT = re.compile(r"(?:PSU\s*)?VOUT\s*[=:]\s*([\d.]+)", re.I)

# Temperature: inlet, outlet, chip
RE_INLET_TEMP = re.compile(r"(?:inlet|input)\s*temp\s*[=:]\s*([\d.]+)", re.I)
RE_OUTLET_TEMP = re.compile(r"(?:outlet|output|exhaust)\s*temp\s*[=:]\s*([\d.]+)", re.I)
RE_CHIP_TEMP = re.compile(r"(?:chip|die|junction)\s*temp\s*[=:]\s*([\d.]+)", re.I)
RE_BOARD_TEMP = re.compile(r"(?:board|pcb)\s*(\d+)?\s*temp\s*[=:]\s*([\d.]+)", re.I)

# Fan speeds
RE_FAN = re.compile(r"fan\s*(?:speed\s*)?(?:\d+\s*)?[=:]\s*(\d+)", re.I)

# Power consumption
RE_POWER_W = re.compile(r"(?:power|watt)\s*[=:]\s*([\d.]+)\s*W?", re.I)

# Pool data
RE_POOL = re.compile(r"(?:pool|stratum)\s*(?:url\s*)?[=:]\s*(\S+)", re.I)
RE_ACCEPTED = re.compile(r"[Aa]ccepted\s*[=:]\s*(\d+)")
RE_REJECTED = re.compile(r"[Rr]ejected\s*[=:]\s*(\d+)")

# Uptime
RE_UPTIME = re.compile(r"(?:Elapsed|Uptime)\s*[=:]\s*(\d+)", re.I)

# Dead board detection: avg_volt = 0
RE_DEAD_BOARD = re.compile(r"avg_volt\s+\d+\s*:\s*0(?:\s|$)", re.I)

# Timestamps
RE_TIMESTAMP = re.compile(r"(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2})")

# Error/warn/fatal
RE_ERROR = re.compile(r"\b(?:ERROR|error|Error)\b")
RE_WARN = re.compile(r"\b(?:WARN|warn|Warning|WARNING)\b")
RE_FATAL = re.compile(r"\b(?:FATAL|fatal|Fatal|CRITICAL|critical)\b")
RE_REBOOT = re.compile(
    r"(?:reboot|restart|power.?cycle|gcminer.*start|init.*start)", re.I
)


class AuradineParser(BaseParser):
    """Parser for Auradine Teraflux / FluxOS log files."""

    name = "auradine"

    def can_parse(self, content: str, detected: DetectedMiner) -> bool:
        if detected.brand == "auradine":
            return True
        header = content[:4096]
        indicators = [
            "fluxos" in header.lower(),
            "auradine" in header.lower(),
            "teraflux" in header.lower(),
            "gcminer" in header.lower(),
            "avg_volt" in header.lower(),
            "DVFS" in header,
            "PowerState" in header,
            "monitord" in header.lower(),
            bool(RE_CHIP_DATA.search(header)),
        ]
        return sum(indicators) >= 2

    def parse(self, content: str, detected: DetectedMiner) -> ParsedData:
        data = ParsedData(parser_name=self.name)
        raw_fields: dict[str, Any] = {}
        boards: dict[int, dict[str, Any]] = {}

        # ── Per-chip voltage/frequency data ───────────────────────────────
        chip_volts = []
        chip_freqs = []
        total_chips = 0
        dead_chips = 0

        for m in RE_CHIP_DATA.finditer(content):
            chip_id = int(m.group(1))
            chip_total = int(m.group(2))
            volt = int(m.group(3))
            freq = int(m.group(4))
            total_chips = max(total_chips, chip_total)
            chip_volts.append(volt)
            chip_freqs.append(freq)
            data.voltages.append(float(volt))
            data.frequencies.append(float(freq))
            if volt == 0:
                dead_chips += 1

        if total_chips > 0:
            data.total_chips = total_chips
        data.dead_chips = dead_chips

        # ── avg_volt per board ────────────────────────────────────────────
        for m in RE_AVG_VOLT.finditer(content):
            board_id = int(m.group(1))
            avg_v = int(m.group(2))
            boards.setdefault(board_id, {})["avg_volt"] = avg_v
            if avg_v == 0:
                boards[board_id]["dead"] = True

        for m in RE_BOARD_AVG_VOLT.finditer(content):
            board_id = int(m.group(1))
            avg_v = int(m.group(2))
            boards.setdefault(board_id, {})["avg_volt"] = avg_v

        # ── DVFS adjustments ──────────────────────────────────────────────
        dvfs_events = []
        for m in RE_DVFS_ADJUST.finditer(content):
            dvfs_events.append({"volt": int(m.group(1)), "freq": int(m.group(2))})
        if dvfs_events:
            raw_fields["dvfs_events"] = dvfs_events
            raw_fields["dvfs_event_count"] = len(dvfs_events)

        # ── PowerState ────────────────────────────────────────────────────
        power_states = []
        for m in RE_POWER_STATE.finditer(content):
            power_states.append(m.group(1))
        if power_states:
            raw_fields["power_states"] = power_states

        power_reductions = len(RE_POWER_REDUCTION.findall(content))
        if power_reductions:
            raw_fields["power_reduction_events"] = power_reductions

        power_clips = len(RE_POWER_STATE_CLIP.findall(content))
        if power_clips:
            raw_fields["power_state_clips"] = power_clips

        # ── Hashrate ──────────────────────────────────────────────────────
        m = RE_HASHRATE.search(content)
        if m:
            hr = float(m.group(1))
            unit = m.group(2).upper()
            if unit == "GH":
                hr /= 1000.0
            elif unit == "MH":
                hr /= 1000000.0
            data.hashrate_th = hr

        if not data.hashrate_th:
            m = RE_GH_TOTAL.search(content)
            if m:
                data.hashrate_th = float(m.group(1))

        # ── Hitrate ───────────────────────────────────────────────────────
        hitrates = []
        for m in RE_HITRATE.finditer(content):
            hitrates.append(float(m.group(1)))
        if hitrates:
            raw_fields["hitrate"] = hitrates[-1]  # latest
            raw_fields["hitrate_min"] = min(hitrates)
            raw_fields["hitrate_avg"] = sum(hitrates) / len(hitrates)

        # ── PSU IOUT/VOUT ─────────────────────────────────────────────────
        m = RE_PSU_IOUT.search(content)
        if m:
            data.psu_current = float(m.group(1))
            raw_fields["psu_iout"] = data.psu_current

        m = RE_PSU_VOUT.search(content)
        if m:
            data.psu_voltage = float(m.group(1))
            raw_fields["psu_vout"] = data.psu_voltage

        # ── Temperatures ──────────────────────────────────────────────────
        m = RE_INLET_TEMP.search(content)
        if m:
            data.inlet_temp = float(m.group(1))

        m = RE_OUTLET_TEMP.search(content)
        if m:
            data.outlet_temp = float(m.group(1))

        for m in RE_CHIP_TEMP.finditer(content):
            data.chip_temps.append(float(m.group(1)))

        for m in RE_BOARD_TEMP.finditer(content):
            board_id = int(m.group(1)) if m.group(1) else len(data.board_temps)
            temp = float(m.group(2))
            data.board_temps.append(temp)
            boards.setdefault(board_id, {})["temp"] = temp

        # ── Fan speeds ────────────────────────────────────────────────────
        for m in RE_FAN.finditer(content):
            data.fan_speeds.append(int(m.group(1)))

        # ── Power ─────────────────────────────────────────────────────────
        m = RE_POWER_W.search(content)
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

        # ── Uptime ────────────────────────────────────────────────────────
        m = RE_UPTIME.search(content)
        if m:
            data.uptime_seconds = int(m.group(1))

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
