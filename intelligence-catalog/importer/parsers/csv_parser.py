"""CSV/spreadsheet parser — spec sheet and fleet inventory CSV parsing.

Handles:
- Manufacturer spec sheet CSVs
- Fleet inventory exports
- Auto-detects columns by header names
- Maps to hardware.miner_models fields
"""

import csv
import io
import logging
import re
from typing import Any

from models import DetectedMiner, ParsedData
from .base_parser import BaseParser

logger = logging.getLogger("importer.parsers.csv")

# ─── Column name mapping — canonical field → possible header variants ─────────

COLUMN_MAPPINGS = {
    "manufacturer": [
        "manufacturer", "brand", "maker", "vendor", "mfg", "company",
    ],
    "model": [
        "model", "model_name", "model_number", "product", "miner", "device",
        "canonical_name", "name",
    ],
    "hashrate_th": [
        "hashrate", "hashrate_th", "hash_rate", "th/s", "th", "ths",
        "stock_hashrate", "rated_hashrate", "nominal_hashrate",
    ],
    "power_w": [
        "power", "power_w", "watts", "wattage", "power_consumption",
        "stock_power", "rated_power", "tdp",
    ],
    "efficiency_j_th": [
        "efficiency", "efficiency_j_th", "j/th", "j_th", "jt",
    ],
    "algorithm": [
        "algorithm", "algo", "hash_algorithm",
    ],
    "chip": [
        "chip", "asic", "asic_chip", "processor",
    ],
    "process_node": [
        "process", "process_node", "nm", "node", "technology",
    ],
    "cooling_type": [
        "cooling", "cooling_type", "cool",
    ],
    "hashboard_count": [
        "hashboards", "boards", "hashboard_count", "board_count",
    ],
    "release_date": [
        "release_date", "released", "launch_date", "date",
    ],
    "serial": [
        "serial", "serial_number", "sn",
    ],
    "mac": [
        "mac", "mac_address",
    ],
    "ip_address": [
        "ip", "ip_address", "address",
    ],
    "firmware": [
        "firmware", "fw", "firmware_version", "fw_version",
    ],
    "status": [
        "status", "state", "condition",
    ],
    "location": [
        "location", "rack", "position", "site",
    ],
    "notes": [
        "notes", "comments", "remarks",
    ],
}


def _normalize_header(header: str) -> str:
    """Normalize a CSV header for matching."""
    return re.sub(r"[^a-z0-9]", "", header.lower().strip())


def _map_headers(headers: list[str]) -> dict[str, int]:
    """Map CSV headers to canonical field names.

    Returns: {canonical_field: column_index}
    """
    mapped = {}
    for idx, raw_header in enumerate(headers):
        norm = _normalize_header(raw_header)
        for field, variants in COLUMN_MAPPINGS.items():
            for variant in variants:
                if _normalize_header(variant) == norm:
                    mapped[field] = idx
                    break
    return mapped


class CSVParser(BaseParser):
    """Parser for CSV spec sheets and fleet inventory files."""

    name = "csv"

    def can_parse(self, content: str, detected: DetectedMiner) -> bool:
        # Must be a CSV-ish file
        if not content.strip():
            return False

        # Check first few lines for CSV structure
        lines = content.strip().split("\n", 5)
        if len(lines) < 2:
            return False

        # Check for comma or tab delimiters
        first_line = lines[0]
        if "," not in first_line and "\t" not in first_line:
            return False

        # Check that header row has recognizable mining-related columns
        norm_header = first_line.lower()
        mining_keywords = [
            "model", "hashrate", "power", "manufacturer", "brand",
            "miner", "serial", "th", "watts", "efficiency",
        ]
        matches = sum(1 for kw in mining_keywords if kw in norm_header)
        return matches >= 2

    def parse(self, content: str, detected: DetectedMiner) -> ParsedData:
        data = ParsedData(parser_name=self.name)
        raw_fields: dict[str, Any] = {}

        # Detect delimiter
        first_line = content.split("\n", 1)[0]
        if "\t" in first_line and first_line.count("\t") > first_line.count(","):
            delimiter = "\t"
        else:
            delimiter = ","

        reader = csv.reader(io.StringIO(content), delimiter=delimiter)
        rows = list(reader)

        if len(rows) < 2:
            return data

        headers = rows[0]
        col_map = _map_headers(headers)

        if not col_map:
            # No recognized columns — store everything raw
            raw_fields["csv_headers"] = headers
            raw_fields["csv_row_count"] = len(rows) - 1
            data.raw_fields = raw_fields
            data.data_points_count = self._count_data_points(data)
            return data

        raw_fields["csv_mapped_columns"] = {k: headers[v] for k, v in col_map.items()}
        raw_fields["csv_row_count"] = len(rows) - 1

        # Parse each data row
        miners = []
        for row_idx, row in enumerate(rows[1:], start=2):
            if not any(cell.strip() for cell in row):
                continue  # skip empty rows

            miner_data = {}
            for field, col_idx in col_map.items():
                if col_idx < len(row):
                    val = row[col_idx].strip()
                    if val:
                        miner_data[field] = val

            if miner_data:
                miners.append(miner_data)

        raw_fields["miners"] = miners
        raw_fields["miner_count"] = len(miners)

        # Extract aggregate stats
        hashrates = []
        powers = []
        for m in miners:
            if "hashrate_th" in m:
                try:
                    hashrates.append(float(m["hashrate_th"]))
                except ValueError:
                    pass
            if "power_w" in m:
                try:
                    powers.append(float(m["power_w"]))
                except ValueError:
                    pass

        if hashrates:
            data.hashrate_th = sum(hashrates) / len(hashrates)
            raw_fields["hashrate_avg"] = data.hashrate_th
            raw_fields["hashrate_min"] = min(hashrates)
            raw_fields["hashrate_max"] = max(hashrates)

        if powers:
            data.power_w = sum(powers) / len(powers)
            raw_fields["power_avg"] = data.power_w

        if data.hashrate_th and data.power_w and data.hashrate_th > 0:
            data.efficiency_j_th = round(data.power_w / data.hashrate_th, 2)

        # Capture unmapped headers as potential unknown fields
        mapped_indices = set(col_map.values())
        for idx, header in enumerate(headers):
            if idx not in mapped_indices and header.strip():
                raw_fields[f"unmapped_col_{header.strip()}"] = [
                    row[idx].strip() if idx < len(row) else ""
                    for row in rows[1:6]  # sample first 5 rows
                ]

        data.raw_fields = raw_fields
        data.data_points_count = self._count_data_points(data)
        return data
