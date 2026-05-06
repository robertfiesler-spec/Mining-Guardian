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
   (P-018A), which reads `GUARDIAN_PG_HOST/_PORT/_USER/_PASSWORD/
   _CATALOG_DBNAME` and falls back to `MG_DB_PASSWORD`. The previous
   single-DB defaults (`PGHOST/PGPORT/PGUSER/PGDATABASE` → operational
   `mining_guardian`) silently routed every proposal to the operational
   stub of `staging.miner_model_proposals`, where they were invisible
   to anyone reading the seeded catalog. P-018B closed that gap.

   Watchers may still run in cron jobs independent of the API process —
   `core.db_targets` is dependency-free and safe to import there.

Public API
----------
    propose_miner_model(slug, payload, *, source_tool, source_url=None,
                         source_run_id=None) -> Optional[UUID]
    propose_manufacturer(brand, payload, *, source_tool, ...) -> Optional[UUID]
    propose_alias(miner_slug, alias, *, source_tool, ...) -> Optional[UUID]

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
