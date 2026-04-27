#!/usr/bin/env python3
"""tests/test_microbt_parser.py — PR #18 fixture + parser unit tests."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_WATCHERS = _HERE.parent
sys.path.insert(0, str(_WATCHERS))

import manufacturer_watcher as mw  # noqa: E402
from parsers import microbt  # noqa: E402


class MicroBTFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = _WATCHERS / "parsers" / "fixtures" / "microbt_offline.json"
        cls.data = json.loads(cls.path.read_text())

    def test_fixture_exists(self):
        self.assertTrue(self.path.exists())

    def test_at_least_eight_models(self):
        # M50 family + M60 family + a couple hydro = >=8
        self.assertGreaterEqual(len(self.data["models"]), 8)

    def test_required_fields(self):
        for m in self.data["models"]:
            for f in ("slug", "manufacturer", "display_name", "algorithm", "specs"):
                self.assertIn(f, m, f"missing {f} in {m}")
            self.assertEqual(m["manufacturer"], "microbt")

    def test_only_sha256(self):
        for m in self.data["models"]:
            self.assertIn("sha", m["algorithm"].lower(),
                          f"non-SHA-256 SKU: {m['slug']}")

    def test_slugs_unique_and_prefixed(self):
        slugs = [m["slug"] for m in self.data["models"]]
        self.assertEqual(len(slugs), len(set(slugs)))
        for s in slugs:
            self.assertTrue(s.startswith("microbt-whatsminer-"),
                            f"unexpected slug shape: {s}")

    def test_extra_aliases_reference_real_slugs(self):
        valid = {m["slug"] for m in self.data["models"]}
        for slug in self.data.get("extra_aliases", {}):
            self.assertIn(slug, valid)


class MicroBTParserTests(unittest.TestCase):
    def test_parser_loads_in_offline_mode(self):
        p = microbt.Parser(offline=True)
        result = p.fetch()
        self.assertGreaterEqual(len(result.models), 8)
        for m in result.models:
            self.assertEqual(m["manufacturer"], "microbt")

    def test_dropping_non_sha_skus(self):
        """Inject a fake non-SHA model and confirm _filtered drops it."""
        p = microbt.Parser(offline=True)
        from manufacturer_watcher import ParseResult
        synthetic = ParseResult(
            models=[
                {"slug": "microbt-whatsminer-bogus",
                 "manufacturer": "microbt", "display_name": "Bogus",
                 "algorithm": "kHeavyHash", "specs": {}},
                {"slug": "microbt-whatsminer-m50",
                 "manufacturer": "microbt", "display_name": "M50",
                 "algorithm": "SHA-256", "specs": {}},
            ],
            extra_aliases={},
        )
        out = p._filtered(synthetic)
        slugs = [m["slug"] for m in out.models]
        self.assertNotIn("microbt-whatsminer-bogus", slugs)
        self.assertIn("microbt-whatsminer-m50", slugs)


class MicroBTDryRunTests(unittest.TestCase):
    def test_dry_run_through_engine(self):
        stats = mw.run_watcher(only=["microbt"], offline=True, dry_run=True)
        self.assertEqual(stats.parsers_run, 1)
        self.assertEqual(stats.parsers_failed, 0)
        self.assertGreaterEqual(stats.models_proposed, 8)
        self.assertGreaterEqual(stats.aliases_proposed, 8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
