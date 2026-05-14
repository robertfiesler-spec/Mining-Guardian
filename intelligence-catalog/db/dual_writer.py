#!/usr/bin/env python3
"""
intelligence-catalog/db/dual_writer.py — C1 dual-write intake (PR #15)

Per D-12 (Postgres-as-truth, locked 2026-04-27): every write that touches the
mining catalog goes to Postgres FIRST. The legacy unified_miner_index.json
file becomes a debug / git-tracked export only — the source of truth is
hardware.* in Postgres.

This module is the intake side of that contract. Watchers and the
catalog_updater tool call:

    propose_miner_model(slug, payload, source_tool="catalog_updater")

…which UPSERTs into staging.miner_model_proposals. A separate promotion step
(promote_validated_miner_models) reads validated proposals and copies them
into hardware.miner_models. Promotion is intentionally manual / batched so a
human can review what the watchers have proposed before they hit truth.

Design choices
--------------
1. Best-effort on the WRITE path. If Postgres is unreachable, we log and
   continue — JSON write must NOT be blocked by Postgres downtime during the
   transition period (May 5 → mid-May). Once C5 (the feedback loop) is wired,
   this fail-soft policy will be re-evaluated.
2. Staging holds RAW JSONB payloads, not normalized columns. The promotion
   function does the normalization. This means a watcher schema change does
   not require a staging schema change — only the promote function changes.
3. payload_hash + slug is unique across {pending, validated} rows. Re-writing
   the same payload is a no-op (the unique index swallows it via
   ON CONFLICT DO NOTHING). Re-writing a CHANGED payload supersedes any
   prior pending row for the same slug.
4. Connection management: this module talks to the CATALOG database
   (`mining_guardian_catalog`) — `staging.miner_model_proposals`,
   `staging.manufacturer_proposals`, `staging.alias_proposals`, and
   `hardware.miner_models` (read by the promote step) all live there.
   Connection parameters resolve through `core.db_targets.catalog_target()`
   (P-018A), which reads the catalog-side env-var family and falls back
   to `MG_DB_PASSWORD` for the password — see `core/db_targets.py` for
   the canonical list. The previous single-DB defaults
   (`PGHOST/PGPORT/PGUSER/PGDATABASE` → operational `mining_guardian`)
   silently routed every proposal to the operational stub of
   `staging.miner_model_proposals`, where they were invisible to anyone
   reading the seeded catalog. P-018B closed that gap.

   Watchers may still run in cron jobs independent of the API process —
   `core.db_targets` is dependency-free and safe to import there.

Public API
----------
  Proposal writers (UPSERT into staging.*, await a separate promote step):
    propose_miner_model(slug, payload, *, source_tool, source_url=None,
                         source_run_id=None) -> Optional[UUID]
    propose_manufacturer(brand, payload, *, source_tool, ...) -> Optional[UUID]
    propose_alias(miner_slug, alias, *, source_tool, ...) -> Optional[UUID]

  Catalog intake writers (W10 — write DIRECT to catalog tables, no staging;
  the W11 Slack /intel Approve flow is their validation gate):
    propose_firmware_release(family, version, payload, *, source_tool,
                         source_url=None) -> Optional[UUID]
    propose_firmware_compatibility(firmware_slug, miner_slug, payload, *,
                         source_tool) -> Optional[UUID]
    propose_data_conflict(conflict_table, conflict_row_id, conflict_field,
                         value_a, value_b, source_a_id, source_b_id, payload,
                         *, source_tool) -> Optional[UUID]
    record_freshness_check(tracked_table, tracked_row_id, found_new, payload,
                         *, source_tool) -> Optional[UUID]

    promote_validated_miner_models() -> int  # returns count promoted
    list_pending_proposals(limit=50) -> list[dict]
    is_postgres_available() -> bool

CLI
---
    python -m intelligence_catalog.db.dual_writer --status
    python -m intelligence_catalog.db.dual_writer --list-pending
    python -m intelligence_catalog.db.dual_writer --promote-validated
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from typing import Any, Optional
from uuid import UUID

LOG = logging.getLogger("dual_writer")


# ──────────────────────────────────────────────────────────────────────────
# Connection helpers
# ──────────────────────────────────────────────────────────────────────────

# Register Python UUID <-> Postgres uuid adapter exactly once. Without this,
# psycopg2 cannot adapt a uuid.UUID object as a parameter and every propose_*
# call that passes source_run_id fails with "can't adapt type 'UUID'".
# Patched in PR #16 after the C3 watcher exposed the gap during sandbox runs.
_UUID_ADAPTER_REGISTERED = False


def _ensure_uuid_adapter() -> None:
    global _UUID_ADAPTER_REGISTERED
    if _UUID_ADAPTER_REGISTERED:
        return
    try:
        import psycopg2.extras  # type: ignore
        psycopg2.extras.register_uuid()
        _UUID_ADAPTER_REGISTERED = True
    except Exception as exc:  # pragma: no cover
        LOG.warning("could not register UUID adapter: %s", exc)


def _resolve_catalog_target():
    """Resolve the catalog DB connection target via core.db_targets.

    The intelligence-catalog dir lives next to (not inside) the `core`
    package, so we tolerate the case where `intelligence-catalog/` is on
    sys.path but the repo root is not — add the repo root once if needed
    so `from core.db_targets import catalog_target` resolves. This keeps
    the module importable from cron watchers that set their own cwd.
    """
    try:
        from core.db_targets import catalog_target
    except ImportError:
        import sys
        from pathlib import Path
        repo_root = Path(__file__).resolve().parents[2]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from core.db_targets import catalog_target  # type: ignore[no-redef]
    return catalog_target()


def _get_connection():
    """Open a Postgres connection to the CATALOG DB. Returns None on any
    failure — the caller logs and degrades gracefully.

    P-018B: dbname is sourced from `GUARDIAN_PG_CATALOG_DBNAME` (default
    `mining_guardian_catalog`) via `core.db_targets.catalog_target()`,
    not `PGDATABASE` (which on the Mini points at the operational DB).
    """
    try:
        import psycopg2  # type: ignore
        from psycopg2.extras import Json  # noqa: F401  (re-exported below)
    except ImportError:
        LOG.warning("psycopg2 not installed; dual-write disabled.")
        return None

    _ensure_uuid_adapter()

    target = _resolve_catalog_target()
    if not target.password:
        # Match the previous explicit-pw guard so a missing env yields the
        # same fail-soft "dual-write disabled" path callers already handle.
        LOG.warning(
            "no DB password set (GUARDIAN_PG_PASSWORD / MG_DB_PASSWORD); "
            "dual-write disabled."
        )
        return None

    try:
        return psycopg2.connect(connect_timeout=5, **target.connect_kwargs())
    except Exception as exc:
        LOG.warning("Postgres unreachable: %s; dual-write disabled.", exc)
        return None


def is_postgres_available() -> bool:
    """Lightweight liveness check — open and immediately close a connection."""
    conn = _get_connection()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True
    except Exception as exc:
        LOG.warning("Postgres reachability probe failed: %s", exc)
        return False
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────────
# Payload hashing
# ──────────────────────────────────────────────────────────────────────────

def _payload_hash(payload: dict) -> str:
    """Stable SHA-256 hash of a dict. Used to dedup identical proposals."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ──────────────────────────────────────────────────────────────────────────
# Proposal writers (UPSERT into staging.*)
# ──────────────────────────────────────────────────────────────────────────

def propose_miner_model(
    slug: str,
    payload: dict,
    *,
    source_tool: str,
    source_url: Optional[str] = None,
    source_run_id: Optional[UUID] = None,
) -> Optional[UUID]:
    """Write (or no-op if duplicate) a proposal into staging.miner_model_proposals.

    Returns the proposal UUID, or None if the write was skipped (postgres down,
    duplicate hash, etc.). A None return is NOT a failure — JSON path proceeds.
    """
    if not slug:
        raise ValueError("propose_miner_model: slug is required")
    if not isinstance(payload, dict):
        raise ValueError("propose_miner_model: payload must be a dict")
    if not source_tool:
        raise ValueError("propose_miner_model: source_tool is required")

    conn = _get_connection()
    if conn is None:
        return None

    h = _payload_hash(payload)

    try:
        from psycopg2.extras import Json
        with conn, conn.cursor() as cur:
            # Supersede any prior pending/validated row for this slug+different hash
            cur.execute(
                """
                UPDATE staging.miner_model_proposals
                SET status = 'superseded', updated_at = NOW()
                WHERE slug = %s
                  AND status IN ('pending', 'validated')
                  AND payload_hash <> %s
                """,
                (slug, h),
            )
            # Insert; unique index on (slug, payload_hash) WHERE status IN
            # ('pending','validated') makes identical re-writes a no-op.
            cur.execute(
                """
                INSERT INTO staging.miner_model_proposals
                    (slug, payload, source_tool, source_url, source_run_id, payload_hash)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (slug, payload_hash)
                  WHERE status IN ('pending', 'validated')
                  DO NOTHING
                RETURNING id
                """,
                (slug, Json(payload), source_tool, source_url, source_run_id, h),
            )
            row = cur.fetchone()
            return row[0] if row else None
    except Exception as exc:
        LOG.warning("propose_miner_model(%s) failed: %s", slug, exc)
        return None
    finally:
        conn.close()


def propose_manufacturer(
    brand: str,
    payload: dict,
    *,
    source_tool: str,
    source_url: Optional[str] = None,
    source_run_id: Optional[UUID] = None,
) -> Optional[UUID]:
    """Write a proposal into staging.manufacturer_proposals."""
    if not brand:
        raise ValueError("propose_manufacturer: brand is required")
    conn = _get_connection()
    if conn is None:
        return None

    h = _payload_hash(payload)
    try:
        from psycopg2.extras import Json
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE staging.manufacturer_proposals
                SET status = 'superseded', updated_at = NOW()
                WHERE brand = %s
                  AND status IN ('pending', 'validated')
                  AND payload_hash <> %s
                """,
                (brand, h),
            )
            cur.execute(
                """
                INSERT INTO staging.manufacturer_proposals
                    (brand, payload, source_tool, source_url, source_run_id, payload_hash)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (brand, payload_hash)
                  WHERE status IN ('pending', 'validated')
                  DO NOTHING
                RETURNING id
                """,
                (brand, Json(payload), source_tool, source_url, source_run_id, h),
            )
            row = cur.fetchone()
            return row[0] if row else None
    except Exception as exc:
        LOG.warning("propose_manufacturer(%s) failed: %s", brand, exc)
        return None
    finally:
        conn.close()


def propose_alias(
    miner_slug: str,
    alias: str,
    *,
    source_tool: str,
    alias_source: str = "unknown",
    is_common: bool = False,
    notes: Optional[str] = None,
    source_url: Optional[str] = None,
    source_run_id: Optional[UUID] = None,
) -> Optional[UUID]:
    """Write a proposal into staging.alias_proposals."""
    if not miner_slug or not alias:
        raise ValueError("propose_alias: miner_slug and alias are required")
    conn = _get_connection()
    if conn is None:
        return None
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO staging.alias_proposals
                    (miner_slug, alias, alias_source, is_common, notes,
                     source_tool, source_url, source_run_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (miner_slug, alias)
                  WHERE status IN ('pending', 'validated')
                  DO NOTHING
                RETURNING id
                """,
                (miner_slug, alias, alias_source, is_common, notes,
                 source_tool, source_url, source_run_id),
            )
            row = cur.fetchone()
            return row[0] if row else None
    except Exception as exc:
        LOG.warning("propose_alias(%s, %s) failed: %s", miner_slug, alias, exc)
        return None
    finally:
        conn.close()



# ──────────────────────────────────────────────────────────────────────────
# Catalog intake writers (DIRECT to catalog tables — NOT staging.*)
# ──────────────────────────────────────────────────────────────────────────
#
# W10 (see docs/strategy/04_MASTER_EXECUTION_PLAN.md §W10). Unlike the
# propose_* functions above — which land in staging.* and wait for a separate
# promote step — these four write DIRECTLY into their catalog tables. There is
# no staging.firmware_proposals / staging.conflict_proposals etc.; the repo's
# staging schema has exactly three proposal tables (miner_model, manufacturer,
# alias) and no others.
#
# The validation gate for these is the W11 Slack /intel Approve flow: the
# operator reviews each finding in Slack and Approve flips bobby_verified=TRUE
# on the row that was written here. So the contract is "write the row now,
# operator blesses it in Slack" — not "stage now, promote later".
#
# What they DO keep from the propose_* pattern:
#   * fail-soft — Postgres unreachable → log + return None, never raise
#   * ValueError on missing/invalid REQUIRED arguments (caller bug, not a
#     runtime condition — surfaced loudly, same as propose_miner_model)
#   * with conn, conn.cursor() as cur:  (transaction per call)
#   * conn.close() in finally
#
# A None return is NOT a failure — it means the write was skipped (Postgres
# down, duplicate, or an unresolved foreign key). Callers treat None as
# "nothing landed, move on", exactly as they do for the propose_* functions.


# Valid values of the public.firmware_family enum, mirrored here so
# propose_firmware_release can reject a bad family with a clear ValueError
# BEFORE opening a connection — rather than letting Postgres raise an opaque
# "invalid input value for enum" mid-transaction. Keep in sync with
# intelligence-catalog/seed-data/intelligence_catalog_schema.sql (CREATE TYPE
# public.firmware_family). The cohort guard test asserts this stays in sync.
_FIRMWARE_FAMILIES = frozenset({
    "stock_bitmain", "stock_microbt", "stock_auradine", "stock_canaan",
    "bixbit", "braiins_os", "vnish", "luxos", "epic", "auradine_native",
    "hiveon", "other", "unknown",
})


def propose_firmware_release(
    family: str,
    version: str,
    payload: dict,
    *,
    source_tool: str,
    source_url: Optional[str] = None,
) -> Optional[UUID]:
    """UPSERT a firmware release into firmware.firmware_releases.

    The table's natural key is UNIQUE (firmware_family, version_string), so a
    re-write of the same family+version updates the existing row rather than
    duplicating it. This makes the function idempotent: the W11 /intel handler
    can re-send the same finding (operator pastes the same morning chat twice)
    without creating duplicate releases.

    Required args:
        family       — one of public.firmware_family (see _FIRMWARE_FAMILIES).
                       Rejected with ValueError if not a known family.
        version      — the version_string, e.g. "1.11.0.30", "24.09".
        payload      — dict of optional columns to set. Recognized keys:
                       display_name, developer_name, developer_url,
                       download_url, release_notes_url, release_date,
                       is_current_stable, is_beta, notes. Unknown keys are
                       ignored (kept out of the row, not stuffed into metadata
                       — metadata stays caller-controlled via the 'metadata'
                       key if present).
        source_tool  — provenance, e.g. 'firmware_tracker_perplexity'.

    Returns the row UUID (insert or update), or None on fail-soft skip.
    """
    if not family:
        raise ValueError("propose_firmware_release: family is required")
    if family not in _FIRMWARE_FAMILIES:
        raise ValueError(
            f"propose_firmware_release: family '{family}' is not a known "
            f"public.firmware_family value ({sorted(_FIRMWARE_FAMILIES)})"
        )
    if not version:
        raise ValueError("propose_firmware_release: version is required")
    if not isinstance(payload, dict):
        raise ValueError("propose_firmware_release: payload must be a dict")
    if not source_tool:
        raise ValueError("propose_firmware_release: source_tool is required")

    conn = _get_connection()
    if conn is None:
        return None

    # display_name is NOT NULL on the table; default it from family+version
    # when the caller did not supply one.
    display_name = payload.get("display_name") or f"{family} {version}"

    try:
        from psycopg2.extras import Json
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO firmware.firmware_releases
                    (firmware_family, version_string, display_name,
                     developer_name, developer_url, download_url,
                     release_notes_url, release_date,
                     is_current_stable, is_beta, notes,
                     primary_source_id, metadata)
                VALUES
                    (%s, %s, %s,
                     %s, %s, %s,
                     %s, %s,
                     %s, %s, %s,
                     %s, %s)
                ON CONFLICT (firmware_family, version_string) DO UPDATE SET
                    display_name      = EXCLUDED.display_name,
                    developer_name    = COALESCE(EXCLUDED.developer_name,
                                                 firmware_releases.developer_name),
                    developer_url     = COALESCE(EXCLUDED.developer_url,
                                                 firmware_releases.developer_url),
                    download_url      = COALESCE(EXCLUDED.download_url,
                                                 firmware_releases.download_url),
                    release_notes_url = COALESCE(EXCLUDED.release_notes_url,
                                                 firmware_releases.release_notes_url),
                    release_date      = COALESCE(EXCLUDED.release_date,
                                                 firmware_releases.release_date),
                    notes             = COALESCE(EXCLUDED.notes,
                                                 firmware_releases.notes),
                    updated_at        = NOW()
                RETURNING id
                """,
                (
                    family, version, display_name,
                    payload.get("developer_name"), payload.get("developer_url"),
                    payload.get("download_url"),
                    payload.get("release_notes_url"), payload.get("release_date"),
                    bool(payload.get("is_current_stable", False)),
                    bool(payload.get("is_beta", False)),
                    payload.get("notes"),
                    payload.get("primary_source_id"),
                    Json(payload.get("metadata", {})),
                ),
            )
            row = cur.fetchone()
            return row[0] if row else None
    except Exception as exc:
        LOG.warning("propose_firmware_release(%s, %s) failed: %s",
                    family, version, exc)
        return None
    finally:
        conn.close()


def propose_firmware_compatibility(
    firmware_slug: str,
    miner_slug: str,
    payload: dict,
    *,
    source_tool: str,
) -> Optional[UUID]:
    """UPSERT a firmware×hardware compatibility row into
    firmware.firmware_compatibility.

    The table keys on UUIDs (firmware_id, miner_model_id), but the W11 intake
    path supplies human strings. This function resolves:
        firmware_slug → firmware.firmware_releases.version_string
        miner_slug    → hardware.miner_models.canonical_name

    Resolution policy (W10 decision 1a — fail-soft skip with a logged reason):
    if EITHER side does not resolve, the function logs which side failed and
    returns None WITHOUT writing. This is not an error — a compatibility fact
    simply cannot be expressed until both the firmware release and the miner
    model exist in the catalog. The W11 handler treats None as "couldn't land
    this finding yet" and surfaces it to the operator, who can propose the
    missing firmware release first, then re-send.

    The natural key UNIQUE (firmware_id, miner_model_id) makes the write
    idempotent once both sides resolve.

    Required args:
        firmware_slug — version_string of an existing firmware release.
        miner_slug    — canonical_name of an existing miner model.
        payload       — dict of optional columns. Recognized keys:
                        is_compatible, is_officially_supported,
                        typical_hashrate_th, typical_power_w,
                        max_achievable_th, max_achievable_w, efficiency_j_th,
                        install_difficulty, notes, metadata.
        source_tool   — provenance.

    Returns the row UUID, or None on fail-soft skip (Postgres down OR an
    unresolved slug on either side).
    """
    if not firmware_slug:
        raise ValueError(
            "propose_firmware_compatibility: firmware_slug is required")
    if not miner_slug:
        raise ValueError(
            "propose_firmware_compatibility: miner_slug is required")
    if not isinstance(payload, dict):
        raise ValueError(
            "propose_firmware_compatibility: payload must be a dict")
    if not source_tool:
        raise ValueError(
            "propose_firmware_compatibility: source_tool is required")

    conn = _get_connection()
    if conn is None:
        return None

    try:
        from psycopg2.extras import Json
        with conn, conn.cursor() as cur:
            # Resolve firmware_slug → firmware_releases.id
            cur.execute(
                "SELECT id FROM firmware.firmware_releases "
                "WHERE version_string = %s",
                (firmware_slug,),
            )
            fw_row = cur.fetchone()
            if not fw_row:
                LOG.warning(
                    "propose_firmware_compatibility: firmware_slug '%s' did "
                    "not resolve to a firmware.firmware_releases row — "
                    "skipping (propose the firmware release first)",
                    firmware_slug,
                )
                return None
            firmware_id = fw_row[0]

            # Resolve miner_slug → miner_models.id
            cur.execute(
                "SELECT id FROM hardware.miner_models "
                "WHERE canonical_name = %s",
                (miner_slug,),
            )
            mm_row = cur.fetchone()
            if not mm_row:
                LOG.warning(
                    "propose_firmware_compatibility: miner_slug '%s' did not "
                    "resolve to a hardware.miner_models row — skipping "
                    "(propose/promote the miner model first)",
                    miner_slug,
                )
                return None
            miner_model_id = mm_row[0]

            cur.execute(
                """
                INSERT INTO firmware.firmware_compatibility
                    (firmware_id, miner_model_id,
                     is_compatible, is_officially_supported,
                     typical_hashrate_th, typical_power_w,
                     max_achievable_th, max_achievable_w, efficiency_j_th,
                     install_difficulty, notes,
                     primary_source_id, metadata)
                VALUES
                    (%s, %s,
                     %s, %s,
                     %s, %s,
                     %s, %s, %s,
                     %s, %s,
                     %s, %s)
                ON CONFLICT (firmware_id, miner_model_id) DO UPDATE SET
                    is_compatible           = EXCLUDED.is_compatible,
                    is_officially_supported = EXCLUDED.is_officially_supported,
                    typical_hashrate_th     = COALESCE(EXCLUDED.typical_hashrate_th,
                                                       firmware_compatibility.typical_hashrate_th),
                    typical_power_w         = COALESCE(EXCLUDED.typical_power_w,
                                                       firmware_compatibility.typical_power_w),
                    max_achievable_th       = COALESCE(EXCLUDED.max_achievable_th,
                                                       firmware_compatibility.max_achievable_th),
                    max_achievable_w        = COALESCE(EXCLUDED.max_achievable_w,
                                                       firmware_compatibility.max_achievable_w),
                    efficiency_j_th         = COALESCE(EXCLUDED.efficiency_j_th,
                                                       firmware_compatibility.efficiency_j_th),
                    install_difficulty      = COALESCE(EXCLUDED.install_difficulty,
                                                       firmware_compatibility.install_difficulty),
                    notes                   = COALESCE(EXCLUDED.notes,
                                                       firmware_compatibility.notes),
                    updated_at              = NOW()
                RETURNING id
                """,
                (
                    firmware_id, miner_model_id,
                    bool(payload.get("is_compatible", True)),
                    bool(payload.get("is_officially_supported", False)),
                    payload.get("typical_hashrate_th"),
                    payload.get("typical_power_w"),
                    payload.get("max_achievable_th"),
                    payload.get("max_achievable_w"),
                    payload.get("efficiency_j_th"),
                    payload.get("install_difficulty", "easy"),
                    payload.get("notes"),
                    payload.get("primary_source_id"),
                    Json(payload.get("metadata", {})),
                ),
            )
            row = cur.fetchone()
            return row[0] if row else None
    except Exception as exc:
        LOG.warning("propose_firmware_compatibility(%s, %s) failed: %s",
                    firmware_slug, miner_slug, exc)
        return None
    finally:
        conn.close()


def propose_data_conflict(
    conflict_table: str,
    conflict_row_id: UUID,
    conflict_field: str,
    value_a: Any,
    value_b: Any,
    source_a_id: UUID,
    source_b_id: UUID,
    payload: dict,
    *,
    source_tool: str,
) -> Optional[UUID]:
    """Record a source-disagreement into knowledge.data_conflicts.

    Example: Bitmain's page says S19j Pro = 104 TH/s, a community source says
    96 TH/s. Both values are kept; the row tracks that they disagree and (once
    resolved) which won.

    Dedup (W10 decision 2b — in-function check, correct WITHOUT a DB index):
    knowledge.data_conflicts has no natural UNIQUE constraint. Before
    inserting, this function checks for an existing UNRESOLVED conflict on the
    same (conflict_table, conflict_row_id, conflict_field) triple and returns
    that row's id instead of inserting a duplicate. This makes the function
    idempotent for the common case (operator re-pastes the same morning chat)
    WITHOUT requiring a schema migration.

    NOTE: a follow-up migration may add a partial UNIQUE index on
    (conflict_table, conflict_row_id, conflict_field) WHERE NOT is_resolved as
    a DB-enforced backstop (W10 decision 2 — see EXECUTION_PLAN_STATUS.md).
    This function is written to be correct EITHER WAY: with the index it is
    belt-and-suspenders; without it the in-function check still holds. The
    index location question (catalog migrations have no settled home in the
    repo yet) is the one open item — the function itself is not blocked on it.

    Required args:
        conflict_table   — the catalog table the disputed value lives in,
                           e.g. 'hardware.miner_models'.
        conflict_row_id  — UUID of the disputed row.
        conflict_field   — the column name in dispute, e.g. 'stock_hashrate_th'.
        value_a, value_b — the competing values. Stored as JSONB; pass a dict
                           like {"raw": "104", "unit": "TH/s"} or a scalar.
        source_a_id      — UUID FK → knowledge.sources, the source of value_a.
        source_b_id      — UUID FK → knowledge.sources, the source of value_b.
        payload          — dict of optional columns. Recognized keys:
                           resolution_strategy (default 'manual_review'),
                           severity (default 'low'), resolution_notes,
                           metadata.
        source_tool      — provenance.

    Returns the row UUID (new, or the existing unresolved one), or None on
    fail-soft skip.
    """
    if not conflict_table:
        raise ValueError("propose_data_conflict: conflict_table is required")
    if not conflict_row_id:
        raise ValueError("propose_data_conflict: conflict_row_id is required")
    if not conflict_field:
        raise ValueError("propose_data_conflict: conflict_field is required")
    if not source_a_id or not source_b_id:
        raise ValueError(
            "propose_data_conflict: source_a_id and source_b_id are required")
    if not isinstance(payload, dict):
        raise ValueError("propose_data_conflict: payload must be a dict")
    if not source_tool:
        raise ValueError("propose_data_conflict: source_tool is required")

    conn = _get_connection()
    if conn is None:
        return None

    try:
        from psycopg2.extras import Json
        with conn, conn.cursor() as cur:
            # Dedup: an unresolved conflict on the same triple already exists?
            # Return it instead of inserting a duplicate.
            cur.execute(
                """
                SELECT id FROM knowledge.data_conflicts
                WHERE conflict_table = %s
                  AND conflict_row_id = %s
                  AND conflict_field = %s
                  AND is_resolved = FALSE
                ORDER BY created_at
                LIMIT 1
                """,
                (conflict_table, str(conflict_row_id), conflict_field),
            )
            existing = cur.fetchone()
            if existing:
                LOG.info(
                    "propose_data_conflict: unresolved conflict already "
                    "exists for %s.%s row=%s — returning existing id",
                    conflict_table, conflict_field, conflict_row_id,
                )
                return existing[0]

            cur.execute(
                """
                INSERT INTO knowledge.data_conflicts
                    (conflict_table, conflict_row_id, conflict_field,
                     value_a, value_b, source_a_id, source_b_id,
                     resolution_strategy, severity, resolution_notes,
                     metadata)
                VALUES
                    (%s, %s, %s,
                     %s, %s, %s, %s,
                     %s, %s, %s,
                     %s)
                RETURNING id
                """,
                (
                    conflict_table, str(conflict_row_id), conflict_field,
                    Json(value_a), Json(value_b), source_a_id, source_b_id,
                    payload.get("resolution_strategy", "manual_review"),
                    payload.get("severity", "low"),
                    payload.get("resolution_notes"),
                    Json(payload.get("metadata", {})),
                ),
            )
            row = cur.fetchone()
            return row[0] if row else None
    except Exception as exc:
        LOG.warning("propose_data_conflict(%s.%s) failed: %s",
                    conflict_table, conflict_field, exc)
        return None
    finally:
        conn.close()


def record_freshness_check(
    tracked_table: str,
    tracked_row_id: UUID,
    found_new: bool,
    payload: dict,
    *,
    source_tool: str,
) -> Optional[UUID]:
    """APPEND a freshness observation into knowledge.freshness_log.

    This is the "nothing new today" recorder — the most common W11 /intel
    finding shape. When a Perplexity watcher runs and reports no change, that
    "I checked and it's still current" IS catalog data: it advances the
    last_verified_at clock for the tracked row.

    APPEND, not UPSERT (W10 — knowledge.freshness_log is one of the catalog's
    intentionally append-only event-log tables; see W26 in the catalog design
    plan). Every watcher run is a genuinely new row — the log's value is the
    full history of when something was checked, so there is no dedup and no
    ON CONFLICT. Two checks of the same row on the same day are two real
    events and both belong in the log.

    Required args:
        tracked_table  — the catalog table whose freshness is being recorded,
                         e.g. 'hardware.miner_models'.
        tracked_row_id — UUID of the row that was verified.
        found_new      — did the watcher find a change? False is the common
                         case ("checked, still current"). The boolean is
                         folded into metadata. Note this function does NOT
                         touch is_stale on the tracked row — staleness is a
                         derived/queried property, not something one check
                         flips. record_freshness_check only records the
                         observation event.
        payload        — dict of optional columns. Recognized keys:
                         tracked_field (NULL = whole row), verification_method
                         (e.g. 'api_pull', 'manual_check'), next_verify_due,
                         verified_by (UUID FK → knowledge.contributors),
                         metadata.
        source_tool    — provenance, e.g. 'firmware_tracker_perplexity'.

    Returns the new row UUID, or None on fail-soft skip.
    """
    if not tracked_table:
        raise ValueError("record_freshness_check: tracked_table is required")
    if not tracked_row_id:
        raise ValueError("record_freshness_check: tracked_row_id is required")
    if not isinstance(payload, dict):
        raise ValueError("record_freshness_check: payload must be a dict")
    if not source_tool:
        raise ValueError("record_freshness_check: source_tool is required")

    conn = _get_connection()
    if conn is None:
        return None

    # The found_new boolean and the source_tool provenance are not first-class
    # columns on knowledge.freshness_log — fold them into metadata alongside
    # any caller-supplied metadata so nothing is lost.
    meta = dict(payload.get("metadata", {}))
    meta.setdefault("found_new", bool(found_new))
    meta.setdefault("source_tool", source_tool)

    try:
        from psycopg2.extras import Json
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO knowledge.freshness_log
                    (tracked_table, tracked_row_id, tracked_field,
                     last_verified_at, verified_by, verification_method,
                     next_verify_due, metadata)
                VALUES
                    (%s, %s, %s,
                     NOW(), %s, %s,
                     %s, %s)
                RETURNING id
                """,
                (
                    tracked_table, str(tracked_row_id),
                    payload.get("tracked_field"),
                    payload.get("verified_by"),
                    payload.get("verification_method"),
                    payload.get("next_verify_due"),
                    Json(meta),
                ),
            )
            row = cur.fetchone()
            return row[0] if row else None
    except Exception as exc:
        LOG.warning("record_freshness_check(%s) failed: %s",
                    tracked_table, exc)
        return None
    finally:
        conn.close()

# ──────────────────────────────────────────────────────────────────────────
# Read helpers
# ──────────────────────────────────────────────────────────────────────────

def list_pending_proposals(limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent pending/validated proposals across all 3 tables."""
    conn = _get_connection()
    if conn is None:
        return []
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "SELECT proposal_type, id, key, source_tool, status, created_at "
                "FROM staging.pending_proposals LIMIT %s",
                (limit,),
            )
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as exc:
        LOG.warning("list_pending_proposals failed: %s", exc)
        return []
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────────
# Promotion (staging → hardware.*)
# ──────────────────────────────────────────────────────────────────────────
#
# Promotion is intentionally a separate step from the WRITE path. The contract
# is: watchers / catalog_updater write *proposals*; a human (or a future C5
# automated validator) flips status to 'validated'; this function then promotes
# validated proposals into hardware.miner_models / hardware.manufacturers /
# hardware.model_aliases.
#
# For PR #15 the promotion logic for miner_models is implemented as a careful
# UPSERT keyed on canonical_name. Manufacturers and aliases promotion will land
# alongside PR #16 (the manufacturer watcher) since that's where they get
# exercised. The function structure is in place here so PR #16 can fill them.

def promote_validated_miner_models(dry_run: bool = False) -> int:
    """Promote staging.miner_model_proposals where status='validated' into
    hardware.miner_models. Returns the count promoted.

    The proposal payload is expected to look like the unified_miner_index.json
    entry shape:

        {
          "manufacturer": "bitmain",
          "display_name": "Antminer S21 Pro",
          "specs": {
              "stock_hashrate_th": 234,
              "stock_power_w": 3531,
              ...
          },
          ...
        }

    Promotion logic:
      1. Look up manufacturer_id by brand string in hardware.manufacturers.
         If brand is not in the enum / table, mark the proposal 'rejected'
         with a clear note and skip. (The manufacturer must be promoted
         FIRST — that's what PR #16 wires up.)
      2. UPSERT into hardware.miner_models using canonical_name as the key.
         (canonical_name has no UNIQUE today — the seed used model_number;
         we add a partial UNIQUE on canonical_name in the staging schema
         once the watcher track stabilizes. For now, we INSERT only if no
         row exists with the same canonical_name; otherwise UPDATE.)
      3. Stamp the proposal as 'promoted', set promoted_to_id and promoted_at.
    """
    conn = _get_connection()
    if conn is None:
        return 0

    promoted = 0
    rejected = 0
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, slug, payload
                FROM staging.miner_model_proposals
                WHERE status = 'validated'
                ORDER BY created_at
                """
            )
            rows = cur.fetchall()

            for prop_id, slug, payload in rows:
                # Resolve manufacturer
                brand = (payload or {}).get("manufacturer")
                if not brand:
                    cur.execute(
                        "UPDATE staging.miner_model_proposals "
                        "SET status='rejected', validation_notes=%s "
                        "WHERE id=%s",
                        ("payload missing 'manufacturer' field", prop_id),
                    )
                    rejected += 1
                    continue

                cur.execute(
                    "SELECT id FROM hardware.manufacturers WHERE brand = %s::manufacturer_brand",
                    (brand,),
                )
                m = cur.fetchone()
                if not m:
                    cur.execute(
                        "UPDATE staging.miner_model_proposals "
                        "SET status='rejected', validation_notes=%s "
                        "WHERE id=%s",
                        (f"manufacturer brand '{brand}' not in hardware.manufacturers; "
                         f"promote that first", prop_id),
                    )
                    rejected += 1
                    continue
                manufacturer_id = m[0]

                # Pull spec fields with safe defaults
                specs = payload.get("specs", {}) or {}
                canonical_name = payload.get("display_name") or payload.get("name") or slug
                cooling_type = (specs.get("cooling_type")
                                or payload.get("cooling_type") or "air")
                hashboard_count = specs.get("hashboard_count") or 3
                stock_hashrate = (specs.get("stock_hashrate_th")
                                  or specs.get("hashrate_ths")
                                  or specs.get("hashrate_th"))
                stock_power = specs.get("stock_power_w") or specs.get("power_w")

                if stock_hashrate is None:
                    cur.execute(
                        "UPDATE staging.miner_model_proposals "
                        "SET status='rejected', validation_notes=%s "
                        "WHERE id=%s",
                        ("payload missing stock_hashrate_th / hashrate_ths / hashrate_th",
                         prop_id),
                    )
                    rejected += 1
                    continue

                if dry_run:
                    LOG.info("[dry-run] would promote slug=%s brand=%s name=%s",
                             slug, brand, canonical_name)
                    continue

                # UPSERT keyed on canonical_name
                cur.execute(
                    "SELECT id FROM hardware.miner_models WHERE canonical_name = %s",
                    (canonical_name,),
                )
                existing = cur.fetchone()

                if existing:
                    target_id = existing[0]
                    cur.execute(
                        """
                        UPDATE hardware.miner_models
                        SET stock_hashrate_th = COALESCE(%s, stock_hashrate_th),
                            stock_power_w     = COALESCE(%s, stock_power_w),
                            hashboard_count   = COALESCE(%s, hashboard_count),
                            cooling_type      = COALESCE(%s::cooling_type, cooling_type),
                            updated_at        = NOW()
                        WHERE id = %s
                        """,
                        (stock_hashrate, stock_power, hashboard_count,
                         cooling_type, target_id),
                    )
                else:
                    # Resolve a primary_source_id (NOT NULL on hardware.miner_models).
                    # Prefer 'catalog_research_2026' for tool-driven proposals; if that
                    # row does not exist (test DBs without the seed) fall back to the
                    # first source registered.
                    cur.execute(
                        "SELECT id FROM knowledge.sources "
                        "WHERE source_key='catalog_research_2026' "
                        "UNION ALL SELECT id FROM knowledge.sources LIMIT 1"
                    )
                    src_row = cur.fetchone()
                    primary_source_id = src_row[0] if src_row else None

                    cur.execute(
                        """
                        INSERT INTO hardware.miner_models
                            (manufacturer_id, canonical_name, cooling_type,
                             hashboard_count, stock_hashrate_th, stock_power_w,
                             primary_source_id)
                        VALUES (%s, %s, %s::cooling_type, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (manufacturer_id, canonical_name, cooling_type,
                         hashboard_count, stock_hashrate, stock_power,
                         primary_source_id),
                    )
                    target_id = cur.fetchone()[0]

                cur.execute(
                    "UPDATE staging.miner_model_proposals "
                    "SET status='promoted', promoted_at=NOW(), promoted_to_id=%s "
                    "WHERE id=%s",
                    (target_id, prop_id),
                )
                promoted += 1

        LOG.info("promote_validated_miner_models: promoted=%d rejected=%d", promoted, rejected)
        return promoted
    except Exception as exc:
        LOG.error("promote_validated_miner_models failed: %s", exc)
        return promoted
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mining-Guardian dual-write intake (C1 / D-12)",
    )
    parser.add_argument("--status", action="store_true",
                        help="Show whether Postgres is reachable")
    parser.add_argument("--list-pending", action="store_true",
                        help="List the first 50 pending/validated proposals")
    parser.add_argument("--promote-validated", action="store_true",
                        help="Promote validated miner_model proposals into "
                             "hardware.miner_models")
    parser.add_argument("--dry-run", action="store_true",
                        help="With --promote-validated, print but do not write")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose logging")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    did_anything = False

    if args.status:
        ok = is_postgres_available()
        print(f"Postgres reachable: {ok}")
        did_anything = True

    if args.list_pending:
        for row in list_pending_proposals():
            print(json.dumps(row, default=str, sort_keys=True))
        did_anything = True

    if args.promote_validated:
        n = promote_validated_miner_models(dry_run=args.dry_run)
        print(f"Promoted {n} miner_model proposals")
        did_anything = True

    if not did_anything:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
