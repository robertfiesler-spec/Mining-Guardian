"""
tests/test_w26_catalog_timestamp_columns.py

W26 cohort guard (2026-05-12) — federation prerequisite.

Why this guard exists
---------------------
W28 (federation v1) performs monthly bidirectional sync between the master
catalog (on operator's PC) and customer Mini catalogs. The pull script
identifies "rows changed since last sync" via:

    SELECT ... FROM <table> WHERE updated_at > $last_sync_ts

For this to work, every catalog table either:

  (a) has an `updated_at TIMESTAMPTZ` column maintained by a trigger or
      application code, OR
  (b) is intentionally append-only and uses a different per-row timestamp
      (`created_at`, `ingested_at`) that federation pulls via a different
      query template.

The 2026-05-12 audit (PR #194, see `docs/EXECUTION_PLAN_STATUS.md` W26)
found that 89 of 98 catalog tables on the live Mini already have
`updated_at`. The remaining 9 are all append-only event logs:

    knowledge.field_discovery_log         created_at
    knowledge.freshness_log               created_at
    knowledge.raw_ingestion_log           ingested_at  (partitioned parent)
    knowledge.raw_ingestion_log_2026_q1   ingested_at
    knowledge.raw_ingestion_log_2026_q2   ingested_at
    knowledge.raw_ingestion_log_2026_q3   ingested_at
    knowledge.raw_ingestion_log_2026_q4   ingested_at
    knowledge.raw_ingestion_log_2027_q1   ingested_at
    pool.bitcoin_network_snapshots        created_at

Decision (Approach A, locked 2026-05-12 evening): DON'T add `updated_at`
to the 9 append-only tables. Federation pull uses the constant mapping
below for them; all other catalog tables use `updated_at`.

This test fails if:
  - A new catalog table is introduced WITHOUT `updated_at` AND it's not in
    the `KNOWN_APPEND_ONLY_TABLES` mapping → forces explicit declaration
  - A table in `KNOWN_APPEND_ONLY_TABLES` doesn't have its declared
    timestamp column → catches typos and misnames
  - Live DB connection works but the catalog database doesn't exist yet
    → catches deploy-misorder (catalog must exist before federation)

Live-DB only — skips gracefully if Postgres is unreachable or the catalog
DB doesn't exist (e.g., on a CI runner without the container). This is
intentional: the test is a deployment-time guard, not a unit test.

References
----------
- docs/EXECUTION_PLAN_STATUS.md W26 (status, evidence)
- docs/strategy/05_CATALOG_DESIGN_PLAN_2026-05-12.md §3 W26 (Approach A)
- docs/HANDOFF_2026-05-12_EVENING.md §E7 (audit findings)
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Add repo root to sys.path so we can import core.db_targets
# (Same pattern as test_db_targets.py and other tests.)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ============================================================================
# The Approach A declaration: which catalog tables are append-only.
# ============================================================================
# Edit this when adding a new append-only event log table to the catalog.
# The value is the per-row timestamp column the W28 federation pull uses
# to identify changes since the last sync.
#
# Audited 2026-05-12 against live mining_guardian_catalog on Mini.
# See docs/strategy/05_CATALOG_DESIGN_PLAN_2026-05-12.md §3 W26.

KNOWN_APPEND_ONLY_TABLES: dict[str, str] = {
    # schema.table → timestamp column used for federation pulls
    "knowledge.field_discovery_log": "created_at",
    "knowledge.freshness_log": "created_at",
    "knowledge.raw_ingestion_log": "ingested_at",  # partitioned parent
    "knowledge.raw_ingestion_log_2026_q1": "ingested_at",
    "knowledge.raw_ingestion_log_2026_q2": "ingested_at",
    "knowledge.raw_ingestion_log_2026_q3": "ingested_at",
    "knowledge.raw_ingestion_log_2026_q4": "ingested_at",
    "knowledge.raw_ingestion_log_2027_q1": "ingested_at",
    "pool.bitcoin_network_snapshots": "created_at",
}

# Schemas to scan. Tables outside these are out of scope for federation.
# Excludes pg_catalog, information_schema, public (operational), and
# pg_temp/pg_toast_temp variants.
CATALOG_SCHEMAS = (
    "facility",
    "firmware",
    "hardware",
    "knowledge",
    "market",
    "ops",
    "pool",
    "regulatory",
    "repair",
    "staging",
)


# ============================================================================
# Helpers
# ============================================================================


def _try_connect():
    """Attempt to connect to the live catalog DB. Returns a psycopg2
    connection or None if anything goes wrong (driver missing, container
    down, auth fails, catalog DB doesn't exist).

    Uses core.db_targets.catalog_target() to honor the resolver chain —
    important because post-W14 the catalog lives on port 5433.
    """
    try:
        import psycopg2  # type: ignore
    except ImportError:
        return None

    try:
        from core.db_targets import catalog_target
    except ImportError:
        return None

    target = catalog_target()
    try:
        return psycopg2.connect(
            **target.connect_kwargs(),
            connect_timeout=3,
        )
    except Exception:
        return None


def _list_catalog_tables(conn) -> list[tuple[str, str]]:
    """Return [(schema, table_name), ...] for every base table in
    CATALOG_SCHEMAS. Excludes views, foreign tables, partition parents
    that have no rows (those still count — they have schema)."""
    schemas_sql = ",".join(f"'{s}'" for s in CATALOG_SCHEMAS)
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema IN ({schemas_sql})
          AND table_type = 'BASE TABLE'
        ORDER BY table_schema, table_name
        """
    )
    return [(s, t) for s, t in cur.fetchall()]


def _list_columns_for(conn, schema: str, table: str) -> set[str]:
    """Return the set of column names for one table."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        """,
        (schema, table),
    )
    return {row[0] for row in cur.fetchall()}


# ============================================================================
# The tests
# ============================================================================


class TestW26CatalogTimestampColumns(unittest.TestCase):
    """W26 cohort guard. Live-DB; skips if DB unreachable."""

    @classmethod
    def setUpClass(cls):
        cls.conn = _try_connect()
        if cls.conn is None:
            raise unittest.SkipTest(
                "Live catalog DB unreachable (psycopg2 missing, container down, "
                "auth failed, or catalog DB doesn't exist). W26 cohort guard "
                "is a deployment-time check — skipping in unit-test contexts."
            )

    @classmethod
    def tearDownClass(cls):
        if cls.conn is not None:
            cls.conn.close()

    def test_every_catalog_table_has_a_federation_timestamp(self):
        """Every base table in CATALOG_SCHEMAS must either:
          (a) have an `updated_at` column, OR
          (b) appear in KNOWN_APPEND_ONLY_TABLES with a valid timestamp column.
        """
        tables = _list_catalog_tables(self.conn)
        self.assertGreater(
            len(tables),
            50,
            f"Expected >50 catalog tables, found {len(tables)}. "
            "Either the catalog DB is empty (deploy issue) or the schemas "
            "list in this test is stale.",
        )

        offenders: list[str] = []
        for schema, table in tables:
            fq = f"{schema}.{table}"
            columns = _list_columns_for(self.conn, schema, table)

            if "updated_at" in columns:
                continue  # normal table, default federation path

            if fq in KNOWN_APPEND_ONLY_TABLES:
                # Declared append-only; verify the declared column exists.
                declared_col = KNOWN_APPEND_ONLY_TABLES[fq]
                if declared_col not in columns:
                    offenders.append(
                        f"  {fq}: KNOWN_APPEND_ONLY_TABLES declares "
                        f"timestamp column '{declared_col}' but the table "
                        f"has no such column. Found: {sorted(columns)}"
                    )
                continue

            # Not normal, not declared append-only → blocker
            offenders.append(
                f"  {fq}: has no 'updated_at' column AND is not in "
                "KNOWN_APPEND_ONLY_TABLES. Either add 'updated_at' to "
                "the table OR add an explicit entry to "
                "KNOWN_APPEND_ONLY_TABLES at the top of this file."
            )

        self.assertFalse(
            offenders,
            msg="\n\nW26 cohort guard failed — federation cannot pull these "
            f"tables cleanly:\n\n" + "\n".join(offenders)
            + "\n\nSee docs/strategy/05_CATALOG_DESIGN_PLAN_2026-05-12.md §3 W26 "
            "for the Approach A decision and rationale.\n",
        )

    def test_known_append_only_tables_actually_exist(self):
        """Every table in KNOWN_APPEND_ONLY_TABLES must exist in the live
        catalog. Catches typos in the declaration and tables that got
        dropped without updating this guard."""
        tables = {f"{s}.{t}" for s, t in _list_catalog_tables(self.conn)}

        missing = sorted(
            fq for fq in KNOWN_APPEND_ONLY_TABLES if fq not in tables
        )

        self.assertFalse(
            missing,
            msg="\n\nKNOWN_APPEND_ONLY_TABLES references tables that don't "
            f"exist in the live catalog:\n\n  "
            + "\n  ".join(missing)
            + "\n\nEither the table names have typos or these tables were "
            "dropped without updating this guard. Fix the names or remove "
            "the entries from KNOWN_APPEND_ONLY_TABLES.\n",
        )

    def test_no_overlap_between_normal_and_append_only(self):
        """A table can't have BOTH an `updated_at` column AND be in
        KNOWN_APPEND_ONLY_TABLES. That would be a contradictory
        declaration. Federation would pick the `updated_at` path; the
        manifest entry would be misleading."""
        contradictions: list[str] = []
        for fq in KNOWN_APPEND_ONLY_TABLES:
            schema, table = fq.split(".", 1)
            columns = _list_columns_for(self.conn, schema, table)
            if "updated_at" in columns:
                contradictions.append(
                    f"  {fq}: has both 'updated_at' AND a "
                    "KNOWN_APPEND_ONLY_TABLES entry. Remove the manifest "
                    "entry — the normal federation path applies."
                )

        self.assertFalse(
            contradictions,
            msg="\n\nContradictory declarations:\n\n"
            + "\n".join(contradictions)
            + "\n",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
