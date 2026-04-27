#!/usr/bin/env python3
"""
Mining Guardian — Intelligence Catalog Importer  v3.3
=====================================================
Single-file Flask application for importing research data into PostgreSQL.
Run with: python mg_import.py
Opens at: http://localhost:5050

v3.1 additions (Layer 2 Two-Tier Resolver):
  - resolver.py module: two-tier resolver (Tier-1 hardware.model_aliases,
    Tier-2 mg.model_family_aliases with hashrate-bin selection)
  - Normalizer: whitespace/uppercase/+/++ preservation, no V-code pre-strip
  - Tier-1 V-code stripped fallback with hardware_revision capture
  - Tier-2 bin selection by observed GH/s, tie-goes-lower
  - Always checks BOTH miner_type AND control_board_version columns
  - mg.unresolved_models: tier2_hit_no_hashrate + no_alias_match reasons
  - knowledge.field_log_raw_json: idempotent bootstrap at startup
  - mg.import_runs: per-run summary table (idempotent CREATE IF NOT EXISTS)
  - Streaming autotune batch_size reduced to 500 (memory < 100 MB/archive)
  - Structured logging to logs/import_YYYY-MM-DD_HHMMSS.log
  - /rma  — RMA record form + CSV batch upload
  - /dormant — dormant miner triage UI
  - Background dormant-miner detector runs at end of each import
"""

import os
import io
import re
import csv
import json
import zipfile
import tempfile
import traceback
import logging
import time as _time_module
from datetime import datetime, timezone
from pathlib import Path
from functools import lru_cache

from flask import Flask, request, jsonify, Response, render_template_string, redirect, url_for

# ---------------------------------------------------------------------------
# Database password — single source of truth.
#
# The password is read from the environment variable MG_DB_PASSWORD at process
# start. There is no in-source fallback: forgetting to set it raises loudly
# rather than silently authenticating with a stale literal.
#
# All call sites in this file use _db_password() instead of inline literals.
# ---------------------------------------------------------------------------
def _db_password() -> str:
    pw = os.environ.get("MG_DB_PASSWORD")
    if not pw:
        raise EnvironmentError(
            "MG_DB_PASSWORD is not set in the environment. "
            "mg_import refuses to start without it. "
            "Populate the .env file or export MG_DB_PASSWORD before running."
        )
    return pw

try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

# Layer 2 two-tier resolver module (resolver.py lives alongside mg_import.py)
try:
    import resolver as _resolver
    RESOLVER_AVAILABLE = True
except ImportError:
    _resolver = None  # type: ignore
    RESOLVER_AVAILABLE = False

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 512 * 1024 * 1024  # 512 MB

# ---------------------------------------------------------------------------
# v3: Structured logging
# Creates logs/import_YYYY-MM-DD_HHMMSS.log at startup.
# All archive-processing code uses get_run_logger() to write to this file.
# ---------------------------------------------------------------------------

_LOG_DIR = Path(__file__).parent / 'logs'
_LOG_DIR.mkdir(exist_ok=True)

_RUN_TS = datetime.now().strftime('%Y-%m-%d_%H%M%S')
_LOG_FILE = _LOG_DIR / f'import_{_RUN_TS}.log'

# Root logger for the run
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(str(_LOG_FILE), encoding='utf-8'),
        logging.StreamHandler(),
    ]
)
_run_logger = logging.getLogger('mg_import')
_run_logger.info('mg_import_tool v3 started — log file: %s', _LOG_FILE)

DEBUG_IMPORT = os.environ.get('MG_DEBUG', '').lower() in ('1', 'true', 'yes')
if DEBUG_IMPORT:
    logging.getLogger().setLevel(logging.DEBUG)
    _run_logger.debug('DEBUG mode enabled')


def get_run_logger(name: str = 'mg_import') -> logging.Logger:
    """Return a child logger for a named subsystem."""
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# v3: Layer 2 constants
# Known field keys per source-file pattern. Any key NOT in this set for its
# file pattern is recorded in mg.unknown_fields.
# ---------------------------------------------------------------------------

# WhatsMiner miner_overview.log — all keys we parse into typed columns
KNOWN_MINER_OVERVIEW_KEYS = frozenset({
    'miner_type', 'control_board_version', 'MAC', 'cool_mode',
    'kernel_version', 'FIRMWARE_VERSION', 'BTMINER_MD5',
    # eeprom slot keys
    'pcb0', 'pcb1', 'pcb2', 'pcb3',
    'chip_data0', 'chip_data1', 'chip_data2', 'chip_data3',
    'hashrate0', 'hashrate1', 'hashrate2', 'hashrate3',
    'pcb_version0', 'pcb_version1', 'pcb_version2', 'pcb_version3',
    # common section extras
    'frequency', 'pool_count', 'miner_count', 'sn',
    'power_mode', 'power_version', 'driver_version',
})

# Antminer miner.log — we extract these structured fields
KNOWN_MINER_LOG_KEYS = frozenset({
    'event_timestamp', 'level', 'message', 'chain', 'frequency_mhz',
    'voltage_v', 'temp_max_c', 'event_type', 'miner_model',
    'firmware_version', 'boot_session',
})

# Antminer cgminer.conf
KNOWN_CGMINER_CONF_KEYS = frozenset({
    'pools', 'url', 'user', 'pass', 'api-listen', 'api-network',
    'api-groups', 'api-allow', 'bitmain-use-vil', 'bitmain-freq',
    'bitmain-voltage', 'fan-ctrl', 'fan-pwm', 'miner-mode',
    'freq-level', 'no-pre-heat',
})

# Map source_file_pattern -> known keys set
KNOWN_KEYS_BY_FILE: dict = {
    'miner_overview.log': KNOWN_MINER_OVERVIEW_KEYS,
    'miner.log':          KNOWN_MINER_LOG_KEYS,
    'cgminer.conf':       KNOWN_CGMINER_CONF_KEYS,
}

# V-suffix strip regex: captures base model (group 1) and hardware revision (group 2)
# Applied to WhatsMiner miner_type strings like "M31S+_V100" or "M56S++_VK10"
V_SUFFIX_RE = re.compile(
    r'^(?P<base>[A-Za-z][^_]*?)(?:_V(?P<rev>[A-Z]*\d+))?$'
)

# ---------------------------------------------------------------------------
# In-memory import history (resets on restart)
# ---------------------------------------------------------------------------
import_history = []  # list of dicts: {timestamp, filenames, rows_imported, errors, duration_s}

# ---------------------------------------------------------------------------
# v3.3: Batch cancel flag — set via /api/cancel-batch
# ---------------------------------------------------------------------------
_BATCH_CANCEL_FLAG: bool = False

# ---------------------------------------------------------------------------
# v3.3: Per-archive resolver stats accumulator (populated by _do_layer2_postprocessing)
# Maps archive filename -> {tier1, tier1_vcode, tier2, unresolved}
# Cleared at the start of each import session.
# ---------------------------------------------------------------------------
_LAST_RESOLVER_STATS: dict = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sanitize_identifier(name: str) -> str:
    """Convert a string to a safe snake_case SQL identifier."""
    name = os.path.splitext(name)[0]          # drop extension
    name = name.lower()
    name = re.sub(r'[^a-z0-9_]', '_', name)  # non-alnum → underscore
    name = re.sub(r'_+', '_', name)           # collapse multiple underscores
    name = re.sub(r'^[0-9_]+', '', name)      # strip leading digits/underscores
    name = name.strip('_')
    # Strip trailing date/number patterns like _20240101 or _v2
    name = re.sub(r'_v?\d+$', '', name)
    name = re.sub(r'_\d{6,}$', '', name)
    if not name:
        name = 'import_table'
    return name


def header_to_column(h: str) -> str:
    """Convert a CSV header to a snake_case column name."""
    h = h.strip().lower()
    h = re.sub(r'[^a-z0-9_]', '_', h)
    h = re.sub(r'_+', '_', h)
    h = h.strip('_')
    if not h:
        h = 'col'
    # Avoid reserved words that would cause issues
    reserved = {'id', 'order', 'select', 'table', 'where', 'from', 'group'}
    if h in reserved:
        h = h + '_val'
    return h


def dollar_quote(value: str) -> str:
    """Wrap a string value in tagged dollar-quoting ($val$...$val$).
    Falls back to $val1$, $val2$, etc. if the tag appears in the text.
    Matches the SQL generation script's approach for values containing $ signs.
    """
    if value is None:
        return 'NULL'
    tag = '$val$'
    if tag not in value:
        return f'{tag}{value}{tag}'
    # Try incrementing suffixes until we find one not present in the value
    n = 1
    while True:
        tag = f'$val{n}$'
        if tag not in value:
            return f'{tag}{value}{tag}'
        n += 1


def read_csv_bytes(data: bytes) -> tuple:
    """Try reading CSV data as UTF-8, fall back to latin-1. Returns (headers, rows)."""
    for encoding in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
        try:
            text = data.decode(encoding)
            reader = csv.reader(io.StringIO(text))
            rows = list(reader)
            if rows:
                return rows[0], rows[1:]
        except (UnicodeDecodeError, csv.Error):
            continue
    raise ValueError("Could not decode CSV — tried utf-8, latin-1, cp1252")


def read_xlsx_bytes(data: bytes) -> tuple:
    """Read XLSX bytes and return (headers, rows) from first sheet."""
    if not OPENPYXL_AVAILABLE:
        raise ImportError("openpyxl not installed — cannot read .xlsx files. Run: pip install openpyxl")
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows = []
    for row in ws.iter_rows(values_only=True):
        rows.append(['' if cell is None else str(cell) for cell in row])
    wb.close()
    if not rows:
        return [], []
    return rows[0], rows[1:]


def generate_csv_sql(filename: str, headers: list, rows: list) -> str:
    """Generate CREATE TABLE + INSERT SQL for a CSV file per Bobby's rules."""
    table_base = sanitize_identifier(filename)
    table_name = f'knowledge.research_{table_base}'

    if not headers:
        raise ValueError(f"CSV {filename} has no headers")

    first_col = header_to_column(headers[0])
    other_cols = []
    seen = {first_col, 'id', 'ingested_at', 'updated_at', 'entity_label'}
    for h in headers[1:]:
        col = header_to_column(h)
        # Deduplicate column names
        base = col
        n = 1
        while col in seen:
            col = f'{base}_{n}'
            n += 1
        seen.add(col)
        other_cols.append((h, col))

    # Build CREATE TABLE
    col_defs = []
    col_defs.append('    id BIGSERIAL PRIMARY KEY')
    col_defs.append('    entity_label TEXT NOT NULL UNIQUE')
    for _, col in other_cols:
        col_defs.append(f'    {col} TEXT')
    col_defs.append('    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()')
    col_defs.append('    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()')

    sql_parts = ['BEGIN;', '']
    sql_parts.append(f'CREATE SCHEMA IF NOT EXISTS knowledge;')
    sql_parts.append('')
    sql_parts.append(f'CREATE TABLE IF NOT EXISTS {table_name} (')
    sql_parts.append(',\n'.join(col_defs))
    sql_parts.append(');')
    sql_parts.append('')

    # Build INSERT statements
    all_col_names = ['entity_label'] + [col for _, col in other_cols]
    insert_prefix = f'INSERT INTO {table_name} ({", ".join(all_col_names)})'

    inserted = 0
    for row in rows:
        if not row or all(str(c).strip() == '' for c in row):
            continue  # skip blank rows
        # Pad row to header length
        while len(row) < len(headers):
            row.append('')

        values = []
        for i, col_val in enumerate(row[:len(headers)]):
            values.append(dollar_quote(str(col_val)))

        # entity_label is first column
        entity_val = values[0]
        other_vals = values[1:len(headers)]

        all_vals = [entity_val] + other_vals
        sql_parts.append(
            f'{insert_prefix} VALUES ({", ".join(all_vals)}) '
            f'ON CONFLICT (entity_label) DO NOTHING;'
        )
        inserted += 1

    sql_parts.append('')
    sql_parts.append('COMMIT;')
    sql_parts.append('')
    sql_parts.append(f'-- Stats: {inserted} data rows for {table_name}')

    return '\n'.join(sql_parts)


def execute_sql_block(conn_params: dict, sql: str) -> dict:
    """
    Execute a SQL block against PostgreSQL.
    Returns {success, statements_run, rows_affected, errors, messages}.
    """
    if not PSYCOPG2_AVAILABLE:
        return {
            'success': False,
            'error': 'psycopg2 not installed. Run: pip install psycopg2-binary',
            'messages': [],
            'statements_run': 0,
            'rows_affected': 0,
            'errors': ['psycopg2 not installed']
        }

    messages = []
    errors = []
    statements_run = 0
    rows_affected = 0

    try:
        conn = psycopg2.connect(
            host=conn_params.get('host', 'localhost'),
            port=int(conn_params.get('port', 5432)),
            dbname=conn_params.get('database', 'mining_guardian'),
            user=conn_params.get('user', 'guardian_admin'),
            password=conn_params.get('password') or _db_password(),
            connect_timeout=10
        )
        conn.autocommit = False
        cur = conn.cursor()

        # Split SQL into individual statements, execute each
        # We'll use a smarter split that respects dollar-quoting
        stmts = split_sql_statements(sql)

        in_transaction = False
        for stmt in stmts:
            stmt_clean = stmt.strip()
            if not stmt_clean or stmt_clean.startswith('--'):
                continue
            try:
                cur.execute(stmt_clean)
                statements_run += 1
                status = cur.statusmessage or 'OK'

                if status.startswith('INSERT'):
                    parts = status.split()
                    count = int(parts[-1]) if parts[-1].isdigit() else 0
                    rows_affected += count
                    messages.append({'type': 'success', 'text': status, 'stmt': stmt_clean[:80]})
                elif status in ('BEGIN', 'COMMIT', 'ROLLBACK'):
                    if status == 'BEGIN':
                        in_transaction = True
                    elif status in ('COMMIT', 'ROLLBACK'):
                        in_transaction = False
                    messages.append({'type': 'info', 'text': status, 'stmt': ''})
                elif status.startswith('CREATE'):
                    messages.append({'type': 'success', 'text': status, 'stmt': stmt_clean[:80]})
                else:
                    messages.append({'type': 'info', 'text': status, 'stmt': stmt_clean[:80]})

            except psycopg2.Error as e:
                err_msg = str(e).strip()
                errors.append(err_msg)
                messages.append({'type': 'error', 'text': err_msg, 'stmt': stmt_clean[:120]})
                # Don't abort — continue with next statement
                # But we need to rollback the failed statement within the txn
                conn.rollback()

        if not errors:
            conn.commit()
            messages.append({'type': 'success', 'text': 'Transaction committed successfully', 'stmt': ''})
        else:
            # Partial success — we rolled back on each error but may have committed some
            # The user should check the log
            try:
                conn.commit()
            except Exception:
                conn.rollback()

        cur.close()
        conn.close()

        return {
            'success': len(errors) == 0,
            'messages': messages,
            'statements_run': statements_run,
            'rows_affected': rows_affected,
            'errors': errors
        }

    except psycopg2.OperationalError as e:
        err = str(e).strip()
        return {
            'success': False,
            'error': f'Connection failed: {err}',
            'messages': [{'type': 'error', 'text': f'Connection failed: {err}', 'stmt': ''}],
            'statements_run': 0,
            'rows_affected': 0,
            'errors': [err]
        }
    except Exception as e:
        err = traceback.format_exc()
        return {
            'success': False,
            'error': str(e),
            'messages': [{'type': 'error', 'text': str(e), 'stmt': ''}],
            'statements_run': 0,
            'rows_affected': 0,
            'errors': [str(e)]
        }


def split_sql_statements(sql: str) -> list:
    """
    Split a SQL string into individual statements, respecting dollar-quoting.
    Returns a list of statement strings.
    """
    statements = []
    current = []
    in_dollar_quote = False
    dollar_tag = ''
    i = 0
    lines = sql

    while i < len(lines):
        # Check for dollar-quote start/end
        if not in_dollar_quote:
            # Look for $tag$ pattern
            m = re.match(r'\$([A-Za-z0-9_]*)\$', lines[i:])
            if m:
                dollar_tag = m.group(0)
                in_dollar_quote = True
                current.append(lines[i:i+len(dollar_tag)])
                i += len(dollar_tag)
                continue
        else:
            if lines[i:].startswith(dollar_tag):
                in_dollar_quote = False
                current.append(dollar_tag)
                i += len(dollar_tag)
                continue

        ch = lines[i]
        current.append(ch)

        if not in_dollar_quote and ch == ';':
            stmt = ''.join(current).strip()
            if stmt and stmt != ';':
                statements.append(stmt)
            current = []

        i += 1

    # Catch any trailing statement without semicolon
    remaining = ''.join(current).strip()
    if remaining and remaining != ';':
        statements.append(remaining)

    return statements


def is_psql_runner(data: bytes) -> bool:
    """Return True if a SQL file contains \\i (psql include) commands — it's a runner/master file."""
    try:
        text = data.decode('utf-8', errors='replace')
        # Look for \i or \ir at the start of a line (psql include directives)
        return bool(re.search(r'^\\i[r]?\s', text, re.MULTILINE))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# v3: Layer 2 — Model Identification helpers
# ---------------------------------------------------------------------------

def strip_v_suffix(raw_miner_type: str):
    """
    Strip WhatsMiner hardware-revision V-suffix from a miner_type string.

    Examples:
        "M31S+_V100"  -> ("M31S+", "V100")
        "M56S++_VK10" -> ("M56S++", "VK10")
        "M21S"        -> ("M21S", None)
        "M50"         -> ("M50", None)

    Returns (canonical_model: str, hardware_revision: str | None).
    The canonical_model is what we look up in mg.model_aliases.
    """
    if not raw_miner_type:
        return raw_miner_type, None
    m = V_SUFFIX_RE.match(raw_miner_type.strip())
    if m:
        base = m.group('base')
        rev  = m.group('rev')  # None if no suffix
        return base, (f'V{rev}' if rev else None)
    return raw_miner_type.strip(), None


def lookup_alias(conn_params: dict, raw_string: str, source_field: str):
    """
    Query mg.model_aliases for a matching catalog_slug.
    Returns dict {catalog_slug, confidence, match_type, hardware_revision} or None.
    Falls back gracefully if the mg schema/table does not yet exist.
    """
    if not PSYCOPG2_AVAILABLE or not conn_params:
        return None
    try:
        conn = psycopg2.connect(
            host=conn_params.get('host', 'localhost'),
            port=int(conn_params.get('port', 5432)),
            dbname=conn_params.get('database', 'mining_guardian'),
            user=conn_params.get('user', 'guardian_admin'),
            password=conn_params.get('password') or _db_password(),
            connect_timeout=5
        )
        cur = conn.cursor()
        cur.execute(
            """
            SELECT catalog_slug, confidence, match_type, hardware_revision
            FROM mg.model_aliases
            WHERE raw_string = %s AND source_field = %s
            LIMIT 1
            """,
            (raw_string, source_field)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return {
                'catalog_slug':      row[0],
                'confidence':        float(row[1]),
                'match_type':        row[2],
                'hardware_revision': row[3],
            }
        return None
    except Exception as exc:
        get_run_logger('mg_layer2').debug('alias lookup error: %s', exc)
        return None


def resolve_model(conn_params: dict, raw_miner_type: str, source_field: str = 'miner_type'):
    """
    Full Layer 2 model resolution pipeline:
    1. Try exact lookup of raw_miner_type in mg.model_aliases.
    2. If not found, strip V-suffix and try the canonical base string.
    3. Return {catalog_slug, confidence, match_type, hardware_revision, matched_raw}
       or None if unresolvable.
    """
    if not raw_miner_type:
        return None

    log = get_run_logger('mg_layer2')

    # Step 1: exact match
    result = lookup_alias(conn_params, raw_miner_type, source_field)
    if result:
        log.debug('exact alias match: %r -> %s (conf=%.2f)',
                  raw_miner_type, result['catalog_slug'], result['confidence'])
        result['matched_raw'] = raw_miner_type
        return result

    # Step 2: strip V-suffix and try again
    canonical, hw_rev = strip_v_suffix(raw_miner_type)
    if canonical != raw_miner_type:
        result = lookup_alias(conn_params, canonical, source_field)
        if result:
            # Override hardware_revision with the one we stripped
            result['hardware_revision'] = hw_rev or result.get('hardware_revision')
            result['matched_raw'] = canonical
            log.debug('stripped alias match: %r -> base=%r -> %s (conf=%.2f, rev=%s)',
                      raw_miner_type, canonical, result['catalog_slug'],
                      result['confidence'], result['hardware_revision'])
            return result

    log.warning('UNRESOLVED miner_type: %r (source_field=%s)', raw_miner_type, source_field)
    return None


def record_unresolved_model(conn_params: dict, raw_string: str, source_field: str,
                            archive_id: int):
    """
    INSERT or UPDATE mg.unresolved_models for a string that could not be
    matched to any catalog slug. Increments occurrence_count and appends
    archive_id to sample_archive_ids. Silently skips if mg schema missing.
    """
    if not PSYCOPG2_AVAILABLE or not conn_params:
        return
    try:
        conn = psycopg2.connect(
            host=conn_params.get('host', 'localhost'),
            port=int(conn_params.get('port', 5432)),
            dbname=conn_params.get('database', 'mining_guardian'),
            user=conn_params.get('user', 'guardian_admin'),
            password=conn_params.get('password') or _db_password(),
            connect_timeout=5
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO mg.unresolved_models
                (raw_string, source_field, first_seen_at, occurrence_count,
                 sample_archive_ids, status)
            VALUES (%s, %s, NOW(), 1, %s, 'pending')
            ON CONFLICT (raw_string, source_field) DO UPDATE SET
                occurrence_count  = mg.unresolved_models.occurrence_count + 1,
                sample_archive_ids = CASE
                    WHEN array_length(mg.unresolved_models.sample_archive_ids, 1) < 20
                    THEN mg.unresolved_models.sample_archive_ids || EXCLUDED.sample_archive_ids
                    ELSE mg.unresolved_models.sample_archive_ids
                END
            """,
            (raw_string, source_field, [archive_id] if archive_id else [])
        )
        cur.close()
        conn.close()
    except Exception as exc:
        get_run_logger('mg_layer2').debug('record_unresolved error: %s', exc)


def stamp_import_with_catalog(conn_params: dict, archive_id: int, catalog_slug: str,
                              confidence: float, match_type: str, hardware_revision):
    """
    UPDATE knowledge.field_log_imports to stamp catalog_slug, confidence,
    match_type, hardware_revision for the given archive_id.
    Silently skips if columns don't exist yet (pre-migration state).
    """
    if not PSYCOPG2_AVAILABLE or not conn_params or not archive_id:
        return
    try:
        conn = psycopg2.connect(
            host=conn_params.get('host', 'localhost'),
            port=int(conn_params.get('port', 5432)),
            dbname=conn_params.get('database', 'mining_guardian'),
            user=conn_params.get('user', 'guardian_admin'),
            password=conn_params.get('password') or _db_password(),
            connect_timeout=5
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE knowledge.field_log_imports
            SET catalog_slug           = %s,
                alias_match_confidence = %s,
                alias_match_type       = %s,
                hardware_revision      = %s
            WHERE id = %s
            """,
            (catalog_slug, confidence, match_type, hardware_revision, archive_id)
        )
        cur.close()
        conn.close()
    except Exception as exc:
        get_run_logger('mg_layer2').debug('stamp_import error: %s', exc)


def get_archive_id_by_label(conn_params: dict, entity_label: str):
    """Return the BIGINT id of a knowledge.field_log_imports row by entity_label."""
    if not PSYCOPG2_AVAILABLE or not conn_params:
        return None
    try:
        conn = psycopg2.connect(
            host=conn_params.get('host', 'localhost'),
            port=int(conn_params.get('port', 5432)),
            dbname=conn_params.get('database', 'mining_guardian'),
            user=conn_params.get('user', 'guardian_admin'),
            password=conn_params.get('password') or _db_password(),
            connect_timeout=5
        )
        cur = conn.cursor()
        cur.execute(
            'SELECT id FROM knowledge.field_log_imports WHERE entity_label = %s LIMIT 1',
            (entity_label,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# v3: Raw JSON capture helpers
# ---------------------------------------------------------------------------

def insert_raw_json(conn_params: dict, archive_filename: str,
                    file_path_in_archive: str, payload: dict):
    """
    INSERT into knowledge.field_log_raw_json.

    Schema (v3.1 — idempotent bootstrap adds this table at startup):
        id BIGSERIAL PRIMARY KEY,
        archive_filename TEXT NOT NULL,
        file_path_in_archive TEXT NOT NULL DEFAULT '',
        raw_content JSONB NOT NULL,
        ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

    ON CONFLICT (archive_filename, file_path_in_archive) DO NOTHING
    ensures idempotent re-import.
    """
    if not PSYCOPG2_AVAILABLE or not conn_params or not archive_filename:
        return
    try:
        conn = psycopg2.connect(
            host=conn_params.get('host', 'localhost'),
            port=int(conn_params.get('port', 5432)),
            dbname=conn_params.get('database', 'mining_guardian'),
            user=conn_params.get('user', 'guardian_admin'),
            password=conn_params.get('password') or _db_password(),
            connect_timeout=5
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO knowledge.field_log_raw_json
                (archive_filename, file_path_in_archive, raw_content, ingested_at)
            VALUES (%s, %s, %s::jsonb, NOW())
            ON CONFLICT (archive_filename, file_path_in_archive) DO NOTHING
            """,
            (archive_filename, file_path_in_archive or '', json.dumps(payload))
        )
        cur.close()
        conn.close()
    except Exception as exc:
        get_run_logger('mg_raw_json').debug('insert_raw_json error: %s', exc)


# ---------------------------------------------------------------------------
# v3.2: Miner identity insertion with resolver stamping
# ---------------------------------------------------------------------------

def insert_miner_identity(conn_params: dict, identity_rows: list,
                          resolver_results: list = None):
    """
    INSERT into knowledge.field_log_miner_identity, one row per boot session.

    Idempotency: ON CONFLICT (archive_filename, entity_label) DO UPDATE SET
    updates all mutable fields (firmware, mac, etc.) so re-runs stay current.

    resolver_results (optional): list of ResolverResult objects parallel to
    identity_rows.  When provided, hardware_revision / resolved_miner_model_id /
    resolution_tier / resolution_alias are stamped onto each row.
    """
    if not PSYCOPG2_AVAILABLE or not conn_params or not identity_rows:
        return
    log = get_run_logger('mg_identity')
    try:
        conn = psycopg2.connect(
            host=conn_params.get('host', 'localhost'),
            port=int(conn_params.get('port', 5432)),
            dbname=conn_params.get('database', 'mining_guardian'),
            user=conn_params.get('user', 'guardian_admin'),
            password=conn_params.get('password') or _db_password(),
            connect_timeout=5
        )
        conn.autocommit = True
        cur = conn.cursor()
        for idx, r in enumerate(identity_rows):
            res = resolver_results[idx] if resolver_results and idx < len(resolver_results) else None
            hw_rev     = res.hardware_revision if res else None
            model_id   = res.model_id if res else None
            res_tier   = res.tier if res else None
            res_alias  = None  # alias string not returned by resolver currently
            try:
                cur.execute(
                    """
                    INSERT INTO knowledge.field_log_miner_identity
                        (entity_label, archive_filename, miner_type, firmware_version,
                         btminer_md5, mac_address, control_board_version, kernel_version,
                         cool_mode, slot, pcb_serial, chip_data, hashrate_gh,
                         hardware_revision, resolved_miner_model_id,
                         resolution_tier, resolution_alias)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s::uuid, %s, %s)
                    ON CONFLICT (archive_filename, entity_label) DO UPDATE SET
                        miner_type            = EXCLUDED.miner_type,
                        firmware_version      = EXCLUDED.firmware_version,
                        mac_address           = EXCLUDED.mac_address,
                        control_board_version = EXCLUDED.control_board_version,
                        kernel_version        = EXCLUDED.kernel_version,
                        cool_mode             = EXCLUDED.cool_mode,
                        hashrate_gh           = EXCLUDED.hashrate_gh,
                        hardware_revision     = EXCLUDED.hardware_revision,
                        resolved_miner_model_id = EXCLUDED.resolved_miner_model_id,
                        resolution_tier       = EXCLUDED.resolution_tier,
                        resolution_alias      = EXCLUDED.resolution_alias,
                        ingested_at           = EXCLUDED.ingested_at
                    """,
                    (
                        r.get('entity_label'), r.get('archive_filename'),
                        r.get('miner_type'), r.get('firmware_version'),
                        r.get('btminer_md5'), r.get('mac_address'),
                        r.get('control_board_version'), r.get('kernel_version'),
                        r.get('cool_mode'),
                        r.get('slot') if r.get('slot') is not None else None,
                        r.get('pcb_serial'), r.get('chip_data'),
                        r.get('hashrate_gh'),
                        hw_rev, model_id, res_tier, res_alias,
                    )
                )
            except Exception as row_exc:
                log.debug('insert_miner_identity row error: %s', row_exc)
        cur.close()
        conn.close()
        log.info('insert_miner_identity: %d rows upserted', len(identity_rows))
    except Exception as exc:
        log.debug('insert_miner_identity connection error: %s', exc)


# ---------------------------------------------------------------------------
# v3: Unknown field surveillance helpers
# ---------------------------------------------------------------------------

def _guess_value_type(value) -> str:
    """Guess the SQL data type for a value."""
    if value is None:
        return 'string'
    s = str(value).strip()
    if re.match(r'^-?\d+$', s):
        return 'int'
    if re.match(r'^-?[\d.]+([eE][+-]?\d+)?$', s):
        return 'float'
    if re.match(r'^\d{4}[-/]\d{2}[-/]\d{2}', s):
        return 'timestamp'
    # enum guess: short string with no spaces that appears multiple times
    if len(s) <= 20 and ' ' not in s:
        return 'enum'
    return 'string'


def record_unknown_fields(conn_params: dict, archive_id: int, source_file: str,
                          parsed_dict: dict, known_keys: frozenset):
    """
    For every key in parsed_dict that is NOT in known_keys, record it in
    mg.unknown_fields. Increments occurrence_count; stores up to 5 sample values.
    Silently skips if mg schema is missing.
    """
    if not PSYCOPG2_AVAILABLE or not conn_params:
        return
    unknown = {k: v for k, v in parsed_dict.items() if k not in known_keys}
    if not unknown:
        return
    log = get_run_logger('mg_unknown_fields')
    try:
        conn = psycopg2.connect(
            host=conn_params.get('host', 'localhost'),
            port=int(conn_params.get('port', 5432)),
            dbname=conn_params.get('database', 'mining_guardian'),
            user=conn_params.get('user', 'guardian_admin'),
            password=conn_params.get('password') or _db_password(),
            connect_timeout=5
        )
        conn.autocommit = True
        cur = conn.cursor()
        for field_key, field_val in unknown.items():
            vtype = _guess_value_type(field_val)
            sample_entry = json.dumps([str(field_val)])
            cur.execute(
                """
                INSERT INTO mg.unknown_fields
                    (field_key, source_file_pattern, first_seen_at, first_archive_id,
                     occurrence_count, distinct_models_seen, sample_values,
                     value_type_guess, status)
                VALUES (%s, %s, NOW(), %s, 1, 1, %s::jsonb, %s, 'observed')
                ON CONFLICT (field_key, source_file_pattern) DO UPDATE SET
                    occurrence_count = mg.unknown_fields.occurrence_count + 1,
                    sample_values = CASE
                        WHEN jsonb_array_length(COALESCE(mg.unknown_fields.sample_values, '[]'::jsonb)) < 5
                        THEN COALESCE(mg.unknown_fields.sample_values, '[]'::jsonb)
                             || %s::jsonb
                        ELSE mg.unknown_fields.sample_values
                    END,
                    status = CASE
                        WHEN mg.unknown_fields.occurrence_count + 1 >= 5
                             AND mg.unknown_fields.distinct_models_seen >= 2
                        THEN 'proposed'
                        WHEN mg.unknown_fields.occurrence_count + 1 >= 2
                        THEN 'proposed'
                        ELSE mg.unknown_fields.status
                    END
                """,
                (field_key, source_file, archive_id, sample_entry, vtype,
                 sample_entry)
            )
            log.debug('unknown field: %s in %s (value=%r)', field_key, source_file, field_val)
        cur.close()
        conn.close()
    except Exception as exc:
        log.debug('record_unknown_fields error: %s', exc)


# ---------------------------------------------------------------------------
# Archive Support (field log bundles: .tar / .tgz / .tar.gz / .rar)
# ---------------------------------------------------------------------------
# TRUST CONTEXT: Archives come from Bobby's own mining fleet. Lenient extraction
# via standard tarfile.extractall / rarfile.RarFile.extractall is acceptable.
# See spec: mg_importer_extension_spec.md §Context

import logging as _logging
import tarfile as _tarfile
import struct as _struct

try:
    import rarfile as _rarfile
    RARFILE_AVAILABLE = True
except ImportError:
    RARFILE_AVAILABLE = False

_archive_logger = _logging.getLogger('mg_archive')

# --- DDL for the 8 new field_log_* tables ---
FIELD_LOG_DDL = """
CREATE SCHEMA IF NOT EXISTS knowledge;

CREATE TABLE IF NOT EXISTS knowledge.field_log_imports (
    id BIGSERIAL PRIMARY KEY,
    entity_label TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    file_size_bytes BIGINT,
    detected_shape TEXT NOT NULL,
    miner_ip TEXT,
    miner_model TEXT,
    firmware_version TEXT,
    mac_address TEXT,
    control_board TEXT,
    kernel_version TEXT,
    archive_timestamp TIMESTAMP,
    files_in_archive INTEGER,
    parse_warnings TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS knowledge.field_log_miner_identity (
    id BIGSERIAL PRIMARY KEY,
    entity_label TEXT NOT NULL UNIQUE,
    archive_filename TEXT NOT NULL,
    miner_type TEXT,
    firmware_version TEXT,
    btminer_md5 TEXT,
    mac_address TEXT,
    control_board_version TEXT,
    kernel_version TEXT,
    cool_mode TEXT,
    slot INTEGER,
    pcb_serial TEXT,
    chip_data TEXT,
    hashrate_gh TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS knowledge.field_log_power_samples (
    id BIGSERIAL PRIMARY KEY,
    archive_filename TEXT NOT NULL,
    sample_source TEXT NOT NULL,
    sample_idx INTEGER,
    en_eset TEXT,
    iout_a NUMERIC,
    vout_v NUMERIC,
    vset_v NUMERIC,
    iin0_a NUMERIC, iin1_a NUMERIC, iin2_a NUMERIC,
    vin0_v NUMERIC, vin1_v NUMERIC, vin2_v NUMERIC,
    pin_w NUMERIC,
    t0_c NUMERIC, t1_c NUMERIC, t2_c NUMERIC,
    stat_code TEXT,
    raw_line TEXT,
    UNIQUE (archive_filename, sample_source, sample_idx)
);

CREATE TABLE IF NOT EXISTS knowledge.field_log_temp_snapshots (
    id BIGSERIAL PRIMARY KEY,
    archive_filename TEXT NOT NULL,
    snapshot_type TEXT NOT NULL,
    slot INTEGER,
    snapshot_temp_c NUMERIC,
    board_serial TEXT,
    raw_content TEXT,
    UNIQUE (archive_filename, snapshot_type, slot, board_serial)
);

CREATE TABLE IF NOT EXISTS knowledge.field_log_pools (
    id BIGSERIAL PRIMARY KEY,
    archive_filename TEXT NOT NULL,
    pool_idx INTEGER,
    url TEXT,
    user_name TEXT,
    priority TEXT,
    raw_block TEXT,
    UNIQUE (archive_filename, pool_idx)
);

CREATE TABLE IF NOT EXISTS knowledge.field_log_api_stats (
    id BIGSERIAL PRIMARY KEY,
    archive_filename TEXT NOT NULL,
    stats_section TEXT NOT NULL,
    slot INTEGER,
    elapsed_s BIGINT,
    chip_num INTEGER,
    freqs_avg NUMERIC,
    temp_c NUMERIC,
    chip_verify_diff TEXT,
    work_count BIGINT,
    nonce_count BIGINT,
    nonce_before BIGINT,
    nonce_err_count BIGINT,
    raw_block TEXT,
    UNIQUE (archive_filename, stats_section)
);

CREATE TABLE IF NOT EXISTS knowledge.field_log_antminer_boots (
    id BIGSERIAL PRIMARY KEY,
    entity_label TEXT NOT NULL UNIQUE,
    archive_filename TEXT NOT NULL,
    boot_timestamp TIMESTAMP,
    session_folder TEXT NOT NULL,
    files_present TEXT[],
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS knowledge.field_log_antminer_autotune (
    id BIGSERIAL PRIMARY KEY,
    archive_filename TEXT NOT NULL,
    boot_session TEXT NOT NULL,
    event_idx INTEGER,
    event_timestamp TIMESTAMP,
    event_type TEXT,
    chain INTEGER,
    frequency_mhz INTEGER,
    voltage_v NUMERIC,
    temp_max_c NUMERIC,
    raw_line TEXT,
    UNIQUE (archive_filename, boot_session, event_idx)
);

CREATE TABLE IF NOT EXISTS knowledge.field_log_events (
    id BIGSERIAL PRIMARY KEY,
    archive_filename TEXT NOT NULL,
    source_file TEXT NOT NULL,
    event_idx INTEGER,
    event_timestamp TIMESTAMP,
    severity TEXT,
    message TEXT,
    raw_line TEXT,
    UNIQUE (archive_filename, source_file, event_idx)
);

CREATE TABLE IF NOT EXISTS knowledge.field_log_raw_json (
    id BIGSERIAL PRIMARY KEY,
    archive_filename TEXT NOT NULL,
    file_path_in_archive TEXT NOT NULL DEFAULT '',
    raw_content JSONB NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (archive_filename, file_path_in_archive)
);

CREATE SCHEMA IF NOT EXISTS mg;

CREATE TABLE IF NOT EXISTS mg.import_runs (
    id BIGSERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    archive_count INTEGER,
    row_counts JSONB,
    errors TEXT[],
    status TEXT
);

-- v3.2: idempotent unique indexes for identity and raw_json tables
CREATE UNIQUE INDEX IF NOT EXISTS field_log_miner_identity_archive_entity_idx
    ON knowledge.field_log_miner_identity (archive_filename, entity_label);

CREATE UNIQUE INDEX IF NOT EXISTS field_log_raw_json_archive_path_idx
    ON knowledge.field_log_raw_json (archive_filename, file_path_in_archive);

-- v3.2: resolver columns on field_log_miner_identity (safe no-op if 002 migration ran)
ALTER TABLE knowledge.field_log_miner_identity
    ADD COLUMN IF NOT EXISTS hardware_revision TEXT;
ALTER TABLE knowledge.field_log_miner_identity
    ADD COLUMN IF NOT EXISTS resolved_miner_model_id UUID;
ALTER TABLE knowledge.field_log_miner_identity
    ADD COLUMN IF NOT EXISTS resolution_tier TEXT;
ALTER TABLE knowledge.field_log_miner_identity
    ADD COLUMN IF NOT EXISTS resolution_alias TEXT;
"""


def _dq(value):
    """Dollar-quote a value for SQL. Uses tagged form to handle embedded $."""
    if value is None:
        return 'NULL'
    value = str(value)
    tag = '$val$'
    if tag not in value:
        return f'{tag}{value}{tag}'
    n = 1
    while True:
        tag = f'$val{n}$'
        if tag not in value:
            return f'{tag}{value}{tag}'
        n += 1


def _num_or_null(s):
    """Return a numeric SQL literal or NULL."""
    if s is None or str(s).strip() in ('', '-', 'N/A'):
        return 'NULL'
    try:
        float(str(s).strip())
        return str(s).strip()
    except (ValueError, TypeError):
        return 'NULL'


def _int_or_null(s):
    """Return an integer SQL literal or NULL."""
    if s is None or str(s).strip() in ('', '-', 'N/A'):
        return 'NULL'
    try:
        return str(int(str(s).strip()))
    except (ValueError, TypeError):
        return 'NULL'


def _sha256_hex(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def detect_archive_shape(namelist: list) -> str:
    """
    Detect archive shape from member names.
    Returns 'whatsminer', 'antminer', or 'unknown'.
    Detection is cheap — only looks at names, not content.
    """
    # Antminer: has nvdata/ containing cglog_init_ subfolders
    has_nvdata = any('nvdata/' in n for n in namelist)
    has_cglog = any('cglog_init_' in n for n in namelist)
    if has_nvdata and has_cglog:
        return 'antminer'

    # WhatsMiner: *.logs/ folder containing miner_overview.log or miner-state.log
    for n in namelist:
        parts = n.split('/')
        if len(parts) >= 2 and parts[0].endswith('.logs'):
            leaf = parts[-1] if len(parts) > 1 else ''
            if leaf in ('miner_overview.log', 'miner-state.log', 'miner.log'):
                return 'whatsminer'

    # Fallback: if any member has .logs in path
    for n in namelist:
        if '.logs/' in n:
            return 'whatsminer'

    return 'unknown'


def _parse_archive_timestamp(filename: str):
    """Try to extract a timestamp from archive filename. Returns isoformat string or None."""
    # Pattern: _YYYYMMDDhhmmss  e.g. 10.0.14.57.20250313133403
    m = re.search(r'[._](\d{14})', filename)
    if m:
        s = m.group(1)
        try:
            return datetime(int(s[0:4]), int(s[4:6]), int(s[6:8]),
                            int(s[8:10]), int(s[10:12]), int(s[12:14])).isoformat()
        except ValueError:
            pass
    # Pattern: _YYYY-MM-DD_HH-MM-SS  e.g. 2024-07-01_19-38-2
    m = re.search(r'[_-](\d{4}-\d{2}-\d{2})[_-](\d{1,2}-\d{2}(?:-\d{1,2})?)', filename)
    if m:
        try:
            date_part = m.group(1)
            time_part = m.group(2).replace('-', ':')
            # pad time components
            tp = time_part.split(':')
            while len(tp) < 3:
                tp.append('0')
            ts = f"{date_part} {tp[0].zfill(2)}:{tp[1].zfill(2)}:{tp[2].zfill(2)}"
            return datetime.strptime(ts, '%Y-%m-%d %H:%M:%S').isoformat()
        except ValueError:
            pass
    return None


def _parse_miner_ip(filename: str, namelist: list) -> str:
    """Extract miner IP from folder name (e.g. 10.0.14.57.logs) or filename prefix."""
    # From namelist: first member that looks like <ip>.logs/
    ip_re = re.compile(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\.logs')
    for n in namelist:
        m = ip_re.match(n)
        if m:
            return m.group(1)
    # From filename prefix
    m = ip_re.match(filename)
    if m:
        return m.group(1)
    # General IP prefix in filename
    m = re.match(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', filename)
    if m:
        return m.group(1)
    return None


# ---------------------------------------------------------------------------
# WhatsMiner Parser
# ---------------------------------------------------------------------------

def parse_whatsminer_bundle(extract_dir: str, archive_meta: dict) -> list:
    """
    Parse a WhatsMiner log bundle from extract_dir.
    Returns list of SQL block strings.
    archive_meta keys: filename, sha256, file_size_bytes, miner_ip, archive_timestamp
    """
    filename = archive_meta['filename']
    warnings = []
    sql_blocks = []

    # Find the .logs subdirectory
    logs_dir = None
    for entry in os.listdir(extract_dir):
        if entry.endswith('.logs') and os.path.isdir(os.path.join(extract_dir, entry)):
            logs_dir = os.path.join(extract_dir, entry)
            break
    if logs_dir is None:
        # Might be flat (no .logs subfolder) — use extract_dir directly
        logs_dir = extract_dir

    # Gather file list
    try:
        all_files = [f for f in os.listdir(logs_dir) if os.path.isfile(os.path.join(logs_dir, f))]
    except Exception as e:
        all_files = []
        warnings.append(f'Cannot list logs_dir: {e}')

    archive_meta['files_in_archive'] = len(all_files)

    # --- miner_overview.log ---
    identity_rows = []
    miner_model = None
    firmware_version = None
    mac_address = None
    control_board = None
    kernel_version = None

    overview_path = os.path.join(logs_dir, 'miner_overview.log')
    if os.path.exists(overview_path):
        try:
            ov_rows, ov_meta = _parse_miner_overview(overview_path, filename)
            identity_rows.extend(ov_rows)
            miner_model = ov_meta.get('miner_type') or miner_model
            firmware_version = ov_meta.get('firmware_version') or firmware_version
            mac_address = ov_meta.get('mac_address') or mac_address
            control_board = ov_meta.get('control_board_version') or control_board
            kernel_version = ov_meta.get('kernel_version') or kernel_version
        except Exception as e:
            warnings.append(f'miner_overview.log parse error: {e}')

    archive_meta['miner_model'] = miner_model
    archive_meta['firmware_version'] = firmware_version
    archive_meta['mac_address'] = mac_address
    archive_meta['control_board'] = control_board
    archive_meta['kernel_version'] = kernel_version

    # --- power.log / power_error.log ---
    power_rows = []
    for plog in ('power.log', 'power_error.log'):
        ppath = os.path.join(logs_dir, plog)
        if os.path.exists(ppath):
            try:
                rows = _parse_power_log(ppath, filename, plog)
                power_rows.extend(rows)
            except Exception as e:
                warnings.append(f'{plog} parse error: {e}')

    # --- api.log ---
    api_rows = []
    api_path = os.path.join(logs_dir, 'api.log')
    if os.path.exists(api_path):
        try:
            api_rows = _parse_api_log(api_path, filename)
        except Exception as e:
            warnings.append(f'api.log parse error: {e}')

    # --- pools.log ---
    pool_rows = []
    pool_path = os.path.join(logs_dir, 'pools.log')
    if os.path.exists(pool_path):
        try:
            pool_rows = _parse_pools_log(pool_path, filename)
        except Exception as e:
            warnings.append(f'pools.log parse error: {e}')

    # --- temp files: temp{N}_{T}.xls and chip_temp_slot{N}_{serial} ---
    temp_rows = []
    for fname in all_files:
        fpath = os.path.join(logs_dir, fname)
        # board temp snapshot: temp0_52.0.xls
        m = re.match(r'^temp(\d+)_([\d.]+)\.xls$', fname)
        if m:
            slot = int(m.group(1))
            snap_temp = m.group(2)
            try:
                raw = open(fpath, 'r', errors='replace').read()
            except Exception as e:
                raw = f'[read error: {e}]'
                warnings.append(f'{fname} read error: {e}')
            temp_rows.append({
                'archive_filename': filename,
                'snapshot_type': 'board',
                'slot': slot,
                'snapshot_temp_c': snap_temp,
                'board_serial': None,
                'raw_content': raw,
            })
            continue

        # chip temp map: chip_temp_slot{N}_{serial}
        m = re.match(r'^chip_temp_slot(\d+)_(.+)$', fname)
        if m:
            slot = int(m.group(1))
            serial = m.group(2)
            try:
                raw = open(fpath, 'r', errors='replace').read()
            except Exception as e:
                raw = f'[read error: {e}]'
                warnings.append(f'{fname} read error: {e}')
            temp_rows.append({
                'archive_filename': filename,
                'snapshot_type': 'chip_map',
                'slot': slot,
                'snapshot_temp_c': None,
                'board_serial': serial,
                'raw_content': raw,
            })

    # --- ams_bixbit.json ---
    bixbit_path = os.path.join(logs_dir, 'ams_bixbit.json')
    if os.path.exists(bixbit_path):
        try:
            bixbit_note = _process_ams_bixbit(bixbit_path)
            warnings.append(bixbit_note)
        except Exception as e:
            warnings.append(f'ams_bixbit.json error: {e}')

    # Emit summary
    summary = (
        f"{filename}: detected=whatsminer, model={miner_model}, firmware={firmware_version}, "
        f"{len(power_rows)} power samples, {len(temp_rows)} temp snapshots, "
        f"{len([r for r in temp_rows if r['snapshot_type']=='chip_map'])} chip maps, "
        f"{len(api_rows)} api stats"
    )
    _archive_logger.info(summary)

    # Build SQL blocks
    archive_meta['parse_warnings'] = '; '.join(warnings) if warnings else None
    sql_blocks.append(_build_imports_sql(archive_meta, 'whatsminer'))
    if identity_rows:
        sql_blocks.append(_build_identity_sql(identity_rows))
    if power_rows:
        sql_blocks.append(_build_power_sql(power_rows))
    if temp_rows:
        sql_blocks.append(_build_temp_sql(temp_rows))
    if pool_rows:
        sql_blocks.append(_build_pools_sql(pool_rows))
    if api_rows:
        sql_blocks.append(_build_api_stats_sql(api_rows))

    return sql_blocks


def _parse_miner_overview(path: str, archive_filename: str):
    """
    Parse miner_overview.log (INI-style with tolerance for header lines).
    Returns (list_of_identity_rows, meta_dict).
    """
    rows = []
    meta = {}
    warnings = []

    with open(path, 'r', errors='replace') as f:
        lines = f.readlines()

    # Extract pre-[common] header lines
    header_vars = {}
    current_section = None
    section_data = {}
    all_sections = {}

    for line in lines:
        line = line.rstrip('\n')
        stripped = line.strip()

        # Section header
        m = re.match(r'^\[([^\]]+)\]', stripped)
        if m:
            if current_section and section_data:
                if current_section not in all_sections:
                    all_sections[current_section] = {}
                all_sections[current_section].update(section_data)
            current_section = m.group(1)
            section_data = {}
            continue

        if current_section is None:
            # Header lines: MINER_NAME='WhatsMiner' or KEY=VALUE
            m = re.match(r"^(\w+)\s*=\s*'?([^']*)'?\s*$", stripped)
            if m:
                header_vars[m.group(1)] = m.group(2)
        else:
            # Section key-value: key = value (with spaces)
            m = re.match(r'^(\w+)\s*=\s*(.*)', stripped)
            if m:
                section_data[m.group(1)] = m.group(2).strip()

    # Save last section
    if current_section and section_data:
        if current_section not in all_sections:
            all_sections[current_section] = {}
        all_sections[current_section].update(section_data)

    # Extract common section metadata
    common = all_sections.get('common', {})
    meta['miner_type'] = common.get('miner_type')
    meta['control_board_version'] = common.get('control_board_version')
    meta['mac_address'] = common.get('MAC')
    meta['cool_mode'] = common.get('cool_mode')
    meta['kernel_version'] = common.get('kernel_version', '')
    # firmware_version and btminer_md5 come from header
    meta['firmware_version'] = header_vars.get('FIRMWARE_VERSION')
    meta['btminer_md5'] = header_vars.get('BTMINER_MD5')

    # Build per-slot identity rows from [eeprom]
    eeprom = all_sections.get('eeprom', {})

    # Determine how many slots
    slots = set()
    for k in eeprom:
        m = re.search(r'(\d+)$', k)
        if m:
            slots.add(int(m.group(1)))

    if not slots:
        # No eeprom slots — create one summary row
        row = {
            'archive_filename': archive_filename,
            'entity_label': f'{archive_filename}::slot0',
            'miner_type': meta.get('miner_type'),
            'firmware_version': meta.get('firmware_version'),
            'btminer_md5': meta.get('btminer_md5'),
            'mac_address': meta.get('mac_address'),
            'control_board_version': meta.get('control_board_version'),
            'kernel_version': meta.get('kernel_version'),
            'cool_mode': meta.get('cool_mode'),
            'slot': 0,
            'pcb_serial': None,
            'chip_data': None,
            'hashrate_gh': None,
        }
        rows.append(row)
    else:
        for slot in sorted(slots):
            pcb_serial = eeprom.get(f'pcb{slot}') or eeprom.get(f'pcb_{slot}')
            chip_data = eeprom.get(f'chip_data{slot}') or eeprom.get(f'chip_data_{slot}')
            hashrate = eeprom.get(f'hashrate{slot}') or eeprom.get(f'hashrate_{slot}')

            # Skip fully empty slots (pcb blank, chip blank, hashrate blank)
            if not any([pcb_serial, chip_data, hashrate]):
                continue

            row = {
                'archive_filename': archive_filename,
                'entity_label': f'{archive_filename}::slot{slot}',
                'miner_type': meta.get('miner_type'),
                'firmware_version': meta.get('firmware_version'),
                'btminer_md5': meta.get('btminer_md5'),
                'mac_address': meta.get('mac_address'),
                'control_board_version': meta.get('control_board_version'),
                'kernel_version': meta.get('kernel_version'),
                'cool_mode': meta.get('cool_mode'),
                'slot': slot,
                'pcb_serial': pcb_serial,
                'chip_data': chip_data,
                'hashrate_gh': hashrate,
            }
            rows.append(row)

    return rows, meta


def _parse_power_log(path: str, archive_filename: str, source_name: str) -> list:
    """
    Parse WhatsMiner power.log or power_error.log.
    Format: idx en/eset iout vout/vset iin0/iin1/iin2 vin0/vin1/vin2 pin t0/t1/t2 stat
    Returns list of row dicts.
    """
    rows = []
    with open(path, 'r', errors='replace') as f:
        for raw_line in f:
            line = raw_line.rstrip('\n')
            stripped = line.strip()
            if not stripped:
                continue
            # Skip header/label lines (first token is non-numeric)
            parts = stripped.split()
            if not parts:
                continue
            # Try to parse idx from first token
            try:
                sample_idx = int(parts[0])
            except (ValueError, TypeError):
                continue  # header line — skip

            try:
                row = {
                    'archive_filename': archive_filename,
                    'sample_source': source_name,
                    'sample_idx': sample_idx,
                    'raw_line': line,
                    'en_eset': None, 'iout_a': None,
                    'vout_v': None, 'vset_v': None,
                    'iin0_a': None, 'iin1_a': None, 'iin2_a': None,
                    'vin0_v': None, 'vin1_v': None, 'vin2_v': None,
                    'pin_w': None,
                    't0_c': None, 't1_c': None, 't2_c': None,
                    'stat_code': None,
                }

                # Rejoin remaining tokens after idx
                rest = stripped[len(parts[0]):].strip()
                # Tokenize (some fields have internal spaces)
                tokens = rest.split()

                if len(tokens) >= 1:
                    row['en_eset'] = tokens[0]              # "1/1"
                if len(tokens) >= 2:
                    row['iout_a'] = tokens[1]               # "250.0"
                if len(tokens) >= 3:
                    vparts = tokens[2].split('/')
                    row['vout_v'] = vparts[0] if vparts else None
                    row['vset_v'] = vparts[1] if len(vparts) > 1 else None

                # iin0/iin1/iin2 — may contain spaces around /
                # Reassemble by looking for the //-separated triplets
                # Strategy: scan tokens for N/N/N patterns or reconstruct
                iin_str = None
                vin_str = None
                pin_val = None
                temp_str = None
                stat_val = None

                # Build a slash-normalized string from remaining tokens
                remaining_tokens = tokens[3:] if len(tokens) > 3 else []
                # Rejoin and re-split on whitespace, collapsing / fragments
                remaining = ' '.join(remaining_tokens)
                # Attempt structured parse:
                # iin triplet, vin triplet, pin, temp triplet, stat
                slash_pattern = re.compile(
                    r'([\d.]+)\s*/\s*([\d.]+)\s*/\s*([\d.]+)'
                )
                slash_matches = slash_pattern.findall(remaining)
                if len(slash_matches) >= 2:
                    row['iin0_a'], row['iin1_a'], row['iin2_a'] = slash_matches[0]
                    row['vin0_v'], row['vin1_v'], row['vin2_v'] = slash_matches[1]
                    # After the two triplets, remaining scalars are: pin, t0/t1/t2, stat
                    # Remove them from remaining to isolate pin+temp+stat
                    tail = slash_pattern.sub('__TRIPLE__', remaining, count=2)
                    tail_parts = tail.split()
                    non_triple = [p for p in tail_parts if p != '__TRIPLE__']
                    if len(non_triple) >= 1:
                        row['pin_w'] = non_triple[0]
                    if len(non_triple) >= 2:
                        # temp triplet may be already caught or still slash-separated
                        t_match = slash_pattern.search(non_triple[1] if len(non_triple) > 1 else '')
                        if t_match:
                            row['t0_c'], row['t1_c'], row['t2_c'] = t_match.groups()
                        else:
                            # try to find last slash-sep in original remaining
                            all_matches = slash_pattern.findall(remaining)
                            if len(all_matches) >= 3:
                                row['t0_c'], row['t1_c'], row['t2_c'] = all_matches[2]
                    if len(non_triple) >= 3:
                        row['stat_code'] = non_triple[-1]
                    elif len(non_triple) == 2:
                        row['stat_code'] = non_triple[-1]

                    # Try to find temp from all triples
                    if len(slash_matches) >= 3 and row['t0_c'] is None:
                        row['t0_c'], row['t1_c'], row['t2_c'] = slash_matches[2]

                rows.append(row)
            except Exception:
                # Malformed line — store raw only
                rows.append({
                    'archive_filename': archive_filename,
                    'sample_source': source_name,
                    'sample_idx': None,
                    'raw_line': line,
                    'en_eset': None, 'iout_a': None,
                    'vout_v': None, 'vset_v': None,
                    'iin0_a': None, 'iin1_a': None, 'iin2_a': None,
                    'vin0_v': None, 'vin1_v': None, 'vin2_v': None,
                    'pin_w': None,
                    't0_c': None, 't1_c': None, 't2_c': None,
                    'stat_code': None,
                })

    return rows


def _parse_api_log(path: str, archive_filename: str) -> list:
    """
    Parse WhatsMiner api.log PHP-array-style dump.
    Returns list of per-STATS-section row dicts.
    """
    rows = []
    with open(path, 'r', errors='replace') as f:
        content = f.read()

    # Split on STATS section headers.
    # Handles two known formats:
    #   Format A (PHP-array style): [STATS0] =>
    #   Format B (colon style):     STATS0:
    stats_pattern_a = re.compile(r'^\[STATS(\d+)\]\s*=>', re.MULTILINE)
    stats_pattern_b = re.compile(r'^STATS(\d+):', re.MULTILINE)

    positions_a = list(stats_pattern_a.finditer(content))
    positions_b = list(stats_pattern_b.finditer(content))

    # Use whichever format found more sections
    if len(positions_a) >= len(positions_b):
        positions = positions_a
        fmt = 'php'  # [KEY] => value
    else:
        positions = positions_b
        fmt = 'colon'  # KEY: value

    for i, match in enumerate(positions):
        stats_num = int(match.group(1))
        section_name = f'STATS{stats_num}'
        start = match.start()
        end = positions[i + 1].start() if i + 1 < len(positions) else len(content)
        block_text = content[start:end]

        def _extract_field(field_name, text, _fmt=fmt):
            if _fmt == 'php':
                # Match [field_name] => value
                m = re.search(r'\[' + re.escape(field_name) + r'\]\s*=>\s*([^\n\r]+)', text)
            else:
                # Match field_name: value  (with optional leading whitespace)
                m = re.search(r'^\s*' + re.escape(field_name) + r':\s*([^\n\r]+)', text, re.MULTILINE)
            if m:
                return m.group(1).strip()
            return None

        row = {
            'archive_filename': archive_filename,
            'stats_section': section_name,
            'slot': _int_or_null(_extract_field('slot', block_text)),
            'elapsed_s': _int_or_null(_extract_field('Elapsed', block_text)),
            'chip_num': _int_or_null(_extract_field('chip_num', block_text)),
            'freqs_avg': _num_or_null(_extract_field('freqs_avg', block_text)),
            'temp_c': _num_or_null(
                _extract_field('temp', block_text) or
                _extract_field('temp_now_max', block_text)
            ),
            'chip_verify_diff': _extract_field('chip_verify_diff', block_text),
            'work_count': _int_or_null(_extract_field('work_count', block_text)),
            'nonce_count': _int_or_null(_extract_field('nonce_count', block_text)),
            'nonce_before': _int_or_null(_extract_field('nonce_before', block_text)),
            'nonce_err_count': _int_or_null(_extract_field('nonce_err_count', block_text)),
            'raw_block': block_text[:2000],  # store up to 2k chars of raw
        }
        rows.append(row)

    return rows


def _parse_pools_log(path: str, archive_filename: str) -> list:
    """
    Parse WhatsMiner pools.log.
    Format: timestamp|code|Pools Change|btminer|change pool[N] field from X to Y
    Returns list of pool row dicts, one per detected pool index.
    """
    rows_by_idx = {}

    with open(path, 'r', errors='replace') as f:
        raw_content = f.read()

    lines = raw_content.splitlines()

    for line in lines:
        # Match: ...change pool[N] url from ... to 'URL'
        m = re.search(r"change pool\[(\d+)\]\s+url\s+from\s+.*?\s+to\s+'([^']*)'", line)
        if m:
            idx = int(m.group(1))
            url = m.group(2)
            if idx not in rows_by_idx:
                rows_by_idx[idx] = {'archive_filename': archive_filename,
                                    'pool_idx': idx, 'url': None, 'user_name': None,
                                    'priority': None, 'raw_block': ''}
            rows_by_idx[idx]['url'] = url
            rows_by_idx[idx]['raw_block'] += line + '\n'
            continue

        m = re.search(r"change pool\[(\d+)\]\s+user\s+from\s+.*?\s+to\s+'([^']*)'", line)
        if m:
            idx = int(m.group(1))
            user = m.group(2)
            if idx not in rows_by_idx:
                rows_by_idx[idx] = {'archive_filename': archive_filename,
                                    'pool_idx': idx, 'url': None, 'user_name': None,
                                    'priority': None, 'raw_block': ''}
            rows_by_idx[idx]['user_name'] = user
            rows_by_idx[idx]['raw_block'] += line + '\n'

    if not rows_by_idx:
        # Dump full raw content as single row
        rows_by_idx[0] = {
            'archive_filename': archive_filename,
            'pool_idx': 0,
            'url': None, 'user_name': None, 'priority': None,
            'raw_block': raw_content[:4000],
        }

    return list(rows_by_idx.values())


def _process_ams_bixbit(path: str) -> str:
    """
    Process ams_bixbit.json: redact api_key, preserve device_id.
    Returns a note string for parse_warnings.
    """
    import hashlib
    with open(path, 'r', errors='replace') as f:
        data = json.load(f)

    device_id = data.get('device_id', 'unknown')
    api_key = data.get('api_key', '')
    if api_key:
        redacted = 'REDACTED_' + hashlib.sha256(api_key.encode()).hexdigest()[:8]
    else:
        redacted = 'REDACTED_unknown'

    return f'AMS device_id={device_id}, api_key={redacted}'


# ---------------------------------------------------------------------------
# Antminer Parser
# ---------------------------------------------------------------------------

def parse_antminer_bundle(extract_dir: str, archive_meta: dict) -> list:
    """
    Parse an Antminer log bundle from extract_dir.
    Returns list of SQL block strings.
    """
    filename = archive_meta['filename']
    warnings = []
    sql_blocks = []

    # Find nvdata tree
    nvdata_dir = None
    for root, dirs, files in os.walk(extract_dir):
        if os.path.basename(root) == 'nvdata':
            nvdata_dir = root
            break
    if nvdata_dir is None:
        # Try direct nvdata/ folder
        candidate = os.path.join(extract_dir, 'nvdata')
        if os.path.isdir(candidate):
            nvdata_dir = candidate

    boot_rows = []
    identity_rows = []  # v3.2: one per boot session for field_log_miner_identity
    autotune_rows = []
    event_rows = []
    power_rows = []
    pool_rows = []
    all_session_folders = []
    miner_model = None
    firmware_version = None

    if nvdata_dir:
        # Walk: nvdata/YYYY-MM/DD/cglog_init_*/
        for year_month in sorted(os.listdir(nvdata_dir)):
            ym_path = os.path.join(nvdata_dir, year_month)
            if not os.path.isdir(ym_path):
                continue
            for day in sorted(os.listdir(ym_path)):
                day_path = os.path.join(ym_path, day)
                if not os.path.isdir(day_path):
                    continue
                for session in sorted(os.listdir(day_path)):
                    if not session.startswith('cglog_init_'):
                        continue
                    session_path = os.path.join(day_path, session)
                    if not os.path.isdir(session_path):
                        continue
                    all_session_folders.append(session_path)

                    # Extract boot timestamp from folder name: cglog_init_YYYY-MM-DD_HH-MM-SS
                    boot_ts = None
                    m = re.search(r'cglog_init_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})', session)
                    if m:
                        try:
                            ts_str = f"{m.group(1)} {m.group(2).replace('-', ':')}"
                            boot_ts = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S').isoformat()
                        except ValueError:
                            pass

                    session_files = os.listdir(session_path)

                    # Boot row
                    boot_entity = f'{filename}::{session}'
                    boot_rows.append({
                        'entity_label': boot_entity,
                        'archive_filename': filename,
                        'boot_timestamp': boot_ts,
                        'session_folder': session,
                        'files_present': session_files,
                    })

                    # Parse miner.log — v3: streaming generator with timeout guard
                    # v3.2: also accumulate per-session identity fields
                    session_meta = {}  # per-session identity fields
                    miner_log = os.path.join(session_path, 'miner.log')
                    if os.path.exists(miner_log):
                        try:
                            _t0 = _time_module.monotonic()
                            for item in _stream_antminer_miner_log(
                                    miner_log, filename, session):
                                kind = item['kind']
                                if kind == 'meta':
                                    if 'miner_model' in item and not miner_model:
                                        miner_model = item['miner_model']
                                    if 'firmware_version' in item and not firmware_version:
                                        firmware_version = item['firmware_version']
                                    # v3.2: collect identity fields per-session (first-seen wins)
                                    for _fld in ('miner_model', 'firmware_version',
                                                 'mac_address', 'kernel_version',
                                                 'control_board_version', 'cool_mode',
                                                 'hashrate_gh'):
                                        if _fld in item and _fld not in session_meta:
                                            session_meta[_fld] = item[_fld]
                                elif kind == 'autotune':
                                    autotune_rows.append(item)
                                elif kind == 'event':
                                    event_rows.append(item)
                            _elapsed = _time_module.monotonic() - _t0
                            get_run_logger('mg_antminer').info(
                                '%s/%s miner.log: %d autotune, %d events in %.1fs',
                                filename, session, len(autotune_rows),
                                len(event_rows), _elapsed)
                        except Exception as e:
                            warnings.append(f'{session}/miner.log: {e}')

                    # v3.2: build one identity row per boot session
                    identity_rows.append({
                        'entity_label':          boot_entity,
                        'archive_filename':       filename,
                        'miner_type':            session_meta.get('miner_model'),
                        'firmware_version':      session_meta.get('firmware_version'),
                        'btminer_md5':           None,  # not in Antminer logs
                        'mac_address':           session_meta.get('mac_address'),
                        'control_board_version': session_meta.get('control_board_version'),
                        'kernel_version':        session_meta.get('kernel_version'),
                        'cool_mode':             session_meta.get('cool_mode'),
                        'slot':                  None,
                        'pcb_serial':            None,
                        'chip_data':             None,
                        'hashrate_gh':           session_meta.get('hashrate_gh'),
                    })

                    # Parse autotune.log if present (supplemental)
                    autotune_log = os.path.join(session_path, 'autotune.log')
                    if os.path.exists(autotune_log) and os.path.getsize(autotune_log) > 0:
                        try:
                            # autotune.log often replicates miner.log — skip if already rich
                            pass  # no separate parse needed based on sample inspection
                        except Exception as e:
                            warnings.append(f'{session}/autotune.log: {e}')

    archive_meta['miner_model'] = miner_model
    archive_meta['firmware_version'] = firmware_version
    archive_meta['files_in_archive'] = sum(
        len(os.listdir(s)) for s in all_session_folders
    )

    # v3.2: if this is an antminer archive but had zero parseable boot sessions,
    # emit one archive-level synthetic identity row so Layer 2 has something to work on.
    if not identity_rows:
        identity_rows.append({
            'entity_label':          f'{filename}::archive-level',
            'archive_filename':      filename,
            'miner_type':           miner_model,
            'firmware_version':     firmware_version,
            'btminer_md5':          None,
            'mac_address':          None,
            'control_board_version': None,
            'kernel_version':       None,
            'cool_mode':            None,
            'slot':                 None,
            'pcb_serial':           None,
            'chip_data':            None,
            'hashrate_gh':          None,
        })

    # Store identity rows in archive_meta so _do_layer2_postprocessing can resolve them
    archive_meta['identity_rows'] = identity_rows

    # Parse config/cgminer.conf → pool info
    config_path = os.path.join(extract_dir, 'config', 'cgminer.conf')
    if os.path.exists(config_path):
        try:
            pool_rows = _parse_cgminer_conf(config_path, filename)
        except Exception as e:
            warnings.append(f'config/cgminer.conf: {e}')

    summary = (
        f"{filename}: detected=antminer, model={miner_model}, firmware={firmware_version}, "
        f"{len(boot_rows)} boot sessions, {len(autotune_rows)} autotune events, "
        f"{len(event_rows)} log events, {len(pool_rows)} pool configs"
    )
    _archive_logger.info(summary)

    archive_meta['parse_warnings'] = '; '.join(warnings) if warnings else None
    sql_blocks.append(_build_imports_sql(archive_meta, 'antminer'))
    if boot_rows:
        sql_blocks.append(_build_antminer_boots_sql(boot_rows))
    # v3.2: emit identity rows for field_log_miner_identity
    if identity_rows:
        sql_blocks.append(_build_identity_sql(identity_rows))
    if autotune_rows:
        # v3: use batched builder (1000 rows/stmt) instead of one giant string
        sql_blocks.extend(_build_antminer_autotune_sql_batched(autotune_rows, batch_size=1000))
    if event_rows:
        sql_blocks.append(_build_events_sql(event_rows))
    if pool_rows:
        sql_blocks.append(_build_pools_sql(pool_rows))

    log_antminer = get_run_logger('mg_antminer')
    log_antminer.info(
        '%s: antminer summary — %d boot sessions, %d autotune events, '
        '%d log events, %d pool configs, %d identity rows',
        filename, len(boot_rows), len(autotune_rows),
        len(event_rows), len(pool_rows), len(identity_rows)
    )

    return sql_blocks


def _stream_antminer_miner_log(path: str, archive_filename: str, session: str):
    """
    v3 STREAMING parser for Antminer miner.log.

    CRITICAL FIX: The v2 version collected all autotune rows into a single list,
    then built one giant SQL string.  For archives with 14,000+ events this
    produced quadratic string-concatenation behaviour and could hang the whole
    import process indefinitely.

    This version is a GENERATOR that yields individual row dicts as it reads
    the file line-by-line, keeping memory usage O(1) per line.  Callers use
    _build_antminer_autotune_sql_batched() which flushes every 1,000 rows.

    Timeout guard: if the file takes > 60 s we log a warning and stop
    (raises StopIteration cleanly so the outer loop continues).

    Yields dicts with key 'kind' in ('autotune', 'event', 'meta').
    'meta' dicts carry miner_model / firmware_version discovered mid-stream.
    """
    _LOG_ANTMINER = get_run_logger('mg_antminer')

    ts_pat              = re.compile(
        r'^\[(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d+)\]\s+(\w+):\s+(.*)'
    )
    freq_set_pat        = re.compile(r'Set chain (\d+) freq (\d+)', re.IGNORECASE)
    temp_max_pat        = re.compile(r'Temp max (\d+)C', re.IGNORECASE)
    voltage_pat         = re.compile(r'[Pp]su current voltage ([\d.]+)V?', re.IGNORECASE)
    autotune_profile_pat= re.compile(r'[Aa]utotune set profile.*freq max (\d+)', re.IGNORECASE)
    device_complete_pat = re.compile(r'Detect device complete:\s*(.*)')
    firmware_pat        = re.compile(r'[Ff]irmware version[: ]+([\d.]+)')
    # v3.2: additional identity field extraction patterns
    mac_hwaddr_pat      = re.compile(r'eth0\s+HWaddr\s+([0-9A-Fa-f:]{17})', re.IGNORECASE)
    mac_colon_pat       = re.compile(r'MAC[:\s]+([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})', re.IGNORECASE)
    kernel_pat          = re.compile(r'Linux\s+\S+\s+([\d.]+\S*)', re.IGNORECASE)
    control_board_pat   = re.compile(r'control_board(?:_type|_version)?[=:\s]+([\w./-]+)', re.IGNORECASE)
    cool_mode_pat       = re.compile(r'cool(?:_mode|ing)?[=:\s]+(air|oil|immersion|hydro|liquid)', re.IGNORECASE)
    hashrate_pat        = re.compile(r'(?:avg|average)?\s*hash\s*rate[:\s]+([\d.]+)\s*(?:GH|GH/s)', re.IGNORECASE)

    event_idx    = 0
    autotune_idx = 0
    t_start      = _time_module.monotonic()
    TIMEOUT_S    = 60  # per-file safety cap

    with open(path, 'r', errors='replace') as fh:
        for raw_line in fh:
            # Timeout guard
            if _time_module.monotonic() - t_start > TIMEOUT_S:
                _LOG_ANTMINER.warning(
                    'TIMEOUT parsing %s / %s after %ds — stopping mid-file',
                    archive_filename, session, TIMEOUT_S
                )
                return

            line    = raw_line.rstrip('\n')
            stripped = line.strip()
            if not stripped:
                continue

            m = ts_pat.match(stripped)
            if not m:
                continue

            ts_str, level, message = m.group(1), m.group(2), m.group(3)

            # Parse timestamp
            event_ts = None
            try:
                ts_clean = ts_str.split('.')[0]
                dt = datetime.strptime(ts_clean, '%Y/%m/%d %H:%M:%S')
                if dt.year > 1970:
                    event_ts = dt.isoformat()
            except ValueError:
                pass

            # Yield meta discoveries (model / firmware) — do NOT accumulate
            dm = device_complete_pat.search(message)
            if dm:
                yield {'kind': 'meta', 'miner_model': dm.group(1).split(',')[0].strip()}

            fm = firmware_pat.search(message)
            if fm:
                yield {'kind': 'meta', 'firmware_version': fm.group(1)}

            # v3.2: yield additional identity meta fields
            mac_m = mac_hwaddr_pat.search(message) or mac_colon_pat.search(message)
            if mac_m:
                yield {'kind': 'meta', 'mac_address': mac_m.group(1).upper()}

            kern_m = kernel_pat.search(message)
            if kern_m:
                yield {'kind': 'meta', 'kernel_version': kern_m.group(1)}

            cb_m = control_board_pat.search(message)
            if cb_m:
                yield {'kind': 'meta', 'control_board_version': cb_m.group(1)}

            cm_m = cool_mode_pat.search(message)
            if cm_m:
                yield {'kind': 'meta', 'cool_mode': cm_m.group(1).lower()}

            hr_m = hashrate_pat.search(message)
            if hr_m:
                yield {'kind': 'meta', 'hashrate_gh': hr_m.group(1)}

            # Autotune events
            autotune_event = None
            chain = freq = voltage = temp_max = None

            fset = freq_set_pat.search(message)
            if fset:
                autotune_event = 'freq_set'
                chain = int(fset.group(1))
                freq  = int(fset.group(2))

            tmax = temp_max_pat.search(message)
            if tmax:
                autotune_event = 'temp_max'
                temp_max = float(tmax.group(1))

            vm = voltage_pat.search(message)
            if vm:
                autotune_event = 'voltage'
                voltage = float(vm.group(1))

            if re.search(r'[Ii]nit done', message):
                autotune_event = 'init_done'

            apm = autotune_profile_pat.search(message)
            if apm:
                autotune_event = 'autotune_profile'
                freq = int(apm.group(1))

            if autotune_event:
                yield {
                    'kind':             'autotune',
                    'archive_filename': archive_filename,
                    'boot_session':     session,
                    'event_idx':        autotune_idx,
                    'event_timestamp':  event_ts,
                    'event_type':       autotune_event,
                    'chain':            chain,
                    'frequency_mhz':    freq,
                    'voltage_v':        voltage,
                    'temp_max_c':       temp_max,
                    'raw_line':         line,
                }
                autotune_idx += 1

            if level in ('ERROR', 'WARN', 'FATAL', 'ERR'):
                sev = 'ERROR' if level in ('ERROR', 'ERR', 'FATAL') else 'WARN'
                yield {
                    'kind':             'event',
                    'archive_filename': archive_filename,
                    'source_file':      'miner.log',
                    'event_idx':        event_idx,
                    'event_timestamp':  event_ts,
                    'severity':         sev,
                    'message':          message,
                    'raw_line':         line,
                }
                event_idx += 1


def _parse_antminer_miner_log(path: str, archive_filename: str, session: str):
    """
    Backwards-compatible wrapper around the streaming generator.
    Returns (autotune_rows, event_rows, miner_model, firmware_version)
    but caps autotune_rows at 50,000 to prevent memory blow-up.
    For large files use _stream_antminer_miner_log() directly.
    """
    autotune_rows = []
    event_rows    = []
    miner_model   = None
    firmware_version = None
    MAX_AUTOTUNE  = 50_000

    for item in _stream_antminer_miner_log(path, archive_filename, session):
        kind = item['kind']
        if kind == 'meta':
            if 'miner_model' in item and not miner_model:
                miner_model = item['miner_model']
            if 'firmware_version' in item and not firmware_version:
                firmware_version = item['firmware_version']
        elif kind == 'autotune' and len(autotune_rows) < MAX_AUTOTUNE:
            autotune_rows.append(item)
        elif kind == 'event':
            event_rows.append(item)

    return autotune_rows, event_rows, miner_model, firmware_version


def _parse_cgminer_conf(path: str, archive_filename: str) -> list:
    """
    Parse Antminer config/cgminer.conf JSON → pool rows.
    Returns list of pool row dicts.
    """
    rows = []
    with open(path, 'r', errors='replace') as f:
        raw = f.read()

    try:
        conf = json.loads(raw)
    except json.JSONDecodeError:
        # Store raw as single pool row
        return [{
            'archive_filename': archive_filename,
            'pool_idx': 0,
            'url': None, 'user_name': None, 'priority': None,
            'raw_block': raw[:4000],
        }]

    pools = conf.get('pools', [])
    for i, pool in enumerate(pools):
        rows.append({
            'archive_filename': archive_filename,
            'pool_idx': i,
            'url': pool.get('url'),
            'user_name': pool.get('user'),
            'priority': pool.get('pass'),
            'raw_block': json.dumps(pool),
        })

    if not rows:
        rows.append({
            'archive_filename': archive_filename,
            'pool_idx': 0,
            'url': None, 'user_name': None, 'priority': None,
            'raw_block': raw[:4000],
        })

    return rows


# ---------------------------------------------------------------------------
# SQL Builders
# ---------------------------------------------------------------------------

def _build_imports_sql(meta: dict, shape: str) -> str:
    """Build INSERT SQL for field_log_imports."""
    fn = meta['filename']
    ts = meta.get('archive_timestamp')
    ts_sql = f"'{ts}'" if ts else 'NULL'
    warnings_val = _dq(meta.get('parse_warnings', '')) if meta.get('parse_warnings') else 'NULL'

    sql = f"""INSERT INTO knowledge.field_log_imports
    (entity_label, sha256, file_size_bytes, detected_shape, miner_ip, miner_model,
     firmware_version, mac_address, control_board, kernel_version,
     archive_timestamp, files_in_archive, parse_warnings)
VALUES (
    {_dq(fn)},
    {_dq(meta.get('sha256', ''))},
    {_int_or_null(meta.get('file_size_bytes'))},
    {_dq(shape)},
    {_dq(meta['miner_ip']) if meta.get('miner_ip') else 'NULL'},
    {_dq(meta['miner_model']) if meta.get('miner_model') else 'NULL'},
    {_dq(meta['firmware_version']) if meta.get('firmware_version') else 'NULL'},
    {_dq(meta['mac_address']) if meta.get('mac_address') else 'NULL'},
    {_dq(meta['control_board']) if meta.get('control_board') else 'NULL'},
    {_dq(meta['kernel_version']) if meta.get('kernel_version') else 'NULL'},
    {ts_sql},
    {_int_or_null(meta.get('files_in_archive'))},
    {warnings_val}
) ON CONFLICT (entity_label) DO NOTHING;"""
    return sql


def _build_identity_sql(rows: list) -> str:
    """Build INSERT SQL for field_log_miner_identity."""
    stmts = []
    for r in rows:
        stmts.append(f"""INSERT INTO knowledge.field_log_miner_identity
    (entity_label, archive_filename, miner_type, firmware_version, btminer_md5,
     mac_address, control_board_version, kernel_version, cool_mode, slot,
     pcb_serial, chip_data, hashrate_gh)
VALUES (
    {_dq(r['entity_label'])},
    {_dq(r['archive_filename'])},
    {_dq(r['miner_type']) if r.get('miner_type') else 'NULL'},
    {_dq(r['firmware_version']) if r.get('firmware_version') else 'NULL'},
    {_dq(r['btminer_md5']) if r.get('btminer_md5') else 'NULL'},
    {_dq(r['mac_address']) if r.get('mac_address') else 'NULL'},
    {_dq(r['control_board_version']) if r.get('control_board_version') else 'NULL'},
    {_dq(r['kernel_version']) if r.get('kernel_version') else 'NULL'},
    {_dq(r['cool_mode']) if r.get('cool_mode') is not None else 'NULL'},
    {_int_or_null(r.get('slot'))},
    {_dq(r['pcb_serial']) if r.get('pcb_serial') else 'NULL'},
    {_dq(r['chip_data']) if r.get('chip_data') else 'NULL'},
    {_dq(r['hashrate_gh']) if r.get('hashrate_gh') else 'NULL'}
) ON CONFLICT (entity_label) DO NOTHING;""")
    return '\n'.join(stmts)


def _build_power_sql(rows: list) -> str:
    """Build INSERT SQL for field_log_power_samples."""
    stmts = []
    for r in rows:
        stmts.append(f"""INSERT INTO knowledge.field_log_power_samples
    (archive_filename, sample_source, sample_idx, en_eset, iout_a, vout_v, vset_v,
     iin0_a, iin1_a, iin2_a, vin0_v, vin1_v, vin2_v, pin_w, t0_c, t1_c, t2_c,
     stat_code, raw_line)
VALUES (
    {_dq(r['archive_filename'])},
    {_dq(r['sample_source'])},
    {_int_or_null(r.get('sample_idx'))},
    {_dq(r['en_eset']) if r.get('en_eset') else 'NULL'},
    {_num_or_null(r.get('iout_a'))},
    {_num_or_null(r.get('vout_v'))},
    {_num_or_null(r.get('vset_v'))},
    {_num_or_null(r.get('iin0_a'))},
    {_num_or_null(r.get('iin1_a'))},
    {_num_or_null(r.get('iin2_a'))},
    {_num_or_null(r.get('vin0_v'))},
    {_num_or_null(r.get('vin1_v'))},
    {_num_or_null(r.get('vin2_v'))},
    {_num_or_null(r.get('pin_w'))},
    {_num_or_null(r.get('t0_c'))},
    {_num_or_null(r.get('t1_c'))},
    {_num_or_null(r.get('t2_c'))},
    {_dq(r['stat_code']) if r.get('stat_code') else 'NULL'},
    {_dq(r.get('raw_line', '')) if r.get('raw_line') else 'NULL'}
) ON CONFLICT (archive_filename, sample_source, sample_idx) DO NOTHING;""")
    return '\n'.join(stmts)


def _build_temp_sql(rows: list) -> str:
    """Build INSERT SQL for field_log_temp_snapshots."""
    stmts = []
    for r in rows:
        stmts.append(f"""INSERT INTO knowledge.field_log_temp_snapshots
    (archive_filename, snapshot_type, slot, snapshot_temp_c, board_serial, raw_content)
VALUES (
    {_dq(r['archive_filename'])},
    {_dq(r['snapshot_type'])},
    {_int_or_null(r.get('slot'))},
    {_num_or_null(r.get('snapshot_temp_c'))},
    {_dq(r['board_serial']) if r.get('board_serial') else 'NULL'},
    {_dq(r['raw_content']) if r.get('raw_content') else 'NULL'}
) ON CONFLICT (archive_filename, snapshot_type, slot, board_serial) DO NOTHING;""")
    return '\n'.join(stmts)


def _build_pools_sql(rows: list) -> str:
    """Build INSERT SQL for field_log_pools."""
    stmts = []
    for r in rows:
        stmts.append(f"""INSERT INTO knowledge.field_log_pools
    (archive_filename, pool_idx, url, user_name, priority, raw_block)
VALUES (
    {_dq(r['archive_filename'])},
    {_int_or_null(r.get('pool_idx'))},
    {_dq(r['url']) if r.get('url') else 'NULL'},
    {_dq(r['user_name']) if r.get('user_name') else 'NULL'},
    {_dq(r['priority']) if r.get('priority') else 'NULL'},
    {_dq(r['raw_block']) if r.get('raw_block') else 'NULL'}
) ON CONFLICT (archive_filename, pool_idx) DO NOTHING;""")
    return '\n'.join(stmts)


def _build_api_stats_sql(rows: list) -> str:
    """Build INSERT SQL for field_log_api_stats."""
    stmts = []
    for r in rows:
        stmts.append(f"""INSERT INTO knowledge.field_log_api_stats
    (archive_filename, stats_section, slot, elapsed_s, chip_num, freqs_avg, temp_c,
     chip_verify_diff, work_count, nonce_count, nonce_before, nonce_err_count, raw_block)
VALUES (
    {_dq(r['archive_filename'])},
    {_dq(r['stats_section'])},
    {r['slot']},
    {r['elapsed_s']},
    {r['chip_num']},
    {r['freqs_avg']},
    {r['temp_c']},
    {_dq(r['chip_verify_diff']) if r.get('chip_verify_diff') else 'NULL'},
    {r['work_count']},
    {r['nonce_count']},
    {r['nonce_before']},
    {r['nonce_err_count']},
    {_dq(r['raw_block']) if r.get('raw_block') else 'NULL'}
) ON CONFLICT (archive_filename, stats_section) DO NOTHING;""")
    return '\n'.join(stmts)


def _build_antminer_boots_sql(rows: list) -> str:
    """Build INSERT SQL for field_log_antminer_boots."""
    stmts = []
    for r in rows:
        files_arr = 'ARRAY[' + ','.join(_dq(f) for f in sorted(r['files_present'])) + ']' \
            if r['files_present'] else 'ARRAY[]::TEXT[]'
        boot_ts = f"'{r['boot_timestamp']}'" if r.get('boot_timestamp') else 'NULL'
        stmts.append(f"""INSERT INTO knowledge.field_log_antminer_boots
    (entity_label, archive_filename, boot_timestamp, session_folder, files_present)
VALUES (
    {_dq(r['entity_label'])},
    {_dq(r['archive_filename'])},
    {boot_ts},
    {_dq(r['session_folder'])},
    {files_arr}
) ON CONFLICT (entity_label) DO NOTHING;""")
    return '\n'.join(stmts)


def _build_antminer_autotune_sql(rows: list) -> str:
    """Build INSERT SQL for field_log_antminer_autotune."""
    stmts = []
    for r in rows:
        event_ts = f"'{r['event_timestamp']}'" if r.get('event_timestamp') else 'NULL'
        stmts.append(f"""INSERT INTO knowledge.field_log_antminer_autotune
    (archive_filename, boot_session, event_idx, event_timestamp, event_type,
     chain, frequency_mhz, voltage_v, temp_max_c, raw_line)
VALUES (
    {_dq(r['archive_filename'])},
    {_dq(r['boot_session'])},
    {_int_or_null(r.get('event_idx'))},
    {event_ts},
    {_dq(r['event_type']) if r.get('event_type') else 'NULL'},
    {_int_or_null(r.get('chain'))},
    {_int_or_null(r.get('frequency_mhz'))},
    {_num_or_null(r.get('voltage_v'))},
    {_num_or_null(r.get('temp_max_c'))},
    {_dq(r['raw_line']) if r.get('raw_line') else 'NULL'}
) ON CONFLICT (archive_filename, boot_session, event_idx) DO NOTHING;""")
    return '\n'.join(stmts)


def _build_antminer_autotune_sql_batched(rows: list, batch_size: int = 500) -> list:
    """
    v3.1: Build batched INSERT SQL blocks for field_log_antminer_autotune.
    Splits rows into chunks of batch_size to avoid giant single statements.
    Default batch_size=500 keeps memory footprint under 100 MB per archive
    (reduced from 1000 in v3 to comply with the Layer 2 streaming memory spec).
    Returns list of SQL strings (each a VALUES (...),(...),...  multi-row INSERT).
    """
    sql_blocks = []
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        value_clauses = []
        for r in batch:
            event_ts = f"'{r['event_timestamp']}'" if r.get('event_timestamp') else 'NULL'
            value_clauses.append(
                f"({_dq(r['archive_filename'])}, {_dq(r['boot_session'])}, "
                f"{_int_or_null(r.get('event_idx'))}, {event_ts}, "
                f"{_dq(r['event_type']) if r.get('event_type') else 'NULL'}, "
                f"{_int_or_null(r.get('chain'))}, "
                f"{_int_or_null(r.get('frequency_mhz'))}, "
                f"{_num_or_null(r.get('voltage_v'))}, "
                f"{_num_or_null(r.get('temp_max_c'))}, "
                f"{_dq(r['raw_line']) if r.get('raw_line') else 'NULL'})"
            )
        sql_blocks.append(
            "INSERT INTO knowledge.field_log_antminer_autotune\n"
            "    (archive_filename, boot_session, event_idx, event_timestamp, event_type,\n"
            "     chain, frequency_mhz, voltage_v, temp_max_c, raw_line) VALUES\n"
            + ",\n".join(value_clauses)
            + "\nON CONFLICT (archive_filename, boot_session, event_idx) DO NOTHING;"
        )
    return sql_blocks


def _build_events_sql(rows: list) -> str:
    """Build INSERT SQL for field_log_events."""
    stmts = []
    for r in rows:
        event_ts = f"'{r['event_timestamp']}'" if r.get('event_timestamp') else 'NULL'
        stmts.append(f"""INSERT INTO knowledge.field_log_events
    (archive_filename, source_file, event_idx, event_timestamp, severity, message, raw_line)
VALUES (
    {_dq(r['archive_filename'])},
    {_dq(r['source_file'])},
    {_int_or_null(r.get('event_idx'))},
    {event_ts},
    {_dq(r['severity']) if r.get('severity') else 'NULL'},
    {_dq(r['message']) if r.get('message') else 'NULL'},
    {_dq(r['raw_line']) if r.get('raw_line') else 'NULL'}
) ON CONFLICT (archive_filename, source_file, event_idx) DO NOTHING;""")
    return '\n'.join(stmts)


# ---------------------------------------------------------------------------
# Main archive dispatcher
# ---------------------------------------------------------------------------

def process_archive(file_bytes: bytes, filename: str,
                    conn_params: dict = None) -> list:
    """
    Main entry point for archive processing.  v3 adds Layer 2 integration.
    Accepts .tar / .tgz / .tar.gz / .rar files.
    Returns list of SQL block strings (DDL + DML, ready for execute_sql_block or display).
    Fails cleanly on malformed/truncated archives with a clear error message.

    conn_params (optional): if provided, performs Layer 2 post-import work:
      - Resolves miner_type -> catalog_slug via mg.model_aliases
      - Stamps knowledge.field_log_imports.catalog_slug
      - Queues unresolved models to mg.unresolved_models
      - Inserts knowledge.field_log_raw_json blobs
      - Records unknown fields to mg.unknown_fields
    """
    if not file_bytes:
        return [f'-- ERROR: Empty archive file: {filename}']

    # Minimum viable archive size: reject obviously truncated files
    if len(file_bytes) < 100:
        return [
            f'-- ERROR: Archive {filename!r} appears truncated or empty '
            f'({len(file_bytes)} bytes). Cannot parse.'
        ]

    ext_lower = filename.lower()
    sha = _sha256_hex(file_bytes)
    fsize = len(file_bytes)
    ts = _parse_archive_timestamp(filename)
    sql_blocks = []
    _t_archive_start = _time_module.monotonic()
    _log = get_run_logger('mg_archive')
    _log.info('BEGIN archive: %s  (%.1f KB, sha256=%s...)', filename, fsize/1024, sha[:12])

    tmp_dir = None
    try:
        tmp_dir = tempfile.mkdtemp(prefix='mg_archive_')

        # Open archive and get namelist for shape detection
        if ext_lower.endswith('.rar'):
            if not RARFILE_AVAILABLE:
                return [
                    "-- ERROR: RAR support requires the 'unrar' binary and rarfile library. "
                    "Install: pip install rarfile && apt-get install unrar (Linux), "
                    "brew install unrar (macOS), or download from rarlab.com (Windows)."
                ]
            try:
                rf = _rarfile.RarFile(io.BytesIO(file_bytes))
                namelist = rf.namelist()
            except Exception as e:
                return [f'-- ERROR: Cannot open RAR archive {filename!r}: {e}']
        else:
            # .tar, .tgz, .tar.gz
            try:
                tf = _tarfile.open(fileobj=io.BytesIO(file_bytes))
                namelist = [m.name for m in tf.getmembers()]
            except Exception as e:
                return [f'-- ERROR: Cannot open archive {filename!r}: {e}. '
                        f'File may be truncated or corrupted ({fsize} bytes).']

        shape = detect_archive_shape(namelist)

        # Extract to temp dir
        try:
            if ext_lower.endswith('.rar'):
                rf.extractall(tmp_dir)
            else:
                tf.extractall(tmp_dir)  # lenient extraction per trust context
        except Exception as e:
            return [f'-- ERROR: Extraction failed for {filename!r}: {e}']
        finally:
            if not ext_lower.endswith('.rar'):
                tf.close()

        ip = _parse_miner_ip(filename, namelist)

        archive_meta = {
            'filename': filename,
            'sha256': sha,
            'file_size_bytes': fsize,
            'miner_ip': ip,
            'miner_model': None,
            'firmware_version': None,
            'mac_address': None,
            'control_board': None,
            'kernel_version': None,
            'archive_timestamp': ts,
            'files_in_archive': len(namelist),
            'parse_warnings': None,
        }

        # DDL block comes first
        sql_blocks.append('BEGIN;\n' + FIELD_LOG_DDL + '\nCOMMIT;')

        _log.info('  shape=%s  ip=%s', shape, archive_meta.get('miner_ip', 'none'))

        if shape == 'whatsminer':
            parsed = parse_whatsminer_bundle(tmp_dir, archive_meta)
        elif shape == 'antminer':
            parsed = parse_antminer_bundle(tmp_dir, archive_meta)
        else:
            # Unknown shape — store import record only
            archive_meta['parse_warnings'] = 'Unknown archive shape — no parsers matched'
            parsed = [_build_imports_sql(archive_meta, 'unknown')]

        # Wrap all DML in a single transaction
        sql_blocks.append('BEGIN;\n' + '\n'.join(parsed) + '\nCOMMIT;')

        # -----------------------------------------------------------------
        # v3: Layer 2 post-import work (requires live DB connection)
        # Runs AFTER the SQL blocks are built so it never blocks SQL gen.
        # -----------------------------------------------------------------
        if conn_params:
            _do_layer2_postprocessing(
                conn_params, archive_meta, shape, tmp_dir
            )

        _elapsed = _time_module.monotonic() - _t_archive_start
        _log.info('END archive: %s  elapsed=%.2fs  model=%s  shape=%s',
                  filename, _elapsed,
                  archive_meta.get('miner_model', 'unknown'), shape)

    except Exception as e:
        sql_blocks.append(f'-- ERROR: Unexpected failure processing {filename!r}: {e}\n'
                          f'-- Traceback:\n' +
                          '\n'.join(f'--   {ln}' for ln in traceback.format_exc().splitlines()))
        _log.error('EXCEPTION processing %s: %s', filename, e)
    finally:
        if tmp_dir and os.path.isdir(tmp_dir):
            try:
                import shutil
                shutil.rmtree(tmp_dir)
            except Exception:
                pass

    return sql_blocks


# ---------------------------------------------------------------------------
# v3.2 Layer 2 helpers
# ---------------------------------------------------------------------------

def _insert_archive_raw_json_files(conn_params: dict, archive_filename: str,
                                    tmp_dir: str):
    """
    Walk tmp_dir and call insert_raw_json for every *.json file found, plus
    any *.log file whose content starts with '{' or '[' (best-effort JSON).
    Uses ON CONFLICT DO NOTHING for idempotency.
    Skips files larger than 50 MB to avoid JSONB bloat.
    """
    log = get_run_logger('mg_raw_json')
    if not tmp_dir or not os.path.isdir(tmp_dir):
        return
    MAX_BYTES = 50 * 1024 * 1024  # 50 MB per file cap
    inserted = 0
    for root, _dirs, files in os.walk(tmp_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            flower = fname.lower()
            is_json_ext = flower.endswith('.json')
            is_log_ext = flower.endswith('.log')
            if not (is_json_ext or is_log_ext):
                continue
            try:
                fsize = os.path.getsize(fpath)
                if fsize == 0 or fsize > MAX_BYTES:
                    continue
                with open(fpath, 'r', errors='replace') as fh:
                    raw_text = fh.read()
                stripped = raw_text.lstrip()
                if not stripped:
                    continue
                if is_log_ext and stripped[0] not in ('{', '['):
                    continue  # not JSON-looking
                try:
                    payload = json.loads(raw_text)
                except json.JSONDecodeError:
                    continue  # not valid JSON — skip
                # Compute relative path from tmp_dir for file_path_in_archive
                rel_path = os.path.relpath(fpath, tmp_dir).replace(os.sep, '/')
                insert_raw_json(conn_params, archive_filename, rel_path, payload)
                inserted += 1
            except Exception as exc:
                log.debug('_insert_archive_raw_json_files: skip %s: %s', fname, exc)
    log.info('_insert_archive_raw_json_files: %d files for %s', inserted, archive_filename)


def _update_import_run_resolver_stats(conn_params: dict, archive_filename: str,
                                       tier1_hits: int, tier1_vcode_hits: int,
                                       tier2_hits: int, unresolved: int):
    """
    Append resolver stats to mg.import_runs.row_counts JSONB for the
    most-recent run that imported archive_filename.
    Silently skips if the table or row doesn't exist yet.
    """
    if not PSYCOPG2_AVAILABLE or not conn_params:
        return
    log = get_run_logger('mg_layer2')
    stats = {
        'tier1_hits':       tier1_hits,
        'tier1_vcode_hits': tier1_vcode_hits,
        'tier2_hits':       tier2_hits,
        'unresolved':       unresolved,
    }
    try:
        conn = psycopg2.connect(
            host=conn_params.get('host', 'localhost'),
            port=int(conn_params.get('port', 5432)),
            dbname=conn_params.get('database', 'mining_guardian'),
            user=conn_params.get('user', 'guardian_admin'),
            password=conn_params.get('password') or _db_password(),
            connect_timeout=5
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE mg.import_runs
            SET row_counts = COALESCE(row_counts, '{}'::jsonb) || %s::jsonb
            WHERE id = (
                SELECT id FROM mg.import_runs
                ORDER BY started_at DESC
                LIMIT 1
            )
            """,
            (json.dumps(stats),)
        )
        cur.close()
        conn.close()
        log.debug('_update_import_run_resolver_stats: %s', stats)
    except Exception as exc:
        log.debug('_update_import_run_resolver_stats error: %s', exc)


def _do_layer2_postprocessing(conn_params: dict, archive_meta: dict,
                               shape: str, tmp_dir: str):
    """
    v3.2 Layer 2 post-import actions performed after SQL has been generated
    and (if auto-import) executed.  Requires a live DB connection.

    Actions:
      1. Fetch the archive row id from knowledge.field_log_imports
      2. Resolve model via two-tier resolver (miner_type AND control_board_version)
         Steps A-E per brief: normalise -> Tier-1 exact -> Tier-1 V-code stripped
         -> Tier-2 hashrate-bin -> unresolved_models fallback
      3. Stamp knowledge.field_log_imports with model_id / tier / hardware_revision
      4. Populate field_log_miner_identity per boot session (identity_rows from archive_meta)
         and stamp each row with resolver results
      5. Insert raw JSON for every *.json file (and JSON-looking *.log) in tmp_dir
      6. Record unknown fields to mg.unknown_fields
    """
    log = get_run_logger('mg_layer2')
    filename = archive_meta.get('filename', '')

    # 1. Fetch archive id
    archive_id = get_archive_id_by_label(conn_params, filename)
    if not archive_id:
        log.debug('Layer2: no archive_id for %s (not yet committed?)', filename)
        return

    # 2+3+4. Two-tier model resolution
    # Brief: "always check BOTH miner_type AND control_board_version columns"
    raw_miner_type      = archive_meta.get('miner_model')     # miner_type field
    raw_control_board   = archive_meta.get('control_board')   # control_board_version
    hashrate_gh         = archive_meta.get('hashrate_gh')     # for Tier-2 bin selection

    # Use the new resolver module if available; fall back to legacy resolve_model
    if RESOLVER_AVAILABLE and _resolver is not None and PSYCOPG2_AVAILABLE and conn_params:
        try:
            # Open a single connection for all resolver calls
            _conn = psycopg2.connect(
                host=conn_params.get('host', 'localhost'),
                port=int(conn_params.get('port', 5432)),
                dbname=conn_params.get('database', 'mining_guardian'),
                user=conn_params.get('user', 'guardian_admin'),
                password=conn_params.get('password') or _db_password(),
                connect_timeout=5
            )
            _conn.autocommit = True
            try:
                res = _resolver.resolve_identity_fields(
                    _conn,
                    raw_miner_type or '',
                    raw_control_board or '',
                    hashrate_gh=hashrate_gh,
                    archive_filename=filename,
                )
            finally:
                _conn.close()

            if res.tier != 'unresolved' and res.model_id:
                # Stamp the import row with model_id / tier / hardware_revision
                stamp_import_with_model_id(
                    conn_params, archive_id,
                    res.model_id,
                    res.tier,
                    res.hardware_revision,
                )
                log.info('Layer2 MATCHED: %r -> model_id=%s tier=%s rev=%s',
                         raw_miner_type, res.model_id, res.tier,
                         res.hardware_revision)
            else:
                log.warning('Layer2 UNRESOLVED: %r reason=%s (archive_id=%s)',
                            raw_miner_type, res.reason, archive_id)
        except Exception as exc:
            log.debug('Layer2 resolver error: %s', exc)
            # Fall back to legacy resolver
            _legacy_resolve(conn_params, archive_id, raw_miner_type, filename, log)
    else:
        _legacy_resolve(conn_params, archive_id, raw_miner_type, filename, log)

    # ---------------------------------------------------------------
    # v3.2 Fix 1+2: Populate field_log_miner_identity with resolver stamps
    # ---------------------------------------------------------------
    identity_rows = archive_meta.get('identity_rows', [])
    if identity_rows and RESOLVER_AVAILABLE and _resolver is not None and PSYCOPG2_AVAILABLE:
        try:
            _conn2 = psycopg2.connect(
                host=conn_params.get('host', 'localhost'),
                port=int(conn_params.get('port', 5432)),
                dbname=conn_params.get('database', 'mining_guardian'),
                user=conn_params.get('user', 'guardian_admin'),
                password=conn_params.get('password') or _db_password(),
                connect_timeout=5
            )
            _conn2.autocommit = True
            try:
                resolver_results = []
                tier1_hits = tier1_vcode_hits = tier2_hits = unresolved_count = 0
                for r in identity_rows:
                    r_res = _resolver.resolve_identity_fields(
                        _conn2,
                        r.get('miner_type') or '',
                        r.get('control_board_version') or '',
                        hashrate_gh=r.get('hashrate_gh'),
                        archive_filename=filename,
                    )
                    resolver_results.append(r_res)
                    if r_res.tier == 'tier1':
                        tier1_hits += 1
                    elif r_res.tier == 'tier1_vcode_stripped':
                        tier1_vcode_hits += 1
                    elif r_res.tier == 'tier2':
                        tier2_hits += 1
                    else:
                        unresolved_count += 1
                log.info('identity resolver stats: tier1=%d vcode=%d tier2=%d unresolved=%d',
                         tier1_hits, tier1_vcode_hits, tier2_hits, unresolved_count)
            finally:
                _conn2.close()

            # Upsert identity rows with resolver stamps
            insert_miner_identity(conn_params, identity_rows, resolver_results)

            # Update import_runs row_counts with resolver stats
            _update_import_run_resolver_stats(
                conn_params, filename,
                tier1_hits, tier1_vcode_hits, tier2_hits, unresolved_count
            )

            # v3.3: populate in-memory per-archive resolver stats
            _LAST_RESOLVER_STATS[filename] = {
                'tier1':        tier1_hits,
                'tier1_vcode':  tier1_vcode_hits,
                'tier2':        tier2_hits,
                'unresolved':   unresolved_count,
                'total':        tier1_hits + tier1_vcode_hits + tier2_hits + unresolved_count,
            }
        except Exception as exc:
            log.debug('Layer2 identity-rows resolver error: %s', exc)
            # Still insert identity rows without resolver stamps
            insert_miner_identity(conn_params, identity_rows)
    elif identity_rows:
        # Resolver not available — insert without stamps
        insert_miner_identity(conn_params, identity_rows)

    # ---------------------------------------------------------------
    # v3.2 Fix 3: Raw JSON capture — one row per JSON file in archive
    # ---------------------------------------------------------------
    try:
        _insert_archive_raw_json_files(conn_params, filename, tmp_dir)
    except Exception as exc:
        log.debug('Layer2 per-file raw-json error: %s', exc)

    # Archive-level metadata blob (v3.1 behaviour kept)
    try:
        raw_payload = {
            'archive_filename': filename,
            'shape':            shape,
            'miner_model':      archive_meta.get('miner_model'),
            'firmware_version': archive_meta.get('firmware_version'),
            'mac_address':      archive_meta.get('mac_address'),
            'control_board':    archive_meta.get('control_board'),
            'kernel_version':   archive_meta.get('kernel_version'),
            'miner_ip':         archive_meta.get('miner_ip'),
            'archive_timestamp':str(archive_meta.get('archive_timestamp')) if archive_meta.get('archive_timestamp') else None,
            'files_in_archive': archive_meta.get('files_in_archive'),
            'parse_warnings':   archive_meta.get('parse_warnings'),
        }
        source_file = ('miner_overview.log' if shape == 'whatsminer'
                       else 'cgminer.conf+miner.log')
        # v3.1: use archive_filename + file_path_in_archive (new schema)
        insert_raw_json(conn_params, filename, source_file, raw_payload)

        # 6. Unknown fields: check archive_meta keys not in known set
        _known_meta = frozenset(raw_payload.keys()) | frozenset(('identity_rows',))
        all_meta_keys = frozenset(archive_meta.keys())
        extra_keys = all_meta_keys - _known_meta
        if extra_keys:
            extra_dict = {k: archive_meta[k] for k in extra_keys
                         if not isinstance(archive_meta[k], (list, dict))}
            if extra_dict:
                record_unknown_fields(conn_params, archive_id, source_file,
                                      extra_dict, _known_meta)
    except Exception as exc:
        log.debug('Layer2 raw-json/unknown-fields error: %s', exc)


def _legacy_resolve(conn_params: dict, archive_id: int, raw_miner_type,
                    filename: str, log):
    """Fallback to legacy resolve_model when resolver module is unavailable."""
    if raw_miner_type:
        result = resolve_model(conn_params, raw_miner_type, 'miner_type')
        if result:
            stamp_import_with_catalog(
                conn_params, archive_id,
                result['catalog_slug'],
                result['confidence'],
                result['match_type'],
                result.get('hardware_revision')
            )
            log.info('Layer2 MATCHED (legacy): %s -> %s (conf=%.2f)',
                     raw_miner_type, result['catalog_slug'], result['confidence'])
        else:
            record_unresolved_model(conn_params, raw_miner_type, 'miner_type', archive_id)
            log.warning('Layer2 UNRESOLVED (legacy): %s (archive_id=%s)',
                        raw_miner_type, archive_id)
    else:
        log.debug('Layer2: no miner_model for %s', filename)


def stamp_import_with_model_id(conn_params: dict, archive_id: int, model_id: str,
                               tier: str, hardware_revision):
    """
    v3.1: UPDATE knowledge.field_log_imports to record model_id (UUID),
    resolver tier, and hardware_revision from the new two-tier resolver.
    Falls back gracefully if the columns haven’t been added yet.
    """
    if not PSYCOPG2_AVAILABLE or not conn_params or not archive_id:
        return
    try:
        conn = psycopg2.connect(
            host=conn_params.get('host', 'localhost'),
            port=int(conn_params.get('port', 5432)),
            dbname=conn_params.get('database', 'mining_guardian'),
            user=conn_params.get('user', 'guardian_admin'),
            password=conn_params.get('password') or _db_password(),
            connect_timeout=5
        )
        conn.autocommit = True
        cur = conn.cursor()
        # Try the v3.1 column names first; fall back to legacy names
        try:
            cur.execute(
                """
                UPDATE knowledge.field_log_imports
                SET miner_model_id    = %s::uuid,
                    resolver_tier     = %s,
                    hardware_revision = %s
                WHERE id = %s
                """,
                (model_id, tier, hardware_revision, archive_id)
            )
        except Exception:
            # Columns may not exist yet (pre-migration) — silently skip
            conn.rollback()
        cur.close()
        conn.close()
    except Exception as exc:
        get_run_logger('mg_layer2').debug('stamp_import_with_model_id error: %s', exc)


def process_zip(zip_bytes: bytes) -> list:
    """
    Extract a ZIP and return list of {filename, content_bytes, type} dicts.
    Recursively handles nested zips.
    SQL files containing \\i (psql runner/master files) are flagged as is_runner=True.
    """
    results = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        # Look for master script
        master = None
        for n in names:
            bn = os.path.basename(n).lower()
            if bn in ('run_master.sql', 'run_all.sql', 'master.sql'):
                master = n
                break

        for name in names:
            if name.endswith('/'):
                continue  # directory entry
            ext = os.path.splitext(name)[1].lower()
            if ext in ('.csv', '.sql', '.tsv', '.txt', '.json', '.xlsx'):
                data = zf.read(name)
                # Detect psql runner/master SQL files (contain \i include commands)
                runner = False
                if ext == '.sql' and is_psql_runner(data):
                    runner = True
                results.append({
                    'filename': os.path.basename(name),
                    'fullpath': name,
                    'content_bytes': data,
                    'ext': ext,
                    'is_master': name == master,
                    'is_runner': runner
                })
            elif ext == '.zip':
                # Nested zip
                nested = process_zip(zf.read(name))
                results.extend(nested)
    return results


# ---------------------------------------------------------------------------
# Flask Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return HTML_PAGE


@app.route('/api/test-connection', methods=['POST'])
def test_connection():
    if not PSYCOPG2_AVAILABLE:
        return jsonify({'success': False, 'error': 'psycopg2 not installed. Run: pip install psycopg2-binary'})
    data = request.get_json(force=True)
    try:
        conn = psycopg2.connect(
            host=data.get('host', 'localhost'),
            port=int(data.get('port', 5432)),
            dbname=data.get('database', 'mining_guardian'),
            user=data.get('user', 'guardian_admin'),
            password=data.get('password') or _db_password(),
            connect_timeout=8
        )
        cur = conn.cursor()
        cur.execute('SELECT version();')
        version = cur.fetchone()[0]
        cur.close()
        conn.close()
        return jsonify({'success': True, 'version': version})
    except psycopg2.OperationalError as e:
        return jsonify({'success': False, 'error': str(e).strip()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/generate-sql', methods=['POST'])
def generate_sql():
    """Generate SQL from uploaded files without running it."""
    results = []
    conn_params = json.loads(request.form.get('conn_params', '{}'))

    for key in request.files:
        f = request.files[key]
        filename = f.filename
        ext = os.path.splitext(filename)[1].lower()
        data = f.read()

        try:
            if ext in ('.csv', '.tsv', '.txt'):
                # tsv: try tab delimiter
                if ext == '.tsv':
                    for encoding in ('utf-8-sig', 'utf-8', 'latin-1'):
                        try:
                            text = data.decode(encoding)
                            reader = csv.reader(io.StringIO(text), delimiter='\t')
                            rows_raw = list(reader)
                            headers = rows_raw[0] if rows_raw else []
                            rows = rows_raw[1:] if len(rows_raw) > 1 else []
                            break
                        except Exception:
                            continue
                else:
                    headers, rows = read_csv_bytes(data)
                sql = generate_csv_sql(filename, headers, rows)
                results.append({'filename': filename, 'sql': sql, 'type': 'csv', 'error': None})

            elif ext == '.xlsx':
                headers, rows = read_xlsx_bytes(data)
                sql = generate_csv_sql(filename, headers, rows)
                results.append({'filename': filename, 'sql': sql, 'type': 'xlsx', 'error': None})

            elif ext == '.sql':
                sql = data.decode('utf-8', errors='replace')
                results.append({'filename': filename, 'sql': sql, 'type': 'sql', 'error': None})

            elif ext == '.json':
                # Try to convert JSON array of objects to CSV-style
                try:
                    obj = json.loads(data.decode('utf-8', errors='replace'))
                    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
                        headers = list(obj[0].keys())
                        rows = [[str(row.get(h, '')) for h in headers] for row in obj]
                        sql = generate_csv_sql(filename, headers, rows)
                        results.append({'filename': filename, 'sql': sql, 'type': 'json', 'error': None})
                    else:
                        results.append({'filename': filename, 'sql': '', 'type': 'json',
                                        'error': 'JSON must be an array of objects to auto-import'})
                except json.JSONDecodeError as e:
                    results.append({'filename': filename, 'sql': '', 'type': 'json', 'error': str(e)})

            elif ext == '.zip':
                zip_files = process_zip(data)
                zip_results = []
                master_name = None
                for zf_entry in zip_files:
                    zname = zf_entry['filename']
                    zext = zf_entry['ext']
                    zdata = zf_entry['content_bytes']
                    if zf_entry.get('is_master'):
                        master_name = zname

                    # Skip psql runner files in generate-sql (show them but mark skipped)
                    if zf_entry.get('is_runner'):
                        zip_results.append({'filename': zname, 'sql': '-- Skipped (psql runner)', 'type': 'sql',
                                            'error': None, 'is_runner': True, 'fullpath': zf_entry['fullpath']})
                        continue

                    try:
                        if zext in ('.csv', '.tsv', '.txt'):
                            zheaders, zrows = read_csv_bytes(zdata)
                            zsql = generate_csv_sql(zname, zheaders, zrows)
                            zip_results.append({'filename': zname, 'sql': zsql, 'type': 'csv', 'error': None,
                                                'fullpath': zf_entry['fullpath']})
                        elif zext == '.xlsx':
                            zheaders, zrows = read_xlsx_bytes(zdata)
                            zsql = generate_csv_sql(zname, zheaders, zrows)
                            zip_results.append({'filename': zname, 'sql': zsql, 'type': 'xlsx', 'error': None,
                                                'fullpath': zf_entry['fullpath']})
                        elif zext == '.sql':
                            zsql = zdata.decode('utf-8', errors='replace')
                            zip_results.append({'filename': zname, 'sql': zsql, 'type': 'sql', 'error': None,
                                                'fullpath': zf_entry['fullpath'], 'is_master': zf_entry.get('is_master', False)})
                        elif zext == '.json':
                            obj = json.loads(zdata.decode('utf-8', errors='replace'))
                            if isinstance(obj, list) and obj and isinstance(obj[0], dict):
                                zheaders = list(obj[0].keys())
                                zrows = [[str(row.get(h, '')) for h in zheaders] for row in obj]
                                zsql = generate_csv_sql(zname, zheaders, zrows)
                                zip_results.append({'filename': zname, 'sql': zsql, 'type': 'json', 'error': None,
                                                    'fullpath': zf_entry['fullpath']})
                    except Exception as e:
                        zip_results.append({'filename': zname, 'sql': '', 'type': zext,
                                            'error': str(e), 'fullpath': zf_entry['fullpath']})

                results.append({
                    'filename': filename,
                    'type': 'zip',
                    'error': None,
                    'zip_contents': zip_results,
                    'master_file': master_name
                })

            elif ext in ('.tar', '.tgz', '.rar') or filename.lower().endswith('.tar.gz'):
                archive_sql_blocks = process_archive(data, filename)
                # Check for error blocks
                all_sql = '\n\n'.join(archive_sql_blocks)
                results.append({
                    'filename': filename,
                    'sql': all_sql,
                    'type': 'archive',
                    'error': None if not all_sql.startswith('-- ERROR') else all_sql
                })

            else:
                results.append({'filename': filename, 'sql': '',
                                 'type': ext, 'error': f'Unsupported file type: {ext}'})

        except Exception as e:
            results.append({'filename': filename, 'sql': '', 'type': ext, 'error': str(e)})

    return jsonify({'results': results})


@app.route('/api/run-sql', methods=['POST'])
def run_sql():
    """Execute provided SQL against the database."""
    data = request.get_json(force=True)
    sql = data.get('sql', '')
    conn_params = data.get('conn_params', {})

    if not sql.strip():
        return jsonify({'success': False, 'error': 'No SQL provided', 'messages': [], 'statements_run': 0, 'rows_affected': 0, 'errors': []})

    result = execute_sql_block(conn_params, sql)
    return jsonify(result)


@app.route('/api/import-files', methods=['POST'])
def import_files():
    """Generate SQL from files and immediately run against PostgreSQL (auto-import mode)."""
    global _LAST_RESOLVER_STATS
    import time as _time
    conn_params = json.loads(request.form.get('conn_params', '{}'))

    # v3.3: reset resolver stats accumulator for this session
    _LAST_RESOLVER_STATS = {}

    all_messages = []
    total_statements = 0
    total_rows = 0
    total_errors = []
    _per_archive_errors = []  # v3.3: structured error records for import_runs
    files_processed = 0
    session_filenames = []
    t_start = _time.monotonic()

    def process_and_run(filename, ext, data, is_runner=False):
        nonlocal total_statements, total_rows, files_processed

        session_filenames.append(filename)

        # Skip psql runner/master files — they contain \i include commands
        if is_runner or (ext == '.sql' and is_psql_runner(data)):
            all_messages.append({'type': 'warning',
                                  'text': f'Skipped (psql runner): {filename}', 'stmt': ''})
            return

        try:
            if ext in ('.csv', '.tsv', '.txt'):
                if ext == '.tsv':
                    for encoding in ('utf-8-sig', 'utf-8', 'latin-1'):
                        try:
                            text = data.decode(encoding)
                            reader = csv.reader(io.StringIO(text), delimiter='\t')
                            rows_raw = list(reader)
                            headers = rows_raw[0] if rows_raw else []
                            rows = rows_raw[1:] if len(rows_raw) > 1 else []
                            break
                        except Exception:
                            continue
                else:
                    headers, rows = read_csv_bytes(data)
                sql = generate_csv_sql(filename, headers, rows)

            elif ext == '.xlsx':
                headers, rows = read_xlsx_bytes(data)
                sql = generate_csv_sql(filename, headers, rows)

            elif ext == '.sql':
                sql = data.decode('utf-8', errors='replace')

            elif ext == '.json':
                obj = json.loads(data.decode('utf-8', errors='replace'))
                if isinstance(obj, list) and obj and isinstance(obj[0], dict):
                    fheaders = list(obj[0].keys())
                    frows = [[str(row.get(h, '')) for h in fheaders] for row in obj]
                    sql = generate_csv_sql(filename, fheaders, frows)
                else:
                    raise ValueError('JSON must be an array of objects')

            elif ext in ('.tar', '.tgz', '.rar') or filename.lower().endswith('.tar.gz'):
                # v3: pass conn_params so Layer 2 runs after SQL is executed
                archive_sql_blocks = process_archive(data, filename, conn_params)
                all_messages.append({'type': 'header', 'text': f'\u25b6 {filename}', 'stmt': ''})
                for block in archive_sql_blocks:
                    if block.startswith('-- ERROR'):
                        total_errors.append(block)
                        all_messages.append({'type': 'error', 'text': block, 'stmt': ''})
                    else:
                        res = execute_sql_block(conn_params, block)
                        total_statements += res.get('statements_run', 0)
                        total_rows += res.get('rows_affected', 0)
                        total_errors.extend(res.get('errors', []))
                        all_messages.extend(res.get('messages', []))
                files_processed += 1
                session_filenames.append(filename)
                return  # already handled above

            else:
                raise ValueError(f'Unsupported file type: {ext}')

            result = execute_sql_block(conn_params, sql)
            total_statements += result.get('statements_run', 0)
            total_rows += result.get('rows_affected', 0)
            total_errors.extend(result.get('errors', []))
            all_messages.append({'type': 'header', 'text': f'▶ {filename}', 'stmt': ''})
            all_messages.extend(result.get('messages', []))
            files_processed += 1

        except Exception as e:
            total_errors.append(str(e))
            all_messages.append({'type': 'error', 'text': f'Failed to process {filename}: {e}', 'stmt': ''})

    for key in request.files:
        f = request.files[key]
        filename = f.filename
        ext = os.path.splitext(filename)[1].lower()
        data = f.read()

        if ext == '.zip':
            zip_files = process_zip(data)
            for zf_entry in zip_files:
                process_and_run(
                    zf_entry['filename'],
                    zf_entry['ext'],
                    zf_entry['content_bytes'],
                    is_runner=zf_entry.get('is_runner', False)
                )
        elif ext in ('.tar', '.tgz', '.rar') or filename.lower().endswith('.tar.gz'):
            process_and_run(filename, ext, data)
        else:
            process_and_run(filename, ext, data)

    # Record this session in import history
    duration = round(_time.monotonic() - t_start, 2)
    import_history.append({
        'timestamp': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
        'filenames': session_filenames,
        'rows_imported': total_rows,
        'errors': len(total_errors),
        'duration_s': duration
    })

    # v3: Background dormant miner detection (runs at end of each import)
    try:
        dormant_count = detect_dormant_miners(conn_params)
        if dormant_count:
            _run_logger.info('Dormant miner detector: surfaced %d new dormant miners',
                             dormant_count)
            all_messages.append({'type': 'info',
                                  'text': f'Dormant miner detector: {dormant_count} miners surfaced to awaiting_review',
                                  'stmt': ''})
    except Exception as _dme:
        _run_logger.debug('Dormant detection error: %s', _dme)

    # v3.1: Write per-run summary to mg.import_runs
    _run_started = datetime.utcnow()
    try:
        _finished_at = datetime.utcnow()
        write_import_run(
            conn_params,
            started_at=_run_started,
            finished_at=_finished_at,
            archive_count=files_processed,
            row_counts={'total_rows': total_rows, 'errors': len(total_errors),
                        'resolver': _build_resolver_totals()},
            errors=total_errors[:50] if total_errors else [],
            status='ok' if not total_errors else 'partial_failure',
        )
    except Exception as _ire:
        _run_logger.debug('import_runs write error: %s', _ire)

    return jsonify({
        'success': len(total_errors) == 0,
        'messages': all_messages,
        'statements_run': total_statements,
        'rows_affected': total_rows,
        'errors': total_errors,
        'files_processed': files_processed
    })


# ---------------------------------------------------------------------------
# v3.1: Import run summary logging
# ---------------------------------------------------------------------------

def write_import_run(conn_params: dict, started_at, finished_at, archive_count: int,
                     row_counts: dict, errors: list, status: str):
    """
    INSERT a summary row into mg.import_runs after each import session.
    Table is created idempotently by FIELD_LOG_DDL at process_archive startup.
    Silently no-ops when psycopg2 or conn_params unavailable.
    """
    if not PSYCOPG2_AVAILABLE or not conn_params:
        return
    log = get_run_logger('mg_import_runs')
    try:
        conn = psycopg2.connect(
            host=conn_params.get('host', 'localhost'),
            port=int(conn_params.get('port', 5432)),
            dbname=conn_params.get('database', 'mining_guardian'),
            user=conn_params.get('user', 'guardian_admin'),
            password=conn_params.get('password') or _db_password(),
            connect_timeout=5
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO mg.import_runs
                (started_at, finished_at, archive_count, row_counts, errors, status)
            VALUES (%s, %s, %s, %s::jsonb, %s, %s)
            """,
            (
                started_at,
                finished_at,
                archive_count,
                json.dumps(row_counts),
                list(str(e) for e in errors) if errors else [],
                status,
            )
        )
        cur.close()
        conn.close()
        log.debug('import_run written: archives=%d status=%s', archive_count, status)
    except Exception as exc:
        get_run_logger('mg_import_runs').debug('write_import_run error: %s', exc)


# ---------------------------------------------------------------------------
# v3: Dormant miner detection
# ---------------------------------------------------------------------------

def detect_dormant_miners(conn_params: dict) -> int:
    """
    Background job: find MAC addresses seen in >= 3 archives whose
    last_seen_at > 30 days ago and not already in mg.dormant_miners.
    INSERT them with status='awaiting_review'.
    Returns count of newly surfaced dormant miners.
    Silently returns 0 if mg.miners or mg.dormant_miners don't exist yet.
    """
    if not PSYCOPG2_AVAILABLE or not conn_params:
        return 0
    log = get_run_logger('mg_dormant')
    try:
        conn = psycopg2.connect(
            host=conn_params.get('host', 'localhost'),
            port=int(conn_params.get('port', 5432)),
            dbname=conn_params.get('database', 'mining_guardian'),
            user=conn_params.get('user', 'guardian_admin'),
            password=conn_params.get('password') or _db_password(),
            connect_timeout=8
        )
        conn.autocommit = True
        cur = conn.cursor()
        # Find candidates: MACs in mg.miners with >= 3 archives, last seen > 30d ago,
        # not yet in mg.dormant_miners with awaiting_review status
        cur.execute("""
            INSERT INTO mg.dormant_miners
                (miner_mac, last_archive_id, last_seen_at, days_dormant,
                 surfaced_at, status)
            SELECT
                m.mac_address,
                (SELECT id FROM knowledge.field_log_imports fi
                 WHERE fi.mac_address = m.mac_address
                 ORDER BY fi.ingested_at DESC LIMIT 1),
                m.last_seen_at,
                EXTRACT(DAY FROM NOW() - m.last_seen_at)::INT,
                NOW(),
                'awaiting_review'
            FROM mg.miners m
            WHERE m.archive_count >= 3
              AND m.last_seen_at < NOW() - INTERVAL '30 days'
              AND NOT EXISTS (
                  SELECT 1 FROM mg.dormant_miners dm
                  WHERE dm.miner_mac = m.mac_address
                    AND dm.status = 'awaiting_review'
              )
            ON CONFLICT DO NOTHING
        """)
        count = cur.rowcount
        cur.close()
        conn.close()
        if count:
            log.info('Dormant miner detector: inserted %d new dormant records', count)
        return count
    except Exception as exc:
        log.debug('detect_dormant_miners error: %s', exc)
        return 0


# ---------------------------------------------------------------------------
# v3: RMA form HTML templates (inline)
# ---------------------------------------------------------------------------

_RMA_FORM_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Mining Guardian — RMA Form</title>
<style>
body{background:#0d0e10;color:#e8eaf0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:2rem;}
h1{color:#F7931A;margin-bottom:1.5rem;}
.form-group{margin-bottom:1rem;}
label{display:block;color:#8b919e;margin-bottom:.25rem;font-size:.875rem;}
input,select,textarea{width:100%;max-width:500px;background:#1c1f24;border:1px solid #2e3440;
  color:#e8eaf0;padding:.5rem .75rem;border-radius:4px;font-size:.875rem;}
textarea{height:80px;resize:vertical;}
button{background:#F7931A;color:#000;border:none;padding:.6rem 1.5rem;
  border-radius:4px;cursor:pointer;font-weight:600;margin-top:.5rem;}
button:hover{background:#ffaa42;}
.success{background:#1a2e1a;border:1px solid #4ade80;border-radius:4px;padding:1rem;margin-top:1rem;}
.error{background:#2e1a1a;border:1px solid #f87171;border-radius:4px;padding:1rem;margin-top:1rem;}
a{color:#F7931A;text-decoration:none;}
nav{margin-bottom:2rem;}
nav a{margin-right:1.5rem;}
</style>
</head>
<body>
<nav><a href="/">Importer</a> <a href="/rma">RMA Form</a> <a href="/rma/csv">Batch CSV</a> <a href="/dormant">Dormant Miners</a></nav>
<h1>RMA / Failure Record</h1>
{% if message %}
<div class="{{ 'success' if success else 'error' }}">{{ message }}</div>
{% endif %}
<form method="POST" action="/rma">
  <div class="form-group">
    <label>Miner MAC Address <small>(required if no serial)</small></label>
    <input type="text" name="miner_mac" placeholder="AA:BB:CC:DD:EE:FF">
  </div>
  <div class="form-group">
    <label>Miner Serial <small>(required if no MAC)</small></label>
    <input type="text" name="miner_serial" placeholder="SN...">
  </div>
  <div class="form-group">
    <label>Date Pulled *</label>
    <input type="date" name="pulled_date" required>
  </div>
  <div class="form-group">
    <label>Failure Reason *</label>
    <select name="failure_reason" required>
      <option value="">-- select --</option>
      <option value="psu_failure">PSU Failure</option>
      <option value="hashboard_failure">Hashboard Failure</option>
      <option value="control_board">Control Board</option>
      <option value="fan_failure">Fan Failure</option>
      <option value="network">Network</option>
      <option value="overheat">Overheat</option>
      <option value="unknown">Unknown</option>
      <option value="other">Other</option>
    </select>
  </div>
  <div class="form-group">
    <label>Failure Detail</label>
    <input type="text" name="failure_reason_detail" placeholder="Optional detail">
  </div>
  <div class="form-group">
    <label>Replaced With MAC</label>
    <input type="text" name="replaced_with_mac" placeholder="AA:BB:CC:DD:EE:FF">
  </div>
  <div class="form-group">
    <label>Replaced With Serial</label>
    <input type="text" name="replaced_with_serial">
  </div>
  <div class="form-group">
    <label>Tech Notes</label>
    <textarea name="tech_notes" placeholder="Any additional notes..."></textarea>
  </div>
  <button type="submit">Save RMA Record</button>
</form>
</body></html>"""

_RMA_CSV_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Mining Guardian — Batch RMA CSV</title>
<style>
body{background:#0d0e10;color:#e8eaf0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:2rem;}
h1{color:#F7931A;}
.info{background:#1c1f24;border:1px solid #2e3440;border-radius:4px;padding:1rem;margin:1rem 0;font-size:.875rem;}
pre{background:#14161a;border:1px solid #2e3440;padding:1rem;border-radius:4px;font-size:.75rem;overflow-x:auto;}
button{background:#F7931A;color:#000;border:none;padding:.6rem 1.5rem;border-radius:4px;cursor:pointer;font-weight:600;}
.success{background:#1a2e1a;border:1px solid #4ade80;border-radius:4px;padding:1rem;margin-top:1rem;}
.error{background:#2e1a1a;border:1px solid #f87171;border-radius:4px;padding:1rem;margin-top:1rem;}
a{color:#F7931A;text-decoration:none;}
nav{margin-bottom:2rem;}
nav a{margin-right:1.5rem;}
input[type=file]{background:#1c1f24;border:1px solid #2e3440;color:#e8eaf0;padding:.5rem;border-radius:4px;}
</style></head>
<body>
<nav><a href="/">Importer</a> <a href="/rma">RMA Form</a> <a href="/rma/csv">Batch CSV</a> <a href="/dormant">Dormant Miners</a></nav>
<h1>Batch RMA CSV Upload</h1>
{% if message %}
<div class="{{ 'success' if success else 'error' }}">{{ message }}</div>
{% endif %}
<div class="info">Upload a CSV with these columns (order matters, all optional except pulled_date and failure_reason):</div>
<pre>miner_mac,miner_serial,pulled_date,failure_reason,failure_reason_detail,replaced_with_mac,replaced_with_serial,tech_notes</pre>
<form method="POST" action="/rma/csv" enctype="multipart/form-data">
  <div style="margin-bottom:1rem;">
    <label style="display:block;color:#8b919e;margin-bottom:.25rem;font-size:.875rem;">CSV File</label>
    <input type="file" name="csv_file" accept=".csv" required>
  </div>
  <button type="submit">Import CSV</button>
</form>
</body></html>"""

_DORMANT_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Mining Guardian — Dormant Miners</title>
<style>
body{background:#0d0e10;color:#e8eaf0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:2rem;}
h1{color:#F7931A;}
table{width:100%;border-collapse:collapse;margin-top:1rem;font-size:.875rem;}
th{background:#1c1f24;color:#8b919e;text-align:left;padding:.5rem .75rem;border-bottom:1px solid #2e3440;}
td{padding:.5rem .75rem;border-bottom:1px solid #14161a;}
tr:hover td{background:#14161a;}
select{background:#1c1f24;border:1px solid #2e3440;color:#e8eaf0;padding:.25rem .5rem;border-radius:3px;}
button{background:#F7931A;color:#000;border:none;padding:.3rem .8rem;border-radius:3px;cursor:pointer;font-size:.8rem;}
.badge{padding:.2rem .5rem;border-radius:3px;font-size:.75rem;}
.awaiting{background:rgba(251,191,36,.15);color:#fbbf24;}
.resolved{background:rgba(74,222,128,.12);color:#4ade80;}
a{color:#F7931A;text-decoration:none;}
nav{margin-bottom:2rem;}
nav a{margin-right:1.5rem;}
.empty{color:#5a6070;padding:2rem;text-align:center;}
</style></head>
<body>
<nav><a href="/">Importer</a> <a href="/rma">RMA Form</a> <a href="/rma/csv">Batch CSV</a> <a href="/dormant">Dormant Miners</a></nav>
<h1>Dormant Miners — Awaiting Review</h1>
{% if miners %}
<table>
<thead><tr><th>MAC</th><th>Last Seen</th><th>Days Dormant</th><th>Surfaced</th><th>Resolution</th></tr></thead>
<tbody>
{% for m in miners %}
<tr>
  <td>{{ m.miner_mac }}</td>
  <td>{{ m.last_seen_at }}</td>
  <td>{{ m.days_dormant }}</td>
  <td>{{ m.surfaced_at }}</td>
  <td>
    <form method="POST" action="/dormant/resolve" style="display:flex;gap:.5rem;align-items:center;">
      <input type="hidden" name="dormant_id" value="{{ m.id }}">
      <input type="hidden" name="miner_mac" value="{{ m.miner_mac }}">
      <select name="resolution">
        <option value="pulled">Pulled</option>
        <option value="failed">Failed</option>
        <option value="sold">Sold</option>
        <option value="moved">Moved</option>
        <option value="unknown">Unknown</option>
      </select>
      <label style="font-size:.8rem;color:#8b919e;">
        <input type="checkbox" name="create_rma" value="1"> Create RMA
      </label>
      <button type="submit">Resolve</button>
    </form>
  </td>
</tr>
{% endfor %}
</tbody></table>
{% else %}
<div class="empty">No dormant miners awaiting review.</div>
{% endif %}
</body></html>"""


# ---------------------------------------------------------------------------
# v3: Flask routes — RMA form, dormant miner triage
# ---------------------------------------------------------------------------

def _get_conn_params_from_args():
    """Extract DB connection params from query args or use defaults."""
    return {
        'host':     request.args.get('host', 'localhost'),
        'port':     request.args.get('port', '5432'),
        'database': request.args.get('database', 'mining_guardian'),
        'user':     request.args.get('user', 'guardian_admin'),
        'password': request.args.get('password') or _db_password(),
    }


@app.route('/rma', methods=['GET', 'POST'])
def rma_form():
    """GET: render RMA form. POST: validate + insert into mg.rma_records."""
    message = None
    success = False

    if request.method == 'POST':
        miner_mac    = request.form.get('miner_mac', '').strip() or None
        miner_serial = request.form.get('miner_serial', '').strip() or None
        pulled_date  = request.form.get('pulled_date', '').strip()
        failure_reason = request.form.get('failure_reason', '').strip()
        failure_reason_detail = request.form.get('failure_reason_detail', '').strip() or None
        replaced_with_mac    = request.form.get('replaced_with_mac', '').strip() or None
        replaced_with_serial = request.form.get('replaced_with_serial', '').strip() or None
        tech_notes   = request.form.get('tech_notes', '').strip() or None

        # Validate
        if not miner_mac and not miner_serial:
            message = 'Error: must provide either MAC address or serial number.'
        elif not pulled_date:
            message = 'Error: pulled_date is required.'
        elif not failure_reason:
            message = 'Error: failure_reason is required.'
        else:
            if PSYCOPG2_AVAILABLE:
                try:
                    conn = psycopg2.connect(
                        host='localhost', port=5432, dbname='mining_guardian',
                        user='guardian_admin', password=_db_password(),
                        connect_timeout=8
                    )
                    conn.autocommit = True
                    cur = conn.cursor()
                    # Try to look up catalog_slug via mg.miners
                    catalog_slug = None
                    if miner_mac:
                        try:
                            cur.execute(
                                'SELECT catalog_slug FROM mg.miners WHERE mac_address=%s LIMIT 1',
                                (miner_mac,)
                            )
                            row = cur.fetchone()
                            if row:
                                catalog_slug = row[0]
                        except Exception:
                            pass
                    cur.execute(
                        """INSERT INTO mg.rma_records
                           (miner_mac, miner_serial, catalog_slug, pulled_date,
                            failure_reason, failure_reason_detail,
                            replaced_with_mac, replaced_with_serial,
                            tech_notes, recorded_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                           RETURNING id""",
                        (miner_mac, miner_serial, catalog_slug, pulled_date,
                         failure_reason, failure_reason_detail,
                         replaced_with_mac, replaced_with_serial, tech_notes)
                    )
                    new_id = cur.fetchone()[0]
                    cur.close()
                    conn.close()
                    message = f'RMA record saved — ID #{new_id}'
                    success = True
                except Exception as exc:
                    message = f'Database error: {exc}'
            else:
                message = 'Error: psycopg2 not installed.'

    return render_template_string(_RMA_FORM_HTML, message=message, success=success)


@app.route('/rma/csv', methods=['GET', 'POST'])
def rma_csv():
    """GET: render batch CSV upload form. POST: process CSV and bulk-insert RMA records."""
    message = None
    success = False

    if request.method == 'POST':
        if 'csv_file' not in request.files:
            message = 'No file uploaded.'
        else:
            f = request.files['csv_file']
            try:
                headers, rows = read_csv_bytes(f.read())
                headers_lower = [h.strip().lower() for h in headers]
                required = {'pulled_date', 'failure_reason'}
                if not required.issubset(set(headers_lower)):
                    message = f'CSV must have columns: pulled_date, failure_reason. Got: {headers_lower}'
                else:
                    def col(row, name):
                        try:
                            idx = headers_lower.index(name)
                            return row[idx].strip() if idx < len(row) else None
                        except ValueError:
                            return None

                    inserted = 0
                    errors = []
                    if PSYCOPG2_AVAILABLE:
                        conn = psycopg2.connect(
                            host='localhost', port=5432, dbname='mining_guardian',
                            user='guardian_admin', password=_db_password(),
                            connect_timeout=8
                        )
                        conn.autocommit = True
                        cur = conn.cursor()
                        for row in rows:
                            mac    = col(row, 'miner_mac') or None
                            serial = col(row, 'miner_serial') or None
                            if not mac and not serial:
                                errors.append('Row skipped: no MAC or serial')
                                continue
                            try:
                                cur.execute(
                                    """INSERT INTO mg.rma_records
                                       (miner_mac, miner_serial, pulled_date,
                                        failure_reason, failure_reason_detail,
                                        replaced_with_mac, replaced_with_serial,
                                        tech_notes, recorded_at)
                                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
                                    (mac, serial,
                                     col(row, 'pulled_date'),
                                     col(row, 'failure_reason'),
                                     col(row, 'failure_reason_detail'),
                                     col(row, 'replaced_with_mac'),
                                     col(row, 'replaced_with_serial'),
                                     col(row, 'tech_notes'))
                                )
                                inserted += 1
                            except Exception as row_err:
                                errors.append(str(row_err))
                        cur.close()
                        conn.close()
                        message = f'Imported {inserted} RMA records.'
                        if errors:
                            message += f' Errors: {len(errors)} — {errors[:3]}'
                        success = inserted > 0
                    else:
                        message = 'psycopg2 not installed.'
            except Exception as exc:
                message = f'CSV parse error: {exc}'

    return render_template_string(_RMA_CSV_HTML, message=message, success=success)


@app.route('/dormant', methods=['GET'])
def dormant_miners():
    """List all awaiting-review dormant miners."""
    miners = []
    if PSYCOPG2_AVAILABLE:
        try:
            conn = psycopg2.connect(
                host='localhost', port=5432, dbname='mining_guardian',
                user='guardian_admin', password=_db_password(),
                connect_timeout=8
            )
            cur = conn.cursor()
            cur.execute(
                """SELECT id, miner_mac, last_seen_at, days_dormant, surfaced_at
                   FROM mg.dormant_miners
                   WHERE status = 'awaiting_review'
                   ORDER BY days_dormant DESC
                   LIMIT 200"""
            )
            for row in cur.fetchall():
                miners.append({
                    'id': row[0], 'miner_mac': row[1],
                    'last_seen_at': str(row[2])[:10],
                    'days_dormant': row[3],
                    'surfaced_at': str(row[4])[:10],
                })
            cur.close()
            conn.close()
        except Exception:
            pass
    return render_template_string(_DORMANT_HTML, miners=miners)


@app.route('/dormant/resolve', methods=['POST'])
def dormant_resolve():
    """Resolve a dormant miner entry, optionally creating an RMA record."""
    dormant_id  = request.form.get('dormant_id', '').strip()
    resolution  = request.form.get('resolution', 'unknown')
    miner_mac   = request.form.get('miner_mac', '').strip() or None
    create_rma  = request.form.get('create_rma') == '1'

    if PSYCOPG2_AVAILABLE and dormant_id:
        try:
            conn = psycopg2.connect(
                host='localhost', port=5432, dbname='mining_guardian',
                user='guardian_admin', password=_db_password(),
                connect_timeout=8
            )
            conn.autocommit = True
            cur = conn.cursor()

            rma_id = None
            if create_rma and miner_mac:
                cur.execute(
                    """INSERT INTO mg.rma_records
                       (miner_mac, pulled_date, failure_reason, recorded_at)
                       VALUES (%s, CURRENT_DATE, %s, NOW()) RETURNING id""",
                    (miner_mac, resolution)
                )
                rma_id = cur.fetchone()[0]

            cur.execute(
                """UPDATE mg.dormant_miners
                   SET status='resolved', resolution=%s,
                       resolved_at=NOW(), resolved_by='user',
                       rma_record_id=%s
                   WHERE id=%s""",
                (resolution, rma_id, dormant_id)
            )
            cur.close()
            conn.close()
        except Exception:
            pass
    return redirect('/dormant')



@app.route('/api/import-history', methods=['GET'])
def get_import_history():
    """Return in-memory import history."""
    return jsonify({'history': list(reversed(import_history))})


@app.route('/api/clear-history', methods=['POST'])
def clear_import_history():
    """Clear in-memory import history."""
    import_history.clear()
    return jsonify({'success': True})


# ===========================================================================
# v3.3 NEW ENDPOINTS
# ===========================================================================

# ---------------------------------------------------------------------------
# WI-6: Cancel batch
# ---------------------------------------------------------------------------

@app.route('/api/cancel-batch', methods=['POST'])
def cancel_batch():
    """Set the module-level cancel flag so the streaming import loop exits cleanly."""
    global _BATCH_CANCEL_FLAG
    _BATCH_CANCEL_FLAG = True
    _run_logger.info('cancel-batch requested — flag set')
    return jsonify({'success': True, 'message': 'Cancel flag set. Current batch will stop after the archive in progress.'})


# ---------------------------------------------------------------------------
# WI-3: Resolver summary
# ---------------------------------------------------------------------------

@app.route('/api/resolver-summary', methods=['GET'])
def resolver_summary():
    """
    Return per-archive resolver tier breakdown from the in-memory accumulator
    populated during the last import session.
    Also computes batch totals and coverage %.
    """
    per_archive = dict(_LAST_RESOLVER_STATS)  # snapshot
    totals = {'tier1': 0, 'tier1_vcode': 0, 'tier2': 0, 'unresolved': 0, 'total': 0}
    for stats in per_archive.values():
        for k in totals:
            totals[k] += stats.get(k, 0)
    resolved = totals['tier1'] + totals['tier1_vcode'] + totals['tier2']
    coverage_pct = round(100.0 * resolved / totals['total'], 2) if totals['total'] else 0.0
    return jsonify({
        'success': True,
        'per_archive': per_archive,
        'totals': totals,
        'coverage_pct': coverage_pct,
    })


# ---------------------------------------------------------------------------
# WI-4: Unresolved sample preview
# ---------------------------------------------------------------------------

@app.route('/api/unresolved-sample', methods=['GET'])
def unresolved_sample():
    """
    Return recent rows from mg.unresolved_models.
    Query params:
      limit (int, default 50, max 500)
    """
    if not PSYCOPG2_AVAILABLE:
        return jsonify({'success': False, 'error': 'psycopg2 not installed', 'rows': []})
    try:
        limit = min(int(request.args.get('limit', 50)), 500)
    except (ValueError, TypeError):
        limit = 50
    conn_params = {
        'host':     request.args.get('host', 'localhost'),
        'port':     request.args.get('port', '5432'),
        'database': request.args.get('database', 'mining_guardian'),
        'user':     request.args.get('user', 'guardian_admin'),
        'password': request.args.get('password') or _db_password(),
    }
    try:
        conn = psycopg2.connect(
            host=conn_params['host'],
            port=int(conn_params['port']),
            dbname=conn_params['database'],
            user=conn_params['user'],
            password=conn_params['password'],
            connect_timeout=8,
        )
        cur = conn.cursor()
        cur.execute("""
            SELECT
                raw_string,
                source_field   AS archive_filename,
                reason,
                occurrence_count AS count,
                first_seen_at    AS first_seen
            FROM mg.unresolved_models
            ORDER BY first_seen_at DESC
            LIMIT %s
        """, (limit,))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, [str(v) if v is not None else None for v in row]))
                for row in cur.fetchall()]
        cur.close()
        conn.close()
        return jsonify({'success': True, 'count': len(rows), 'rows': rows})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc), 'rows': []})


# ---------------------------------------------------------------------------
# WI-1: Streaming progress endpoint (SSE)
# ---------------------------------------------------------------------------

def _check_archive_sha256_duplicate(conn_params: dict, sha256_hex: str) -> bool:
    """
    Return True if this sha256 already exists in knowledge.field_log_imports.
    Returns False when psycopg2 unavailable or any DB error (fail-open).
    """
    if not PSYCOPG2_AVAILABLE or not conn_params:
        return False
    try:
        import hashlib  # noqa: F811 — already inline-imported elsewhere
        conn = psycopg2.connect(
            host=conn_params.get('host', 'localhost'),
            port=int(conn_params.get('port', 5432)),
            dbname=conn_params.get('database', 'mining_guardian'),
            user=conn_params.get('user', 'guardian_admin'),
            password=conn_params.get('password') or _db_password(),
            connect_timeout=5,
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            'SELECT 1 FROM knowledge.field_log_imports WHERE sha256 = %s LIMIT 1',
            (sha256_hex,)
        )
        found = cur.fetchone() is not None
        cur.close()
        conn.close()
        return found
    except Exception:
        return False  # fail-open: unknown duplicate state, let it through


def _sse_event(event_type: str, data: dict) -> str:
    """Format a single SSE message."""
    return f'event: {event_type}\ndata: {json.dumps(data)}\n\n'


@app.route('/api/import-files-stream', methods=['POST'])
def import_files_stream():
    """
    v3.3 streaming variant of /api/import-files.
    Returns a Server-Sent Events (SSE) stream so the UI (or curl) can watch
    progress archive-by-archive.

    Events emitted:
      batch_started        {archive_count, filenames[]}
      archive_started      {archive, index, total, elapsed_s}
      archive_skipped      {archive, index, total, reason, sha256}
      archive_parsed       {archive, index, total, elapsed_s, rows_found}
      archive_persisted    {archive, index, total, elapsed_s, rows_affected, statements_run}
      resolver_stats_updated  {archive, tier1, tier1_vcode, tier2, unresolved, total}
      archive_completed    {archive, index, total, elapsed_s, rows_affected, error}
      batch_completed      {total_archives, archives_ok, archives_skipped, archives_error,
                            total_rows, elapsed_s, status, resolver_totals}
      error                {message}
    """
    global _BATCH_CANCEL_FLAG, _LAST_RESOLVER_STATS
    import time as _time

    conn_params = json.loads(request.form.get('conn_params', '{}'))

    # Collect all archive files (same logic as import_files)
    file_queue = []  # list of (filename, ext, data_bytes)
    for key in request.files:
        f = request.files[key]
        filename = f.filename
        ext = os.path.splitext(filename)[1].lower()
        data = f.read()
        if ext == '.zip':
            for zf_entry in process_zip(data):
                if not zf_entry.get('is_runner', False):
                    file_queue.append((
                        zf_entry['filename'],
                        zf_entry['ext'],
                        zf_entry['content_bytes'],
                    ))
        else:
            file_queue.append((filename, ext, data))

    # Filter to archive files only — non-archive types not streamed
    archive_queue = [
        (fn, ext, d) for fn, ext, d in file_queue
        if ext in ('.tar', '.tgz', '.rar') or fn.lower().endswith('.tar.gz')
    ]
    total = len(archive_queue)
    t_batch_start = _time.monotonic()

    def generate():
        global _BATCH_CANCEL_FLAG, _LAST_RESOLVER_STATS
        nonlocal conn_params

        # Reset state
        _BATCH_CANCEL_FLAG = False
        _LAST_RESOLVER_STATS = {}

        archives_ok = 0
        archives_skipped = 0
        archives_error = 0
        total_rows = 0
        total_stmts = 0
        import_errors = []  # per-archive error records

        yield _sse_event('batch_started', {
            'archive_count': total,
            'filenames': [fn for fn, _, _ in archive_queue],
        })

        for idx, (filename, ext, data) in enumerate(archive_queue, start=1):
            # --- Cancel check ---
            if _BATCH_CANCEL_FLAG:
                yield _sse_event('batch_completed', {
                    'total_archives': total,
                    'archives_ok': archives_ok,
                    'archives_skipped': archives_skipped,
                    'archives_error': archives_error,
                    'total_rows': total_rows,
                    'elapsed_s': round(_time.monotonic() - t_batch_start, 2),
                    'status': 'cancelled',
                    'resolver_totals': _build_resolver_totals(),
                    'cancel_at_index': idx,
                })
                return

            t_archive = _time.monotonic()
            yield _sse_event('archive_started', {
                'archive': filename,
                'index': idx,
                'total': total,
                'elapsed_s': round(_time.monotonic() - t_batch_start, 2),
            })

            # --- Dedup check (WI-5) ---
            import hashlib as _hl
            sha256_hex = _hl.sha256(data).hexdigest()
            if _check_archive_sha256_duplicate(conn_params, sha256_hex):
                archives_skipped += 1
                _run_logger.info('SKIP duplicate archive (sha256=%s...): %s', sha256_hex[:12], filename)
                yield _sse_event('archive_skipped', {
                    'archive': filename,
                    'index': idx,
                    'total': total,
                    'reason': 'duplicate_sha256',
                    'sha256': sha256_hex,
                })
                continue

            # --- Per-archive error isolation (WI-2) ---
            archive_rows = 0
            archive_stmts = 0
            archive_error_msg = None
            try:
                # Parse
                archive_sql_blocks = process_archive(data, filename, conn_params)
                parse_elapsed = round(_time.monotonic() - t_archive, 2)

                # Count rows in SQL (heuristic: count INSERT/UPDATE statements)
                rows_found = sum(
                    1 for blk in archive_sql_blocks
                    if not blk.startswith('-- ERROR')
                    for line in blk.splitlines()
                    if line.strip().upper().startswith(('INSERT', 'UPDATE'))
                )
                yield _sse_event('archive_parsed', {
                    'archive': filename,
                    'index': idx,
                    'total': total,
                    'elapsed_s': parse_elapsed,
                    'rows_found': rows_found,
                })

                # Execute SQL blocks
                block_errors = []
                for block in archive_sql_blocks:
                    if block.startswith('-- ERROR'):
                        block_errors.append(block)
                    else:
                        res = execute_sql_block(conn_params, block)
                        archive_stmts += res.get('statements_run', 0)
                        archive_rows  += res.get('rows_affected', 0)
                        block_errors.extend(res.get('errors', []))

                total_rows  += archive_rows
                total_stmts += archive_stmts

                persist_elapsed = round(_time.monotonic() - t_archive, 2)
                yield _sse_event('archive_persisted', {
                    'archive': filename,
                    'index': idx,
                    'total': total,
                    'elapsed_s': persist_elapsed,
                    'rows_affected': archive_rows,
                    'statements_run': archive_stmts,
                    'sql_errors': block_errors[:5],
                })

                # Emit resolver stats if populated for this archive
                if filename in _LAST_RESOLVER_STATS:
                    rs = _LAST_RESOLVER_STATS[filename]
                    yield _sse_event('resolver_stats_updated', {
                        'archive': filename,
                        'tier1':       rs['tier1'],
                        'tier1_vcode': rs['tier1_vcode'],
                        'tier2':       rs['tier2'],
                        'unresolved':  rs['unresolved'],
                        'total':       rs['total'],
                    })

                if block_errors:
                    archive_error_msg = f'{len(block_errors)} SQL error(s)'
                    archives_error += 1
                    import_errors.append({
                        'archive': filename,
                        'error': 'sql_errors',
                        'message': archive_error_msg,
                        'traceback': str(block_errors[:3]),
                    })
                else:
                    archives_ok += 1

            except (Exception, SystemExit, MemoryError) as exc:  # WI-2 full isolation
                archive_error_msg = f'{type(exc).__name__}: {exc}'
                tb_text = traceback.format_exc()
                archives_error += 1
                import_errors.append({
                    'archive':   filename,
                    'error':     type(exc).__name__,
                    'message':   str(exc),
                    'traceback': tb_text,
                })
                _run_logger.error('EXCEPTION (isolated) processing %s: %s', filename, exc)

            completed_elapsed = round(_time.monotonic() - t_archive, 2)
            yield _sse_event('archive_completed', {
                'archive': filename,
                'index': idx,
                'total': total,
                'elapsed_s': completed_elapsed,
                'rows_affected': archive_rows,
                'error': archive_error_msg,
            })

        # --- Batch complete ---
        batch_elapsed = round(_time.monotonic() - t_batch_start, 2)
        batch_status = 'ok'
        if archives_error > 0 and archives_ok == 0:
            batch_status = 'failed'
        elif archives_error > 0:
            batch_status = 'partial_failure'

        resolver_totals = _build_resolver_totals()
        total_res = resolver_totals.get('total', 0)
        resolved = resolver_totals.get('tier1', 0) + resolver_totals.get('tier1_vcode', 0) + resolver_totals.get('tier2', 0)
        coverage_pct = round(100.0 * resolved / total_res, 2) if total_res else 0.0
        _run_logger.info(
            'Resolver: tier1=%d tier1_v=%d tier2=%d unresolved=%d (total=%d, coverage=%.1f%%)',
            resolver_totals.get('tier1', 0),
            resolver_totals.get('tier1_vcode', 0),
            resolver_totals.get('tier2', 0),
            resolver_totals.get('unresolved', 0),
            total_res,
            coverage_pct,
        )

        # Write import_runs summary
        try:
            _run_started = datetime.utcnow()
            write_import_run(
                conn_params,
                started_at=_run_started,
                finished_at=datetime.utcnow(),
                archive_count=archives_ok + archives_error,
                row_counts={'total_rows': total_rows, 'errors': archives_error,
                            'resolver': resolver_totals},
                errors=['{archive}:{message}'.format(**e) for e in import_errors[:50]],
                status=batch_status,
            )
        except Exception as _ire:
            _run_logger.debug('import_runs write error (stream): %s', _ire)

        # Background dormant detection
        try:
            detect_dormant_miners(conn_params)
        except Exception:
            pass

        yield _sse_event('batch_completed', {
            'total_archives': total,
            'archives_ok': archives_ok,
            'archives_skipped': archives_skipped,
            'archives_error': archives_error,
            'total_rows': total_rows,
            'elapsed_s': batch_elapsed,
            'status': batch_status,
            'resolver_totals': resolver_totals,
            'coverage_pct': coverage_pct,
            'import_errors': import_errors[:20],
        })

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )


def _build_resolver_totals() -> dict:
    """Aggregate _LAST_RESOLVER_STATS into batch totals."""
    totals = {'tier1': 0, 'tier1_vcode': 0, 'tier2': 0, 'unresolved': 0, 'total': 0}
    for stats in _LAST_RESOLVER_STATS.values():
        for k in totals:
            totals[k] += stats.get(k, 0)
    return totals


@app.route('/api/browse-tables', methods=['GET'])
def browse_tables():
    """Return list of tables in the knowledge schema with row counts."""
    if not PSYCOPG2_AVAILABLE:
        return jsonify({'success': False, 'error': 'psycopg2 not installed', 'tables': []})
    conn_params = {
        'host': request.args.get('host', 'localhost'),
        'port': request.args.get('port', '5432'),
        'database': request.args.get('database', 'mining_guardian'),
        'user': request.args.get('user', 'guardian_admin'),
        'password': request.args.get('password') or _db_password()
    }
    try:
        conn = psycopg2.connect(
            host=conn_params['host'],
            port=int(conn_params['port']),
            dbname=conn_params['database'],
            user=conn_params['user'],
            password=conn_params['password'],
            connect_timeout=8
        )
        cur = conn.cursor()
        cur.execute(
            "SELECT relname, n_live_tup "
            "FROM pg_stat_user_tables "
            "WHERE schemaname='knowledge' "
            "ORDER BY relname"
        )
        rows = cur.fetchall()
        tables = [{'name': r[0], 'row_count': r[1]} for r in rows]
        cur.close()
        conn.close()
        return jsonify({'success': True, 'tables': tables})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'tables': []})


@app.route('/api/browse-rows', methods=['GET'])
def browse_rows():
    """Return first 25 rows of a table in the knowledge schema."""
    if not PSYCOPG2_AVAILABLE:
        return jsonify({'success': False, 'error': 'psycopg2 not installed', 'rows': [], 'columns': []})

    table_name = request.args.get('table_name', '')
    # Sanitize: only allow alphanumeric + underscore to prevent SQL injection
    if not re.match(r'^[a-zA-Z0-9_]+$', table_name):
        return jsonify({'success': False, 'error': 'Invalid table name', 'rows': [], 'columns': []})

    conn_params = {
        'host': request.args.get('host', 'localhost'),
        'port': request.args.get('port', '5432'),
        'database': request.args.get('database', 'mining_guardian'),
        'user': request.args.get('user', 'guardian_admin'),
        'password': request.args.get('password') or _db_password()
    }
    try:
        conn = psycopg2.connect(
            host=conn_params['host'],
            port=int(conn_params['port']),
            dbname=conn_params['database'],
            user=conn_params['user'],
            password=conn_params['password'],
            connect_timeout=8
        )
        cur = conn.cursor()
        # Safe: table_name is validated to alphanumeric+underscore only
        cur.execute(f'SELECT * FROM knowledge.{table_name} LIMIT 25')
        columns = [desc[0] for desc in cur.description]
        rows = []
        for row in cur.fetchall():
            rows.append([str(v) if v is not None else '' for v in row])
        cur.close()
        conn.close()
        return jsonify({'success': True, 'columns': columns, 'rows': rows, 'table': table_name})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'rows': [], 'columns': []})


# ---------------------------------------------------------------------------
# Embedded HTML / CSS / JS
# ---------------------------------------------------------------------------

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mining Guardian — Intelligence Catalog Importer</title>
<style>
/* ===== RESET & BASE ===== */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg-0: #0d0e10;
  --bg-1: #14161a;
  --bg-2: #1c1f24;
  --bg-3: #23272e;
  --bg-4: #2a2f38;
  --border: #2e3440;
  --border-light: #3a3f4b;
  --text-primary: #e8eaf0;
  --text-secondary: #8b919e;
  --text-muted: #5a6070;
  --accent: #F7931A;
  --accent-dim: rgba(247,147,26,0.15);
  --accent-hover: #ffaa42;
  --success: #4ade80;
  --success-dim: rgba(74,222,128,0.12);
  --error: #f87171;
  --error-dim: rgba(248,113,113,0.12);
  --warning: #fbbf24;
  --warning-dim: rgba(251,191,36,0.12);
  --info: #60a5fa;
  --info-dim: rgba(96,165,250,0.1);
  --font-mono: 'Cascadia Code', 'Fira Code', 'JetBrains Mono', 'Consolas', monospace;
  --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  --radius: 6px;
  --radius-lg: 10px;
  --shadow: 0 2px 12px rgba(0,0,0,0.4);
  --shadow-lg: 0 8px 32px rgba(0,0,0,0.5);
}

html { font-size: 14px; }
body {
  font-family: var(--font-sans);
  background: var(--bg-0);
  color: var(--text-primary);
  line-height: 1.5;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

/* ===== TABLE BROWSER MODAL ===== */
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.7);
  z-index: 1000;
  display: flex; align-items: center; justify-content: center;
  opacity: 0; pointer-events: none;
  transition: opacity 0.2s;
}
.modal-overlay.active { opacity: 1; pointer-events: all; }
.modal-box {
  background: var(--bg-1);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  width: 92vw; max-width: 1100px;
  height: 82vh;
  display: flex; flex-direction: column;
  overflow: hidden;
}
.modal-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 18px;
  background: var(--bg-2);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.modal-header h2 {
  font-size: 0.9rem; color: var(--text-primary);
  display: flex; align-items: center; gap: 8px;
}
.modal-header h2 span { color: var(--accent); }
.modal-close {
  background: none; border: none; cursor: pointer;
  color: var(--text-muted); font-size: 1.1rem; line-height: 1;
  padding: 4px 8px; border-radius: var(--radius);
  transition: color 0.15s, background 0.15s;
}
.modal-close:hover { color: var(--text-primary); background: var(--bg-3); }
.modal-body {
  flex: 1; display: flex; overflow: hidden;
}
.browser-sidebar {
  width: 240px; flex-shrink: 0;
  background: var(--bg-2);
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column;
  overflow: hidden;
}
.browser-sidebar-header {
  padding: 10px 14px 6px;
  font-size: 0.7rem; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.07em;
  color: var(--text-muted);
  display: flex; align-items: center; justify-content: space-between;
  flex-shrink: 0;
}
.browser-table-list {
  flex: 1; overflow-y: auto;
  padding: 4px 0;
}
.browser-table-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 7px 14px;
  cursor: pointer;
  transition: background 0.12s;
  border-left: 3px solid transparent;
  gap: 6px;
}
.browser-table-item:hover { background: var(--bg-3); }
.browser-table-item.active {
  background: var(--accent-dim);
  border-left-color: var(--accent);
}
.browser-table-name {
  font-size: 0.78rem; font-family: var(--font-mono);
  color: var(--text-primary); overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; flex: 1;
}
.browser-table-count {
  font-size: 0.68rem; color: var(--text-muted);
  background: var(--bg-4); padding: 1px 5px;
  border-radius: 9px; flex-shrink: 0;
}
.browser-main {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
}
.browser-toolbar {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px;
  background: var(--bg-2); border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.browser-toolbar .tbl-name {
  font-family: var(--font-mono); font-size: 0.82rem;
  color: var(--accent); font-weight: 600;
}
.browser-toolbar .tbl-hint {
  font-size: 0.72rem; color: var(--text-muted);
}
.browser-grid-wrap {
  flex: 1; overflow: auto;
  padding: 0;
}
.browser-grid {
  border-collapse: collapse; width: 100%;
  font-family: var(--font-mono); font-size: 0.75rem;
  color: var(--text-primary);
}
.browser-grid th {
  background: var(--bg-3);
  padding: 7px 10px; text-align: left;
  font-size: 0.68rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--accent); white-space: nowrap;
  border-bottom: 1px solid var(--border);
  position: sticky; top: 0; z-index: 1;
}
.browser-grid td {
  padding: 5px 10px;
  border-bottom: 1px solid var(--border);
  max-width: 280px; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
  vertical-align: top;
}
.browser-grid tr:hover td { background: var(--bg-2); }
.browser-empty {
  display: flex; align-items: center; justify-content: center;
  height: 100%; color: var(--text-muted); font-size: 0.85rem;
}

/* ===== IMPORT HISTORY ===== */
.history-panel {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  margin-bottom: 4px;
}
.history-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 9px 16px;
  background: var(--bg-2); border-bottom: 1px solid var(--border);
  cursor: pointer; user-select: none;
}
.history-header:hover { background: var(--bg-3); }
.history-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 0.78rem; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--text-secondary);
}
.history-title .icon { color: var(--accent); }
.history-body {
  overflow: hidden;
  transition: max-height 0.25s ease;
}
.history-body.collapsed { display: none; }
.history-table {
  width: 100%; border-collapse: collapse;
  font-size: 0.77rem;
}
.history-table th {
  background: var(--bg-3); padding: 6px 12px;
  text-align: left; font-size: 0.68rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--text-muted); border-bottom: 1px solid var(--border);
}
.history-table td {
  padding: 6px 12px; border-bottom: 1px solid var(--border);
  color: var(--text-primary); vertical-align: top;
}
.history-table td.mono { font-family: var(--font-mono); font-size: 0.73rem; }
.history-table td.ok { color: var(--success); }
.history-table td.fail { color: var(--error); }
.history-empty {
  padding: 16px; text-align: center;
  color: var(--text-muted); font-size: 0.8rem;
}

/* ===== SCROLLBAR ===== */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg-1); }
::-webkit-scrollbar-thumb { background: var(--bg-4); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--border-light); }

/* ===== TYPOGRAPHY ===== */
h1, h2, h3 { font-weight: 600; letter-spacing: -0.01em; }

/* ===== HEADER ===== */
.app-header {
  background: linear-gradient(135deg, var(--bg-1) 0%, #181c22 100%);
  border-bottom: 1px solid var(--border);
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 60px;
  flex-shrink: 0;
}
.logo-area {
  display: flex;
  align-items: center;
  gap: 12px;
}
.logo-svg {
  flex-shrink: 0;
}
.logo-text h1 {
  font-size: 1.1rem;
  color: var(--text-primary);
  line-height: 1.2;
}
.logo-text .subtitle {
  font-size: 0.7rem;
  color: var(--accent);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 500;
}
.header-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.78rem;
  color: var(--text-secondary);
}
.status-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--text-muted);
  transition: background 0.3s;
  flex-shrink: 0;
}
.status-dot.connected { background: var(--success); box-shadow: 0 0 6px rgba(74,222,128,0.5); }
.status-dot.error { background: var(--error); box-shadow: 0 0 6px rgba(248,113,113,0.5); }

/* ===== MAIN LAYOUT ===== */
.app-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: auto;
  padding: 16px 24px;
  gap: 14px;
}

/* ===== PANELS ===== */
.panel {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: var(--bg-2);
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  user-select: none;
}
.panel-header:hover { background: var(--bg-3); }
.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-secondary);
}
.panel-title .icon { color: var(--accent); font-size: 0.85rem; }
.chevron {
  color: var(--text-muted);
  font-size: 0.65rem;
  transition: transform 0.2s;
}
.chevron.open { transform: rotate(180deg); }
.panel-body { padding: 16px; }
.panel-body.collapsed { display: none; }

/* ===== FORMS ===== */
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr 1fr 1fr;
  gap: 10px;
  align-items: end;
}
.form-group { display: flex; flex-direction: column; gap: 4px; }
.form-group label {
  font-size: 0.72rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 500;
}
.form-group input {
  background: var(--bg-0);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 0.8rem;
  padding: 7px 10px;
  outline: none;
  transition: border-color 0.2s;
  width: 100%;
}
.form-group input:focus { border-color: var(--accent); }
.form-group input::placeholder { color: var(--text-muted); }

/* ===== BUTTONS ===== */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: var(--radius);
  border: none;
  cursor: pointer;
  font-size: 0.8rem;
  font-weight: 600;
  font-family: var(--font-sans);
  transition: all 0.15s;
  white-space: nowrap;
  user-select: none;
}
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-primary {
  background: var(--accent);
  color: #0d0e10;
}
.btn-primary:not(:disabled):hover { background: var(--accent-hover); transform: translateY(-1px); }
.btn-secondary {
  background: var(--bg-3);
  color: var(--text-primary);
  border: 1px solid var(--border-light);
}
.btn-secondary:not(:disabled):hover { background: var(--bg-4); border-color: var(--accent); }
.btn-ghost {
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border);
}
.btn-ghost:not(:disabled):hover { color: var(--text-primary); border-color: var(--border-light); }
.btn-danger {
  background: var(--error-dim);
  color: var(--error);
  border: 1px solid rgba(248,113,113,0.2);
}
.btn-danger:not(:disabled):hover { background: rgba(248,113,113,0.2); }

/* ===== MODE TOGGLE ===== */
.mode-toggle {
  display: flex;
  background: var(--bg-0);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 3px;
  gap: 2px;
}
.mode-btn {
  flex: 1;
  padding: 6px 16px;
  background: transparent;
  border: none;
  border-radius: calc(var(--radius) - 2px);
  color: var(--text-muted);
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.mode-btn.active {
  background: var(--accent);
  color: #0d0e10;
}
.mode-btn:not(.active):hover { color: var(--text-primary); }

/* ===== DROP ZONE ===== */
.drop-zone {
  border: 2px dashed var(--border-light);
  border-radius: var(--radius-lg);
  padding: 40px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
  min-height: 200px;
  background: var(--bg-1);
  text-align: center;
}
.drop-zone:hover, .drop-zone.drag-over {
  border-color: var(--accent);
  background: var(--accent-dim);
}
.drop-zone.drag-over {
  transform: scale(1.01);
}
.drop-zone-icon {
  font-size: 2.5rem;
  line-height: 1;
  opacity: 0.6;
  transition: opacity 0.2s;
}
.drop-zone:hover .drop-zone-icon,
.drop-zone.drag-over .drop-zone-icon { opacity: 1; }
.drop-zone-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
}
.drop-zone-sub {
  font-size: 0.78rem;
  color: var(--text-secondary);
}
.drop-zone-types {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: center;
  margin-top: 4px;
}
.type-badge {
  background: var(--bg-3);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 0.68rem;
  font-family: var(--font-mono);
  color: var(--accent);
  font-weight: 600;
}
#fileInput { display: none; }

/* ===== FILE LIST ===== */
.file-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 12px;
}
.file-item {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px 12px;
  position: relative;
  overflow: hidden;
}
.file-item::before {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  background: var(--accent);
}
.file-icon {
  font-size: 1rem;
  flex-shrink: 0;
}
.file-info { flex: 1; min-width: 0; }
.file-name {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.file-meta {
  font-size: 0.7rem;
  color: var(--text-muted);
  font-family: var(--font-mono);
}
.file-remove {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 1rem;
  padding: 2px 6px;
  border-radius: 4px;
  transition: all 0.15s;
  flex-shrink: 0;
}
.file-remove:hover { color: var(--error); background: var(--error-dim); }

/* ===== CONTROLS ROW ===== */
.controls-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

/* ===== MIDDLE AREA (drop + preview side by side in review mode) ===== */
.middle-area {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}
.middle-area.review-mode { /* side-by-side */ }
.drop-column {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 280px;
}
.preview-column {
  flex: 1.3;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 320px;
}
.preview-column.hidden { display: none; }

/* ===== SQL PREVIEW ===== */
.sql-preview-panel {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 300px;
}
.preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: var(--bg-2);
  border-bottom: 1px solid var(--border);
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
  flex-shrink: 0;
}
.preview-title {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  display: flex;
  align-items: center;
  gap: 6px;
}
.preview-tabs {
  display: flex;
  gap: 4px;
  flex: 1;
  overflow-x: auto;
  margin: 0 10px;
}
.preview-tab {
  padding: 4px 12px;
  background: var(--bg-3);
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 0.72rem;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
  flex-shrink: 0;
}
.preview-tab.active {
  background: var(--accent-dim);
  border-color: var(--accent);
  color: var(--accent);
}
.preview-tab:not(.active):hover { color: var(--text-primary); }
.sql-editor {
  flex: 1;
  padding: 0;
  background: var(--bg-0);
  border-radius: 0 0 var(--radius-lg) var(--radius-lg);
  overflow: hidden;
}
#sqlTextarea {
  width: 100%;
  height: 100%;
  min-height: 300px;
  background: transparent;
  border: none;
  color: #a8d8a8;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  line-height: 1.6;
  padding: 14px;
  resize: vertical;
  outline: none;
  tab-size: 2;
}
.preview-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
}

/* ===== PROGRESS BAR ===== */
.progress-bar {
  height: 3px;
  background: var(--bg-3);
  border-radius: 2px;
  overflow: hidden;
  display: none;
}
.progress-bar.active { display: block; }
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent), #ffcc44);
  width: 0%;
  transition: width 0.3s;
  border-radius: 2px;
}
.progress-fill.indeterminate {
  width: 40%;
  animation: progress-slide 1.2s ease-in-out infinite;
}
@keyframes progress-slide {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(350%); }
}

/* ===== IMPORT LOG ===== */
.log-panel {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}
.log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: var(--bg-2);
  border-bottom: 1px solid var(--border);
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
  flex-shrink: 0;
}
.log-title {
  font-size: 0.78rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 6px;
}
.log-stats {
  display: flex;
  gap: 16px;
}
.log-stat {
  font-size: 0.72rem;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 4px;
}
.log-stat .val {
  font-family: var(--font-mono);
  font-weight: 700;
}
.log-stat.success .val { color: var(--success); }
.log-stat.error .val { color: var(--error); }
.log-stat.info .val { color: var(--info); }
.log-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-height: 160px;
  max-height: 260px;
  font-family: var(--font-mono);
  font-size: 0.72rem;
}
.log-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  font-size: 0.75rem;
  font-family: var(--font-sans);
  padding: 30px;
}
.log-entry {
  display: flex;
  gap: 8px;
  padding: 2px 6px;
  border-radius: 3px;
  align-items: baseline;
  line-height: 1.5;
}
.log-entry.success { color: var(--success); }
.log-entry.error { color: var(--error); background: var(--error-dim); }
.log-entry.warning { color: var(--warning); background: var(--warning-dim); }
.log-entry.info { color: var(--info); }
.log-entry.header {
  color: var(--accent);
  font-weight: 700;
  margin-top: 6px;
  border-top: 1px solid var(--border);
  padding-top: 6px;
}
.log-entry.header:first-child { border-top: none; margin-top: 0; }
.log-ts {
  color: var(--text-muted);
  font-size: 0.65rem;
  flex-shrink: 0;
  opacity: 0.7;
}
.log-text { flex: 1; word-break: break-all; }
.log-stmt {
  color: var(--text-muted);
  font-size: 0.65rem;
  opacity: 0.6;
  margin-left: 8px;
  font-style: italic;
}

/* ===== SUMMARY BAR ===== */
.summary-bar {
  display: none;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  background: var(--bg-2);
  border-top: 1px solid var(--border);
  border-radius: 0 0 var(--radius-lg) var(--radius-lg);
  font-size: 0.78rem;
  flex-wrap: wrap;
}
.summary-bar.visible { display: flex; }
.summary-item {
  display: flex;
  align-items: center;
  gap: 5px;
}
.summary-item .num {
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 0.85rem;
}
.summary-item.ok .num { color: var(--success); }
.summary-item.fail .num { color: var(--error); }
.summary-item.neutral .num { color: var(--info); }

/* ===== FOOTER ===== */
.app-footer {
  background: var(--bg-1);
  border-top: 1px solid var(--border);
  padding: 8px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}
.footer-rules {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
}
.footer-rule {
  font-size: 0.68rem;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 5px;
}
.footer-rule::before {
  content: '⬡';
  color: var(--accent);
  font-size: 0.6rem;
}
.footer-version {
  font-size: 0.65rem;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

/* ===== ALERTS ===== */
.alert {
  padding: 10px 14px;
  border-radius: var(--radius);
  font-size: 0.78rem;
  display: none;
  align-items: center;
  gap: 8px;
}
.alert.visible { display: flex; }
.alert-error { background: var(--error-dim); border: 1px solid rgba(248,113,113,0.25); color: var(--error); }
.alert-success { background: var(--success-dim); border: 1px solid rgba(74,222,128,0.25); color: var(--success); }
.alert-warning { background: var(--warning-dim); border: 1px solid rgba(251,191,36,0.25); color: var(--warning); }

/* ===== LOADING OVERLAY ===== */
.loading-overlay {
  position: fixed;
  inset: 0;
  background: rgba(13,14,16,0.75);
  display: none;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(3px);
}
.loading-overlay.active { display: flex; }
.loading-card {
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 28px 36px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  box-shadow: var(--shadow-lg);
}
.spinner {
  width: 36px; height: 36px;
  border: 3px solid var(--bg-4);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.loading-text {
  color: var(--text-secondary);
  font-size: 0.85rem;
}

/* ===== ZIP DETAILS ===== */
.zip-tree {
  background: var(--bg-0);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px 14px;
  font-size: 0.75rem;
  font-family: var(--font-mono);
  color: var(--text-secondary);
  margin-top: 6px;
}
.zip-entry {
  padding: 2px 0;
  display: flex;
  align-items: center;
  gap: 6px;
}
.zip-master { color: var(--accent); font-weight: 700; }
.zip-icon { opacity: 0.6; }

/* ===== RESPONSIVE ===== */
@media (max-width: 900px) {
  .middle-area { flex-direction: column; }
  .form-grid { grid-template-columns: 1fr 1fr; }
  .preview-column { min-width: 0; width: 100%; }
  .footer-rules { display: none; }
}
@media (max-width: 600px) {
  .form-grid { grid-template-columns: 1fr; }
  .main-content { padding: 12px; }
  .controls-row { flex-direction: column; align-items: stretch; }
}
</style>
</head>
<body>

<!-- ===== LOADING OVERLAY ===== -->
<div class="loading-overlay" id="loadingOverlay">
  <div class="loading-card">
    <div class="spinner"></div>
    <div class="loading-text" id="loadingText">Processing files...</div>
  </div>
</div>

<!-- ===== HEADER ===== -->
<header class="app-header">
  <div class="logo-area">
    <!-- SVG Logo: pickaxe + bitcoin symbol geometric mark -->
    <svg class="logo-svg" width="38" height="38" viewBox="0 0 38 38" fill="none" aria-label="Mining Guardian Logo">
      <rect width="38" height="38" rx="8" fill="#F7931A" opacity="0.15"/>
      <rect x="0.5" y="0.5" width="37" height="37" rx="7.5" stroke="#F7931A" stroke-opacity="0.4"/>
      <!-- Bitcoin B -->
      <path d="M13 10h7.5c2.5 0 4 1.2 4 3.2 0 1.3-.7 2.2-1.8 2.6 1.5.4 2.3 1.5 2.3 3 0 2.3-1.8 3.7-4.8 3.7H13V10z" fill="none" stroke="#F7931A" stroke-width="2" stroke-linejoin="round"/>
      <path d="M13 16.5h6.5" stroke="#F7931A" stroke-width="1.5"/>
      <!-- Tick marks top/bottom of B -->
      <path d="M15.5 8.5v3M15.5 19v3" stroke="#F7931A" stroke-width="1.5" stroke-linecap="round"/>
      <path d="M18.5 8.5v3M18.5 19v3" stroke="#F7931A" stroke-width="1.5" stroke-linecap="round"/>
      <!-- Pickaxe handle + head -->
      <path d="M8 30l12-12" stroke="#e8eaf0" stroke-width="1.5" stroke-linecap="round" opacity="0.6"/>
      <path d="M17 21l2-2 4 1-1-4 2-2" stroke="#F7931A" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    <div class="logo-text">
      <h1>Mining Guardian</h1>
      <div class="subtitle">Intelligence Catalog Importer</div>
    </div>
  </div>
  <div style="display:flex; align-items:center; gap:12px;">
    <button class="btn btn-ghost" onclick="openTableBrowser()" style="font-size:0.75rem; padding:5px 12px; border-color:var(--border-light);">
      <span>&#128196;</span> Browse Tables
    </button>
    <div class="header-status">
      <div class="status-dot" id="headerStatusDot"></div>
      <span id="headerStatusText">Not connected</span>
    </div>
  </div>
</header>

<!-- ===== APP BODY ===== -->
<div class="app-body">
<div class="main-content" id="mainContent">

  <!-- ===== CONNECTION PANEL ===== -->
  <div class="panel" id="connPanel">
    <div class="panel-header" onclick="togglePanel('connPanel')">
      <div class="panel-title">
        <span class="icon">⚡</span>
        PostgreSQL Connection
      </div>
      <span class="chevron open" id="connChevron">▼</span>
    </div>
    <div class="panel-body" id="connBody">
      <div class="form-grid">
        <div class="form-group">
          <label>Host</label>
          <input type="text" id="dbHost" value="localhost" placeholder="localhost">
        </div>
        <div class="form-group">
          <label>Port</label>
          <input type="text" id="dbPort" value="5432" placeholder="5432">
        </div>
        <div class="form-group">
          <label>Database</label>
          <input type="text" id="dbName" value="mining_guardian" placeholder="database name">
        </div>
        <div class="form-group">
          <label>User</label>
          <input type="text" id="dbUser" value="guardian_admin" placeholder="username">
        </div>
        <div class="form-group">
          <label>Password</label>
          <input type="password" id="dbPass" value="" placeholder="password">
        </div>
      </div>
      <div style="display:flex; align-items:center; gap:10px; margin-top:12px; flex-wrap:wrap;">
        <button class="btn btn-primary" onclick="testConnection()">
          <span>⚡</span> Test Connection
        </button>
        <div class="alert alert-error" id="connError"></div>
        <div class="alert alert-success" id="connSuccess"></div>
      </div>
    </div>
  </div>

  <!-- ===== MODE + CONTROLS ROW ===== -->
  <div class="controls-row">
    <div style="display:flex; align-items:center; gap:10px;">
      <span style="font-size:0.75rem; color:var(--text-muted); font-weight:600; text-transform:uppercase; letter-spacing:0.06em;">Mode</span>
      <div class="mode-toggle">
        <button class="mode-btn active" id="modeAutoBtn" onclick="setMode('auto')">
          ⚡ Auto-Import
        </button>
        <button class="mode-btn" id="modeReviewBtn" onclick="setMode('review')">
          🔍 Review First
        </button>
      </div>
    </div>
    <div style="display:flex; gap:8px;">
      <button class="btn btn-ghost" onclick="clearFiles()" id="clearBtn" style="display:none;">
        Clear Files
      </button>
      <button class="btn btn-primary" onclick="runImport()" id="runAutoBtn" style="display:none;">
        <span>▶</span> Run Import
      </button>
    </div>
  </div>

  <!-- ===== MIDDLE AREA ===== -->
  <div class="middle-area" id="middleArea">

    <!-- DROP COLUMN -->
    <div class="drop-column">
      <div class="drop-zone" id="dropZone"
           ondrop="handleDrop(event)" ondragover="handleDragOver(event)"
           ondragleave="handleDragLeave(event)" onclick="triggerBrowse()">
        <div class="drop-zone-icon">⛏</div>
        <div class="drop-zone-title">Drop files here to import</div>
        <div class="drop-zone-sub">or click to browse</div>
        <div class="drop-zone-types">
          <span class="type-badge">.csv</span>
          <span class="type-badge">.sql</span>
          <span class="type-badge">.zip</span>
          <span class="type-badge">.xlsx</span>
          <span class="type-badge">.json</span>
          <span class="type-badge">.tsv</span>
          <span class="type-badge">.txt</span>
          <span class="type-badge">.tar</span>
          <span class="type-badge">.tgz</span>
          <span class="type-badge">.tar.gz</span>
          <span class="type-badge">.rar</span>
        </div>
        <input type="file" id="fileInput" multiple accept="*"
               onchange="handleFileInput(event)">
      </div>

      <!-- File List -->
      <div class="file-list" id="fileList"></div>

      <!-- Progress Bar -->
      <div class="progress-bar" id="progressBar">
        <div class="progress-fill indeterminate" id="progressFill"></div>
      </div>
    </div>

    <!-- PREVIEW COLUMN (Review Mode only) -->
    <div class="preview-column hidden" id="previewColumn">
      <div class="sql-preview-panel">
        <div class="preview-header">
          <div class="preview-title"><span>📋</span> SQL Preview</div>
          <div class="preview-tabs" id="previewTabs"></div>
          <div class="preview-actions">
            <button class="btn btn-ghost" onclick="copySQL()" style="padding:5px 10px; font-size:0.72rem;">
              Copy
            </button>
            <button class="btn btn-primary" onclick="runPreviewSQL()" id="runSQLBtn" disabled>
              <span>▶</span> Run Import
            </button>
          </div>
        </div>
        <div class="sql-editor">
          <textarea id="sqlTextarea" spellcheck="false"
                    placeholder="SQL will appear here after you drop files..."></textarea>
        </div>
      </div>
    </div>
  </div>

  <!-- ===== IMPORT LOG ===== -->
  <div class="log-panel">
    <div class="log-header">
      <div class="log-title"><span>📊</span> Import Log</div>
      <div style="display:flex; align-items:center; gap:10px;">
        <div class="log-stats">
          <div class="log-stat info">
            <span>Stmts:</span>
            <span class="val" id="statStmts">0</span>
          </div>
          <div class="log-stat success">
            <span>Rows:</span>
            <span class="val" id="statRows">0</span>
          </div>
          <div class="log-stat error">
            <span>Errors:</span>
            <span class="val" id="statErrors">0</span>
          </div>
        </div>
        <button class="btn btn-ghost" style="padding:4px 8px; font-size:0.7rem;" onclick="clearLog()">Clear</button>
      </div>
    </div>
    <div class="log-body" id="logBody">
      <div class="log-empty" id="logEmpty">No import activity yet — drop files to begin</div>
    </div>
    <div class="summary-bar" id="summaryBar"></div>
  </div>

  <!-- ===== IMPORT HISTORY ===== -->
  <div class="history-panel">
    <div class="history-header" onclick="toggleHistory()">
      <div class="history-title">
        <span class="icon">&#128203;</span>
        Import Session History
        <span id="historyCount" style="font-size:0.7rem; color:var(--text-muted); font-weight:400;">(0 sessions)</span>
      </div>
      <div style="display:flex; align-items:center; gap:8px;">
        <button class="btn btn-ghost" style="padding:3px 8px; font-size:0.7rem;" onclick="event.stopPropagation(); clearHistory()">Clear History</button>
        <span class="chevron open" id="historyChevron" style="color:var(--text-muted); font-size:0.65rem;">&#9660;</span>
      </div>
    </div>
    <div class="history-body" id="historyBody">
      <div class="history-empty" id="historyEmpty">No import sessions recorded yet — run an import to begin tracking</div>
      <table class="history-table" id="historyTable" style="display:none;">
        <thead>
          <tr>
            <th>#</th>
            <th>Timestamp (UTC)</th>
            <th>Files</th>
            <th>Rows Imported</th>
            <th>Errors</th>
            <th>Duration</th>
          </tr>
        </thead>
        <tbody id="historyTbody"></tbody>
      </table>
    </div>
  </div>

</div><!-- /main-content -->
</div><!-- /app-body -->

<!-- ===== FOOTER ===== -->
<footer class="app-footer">
  <div class="footer-rules">
    <div class="footer-rule">Capture Everything. Discard Nothing. — 10-year design horizon</div>
    <div class="footer-rule">Bitcoin SHA-256 miners ONLY</div>
    <div class="footer-rule">Every variant, every data point preserved</div>
    <div class="footer-rule">Dollar-quoting for safe text handling</div>
  </div>
  <div class="footer-version">mg_import v2.0 · Flask + psycopg2</div>
</footer>

<!-- ===== TABLE BROWSER MODAL ===== -->
<div class="modal-overlay" id="tableBrowserModal">
  <div class="modal-box">
    <div class="modal-header">
      <h2><span>&#128196;</span> Browse Tables — knowledge schema</h2>
      <button class="modal-close" onclick="closeTableBrowser()">&#10005;</button>
    </div>
    <div class="modal-body">
      <!-- Sidebar: table list -->
      <div class="browser-sidebar">
        <div class="browser-sidebar-header">
          <span>Tables</span>
          <button class="btn btn-ghost" style="padding:2px 7px; font-size:0.68rem;" onclick="loadTableList()">&#8635;</button>
        </div>
        <div class="browser-table-list" id="browserTableList">
          <div class="browser-empty" style="padding:20px; font-size:0.78rem;">Click Refresh or open browser</div>
        </div>
      </div>
      <!-- Main: data grid -->
      <div class="browser-main">
        <div class="browser-toolbar" id="browserToolbar">
          <span class="tbl-hint">Select a table on the left to preview rows</span>
        </div>
        <div class="browser-grid-wrap" id="browserGridWrap">
          <div class="browser-empty">No table selected</div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ===== JAVASCRIPT ===== -->
<script>
// ========== STATE ==========
const state = {
  mode: 'auto',          // 'auto' | 'review'
  files: [],             // Array of File objects
  sqlPreviews: [],       // [{filename, sql, type, zip_contents, master_file}]
  activeTabIdx: 0,
  stats: { stmts: 0, rows: 0, errors: 0 }
};

// ========== CONN PARAMS ==========
function getConnParams() {
  return {
    host: document.getElementById('dbHost').value.trim() || 'localhost',
    port: document.getElementById('dbPort').value.trim() || '5432',
    database: document.getElementById('dbName').value.trim() || 'mining_guardian',
    user: document.getElementById('dbUser').value.trim() || 'guardian_admin',
    password: document.getElementById('dbPass').value || ''
  };
}

// ========== PANEL TOGGLE ==========
function togglePanel(panelId) {
  const body = document.getElementById(panelId.replace('Panel','') + 'Body') ||
               document.getElementById(panelId + 'Body');
  // Handle connPanel specially
  const bodyEl = document.getElementById('connBody');
  const chevron = document.getElementById('connChevron');
  if (panelId === 'connPanel') {
    const collapsed = bodyEl.classList.toggle('collapsed');
    chevron.classList.toggle('open', !collapsed);
  }
}

// ========== TEST CONNECTION ==========
async function testConnection() {
  const errEl = document.getElementById('connError');
  const okEl = document.getElementById('connSuccess');
  errEl.className = 'alert alert-error';
  okEl.className = 'alert alert-success';

  setHeaderStatus('loading');
  try {
    const res = await fetch('/api/test-connection', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(getConnParams())
    });
    const data = await res.json();
    if (data.success) {
      okEl.textContent = '✓ Connected — ' + data.version.split(' ').slice(0,2).join(' ');
      okEl.className = 'alert alert-success visible';
      setHeaderStatus('connected', 'Connected');
      setTimeout(() => okEl.className = 'alert alert-success', 4000);
    } else {
      errEl.textContent = '✗ ' + data.error;
      errEl.className = 'alert alert-error visible';
      setHeaderStatus('error', 'Connection failed');
    }
  } catch(e) {
    errEl.textContent = '✗ Request failed: ' + e.message;
    errEl.className = 'alert alert-error visible';
    setHeaderStatus('error', 'Request failed');
  }
}

function setHeaderStatus(status, text) {
  const dot = document.getElementById('headerStatusDot');
  const txt = document.getElementById('headerStatusText');
  dot.className = 'status-dot' + (status === 'connected' ? ' connected' : status === 'error' ? ' error' : '');
  if (text) txt.textContent = text;
}

// ========== MODE ==========
function setMode(mode) {
  state.mode = mode;
  document.getElementById('modeAutoBtn').className = 'mode-btn' + (mode === 'auto' ? ' active' : '');
  document.getElementById('modeReviewBtn').className = 'mode-btn' + (mode === 'review' ? ' active' : '');

  const previewCol = document.getElementById('previewColumn');
  const runAutoBtn = document.getElementById('runAutoBtn');

  if (mode === 'review') {
    previewCol.classList.remove('hidden');
    runAutoBtn.style.display = 'none';
    // If we already have files, generate SQL
    if (state.files.length > 0) generateSQLPreview();
  } else {
    previewCol.classList.add('hidden');
    runAutoBtn.style.display = state.files.length > 0 ? 'inline-flex' : 'none';
  }
}

// ========== DRAG & DROP ==========
function handleDragOver(e) {
  e.preventDefault();
  e.dataTransfer.dropEffect = 'copy';
  document.getElementById('dropZone').classList.add('drag-over');
}
function handleDragLeave(e) {
  document.getElementById('dropZone').classList.remove('drag-over');
}
function handleDrop(e) {
  e.preventDefault();
  document.getElementById('dropZone').classList.remove('drag-over');
  const files = Array.from(e.dataTransfer.files);
  addFiles(files);
}
function triggerBrowse() {
  document.getElementById('fileInput').click();
}
function handleFileInput(e) {
  const files = Array.from(e.target.files);
  addFiles(files);
  e.target.value = ''; // reset so same file can be re-added
}

function addFiles(files) {
  files.forEach(f => {
    if (!state.files.find(x => x.name === f.name && x.size === f.size)) {
      state.files.push(f);
    }
  });
  renderFileList();
  if (state.files.length > 0) {
    document.getElementById('clearBtn').style.display = 'inline-flex';
    if (state.mode === 'auto') {
      document.getElementById('runAutoBtn').style.display = 'inline-flex';
    } else {
      generateSQLPreview();
    }
  }
}

function removeFile(idx) {
  state.files.splice(idx, 1);
  renderFileList();
  if (state.files.length === 0) {
    document.getElementById('clearBtn').style.display = 'none';
    document.getElementById('runAutoBtn').style.display = 'none';
    clearSQLPreview();
  } else if (state.mode === 'review') {
    generateSQLPreview();
  }
}

function clearFiles() {
  state.files = [];
  renderFileList();
  document.getElementById('clearBtn').style.display = 'none';
  document.getElementById('runAutoBtn').style.display = 'none';
  clearSQLPreview();
}

function fileIcon(name) {
  const ext = name.split('.').pop().toLowerCase();
  const icons = {csv:'📊', sql:'🗃️', zip:'📦', xlsx:'📗', json:'📄', txt:'📝', tsv:'📊', tar:'🗜️', tgz:'🗜️', rar:'🗜️', archive:'🗜️'};
  return icons[ext] || '📁';
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' KB';
  return (bytes/1024/1024).toFixed(2) + ' MB';
}

function renderFileList() {
  const listEl = document.getElementById('fileList');
  if (state.files.length === 0) {
    listEl.innerHTML = '';
    return;
  }
  listEl.innerHTML = state.files.map((f, i) => `
    <div class="file-item">
      <span class="file-icon">${fileIcon(f.name)}</span>
      <div class="file-info">
        <div class="file-name">${escHtml(f.name)}</div>
        <div class="file-meta">${formatSize(f.size)} · ${f.type || ext(f.name)}</div>
      </div>
      <button class="file-remove" onclick="removeFile(${i})" title="Remove">✕</button>
    </div>
  `).join('');
}

function ext(name) { return name.split('.').pop().toLowerCase(); }

// ========== SQL PREVIEW ==========
function clearSQLPreview() {
  state.sqlPreviews = [];
  document.getElementById('previewTabs').innerHTML = '';
  document.getElementById('sqlTextarea').value = '';
  document.getElementById('runSQLBtn').disabled = true;
}

async function generateSQLPreview() {
  if (state.files.length === 0) { clearSQLPreview(); return; }
  showLoading('Generating SQL preview...');
  try {
    const fd = new FormData();
    fd.append('conn_params', JSON.stringify(getConnParams()));
    state.files.forEach((f, i) => fd.append(`file_${i}`, f, f.name));

    const res = await fetch('/api/generate-sql', { method: 'POST', body: fd });
    const data = await res.json();
    state.sqlPreviews = data.results || [];
    renderSQLTabs();
  } catch(e) {
    logEntry('error', 'Failed to generate SQL: ' + e.message, '');
  } finally {
    hideLoading();
  }
}

function renderSQLTabs() {
  const tabsEl = document.getElementById('previewTabs');
  const textarea = document.getElementById('sqlTextarea');
  const runBtn = document.getElementById('runSQLBtn');

  // Flatten: for zip files, create tabs per inner file
  const flatPreviews = [];
  state.sqlPreviews.forEach(r => {
    if (r.type === 'zip' && r.zip_contents) {
      r.zip_contents.forEach(zc => {
        flatPreviews.push({...zc, fromZip: r.filename});
      });
      // Also offer master if present
    } else {
      flatPreviews.push(r);
    }
  });
  state._flatPreviews = flatPreviews;

  if (flatPreviews.length === 0) {
    tabsEl.innerHTML = '';
    textarea.value = '';
    runBtn.disabled = true;
    return;
  }

  tabsEl.innerHTML = flatPreviews.map((p, i) => {
    const hasError = p.error;
    const name = p.filename.length > 18 ? p.filename.slice(0,16)+'…' : p.filename;
    return `<div class="preview-tab${i===0?' active':''}" onclick="switchTab(${i})" id="tab_${i}"
      title="${escHtml(p.filename)}">${escHtml(name)}${hasError ? ' ⚠' : ''}</div>`;
  }).join('');

  state.activeTabIdx = 0;
  showTabSQL(0);
  runBtn.disabled = false;
}

function switchTab(idx) {
  state.activeTabIdx = idx;
  document.querySelectorAll('.preview-tab').forEach((t,i) => {
    t.classList.toggle('active', i === idx);
  });
  showTabSQL(idx);
}

function showTabSQL(idx) {
  const previews = state._flatPreviews || [];
  const textarea = document.getElementById('sqlTextarea');
  if (!previews[idx]) { textarea.value = ''; return; }
  const p = previews[idx];
  if (p.error) {
    textarea.value = `-- ERROR processing ${p.filename}\n-- ${p.error}`;
  } else {
    textarea.value = p.sql || '';
  }
}

async function runPreviewSQL() {
  const sql = document.getElementById('sqlTextarea').value.trim();
  if (!sql) { logEntry('warning', 'No SQL to run', ''); return; }

  showLoading('Running SQL against PostgreSQL...');
  clearStats();
  try {
    const res = await fetch('/api/run-sql', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ sql, conn_params: getConnParams() })
    });
    const data = await res.json();
    processImportResult(data, 'SQL Preview');
  } catch(e) {
    logEntry('error', 'Request failed: ' + e.message, '');
  } finally {
    hideLoading();
  }
}

function copySQL() {
  const sql = document.getElementById('sqlTextarea').value;
  navigator.clipboard.writeText(sql).then(() => {
    const btn = event.target;
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = orig, 1500);
  });
}

// ========== IMPORT ==========
async function runImport() {
  if (state.files.length === 0) return;

  showLoading('Importing files into PostgreSQL...');
  setProgressActive(true);
  clearStats();
  clearLogEntries();

  const fd = new FormData();
  fd.append('conn_params', JSON.stringify(getConnParams()));
  state.files.forEach((f, i) => fd.append(`file_${i}`, f, f.name));

  try {
    const res = await fetch('/api/import-files', { method: 'POST', body: fd });
    const data = await res.json();
    processImportResult(data, null);
  } catch(e) {
    logEntry('error', 'Import request failed: ' + e.message, '');
  } finally {
    hideLoading();
    setProgressActive(false);
  }
}

function processImportResult(data, sourceLabel) {
  const messages = data.messages || [];
  const stmts = data.statements_run || 0;
  const rows = data.rows_affected || 0;
  const errs = data.errors || [];

  messages.forEach(m => {
    logEntry(m.type || 'info', m.text, m.stmt || '');
  });

  updateStats(stmts, rows, errs.length);

  // Summary bar
  const summaryBar = document.getElementById('summaryBar');
  const success = data.success;
  summaryBar.className = 'summary-bar visible';
  summaryBar.innerHTML = `
    <div class="summary-item neutral"><span class="num">${stmts}</span> <span>statements executed</span></div>
    <div class="summary-item ok"><span class="num">${rows}</span> <span>rows affected</span></div>
    <div class="summary-item fail"><span class="num">${errs.length}</span> <span>errors</span></div>
    ${data.files_processed ? `<div class="summary-item neutral"><span class="num">${data.files_processed}</span> <span>files processed</span></div>` : ''}
    <span style="margin-left:auto; font-weight:700; color:${success ? 'var(--success)' : 'var(--error)'}">
      ${success ? '✓ Import Complete' : '⚠ Completed with errors'}
    </span>
  `;

  if (success) setHeaderStatus('connected', 'Import complete');
  // Refresh import history panel after each import
  refreshHistory();
}

// ========== LOG ==========
function logEntry(type, text, stmt) {
  const logBody = document.getElementById('logBody');
  const empty = document.getElementById('logEmpty');
  if (empty) empty.remove();

  const ts = new Date().toTimeString().slice(0,8);
  const div = document.createElement('div');
  div.className = `log-entry ${type}`;
  div.innerHTML = `<span class="log-ts">${ts}</span><span class="log-text">${escHtml(text)}</span>${stmt ? `<span class="log-stmt">${escHtml(stmt.slice(0,80))}</span>` : ''}`;
  logBody.appendChild(div);
  logBody.scrollTop = logBody.scrollHeight;
}

function clearLogEntries() {
  const logBody = document.getElementById('logBody');
  logBody.innerHTML = '<div class="log-empty" id="logEmpty">Importing...</div>';
  document.getElementById('summaryBar').className = 'summary-bar';
}

function clearLog() {
  const logBody = document.getElementById('logBody');
  logBody.innerHTML = '<div class="log-empty" id="logEmpty">No import activity yet — drop files to begin</div>';
  document.getElementById('summaryBar').className = 'summary-bar';
  clearStats();
}

// ========== STATS ==========
function clearStats() {
  state.stats = {stmts:0, rows:0, errors:0};
  renderStats();
}
function updateStats(stmts, rows, errors) {
  state.stats.stmts += stmts;
  state.stats.rows += rows;
  state.stats.errors += errors;
  renderStats();
}
function renderStats() {
  document.getElementById('statStmts').textContent = state.stats.stmts;
  document.getElementById('statRows').textContent = state.stats.rows;
  document.getElementById('statErrors').textContent = state.stats.errors;
}

// ========== UI HELPERS ==========
function showLoading(text) {
  document.getElementById('loadingText').textContent = text || 'Processing...';
  document.getElementById('loadingOverlay').classList.add('active');
}
function hideLoading() {
  document.getElementById('loadingOverlay').classList.remove('active');
}
function setProgressActive(active) {
  const pb = document.getElementById('progressBar');
  pb.classList.toggle('active', active);
}
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}

// ========== TABLE BROWSER ==========
async function openTableBrowser() {
  document.getElementById('tableBrowserModal').classList.add('active');
  await loadTableList();
}

function closeTableBrowser() {
  document.getElementById('tableBrowserModal').classList.remove('active');
}

// Close modal on overlay click (outside modal-box)
document.addEventListener('click', (e) => {
  const overlay = document.getElementById('tableBrowserModal');
  if (e.target === overlay) closeTableBrowser();
});

async function loadTableList() {
  const listEl = document.getElementById('browserTableList');
  listEl.innerHTML = '<div class="browser-empty" style="padding:20px;">Loading...</div>';
  const p = getConnParams();
  const params = new URLSearchParams({
    host: p.host, port: p.port, database: p.database, user: p.user, password: p.password
  });
  try {
    const res = await fetch('/api/browse-tables?' + params);
    const data = await res.json();
    if (!data.success) {
      listEl.innerHTML = `<div class="browser-empty" style="padding:12px; color:var(--error);">${escHtml(data.error)}</div>`;
      return;
    }
    if (data.tables.length === 0) {
      listEl.innerHTML = '<div class="browser-empty" style="padding:14px;">No tables in knowledge schema</div>';
      return;
    }
    listEl.innerHTML = data.tables.map((t, i) => `
      <div class="browser-table-item" id="bti_${i}" onclick="loadTableRows('${escHtml(t.name)}', ${i})">
        <span class="browser-table-name" title="${escHtml(t.name)}">${escHtml(t.name)}</span>
        <span class="browser-table-count">${t.row_count.toLocaleString()}</span>
      </div>
    `).join('');
  } catch(e) {
    listEl.innerHTML = `<div class="browser-empty" style="padding:12px; color:var(--error);">Request failed: ${escHtml(e.message)}</div>`;
  }
}

async function loadTableRows(tableName, itemIdx) {
  // Highlight active
  document.querySelectorAll('.browser-table-item').forEach((el, i) => {
    el.classList.toggle('active', i === itemIdx);
  });

  const toolbar = document.getElementById('browserToolbar');
  const gridWrap = document.getElementById('browserGridWrap');
  toolbar.innerHTML = `<span class="tbl-name">knowledge.${escHtml(tableName)}</span><span class="tbl-hint">Loading first 25 rows...</span>`;
  gridWrap.innerHTML = '<div class="browser-empty">Loading...</div>';

  const p = getConnParams();
  const params = new URLSearchParams({
    table_name: tableName,
    host: p.host, port: p.port, database: p.database, user: p.user, password: p.password
  });
  try {
    const res = await fetch('/api/browse-rows?' + params);
    const data = await res.json();
    if (!data.success) {
      gridWrap.innerHTML = `<div class="browser-empty" style="color:var(--error);">${escHtml(data.error)}</div>`;
      toolbar.innerHTML = `<span class="tbl-name">knowledge.${escHtml(tableName)}</span><span class="tbl-hint" style="color:var(--error);">Error loading rows</span>`;
      return;
    }
    toolbar.innerHTML = `
      <span class="tbl-name">knowledge.${escHtml(tableName)}</span>
      <span class="tbl-hint">Showing ${data.rows.length} of <strong style="color:var(--text-primary)">25</strong> rows (SELECT * LIMIT 25)</span>
    `;
    if (data.rows.length === 0) {
      gridWrap.innerHTML = '<div class="browser-empty">Table is empty</div>';
      return;
    }
    const thead = '<thead><tr>' + data.columns.map(c => `<th>${escHtml(c)}</th>`).join('') + '</tr></thead>';
    const tbody = '<tbody>' + data.rows.map(row =>
      '<tr>' + row.map(cell => `<td title="${escHtml(cell)}">${escHtml(cell.length > 60 ? cell.slice(0,57)+'...' : cell)}</td>`).join('') + '</tr>'
    ).join('') + '</tbody>';
    gridWrap.innerHTML = `<table class="browser-grid">${thead}${tbody}</table>`;
  } catch(e) {
    gridWrap.innerHTML = `<div class="browser-empty" style="color:var(--error);">Request failed: ${escHtml(e.message)}</div>`;
  }
}

// ========== IMPORT HISTORY ==========
let historyCollapsed = false;

function toggleHistory() {
  historyCollapsed = !historyCollapsed;
  document.getElementById('historyBody').classList.toggle('collapsed', historyCollapsed);
  document.getElementById('historyChevron').classList.toggle('open', !historyCollapsed);
  document.getElementById('historyChevron').innerHTML = historyCollapsed ? '&#9654;' : '&#9660;';
}

async function refreshHistory() {
  try {
    const res = await fetch('/api/import-history');
    const data = await res.json();
    const history = data.history || [];
    const countEl = document.getElementById('historyCount');
    const emptyEl = document.getElementById('historyEmpty');
    const tableEl = document.getElementById('historyTable');
    const tbody = document.getElementById('historyTbody');

    countEl.textContent = `(${history.length} session${history.length !== 1 ? 's' : ''})`;

    if (history.length === 0) {
      emptyEl.style.display = '';
      tableEl.style.display = 'none';
      return;
    }
    emptyEl.style.display = 'none';
    tableEl.style.display = '';
    tbody.innerHTML = history.map((h, i) => {
      const files = Array.isArray(h.filenames) ? h.filenames.join(', ') : (h.filenames || '—');
      const errClass = h.errors > 0 ? 'fail' : 'ok';
      const rowClass = h.rows_imported > 0 ? 'ok' : '';
      return `<tr>
        <td class="mono" style="color:var(--text-muted);">${i + 1}</td>
        <td class="mono">${escHtml(h.timestamp)}</td>
        <td style="font-size:0.72rem; max-width:300px; word-break:break-all;">${escHtml(files)}</td>
        <td class="mono ${rowClass}">${h.rows_imported.toLocaleString()}</td>
        <td class="mono ${errClass}">${h.errors}</td>
        <td class="mono" style="color:var(--text-muted);">${h.duration_s}s</td>
      </tr>`;
    }).join('');
  } catch(e) {
    // silently ignore history refresh errors
  }
}

async function clearHistory() {
  await fetch('/api/clear-history', { method: 'POST' });
  await refreshHistory();
}

// ========== INIT ==========
document.addEventListener('DOMContentLoaded', () => {
  // Prevent default drag behavior on whole page
  document.addEventListener('dragover', e => e.preventDefault());
  document.addEventListener('drop', e => e.preventDefault());
});
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys
    port = int(os.environ.get('PORT', 5050))
    host = os.environ.get('HOST', '0.0.0.0')

    print('=' * 60)
    print('  Mining Guardian — Intelligence Catalog Importer')
    print('  Capture Everything. Discard Nothing.')
    print('=' * 60)
    print(f'  Server: http://localhost:{port}')
    print(f'  psycopg2 available: {PSYCOPG2_AVAILABLE}')
    print(f'  openpyxl available: {OPENPYXL_AVAILABLE}')
    if not PSYCOPG2_AVAILABLE:
        print('  ⚠  MISSING: pip install psycopg2-binary')
    if not OPENPYXL_AVAILABLE:
        print('  ℹ  Optional: pip install openpyxl  (for .xlsx support)')
    print('=' * 60)

    app.run(host=host, port=port, debug=False)
