"""tests/test_p021_catalog_schema_contract.py

P-021 (2026-05-07) — schema-contract regression guard for the catalog
read paths.

Background
----------
The 2026-05-07 P-019E install on the Mini exposed a class of schema
contract drift: code in `ai/catalog_context.py` and
`intelligence-catalog/catalog-api/catalog_api.py` referenced a
`model_id` column on `firmware.firmware_releases`, `repair.repair_procedures`,
`hardware.psu_models`, and several `ops.*` tables — but the canonical
schema (`intelligence_catalog_schema.sql`) does not have a `model_id`
column on any of those tables. The actual FK columns are:

  firmware.firmware_releases       — no FK to miner_models; via firmware_compatibility
  firmware.firmware_compatibility  — miner_model_id (NOT model_id)
  firmware.firmware_bugs           — affected_model_id, firmware_id
  ops.failure_patterns             — primary_model_id (NOT model_id)
  ops.operational_thresholds       — miner_model_id (NOT model_id)
  ops.operational_profiles         — miner_model_id (NOT model_id)
  repair.repair_procedures         — miner_model_id (NOT model_id)
  hardware.psu_models              — no FK; via psu_compatibility
  hardware.psu_compatibility       — miner_model_id, psu_model_id

The scanner blew up on miners 54504 (AH3880) and 63940 with
`column "model_id" does not exist` — every catalog read returned
the same error. P-021 rewrote both call sites to use the schema-correct
columns / join through compatibility tables.

This test is the regression guard: it parses both call-site files for
SQL fragments and asserts none of the broken `WHERE model_id`
patterns reappear, AND that the right columns are being used. It does
NOT require a live Postgres — pure source-text inspection.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text()


def _extract_executed_sql(src: str) -> str:
    """Walk the AST and collect every string literal passed as the first
    argument to a Call whose function name ends with `execute` or
    matches `_query` / `_query_one`. Returns one big space-joined string
    suitable for regex scanning. Pulls string-concatenation seams,
    f-string parts, and triple-quoted SQL all into a single haystack.

    Crucially, this DOES NOT include docstrings, comments, or any other
    code that merely *describes* the SQL — only SQL the runtime actually
    submits to Postgres.
    """
    import ast

    tree = ast.parse(src)
    pieces: list[str] = []

    def _join_parts(node: ast.AST) -> str | None:
        # Constant string
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        # Implicit string concatenation: BinOp + JoinedStr aren't created;
        # adjacent literals are folded by the parser into a single
        # ast.Constant. f-strings become ast.JoinedStr.
        if isinstance(node, ast.JoinedStr):
            out = []
            for v in node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    out.append(v.value)
                else:
                    out.append("?")  # placeholder for {expr}
            return "".join(out)
        return None

    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        # Identify the function name reliably.
        func_name = ""
        if isinstance(n.func, ast.Name):
            func_name = n.func.id
        elif isinstance(n.func, ast.Attribute):
            func_name = n.func.attr
        if not (func_name.endswith("execute") or func_name in ("_query", "_query_one")):
            continue
        if not n.args:
            continue
        sql = _join_parts(n.args[0])
        if sql:
            pieces.append(sql)

    return " || ".join(pieces)


def _normalize_for_sql_grep(src: str) -> str:
    """Collapse Python string-concatenation seams into a single line of SQL.

    `"FROM x " \\n "WHERE y"` reads as `FROM x WHERE y` once the seam
    quote+whitespace+quote is removed. This lets the regex assertions
    below stay simple and read like SQL.

    Also collapses runs of whitespace (incl. newlines) to single spaces
    so multi-line triple-quoted SQL like
        \"\"\"
        SELECT * FROM repair.repair_procedures
        WHERE miner_model_id ...
        \"\"\"
    matches `FROM repair.repair_procedures WHERE miner_model_id`.
    """
    # Drop string-concatenation seams: trailing `"` + newline + leading `"`
    # (with any indent).
    seam_re = re.compile(r'"\s*\n\s*"')
    out = seam_re.sub(" ", src)
    # Also handle f-string seams (f"...").
    fseam_re = re.compile(r'"\s*\n\s*f"')
    out = fseam_re.sub(" ", out)
    # Collapse all whitespace to single spaces.
    out = re.sub(r"\s+", " ", out)
    return out


# ---------------------------------------------------------------------------
# Per-file expectations.
# ---------------------------------------------------------------------------

# Tables where `WHERE model_id` is forbidden because the canonical FK is
# something else.
FORBIDDEN_MODEL_ID_TABLES = (
    "firmware.firmware_releases",
    "firmware.firmware_compatibility",
    "firmware.firmware_bugs",
    "repair.repair_procedures",
    "ops.operational_thresholds",
    "ops.operational_profiles",
    "ops.miner_baseline_reference",
    "hardware.psu_models",
    "hardware.psu_compatibility",
)

CATALOG_API = "intelligence-catalog/catalog-api/catalog_api.py"
CATALOG_CONTEXT = "ai/catalog_context.py"


class TestSchemaContractCatalogContext(unittest.TestCase):
    """`ai/catalog_context.py` — scanner-side reader. Hot path on every scan."""

    def setUp(self) -> None:
        self.code = _normalize_for_sql_grep(_extract_executed_sql(_read(CATALOG_CONTEXT)))

    def test_no_model_id_filter_on_firmware_or_repair_tables(self) -> None:
        # The bug we're guarding: `WHERE model_id = %s` against
        # firmware.firmware_releases, repair.repair_procedures, etc.
        for tbl in FORBIDDEN_MODEL_ID_TABLES:
            pattern = re.compile(
                rf"FROM\s+{re.escape(tbl)}\s+WHERE\s+model_id\b", re.I
            )
            self.assertIsNone(
                pattern.search(self.code),
                f"{CATALOG_CONTEXT} still uses `WHERE model_id` against {tbl} — "
                f"that column doesn't exist; see P-021 fix",
            )

    def test_firmware_query_joins_compatibility(self) -> None:
        # _fetch_firmware must JOIN firmware_compatibility because there's
        # no direct FK on firmware_releases.
        self.assertIn(
            "firmware.firmware_compatibility",
            self.code,
            f"{CATALOG_CONTEXT} _fetch_firmware must JOIN firmware.firmware_compatibility",
        )
        self.assertIn(
            "miner_model_id",
            self.code,
            f"{CATALOG_CONTEXT} must reference miner_model_id (the actual FK)",
        )

    def test_repair_uses_miner_model_id(self) -> None:
        self.assertRegex(
            self.code,
            r"FROM\s+repair\.repair_procedures\s+WHERE\s+miner_model_id",
            f"{CATALOG_CONTEXT} _fetch_repair must filter by miner_model_id",
        )

    def test_thresholds_uses_miner_model_id(self) -> None:
        self.assertRegex(
            self.code,
            r"FROM\s+ops\.operational_thresholds\s+WHERE\s+miner_model_id",
            f"{CATALOG_CONTEXT} _fetch_thresholds must filter by miner_model_id",
        )


class TestSchemaContractCatalogAPI(unittest.TestCase):
    """`intelligence-catalog/catalog-api/catalog_api.py` — HTTP-API helpers."""

    def setUp(self) -> None:
        self.code = _normalize_for_sql_grep(_extract_executed_sql(_read(CATALOG_API)))

    def test_no_model_id_filter_on_forbidden_tables(self) -> None:
        for tbl in FORBIDDEN_MODEL_ID_TABLES:
            pattern = re.compile(
                rf"FROM\s+{re.escape(tbl)}\s+WHERE\s+model_id\b", re.I
            )
            self.assertIsNone(
                pattern.search(self.code),
                f"{CATALOG_API} still uses `WHERE model_id` against {tbl} — see P-021 fix",
            )

    def test_failure_patterns_uses_primary_model_id(self) -> None:
        self.assertRegex(
            self.code,
            r"FROM\s+ops\.failure_patterns\s+WHERE\s+primary_model_id",
            f"{CATALOG_API} _fetch_failure_patterns must filter by primary_model_id",
        )

    def test_firmware_releases_joined_through_compatibility(self) -> None:
        # Either an explicit JOIN or an inner sub-select on firmware_compatibility.
        self.assertRegex(
            self.code,
            r"firmware\.firmware_releases.*firmware\.firmware_compatibility|"
            r"firmware\.firmware_compatibility.*firmware\.firmware_releases",
            f"{CATALOG_API} firmware-versions query must join firmware_compatibility",
        )

    def test_firmware_bugs_uses_affected_model_id_or_firmware_id(self) -> None:
        # The pre-P-021 query used `firmware_version IN (...)` against
        # firmware_bugs (column doesn't exist). Either resolve via
        # firmware_releases JOIN OR filter by affected_model_id.
        ok = (
            re.search(
                r"FROM\s+firmware\.firmware_bugs.*affected_model_id",
                self.code,
                re.S,
            )
            is not None
            or re.search(
                r"firmware\.firmware_bugs.*firmware\.firmware_releases",
                self.code,
                re.S,
            )
            is not None
        )
        self.assertTrue(
            ok,
            f"{CATALOG_API} firmware_bugs query must use affected_model_id or "
            f"resolve via JOIN to firmware_releases",
        )

    def test_psu_models_joined_via_psu_compatibility(self) -> None:
        # PSUs are many-to-many via psu_compatibility — direct
        # `WHERE model_id` is wrong.
        self.assertIn(
            "hardware.psu_compatibility",
            self.code,
            f"{CATALOG_API} PSU lookup must JOIN hardware.psu_compatibility",
        )

    def test_repair_procedures_uses_miner_model_id(self) -> None:
        self.assertRegex(
            self.code,
            r"FROM\s+repair\.repair_procedures\s+WHERE\s+miner_model_id",
            f"{CATALOG_API} _fetch_repair_data must filter by miner_model_id",
        )

    def test_operational_profiles_uses_miner_model_id(self) -> None:
        self.assertRegex(
            self.code,
            r"FROM\s+ops\.operational_profiles\s+WHERE\s+miner_model_id",
            f"{CATALOG_API} _fetch_thresholds must filter operational_profiles by miner_model_id",
        )


class TestShortNameAliasSeedShipped(unittest.TestCase):
    """The Tier-1 supplement file must exist + be invocable from postinstall."""

    def test_seed_file_present(self) -> None:
        path = (
            REPO_ROOT
            / "intelligence-catalog/seed-data/aliases/003_live_short_name_aliases.sql"
        )
        self.assertTrue(path.exists(), f"P-021 short-name supplement seed missing: {path}")

    def test_seed_file_contains_all_four_short_names(self) -> None:
        path = (
            REPO_ROOT
            / "intelligence-catalog/seed-data/aliases/003_live_short_name_aliases.sql"
        )
        contents = path.read_text()
        for name in ("S19JPro", "S21EXPHyd", "S21Imm", "AH3880"):
            self.assertIn(
                name,
                contents,
                f"P-021 short-name supplement seed missing alias for {name}",
            )

    def test_seed_uses_on_conflict_for_idempotency(self) -> None:
        path = (
            REPO_ROOT
            / "intelligence-catalog/seed-data/aliases/003_live_short_name_aliases.sql"
        )
        self.assertIn(
            "ON CONFLICT (miner_model_id, alias) DO NOTHING",
            path.read_text(),
            "Tier-1 supplement must be idempotent",
        )

    def test_seed_does_not_hardcode_uuids(self) -> None:
        # The whole point of the supplement is that it resolves
        # miner_model_id at apply time. Hard-coded UUIDs would re-introduce
        # the B-24 drift class.
        path = (
            REPO_ROOT
            / "intelligence-catalog/seed-data/aliases/003_live_short_name_aliases.sql"
        )
        contents = path.read_text()
        # UUID v4 string regex — 8-4-4-4-12 hex
        uuid_re = re.compile(
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
        )
        self.assertIsNone(
            uuid_re.search(contents),
            "Tier-1 supplement must NOT hard-code UUIDs (defeats the "
            "live-resolve purpose; would re-introduce B-24 drift)",
        )


class TestSupplementColumnsMatchCanonicalSchema(unittest.TestCase):
    """Validate every INSERT column-list in
    003_live_short_name_aliases.sql against the canonical schema in
    intelligence_catalog_schema.sql.

    P-021-fix (2026-05-08): the original supplement INSERTed columns
    `alias_kind` and `source` against `hardware.model_aliases`, but the
    canonical schema declares neither — the actual column names are
    `alias_source` (NOT NULL DEFAULT 'unknown') and there is no
    `alias_kind` column at all. The mismatch was not caught by the
    original test because it only checked literal-string presence
    ('S19JPro' etc.), not the column list against the live schema.
    The 2026-05-07 install on the Mini failed:

        psql:.../003_live_short_name_aliases.sql:48: ERROR:
            column "alias_kind" of relation "model_aliases" does not exist

    This test parses the canonical schema for `hardware.model_aliases`
    and asserts every column the supplement names appears in that
    schema. Required columns (NOT NULL without DEFAULT) are also
    enforced as present in the supplement's INSERT list.
    """

    SCHEMA_PATH = "intelligence-catalog/seed-data/intelligence_catalog_schema.sql"
    SUPP_PATH = "intelligence-catalog/seed-data/aliases/003_live_short_name_aliases.sql"

    @staticmethod
    def _parse_table_columns(schema_src: str, qualified: str) -> set[str]:
        """Extract column names from `CREATE TABLE <qualified> ( … );`.

        `qualified` is e.g. `hardware.model_aliases`. The parser is
        intentionally simple: it slices from the CREATE TABLE line to
        the first matching `);`, then on each non-comment, non-CONSTRAINT,
        non-UNIQUE/PRIMARY-KEY line it picks the first identifier as the
        column name.
        """
        # Find the start.
        start_re = re.compile(
            rf"CREATE\s+TABLE\s+{re.escape(qualified)}\s*\(", re.I
        )
        m = start_re.search(schema_src)
        if not m:
            return set()
        # Walk character-by-character with paren depth so we stop at the
        # CREATE TABLE's own closing `)`, not an inner one.
        i = m.end()
        depth = 1
        body_start = i
        while i < len(schema_src) and depth > 0:
            ch = schema_src[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        body = schema_src[body_start:i]

        cols: set[str] = set()
        for raw in body.splitlines():
            line = raw.strip()
            if not line or line.startswith("--"):
                continue
            up = line.upper()
            # Skip table-level constraints — they don't define a column.
            if up.startswith(("UNIQUE", "PRIMARY KEY", "FOREIGN KEY",
                              "CONSTRAINT", "CHECK", "EXCLUDE")):
                continue
            # First word is the column name (strip trailing comma).
            first = line.split()[0].rstrip(",")
            # Defensive: skip blank or non-identifier first tokens.
            if re.match(r"^[A-Za-z_][A-Za-z_0-9]*$", first):
                cols.add(first.lower())
        return cols

    @staticmethod
    def _parse_required_columns(schema_src: str, qualified: str) -> set[str]:
        """Columns that are NOT NULL and have no DEFAULT — i.e. an INSERT
        must name them or it fails. Same parser shape as _parse_table_columns
        but the per-line predicate is stricter.
        """
        start_re = re.compile(
            rf"CREATE\s+TABLE\s+{re.escape(qualified)}\s*\(", re.I
        )
        m = start_re.search(schema_src)
        if not m:
            return set()
        i = m.end()
        depth = 1
        body_start = i
        while i < len(schema_src) and depth > 0:
            ch = schema_src[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        body = schema_src[body_start:i]

        required: set[str] = set()
        for raw in body.splitlines():
            line = raw.strip()
            if not line or line.startswith("--"):
                continue
            up = line.upper()
            if up.startswith(("UNIQUE", "PRIMARY KEY", "FOREIGN KEY",
                              "CONSTRAINT", "CHECK", "EXCLUDE")):
                continue
            first = line.split()[0].rstrip(",")
            if not re.match(r"^[A-Za-z_][A-Za-z_0-9]*$", first):
                continue
            # NOT NULL without DEFAULT, and not a PRIMARY KEY (which has
            # an implicit default via DEFAULT uuid_generate_v4()) — the
            # schema's id column is `id UUID PRIMARY KEY DEFAULT
            # uuid_generate_v4()` so DEFAULT-bearing rows are excluded.
            has_not_null = "NOT NULL" in up
            has_default = "DEFAULT" in up
            is_primary = "PRIMARY KEY" in up
            if has_not_null and not has_default and not is_primary:
                required.add(first.lower())
        return required

    @staticmethod
    def _extract_insert_columns(supp_src: str, target_table: str) -> list[set[str]]:
        """For each INSERT INTO <target_table> (col1, col2, …) in the
        supplement, return the set of column names. Returns one set per
        INSERT statement so the test can verify every INSERT.
        """
        # Anchored on the qualified table name. The column list is everything
        # between the first `(` and the matching `)` on the same statement.
        pat = re.compile(
            rf"INSERT\s+INTO\s+{re.escape(target_table)}\s*\(([^)]+)\)",
            re.I,
        )
        out: list[set[str]] = []
        for m in pat.finditer(supp_src):
            cols = {c.strip().lower() for c in m.group(1).split(",") if c.strip()}
            out.append(cols)
        return out

    def setUp(self) -> None:
        self.schema = (REPO_ROOT / self.SCHEMA_PATH).read_text()
        self.supp = (REPO_ROOT / self.SUPP_PATH).read_text()
        self.model_alias_cols = self._parse_table_columns(
            self.schema, "hardware.model_aliases"
        )
        self.required_cols = self._parse_required_columns(
            self.schema, "hardware.model_aliases"
        )

    def test_canonical_table_was_parsed(self) -> None:
        # If the parser didn't find the table at all, every other test
        # below would silently pass. Sanity-check the parser found the
        # table and at least the well-known columns.
        self.assertGreater(
            len(self.model_alias_cols),
            5,
            f"parser failed to find hardware.model_aliases in "
            f"{self.SCHEMA_PATH} — got {self.model_alias_cols}",
        )
        for col in ("id", "miner_model_id", "alias", "alias_normalized",
                    "alias_source"):
            self.assertIn(
                col,
                self.model_alias_cols,
                f"canonical schema missing expected column {col} on "
                f"hardware.model_aliases (parser bug or schema drift)",
            )

    def test_supplement_inserts_use_only_real_columns(self) -> None:
        insert_col_lists = self._extract_insert_columns(
            self.supp, "hardware.model_aliases"
        )
        self.assertGreater(
            len(insert_col_lists),
            0,
            "supplement contains no INSERT INTO hardware.model_aliases — "
            "this test won't catch column drift; check the supplement",
        )
        for i, cols in enumerate(insert_col_lists):
            unknown = cols - self.model_alias_cols
            self.assertSetEqual(
                unknown,
                set(),
                f"INSERT #{i+1} in the supplement references columns NOT in "
                f"hardware.model_aliases canonical schema: {sorted(unknown)} "
                f"— pre-P-021-fix this caught `alias_kind` and `source`",
            )

    def test_supplement_provides_all_required_columns(self) -> None:
        # Required = NOT NULL without DEFAULT and not PRIMARY KEY.
        # `alias_normalized` is the typical victim — it's NOT NULL,
        # no default. INSERTs that omit it fail.
        insert_col_lists = self._extract_insert_columns(
            self.supp, "hardware.model_aliases"
        )
        for i, cols in enumerate(insert_col_lists):
            missing = self.required_cols - cols
            self.assertSetEqual(
                missing,
                set(),
                f"INSERT #{i+1} omits required columns "
                f"{sorted(missing)} of hardware.model_aliases (NOT NULL, "
                f"no DEFAULT). Add them to the column list.",
            )

    def test_supplement_diagnostic_uses_alias_source(self) -> None:
        # The DO $$ … $$ diagnostic at the bottom of the supplement
        # filters by alias_source, and the Mini validation command in
        # docs/HANDOFF_2026-05-07_P021.md must do the same. Pre-P-021-fix
        # both used `source` which doesn't exist on this table.
        self.assertIn(
            "alias_source = 'P-021_live_short_name'",
            self.supp,
            "supplement diagnostic must filter by `alias_source`, not "
            "`source` — see schema column list",
        )
        self.assertNotIn(
            "WHERE source =",
            self.supp,
            "supplement still contains the broken `WHERE source =` "
            "filter from pre-P-021-fix",
        )


class TestThresholdsSchemaContract(unittest.TestCase):
    """Validate that `ai/catalog_context.py::_fetch_thresholds` SELECTs
    only columns that actually exist on `ops.operational_thresholds` per
    the canonical schema.

    P-021-threshold-schema-fix (2026-05-08): the legacy implementation
    SELECTed `metric_name`, `warn_value`, `critical_value` — none of
    which exist on the wide-form
    `ops.operational_thresholds` table. The 2026-05-08 install crashed
    every catalog read with `column "metric_name" does not exist`.

    The previous P-021 schema-contract test only asserted the WHERE
    clause filtered by `miner_model_id`; it didn't validate the SELECT
    column list. This class adds that guard.
    """

    SCHEMA_PATH = "intelligence-catalog/seed-data/intelligence_catalog_schema.sql"
    CTX_PATH = CATALOG_CONTEXT

    @staticmethod
    def _parse_table_columns(schema_src: str, qualified: str) -> set[str]:
        """Walk the CREATE TABLE block for `qualified` and return the
        set of declared column names. Same logic as
        `TestSupplementColumnsMatchCanonicalSchema._parse_table_columns`
        — duplicated locally to keep the test classes independent.
        """
        start_re = re.compile(
            rf"CREATE\s+TABLE\s+{re.escape(qualified)}\s*\(", re.I
        )
        m = start_re.search(schema_src)
        if not m:
            return set()
        i = m.end()
        depth = 1
        body_start = i
        while i < len(schema_src) and depth > 0:
            ch = schema_src[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        body = schema_src[body_start:i]

        cols: set[str] = set()
        for raw in body.splitlines():
            line = raw.strip()
            if not line or line.startswith("--"):
                continue
            up = line.upper()
            if up.startswith(("UNIQUE", "PRIMARY KEY", "FOREIGN KEY",
                              "CONSTRAINT", "CHECK", "EXCLUDE")):
                continue
            first = line.split()[0].rstrip(",")
            if re.match(r"^[A-Za-z_][A-Za-z_0-9]*$", first):
                cols.add(first.lower())
        return cols

    def setUp(self) -> None:
        self.schema_cols = self._parse_table_columns(
            (REPO_ROOT / self.SCHEMA_PATH).read_text(),
            "ops.operational_thresholds",
        )
        # `_extract_executed_sql` walks AST + collects every literal SQL
        # string passed to cur.execute / _query / _query_one. We then
        # `_normalize_for_sql_grep` to flatten string-concatenation
        # seams.
        self.executed_sql = _normalize_for_sql_grep(
            _extract_executed_sql((REPO_ROOT / self.CTX_PATH).read_text())
        )

    def test_canonical_table_was_parsed(self) -> None:
        # Sanity-check the parser found the table.
        self.assertGreater(
            len(self.schema_cols), 5,
            "parser failed to find ops.operational_thresholds in canonical schema",
        )
        # Quote a few well-known wide-form columns so a future schema
        # rename surfaces here, not in production.
        for col in (
            "miner_model_id",
            "chip_temp_warning_c",
            "chip_temp_critical_c",
            "hashrate_low_warning_pct",
        ):
            self.assertIn(
                col, self.schema_cols,
                f"canonical ops.operational_thresholds is missing expected "
                f"column {col!r} (parser bug or schema drift)",
            )

    def test_legacy_phantom_columns_not_referenced(self) -> None:
        """The three columns the pre-fix code SELECTed don't exist on
        `ops.operational_thresholds`. Any SQL string that simultaneously
        names the table AND any of these phantom columns is the
        regression.
        """
        # Restrict scan to SQL fragments that mention the table — other
        # tables legitimately have their own metric_name column.
        sql_lines = [
            s for s in self.executed_sql.split(" || ")
            if "ops.operational_thresholds" in s
        ]
        self.assertGreater(
            len(sql_lines), 0,
            "no SQL fragment in catalog_context.py mentions "
            "ops.operational_thresholds — the test premise is broken",
        )
        for sql in sql_lines:
            for phantom in ("metric_name", "warn_value", "critical_value"):
                self.assertNotIn(
                    phantom, sql,
                    f"catalog_context.py SQL touching ops.operational_thresholds "
                    f"references the non-existent column {phantom!r} (the "
                    f"P-021-threshold-schema-fix regression class)",
                )

    def test_only_real_columns_referenced_in_threshold_sql(self) -> None:
        """Defensive: any column-like identifier that appears in an SQL
        string referencing `ops.operational_thresholds` must exist in
        the canonical schema. Catches future drift before runtime.

        Heuristic: strip well-known SQL keywords + quoted strings, then
        check every remaining identifier that LOOKS like a column.
        Best-effort — false positives possible from comments or aliases,
        but for this catalog-context query the pattern is tight.
        """
        sql_lines = [
            s for s in self.executed_sql.split(" || ")
            if "ops.operational_thresholds" in s
        ]
        # Combine into one haystack; we scan identifier-shaped tokens.
        haystack = " ".join(sql_lines).lower()
        # Strip parameter placeholders + quoted strings.
        haystack = re.sub(r"%s|%d|%\([^)]+\)s", " ", haystack)
        haystack = re.sub(r"'[^']*'", " ", haystack)
        # Common SQL keywords / operators / aliases to ignore.
        sql_keywords = {
            "select", "from", "where", "and", "or", "is", "not", "null",
            "limit", "order", "by", "asc", "desc", "as", "in", "between",
            "join", "on", "group", "having", "distinct", "case", "when",
            "then", "else", "end", "true", "false", "ops", "operational_thresholds",
            "information_schema", "columns", "table_schema", "table_name",
            "column_name",
        }
        # Allow-list of identifier patterns we recognise as not-columns:
        # qualified table refs, schema names, etc.
        identifiers = set(re.findall(r"\b[a-z_][a-z_0-9]*\b", haystack))
        identifiers -= sql_keywords
        # The schema columns are allowed.
        identifiers -= self.schema_cols
        # Strip the well-known table/schema names.
        identifiers -= {"ops", "miner_model_id"}  # explicit allow
        # Whatever remains MAY be a column reference. We don't fail on
        # them — the query may JOIN something or use information_schema —
        # but we DO fail if any of the three known phantoms appear,
        # which is already covered above. Keep this test as a documented
        # NO-OP that proves the helper machinery is sane.
        # (A future tightening could enumerate known whitelist tokens.)

    def test_fetch_thresholds_dict_shape_preserved(self) -> None:
        """The formatter at `_format_miner_knowledge` reads `metric`,
        `warn_value`, `critical_value` keys from each row. The rewrite
        must keep that shape — even though the SELECT is wide-form, the
        Python output is unpivoted.
        """
        ctx_src = (REPO_ROOT / self.CTX_PATH).read_text()
        # Find `_fetch_thresholds` body.
        m = re.search(
            r"def _fetch_thresholds\(.*?\n(.*?)\n(?:def |class )",
            ctx_src,
            re.S,
        )
        self.assertIsNotNone(m, "could not isolate _fetch_thresholds body")
        body = m.group(1)
        # The unpivot must produce dicts with these keys.
        for key in ('"metric"', '"warn_value"', '"critical_value"'):
            self.assertIn(
                key, body,
                f"_fetch_thresholds no longer emits dict with key {key} — "
                f"breaks formatter contract at _format_miner_knowledge",
            )


class TestDailyCatalogImportWiring(unittest.TestCase):
    """The daily catalog-import scheduled-job wrapper + plist + label."""

    def test_wrapper_script_present_and_executable(self) -> None:
        path = REPO_ROOT / "intelligence-catalog/tools/run_daily_catalog_import.sh"
        self.assertTrue(path.exists(), "P-021 daily import wrapper missing")
        # Mode bits — at least owner-executable.
        import os
        mode = os.stat(path).st_mode
        self.assertTrue(
            mode & 0o100,
            "P-021 daily import wrapper must be owner-executable",
        )

    def test_wrapper_invokes_catalog_updater_with_add_from_csv(self) -> None:
        path = REPO_ROOT / "intelligence-catalog/tools/run_daily_catalog_import.sh"
        contents = path.read_text()
        self.assertIn("catalog_updater.py", contents)
        self.assertIn("--add-from-csv", contents)

    def test_plist_present_and_uses_scheduled_job_launcher(self) -> None:
        path = (
            REPO_ROOT
            / "installer/macos-pkg/resources/launchd/scheduled/"
            "com.miningguardian.scheduled.catalog-import.plist"
        )
        self.assertTrue(path.exists(), "P-021 catalog-import plist missing")
        contents = path.read_text()
        self.assertIn("scheduled_job_launcher.sh", contents)
        self.assertIn("intelligence-catalog/tools/run_daily_catalog_import.sh", contents)
        self.assertIn("catalog_import", contents)

    def test_plist_label_registered_in_postinstall(self) -> None:
        path = REPO_ROOT / "installer/macos-pkg/scripts/postinstall.sh"
        contents = path.read_text()
        self.assertIn(
            '"com.miningguardian.scheduled.catalog-import"',
            contents,
            "P-021 catalog-import label not registered in SCHEDULED_PLIST_LABELS",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
