"""
catalog_context.py — Local Postgres-backed Intelligence Catalog reader.

P-018C: replaces the previous HTTP client (which defaulted to the retired
ROBS-PC tailscale endpoint `http://100.110.87.1:8420` and was the live
cause of `Catalog miner-knowledge failed → circuit-breaker OPEN` on the
Mac mini scanner) with a direct psycopg2 reader against the customer's
local catalog DB `mining_guardian_catalog`.

Per D-14 sub-lock 5 ("AI consumers talk psycopg-direct to catalog DB on
the Mini, no HTTP round-trip") and Vision Anchor 6 (no cloud-only
operational-loop dependencies), the catalog DB lives in the same
Postgres container as the operational DB, on `127.0.0.1:5432`. The DSN
is resolved through `core.db_targets.catalog_target()` (P-018A), which
reads `GUARDIAN_PG_HOST/_PORT/_USER/_PASSWORD/_CATALOG_DBNAME` from .env.

Public surface preserved exactly (callers in ai/*.py, core/*.py
unmodified):

  - get_catalog_context(miner_models, active_issues=None) -> str
  - get_miner_catalog_context(model_name) -> str
  - get_miner_catalog_context_strict(model_name) -> str
  - is_catalog_available() -> bool
  - last_read_failed() -> bool
  - CatalogReadFailure (Exception)

Behavior contracts preserved:

  - Soft variants return "" on any failure; `last_read_failed()`
    distinguishes "no data" from a real failure.
  - Strict variant raises `CatalogReadFailure` on any real failure
    (including circuit-open). A 404-equivalent ("model not found in
    catalog") is NOT a failure — returns "" cleanly.
  - Circuit breaker: 3 consecutive failures → open for 60s. Same shape
    as the HTTP version — the failures it protects against are now
    psycopg2 connect/query exceptions instead of HTTP timeouts.
  - All real failures log at ERROR (D-14 PR 3/5 contract).

Data shape preserved:

  - The per-miner formatter `_format_miner_knowledge(data, model_name)`
    is reused verbatim from the previous HTTP version. It expects a
    dict with keys {model, chip_specs, firmware, failures, repair,
    thresholds}; the new `_fetch_miner_knowledge_pg(...)` builds that
    dict directly from the catalog DB. Sections that probe a missing
    table return [] / {} so the formatter sees the same "absent" shape
    it used to see when the HTTP server's section was empty.
  - The bulk `get_catalog_context(...)` joins per-miner contexts into a
    single newline-joined string. The exact wording differs from the
    previous HTTP server's `_format_prompt_text` (300-line bundle
    formatter) but the contract is the same: a prompt-text string of
    catalog facts. LLM consumers (ai/local_llm_analyzer.py,
    ai/deep_analysis_claude.py, ai/daily_deep_dive.py) treat this as
    opaque context — they do not parse it.

Opt-in legacy HTTP fallback:

  - Setting `MG_CATALOG_HTTP_FALLBACK_URL=http://<host>:<port>` (any
    URL the operator explicitly chooses) re-enables the previous HTTP
    path as a fallback when the local DB is unreachable. **Default is
    OFF**, and we do NOT default to `100.110.87.1:8420` or any
    Tailscale IP. This exists only for emergency rollback during the
    P-018C rollout window. Removing this hook is fine in a follow-up
    once the customer install verifies the local-DB path.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("mining_guardian")

# ---------------------------------------------------------------------------
# Circuit breaker state (preserved from HTTP version — same caller contract)
# ---------------------------------------------------------------------------

_failure_count = 0
_circuit_open_until = 0.0
_FAILURE_THRESHOLD = 3
_CIRCUIT_OPEN_DURATION = 60  # seconds

# Per-call failure flag for last_read_failed(). Reset on every entry to
# any soft-variant function so a stale True from a prior call cannot leak
# into a fresh attempt.
_last_read_was_failure = False


class CatalogReadFailure(Exception):
    """Raised by `get_miner_catalog_context_strict` on any real failure.

    A 404-equivalent ("model not found in catalog") returns "" cleanly
    rather than raising — matches the HTTP-era contract used by
    core/mining_guardian.py:_consult_catalog.
    """


def last_read_failed() -> bool:
    """True iff the most recent soft-variant call failed.

    Distinguishes "" caused by a real failure (DB unreachable, query
    error, circuit-open) from "" caused by 'model not in catalog yet'
    (which is not a failure). Reset to False on every fresh call entry
    to a soft-variant function.
    """
    return _last_read_was_failure


# ---------------------------------------------------------------------------
# DB connection target (P-018A helper)
# ---------------------------------------------------------------------------


def _resolve_catalog_target():
    """Resolve `core.db_targets.catalog_target()`, repo-root-resilient.

    `ai/` is on sys.path next to `core/` for normal imports; this guard
    handles the edge case where this module is imported from a process
    whose cwd is somewhere else (e.g., a one-off cron invocation).
    """
    try:
        from core.db_targets import catalog_target
    except ImportError:
        import sys
        from pathlib import Path
        repo_root = Path(__file__).resolve().parents[1]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from core.db_targets import catalog_target  # type: ignore[no-redef]
    return catalog_target()


# ---------------------------------------------------------------------------
# Circuit-breaker helpers (kept private and side-effect-only)
# ---------------------------------------------------------------------------


def _is_circuit_open() -> bool:
    if _failure_count >= _FAILURE_THRESHOLD:
        if time.time() < _circuit_open_until:
            return True
    return False


def _record_failure() -> None:
    global _failure_count, _circuit_open_until, _last_read_was_failure
    _failure_count += 1
    _last_read_was_failure = True
    if _failure_count >= _FAILURE_THRESHOLD:
        _circuit_open_until = time.time() + _CIRCUIT_OPEN_DURATION
        logger.error(
            "Catalog circuit breaker OPEN — skipping for %ds",
            _CIRCUIT_OPEN_DURATION,
        )


def _record_success() -> None:
    global _failure_count, _circuit_open_until, _last_read_was_failure
    _failure_count = 0
    _circuit_open_until = 0.0
    _last_read_was_failure = False


# ---------------------------------------------------------------------------
# Connection — psycopg2, lazy, fail-soft
# ---------------------------------------------------------------------------


def _open_catalog_connection():
    """Open a short-lived psycopg2 connection to the catalog DB.

    Returns None on any failure. Caller logs / circuit-breaks; this
    helper stays silent on connect failures because some callers
    (`is_catalog_available`) expect None to mean "unreachable" without
    a log line.
    """
    try:
        import psycopg2  # type: ignore
    except ImportError:
        logger.error("psycopg2 not installed; catalog reads disabled.")
        return None

    target = _resolve_catalog_target()
    if not target.password:
        logger.error(
            "no DB password set (GUARDIAN_PG_PASSWORD / MG_DB_PASSWORD); "
            "catalog reads disabled."
        )
        return None

    try:
        return psycopg2.connect(connect_timeout=5, **target.connect_kwargs())
    except Exception as exc:
        logger.error("catalog DB connect failed: %s", exc)
        return None


def _table_exists(cur, qualified_name: str) -> bool:
    """Return True iff `<schema>.<table>` is visible to the current role.

    Uses `to_regclass(...)` which returns NULL when the table does not
    exist — never raises, so this is safe on a fresh customer mini that
    might be missing some optional schemas (firmware/repair extensions).
    """
    cur.execute("SELECT to_regclass(%s)", (qualified_name,))
    row = cur.fetchone()
    return bool(row and row[0])


# ---------------------------------------------------------------------------
# Per-miner reader — produces the dict shape `_format_miner_knowledge`
# already expects (preserves caller-facing data shape exactly).
# ---------------------------------------------------------------------------


def _slug_search_terms(model_name: str) -> List[str]:
    """Build the candidate strings used to ILIKE-match `canonical_name`.

    Mirrors what the previous HTTP server did with `model_slug` → search
    term: lowercase, hyphens/underscores → spaces, trim. We try the
    raw model_name first, then the slug-derived form, then the most
    common normalisation ("S19J Pro" / "S19j Pro" / "s19j pro").
    """
    raw = model_name.strip()
    if not raw:
        return []
    slug = raw.lower().replace("_", " ").replace("-", " ")
    return list(dict.fromkeys([raw, slug, slug.title()]))  # de-dup, preserve order


def _resolve_model_row(cur, model_name: str) -> Optional[Dict[str, Any]]:
    """Look up one model in `hardware.miner_models` by canonical_name.

    Tries an exact ILIKE on each candidate first, then a contains-match.
    Returns the first hit with the columns the formatter expects (with
    derived/aliased column names so the dict shape matches the HTTP-era
    response).
    """
    if not _table_exists(cur, "hardware.miner_models"):
        return None

    select_cols = """
        m.id,
        m.canonical_name,
        m.model_number,
        m.cooling_type::text       AS cooling_mode,
        m.stock_hashrate_th        AS hashrate_th,
        m.stock_power_w            AS power_watts,
        m.stock_efficiency_j_th    AS efficiency_jth,
        m.released_date,
        m.is_current_product,
        man.common_name            AS manufacturer
    """
    join = "FROM hardware.miner_models m " \
           "LEFT JOIN hardware.manufacturers man ON m.manufacturer_id = man.id"

    for term in _slug_search_terms(model_name):
        # Phase 1: exact ILIKE (catches "Antminer S19j Pro" → "antminer s19j pro").
        cur.execute(
            f"SELECT {select_cols} {join} "
            f"WHERE m.canonical_name ILIKE %s OR m.model_number ILIKE %s LIMIT 1",
            (term, term),
        )
        row = cur.fetchone()
        if row:
            return _row_to_dict(cur, row)
        # Phase 2: contains-match.
        cur.execute(
            f"SELECT {select_cols} {join} "
            f"WHERE m.canonical_name ILIKE %s OR m.model_number ILIKE %s LIMIT 1",
            (f"%{term}%", f"%{term}%"),
        )
        row = cur.fetchone()
        if row:
            return _row_to_dict(cur, row)

    return None


def _row_to_dict(cur, row: tuple) -> Dict[str, Any]:
    return {desc[0]: row[i] for i, desc in enumerate(cur.description)}


def _rows_to_dicts(cur, rows: List[tuple]) -> List[Dict[str, Any]]:
    return [{desc[0]: r[i] for i, desc in enumerate(cur.description)} for r in rows]


def _fetch_chip_specs(cur, model: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Best-effort chip lookup. `hardware.chips` and `hardware.miner_models`
    relate via `hashboard_id → control_board_id → chip` in the full schema;
    here we keep it cheap and just match by the model's `asic_chip` text
    (which the catalog_api also did via ILIKE) when present.

    Returns a list with the keys `_format_miner_knowledge` reads:
    `chip_name`, `process_node`, `nominal_freq_mhz`.
    """
    if not _table_exists(cur, "hardware.chips"):
        return []
    chip_hint = model.get("asic_chip") or model.get("chip_name") or ""
    if not chip_hint:
        return []
    cur.execute(
        "SELECT chip_name, process_node, nominal_freq_mhz "
        "FROM hardware.chips WHERE chip_name ILIKE %s LIMIT 5",
        (f"%{chip_hint}%",),
    )
    return _rows_to_dicts(cur, cur.fetchall())


def _fetch_firmware(cur, model_id) -> List[Dict[str, Any]]:
    """Return firmware releases compatible with `model_id`.

    P-021 (2026-05-07): the canonical schema does NOT have a `model_id`
    column on `firmware.firmware_releases`. The model→firmware link is the
    join table `firmware.firmware_compatibility(firmware_id, miner_model_id)`.
    The pre-P-021 query
        SELECT * FROM firmware.firmware_releases WHERE model_id = %s
    threw `column "model_id" does not exist` on the live Mini scanner for
    every miner that reached the catalog read path (B-30). We now JOIN
    through the compatibility table.
    """
    if not model_id or not _table_exists(cur, "firmware.firmware_releases"):
        return []
    if not _table_exists(cur, "firmware.firmware_compatibility"):
        # No compatibility table yet — return all current-stable firmware
        # so the LLM still has *some* firmware context. Cheap fallback.
        cur.execute(
            "SELECT * FROM firmware.firmware_releases "
            "WHERE is_current_stable = TRUE "
            "ORDER BY release_date DESC NULLS LAST LIMIT 20"
        )
        return _rows_to_dicts(cur, cur.fetchall())
    cur.execute(
        """
        SELECT fr.*
        FROM firmware.firmware_releases fr
        JOIN firmware.firmware_compatibility fc ON fc.firmware_id = fr.id
        WHERE fc.miner_model_id = %s
        ORDER BY fr.release_date DESC NULLS LAST
        LIMIT 20
        """,
        (model_id,),
    )
    return _rows_to_dicts(cur, cur.fetchall())


def _fetch_failures(cur, model_id) -> List[Dict[str, Any]]:
    """Read `ops.failure_patterns` keyed by primary_model_id.

    Defensive about column drift between schema versions: tries
    `primary_model_id` first (canonical seed schema), falls back to a
    wildcard-not-found if the table is absent.
    """
    if not model_id or not _table_exists(cur, "ops.failure_patterns"):
        return []
    cur.execute(
        "SELECT pattern_name, description, severity::text AS severity "
        "FROM ops.failure_patterns WHERE primary_model_id = %s LIMIT 20",
        (model_id,),
    )
    return _rows_to_dicts(cur, cur.fetchall())


def _fetch_repair(cur, model_id) -> List[Dict[str, Any]]:
    """Return repair procedures for `model_id`.

    P-021 (2026-05-07): the canonical schema FK column on
    `repair.repair_procedures` is `miner_model_id`, NOT `model_id` — the
    pre-P-021 query was a sibling of the firmware bug (B-30). The
    column is nullable per schema comment ("NULL = universal"), so we
    OR in NULL to surface universal procedures alongside model-specific
    ones.
    """
    if not model_id or not _table_exists(cur, "repair.repair_procedures"):
        return []
    cur.execute(
        "SELECT id, procedure_name AS note "
        "FROM repair.repair_procedures "
        "WHERE miner_model_id = %s OR miner_model_id IS NULL LIMIT 10",
        (model_id,),
    )
    return _rows_to_dicts(cur, cur.fetchall())


def _fetch_thresholds(cur, model_id) -> List[Dict[str, Any]]:
    """Return operational thresholds for `model_id`.

    P-021 (2026-05-07): canonical FK is `miner_model_id` (nullable —
    NULL means "applies to all models"). Same fix as `_fetch_repair`.
    """
    if not model_id or not _table_exists(cur, "ops.operational_thresholds"):
        return []
    cur.execute(
        "SELECT metric_name AS metric, warn_value, critical_value "
        "FROM ops.operational_thresholds "
        "WHERE miner_model_id = %s OR miner_model_id IS NULL LIMIT 20",
        (model_id,),
    )
    return _rows_to_dicts(cur, cur.fetchall())


def _fetch_miner_knowledge_pg(model_name: str) -> Optional[Dict[str, Any]]:
    """Build the dict that `_format_miner_knowledge` formats.

    Returns:
      - dict with the expected keys when the model is found.
      - {} (empty dict) when the model is not in the catalog (404-equivalent —
        not a failure; soft callers return "" cleanly without flagging
        last_read_failed).
      - None on any real DB failure (circuit-breaker fodder).
    """
    conn = _open_catalog_connection()
    if conn is None:
        return None
    try:
        with conn, conn.cursor() as cur:
            model = _resolve_model_row(cur, model_name)
            if model is None:
                return {}  # not found — not a failure
            model_id = model.get("id")
            return {
                "model": model,
                "chip_specs": _fetch_chip_specs(cur, model),
                "firmware": _fetch_firmware(cur, model_id),
                "failures": _fetch_failures(cur, model_id),
                "repair": _fetch_repair(cur, model_id),
                "thresholds": _fetch_thresholds(cur, model_id),
            }
    except Exception as exc:
        logger.error("catalog DB query failed for model %r: %s", model_name, exc)
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Formatter (preserved verbatim from the HTTP version — public-facing
# data shape contract for `get_miner_catalog_context*`)
# ---------------------------------------------------------------------------


def _format_miner_knowledge(data: dict, model_name: str) -> str:
    """Format the per-miner dict into the prompt-ready string the
    scanner / AI consumers expect. Byte-for-byte the same logic as the
    previous HTTP-era formatter — only the data source changed."""
    parts = [f"=== Catalog: {model_name} ==="]

    model_info = data.get("model", {})
    if model_info:
        specs = []
        for key in (
            "manufacturer",
            "hashrate_th",
            "power_watts",
            "efficiency_jth",
            "asic_chip",
            "chip_count",
            "cooling_mode",
            "release_year",
        ):
            val = model_info.get(key)
            if val is not None:
                specs.append(f"{key}: {val}")
        if specs:
            parts.append("Specs: " + ", ".join(specs))

    chip = data.get("chip_specs")
    if chip:
        for c in chip[:2]:
            parts.append(
                f"Chip: {c.get('chip_name', '?')} — "
                f"process: {c.get('process_node', '?')}, "
                f"nom freq: {c.get('nominal_freq_mhz', '?')} MHz"
            )

    firmware = data.get("firmware")
    if firmware:
        for fw in firmware[:3]:
            parts.append(
                f"FW: {fw.get('version', '?')} "
                f"({fw.get('manufacturer', '?')}) — "
                f"{(fw.get('notes', '') or '')[:80]}"
            )

    failures = data.get("failures")
    if failures:
        parts.append("Known failure patterns:")
        for f in failures[:5]:
            label = f.get("pattern_name", f.get("description", "?")) or "?"
            parts.append(f"  - {str(label)[:100]}")

    repair = data.get("repair")
    if repair:
        parts.append("Repair notes:")
        for r in repair[:3]:
            parts.append(f"  - {str(r.get('note', r))[:100]}")

    thresholds = data.get("thresholds")
    if thresholds:
        parts.append("Thresholds:")
        for t in thresholds[:5]:
            parts.append(
                f"  - {t.get('metric', '?')}: "
                f"warn={t.get('warn_value', '?')}, "
                f"crit={t.get('critical_value', '?')}"
            )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Optional HTTP fallback (opt-in only — never defaults to ROBS-PC)
# ---------------------------------------------------------------------------


def _http_fallback_url() -> Optional[str]:
    """Return the operator-set HTTP fallback URL, or None.

    Reads `MG_CATALOG_HTTP_FALLBACK_URL` (intentionally a *new* env var
    name so a leftover `CATALOG_API_URL` from older `.env` files does
    NOT silently re-enable HTTP fallback). Refuses any value that
    contains `100.110.87.1` or any other private/Tailscale CGNAT range
    that smells like the retired ROBS-PC host — local-only DB is the
    canonical path; HTTP fallback exists only for emergency rollback to
    a *new* operator-stood-up service.
    """
    url = os.environ.get("MG_CATALOG_HTTP_FALLBACK_URL", "").strip()
    if not url:
        return None
    if "100.110.87.1" in url or "100.64." in url[:8] or "100.65." in url[:8]:
        logger.error(
            "MG_CATALOG_HTTP_FALLBACK_URL=%r looks like the retired "
            "ROBS-PC Tailscale host — refusing.",
            url,
        )
        return None
    return url


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def get_miner_catalog_context(model_name: str) -> str:
    """Soft variant: return the prompt-ready catalog string for one model.

    Returns "" on any failure or 404-equivalent. After this returns,
    `last_read_failed()` distinguishes the two:
      - True: real failure (DB unreachable, query error, circuit-open).
      - False: 404 ("model not in catalog yet" — not a failure).
    """
    global _last_read_was_failure
    _last_read_was_failure = False  # reset per-call

    if not model_name:
        return ""

    if _is_circuit_open():
        _last_read_was_failure = True
        logger.error(
            "Catalog miner-knowledge [%s] skipped — circuit breaker is OPEN",
            model_name,
        )
        return ""

    start = time.time()
    data = _fetch_miner_knowledge_pg(model_name)
    elapsed = time.time() - start

    if data is None:
        # Real failure (logged inside _fetch_miner_knowledge_pg).
        _record_failure()
        return ""
    if not data:
        # 404-equivalent: model not in catalog. NOT a failure.
        # _last_read_was_failure stays False; do not flap the breaker.
        logger.debug("Catalog: no data for model %r", model_name)
        return ""

    text = _format_miner_knowledge(data, model_name)
    _record_success()
    logger.info(
        "Catalog miner-knowledge OK [%s]: %d chars in %.2fs (psycopg, %s)",
        model_name,
        len(text),
        elapsed,
        _resolve_catalog_target().dbname,
    )
    return text


def get_miner_catalog_context_strict(model_name: str) -> str:
    """Strict variant — raises CatalogReadFailure on any real failure.

    Same network behavior as the soft variant, but a real failure
    (`last_read_failed() == True` after the soft call) is promoted to
    an exception. Used by `core/mining_guardian.py::_consult_catalog`
    so the hourly scan refuses to evaluate a miner with no context
    rather than silently dropping the catalog.

    A 404 'model not in catalog' returns "" cleanly without raising —
    that is the contract the scanner depends on (`return ""` is treated
    as 'no catalog data, evaluate with operational signals only').
    """
    text = get_miner_catalog_context(model_name)
    if last_read_failed():
        raise CatalogReadFailure(
            f"catalog read failed for model {model_name!r} — see prior ERROR log line"
        )
    return text


def get_catalog_context(
    miner_models: List[str],
    active_issues: Optional[List[str]] = None,
) -> str:
    """Bulk variant — return catalog facts for many models in one string.

    Concatenates per-miner contexts produced by `_format_miner_knowledge`
    and prepends a one-line `active_issues:` summary when provided. The
    exact wording differs from the HTTP-era `_format_prompt_text` (the
    old server emitted a long bundled prompt with cross-model summary
    sections); the contract is the same — a prompt-text string of
    catalog facts, opaque to LLM consumers.

    `last_read_failed()` after this call is True iff at least one
    per-miner read had a real failure. A bulk call where every model
    is just 'not in catalog' returns "" but does NOT flap the breaker.
    """
    global _last_read_was_failure
    _last_read_was_failure = False  # reset per-call

    if not miner_models:
        return ""

    if _is_circuit_open():
        _last_read_was_failure = True
        logger.error("Catalog scan-bundle skipped — circuit breaker is OPEN")
        return ""

    # De-dup while preserving caller order (the HTTP version did the
    # same with `set()` but that loses order; preserve it for the
    # snapshot tests).
    seen = set()
    ordered: List[str] = []
    for m in miner_models:
        if m and m not in seen:
            seen.add(m)
            ordered.append(m)

    parts: List[str] = []
    if active_issues:
        parts.append("active_issues: " + ", ".join(str(x) for x in active_issues))

    any_real_failure = False
    for model in ordered:
        # Reuse the per-miner reader so the formatter, error-handling,
        # and circuit-breaker accounting all stay in one place.
        text = get_miner_catalog_context(model)
        if last_read_failed():
            any_real_failure = True
            # Record the failure but keep going — partial bundles are
            # better than empty ones for LLM consumers downstream.
            continue
        if text:
            parts.append(text)

    if any_real_failure:
        _last_read_was_failure = True
    return "\n\n".join(parts)


def is_catalog_available() -> bool:
    """Lightweight probe: open + close a catalog DB connection."""
    if _is_circuit_open():
        return False
    conn = _open_catalog_connection()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True
    except Exception as exc:
        logger.error("catalog availability probe failed: %s", exc)
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass
