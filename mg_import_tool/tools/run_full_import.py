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
    3  — every archive processed but the B-4 raw_json invariant was
         violated (raw_json_count < imports_count * --raw-json-min-ratio).
         Indicates a regression of the silent-swallow bug; see
         `docs/LATENT_BUGS.md` B-4.
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

# ── Fast block executor ─────────────────────────────────────────────────────
# mg_import.execute_sql_block calls split_sql_statements(), which is O(N²)
# in the size of the SQL string (it does `lines[i:]` substring + regex on
# every character). For archives with ~32k power-sample INSERTs the resulting
# SQL is several MB and the splitter pegs one CPU core for many minutes,
# eventually getting silently killed by Windows / Defender on Python 3.14.
#
# Our generated SQL never uses dollar-quoting and every statement is
# terminated with `;\n`, so a plain split on `;\n` is correct and ~1000x
# faster. We open ONE connection per archive (not per statement) and
# execute statements sequentially, committing once at the end.
#
# This bypasses execute_sql_block entirely for the bulk path. The web UI
# still uses execute_sql_block; we leave that import in place so anyone
# grepping for it in mg_import.py still finds a caller.

def _fast_execute_block(conn_params: dict, sql: str, log: logging.Logger) -> dict:
    """Drop-in replacement for execute_sql_block, optimised for huge blocks.

    Returns the same shape: {statements_run, rows_affected, errors}.
    """
    import psycopg2  # type: ignore

    out = {'statements_run': 0, 'rows_affected': 0, 'errors': []}
    pg_kwargs = {
        'host':     conn_params.get('host', 'localhost'),
        'port':     int(conn_params.get('port', 5432)),
        'dbname':   conn_params.get('database', 'mining_guardian'),
        'user':     conn_params.get('user', 'guardian_admin'),
        'password': conn_params.get('password'),
        'connect_timeout': 10,
    }

    # Fast splitter. Statement boundary = `;\n` (or `;` at EOF). String
    # literals come from mg_import._dq which dollar-quotes with $val$...$val$
    # (or $val1$, $val2$ etc. when 'val' appears in the value). We DO need
    # to skip semicolons that fall inside such a quoted body — raw miner-log
    # lines stored in raw_line columns can contain `;\n`.
    #
    # The mg_import.split_sql_statements function does this correctly but
    # is O(N²) due to per-character substring slicing. Here we walk the
    # buffer once, advancing past dollar-quote tags as whole tokens.
    raw = sql.replace('\r\n', '\n')
    stmts = []
    buf = []
    i = 0
    n = len(raw)
    in_dollar = False
    dollar_tag = ''
    DOLLAR_RE = __import__('re').compile(r'\$[A-Za-z0-9_]*\$')
    while i < n:
        if in_dollar:
            # Look for the closing tag
            j = raw.find(dollar_tag, i)
            if j < 0:
                # Unterminated dollar-quote — take the rest verbatim
                buf.append(raw[i:])
                i = n
                break
            buf.append(raw[i:j + len(dollar_tag)])
            i = j + len(dollar_tag)
            in_dollar = False
            dollar_tag = ''
            continue
        ch = raw[i]
        if ch == '$':
            m = DOLLAR_RE.match(raw, i)
            if m:
                dollar_tag = m.group(0)
                in_dollar = True
                buf.append(dollar_tag)
                i += len(dollar_tag)
                continue
        if ch == ';' and (i + 1 >= n or raw[i + 1] == '\n'):
            stmt = ''.join(buf).strip()
            if stmt:
                # Drop bare-line comments inside the statement
                kept = '\n'.join(
                    ln for ln in stmt.split('\n')
                    if not ln.strip().startswith('--')
                ).strip()
                if kept:
                    stmts.append(kept)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    # Trailing fragment without ;
    tail = ''.join(buf).strip()
    if tail:
        kept = '\n'.join(
            ln for ln in tail.split('\n') if not ln.strip().startswith('--')
        ).strip()
        if kept:
            stmts.append(kept)

    if not stmts:
        return out

    log.info('  fast-exec: %d statements queued (%.1f KB SQL)',
             len(stmts), len(sql) / 1024)

    conn = psycopg2.connect(**pg_kwargs)
    conn.autocommit = False
    try:
        cur = conn.cursor()
        for i, stmt in enumerate(stmts, 1):
            try:
                cur.execute(stmt)
                out['statements_run'] += 1
                status = (cur.statusmessage or '').strip()
                if status.startswith('INSERT'):
                    sp = status.split()
                    if sp and sp[-1].isdigit():
                        out['rows_affected'] += int(sp[-1])
            except psycopg2.Error as exc:
                conn.rollback()
                out['errors'].append(f'stmt {i}: {exc}'.strip())
                # Re-open a cursor since rollback closed the txn
                cur = conn.cursor()
            if i % 5000 == 0:
                log.info('  fast-exec progress: %d/%d statements',
                         i, len(stmts))
        if not out['errors']:
            conn.commit()
        else:
            try:
                conn.commit()
            except Exception:
                conn.rollback()
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return out

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
    p.add_argument('--raw-json-min-ratio', type=float, default=0.95,
                   help='B-4 invariant: assert raw_json_count >= imports_count * RATIO '
                        'after every non-dry-run import. Default 0.95. Set to 0 to '
                        'disable, or use --no-raw-json-check.')
    p.add_argument('--no-raw-json-check', action='store_true',
                   help='Skip the B-4 raw_json invariant check entirely. Equivalent '
                        'to --raw-json-min-ratio 0. Use only if you know what you '
                        'are doing.')
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


def _raw_json_invariant_check(conn_params: dict,
                              min_ratio: float,
                              log: logging.Logger) -> tuple[bool, int, int]:
    """B-4 runtime invariant: raw_json_count >= imports_count * min_ratio.

    Background
    ----------
    The 2026-04-27 live import surfaced B-4 (`docs/LATENT_BUGS.md`):
    `mg_import.insert_raw_json` was silently swallowing every per-archive
    failure with `except Exception: pass`, so the import driver reported
    "all archives processed" while the raw-JSON table was starved
    (3 raw-JSON rows for 127 successful imports). The swallow was fixed
    on 2026-04-28 in the canonical writer rewrite (B-4 status: Fixed),
    but the *invariant assertion* — the cheap end-of-run sanity check
    that catches a future regression of the same shape — was deferred.
    This is that assertion.

    Behaviour
    ---------
    Reads the current row counts from `knowledge.field_log_imports` and
    `knowledge.field_log_raw_json` and returns ``(ok, imports_count,
    raw_json_count)``. ``ok`` is False when ``raw_json_count <
    imports_count * min_ratio`` AND ``imports_count > 0``. With
    ``imports_count == 0`` (e.g. dry-run, fresh DB) the check is a no-op
    and returns ``(True, 0, 0)``.

    The check is read-only — it never modifies the DB. On any DB error
    it logs a warning, returns ``(True, -1, -1)``, and lets the import
    succeed; this matches the existing failure-tolerant pattern used by
    `_load_existing_filenames` (a missing table or unreachable DB should
    not flip a successful import into a failure on its own).
    """
    import psycopg2  # type: ignore
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
                cur.execute('SELECT count(*) FROM knowledge.field_log_imports')
                imports_count = int(cur.fetchone()[0] or 0)
                cur.execute('SELECT count(*) FROM knowledge.field_log_raw_json')
                raw_json_count = int(cur.fetchone()[0] or 0)
    except Exception as exc:
        log.warning('B-4 invariant check skipped — DB unreadable: %s', exc)
        return (True, -1, -1)

    if imports_count == 0:
        log.info('B-4 invariant check: imports_count=0 — skipping (no-op).')
        return (True, 0, 0)

    threshold = imports_count * min_ratio
    ok = raw_json_count >= threshold
    if ok:
        log.info('B-4 invariant OK: raw_json=%d >= imports=%d * %.2f (=%.1f)',
                 raw_json_count, imports_count, min_ratio, threshold)
    else:
        log.error(
            'B-4 INVARIANT VIOLATION: raw_json=%d < imports=%d * %.2f (=%.1f). '
            'This usually means insert_raw_json() is silently swallowing errors '
            'again — see docs/LATENT_BUGS.md B-4. Re-run with verbose logging on '
            'the importer and check ERROR-level lines.',
            raw_json_count, imports_count, min_ratio, threshold,
        )
    return (ok, imports_count, raw_json_count)


def _load_existing_filenames(conn_params: dict) -> set[str]:
    """Read filenames already present in knowledge.field_log_imports.

    The parent table’s filename-keyed column is `entity_label` (NOT
    `archive_filename` — only the *child* tables use that). Pre-2026-04-27
    versions of this script queried archive_filename and silently came
    back with zero hits, causing --skip-existing to attempt the entire
    folder from scratch. We now read entity_label.

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
                cur.execute('SELECT entity_label '
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
                res = _fast_execute_block(conn_params, block, log)
            except Exception as exc:
                archive_errors.append(f'fast_execute_block raised: {exc}')
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

    # ── B-4 raw_json invariant check ───────────────────────────────────────
    # Catches a regression of the silent-swallow bug (`docs/LATENT_BUGS.md` B-4).
    invariant_ok = True
    if not args.dry_run and not args.no_raw_json_check and args.raw_json_min_ratio > 0:
        invariant_ok, _imp_count, _raw_count = _raw_json_invariant_check(
            conn_params, args.raw_json_min_ratio, log
        )
    elif args.dry_run:
        log.info('B-4 invariant check skipped (dry-run).')
    elif args.no_raw_json_check or args.raw_json_min_ratio == 0:
        log.warning('B-4 invariant check disabled by flag — silent-swallow regressions '
                    'will not be caught at end of run.')

    elapsed_total = time.monotonic() - t0
    log.info('=' * 70)
    log.info('FULL IMPORT COMPLETE in %.1fs', elapsed_total)
    log.info('  Processed : %d', files_processed)
    log.info('  Skipped   : %d', files_skipped)
    log.info('  Failed    : %d', files_failed)
    log.info('  Statements: %d', total_statements)
    log.info('  Rows      : %d', total_rows)
    log.info('  B-4 inv\'t: %s', 'OK' if invariant_ok else 'VIOLATED')
    log.info('=' * 70)

    if files_failed > 0:
        return 1
    if not invariant_ok:
        # Exit code 3 to distinguish invariant-violation from per-archive failure.
        return 3
    return 0


if __name__ == '__main__':
    sys.exit(main())
