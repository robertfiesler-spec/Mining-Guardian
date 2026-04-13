"""Database operations for the Intelligence Catalog Importer.

Connects to PostgreSQL 16 on ROBS-PC (container: mining-guardian-db).
All queries use parameterized statements — no string interpolation.
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional

import psycopg2
import psycopg2.extras

from config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
from models import DetectedMiner, ImportJob, TestResult

logger = logging.getLogger("importer.db")

# Register UUID adapter for psycopg2
psycopg2.extras.register_uuid()


def get_connection():
    """Create a new database connection."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=10,
    )


def ensure_schema(conn) -> None:
    """Run schema_additions.sql to create import tracking tables if they don't exist."""
    from pathlib import Path

    schema_file = Path(__file__).parent / "schema_additions.sql"
    if not schema_file.exists():
        logger.warning("schema_additions.sql not found — skipping schema setup")
        return
    sql = schema_file.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    logger.info("Schema verified/created")


# ─── Import Jobs ──────────────────────────────────────────────────────────────

def create_import_job(conn, source_path: str, source_type: str) -> int:
    """Create a new import job and return its import_id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO knowledge.import_jobs (source_path, source_type, status)
            VALUES (%s, %s, 'running')
            RETURNING import_id
            """,
            (source_path, source_type),
        )
        import_id = cur.fetchone()[0]
    conn.commit()
    return import_id


def update_import_job(conn, import_id: int, **kwargs) -> None:
    """Update an import job's counters and status."""
    allowed = {
        "total_files", "processed_files", "skipped_files", "failed_files",
        "needs_review", "status", "notes", "completed_at",
    }
    sets = []
    vals = []
    for k, v in kwargs.items():
        if k not in allowed:
            continue
        sets.append(f"{k} = %s")
        vals.append(v)
    if not sets:
        return
    vals.append(import_id)
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE knowledge.import_jobs SET {', '.join(sets)} WHERE import_id = %s",
            vals,
        )
    conn.commit()


def complete_import_job(conn, job: ImportJob) -> None:
    """Finalize an import job."""
    status = "completed"
    if job.failed_files > 0 and job.processed_files == 0:
        status = "failed"
    elif job.failed_files > 0:
        status = "partial"

    update_import_job(
        conn,
        job.import_id,
        total_files=job.total_files,
        processed_files=job.processed_files,
        skipped_files=job.skipped_files,
        failed_files=job.failed_files,
        needs_review=job.needs_review,
        status=status,
        completed_at=datetime.utcnow(),
    )


# ─── Imported Files ───────────────────────────────────────────────────────────

def check_file_hash_exists(conn, file_hash: str) -> Optional[int]:
    """Check if a file with this hash was already imported. Return file_id or None."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT file_id FROM knowledge.imported_files WHERE file_hash = %s LIMIT 1",
            (file_hash,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def insert_imported_file(
    conn,
    import_id: int,
    original_filename: str,
    original_path: str,
    file_size_bytes: int,
    file_type: str,
    file_hash: str,
    detected: Optional[DetectedMiner],
    processing_status: str,
    processing_notes: str,
    parsed_data: Optional[dict],
    catalog_model_id: Optional[str] = None,
) -> int:
    """Insert a processed file record and return its file_id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO knowledge.imported_files (
                import_id, original_filename, original_path, file_size_bytes,
                file_type, file_hash, detected_brand, detected_model,
                detected_firmware, detected_serial, detected_mac,
                detection_confidence, detection_evidence, catalog_model_id,
                processing_status, processing_notes, parsed_data
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s
            )
            RETURNING file_id
            """,
            (
                import_id,
                original_filename,
                original_path,
                file_size_bytes,
                file_type,
                file_hash,
                detected.brand if detected else None,
                detected.model if detected else None,
                detected.firmware if detected else None,
                detected.serial if detected else None,
                detected.mac if detected else None,
                detected.confidence if detected else None,
                json.dumps(detected.evidence) if detected else "[]",
                catalog_model_id,
                processing_status,
                processing_notes,
                json.dumps(parsed_data) if parsed_data else "{}",
            ),
        )
        file_id = cur.fetchone()[0]
    conn.commit()
    return file_id


# ─── Diagnostic Results ───────────────────────────────────────────────────────

def insert_diagnostic_results(conn, file_id: int, results: list[TestResult]) -> None:
    """Batch insert diagnostic test results for a file."""
    if not results:
        return
    with conn.cursor() as cur:
        for r in results:
            cur.execute(
                """
                INSERT INTO ops.import_diagnostic_results (
                    file_id, test_id, test_name, category, result,
                    severity, evidence, diagnosis, recommended_action, confidence
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    file_id, r.test_id, r.test_name, r.category, r.result,
                    r.severity, r.evidence, r.diagnosis, r.recommended_action,
                    r.confidence,
                ),
            )
    conn.commit()


# ─── Catalog Lookups ──────────────────────────────────────────────────────────

def lookup_miner_model(conn, brand: str, model: str) -> Optional[dict]:
    """Look up a miner model in hardware.miner_models by brand and model name.

    Tries exact canonical_name match first, then model_number, then fuzzy.
    Returns dict with id, canonical_name, stock specs, etc.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # Join with manufacturers to filter by brand
        cur.execute(
            """
            SELECT
                mm.id, mm.canonical_name, mm.model_number, mm.generation,
                mm.stock_hashrate_th, mm.stock_power_w, mm.stock_efficiency_j_th,
                mm.algorithm, mm.manufacturer_id,
                m.brand AS manufacturer_brand
            FROM hardware.miner_models mm
            JOIN hardware.manufacturers m ON mm.manufacturer_id = m.id
            WHERE m.brand = %s
              AND (
                  LOWER(mm.canonical_name) = LOWER(%s)
                  OR LOWER(mm.model_number) = LOWER(%s)
              )
            LIMIT 1
            """,
            (brand.lower(), model, model),
        )
        row = cur.fetchone()
        if row:
            return dict(row)

        # Fuzzy: search canonical_name containing the model string
        cur.execute(
            """
            SELECT
                mm.id, mm.canonical_name, mm.model_number, mm.generation,
                mm.stock_hashrate_th, mm.stock_power_w, mm.stock_efficiency_j_th,
                mm.algorithm, mm.manufacturer_id,
                m.brand AS manufacturer_brand
            FROM hardware.miner_models mm
            JOIN hardware.manufacturers m ON mm.manufacturer_id = m.id
            WHERE m.brand = %s
              AND LOWER(mm.canonical_name) LIKE %s
            ORDER BY LENGTH(mm.canonical_name) ASC
            LIMIT 1
            """,
            (brand.lower(), f"%{model.lower()}%"),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def lookup_model_by_name(conn, name: str) -> Optional[dict]:
    """Search for a miner model by any part of its canonical_name."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                mm.id, mm.canonical_name, mm.model_number, mm.generation,
                mm.stock_hashrate_th, mm.stock_power_w, mm.stock_efficiency_j_th,
                mm.algorithm, mm.manufacturer_id,
                m.brand AS manufacturer_brand
            FROM hardware.miner_models mm
            JOIN hardware.manufacturers m ON mm.manufacturer_id = m.id
            WHERE LOWER(mm.canonical_name) LIKE %s
               OR LOWER(mm.model_number) LIKE %s
            ORDER BY LENGTH(mm.canonical_name) ASC
            LIMIT 1
            """,
            (f"%{name.lower()}%", f"%{name.lower()}%"),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def get_all_model_names(conn) -> list[dict]:
    """Fetch all model names for detection matching. Cached by caller."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                mm.id, mm.canonical_name, mm.model_number, mm.generation,
                mm.algorithm, m.brand AS manufacturer_brand
            FROM hardware.miner_models mm
            JOIN hardware.manufacturers m ON mm.manufacturer_id = m.id
            ORDER BY LENGTH(mm.canonical_name) DESC
            """
        )
        return [dict(r) for r in cur.fetchall()]


# ─── Field Registry / Unknown Fields ─────────────────────────────────────────

def check_field_registry(conn, field_key: str) -> bool:
    """Check if a field is known in knowledge.field_registry."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM knowledge.field_registry WHERE field_key = %s LIMIT 1",
            (field_key,),
        )
        return cur.fetchone() is not None


def register_unknown_field(
    conn,
    raw_field_name: str,
    source_system: str,
    source_endpoint: str,
    raw_value: str,
    raw_type: str,
    source_model: Optional[str] = None,
    parent_object: Optional[str] = None,
    suggested_category: Optional[str] = None,
) -> None:
    """Register a previously unseen field in knowledge.unknown_fields.

    Uses ON CONFLICT to increment occurrence_count if already registered.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO knowledge.unknown_fields (
                raw_field_name, raw_field_value, raw_field_type,
                source_system, source_endpoint, source_model,
                parent_object, llm_suggested_category, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'new')
            ON CONFLICT (raw_field_name, source_system, COALESCE(parent_object, ''))
            WHERE status NOT IN ('duplicate', 'ignored')
            DO UPDATE SET
                occurrence_count = knowledge.unknown_fields.occurrence_count + 1,
                last_seen_at = NOW(),
                sample_values = CASE
                    WHEN jsonb_array_length(knowledge.unknown_fields.sample_values) < 10
                    THEN knowledge.unknown_fields.sample_values || to_jsonb(%s::text)
                    ELSE knowledge.unknown_fields.sample_values
                END
            """,
            (
                raw_field_name, raw_value, raw_type,
                source_system, source_endpoint, source_model,
                parent_object, suggested_category,
                raw_value,
            ),
        )
    conn.commit()


# ─── Reporting Queries ────────────────────────────────────────────────────────

def get_recent_jobs(conn, limit: int = 20) -> list[dict]:
    """Fetch recent import jobs for status display."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT import_id, started_at, completed_at, source_path, source_type,
                   total_files, processed_files, skipped_files, failed_files,
                   needs_review, status
            FROM knowledge.import_jobs
            ORDER BY started_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_needs_review(conn, limit: int = 50) -> list[dict]:
    """Fetch files flagged as needs_review."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT f.file_id, f.import_id, f.original_filename, f.detected_brand,
                   f.detected_model, f.detection_confidence, f.processing_notes,
                   f.imported_at
            FROM knowledge.imported_files f
            WHERE f.processing_status = 'needs_review'
            ORDER BY f.imported_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_import_stats(conn) -> dict:
    """Aggregate import statistics."""
    stats = {}
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT COUNT(*) AS total_jobs FROM knowledge.import_jobs")
        stats["total_jobs"] = cur.fetchone()["total_jobs"]

        cur.execute(
            "SELECT COUNT(*) AS total_files FROM knowledge.imported_files"
        )
        stats["total_files"] = cur.fetchone()["total_files"]

        cur.execute(
            """
            SELECT processing_status, COUNT(*) AS cnt
            FROM knowledge.imported_files
            GROUP BY processing_status
            """
        )
        stats["by_status"] = {r["processing_status"]: r["cnt"] for r in cur.fetchall()}

        cur.execute(
            """
            SELECT detected_brand, COUNT(*) AS cnt
            FROM knowledge.imported_files
            WHERE detected_brand IS NOT NULL
            GROUP BY detected_brand
            ORDER BY cnt DESC
            """
        )
        stats["by_brand"] = {r["detected_brand"]: r["cnt"] for r in cur.fetchall()}

        cur.execute(
            """
            SELECT result, COUNT(*) AS cnt
            FROM ops.import_diagnostic_results
            GROUP BY result
            """
        )
        stats["diagnostics"] = {r["result"]: r["cnt"] for r in cur.fetchall()}

        cur.execute(
            "SELECT COUNT(*) AS cnt FROM knowledge.unknown_fields WHERE status = 'new'"
        )
        stats["unknown_fields_pending"] = cur.fetchone()["cnt"]

    return stats
