#!/usr/bin/env python3
"""
Mining Guardian — Intelligence Catalog Importer
================================================
Single-file Flask application for importing research data into PostgreSQL.
Run with: python mg_import.py
Opens at: http://localhost:5050
"""

import os
import io
import re
import csv
import json
import zipfile
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify, Response

try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 512 * 1024 * 1024  # 512 MB


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
    """Wrap a string value in $$ dollar-quoting, safely escaping any literal $$."""
    if value is None:
        return 'NULL'
    # Escape any literal $$ inside the value
    value = value.replace('$$', '$__$')
    return f'$${value}$$'


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
            password=conn_params.get('password', 'MiningGuardian2026!'),
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


def process_zip(zip_bytes: bytes) -> list:
    """
    Extract a ZIP and return list of {filename, content_bytes, type} dicts.
    Recursively handles nested zips.
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
                results.append({
                    'filename': os.path.basename(name),
                    'fullpath': name,
                    'content_bytes': data,
                    'ext': ext,
                    'is_master': name == master
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
            password=data.get('password', 'MiningGuardian2026!'),
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
    conn_params = json.loads(request.form.get('conn_params', '{}'))

    all_messages = []
    total_statements = 0
    total_rows = 0
    total_errors = []
    files_processed = 0

    def process_and_run(filename, ext, data):
        nonlocal total_statements, total_rows, files_processed
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
                process_and_run(zf_entry['filename'], zf_entry['ext'], zf_entry['content_bytes'])
        else:
            process_and_run(filename, ext, data)

    return jsonify({
        'success': len(total_errors) == 0,
        'messages': all_messages,
        'statements_run': total_statements,
        'rows_affected': total_rows,
        'errors': total_errors,
        'files_processed': files_processed
    })


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
  <div class="header-status">
    <div class="status-dot" id="headerStatusDot"></div>
    <span id="headerStatusText">Not connected</span>
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
          <input type="password" id="dbPass" value="MiningGuardian2026!" placeholder="password">
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
  <div class="footer-version">mg_import v1.0 · Flask + psycopg2</div>
</footer>

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
    password: document.getElementById('dbPass').value || 'MiningGuardian2026!'
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
  const icons = {csv:'📊', sql:'🗃️', zip:'📦', xlsx:'📗', json:'📄', txt:'📝', tsv:'📊'};
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
