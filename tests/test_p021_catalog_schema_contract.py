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
