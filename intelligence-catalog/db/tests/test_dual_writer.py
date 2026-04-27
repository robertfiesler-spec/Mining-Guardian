#!/usr/bin/env python3
"""Tests for intelligence-catalog/db/dual_writer.py (C1 / PR #15).

These exercise the public API against a live Postgres (the sandbox or any
DB where the staging schema has been deployed). They auto-skip when no DB
is reachable so they're safe to run in CI environments without a DB.

Run:
    PGHOST=/tmp PGPORT=5433 MG_DB_PASSWORD=sandbox \
        python intelligence-catalog/db/tests/test_dual_writer.py
"""

import os
import sys
import unittest
from pathlib import Path
from uuid import uuid4

# Path resolution: make intelligence-catalog/db importable
ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT / "intelligence-catalog"))

# Direct import via importlib (hyphen in dir name)
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location(
    "_dual_writer",
    ROOT / "intelligence-catalog" / "db" / "dual_writer.py",
)
dw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dw)


def _have_db() -> bool:
    return dw.is_postgres_available()


@unittest.skipUnless(_have_db(), "no Postgres reachable; skipping integration tests")
class TestDualWriter(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Use a unique per-run slug prefix so reruns don't collide
        cls.run_id = str(uuid4())
        cls.slug_prefix = f"test-pr15-{cls.run_id[:8]}-"

    def test_payload_hash_stable(self):
        a = dw._payload_hash({"a": 1, "b": 2})
        b = dw._payload_hash({"b": 2, "a": 1})
        self.assertEqual(a, b, "hash should be order-independent")

    def test_payload_hash_changes(self):
        a = dw._payload_hash({"a": 1})
        b = dw._payload_hash({"a": 2})
        self.assertNotEqual(a, b)

    def test_propose_miner_model_inserts(self):
        slug = f"{self.slug_prefix}insert"
        proposal_id = dw.propose_miner_model(
            slug=slug,
            payload={"manufacturer": "bitmain", "specs": {"stock_hashrate_th": 100}},
            source_tool="test_dual_writer",
        )
        self.assertIsNotNone(proposal_id)

    def test_propose_miner_model_dedup(self):
        slug = f"{self.slug_prefix}dedup"
        payload = {"manufacturer": "bitmain", "specs": {"stock_hashrate_th": 200}}
        first = dw.propose_miner_model(slug=slug, payload=payload, source_tool="test_dual_writer")
        second = dw.propose_miner_model(slug=slug, payload=payload, source_tool="test_dual_writer")
        self.assertIsNotNone(first)
        self.assertIsNone(second, "duplicate payload should be deduped (None)")

    def test_propose_miner_model_supersedes(self):
        slug = f"{self.slug_prefix}supersede"
        first = dw.propose_miner_model(
            slug=slug,
            payload={"manufacturer": "bitmain", "specs": {"stock_hashrate_th": 1}},
            source_tool="test_dual_writer",
        )
        second = dw.propose_miner_model(
            slug=slug,
            payload={"manufacturer": "bitmain", "specs": {"stock_hashrate_th": 2}},
            source_tool="test_dual_writer",
        )
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertNotEqual(first, second)

        # The first should now be 'superseded'
        import psycopg2  # noqa: E402
        conn = psycopg2.connect(
            host=os.environ.get("PGHOST", "/var/run/postgresql"),
            port=int(os.environ.get("PGPORT", "5432")),
            user=os.environ.get("PGUSER", "guardian_admin"),
            dbname=os.environ.get("PGDATABASE", "mining_guardian"),
            password=os.environ.get("MG_DB_PASSWORD"),
        )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status FROM staging.miner_model_proposals WHERE id=%s",
                    (first,),
                )
                row = cur.fetchone()
                self.assertEqual(row[0], "superseded")

                cur.execute(
                    "SELECT status FROM staging.miner_model_proposals WHERE id=%s",
                    (second,),
                )
                row = cur.fetchone()
                self.assertEqual(row[0], "pending")
        finally:
            conn.close()

    def test_propose_manufacturer_inserts(self):
        brand = f"test-mfg-{self.run_id[:8]}"
        proposal_id = dw.propose_manufacturer(
            brand=brand,
            payload={"legal_name": "Test Mfg Inc.", "country": "US"},
            source_tool="test_dual_writer",
        )
        self.assertIsNotNone(proposal_id)

    def test_propose_alias_inserts(self):
        slug = f"{self.slug_prefix}alias-target"
        proposal_id = dw.propose_alias(
            miner_slug=slug,
            alias=f"TestAlias-{self.run_id[:8]}",
            source_tool="test_dual_writer",
            alias_source="test",
        )
        self.assertIsNotNone(proposal_id)

    def test_promote_validated_round_trip(self):
        slug = f"{self.slug_prefix}promote"
        proposal_id = dw.propose_miner_model(
            slug=slug,
            payload={
                "manufacturer": "bitmain",
                "display_name": f"PR15 Test Miner {self.run_id[:8]}",
                "specs": {
                    "stock_hashrate_th": 999,
                    "stock_power_w": 3000,
                    "hashboard_count": 3,
                    "cooling_type": "air",
                },
            },
            source_tool="test_dual_writer",
        )
        self.assertIsNotNone(proposal_id)

        # Mark it validated
        import psycopg2
        conn = psycopg2.connect(
            host=os.environ.get("PGHOST", "/var/run/postgresql"),
            port=int(os.environ.get("PGPORT", "5432")),
            user=os.environ.get("PGUSER", "guardian_admin"),
            dbname=os.environ.get("PGDATABASE", "mining_guardian"),
            password=os.environ.get("MG_DB_PASSWORD"),
        )
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "UPDATE staging.miner_model_proposals "
                    "SET status='validated', validated_at=NOW() WHERE id=%s",
                    (proposal_id,),
                )

            # Promote
            n = dw.promote_validated_miner_models()
            self.assertGreaterEqual(n, 1)

            # Verify proposal is now 'promoted'
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status, promoted_to_id FROM staging.miner_model_proposals "
                    "WHERE id=%s",
                    (proposal_id,),
                )
                status, promoted_id = cur.fetchone()
                self.assertEqual(status, "promoted")
                self.assertIsNotNone(promoted_id)

                # And hardware.miner_models should have a row with this canonical_name
                cur.execute(
                    "SELECT id, stock_hashrate_th FROM hardware.miner_models WHERE id=%s",
                    (promoted_id,),
                )
                row = cur.fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(int(row[1]), 999)
        finally:
            # Clean up: delete the test miner_model row and the proposal
            with conn, conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM hardware.miner_models WHERE canonical_name LIKE %s",
                    (f"PR15 Test Miner {self.run_id[:8]}%",),
                )
                cur.execute(
                    "DELETE FROM staging.miner_model_proposals WHERE slug LIKE %s",
                    (f"{self.slug_prefix}%",),
                )
                cur.execute(
                    "DELETE FROM staging.manufacturer_proposals WHERE brand LIKE %s",
                    (f"test-mfg-%",),
                )
                cur.execute(
                    "DELETE FROM staging.alias_proposals WHERE miner_slug LIKE %s",
                    (f"{self.slug_prefix}%",),
                )
            conn.close()


class TestUnitNoDB(unittest.TestCase):
    """Tests that don't need a DB."""

    def test_payload_hash_basic(self):
        h = dw._payload_hash({"x": 1})
        self.assertEqual(len(h), 64)  # SHA-256 hex
        self.assertTrue(all(c in "0123456789abcdef" for c in h))

    def test_propose_validates_args(self):
        with self.assertRaises(ValueError):
            dw.propose_miner_model(slug="", payload={}, source_tool="x")
        with self.assertRaises(ValueError):
            dw.propose_miner_model(slug="x", payload="not a dict", source_tool="x")  # type: ignore
        with self.assertRaises(ValueError):
            dw.propose_miner_model(slug="x", payload={}, source_tool="")


if __name__ == "__main__":
    unittest.main(verbosity=2)
