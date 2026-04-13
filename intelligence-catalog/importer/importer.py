#!/usr/bin/env python3
"""Intelligence Catalog Importer — CLI entry point.

Imports Bitcoin SHA-256 ASIC miner data files into the Intelligence Catalog
database (PostgreSQL 16 on ROBS-PC).

Usage:
    python importer.py <path>              Import a file or folder
    python importer.py <path> --dry-run    Show what would be imported
    python importer.py --status            Show recent import jobs
    python importer.py --review            Show files flagged as needs_review
    python importer.py --stats             Show import statistics
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Ensure the importer package is on the path
_IMPORTER_DIR = Path(__file__).resolve().parent
if str(_IMPORTER_DIR) not in sys.path:
    sys.path.insert(0, str(_IMPORTER_DIR))

from config import (
    BITCOIN_SHA256_ONLY,
    DETECTION_CONFIDENCE_THRESHOLD,
    SHA256_BRANDS,
    Color,
    TAG_DETECT,
    TAG_DISCOVERY,
    TAG_ERROR,
    TAG_EXTRACT,
    TAG_IMPORT,
    TAG_OK,
    TAG_PARSE,
    TAG_SKIP,
    TAG_STORE,
    TAG_TEST,
    TAG_WARN,
)
from detector import MinerDetector
from diagnostics.test_battery import DiagnosticBattery
from discovery import FieldDiscovery
from extractor import extract_files
from models import DetectedMiner, ImportJob, ParsedData
from parsers import ALL_PARSERS

# ─── Logging setup ────────────────────────────────────────────────────────────

log_dir = _IMPORTER_DIR / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"import_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stderr),
    ],
)
logger = logging.getLogger("importer")


# ─── Database connection helper ───────────────────────────────────────────────

def connect_db(dry_run: bool = False):
    """Connect to the PostgreSQL database. Returns None if dry_run or failure."""
    if dry_run:
        return None
    try:
        from db import ensure_schema, get_connection
        conn = get_connection()
        ensure_schema(conn)
        return conn
    except Exception as e:
        logger.warning("Database connection failed: %s", e)
        logger.warning("Continuing in offline mode — no data will be stored")
        print(f"{TAG_WARN} Database unavailable: {e}")
        print(f"{TAG_WARN} Running in offline mode — results shown but not stored")
        return None


# ─── Core import logic ────────────────────────────────────────────────────────

def process_file(
    extracted,
    detector: MinerDetector,
    discovery: FieldDiscovery,
    battery: DiagnosticBattery,
    conn,
    import_id: Optional[int],
    dry_run: bool,
    job: ImportJob,
) -> None:
    """Process a single extracted file through the full pipeline."""
    filename = extracted.filename
    content = extracted.content or ""

    if not content.strip():
        logger.info("Skipping empty file: %s", filename)
        job.skipped_files += 1
        return

    # ── Deduplication check ───────────────────────────────────────────
    if conn and not dry_run:
        from db import check_file_hash_exists
        existing = check_file_hash_exists(conn, extracted.file_hash)
        if existing:
            print(f"  {TAG_SKIP} {filename} — duplicate (file #{existing})")
            logger.info("Duplicate file skipped: %s (hash=%s)", filename, extracted.file_hash)
            job.skipped_files += 1
            return

    # ── Step 1: Detection ─────────────────────────────────────────────
    detected = detector.detect(extracted)

    # Check for non-SHA-256
    if BITCOIN_SHA256_ONLY and detected.algorithm != "SHA-256":
        print(f"  {TAG_SKIP} {filename} — non-SHA-256 ({detected.algorithm})")
        logger.info("Non-SHA-256 file skipped: %s", filename)
        job.skipped_files += 1
        if conn and import_id and not dry_run:
            from db import insert_imported_file
            insert_imported_file(
                conn, import_id, filename, extracted.original_path,
                extracted.file_size, extracted.file_type, extracted.file_hash,
                detected, "skipped", f"Non-SHA-256: {detected.algorithm}",
                None, None,
            )
        return

    confidence_str = f"{detected.confidence:.2f}"
    review_flag = " [NEEDS REVIEW]" if detected.needs_review else ""
    print(
        f"  {TAG_DETECT} {detected.display_name} — "
        f"confidence: {confidence_str}{review_flag}"
    )

    # ── Step 2: Parsing ───────────────────────────────────────────────
    parsed: Optional[ParsedData] = None
    for parser_cls in ALL_PARSERS:
        parser = parser_cls()
        try:
            if parser.can_parse(content, detected):
                parsed = parser.parse(content, detected)
                break
        except Exception as e:
            logger.warning("Parser %s failed on %s: %s", parser.name, filename, e)
            continue

    if parsed is None:
        print(f"  {TAG_WARN} No parser could handle {filename}")
        logger.warning("No parser for: %s", filename)
        job.failed_files += 1
        if conn and import_id and not dry_run:
            from db import insert_imported_file
            insert_imported_file(
                conn, import_id, filename, extracted.original_path,
                extracted.file_size, extracted.file_type, extracted.file_hash,
                detected, "failed", "No parser could handle this file",
                None, None,
            )
        return

    print(
        f"  {TAG_PARSE} Extracted {parsed.data_points_count:,} data points "
        f"({parsed.parser_name} parser)"
    )

    # ── Step 3: Auto-discovery of unknown fields ──────────────────────
    if parsed.raw_fields:
        unknowns = discovery.process_raw_fields(
            parsed.raw_fields, filename, detected
        )
        parsed.unknown_fields = unknowns
        if unknowns:
            print(
                f"  {TAG_DISCOVERY} {len(unknowns)} new field(s) discovered"
            )

    # ── Step 4: Diagnostic tests ──────────────────────────────────────
    results = battery.run(parsed, detected)
    summary = battery.format_summary(results)
    print(f"  {TAG_TEST} {summary}")

    # ── Step 5: Store results ─────────────────────────────────────────
    processing_status = "processed"
    if detected.needs_review:
        processing_status = "needs_review"
        job.needs_review += 1

    if conn and import_id and not dry_run:
        from db import insert_diagnostic_results, insert_imported_file

        file_id = insert_imported_file(
            conn, import_id, filename, extracted.original_path,
            extracted.file_size, extracted.file_type, extracted.file_hash,
            detected, processing_status, "",
            parsed.to_dict(),
            detected.catalog_model_id,
        )
        insert_diagnostic_results(conn, file_id, results)
        print(f"  {TAG_STORE} Saved to import #{import_id}, file #{file_id}")
    elif dry_run:
        print(f"  {TAG_STORE} [DRY RUN] Would save to database")
    else:
        print(f"  {TAG_STORE} [OFFLINE] Results not stored (no DB connection)")

    job.processed_files += 1


def run_import(path: str, dry_run: bool = False) -> None:
    """Run the import process on a file or folder."""
    path = os.path.abspath(path)

    if not os.path.exists(path):
        print(f"{TAG_ERROR} Path does not exist: {path}")
        sys.exit(1)

    source_type = "folder" if os.path.isdir(path) else "file"
    mode = " [DRY RUN]" if dry_run else ""

    print(f"\n{TAG_IMPORT} Processing: {path}{mode}")
    print(f"{'─' * 70}")

    # Connect to database
    conn = connect_db(dry_run)

    # Initialize components
    detector = MinerDetector(db_conn=conn)
    discovery = FieldDiscovery(db_conn=conn)
    battery = DiagnosticBattery()

    # Create import job
    import_id = None
    if conn and not dry_run:
        from db import create_import_job
        import_id = create_import_job(conn, path, source_type)
        print(f"{TAG_IMPORT} Import job #{import_id} created")

    job = ImportJob(
        import_id=import_id,
        started_at=datetime.utcnow(),
        source_path=path,
        source_type=source_type,
    )

    # Extract and process files
    file_count = 0
    try:
        for extracted in extract_files(path):
            file_count += 1
            job.total_files = file_count
            print(f"\n{Color.BOLD}[{file_count}]{Color.RESET} {extracted.filename} "
                  f"({extracted.file_type}, {extracted.file_size:,} bytes)")

            try:
                process_file(
                    extracted, detector, discovery, battery,
                    conn, import_id, dry_run, job,
                )
            except Exception as e:
                logger.error("Failed to process %s: %s", extracted.filename, e, exc_info=True)
                print(f"  {TAG_ERROR} {e}")
                job.failed_files += 1
    except KeyboardInterrupt:
        print(f"\n{TAG_WARN} Import interrupted by user")
        job.status = "failed"
    except Exception as e:
        logger.error("Import failed: %s", e, exc_info=True)
        print(f"\n{TAG_ERROR} Import failed: {e}")
        job.status = "failed"

    # Finalize
    if conn and import_id and not dry_run:
        from db import complete_import_job
        complete_import_job(conn, job)

    # Print summary
    print(f"\n{'═' * 70}")
    print(f"{TAG_IMPORT} Import complete")
    print(f"  Total files:     {job.total_files}")
    print(f"  Processed:       {Color.GREEN}{job.processed_files}{Color.RESET}")
    print(f"  Skipped:         {Color.DIM}{job.skipped_files}{Color.RESET}")
    print(f"  Failed:          {Color.RED}{job.failed_files}{Color.RESET}")
    print(f"  Needs review:    {Color.YELLOW}{job.needs_review}{Color.RESET}")
    if import_id:
        print(f"  Import job:      #{import_id}")
    print(f"  Log file:        {log_file}")
    print()

    if conn:
        conn.close()


# ─── Reporting commands ───────────────────────────────────────────────────────

def show_status() -> None:
    """Show recent import jobs."""
    conn = connect_db()
    if not conn:
        print(f"{TAG_ERROR} Cannot connect to database")
        sys.exit(1)

    from db import get_recent_jobs

    jobs = get_recent_jobs(conn)
    if not jobs:
        print("No import jobs found.")
        conn.close()
        return

    try:
        from tabulate import tabulate
        headers = ["ID", "Started", "Status", "Total", "OK", "Skip", "Fail", "Review", "Source"]
        rows = []
        for j in jobs:
            started = j["started_at"].strftime("%Y-%m-%d %H:%M") if j["started_at"] else "?"
            rows.append([
                j["import_id"], started, j["status"],
                j["total_files"], j["processed_files"], j["skipped_files"],
                j["failed_files"], j["needs_review"],
                _truncate(j["source_path"], 40),
            ])
        print(tabulate(rows, headers=headers, tablefmt="simple"))
    except ImportError:
        for j in jobs:
            print(
                f"  #{j['import_id']}  {j['status']:10s}  "
                f"files={j['total_files']}  ok={j['processed_files']}  "
                f"fail={j['failed_files']}  review={j['needs_review']}  "
                f"{_truncate(j['source_path'], 40)}"
            )

    conn.close()


def show_review() -> None:
    """Show files flagged as needs_review."""
    conn = connect_db()
    if not conn:
        print(f"{TAG_ERROR} Cannot connect to database")
        sys.exit(1)

    from db import get_needs_review

    files = get_needs_review(conn)
    if not files:
        print("No files flagged for review.")
        conn.close()
        return

    try:
        from tabulate import tabulate
        headers = ["File ID", "Import", "Filename", "Brand", "Model", "Confidence", "Notes"]
        rows = []
        for f in files:
            rows.append([
                f["file_id"], f["import_id"],
                _truncate(f["original_filename"], 30),
                f["detected_brand"] or "?",
                f["detected_model"] or "?",
                f"{f['detection_confidence']:.2f}" if f["detection_confidence"] else "?",
                _truncate(f["processing_notes"] or "", 30),
            ])
        print(tabulate(rows, headers=headers, tablefmt="simple"))
    except ImportError:
        for f in files:
            print(
                f"  #{f['file_id']}  {f['original_filename']}  "
                f"brand={f['detected_brand']}  model={f['detected_model']}  "
                f"conf={f['detection_confidence']}"
            )

    conn.close()


def show_stats() -> None:
    """Show import statistics."""
    conn = connect_db()
    if not conn:
        print(f"{TAG_ERROR} Cannot connect to database")
        sys.exit(1)

    from db import get_import_stats

    stats = get_import_stats(conn)

    print(f"\n{Color.BOLD}Import Statistics{Color.RESET}")
    print(f"{'─' * 40}")
    print(f"  Total import jobs:     {stats['total_jobs']}")
    print(f"  Total files imported:  {stats['total_files']}")

    if stats.get("by_status"):
        print(f"\n  {Color.BOLD}By Status:{Color.RESET}")
        for status, count in sorted(stats["by_status"].items()):
            print(f"    {status:20s} {count}")

    if stats.get("by_brand"):
        print(f"\n  {Color.BOLD}By Brand:{Color.RESET}")
        for brand, count in stats["by_brand"].items():
            print(f"    {brand:20s} {count}")

    if stats.get("diagnostics"):
        print(f"\n  {Color.BOLD}Diagnostic Results:{Color.RESET}")
        for result, count in sorted(stats["diagnostics"].items()):
            print(f"    {result:10s} {count}")

    print(f"\n  Unknown fields pending: {stats.get('unknown_fields_pending', 0)}")
    print()

    conn.close()


def _truncate(s: str, max_len: int) -> str:
    """Truncate a string with ellipsis."""
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


# ─── CLI argument parsing ─────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Intelligence Catalog Importer — Bitcoin SHA-256 ASIC miner data ingestion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python importer.py /path/to/logs/
  python importer.py miner_data.zip --dry-run
  python importer.py --status
  python importer.py --review
  python importer.py --stats
        """,
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="File or folder to import",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be imported without writing to DB",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show recent import jobs",
    )
    parser.add_argument(
        "--review",
        action="store_true",
        help="Show files flagged as needs_review",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show import statistics",
    )

    args = parser.parse_args()

    # Banner
    print(f"\n{Color.BOLD}{Color.CYAN}Intelligence Catalog Importer v1.0.0{Color.RESET}")
    print(f"{Color.DIM}Bitcoin SHA-256 ASIC Miner Data Ingestion{Color.RESET}\n")

    if args.status:
        show_status()
    elif args.review:
        show_review()
    elif args.stats:
        show_stats()
    elif args.path:
        run_import(args.path, dry_run=args.dry_run)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
