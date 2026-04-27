#!/usr/bin/env python3
"""
tests/test_manufacturer_watcher.py — PR #16 unit tests for the C3 watcher
framework. Network-free; uses dry-run + offline fixture so it passes in
sandbox/CI without internet or Postgres.

Run from repo root:
    python intelligence-catalog/watchers/tests/test_manufacturer_watcher.py
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from uuid import UUID

# Make the watcher package importable
_HERE = Path(__file__).resolve().parent
_WATCHERS = _HERE.parent
sys.path.insert(0, str(_WATCHERS))

import manufacturer_watcher as mw  # noqa: E402


class NormalizeAliasTests(unittest.TestCase):
    """The Python normalize MUST match the SQL normalize_alias contract."""

    def test_basic_lowercase(self):
        self.assertEqual(mw.normalize_alias("Antminer"), "antminer")

    def test_strip_spaces(self):
        self.assertEqual(mw.normalize_alias("S21 EXP"), "s21exp")

    def test_no_change_for_alphanumeric(self):
        self.assertEqual(mw.normalize_alias("S21EXP"), "s21exp")

    def test_strip_punctuation(self):
        self.assertEqual(mw.normalize_alias("S21-EXP+"), "s21exp")

    def test_collide_spaced_and_unspaced(self):
        self.assertEqual(mw.normalize_alias("S21 EXP"), mw.normalize_alias("S21EXP"))

    def test_empty_string(self):
        self.assertEqual(mw.normalize_alias(""), "")

    def test_only_punctuation(self):
        self.assertEqual(mw.normalize_alias("---"), "")

    def test_unicode_safe(self):
        # Em-dash, plus sign, etc. should all strip cleanly
        self.assertEqual(mw.normalize_alias("S21+ Plus"), "s21plus")


class ParserRegistryTests(unittest.TestCase):
    def test_only_bitmain_registered(self):
        # Wed PRs will add microbt/canaan/auradine/bitdeer
        self.assertEqual(mw.PARSER_MODULES, ["parsers.bitmain"])

    def test_bitmain_loads(self):
        parsers = mw._load_parsers()
        self.assertEqual(len(parsers), 1)
        self.assertEqual(parsers[0].BRAND, "bitmain")
        self.assertEqual(parsers[0].DISPLAY_NAME, "Bitmain")
        self.assertTrue(parsers[0].OFFLINE_FIXTURE.exists())

    def test_only_filter(self):
        parsers = mw._load_parsers(only=["bitmain"])
        self.assertEqual(len(parsers), 1)
        empty = mw._load_parsers(only=["nonexistent"])
        self.assertEqual(len(empty), 0)


class BitmainFixtureTests(unittest.TestCase):
    """The fixture itself must satisfy a few invariants."""

    @classmethod
    def setUpClass(cls):
        fixture_path = (
            _WATCHERS / "parsers" / "fixtures" / "bitmain_offline.json"
        )
        cls.data = json.loads(fixture_path.read_text())

    def test_at_least_five_models(self):
        self.assertGreaterEqual(len(self.data["models"]), 5)

    def test_every_model_has_required_fields(self):
        for m in self.data["models"]:
            for f in ("slug", "manufacturer", "display_name", "algorithm", "specs"):
                self.assertIn(f, m, f"missing {f} in {m}")
            self.assertEqual(m["manufacturer"], "bitmain")

    def test_only_sha256(self):
        for m in self.data["models"]:
            algo = m["algorithm"].lower()
            self.assertIn("sha", algo, f"non-SHA-256 SKU: {m['slug']}")

    def test_slugs_are_unique(self):
        slugs = [m["slug"] for m in self.data["models"]]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_extra_aliases_reference_real_slugs(self):
        valid_slugs = {m["slug"] for m in self.data["models"]}
        for slug in self.data.get("extra_aliases", {}):
            self.assertIn(slug, valid_slugs, f"alias for unknown slug: {slug}")

    def test_aliases_collide_as_expected(self):
        """S21 Plus / S21Plus normalize identically; '+' alone strips to nothing
        so 'S21+' would dangerously collapse to 's21' (same as base S21).
        Framework must catch that — verified separately in DryRunTests."""
        plus_aliases = ["S21 Plus", "S21Plus"]
        norms = {mw.normalize_alias(a) for a in plus_aliases}
        self.assertEqual(len(norms), 1, f"expected one norm, got {norms}")
        # And explicitly: S21+ should NOT match S21Plus (they normalize differently)
        self.assertNotEqual(
            mw.normalize_alias("S21+"), mw.normalize_alias("S21Plus"),
            "normalizer should distinguish S21+ (s21) from S21Plus (s21plus)",
        )


class DryRunTests(unittest.TestCase):
    """End-to-end: run the watcher in --offline --dry-run mode."""

    def test_dry_run_returns_stats(self):
        stats = mw.run_watcher(only=["bitmain"], offline=True, dry_run=True)
        self.assertEqual(stats.parsers_run, 1)
        self.assertEqual(stats.parsers_failed, 0)
        self.assertGreaterEqual(stats.models_proposed, 5)
        self.assertGreaterEqual(stats.aliases_proposed, 5)

    def test_dry_run_catches_known_collisions(self):
        """S21+ model_number/display_name normalize to 's21' / 'antminers21',
        which collide with the base S21 model. Framework must skip them and
        flag for triage — that is the whole point of N6's collision check."""
        stats = mw.run_watcher(only=["bitmain"], offline=True, dry_run=True)
        self.assertGreaterEqual(
            stats.aliases_skipped_collision, 2,
            "expected S21+ display_name & model_number to be flagged as colliding",
        )

    def test_dry_run_run_id_is_uuid(self):
        # Pass a known run_id and ensure the function accepts UUID
        from uuid import uuid4
        rid = uuid4()
        stats = mw.run_watcher(
            only=["bitmain"], offline=True, dry_run=True, run_id=rid
        )
        self.assertEqual(stats.parsers_run, 1)


class CollisionDetectionTests(unittest.TestCase):
    """Inject a synthetic parser to verify cross-model collision is enforced."""

    def test_collision_is_detected(self):
        from manufacturer_watcher import BaseParser, ParseResult, run_watcher

        class FakeParser(BaseParser):
            BRAND = "fakebrand"
            DISPLAY_NAME = "Fake"
            START_URLS = []

            def fetch(self):
                return ParseResult(
                    models=[
                        {"slug": "a", "display_name": "X1"},
                        {"slug": "b", "display_name": "X 1"},  # normalizes same
                    ],
                    extra_aliases={},
                )

        # Monkeypatch _load_parsers to return our fake
        original = mw._load_parsers
        mw._load_parsers = lambda only=None: [FakeParser()]
        try:
            stats = mw.run_watcher(offline=True, dry_run=True)
        finally:
            mw._load_parsers = original

        # X1 and X 1 both normalize to "x1"; second one must be flagged.
        self.assertGreaterEqual(stats.aliases_skipped_collision, 1)


class CLITests(unittest.TestCase):
    def test_list_subcommand(self):
        rc = mw.main(["--list"])
        self.assertEqual(rc, 0)

    def test_no_args_returns_help(self):
        rc = mw.main([])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
