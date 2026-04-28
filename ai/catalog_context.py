"""
catalog_context.py — Sync Intelligence Catalog Client

Provides synchronous access to the Intelligence Catalog API running on
ROBS-PC (100.110.87.1:8420) for all AI consumers on the VPS.

Features:
  - Live reads on every call — no client-side cache (D-14 PR 1/5)
  - Circuit breaker (3 failures → skip 60s)
  - Two failure contracts:
      * Soft (legacy):  get_catalog_context / get_miner_catalog_context
        return empty string on any failure — used by the five existing
        AI/briefing consumers wrapped in try/except.
      * Strict (new):   get_miner_catalog_context_strict raises
        CatalogReadFailure on any failure path including the silent
        circuit-open skip. Used by the scanner so it can refuse to
        evaluate a miner instead of proceeding with an empty context.
  - All real failures (HTTP non-200/404, request exception, circuit-open
    skip) log at ERROR (D-14 PR 3/5). Previously these were WARNING —
    making the operator's silent-failure blind spot the worst kind:
    visible only by tailing logs at the right level.
  - Uses requests (sync, already installed)

D-14 note: the previous 5-minute TTL cache was removed because operational
facts (firmware notes, repair patterns, thresholds) are edited live and a
stale read is worse than an extra HTTP round-trip. The catalog API runs on
the same Mac Mini post-cutover; a local round-trip is cheap.

Usage:
  from ai.catalog_context import (
      get_catalog_context,
      get_miner_catalog_context,
      get_miner_catalog_context_strict,
      CatalogReadFailure,
      last_read_failed,
  )
  # Soft contract — returns "" on any failure:
  ctx = get_catalog_context(["S19JPro", "S21 EXP Hydro"], ["low_hashrate"])
  ctx = get_miner_catalog_context("S19JPro")
  # Strict contract — raises CatalogReadFailure on failure:
  try:
      ctx = get_miner_catalog_context_strict("S19JPro")
  except CatalogReadFailure as e:
      logger.error("refusing to evaluate: %s", e)
"""

import logging
import os
import time
from typing import List, Optional

import requests

logger = logging.getLogger("mining_guardian")

CATALOG_API_URL = os.getenv("CATALOG_API_URL", "http://100.110.87.1:8420")
# CRIT-6: never default to a placeholder. If the env var is missing or holds
# a known placeholder, _headers() refuses to build a request rather than
# emitting a useless Authorization header. The caller treats that the same
# as any other failure (returns empty string + opens the circuit).
CATALOG_API_KEY = os.getenv("CATALOG_API_KEY", "")
_CATALOG_KEY_PLACEHOLDERS = {
    "", "CHANGE_ME_TO_A_REAL_SECRET",
    "__GENERATE_AT_INSTALL_TIME__", "__SET_BY_INSTALLER__",
}

# Circuit breaker state
_failure_count = 0
_circuit_open_until = 0.0
_FAILURE_THRESHOLD = 3
_CIRCUIT_OPEN_DURATION = 60  # seconds

# D-14 PR 3/5: tracks whether the most recent read attempt failed. Soft
# callers can poll this after a call returns "" to distinguish "no data
# (404)" from "real failure". Reset to False on every fresh call entry.
_last_read_was_failure = False


class CatalogReadFailure(Exception):
    """Raised by the strict variants of the catalog client.

    D-14 PR 3/5: lets callers (notably the hourly scanner in
    core/mining_guardian.py) refuse to evaluate a miner rather than
    proceeding with an empty catalog context. The soft variants still
    return "" on the same conditions for backwards compatibility with
    the AI/briefing paths.
    """


def last_read_failed() -> bool:
    """Return True iff the most recent soft-variant call failed.

    Distinguishes "" from a real failure. After a successful call or a
    404 "model not in catalog yet" the flag is False; after any other
    failure (HTTP error, request exception, circuit-open skip,
    placeholder-key skip) the flag is True. Reset on every entry to a
    soft-variant function so a stale True from a prior call never leaks
    into a fresh attempt.
    """
    return _last_read_was_failure


def _is_circuit_open() -> bool:
    global _circuit_open_until
    if _failure_count >= _FAILURE_THRESHOLD:
        if time.time() < _circuit_open_until:
            return True
        # Half-open: allow one attempt
    return False


def _record_failure():
    global _failure_count, _circuit_open_until, _last_read_was_failure
    _failure_count += 1
    _last_read_was_failure = True
    if _failure_count >= _FAILURE_THRESHOLD:
        _circuit_open_until = time.time() + _CIRCUIT_OPEN_DURATION
        # D-14 PR 3/5: ERROR (was WARNING). The breaker opening means the
        # catalog has been unreachable for 3 reads — operator must see this.
        logger.error("Catalog circuit breaker OPEN — skipping for %ds", _CIRCUIT_OPEN_DURATION)


def _record_success():
    global _failure_count, _circuit_open_until, _last_read_was_failure
    _failure_count = 0
    _circuit_open_until = 0.0
    _last_read_was_failure = False


def _headers() -> Optional[dict]:
    """Build auth headers, or return None when the API key is unconfigured.

    CRIT-6: returning None lets call sites short-circuit without ever putting
    a placeholder token on the wire. Logged once per process at ERROR
    (D-14 PR 3/5: was WARNING) so the operator sees the configuration
    problem the first time it bites.
    """
    if CATALOG_API_KEY in _CATALOG_KEY_PLACEHOLDERS:
        if not getattr(_headers, "_warned", False):
            logger.error(
                "CATALOG_API_KEY is unset or holds a placeholder; "
                "catalog context calls are disabled until it is set."
            )
            _headers._warned = True  # type: ignore[attr-defined]
        return None
    return {
        "Authorization": f"Bearer {CATALOG_API_KEY}",
        "Content-Type": "application/json",
    }


def get_catalog_context(miner_models: List[str],
                        active_issues: Optional[List[str]] = None) -> str:
    """Call POST /api/v1/context/scan-bundle for bulk context.

    Soft contract: returns prompt_text string or empty string on any
    failure. After this returns, ai.catalog_context.last_read_failed()
    distinguishes a real failure from "no data".

    D-14 PR 3/5 — failure paths now log at ERROR (was WARNING). The
    return contract is unchanged so the five existing AI/briefing
    consumers continue working without modification.
    """
    global _last_read_was_failure
    _last_read_was_failure = False  # reset per-call

    if not miner_models:
        return ""

    if _is_circuit_open():
        # D-14 PR 3/5: previously this returned "" with NO log at all —
        # the worst kind of silent failure. Now logs ERROR on every skip
        # and flags last_read_was_failure so callers can detect it.
        _last_read_was_failure = True
        logger.error("Catalog scan-bundle skipped — circuit breaker is OPEN")
        return ""

    headers = _headers()
    if headers is None:
        # _headers() already logged ERROR once-per-process for the
        # placeholder/unset case. Mark the read as failed.
        _last_read_was_failure = True
        return ""

    try:
        start = time.time()
        resp = requests.post(
            f"{CATALOG_API_URL}/api/v1/context/scan-bundle",
            json={"miner_models": list(set(miner_models)),
                  "active_issues": active_issues or []},
            headers=headers,
            timeout=10,
        )
        elapsed = time.time() - start
        if resp.status_code == 200:
            text = resp.json().get("prompt_text", "")
            _record_success()
            logger.info("Catalog scan-bundle OK: %d chars in %.1fs", len(text), elapsed)
            return text
        # D-14 PR 3/5: ERROR (was WARNING).
        logger.error("Catalog scan-bundle HTTP %s (%.1fs)", resp.status_code, elapsed)
        _record_failure()
    except Exception as e:
        # D-14 PR 3/5: ERROR (was WARNING).
        logger.error("Catalog scan-bundle failed: %s", e)
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

    Soft contract: returns formatted prompt string or empty string on any
    failure. After this returns, ai.catalog_context.last_read_failed()
    distinguishes "" caused by a real failure from "" caused by a 404
    ("model not in catalog yet" — not a failure).

    D-14 PR 3/5 — failure paths now log at ERROR (was WARNING). The
    return contract is unchanged so the five existing AI/briefing
    consumers continue working without modification. Callers that want
    exception-based flow should use get_miner_catalog_context_strict.
    """
    global _last_read_was_failure
    _last_read_was_failure = False  # reset per-call

    if not model_name:
        return ""

    if _is_circuit_open():
        # D-14 PR 3/5: previously this returned "" with NO log at all —
        # the worst kind of silent failure. Now logs ERROR on every skip
        # and flags last_read_was_failure so callers can detect it.
        _last_read_was_failure = True
        logger.error("Catalog miner-knowledge [%s] skipped — circuit breaker is OPEN",
                     model_name)
        return ""

    headers = _headers()
    if headers is None:
        # _headers() already logged ERROR once-per-process. Flag failure.
        _last_read_was_failure = True
        return ""

    # Convert model name to URL slug: "S19J Pro" -> "s19j-pro"
    slug = model_name.strip().lower().replace(" ", "-")

    try:
        start = time.time()
        resp = requests.get(
            f"{CATALOG_API_URL}/api/v1/knowledge/miner/{slug}",
            headers=headers,
            timeout=10,
        )
        elapsed = time.time() - start
        if resp.status_code == 200:
            text = _format_miner_knowledge(resp.json(), model_name)
            _record_success()
            logger.info("Catalog miner-knowledge OK [%s]: %d chars in %.1fs",
                        model_name, len(text), elapsed)
            return text
        if resp.status_code == 404:
            # Model not in catalog yet — not an error.
            # D-14: no cache, so a missing model will re-query each call;
            # that's fine because adding a model in the catalog should be
            # picked up on the very next scan.
            # _last_read_was_failure stays False (this is not a failure).
            logger.debug("Catalog: no data for model '%s'", model_name)
            return ""
        # D-14 PR 3/5: ERROR (was WARNING).
        logger.error("Catalog miner-knowledge HTTP %s for %s (%.1fs)",
                     resp.status_code, model_name, elapsed)
        _record_failure()
    except Exception as e:
        # D-14 PR 3/5: ERROR (was WARNING).
        logger.error("Catalog miner-knowledge failed [%s]: %s", model_name, e)
        _record_failure()
    return ""


def get_miner_catalog_context_strict(model_name: str) -> str:
    """Strict variant of get_miner_catalog_context (D-14 PR 3/5).

    Same network behavior as the soft variant but raises
    CatalogReadFailure on any failure path — including the circuit-open
    silent-skip and the placeholder-key skip. A 404 "model not in catalog
    yet" is NOT a failure; it returns "" cleanly without raising.

    Used by core/mining_guardian.py so the hourly scan can refuse to
    evaluate a miner rather than proceed with an empty context (D-14
    sub-lock 4: "the scanner / AI / briefing logs at ERROR and refuses
    to proceed for that miner"). The five existing AI/briefing consumers
    keep using the soft variant.

    Implementation: call the soft variant, then promote a real failure
    (last_read_failed() == True) to an exception. Empty model name and
    404 'no data' return "" cleanly.
    """
    text = get_miner_catalog_context(model_name)
    if last_read_failed():
        raise CatalogReadFailure(
            f"catalog read failed for model {model_name!r} — see prior ERROR log line"
        )
    return text


def is_catalog_available() -> bool:
    """Check if the Catalog API is healthy."""
    if _is_circuit_open():
        return False
    # /api/v1/health is unauthenticated by design, so we don't gate on _headers()
    # — but if the server is on a different network we still need to reach it.
    try:
        resp = requests.get(
            f"{CATALOG_API_URL}/api/v1/health",
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("status") == "healthy"
    except Exception:
        pass
    return False
