#!/usr/bin/env python3
"""
run_full_import.py — Direct-script bulk re-import driver for the 131-archive
Mining Guardian re-import (2026-04-27).

Why a separate script?
----------------------
The mg_import.py Flask web UI is great for an interactive 1-3 archive test
batch — you watch SSE events scroll by and you can abort. For 131 archives
(~340 MB total) the web UI adds zero value: each archive needs the exact
same conn_params, the same Layer 2 post-processing, and we want a *single*
mg.import_runs row at the end summarising the whole batch.

This driver imports `process_archive`, `execute_sql_block`,
`detect_dormant_miners`, and `write_import_run` directly from mg_import
and runs them in a plain `for` loop. Same code paths, no Flask, no SSE
overhead, no upload-to-server round trip.

Idempotency
-----------
The importer's dedup is filename-keyed (`entity_label` UNIQUE on
`field_log_imports`, `ON CONFLICT (archive_filename, ...) DO UPDATE` on
data tables). Re-running this script over the same folder is safe — every
archive UPDATEs in place rather than creating duplicates.

Usage (from PowerShell on ROBS-PC):
-----------------------------------
    cd C:\\Users\\User\\Mining-Guardian\\mg_import_tool
    python tools/run_full_import.py `
        --archives-dir "C:\\Users\\User\\Documents\\Miner Logs" `
        --pg-host localhost --pg-port 5432 `
        --pg-user guardian_admin --pg-db mining_guardian `
        --log-file D:\\MiningGuardian\\db-backups\\pre-migration\\full_import_2026-04-27.log

The --pg-password arg is intentionally omitted; the script reads
$env:MG_DB_PASSWORD just like the web UI does.

Optional flags
--------------
    --dry-run        Generate SQL but do not execute (prints first 200 chars
                     of each block).
    --limit N        Process only the first N matching archives (for smoke
                     testing). Defaults to no limit.
    --skip-existing  Skip archives whose entity_label already exists in
                     knowledge.field_log_imports. (Off by default — the
                     importer's ON CONFLICT path handles re-imports cleanly,
                     and skipping deprives us of the chance to re-stamp
                     newly-resolved catalog_slug values.)
    --no-layer2      Do not pass conn_params into process_archive (skips
                     Layer 2 stamping/unresolved/raw_json/unknown_fields
                     post-processing). Use only if Layer 2 tables aren't
                     migrated yet.

Exit codes
----------
    0  — every archive processed without error
    1  — at least one archive failed; check the log
    2  — fatal pre-flight failure (no archives found, DB unreachable)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Path setup ──────────────────────────────────────────────────────────────
# Script lives at mg_import_tool/tools/run_full_import.py — make sure the
# parent dir (mg_import_tool/) is on sys.path so `import mg_import` works.
_HERE = Path(__file__).resolve().parent
_PARENT = _HERE.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

# ── Importer entry-points ───────────────────────────────────────────────────
# We import the public callables we need, NOT the Flask app. The module
# imports cleanly without starting the Flask server.
from mg_import import (  # type: ignore
    process_archive,
    execute_sql_block,
    detect_dormant_miners,
    write_import_run,
    _build_resolver_totals,
)

# ── Defaults ────────────────────────────────────────────────────────────────
DEFAULT_EXTENSIONS = ('.tar', '.tgz', '.tar.gz', '.rar')


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description='Mining Guardian — direct-script bulk archive importer',
    )
    p.add_argument('--archives-dir', required=True,
                   help='Directory containing the archive files to import.')
    p.add_argument('--pg-host', default='localhost')
    p.add_argument('--pg-port', type=int, default=5432)
    p.add_argument('--pg-user', default='guardian_admin')
    p.add_argument('--pg-db',   default='mining_guardian')
    p.add_argument('--log-file', default=None,
                   help='Append-mode log file. Defaults to stderr only.')
    p.add_argument('--dry-run', action='store_true',
                   help='Generate SQL but do not execute.')
    p.add_argument('--limit', type=int, default=None,
                   help='Process at most N archives (default: all).')
    p.add_argument('--skip-existing', action='store_true',
                   help='Skip archives already present in field_log_imports.')
    p.add_argument('--no-layer2', action='store_true',
                   help='Disable Layer 2 post-processing.')
    return p


def _setup_logging(log_file: str | None) -> logging.Logger:
    fmt = '%(asctime)s %(levelname)-7s %(message)s'
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, mode='a'))
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers,
                        force=True)
    return logging.getLogger('full_import')


def _discover_archives(archives_dir: Path,
                       limit: int | None) -> list[Path]:
    """Return a sorted, deduplicated list of archive paths."""
    if not archives_dir.is_dir():
        raise FileNotFoundError(f'Not a directory: {archives_dir}')
    found: list[Path] = []
    for p in archives_dir.iterdir():
        if not p.is_file():
            continue
        name_lower = p.name.lower()
        if any(name_lower.endswith(ext) for ext in DEFAULT_EXTENSIONS):
            found.append(p)
    found.sort()
    if limit is not None and limit > 0:
        found = found[:limit]
    return found


def _load_existing_filenames(conn_params: dict) -> set[str]:
    """Read knowledge.field_log_imports.archive_filename for skip-existing.

    conn_params uses mg_import's 'database' key; psycopg2 expects 'dbname',
    so we map across here.
    """
    import psycopg2  # type: ignore
    out: set[str] = set()
    pg_kwargs = {
        'host':     conn_params.get('host', 'localhost'),
        'port':     int(conn_params.get('port', 5432)),
        'dbname':   conn_params.get('database', 'mining_guardian'),
        'user':     conn_params.get('user', 'guardian_admin'),
        'password': conn_params.get('password'),
        'connect_timeout': 5,
    }
    try:
        with psycopg2.connect(**pg_kwargs) as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT archive_filename '
                            'FROM knowledge.field_log_imports')
                for (fn,) in cur.fetchall():
                    if fn:
                        out.add(fn)
    except Exception as exc:
        # Table may not exist yet (pre-bootstrap migration). Treat as empty.
        logging.warning('Could not read field_log_imports: %s', exc)
    return out


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    log = _setup_logging(args.log_file)

    pw = os.environ.get('MG_DB_PASSWORD')
    if not pw:
        log.error('MG_DB_PASSWORD env var is not set. Aborting.')
        return 2

    archives_dir = Path(args.archives_dir).expanduser().resolve()
    log.info('archives-dir = %s', archives_dir)

    try:
        archives = _discover_archives(archives_dir, args.limit)
    except Exception as exc:
        log.error('Archive discovery failed: %s', exc)
        return 2
    if not archives:
        log.error('No archives matched in %s (extensions=%s)',
                  archives_dir, DEFAULT_EXTENSIONS)
        return 2
    total = len(archives)
    log.info('Discovered %d archive(s) to process.', total)

    # NOTE: mg_import.py expects 'database' (not 'dbname') as the key. The
    # web UI's /api/test-connection and process_archive both read
    # conn_params.get('database', ...). Don't change this without grepping
    # mg_import.py first.
    conn_params = {
        'host': args.pg_host,
        'port': args.pg_port,
        'user': args.pg_user,
        'database': args.pg_db,
        'password': pw,
    }

    skip_set: set[str] = set()
    if args.skip_existing:
        skip_set = _load_existing_filenames(conn_params)
        log.info('skip-existing on; %d archive_filename(s) already imported',
                 len(skip_set))

    started_at = datetime.utcnow()
    t0 = time.monotonic()
    files_processed = 0
    files_skipped   = 0
    files_failed    = 0
    total_statements = 0
    total_rows       = 0
    error_log: list[str] = []

    layer2_conn_params = None if args.no_layer2 else conn_params

    for idx, path in enumerate(archives, 1):
        prefix = f'[{idx:>3}/{total}]'
        if path.name in skip_set:
            log.info('%s SKIP %s (already in field_log_imports)',
                     prefix, path.name)
            files_skipped += 1
            continue

        size_kb = path.stat().st_size / 1024
        log.info('%s START %s (%.1f KB)', prefix, path.name, size_kb)
        t_arc = time.monotonic()

        try:
            data = path.read_bytes()
        except Exception as exc:
            log.error('%s READ FAIL %s: %s', prefix, path.name, exc)
            files_failed += 1
            error_log.append(f'{path.name}: read failed: {exc}')
            continue

        try:
            blocks = process_archive(data, path.name, layer2_conn_params)
        except Exception as exc:
            log.exception('%s PARSE FAIL %s: %s', prefix, path.name, exc)
            files_failed += 1
            error_log.append(f'{path.name}: parse failed: {exc}')
            continue

        archive_errors = []
        archive_statements = 0
        archive_rows = 0
        for block in blocks:
            if block.startswith('-- ERROR'):
                archive_errors.append(block)
                continue
            if args.dry_run:
                snippet = block[:200].replace('\n', ' ')
                log.info('%s   [dry-run] block: %s ...', prefix, snippet)
                continue
            try:
                res = execute_sql_block(conn_params, block)
            except Exception as exc:
                archive_errors.append(f'execute_sql_block raised: {exc}')
                continue
            archive_statements += res.get('statements_run', 0)
            archive_rows       += res.get('rows_affected', 0)
            archive_errors.extend(res.get('errors', []) or [])

        elapsed = time.monotonic() - t_arc
        if archive_errors:
            files_failed += 1
            err_preview = archive_errors[0][:200]
            log.error('%s FAIL %s in %.1fs (%d errors; first: %s)',
                      prefix, path.name, elapsed, len(archive_errors),
                      err_preview)
            error_log.extend(f'{path.name}: {e}' for e in archive_errors[:5])
        else:
            files_processed += 1
            total_statements += archive_statements
            total_rows       += archive_rows
            log.info('%s OK   %s in %.1fs (statements=%d rows=%d)',
                     prefix, path.name, elapsed,
                     archive_statements, archive_rows)

    # ── Post-batch housekeeping ────────────────────────────────────────────
    if not args.dry_run:
        try:
            dormant = detect_dormant_miners(conn_params)
            log.info('Dormant detector surfaced %d miner(s) to awaiting_review',
                     dormant)
        except Exception as exc:
            log.warning('Dormant detection failed: %s', exc)

        try:
            write_import_run(
                conn_params,
                started_at=started_at,
                finished_at=datetime.utcnow(),
                archive_count=files_processed,
                row_counts={
                    'total_rows': total_rows,
                    'statements': total_statements,
                    'errors': len(error_log),
                    'resolver': _build_resolver_totals(),
                },
                errors=error_log[:50],
                status='ok' if not error_log else 'partial_failure',
            )
            log.info('Wrote summary row to mg.import_runs.')
        except Exception as exc:
            log.warning('write_import_run failed: %s', exc)

    elapsed_total = time.monotonic() - t0
    log.info('=' * 70)
    log.info('FULL IMPORT COMPLETE in %.1fs', elapsed_total)
    log.info('  Processed : %d', files_processed)
    log.info('  Skipped   : %d', files_skipped)
    log.info('  Failed    : %d', files_failed)
    log.info('  Statements: %d', total_statements)
    log.info('  Rows      : %d', total_rows)
    log.info('=' * 70)

    return 0 if files_failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
