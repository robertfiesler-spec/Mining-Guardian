#!/usr/bin/env python3
"""Tests for the W10 catalog-intake writers in
intelligence-catalog/db/dual_writer.py.

W10 added four functions that — unlike the propose_* proposal writers, which
land in staging.* and await a separate promote step — write DIRECTLY into
catalog tables:

    propose_firmware_release        → firmware.firmware_releases
    propose_firmware_compatibility  → firmware.firmware_compatibility
    propose_data_conflict           → knowledge.data_conflicts
    record_freshness_check          → knowledge.freshness_log

Structure mirrors test_dual_writer.py:
  * importlib load of dual_writer.py (hyphen in the dir name blocks a plain
    import)
  * _have_db() gate — integration tests auto-skip when no catalog DB is
    reachable, so this file is safe in a CI box without Postgres
  * a TestUnitNoDB class for the argument-validation paths, which need no DB

Difference from test_dual_writer.py, on purpose:
  * the integration tests here write to REAL catalog tables, not throwaway
    staging rows. So every test is scrupulous about teardown — fixtures and
    written rows are tagged with a unique per-run marker and removed in a
    finally/tearDownClass that runs even when an assert fails, and teardown
    is idempotent (safe even if a row was never created).
  * verification/cleanup connections reuse dual_writer._get_connection() —
    the module's own helper, which resolves core.db_targets.catalog_target().
    That guarantees the test inspects the SAME database the function wrote
    to. (test_dual_writer.py opens its own psycopg2.connect() off the libpq
    PGHOST/PGDATABASE family, which core.db_targets deliberately does NOT
    honor — reusing _get_connection() sidesteps that mismatch entirely.)

Run:
    Set the catalog-DB connection environment the same way the other
    catalog tests expect it (see core/db_targets.py for the variable
    family the resolver reads, and .env / .env.example on the host).
    With that environment in place:

        python intelligence-catalog/db/tests/test_w10_catalog_intake.py

    The integration tests auto-skip if the catalog DB is unreachable, so
    this file is also safe to run with no environment set at all.
"""

import sys
import unittest
from pathlib import Path
from uuid import uuid4

# Path resolution: make intelligence-catalog/db importable
ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT / "intelligence-catalog"))

# Direct import via importlib (hyphen in dir name blocks a plain import)
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location(
    "_dual_writer",
    ROOT / "intelligence-catalog" / "db" / "dual_writer.py",
)
dw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dw)


def _have_db() -> bool:
    return dw.is_postgres_available()


# ──────────────────────────────────────────────────────────────────────────
# Integration tests — require a reachable catalog DB
# ──────────────────────────────────────────────────────────────────────────

@unittest.skipUnless(_have_db(), "no Postgres reachable; skipping integration tests")
class TestW10CatalogIntake(unittest.TestCase):
    """Write→verify→cleanup against a live catalog DB.

    setUpClass builds the FK prerequisites the writers need (a knowledge.sources
    pair, a hardware.manufacturers + hardware.miner_models row) all tagged with
    a unique run marker. tearDownClass removes everything in reverse-FK order,
    idempotently.
    """

    @classmethod
    def setUpClass(cls):
        cls.run_id = str(uuid4())
        cls.marker = f"test-w10-{cls.run_id[:8]}"
        # version_string / canonical_name / source_key values used across tests
        cls.fw_version = f"{cls.marker}-fw-1.0"
        cls.miner_name = f"{cls.marker} Test Miner"
        cls.source_key_a = f"{cls.marker}-src-a"
        cls.source_key_b = f"{cls.marker}-src-b"

        conn = dw._get_connection()
        assert conn is not None, "setUpClass: catalog DB unreachable"
        try:
            with conn, conn.cursor() as cur:
                # Two knowledge.sources rows — needed as source_a_id / source_b_id
                # by propose_data_conflict, and handy as primary_source_id elsewhere.
                cur.execute(
                    "INSERT INTO knowledge.sources (source_key, display_name, tier) "
                    "VALUES (%s, %s, 'tier4_community'), (%s, %s, 'tier4_community') "
                    "RETURNING id",
                    (cls.source_key_a, f"{cls.marker} source A",
                     cls.source_key_b, f"{cls.marker} source B"),
                )
                rows = cur.fetchall()
                # RETURNING on a multi-row INSERT yields rows in insert order
                cls.source_a_id = rows[0][0]
                cls.source_b_id = rows[1][0]

                # A miner_model fixture — needed by
                # propose_firmware_compatibility's miner_slug resolution.
                # It needs a manufacturer_id FK; rather than create a
                # manufacturer (hardware.manufacturers has several NOT NULL
                # columns — legal_name, common_name — so a bare-brand INSERT
                # fails), reuse an existing seeded manufacturer. The catalog
                # ships seeded with 13+ real manufacturers via
                # deploy_schema.sql, and the real W11 intake flow likewise
                # runs against the populated catalog.
                cur.execute(
                    "SELECT id FROM hardware.manufacturers "
                    "ORDER BY created_at LIMIT 1"
                )
                m = cur.fetchone()
                assert m is not None, (
                    "setUpClass: hardware.manufacturers is empty — "
                    "expected a seeded catalog"
                )
                cls.manufacturer_id = m[0]
                cls._created_manufacturer = False  # never create -> never delete

                cur.execute(
                    """
                    INSERT INTO hardware.miner_models
                        (manufacturer_id, canonical_name, cooling_type,
                         hashboard_count, stock_hashrate_th, primary_source_id)
                    VALUES (%s, %s, 'air'::cooling_type, 3, 100, %s)
                    RETURNING id
                    """,
                    (cls.manufacturer_id, cls.miner_name, cls.source_a_id),
                )
                cls.miner_model_id = cur.fetchone()[0]
        finally:
            conn.close()

    @classmethod
    def tearDownClass(cls):
        """Remove everything setUpClass and the tests created, reverse-FK
        order, idempotently. A LIKE on the run marker sweeps any rows a test
        wrote; explicit deletes by id handle the fixtures."""
        conn = dw._get_connection()
        if conn is None:
            return
        try:
            with conn, conn.cursor() as cur:
                # firmware_compatibility — FK→firmware_releases & miner_models
                cur.execute(
                    "DELETE FROM firmware.firmware_compatibility "
                    "WHERE miner_model_id = %s",
                    (getattr(cls, "miner_model_id", None),),
                )
                # firmware_releases — by the marker in version_string
                cur.execute(
                    "DELETE FROM firmware.firmware_releases "
                    "WHERE version_string LIKE %s",
                    (f"{cls.marker}%",),
                )
                # data_conflicts — by the marker in conflict_table
                cur.execute(
                    "DELETE FROM knowledge.data_conflicts "
                    "WHERE conflict_table LIKE %s",
                    (f"{cls.marker}%",),
                )
                # freshness_log — by the marker in tracked_table
                cur.execute(
                    "DELETE FROM knowledge.freshness_log "
                    "WHERE tracked_table LIKE %s",
                    (f"{cls.marker}%",),
                )
                # miner_models fixture
                cur.execute(
                    "DELETE FROM hardware.miner_models WHERE id = %s",
                    (getattr(cls, "miner_model_id", None),),
                )
                # manufacturer fixture — only if we created it
                if getattr(cls, "_created_manufacturer", False):
                    cur.execute(
                        "DELETE FROM hardware.manufacturers WHERE id = %s",
                        (cls.manufacturer_id,),
                    )
                # knowledge.sources fixtures
                cur.execute(
                    "DELETE FROM knowledge.sources WHERE source_key LIKE %s",
                    (f"{cls.marker}%",),
                )
        finally:
            conn.close()

    # ── propose_firmware_release ──────────────────────────────────────────

    def test_firmware_release_inserts(self):
        fid = dw.propose_firmware_release(
            family="bixbit",
            version=self.fw_version,
            payload={"display_name": f"{self.marker} BiXBiT 1.0",
                     "download_url": "https://example.invalid/fw.tar.gz"},
            source_tool="test_w10",
        )
        self.assertIsNotNone(fid)

        conn = dw._get_connection()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT firmware_family, version_string, download_url "
                    "FROM firmware.firmware_releases WHERE id = %s",
                    (fid,),
                )
                row = cur.fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row[0], "bixbit")
                self.assertEqual(row[1], self.fw_version)
                self.assertEqual(row[2], "https://example.invalid/fw.tar.gz")
        finally:
            conn.close()

    def test_firmware_release_idempotent_upsert(self):
        # Same (family, version) twice — second call UPDATEs, does not
        # duplicate. Both return the same row id.
        v = f"{self.marker}-fw-idem"
        first = dw.propose_firmware_release(
            family="vnish", version=v,
            payload={"notes": "first"}, source_tool="test_w10",
        )
        second = dw.propose_firmware_release(
            family="vnish", version=v,
            payload={"notes": "second"}, source_tool="test_w10",
        )
        self.assertIsNotNone(first)
        self.assertEqual(first, second, "re-write of same family+version "
                         "should UPSERT to the same row, not duplicate")

        conn = dw._get_connection()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM firmware.firmware_releases "
                    "WHERE version_string = %s", (v,),
                )
                self.assertEqual(cur.fetchone()[0], 1)
                # the UPDATE branch took the newer notes
                cur.execute(
                    "SELECT notes FROM firmware.firmware_releases "
                    "WHERE version_string = %s", (v,),
                )
                self.assertEqual(cur.fetchone()[0], "second")
        finally:
            conn.close()

    # ── propose_firmware_compatibility ────────────────────────────────────

    def test_firmware_compatibility_inserts_when_both_resolve(self):
        # Prerequisite: a firmware release whose version_string we can resolve.
        dw.propose_firmware_release(
            family="luxos", version=f"{self.marker}-fw-compat",
            payload={}, source_tool="test_w10",
        )
        cid = dw.propose_firmware_compatibility(
            firmware_slug=f"{self.marker}-fw-compat",
            miner_slug=self.miner_name,
            payload={"is_compatible": True, "typical_hashrate_th": 123.4},
            source_tool="test_w10",
        )
        self.assertIsNotNone(cid)

        conn = dw._get_connection()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT miner_model_id, typical_hashrate_th "
                    "FROM firmware.firmware_compatibility WHERE id = %s",
                    (cid,),
                )
                row = cur.fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row[0], self.miner_model_id)
                self.assertEqual(float(row[1]), 123.4)
        finally:
            conn.close()

    def test_firmware_compatibility_skips_on_unresolved_firmware(self):
        # firmware_slug that does not exist → fail-soft skip → None,
        # and NOTHING written.
        cid = dw.propose_firmware_compatibility(
            firmware_slug=f"{self.marker}-does-not-exist",
            miner_slug=self.miner_name,
            payload={}, source_tool="test_w10",
        )
        self.assertIsNone(cid, "unresolved firmware_slug should fail-soft "
                          "skip and return None")

    def test_firmware_compatibility_skips_on_unresolved_miner(self):
        # Real firmware, bogus miner_slug → fail-soft skip → None.
        dw.propose_firmware_release(
            family="epic", version=f"{self.marker}-fw-orphan",
            payload={}, source_tool="test_w10",
        )
        cid = dw.propose_firmware_compatibility(
            firmware_slug=f"{self.marker}-fw-orphan",
            miner_slug=f"{self.marker}-no-such-miner",
            payload={}, source_tool="test_w10",
        )
        self.assertIsNone(cid, "unresolved miner_slug should fail-soft "
                          "skip and return None")

    # ── propose_data_conflict ─────────────────────────────────────────────

    def test_data_conflict_inserts(self):
        row_id = uuid4()
        cid = dw.propose_data_conflict(
            conflict_table=f"{self.marker}.miner_models",
            conflict_row_id=row_id,
            conflict_field="stock_hashrate_th",
            value_a={"raw": "104", "unit": "TH/s"},
            value_b={"raw": "96", "unit": "TH/s"},
            source_a_id=self.source_a_id,
            source_b_id=self.source_b_id,
            payload={"severity": "low"},
            source_tool="test_w10",
        )
        self.assertIsNotNone(cid)

        conn = dw._get_connection()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT conflict_field, is_resolved, severity "
                    "FROM knowledge.data_conflicts WHERE id = %s",
                    (cid,),
                )
                row = cur.fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row[0], "stock_hashrate_th")
                self.assertFalse(row[1])           # is_resolved defaults FALSE
                self.assertEqual(row[2], "low")
        finally:
            conn.close()

    def test_data_conflict_dedups_unresolved(self):
        # Same (conflict_table, conflict_row_id, conflict_field) triple twice
        # while unresolved → second call returns the FIRST row's id, no dup.
        row_id = uuid4()
        kw = dict(
            conflict_table=f"{self.marker}.dedup",
            conflict_row_id=row_id,
            conflict_field="power_w",
            value_a={"raw": "3000"},
            value_b={"raw": "3250"},
            source_a_id=self.source_a_id,
            source_b_id=self.source_b_id,
            payload={},
            source_tool="test_w10",
        )
        first = dw.propose_data_conflict(**kw)
        second = dw.propose_data_conflict(**kw)
        self.assertIsNotNone(first)
        self.assertEqual(first, second, "an unresolved conflict on the same "
                         "triple should dedup to the existing row")

        conn = dw._get_connection()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM knowledge.data_conflicts "
                    "WHERE conflict_table = %s AND conflict_row_id = %s "
                    "AND conflict_field = %s",
                    (f"{self.marker}.dedup", str(row_id), "power_w"),
                )
                self.assertEqual(cur.fetchone()[0], 1)
        finally:
            conn.close()

    # ── record_freshness_check ────────────────────────────────────────────

    def test_freshness_check_appends(self):
        row_id = uuid4()
        fid = dw.record_freshness_check(
            tracked_table=f"{self.marker}.miner_models",
            tracked_row_id=row_id,
            found_new=False,
            payload={"verification_method": "api_pull"},
            source_tool="test_w10",
        )
        self.assertIsNotNone(fid)

        conn = dw._get_connection()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT verification_method, metadata "
                    "FROM knowledge.freshness_log WHERE id = %s",
                    (fid,),
                )
                row = cur.fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row[0], "api_pull")
                # found_new + source_tool folded into metadata
                self.assertEqual(row[1].get("found_new"), False)
                self.assertEqual(row[1].get("source_tool"), "test_w10")
        finally:
            conn.close()

    def test_freshness_check_does_not_dedup(self):
        # freshness_log is append-only: two checks of the SAME row are two
        # real events and BOTH must land. Distinct ids, two rows.
        row_id = uuid4()
        kw = dict(
            tracked_table=f"{self.marker}.append",
            tracked_row_id=row_id,
            found_new=False,
            payload={},
            source_tool="test_w10",
        )
        first = dw.record_freshness_check(**kw)
        second = dw.record_freshness_check(**kw)
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertNotEqual(first, second, "freshness_log is append-only — "
                            "a repeat check must create a SECOND row")

        conn = dw._get_connection()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM knowledge.freshness_log "
                    "WHERE tracked_table = %s AND tracked_row_id = %s",
                    (f"{self.marker}.append", str(row_id)),
                )
                self.assertEqual(cur.fetchone()[0], 2)
        finally:
            conn.close()


# ──────────────────────────────────────────────────────────────────────────
# Unit tests — no DB required
# ──────────────────────────────────────────────────────────────────────────

class TestW10UnitNoDB(unittest.TestCase):
    """Argument-validation paths. Every W10 writer raises ValueError on a
    missing/invalid REQUIRED arg BEFORE it ever opens a connection, so these
    run without a database."""

    def test_firmware_release_validates_args(self):
        with self.assertRaises(ValueError):
            dw.propose_firmware_release("", "1.0", {}, source_tool="t")
        with self.assertRaises(ValueError):
            dw.propose_firmware_release("not_a_family", "1.0", {}, source_tool="t")
        with self.assertRaises(ValueError):
            dw.propose_firmware_release("bixbit", "", {}, source_tool="t")
        with self.assertRaises(ValueError):
            dw.propose_firmware_release("bixbit", "1.0", "nope", source_tool="t")  # type: ignore
        with self.assertRaises(ValueError):
            dw.propose_firmware_release("bixbit", "1.0", {}, source_tool="")

    def test_firmware_release_accepts_every_known_family(self):
        # Guard: the in-module _FIRMWARE_FAMILIES set must accept each known
        # enum value without raising. (No DB — these will fail-soft to None
        # at the connection step, but must NOT raise ValueError.)
        for fam in dw._FIRMWARE_FAMILIES:
            try:
                dw.propose_firmware_release(fam, "0.0", {}, source_tool="t")
            except ValueError as e:  # pragma: no cover - would be a real bug
                self.fail(f"known family {fam!r} wrongly rejected: {e}")

    def test_firmware_compatibility_validates_args(self):
        with self.assertRaises(ValueError):
            dw.propose_firmware_compatibility("", "m", {}, source_tool="t")
        with self.assertRaises(ValueError):
            dw.propose_firmware_compatibility("f", "", {}, source_tool="t")
        with self.assertRaises(ValueError):
            dw.propose_firmware_compatibility("f", "m", None, source_tool="t")  # type: ignore
        with self.assertRaises(ValueError):
            dw.propose_firmware_compatibility("f", "m", {}, source_tool="")

    def test_data_conflict_validates_args(self):
        u = uuid4()
        with self.assertRaises(ValueError):
            dw.propose_data_conflict("", u, "f", 1, 2, u, u, {}, source_tool="t")
        with self.assertRaises(ValueError):
            dw.propose_data_conflict("tbl", None, "f", 1, 2, u, u, {}, source_tool="t")  # type: ignore
        with self.assertRaises(ValueError):
            dw.propose_data_conflict("tbl", u, "", 1, 2, u, u, {}, source_tool="t")
        with self.assertRaises(ValueError):
            dw.propose_data_conflict("tbl", u, "f", 1, 2, None, u, {}, source_tool="t")  # type: ignore
        with self.assertRaises(ValueError):
            dw.propose_data_conflict("tbl", u, "f", 1, 2, u, None, {}, source_tool="t")  # type: ignore
        with self.assertRaises(ValueError):
            dw.propose_data_conflict("tbl", u, "f", 1, 2, u, u, "nope", source_tool="t")  # type: ignore
        with self.assertRaises(ValueError):
            dw.propose_data_conflict("tbl", u, "f", 1, 2, u, u, {}, source_tool="")

    def test_freshness_check_validates_args(self):
        u = uuid4()
        with self.assertRaises(ValueError):
            dw.record_freshness_check("", u, False, {}, source_tool="t")
        with self.assertRaises(ValueError):
            dw.record_freshness_check("tbl", None, False, {}, source_tool="t")  # type: ignore
        with self.assertRaises(ValueError):
            dw.record_freshness_check("tbl", u, False, "nope", source_tool="t")  # type: ignore
        with self.assertRaises(ValueError):
            dw.record_freshness_check("tbl", u, False, {}, source_tool="")


if __name__ == "__main__":
    unittest.main(verbosity=2)
