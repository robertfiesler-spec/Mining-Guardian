#!/usr/bin/env python3
"""tests/test_auradine_parser.py — PR #20 fixture + parser unit tests.

Auradine is the first parser to exercise the algorithm filter against real
fixture data: AI3680 (Kaspa, kHeavyHash) is intentionally bundled so we can
verify _filtered() drops it before staging proposals are emitted.
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
from parsers import auradine  # noqa: E402


class AuradineFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = _WATCHERS / "parsers" / "fixtures" / "auradine_offline.json"
        cls.data = json.loads(cls.path.read_text())

    def test_fixture_exists(self):
        self.assertTrue(self.path.exists())

    def test_at_least_five_sha_models(self):
        sha = [m for m in self.data["models"]
               if "sha" in m["algorithm"].lower()]
        self.assertGreaterEqual(len(sha), 5)

    def test_required_fields(self):
        for m in self.data["models"]:
            for f in ("slug", "manufacturer", "display_name", "algorithm", "specs"):
                self.assertIn(f, m, f"missing {f} in {m}")
            self.assertEqual(m["manufacturer"], "auradine")

    def test_kaspa_sku_is_present_in_raw_fixture(self):
        """AI3680 must be in the raw fixture so the parser test below
        can verify it is dropped by _filtered()."""
        slugs = [m["slug"] for m in self.data["models"]]
        self.assertIn("auradine-teraflux-ai3680", slugs)

    def test_slugs_unique_and_prefixed(self):
        slugs = [m["slug"] for m in self.data["models"]]
        self.assertEqual(len(slugs), len(set(slugs)))
        for s in slugs:
            self.assertTrue(s.startswith("auradine-teraflux-"),
                            f"unexpected slug shape: {s}")

    def test_extra_aliases_reference_real_slugs(self):
        valid = {m["slug"] for m in self.data["models"]}
        for slug in self.data.get("extra_aliases", {}):
            self.assertIn(slug, valid)


class AuradineParserTests(unittest.TestCase):
    def test_kaspa_sku_dropped_by_filter(self):
        """The Kaspa AI3680 lives in the fixture but must NOT survive
        _filtered() into the parser output."""
        p = auradine.Parser(offline=True)
        result = p.fetch()
        slugs = [m["slug"] for m in result.models]
        self.assertNotIn("auradine-teraflux-ai3680", slugs,
                         "Kaspa SKU should have been filtered out")
        # And the SHA-256 SKUs survive
        self.assertGreaterEqual(len(slugs), 5)

    def test_drop_note_in_result(self):
        p = auradine.Parser(offline=True)
        result = p.fetch()
        joined = " ".join(result.notes)
        self.assertIn("dropped", joined,
                      "expected drop note in ParseResult.notes")
        self.assertIn("auradine-teraflux-ai3680", joined)


class AuradineDryRunTests(unittest.TestCase):
    def test_dry_run_through_engine(self):
        stats = mw.run_watcher(only=["auradine"], offline=True, dry_run=True)
        self.assertEqual(stats.parsers_run, 1)
        self.assertEqual(stats.parsers_failed, 0)
        # AI3680 dropped, so we expect ~5 models
        self.assertGreaterEqual(stats.models_proposed, 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
