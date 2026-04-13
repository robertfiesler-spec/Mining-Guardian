"""Miner detection engine — identifies what miner brand/model a file belongs to.

Uses a layered approach from cheap to expensive:
1. Filename hints — patterns in the filename
2. Path/structure fingerprints — directory names and file organization
3. Header content scan — first 4KB of text content
4. Catalog lookup — match against 313 models in hardware.miner_models
"""

import logging
import re
from typing import Optional

from config import (
    DETECTION_CONFIDENCE_THRESHOLD,
    HEADER_SCAN_BYTES,
    NON_SHA256_ALGORITHMS,
)
from models import DetectedMiner, ExtractedFile

logger = logging.getLogger("importer.detector")

# ─── Filename patterns (brand → list of (regex, model_hint, confidence_boost)) ─

FILENAME_PATTERNS = {
    "bitmain": [
        (re.compile(r"S19[jJ]\s*[Pp]ro", re.I), "S19j Pro", 0.30),
        (re.compile(r"S19[jJ]\s*[Pp]ro\+", re.I), "S19j Pro+", 0.30),
        (re.compile(r"S19\s*XP", re.I), "S19 XP", 0.30),
        (re.compile(r"S19\s*[Kk]\s*[Pp]ro", re.I), "S19k Pro", 0.30),
        (re.compile(r"S21\s*XP", re.I), "S21 XP", 0.30),
        (re.compile(r"S21\s*[Pp]ro", re.I), "S21 Pro", 0.30),
        (re.compile(r"S21\b", re.I), "S21", 0.25),
        (re.compile(r"T21\b", re.I), "T21", 0.25),
        (re.compile(r"S19\b", re.I), "S19", 0.20),
        (re.compile(r"T19\b", re.I), "T19", 0.20),
        (re.compile(r"S17\s*[Pp]ro", re.I), "S17 Pro", 0.25),
        (re.compile(r"S17\+", re.I), "S17+", 0.25),
        (re.compile(r"S17[eE]?", re.I), "S17", 0.20),
        (re.compile(r"S9[ijk]?\b", re.I), "S9", 0.20),
        (re.compile(r"T17\+?", re.I), "T17", 0.20),
        (re.compile(r"AH3880", re.I), "AH3880", 0.35),
        (re.compile(r"[Aa]ntminer", re.I), None, 0.20),
        (re.compile(r"cglog_init", re.I), None, 0.25),
        (re.compile(r"miner\.log", re.I), None, 0.10),
    ],
    "microbt": [
        (re.compile(r"M63[Ss]?\+?", re.I), "M63", 0.30),
        (re.compile(r"M56[Ss]?\+?\+?", re.I), "M56", 0.30),
        (re.compile(r"M53[Ss]?\+?", re.I), "M53", 0.30),
        (re.compile(r"M50[Ss]?\+?\+?", re.I), "M50", 0.30),
        (re.compile(r"M30[Ss]?\+?\+?", re.I), "M30", 0.25),
        (re.compile(r"M33[Ss]?\+?\+?", re.I), "M33", 0.25),
        (re.compile(r"M36[Ss]?\+?\+?", re.I), "M36", 0.25),
        (re.compile(r"M66[Ss]?\+?", re.I), "M66", 0.30),
        (re.compile(r"[Ww]hats[Mm]iner", re.I), None, 0.25),
    ],
    "auradine": [
        (re.compile(r"[Tt]eraflux", re.I), None, 0.30),
        (re.compile(r"AT2880", re.I), "AT2880", 0.35),
        (re.compile(r"AT1500", re.I), "AT1500", 0.35),
        (re.compile(r"[Ff]lux[Oo][Ss]", re.I), None, 0.30),
        (re.compile(r"DVFS", re.I), None, 0.15),
        (re.compile(r"PowerState", re.I), None, 0.15),
        (re.compile(r"gcminer", re.I), None, 0.30),
        (re.compile(r"monitord", re.I), None, 0.20),
    ],
    "canaan": [
        (re.compile(r"[Aa]valon\s*\d+", re.I), None, 0.30),
        (re.compile(r"A1466", re.I), "A1466", 0.35),
        (re.compile(r"A1366", re.I), "A1366", 0.35),
        (re.compile(r"A1266", re.I), "A1266", 0.35),
        (re.compile(r"A1246", re.I), "A1246", 0.35),
        (re.compile(r"A1166\s*[Pp]ro", re.I), "A1166 Pro", 0.35),
        (re.compile(r"[Cc]anaan", re.I), None, 0.25),
    ],
}

# ─── Content header patterns ──────────────────────────────────────────────────

HEADER_BRAND_PATTERNS = {
    "bitmain": [
        (re.compile(r"Antminer\s+(S\d+[a-zA-Z]*\+*\s*(?:Pro|XP)?)", re.I), 0.35),
        (re.compile(r"BM\d{4}", re.I), 0.20),  # BM1387, BM1397, etc.
        (re.compile(r"Chain\[\d+\]", re.I), 0.15),
        (re.compile(r"cgminer", re.I), 0.10),
        (re.compile(r"bitmain", re.I), 0.30),
        (re.compile(r"bmminer", re.I), 0.25),
        (re.compile(r"antpool", re.I), 0.10),
        (re.compile(r"AH3880", re.I), 0.35),
        (re.compile(r"BiXBiT", re.I), 0.25),
        (re.compile(r"cglog_init", re.I), 0.25),
        (re.compile(r"nvdata", re.I), 0.10),
    ],
    "microbt": [
        (re.compile(r"WhatsMiner\s+(M\d+[Ss]?\+*)", re.I), 0.35),
        (re.compile(r"btminer", re.I), 0.25),
        (re.compile(r"microbt", re.I), 0.30),
        (re.compile(r"whatsminer", re.I), 0.30),
        (re.compile(r"eeprom_hw_ver", re.I), 0.20),
    ],
    "auradine": [
        (re.compile(r"Teraflux\s+(AT\d+)", re.I), 0.35),
        (re.compile(r"FluxOS", re.I), 0.30),
        (re.compile(r"auradine", re.I), 0.30),
        (re.compile(r"gcminer", re.I), 0.30),
        (re.compile(r"monitord", re.I), 0.20),
        (re.compile(r"DVFS.*volt", re.I), 0.25),
        (re.compile(r"PowerState", re.I), 0.20),
        (re.compile(r"avg_volt\s+\d+:", re.I), 0.30),
        (re.compile(r"chip\s+\d+/\d+", re.I), 0.15),
        (re.compile(r"IOUT", re.I), 0.15),
    ],
    "canaan": [
        (re.compile(r"Avalon\s*(\d+)", re.I), 0.35),
        (re.compile(r"canaan", re.I), 0.30),
        (re.compile(r"AvalonMiner", re.I), 0.30),
        (re.compile(r"A\d{4}", re.I), 0.15),
        (re.compile(r"mm_version", re.I), 0.20),
    ],
}

# Model extraction patterns from content
MODEL_EXTRACT_PATTERNS = [
    # Bitmain: "Antminer S19j Pro" or "S19j Pro"
    (re.compile(r"Antminer\s+(S\d+[a-zA-Z]*\s*\+*\s*(?:Pro|XP|Hyd)?)", re.I), "bitmain"),
    (re.compile(r"Antminer\s+(T\d+[a-zA-Z]*\s*\+*\s*(?:Pro|XP|Hyd)?)", re.I), "bitmain"),
    # MicroBT: "WhatsMiner M50S+" or "M50S+"
    (re.compile(r"WhatsMiner\s+(M\d+[Ss]?\+*\+?)", re.I), "microbt"),
    (re.compile(r"\b(M\d{2}[Ss]?\+*\+?)\b", re.I), "microbt"),
    # Auradine: "Teraflux AT2880"
    (re.compile(r"Teraflux\s+(AT\d+)", re.I), "auradine"),
    # Canaan: "Avalon A1466" or "AvalonMiner 1466"
    (re.compile(r"Avalon(?:Miner)?\s*(A?\d{4}[A-Za-z]*)", re.I), "canaan"),
    # AH3880 (specific hashboard)
    (re.compile(r"\b(AH3880)\b", re.I), "bitmain"),
]

# Firmware extraction patterns
FIRMWARE_PATTERNS = [
    re.compile(r"firmware[:\s]+v?(\S+)", re.I),
    re.compile(r"fw[:\s]+v?(\S+)", re.I),
    re.compile(r"version[:\s]+v?(\d+\.\d+\.\d+\S*)", re.I),
    re.compile(r"BiXBiT[:\s]+v?(\S+)", re.I),
    re.compile(r"FluxOS[:\s]+v?(\S+)", re.I),
    re.compile(r"cgminer\s+(\d+\.\d+\.\d+)", re.I),
    re.compile(r"bmminer\s+(\d+\.\d+\.\d+)", re.I),
    re.compile(r"btminer\s+(\d+\.\d+\.\d+)", re.I),
]

# Serial number patterns
SERIAL_PATTERNS = [
    re.compile(r"serial[:\s]+(\S+)", re.I),
    re.compile(r"sn[:\s]+(\S+)", re.I),
    re.compile(r"Serial Number[:\s]+(\S+)", re.I),
]

# MAC address patterns
MAC_PATTERNS = [
    re.compile(r"mac[:\s]+([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})", re.I),
    re.compile(r"MAC[:\s]+([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})", re.I),
    re.compile(r"\b([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})\b"),
]

# IP address pattern
IP_PATTERN = re.compile(
    r"(?:ip[:\s]+|IP[:\s]+|address[:\s]+)?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
)

# Non-SHA-256 indicators in content
NON_SHA256_CONTENT_PATTERNS = [
    re.compile(r"\b(?:" + "|".join(NON_SHA256_ALGORITHMS) + r")\b", re.I),
    re.compile(r"(?:KS\d|KA\d|KHeavyHash)", re.I),  # Kaspa miners
    re.compile(r"(?:L7|L9)\b", re.I),  # Litecoin miners (Scrypt)
    re.compile(r"(?:E9|E9\s*Pro)\b", re.I),  # Ethereum miners
    re.compile(r"(?:Z15|Z11)\b", re.I),  # Zcash miners
    re.compile(r"(?:D9|D7|DR5)\b", re.I),  # Decred miners
    re.compile(r"(?:HS[35]|HS\d)\b", re.I),  # Handshake miners
    re.compile(r"IceRiver", re.I),  # KAS miners
]


class MinerDetector:
    """Detects what miner brand/model a file belongs to."""

    def __init__(self, db_conn=None):
        self._conn = db_conn
        self._model_cache: Optional[list[dict]] = None

    def _get_model_cache(self) -> list[dict]:
        """Lazy-load and cache all model names from the catalog."""
        if self._model_cache is None and self._conn:
            try:
                from db import get_all_model_names
                self._model_cache = get_all_model_names(self._conn)
            except Exception as e:
                logger.warning("Could not load model cache: %s", e)
                self._model_cache = []
        return self._model_cache or []

    def detect(self, extracted: ExtractedFile) -> DetectedMiner:
        """Run the full detection pipeline on an extracted file."""
        detected = DetectedMiner()
        brand_scores: dict[str, float] = {}
        evidence: list[str] = []
        model_hint: Optional[str] = None

        # ── Layer 1: Filename hints ───────────────────────────────────────
        filename = extracted.filename
        for brand, patterns in FILENAME_PATTERNS.items():
            for pattern, hint, boost in patterns:
                if pattern.search(filename):
                    brand_scores[brand] = brand_scores.get(brand, 0) + boost
                    evidence.append(f"filename:{pattern.pattern}")
                    if hint and model_hint is None:
                        model_hint = hint

        # ── Layer 2: Path/structure fingerprints ──────────────────────────
        full_path = extracted.original_path.lower()
        if "nvdata" in full_path and "cglog" in full_path:
            brand_scores["bitmain"] = brand_scores.get("bitmain", 0) + 0.20
            evidence.append("path:nvdata/cglog=BiXBiT")
        if "gcminer" in full_path or "monitord" in full_path:
            brand_scores["auradine"] = brand_scores.get("auradine", 0) + 0.25
            evidence.append("path:gcminer/monitord=FluxOS")
        if "btminer" in full_path:
            brand_scores["microbt"] = brand_scores.get("microbt", 0) + 0.20
            evidence.append("path:btminer=WhatsMiner")

        # ── Layer 3: Header content scan ──────────────────────────────────
        content = extracted.content or ""
        header = content[:HEADER_SCAN_BYTES]

        if header:
            # Check for non-SHA-256 algorithms
            for nsp in NON_SHA256_CONTENT_PATTERNS:
                if nsp.search(header):
                    detected.algorithm = "non-SHA-256"
                    detected.confidence = 0.90
                    detected.evidence = [f"non_sha256:{nsp.pattern}"]
                    return detected

            # Brand patterns in content header
            for brand, patterns in HEADER_BRAND_PATTERNS.items():
                for pattern, boost in patterns:
                    m = pattern.search(header)
                    if m:
                        brand_scores[brand] = brand_scores.get(brand, 0) + boost
                        evidence.append(f"content:{pattern.pattern}")
                        # Extract model from captured group if available
                        if m.lastindex and m.lastindex >= 1 and model_hint is None:
                            model_hint = m.group(1).strip()

            # Model extraction from content
            for pattern, brand in MODEL_EXTRACT_PATTERNS:
                m = pattern.search(header)
                if m:
                    candidate = m.group(1).strip()
                    if model_hint is None or len(candidate) > len(model_hint):
                        model_hint = candidate
                    brand_scores[brand] = brand_scores.get(brand, 0) + 0.10
                    evidence.append(f"model_extract:{candidate}")

            # Firmware extraction
            for fp in FIRMWARE_PATTERNS:
                m = fp.search(header)
                if m and detected.firmware is None:
                    detected.firmware = m.group(1)
                    evidence.append(f"firmware:{detected.firmware}")
                    break

            # Serial extraction
            for sp in SERIAL_PATTERNS:
                m = sp.search(header)
                if m and detected.serial is None:
                    detected.serial = m.group(1)
                    evidence.append(f"serial:{detected.serial}")
                    break

            # MAC extraction
            for mp in MAC_PATTERNS:
                m = mp.search(header)
                if m and detected.mac is None:
                    detected.mac = m.group(1)
                    evidence.append(f"mac:{detected.mac}")
                    break

            # IP extraction
            m = IP_PATTERN.search(header)
            if m:
                detected.ip_address = m.group(1)

        # ── Determine winning brand ───────────────────────────────────────
        if brand_scores:
            best_brand = max(brand_scores, key=brand_scores.get)
            detected.brand = best_brand
            detected.confidence = min(brand_scores[best_brand], 1.0)
        else:
            detected.confidence = 0.0

        if model_hint:
            detected.model = model_hint

        detected.evidence = evidence

        # ── Layer 4: Catalog lookup ───────────────────────────────────────
        if detected.brand and detected.model and self._conn:
            try:
                from db import lookup_miner_model
                catalog = lookup_miner_model(self._conn, detected.brand, detected.model)
                if catalog:
                    detected.catalog_model_id = str(catalog["id"])
                    detected.catalog_name = catalog["canonical_name"]
                    detected.manufacturer_id = str(catalog["manufacturer_id"])
                    detected.stock_hashrate_th = (
                        float(catalog["stock_hashrate_th"])
                        if catalog.get("stock_hashrate_th")
                        else None
                    )
                    detected.stock_power_w = (
                        float(catalog["stock_power_w"])
                        if catalog.get("stock_power_w")
                        else None
                    )
                    # Boost confidence for catalog match
                    detected.confidence = min(detected.confidence + 0.20, 1.0)
                    detected.evidence.append(
                        f"catalog_match:{catalog['canonical_name']}"
                    )
            except Exception as e:
                logger.warning("Catalog lookup failed: %s", e)
        elif detected.brand and not detected.model and self._conn:
            # Try to find model from content using full catalog scan
            self._try_catalog_content_match(content, detected)

        return detected

    def _try_catalog_content_match(
        self, content: str, detected: DetectedMiner
    ) -> None:
        """Try to match a model by scanning content against all catalog model names."""
        models = self._get_model_cache()
        brand_models = [
            m for m in models
            if m.get("manufacturer_brand") == detected.brand
        ]

        best_match = None
        best_len = 0
        header = content[:HEADER_SCAN_BYTES * 2]  # scan a bit more

        for m in brand_models:
            name = m.get("canonical_name", "")
            model_num = m.get("model_number", "")
            # Search for the model number (more specific) in the content
            if model_num and model_num.lower() in header.lower():
                if len(model_num) > best_len:
                    best_match = m
                    best_len = len(model_num)

        if best_match:
            detected.model = best_match.get("model_number") or best_match["canonical_name"]
            detected.catalog_model_id = str(best_match["id"])
            detected.catalog_name = best_match["canonical_name"]
            detected.confidence = min(detected.confidence + 0.15, 1.0)
            detected.evidence.append(f"catalog_scan:{best_match['canonical_name']}")
