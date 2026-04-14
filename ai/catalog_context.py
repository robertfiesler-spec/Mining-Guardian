"""
catalog_context.py — Sync Intelligence Catalog Client

Provides synchronous access to the Intelligence Catalog API running on
ROBS-PC (100.110.87.1:8420) for all AI consumers on the VPS.

Features:
  - TTL cache (5 min) to avoid redundant API calls
  - Circuit breaker (3 failures → skip 60s)
  - Never raises — returns empty string on any failure
  - Uses requests (sync, already installed)

Usage:
  from ai.catalog_context import get_catalog_context, get_miner_catalog_context
  ctx = get_catalog_context(["S19JPro", "S21 EXP Hydro"], ["low_hashrate"])
  ctx = get_miner_catalog_context("S19JPro")
"""

import logging
import os
import time
from typing import List, Optional

import requests

logger = logging.getLogger("mining_guardian")

CATALOG_API_URL = os.getenv("CATALOG_API_URL", "http://100.110.87.1:8420")
CATALOG_API_KEY = os.getenv("CATALOG_API_KEY", "CHANGE_ME_TO_A_REAL_SECRET")

# TTL cache: {cache_key: (timestamp, value)}
_cache: dict = {}
_CACHE_TTL = 300  # 5 minutes

# Circuit breaker state
_failure_count = 0
_circuit_open_until = 0.0
_FAILURE_THRESHOLD = 3
_CIRCUIT_OPEN_DURATION = 60  # seconds


def _is_circuit_open() -> bool:
    global _circuit_open_until
    if _failure_count >= _FAILURE_THRESHOLD:
        if time.time() < _circuit_open_until:
            return True
        # Half-open: allow one attempt
    return False


def _record_failure():
    global _failure_count, _circuit_open_until
    _failure_count += 1
    if _failure_count >= _FAILURE_THRESHOLD:
        _circuit_open_until = time.time() + _CIRCUIT_OPEN_DURATION
        logger.warning("Catalog circuit breaker OPEN — skipping for %ds", _CIRCUIT_OPEN_DURATION)


def _record_success():
    global _failure_count, _circuit_open_until
    _failure_count = 0
    _circuit_open_until = 0.0


def _cache_get(key: str) -> Optional[str]:
    entry = _cache.get(key)
    if entry and (time.time() - entry[0]) < _CACHE_TTL:
        return entry[1]
    return None


def _cache_set(key: str, value: str):
    _cache[key] = (time.time(), value)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {CATALOG_API_KEY}",
        "Content-Type": "application/json",
    }


def get_catalog_context(miner_models: List[str],
                        active_issues: Optional[List[str]] = None) -> str:
    """Call POST /api/v1/context/scan-bundle for bulk context.

    Returns prompt_text string or empty string on any failure.
    """
    if not miner_models:
        return ""

    cache_key = f"bundle:{'|'.join(sorted(set(miner_models)))}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    if _is_circuit_open():
        return ""

    try:
        start = time.time()
        resp = requests.post(
            f"{CATALOG_API_URL}/api/v1/context/scan-bundle",
            json={"miner_models": list(set(miner_models)),
                  "active_issues": active_issues or []},
            headers=_headers(),
            timeout=10,
        )
        elapsed = time.time() - start
        if resp.status_code == 200:
            text = resp.json().get("prompt_text", "")
            _record_success()
            _cache_set(cache_key, text)
            logger.info("Catalog scan-bundle OK: %d chars in %.1fs", len(text), elapsed)
            return text
        logger.warning("Catalog scan-bundle HTTP %s (%.1fs)", resp.status_code, elapsed)
        _record_failure()
    except Exception as e:
        logger.warning("Catalog scan-bundle failed: %s", e)
        _record_failure()
    return ""


def _format_miner_knowledge(data: dict, model_name: str) -> str:
    """Format the /knowledge/miner response into a prompt-ready string."""
    parts = [f"=== Catalog: {model_name} ==="]

    model_info = data.get("model", {})
    if model_info:
        specs = []
        for key in ("manufacturer", "hashrate_th", "power_watts", "efficiency_jth",
                    "asic_chip", "chip_count", "cooling_mode", "release_year"):
            val = model_info.get(key)
            if val is not None:
                specs.append(f"{key}: {val}")
        if specs:
            parts.append("Specs: " + ", ".join(specs))

    chip = data.get("chip_specs")
    if chip:
        for c in chip[:2]:
            parts.append(f"Chip: {c.get('chip_name', '?')} — "
                         f"process: {c.get('process_node', '?')}, "
                         f"nom freq: {c.get('nominal_freq_mhz', '?')} MHz")

    firmware = data.get("firmware")
    if firmware:
        for fw in firmware[:3]:
            parts.append(f"FW: {fw.get('version', '?')} "
                         f"({fw.get('manufacturer', '?')}) — "
                         f"{fw.get('notes', '')[:80]}")

    failures = data.get("failures")
    if failures:
        parts.append("Known failure patterns:")
        for f in failures[:5]:
            parts.append(f"  - {f.get('pattern_name', f.get('description', '?'))[:100]}")

    repair = data.get("repair")
    if repair:
        parts.append("Repair notes:")
        for r in repair[:3]:
            parts.append(f"  - {str(r.get('note', r))[:100]}")

    thresholds = data.get("thresholds")
    if thresholds:
        parts.append("Thresholds:")
        for t in thresholds[:5]:
            parts.append(f"  - {t.get('metric', '?')}: "
                         f"warn={t.get('warn_value', '?')}, "
                         f"crit={t.get('critical_value', '?')}")

    return "\n".join(parts)


def get_miner_catalog_context(model_name: str) -> str:
    """Call GET /api/v1/knowledge/miner/{model_slug} for a single model.

    Returns formatted prompt string or empty string on any failure.
    """
    if not model_name:
        return ""

    cache_key = f"miner:{model_name}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    if _is_circuit_open():
        return ""

    # Convert model name to URL slug: "S19J Pro" -> "s19j-pro"
    slug = model_name.strip().lower().replace(" ", "-")

    try:
        start = time.time()
        resp = requests.get(
            f"{CATALOG_API_URL}/api/v1/knowledge/miner/{slug}",
            headers=_headers(),
            timeout=10,
        )
        elapsed = time.time() - start
        if resp.status_code == 200:
            text = _format_miner_knowledge(resp.json(), model_name)
            _record_success()
            _cache_set(cache_key, text)
            logger.info("Catalog miner-knowledge OK [%s]: %d chars in %.1fs",
                        model_name, len(text), elapsed)
            return text
        if resp.status_code == 404:
            # Model not in catalog yet — not an error, cache empty
            _cache_set(cache_key, "")
            logger.debug("Catalog: no data for model '%s'", model_name)
            return ""
        logger.warning("Catalog miner-knowledge HTTP %s for %s (%.1fs)",
                       resp.status_code, model_name, elapsed)
        _record_failure()
    except Exception as e:
        logger.warning("Catalog miner-knowledge failed [%s]: %s", model_name, e)
        _record_failure()
    return ""


def is_catalog_available() -> bool:
    """Check if the Catalog API is healthy."""
    if _is_circuit_open():
        return False
    try:
        resp = requests.get(
            f"{CATALOG_API_URL}/api/v1/health",
            headers=_headers(),
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("status") == "healthy"
    except Exception:
        pass
    return False
