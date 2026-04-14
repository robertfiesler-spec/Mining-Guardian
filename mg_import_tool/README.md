# Mining Guardian — Intelligence Catalog Importer

> *Capture Everything. Discard Nothing.*

A single-file Python web application for importing research data into PostgreSQL. Drag-and-drop CSVs, SQL scripts, ZIP bundles, JSON arrays, Excel files, and TSVs into the `knowledge` schema with auto-generated, dollar-quoted INSERT statements.

---

## Quick Start

### 1. Install dependencies

```bash
pip install flask psycopg2-binary openpyxl
```

- `flask` — web server
- `psycopg2-binary` — PostgreSQL driver (self-contained binary, no libpq needed)
- `openpyxl` — optional, only needed for `.xlsx` support

### 2. Run the tool

```bash
python mg_import.py
```

Opens at **http://localhost:5050**

To use a different port:

```bash
PORT=8080 python mg_import.py
```

---

## Requirements

- Python 3.8+
- Flask 2.x or 3.x
- psycopg2-binary 2.9+
- openpyxl (optional, for `.xlsx`)

---

## Default Database Connection

| Setting  | Default             |
|----------|---------------------|
| Host     | `localhost`         |
| Port     | `5432`              |
| Database | `mining_guardian`   |
| User     | `guardian_admin`    |
| Password | `MiningGuardian2026!` |

All connection settings are editable in the GUI — no config file needed.

---

## Supported File Types

| Extension | Handling |
|-----------|----------|
| `.csv`    | Auto-generates `CREATE TABLE` + `INSERT` statements in `knowledge.research_<name>` |
| `.tsv`    | Same as CSV but tab-delimited |
| `.txt`    | Treated as CSV (comma-delimited) |
| `.sql`    | Passed through directly to PostgreSQL |
| `.json`   | Array of objects → same treatment as CSV |
| `.xlsx`   | First sheet → same treatment as CSV (requires openpyxl) |
| `.zip`    | Extracted recursively; each `.csv`, `.sql`, `.xlsx`, `.json` inside is processed |

---

## How CSV Import Works

Given a file like `bitcoin_miners.csv`:

```
Model Name, Manufacturer, TH/s, Watts
Antminer S21 Pro, Bitmain, 234, 3510
```

The tool generates:

```sql
BEGIN;

CREATE SCHEMA IF NOT EXISTS knowledge;

CREATE TABLE IF NOT EXISTS knowledge.research_bitcoin_miners (
    id BIGSERIAL PRIMARY KEY,
    entity_label TEXT NOT NULL UNIQUE,
    manufacturer TEXT,
    th_s TEXT,
    watts TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO knowledge.research_bitcoin_miners (entity_label, manufacturer, th_s, watts)
VALUES ($$Antminer S21 Pro$$, $$Bitmain$$, $$234$$, $$3510$$)
ON CONFLICT (entity_label) DO NOTHING;

COMMIT;
```

### Key rules:
- **Table name**: `knowledge.research_<filename>` — lowercase, underscores, leading dates/numbers and trailing version suffixes stripped
- **First CSV column** becomes `entity_label TEXT NOT NULL UNIQUE`
- **All remaining columns** become `TEXT` columns in snake_case
- **Dollar-quoting** (`$$value$$`) used for all text values — safe for apostrophes, quotes, special chars
- **Literal `$$` inside cell values** replaced with `$__$` to prevent quoting conflicts
- **`ON CONFLICT (entity_label) DO NOTHING`** — re-importing the same file is idempotent
- Wrapped in `BEGIN`/`COMMIT`

---

## Modes

### Auto-Import Mode
Drop files → SQL is generated and immediately run against PostgreSQL. The Import Log shows real-time results.

### Review First Mode
Drop files → SQL is generated and shown in the preview editor. Review/edit the SQL, then click **Run Import** to execute.

---

## ZIP File Handling

When a `.zip` is dropped:
- All `.csv`, `.sql`, `.xlsx`, `.json` files inside are extracted and processed individually
- Nested ZIPs are handled recursively
- If the ZIP contains `run_master.sql` or `run_all.sql`, it is identified as the master script in the Review panel

---

## Import Log

The bottom log panel shows:
- **Green** — successful INSERT, CREATE TABLE, COMMIT
- **Red** — errors (logged individually, import continues for remaining rows)
- **Orange** — file headers / section breaks
- **Blue** — informational messages

Summary bar at the end shows: statements run · rows affected · error count · files processed.

---

## Error Handling

| Situation | Behavior |
|-----------|----------|
| PostgreSQL unreachable | Clear error message with connection details |
| CSV encoding issues | Tries UTF-8-sig → UTF-8 → Latin-1 → CP1252 |
| Single INSERT fails | Logs error, continues with remaining rows |
| Unsupported file type | Logs warning, skips file |
| Malformed JSON | Logs error with detail |
| openpyxl missing | Error shown when .xlsx is dropped |

---

## Architecture

```
mg_import.py              ← Single Python file (~2000 lines)
├── Flask routes
│   ├── GET  /                     → serves embedded HTML page
│   ├── POST /api/test-connection  → test PostgreSQL connectivity
│   ├── POST /api/generate-sql     → generate SQL from uploaded files (no DB write)
│   ├── POST /api/run-sql          → execute SQL string against PostgreSQL
│   └── POST /api/import-files     → generate + immediately execute (auto-import)
├── Python helpers
│   ├── sanitize_identifier()      → filename → snake_case table name
│   ├── header_to_column()         → CSV header → snake_case column name
│   ├── dollar_quote()             → wrap value in $$ quoting
│   ├── read_csv_bytes()           → multi-encoding CSV reader
│   ├── read_xlsx_bytes()          → XLSX → headers + rows
│   ├── generate_csv_sql()         → full Bobby-rules SQL generation
│   ├── execute_sql_block()        → run SQL against PostgreSQL with per-stmt error handling
│   ├── split_sql_statements()     → dollar-quote-aware SQL splitter
│   └── process_zip()              → extract + classify ZIP contents
└── HTML_PAGE string
    ├── CSS (dark theme, #F7931A accent)
    ├── HTML layout (header, panels, drop zone, log)
    └── JavaScript (drag-drop, API calls, log rendering, tab switching)
```

No external CDN dependencies. Runs fully offline/air-gapped after `pip install`.

---

## Bobby's Rules

- **Capture Everything. Discard Nothing.** — 10-year design horizon
- **Bitcoin SHA-256 miners ONLY**
- **Every variant, every data point preserved**
- **Dollar-quoting for safe text handling**

---

## Troubleshooting

**"Connection refused"**
- Ensure PostgreSQL is running: `pg_lscluster` or `systemctl status postgresql`
- Check host/port match your PostgreSQL configuration (`pg_hba.conf`, `postgresql.conf`)

**"role does not exist"**
- Create the user: `CREATE USER guardian_admin WITH PASSWORD 'MiningGuardian2026!';`
- Grant access: `GRANT ALL PRIVILEGES ON DATABASE mining_guardian TO guardian_admin;`

**"psycopg2 not installed"**
- Run: `pip install psycopg2-binary`
- On some systems: `pip3 install psycopg2-binary`

**"openpyxl not installed"**
- Run: `pip install openpyxl` (only needed for .xlsx files)

**Port already in use**
- `PORT=5051 python mg_import.py`

**Large files (>512 MB)**
- Edit `app.config['MAX_CONTENT_LENGTH']` in `mg_import.py`

---

## License

Internal tool — Mining Guardian Intelligence Platform.
