#!/usr/bin/env python3
"""
intelligence-catalog/db/feedback_loop.py — C5 operational→catalog feedback (PR #22)

Per UNIFIED §4.4 and ROADMAP §Wed: the AI's day-to-day operational ledger
(`public.action_audit_log`, `public.miner_restarts`, `public.llm_analysis`)
must feed back into the catalog so the catalog learns from real fleet
behaviour rather than only factory-spec scrapes. Without this loop the
catalog is read-only fact data and the AI's outcomes never inform future
decisions.

This module is the *aggregation* side of that contract. It reads from the
operational tables (live in `public.*` in DB `mining_guardian` after
migration 001) and *upserts* into the catalog tables (live in DB
`mining_guardian_catalog`):

    public.action_audit_log     →  ops.failure_patterns
    public.llm_analysis         →  market.war_stories
    public.miner_restarts       →  hardware.model_known_issues

P-018C two-connection split: each sync function opens an operational
connection (read-only) AND a catalog connection (model_id lookup +
UPSERT). The catalog write commits independently of the operational
read. Public signatures take `*, op_conn=None, cat_conn=None,
dry_run=False`; both connections are opened internally if not supplied.

Writes are idempotent — running this hourly (or daily) is safe. Each target
row is keyed on a deterministic `pattern_code` / metadata key so subsequent
runs UPDATE rather than INSERT.

Design choices
--------------
1. Best-effort and fail-soft: if a source table is missing (migration not
   yet applied), the corresponding mapping is skipped with a log line. The
   feedback loop never crashes the calling cron.
2. Aggregation runs at SQL level — no row-by-row Python loop over the
   operational tables. This keeps the loop cheap on a fleet that produces
   ~1k audit rows per day.
3. Source attribution: every row written by this module sets
   `primary_source_id` to `bobby_operational` (the tier2 operational
   source seeded with id `a0000000-0000-0000-0000-00000000000f`). That
   makes catalog provenance auditable — a human can grep `WHERE
   primary_source_id = bobby_operational` to see exactly what the
   feedback loop has produced.
4. Model resolution: the operational tables store `model` as free text
   (e.g. "Antminer S19 Pro"). We resolve to `hardware.miner_models.id`
   via canonical_name match; rows with no match are tagged on the
   pattern as model-agnostic (`is_model_specific=false`,
   `primary_model_id=NULL`).

Public API
----------
    sync_action_audit_to_failure_patterns(*, dry_run=False) -> dict
    sync_llm_analysis_to_war_stories(*, dry_run=False) -> dict
    sync_miner_restarts_to_known_issues(*, dry_run=False) -> dict
    run_full_feedback_loop(*, dry_run=False) -> dict

Each returns a stats dict: {rows_read, rows_written, rows_updated,
rows_skipped, error}.

CLI
---
    python -m intelligence_catalog.db.feedback_loop --status
    python -m intelligence_catalog.db.feedback_loop --run-all
    python -m intelligence_catalog.db.feedback_loop --run-all --dry-run
    python -m intelligence_catalog.db.feedback_loop --run audit_log
    python -m intelligence_catalog.db.feedback_loop --run llm_analysis
    python -m intelligence_catalog.db.feedback_loop --run miner_restarts
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Optional

LOG = logging.getLogger("feedback_loop")

# Sentinel source id (bobby_operational, tier2_operational) — seeded in
# 0007 sources migration. Hard-coded so the feedback loop has a stable
# attribution path even if the seed file is re-run. If you change this,
# change the seed too.
SOURCE_ID_BOBBY_OPERATIONAL = "a0000000-0000-0000-0000-00000000000f"


# ──────────────────────────────────────────────────────────────────────────
# Connection helpers — two-connection split (P-018C)
#
# Every sync function reads from `public.<op-table>` (operational DB) and
# writes to `<catalog-schema>.<table>` plus resolves model_id against
# `hardware.miner_models` (both catalog DB). With the two DBs split, this
# module opens TWO connections per run:
#
#   • op_conn   → operational DB via core.db_targets.operational_target()
#                 (read-only here; aggregates audit/llm/restart rows)
#   • cat_conn  → catalog DB     via core.db_targets.catalog_target()
#                 (model_id lookup + UPSERT into ops/market/hardware)
#
# The two halves never share a transaction. Catalog writes commit
# independently of the operational read; that is fine because every
# write is idempotent (`ON CONFLICT DO UPDATE` for failure_patterns,
# UPDATE-then-INSERT for war_stories and model_known_issues — keyed on
# a deterministic metadata idempotency key). A partial write that the
# next run repeats is a no-op. A failure mid-loop leaves the catalog in
# a consistent partial state and the next run resumes naturally.
#
# Public signatures unchanged (`*, dry_run=False`). The legacy `conn=`
# kwarg has been removed because under split DBs it cannot be both
# operational AND catalog; tests and `run_full_feedback_loop` pass
# explicit `op_conn=`/`cat_conn=` instead. CLI/external callers
# (`python -m feedback_loop --run …`) are unaffected.
# ──────────────────────────────────────────────────────────────────────────

_UUID_ADAPTER_REGISTERED = False


def _ensure_uuid_adapter() -> None:
    global _UUID_ADAPTER_REGISTERED
    if _UUID_ADAPTER_REGISTERED:
        return
    try:
        import psycopg2.extras  # type: ignore
        psycopg2.extras.register_uuid()
        _UUID_ADAPTER_REGISTERED = True
    except Exception as exc:
        LOG.warning("could not register UUID adapter: %s", exc)


def _resolve_db_targets():
    """Resolve the two DB targets via core.db_targets, sys.path-resilient.

    Mirrors dual_writer.py's _resolve_catalog_target so cron/CLI runs
    invoked from `intelligence-catalog/` cwd still resolve `core.*`.
    """
    try:
        from core.db_targets import operational_target, catalog_target
    except ImportError:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        from core.db_targets import operational_target, catalog_target  # type: ignore[no-redef]
    return operational_target(), catalog_target()


def _open_connection(target):
    """Open one psycopg2 connection for `target` (operational or catalog).

    Returns None on any failure — caller logs + degrades gracefully.
    """
    try:
        import psycopg2  # type: ignore
    except ImportError:
        LOG.warning("psycopg2 not installed; feedback loop disabled.")
        return None

    _ensure_uuid_adapter()

    if not target.password:
        LOG.warning(
            "no DB password set (GUARDIAN_PG_PASSWORD / MG_DB_PASSWORD); "
            "feedback loop disabled."
        )
        return None

    try:
        return psycopg2.connect(connect_timeout=5, **target.connect_kwargs())
    except Exception as exc:
        LOG.warning("Postgres unreachable (%s): %s; feedback loop disabled.",
                    target.dbname, exc)
        return None


def _open_op_connection():
    """Open the operational DB connection (read-only by convention here)."""
    op_target, _ = _resolve_db_targets()
    return _open_connection(op_target)


def _open_cat_connection():
    """Open the catalog DB connection (model_id lookup + UPSERTs)."""
    _, cat_target = _resolve_db_targets()
    return _open_connection(cat_target)


# Legacy single-connection helper. Kept ONLY because the integration test
# `intelligence-catalog/db/tests/test_feedback_loop.py` imports it via
# `fb._get_connection()` to probe DB availability; removing it would
# AttributeError at test-module import even when the test ultimately
# skips. New callers should use `_open_op_connection` /
# `_open_cat_connection` explicitly. Resolves to the operational target
# to match the pre-P-018C behavior the test relied on.
def _get_connection():
    return _open_op_connection()


def _resolve_model_id(cat_cur, model_text: str):
    """Look up `hardware.miner_models.id` by free-text model name.

    Catalog-DB-side lookup. ILIKE-contains match against `canonical_name`
    OR `model_number`. Returns the UUID or None if not found / table
    missing.
    """
    if not model_text:
        return None
    if not _table_exists(cat_cur, "hardware", "miner_models"):
        return None
    cat_cur.execute(
        "SELECT id FROM hardware.miner_models "
        "WHERE canonical_name ILIKE %s OR model_number ILIKE %s "
        "LIMIT 1",
        (f"%{model_text}%", f"%{model_text}%"),
    )
    row = cat_cur.fetchone()
    return row[0] if row else None


def _table_exists(cur, schema: str, table: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema=%s AND table_name=%s",
        (schema, table),
    )
    return cur.fetchone() is not None


def _empty_stats() -> dict:
    return {
        "rows_read": 0,
        "rows_written": 0,
        "rows_updated": 0,
        "rows_skipped": 0,
        "error": None,
    }


# ──────────────────────────────────────────────────────────────────────────
# 1) action_audit_log → ops.failure_patterns
# ──────────────────────────────────────────────────────────────────────────

def sync_action_audit_to_failure_patterns(
    *, op_conn=None, cat_conn=None, dry_run: bool = False
) -> dict:
    """Aggregate `public.action_audit_log` (operational) into
    `ops.failure_patterns` (catalog).

    Two-connection split (P-018C). The reads happen against `op_conn`,
    the model_id lookup + UPSERTs happen against `cat_conn`. Both
    connections are opened internally if not supplied; caller-supplied
    connections (used by `run_full_feedback_loop` and tests) are NOT
    closed by this function.

    Idempotency: catalog writes use `ON CONFLICT (pattern_code) DO
    UPDATE`. Re-runs UPDATE rather than INSERT.
    """
    stats = _empty_stats()
    own_op = op_conn is None
    own_cat = cat_conn is None
    if op_conn is None:
        op_conn = _open_op_connection()
    if cat_conn is None:
        cat_conn = _open_cat_connection()
    if op_conn is None or cat_conn is None:
        stats["error"] = "no postgres connection (operational or catalog)"
        if own_op and op_conn is not None:
            op_conn.close()
        if own_cat and cat_conn is not None:
            cat_conn.close()
        return stats

    try:
        with op_conn.cursor() as op_cur, cat_conn.cursor() as cat_cur:
            if not _table_exists(op_cur, "public", "action_audit_log"):
                stats["error"] = (
                    "public.action_audit_log not found — migration 001 not yet applied"
                )
                LOG.warning(stats["error"])
                return stats

            # Aggregate (operational read): one query, no per-row I/O.
            op_cur.execute("""
                SELECT
                    aal.model,
                    aal.problem,
                    COUNT(*)            AS occurrences,
                    COUNT(*) FILTER (WHERE aal.decision='APPROVED') AS approved,
                    COUNT(*) FILTER (WHERE aal.decision='DENIED')   AS denied,
                    MIN(aal.timestamp)  AS first_seen,
                    MAX(aal.timestamp)  AS last_seen
                FROM public.action_audit_log aal
                WHERE aal.problem IS NOT NULL AND aal.problem <> ''
                GROUP BY aal.model, aal.problem
                HAVING COUNT(*) >= 2
            """)
            agg_rows = op_cur.fetchall()
            stats["rows_read"] = len(agg_rows)

            for model, problem, occ, approved, denied, first_seen, last_seen in agg_rows:
                # Catalog-side: resolve model_id (best-effort).
                model_id = _resolve_model_id(cat_cur, model) if model else None

                pattern_code = _pattern_code("OP", model or "any", problem)
                pattern_name = (problem[:120]).strip()
                description = (
                    f"Operational pattern observed {occ} time(s) "
                    f"({approved} approved, {denied} denied) on "
                    f"{model or 'fleet'} between {first_seen} and {last_seen}."
                )
                metadata = {
                    "occurrences": occ,
                    "approved": approved,
                    "denied": denied,
                    "first_seen": first_seen.isoformat() if first_seen else None,
                    "last_seen": last_seen.isoformat() if last_seen else None,
                    "operational_model_text": model,
                }
                severity = _classify_severity(occ, denied)
                root_cause_category = _classify_root_cause(problem)

                if dry_run:
                    LOG.info(
                        "[dry-run] would upsert ops.failure_patterns code=%s "
                        "model_id=%s sev=%s",
                        pattern_code, model_id, severity,
                    )
                    stats["rows_skipped"] += 1
                    continue

                cat_cur.execute("""
                    INSERT INTO ops.failure_patterns (
                        pattern_name, pattern_code, description,
                        failure_category, severity,
                        is_model_specific, primary_model_id,
                        root_cause, root_cause_category,
                        estimated_occurrence_rate, occurrence_rate_source,
                        primary_source_id, confidence, verified_by_bobby,
                        metadata
                    ) VALUES (
                        %s, %s, %s,
                        'operational', %s,
                        %s, %s,
                        %s, %s,
                        NULL, 'feedback_loop',
                        %s::uuid, 'medium', false,
                        %s::jsonb
                    )
                    ON CONFLICT (pattern_code) DO UPDATE SET
                        description = EXCLUDED.description,
                        severity    = EXCLUDED.severity,
                        metadata    = ops.failure_patterns.metadata || EXCLUDED.metadata,
                        updated_at  = now()
                    RETURNING (xmax = 0) AS inserted
                """, (
                    pattern_name, pattern_code, description,
                    severity,
                    model_id is not None, model_id,
                    "Inferred from action_audit_log aggregation",
                    root_cause_category,
                    SOURCE_ID_BOBBY_OPERATIONAL,
                    json.dumps(metadata),
                ))
                inserted = cat_cur.fetchone()[0]
                if inserted:
                    stats["rows_written"] += 1
                else:
                    stats["rows_updated"] += 1

            if not dry_run:
                cat_conn.commit()
        return stats
    except Exception as exc:
        LOG.exception("sync_action_audit_to_failure_patterns failed: %s", exc)
        stats["error"] = str(exc)
        if not dry_run:
            try:
                cat_conn.rollback()
            except Exception:
                pass
        return stats
    finally:
        if own_op and op_conn is not None:
            op_conn.close()
        if own_cat and cat_conn is not None:
            cat_conn.close()


# ──────────────────────────────────────────────────────────────────────────
# 2) llm_analysis → market.war_stories
# ──────────────────────────────────────────────────────────────────────────

def sync_llm_analysis_to_war_stories(
    *, op_conn=None, cat_conn=None, dry_run: bool = False
) -> dict:
    """Promote substantive `public.llm_analysis` rows (operational) into
    `market.war_stories` (catalog).

    Two-connection split (P-018C). Reads on `op_conn`, UPSERT on
    `cat_conn`. No model_id resolution needed — `tagged_model_ids` is
    explicitly `'{}'::uuid[]`.

    Idempotency: `metadata @> {llm_analysis_id: …}` UPDATE-first, then
    INSERT if no row matched.
    """
    stats = _empty_stats()
    own_op = op_conn is None
    own_cat = cat_conn is None
    if op_conn is None:
        op_conn = _open_op_connection()
    if cat_conn is None:
        cat_conn = _open_cat_connection()
    if op_conn is None or cat_conn is None:
        stats["error"] = "no postgres connection (operational or catalog)"
        if own_op and op_conn is not None:
            op_conn.close()
        if own_cat and cat_conn is not None:
            cat_conn.close()
        return stats

    try:
        with op_conn.cursor() as op_cur, cat_conn.cursor() as cat_cur:
            if not _table_exists(op_cur, "public", "llm_analysis"):
                stats["error"] = (
                    "public.llm_analysis not found — migration 001 not yet applied"
                )
                LOG.warning(stats["error"])
                return stats

            op_cur.execute("""
                SELECT id, scan_id, analyzed_at, miner_id, prompt, response, model_used
                FROM public.llm_analysis
                WHERE response IS NOT NULL AND length(response) >= 200
                ORDER BY analyzed_at DESC
                LIMIT 500
            """)
            rows = op_cur.fetchall()
            stats["rows_read"] = len(rows)

            for la_id, scan_id, analyzed_at, miner_id, prompt, response, model_used in rows:
                title = (
                    f"AI analysis of miner {miner_id or 'unknown'} on "
                    f"{analyzed_at.date() if analyzed_at else 'unknown'}"
                )
                narrative = response[:4000]
                lesson = _extract_lesson(response)
                topic_tags = _extract_topic_tags(response)
                metadata = {
                    "llm_analysis_id": la_id,
                    "scan_id": scan_id,
                    "miner_id": miner_id,
                    "model_used": model_used,
                }

                if dry_run:
                    LOG.info(
                        "[dry-run] would upsert market.war_stories llm_id=%s",
                        la_id,
                    )
                    stats["rows_skipped"] += 1
                    continue

                cat_cur.execute("""
                    UPDATE market.war_stories
                    SET narrative = %s,
                        lesson_learned = %s,
                        topic_tags = %s,
                        metadata = metadata || %s::jsonb,
                        updated_at = now()
                    WHERE metadata @> %s::jsonb
                    RETURNING id
                """, (
                    narrative, lesson, topic_tags,
                    json.dumps(metadata),
                    json.dumps({"llm_analysis_id": la_id}),
                ))
                if cat_cur.fetchone():
                    stats["rows_updated"] += 1
                    continue

                cat_cur.execute("""
                    INSERT INTO market.war_stories (
                        title, narrative, event_date,
                        tagged_model_ids, tagged_failure_patterns, topic_tags,
                        lesson_learned,
                        is_bobby_story, primary_source_id, confidence,
                        metadata
                    ) VALUES (
                        %s, %s, %s,
                        '{}'::uuid[], '{}'::text[], %s,
                        %s,
                        false, %s::uuid, 'low',
                        %s::jsonb
                    )
                """, (
                    title, narrative,
                    analyzed_at.date() if analyzed_at else None,
                    topic_tags,
                    lesson,
                    SOURCE_ID_BOBBY_OPERATIONAL,
                    json.dumps(metadata),
                ))
                stats["rows_written"] += 1

            if not dry_run:
                cat_conn.commit()
        return stats
    except Exception as exc:
        LOG.exception("sync_llm_analysis_to_war_stories failed: %s", exc)
        stats["error"] = str(exc)
        if not dry_run:
            try:
                cat_conn.rollback()
            except Exception:
                pass
        return stats
    finally:
        if own_op and op_conn is not None:
            op_conn.close()
        if own_cat and cat_conn is not None:
            cat_conn.close()


# ──────────────────────────────────────────────────────────────────────────
# 3) miner_restarts → hardware.model_known_issues
# ──────────────────────────────────────────────────────────────────────────

def sync_miner_restarts_to_known_issues(
    *, op_conn=None, cat_conn=None, dry_run: bool = False
) -> dict:
    """Aggregate `public.miner_restarts` (operational) by (model,
    restart_type) and upsert into `hardware.model_known_issues`
    (catalog). Restart_type maps to issue_type; failure rate
    (failures / total) drives commonality.

    Two-connection split (P-018C). Rows whose model can't be resolved
    against `hardware.miner_models` are skipped (rows_skipped) — this
    matches the original behavior since `miner_model_id` is NOT NULL
    on `hardware.model_known_issues`.
    """
    stats = _empty_stats()
    own_op = op_conn is None
    own_cat = cat_conn is None
    if op_conn is None:
        op_conn = _open_op_connection()
    if cat_conn is None:
        cat_conn = _open_cat_connection()
    if op_conn is None or cat_conn is None:
        stats["error"] = "no postgres connection (operational or catalog)"
        if own_op and op_conn is not None:
            op_conn.close()
        if own_cat and cat_conn is not None:
            cat_conn.close()
        return stats

    try:
        with op_conn.cursor() as op_cur, cat_conn.cursor() as cat_cur:
            if not _table_exists(op_cur, "public", "miner_restarts"):
                stats["error"] = (
                    "public.miner_restarts not found — migration 001 not yet applied"
                )
                LOG.warning(stats["error"])
                return stats

            op_cur.execute("""
                SELECT
                    model,
                    COALESCE(restart_type, 'unspecified') AS restart_type,
                    COUNT(*)                              AS total,
                    COUNT(*) FILTER (WHERE outcome='success') AS succeeded,
                    COUNT(*) FILTER (WHERE outcome='failure') AS failed,
                    AVG(NULLIF(recovery_time_scans, 0))   AS avg_recovery_scans,
                    MIN(restarted_at)                     AS first_seen,
                    MAX(restarted_at)                     AS last_seen
                FROM public.miner_restarts
                WHERE model IS NOT NULL AND model <> ''
                GROUP BY model, COALESCE(restart_type, 'unspecified')
                HAVING COUNT(*) >= 3
            """)
            rows = op_cur.fetchall()
            stats["rows_read"] = len(rows)

            for (model, restart_type, total, succeeded, failed,
                 avg_recovery, first_seen, last_seen) in rows:
                model_id = _resolve_model_id(cat_cur, model)
                if not model_id:
                    stats["rows_skipped"] += 1
                    continue

                fail_rate = (failed / total) if total else 0.0
                commonality = _classify_commonality(fail_rate, total)
                title = f"{restart_type} restart pattern"
                description = (
                    f"Observed {total} restart(s) of type '{restart_type}' "
                    f"on this model: {succeeded} succeeded, {failed} failed "
                    f"(failure rate {fail_rate:.1%}). First seen "
                    f"{first_seen}, last {last_seen}."
                )
                idempotency_key = {
                    "feedback_loop_key": f"restart::{restart_type}",
                }
                metadata = {
                    **idempotency_key,
                    "total_restarts": total,
                    "succeeded": succeeded,
                    "failed": failed,
                    "failure_rate": round(fail_rate, 4),
                    "avg_recovery_scans": float(avg_recovery) if avg_recovery is not None else None,
                    "first_seen": first_seen.isoformat() if first_seen else None,
                    "last_seen": last_seen.isoformat() if last_seen else None,
                    "operational_model_text": model,
                }

                if dry_run:
                    LOG.info(
                        "[dry-run] would upsert hardware.model_known_issues "
                        "model_id=%s type=%s commonality=%s",
                        model_id, restart_type, commonality,
                    )
                    stats["rows_skipped"] += 1
                    continue

                cat_cur.execute("""
                    UPDATE hardware.model_known_issues
                    SET description = %s,
                        commonality = %s,
                        report_count = %s,
                        metadata = metadata || %s::jsonb,
                        first_reported_date = COALESCE(first_reported_date, %s),
                        updated_at = now()
                    WHERE miner_model_id = %s
                      AND metadata @> %s::jsonb
                    RETURNING id
                """, (
                    description, commonality, total,
                    json.dumps(metadata),
                    first_seen.date() if first_seen else None,
                    model_id,
                    json.dumps(idempotency_key),
                ))
                if cat_cur.fetchone():
                    stats["rows_updated"] += 1
                    continue

                cat_cur.execute("""
                    INSERT INTO hardware.model_known_issues (
                        miner_model_id, issue_type, commonality, category,
                        title, description,
                        is_resolved, report_count,
                        bobby_experienced, primary_source_id, confidence,
                        first_reported_date, metadata
                    ) VALUES (
                        %s, %s, %s, 'reliability',
                        %s, %s,
                        false, %s,
                        false, %s::uuid, 'medium',
                        %s, %s::jsonb
                    )
                """, (
                    model_id, restart_type, commonality,
                    title, description,
                    total,
                    SOURCE_ID_BOBBY_OPERATIONAL,
                    first_seen.date() if first_seen else None,
                    json.dumps(metadata),
                ))
                stats["rows_written"] += 1

            if not dry_run:
                cat_conn.commit()
        return stats
    except Exception as exc:
        LOG.exception("sync_miner_restarts_to_known_issues failed: %s", exc)
        stats["error"] = str(exc)
        if not dry_run:
            try:
                cat_conn.rollback()
            except Exception:
                pass
        return stats
    finally:
        if own_op and op_conn is not None:
            op_conn.close()
        if own_cat and cat_conn is not None:
            cat_conn.close()


# ──────────────────────────────────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────────────────────────────────

def run_full_feedback_loop(*, dry_run: bool = False) -> dict:
    """Run all three sync passes, sharing one operational + one catalog
    connection across the three passes.

    P-018C: previously this opened ONE connection and passed it down via
    `conn=`. With split DBs we open TWO connections — operational and
    catalog — and reuse both across the three sync calls. Each sync
    writes commit independently of the others (idempotent UPSERTs make
    a partial run safe to repeat).
    """
    out = {"audit_log": _empty_stats(), "llm_analysis": _empty_stats(),
           "miner_restarts": _empty_stats()}
    op_conn = _open_op_connection()
    cat_conn = _open_cat_connection()
    if op_conn is None or cat_conn is None:
        for v in out.values():
            v["error"] = "no postgres connection (operational or catalog)"
        if op_conn is not None:
            op_conn.close()
        if cat_conn is not None:
            cat_conn.close()
        return out
    try:
        out["audit_log"]      = sync_action_audit_to_failure_patterns(
            op_conn=op_conn, cat_conn=cat_conn, dry_run=dry_run)
        out["llm_analysis"]   = sync_llm_analysis_to_war_stories(
            op_conn=op_conn, cat_conn=cat_conn, dry_run=dry_run)
        out["miner_restarts"] = sync_miner_restarts_to_known_issues(
            op_conn=op_conn, cat_conn=cat_conn, dry_run=dry_run)
    finally:
        for c in (op_conn, cat_conn):
            try:
                c.close()
            except Exception:
                pass
    return out


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

def _pattern_code(prefix: str, *parts: str) -> str:
    """Deterministic, short, dedup-safe code: `PREFIX_<sha8>`."""
    import hashlib
    seed = "::".join(p or "" for p in parts).lower()
    return f"{prefix}_{hashlib.sha1(seed.encode()).hexdigest()[:8]}"


def _classify_severity(occurrences: int, denied: int) -> str:
    """Map (occurrence count, denial count) to failure_severity enum."""
    if occurrences >= 50:
        return "critical"
    if occurrences >= 20:
        return "high"
    if occurrences >= 5:
        return "medium"
    if denied > occurrences * 0.5:
        return "high"  # denied more often than approved → suspicious
    return "low"


def _classify_root_cause(problem: str) -> str:
    """Crude keyword classifier for root_cause_category."""
    p = (problem or "").lower()
    if any(k in p for k in ("temp", "thermal", "hot", "overheat")):
        return "thermal"
    if any(k in p for k in ("hash", "rate", "performance")):
        return "performance"
    if any(k in p for k in ("network", "offline", "unreach")):
        return "network"
    if any(k in p for k in ("power", "psu", "voltage")):
        return "power"
    if any(k in p for k in ("board", "chip", "asic")):
        return "hardware"
    if any(k in p for k in ("firmware", "flash", "version")):
        return "firmware"
    return "unknown"


def _classify_commonality(failure_rate: float, sample_size: int) -> str:
    """Map (failure rate, sample size) to a commonality label."""
    if sample_size < 5:
        return "isolated"
    if failure_rate >= 0.5:
        return "widespread"
    if failure_rate >= 0.2:
        return "common"
    if failure_rate >= 0.05:
        return "occasional"
    return "rare"


def _extract_lesson(response: str) -> str:
    """First sentence of the LLM response, truncated to 500 chars."""
    if not response:
        return "(no lesson extracted)"
    first = response.split(".", 1)[0].strip()
    return (first[:500] or "(no lesson extracted)")


def _extract_topic_tags(response: str) -> list[str]:
    """Cheap topic tagging from common keywords."""
    if not response:
        return []
    r = response.lower()
    candidates = [
        ("thermal",      ["thermal", "overheat", "temp"]),
        ("performance",  ["hashrate", "underperform"]),
        ("network",      ["network", "offline", "unreach"]),
        ("power",        ["power", "psu", "voltage"]),
        ("hardware",     ["asic", "chip", "hashboard"]),
        ("firmware",     ["firmware", "flash"]),
        ("maintenance",  ["clean", "filter", "dust"]),
    ]
    tags = [name for name, kws in candidates if any(kw in r for kw in kws)]
    return tags or ["general"]


# ──────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────

def _main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mining Guardian — operational→catalog feedback loop (C5 / PR #22)",
    )
    parser.add_argument("--status", action="store_true",
                        help="Print connection status and source-table availability")
    parser.add_argument("--run", choices=["audit_log", "llm_analysis", "miner_restarts"],
                        help="Run a single sync pass")
    parser.add_argument("--run-all", action="store_true",
                        help="Run all three sync passes")
    parser.add_argument("--dry-run", action="store_true",
                        help="Do not write to catalog tables; log what would be written")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if args.status:
        op_conn = _open_op_connection()
        cat_conn = _open_cat_connection()
        result = {
            "operational_available": op_conn is not None,
            "catalog_available":     cat_conn is not None,
        }
        if op_conn is not None:
            try:
                with op_conn.cursor() as cur:
                    for src in ("action_audit_log", "llm_analysis", "miner_restarts"):
                        result[f"public.{src}"] = _table_exists(cur, "public", src)
            finally:
                op_conn.close()
        if cat_conn is not None:
            try:
                with cat_conn.cursor() as cur:
                    for tbl in (("ops", "failure_patterns"),
                                ("market", "war_stories"),
                                ("hardware", "model_known_issues"),
                                ("hardware", "miner_models")):
                        result[f"{tbl[0]}.{tbl[1]}"] = _table_exists(cur, *tbl)
            finally:
                cat_conn.close()
        print(json.dumps(result, indent=2))
        return 0

    if args.run_all:
        out = run_full_feedback_loop(dry_run=args.dry_run)
        print(json.dumps(out, indent=2))
        return 0

    if args.run == "audit_log":
        print(json.dumps(sync_action_audit_to_failure_patterns(dry_run=args.dry_run), indent=2))
        return 0
    if args.run == "llm_analysis":
        print(json.dumps(sync_llm_analysis_to_war_stories(dry_run=args.dry_run), indent=2))
        return 0
    if args.run == "miner_restarts":
        print(json.dumps(sync_miner_restarts_to_known_issues(dry_run=args.dry_run), indent=2))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(_main())
