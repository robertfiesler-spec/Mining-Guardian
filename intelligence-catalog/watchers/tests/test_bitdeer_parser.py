#!/usr/bin/env python3
"""tests/test_bitdeer_parser.py — PR #21 fixture + parser unit tests.

Bitdeer's SealMiner catalog is uniformly SHA-256, so the algorithm
filter is exercised against a synthetic non-SHA entry rather than a
real fixture row.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_WATCHERS = _HERE.parent
sys.path.insert(0, str(_WATCHERS))

import manufacturer_watcher as mw  # noqa: E402
from manufacturer_watcher import ParseResult  # noqa: E402
from parsers import bitdeer  # noqa: E402


class BitdeerFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = _WATCHERS / "parsers" / "fixtures" / "bitdeer_offline.json"
        cls.data = json.loads(cls.path.read_text())

    def test_fixture_exists(self):
        self.assertTrue(self.path.exists())

    def test_at_least_twelve_sha_models(self):
        sha = [m for m in self.data["models"]
               if "sha" in m["algorithm"].lower()]
        self.assertGreaterEqual(len(sha), 12)

    def test_required_fields(self):
        for m in self.data["models"]:
            for f in ("slug", "manufacturer", "display_name", "algorithm", "specs"):
                self.assertIn(f, m, f"missing {f} in {m}")
            self.assertEqual(m["manufacturer"], "bitdeer")

    def test_only_sha256_skus(self):
        for m in self.data["models"]:
            self.assertIn("sha", m["algorithm"].lower(),
                          f"non-SHA SKU in fixture: {m['slug']}")

    def test_slugs_unique_and_prefixed(self):
        slugs = [m["slug"] for m in self.data["models"]]
        self.assertEqual(len(slugs), len(set(slugs)))
        for s in slugs:
            self.assertTrue(s.startswith("bitdeer-sealminer-"),
                            f"unexpected slug shape: {s}")

    def test_extra_aliases_reference_real_slugs(self):
        valid = {m["slug"] for m in self.data["models"]}
        for slug in self.data.get("extra_aliases", {}):
            self.assertIn(slug, valid)


class BitdeerParserTests(unittest.TestCase):
    def test_offline_load_returns_models(self):
        p = bitdeer.Parser(offline=True)
        result = p.fetch()
        slugs = [m["slug"] for m in result.models]
        self.assertGreaterEqual(len(slugs), 12)
        self.assertIn("bitdeer-sealminer-a4-ultra-hydro", slugs)

    def test_non_sha_dropped_by_filter(self):
        """Synthetic non-SHA entry must be dropped by _filtered()."""
        p = bitdeer.Parser(offline=True)
        synthetic = ParseResult(models=[
            {"slug": "bitdeer-fake-kaspa", "manufacturer": "bitdeer",
             "display_name": "Fake Kaspa", "algorithm": "kHeavyHash",
             "specs": {}},
            {"slug": "bitdeer-sealminer-a2", "manufacturer": "bitdeer",
             "display_name": "A2", "algorithm": "SHA-256", "specs": {}},
        ])
        out = p._filtered(synthetic)
        slugs = [m["slug"] for m in out.models]
        self.assertNotIn("bitdeer-fake-kaspa", slugs)
        self.assertIn("bitdeer-sealminer-a2", slugs)
        self.assertTrue(any("dropped" in n for n in out.notes))


class BitdeerDryRunTests(unittest.TestCase):
    def test_dry_run_through_engine(self):
        stats = mw.run_watcher(only=["bitdeer"], offline=True, dry_run=True)
        self.assertEqual(stats.parsers_run, 1)
        self.assertEqual(stats.parsers_failed, 0)
        self.assertGreaterEqual(stats.models_proposed, 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
