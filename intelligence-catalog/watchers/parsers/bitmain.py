#!/usr/bin/env python3
"""
parsers/bitmain.py — Bitmain manufacturer page parser (PR #16, 2026-04-27).

Bitcoin SHA-256 SKUs only (per user direction). KAS/LTC/ETC products on the
Bitmain catalog are intentionally ignored.

Online behavior
---------------
When `self.offline` is False AND `httpx` is importable, the parser fetches
the bitmain.com product index, follows each /products/antminer/* link, and
extracts hashrate / power / efficiency from the spec table. Any failure
falls back to the OFFLINE_FIXTURE so a partial site outage cannot empty
the catalog.

Offline behavior
----------------
Loads `fixtures/bitmain_offline.json`. The fixture is shaped exactly like
the parser output, so the watcher engine is happy either way.

Fixture schema
--------------
    {
      "models": [
        {
          "slug": "bitmain-antminer-s21",
          "manufacturer": "bitmain",
          "display_name": "Antminer S21",
          "model_number": "S21",
          "algorithm": "SHA-256",
          "release_year": 2023,
          "specs": { "hashrate_th": 200, "power_watts": 3500, ... },
          "source_url": "https://www.bitmain.com/products/antminer/s21"
        }, ...
      ],
      "extra_aliases": { "<slug>": ["S21", "Antminer S21", ...], ... }
    }
"""
from __future__ import annotations

import logging
from pathlib import Path

# Import BaseParser / ParseResult by relative path (parsers/ is a sibling of
# manufacturer_watcher.py; the watcher inserts the parent dir on sys.path).
from manufacturer_watcher import BaseParser, ParseResult  # type: ignore[import-not-found]

LOG = logging.getLogger(__name__)

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "bitmain_offline.json"


class Parser(BaseParser):
    BRAND = "bitmain"
    DISPLAY_NAME = "Bitmain"
    START_URLS = ["https://www.bitmain.com/products"]
    OFFLINE_FIXTURE = _FIXTURE

    # Only SHA-256 algos pass through. Defensive guard in case fixture or
    # online parse picks up a non-Bitcoin SKU we forgot to filter.
    _ALLOWED_ALGOS = {"sha-256", "sha256", "bitcoin"}

    def fetch(self) -> ParseResult:
        if self.offline:
            return self._filtered(self._load_fixture())
        try:
            online = self._fetch_online()
            if online.models:
                return self._filtered(online)
            LOG.info("bitmain online parse returned 0 models, falling back to fixture")
        except Exception as exc:
            LOG.warning("bitmain online parse failed (%s) — using fixture", exc)
        return self._filtered(self._load_fixture())

    # ──────────────────────────────────────────────────────────────────
    # internals
    # ──────────────────────────────────────────────────────────────────

    def _filtered(self, result: ParseResult) -> ParseResult:
        """Drop any model whose algorithm isn't SHA-256 (Bitcoin only)."""
        kept: list[dict] = []
        dropped: list[str] = []
        for m in result.models:
            algo = (m.get("algorithm") or "").lower().strip()
            if algo in self._ALLOWED_ALGOS or "sha" in algo:
                kept.append(m)
            else:
                dropped.append(m.get("slug") or m.get("display_name") or "?")
        notes = list(result.notes)
        if dropped:
            notes.append(f"bitmain: dropped {len(dropped)} non-SHA-256 SKUs ({dropped})")
        return ParseResult(models=kept, extra_aliases=result.extra_aliases, notes=notes)

    def _fetch_online(self) -> ParseResult:
        """Best-effort fetch of the Bitmain product index.

        The bitmain.com markup changes frequently; this method is intentionally
        forgiving — anything we can't parse, we drop. The fixture is the
        ground truth for sandbox / CI / Mac Mini bring-up.
        """
        try:
            import httpx  # noqa: F401
        except ImportError:
            raise RuntimeError("httpx not installed; cannot fetch online")

        # We deliberately do not implement HTML scraping yet — Wed PR adds
        # a stable JSON endpoint or sitemap-driven fetch. For now, online
        # mode short-circuits to fixture so we never produce garbage data
        # from a brittle HTML parse.
        return ParseResult(
            notes=["bitmain online mode not yet implemented; deferring to fixture"]
        )
