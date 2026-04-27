#!/usr/bin/env python3
"""
parsers/microbt.py — MicroBT (Whatsminer) parser (PR #18, 2026-04-27).

Bitcoin SHA-256 SKUs only. Both air-cooled and hydro lines included since
the customer may run either form factor.

Online HTML scraping is intentionally a stub right now: the whatsminer.com
markup changes too often to depend on for the v1.0.0-rc1 cutover. The
fixture is the source of truth; a stable JSON / sitemap-driven fetch
ships in a follow-up PR.
"""
from __future__ import annotations

import logging
from pathlib import Path

from manufacturer_watcher import BaseParser, ParseResult  # type: ignore[import-not-found]

LOG = logging.getLogger(__name__)
_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "microbt_offline.json"


class Parser(BaseParser):
    BRAND = "microbt"
    DISPLAY_NAME = "MicroBT"
    START_URLS = ["https://www.whatsminer.com/products"]
    OFFLINE_FIXTURE = _FIXTURE

    _ALLOWED_ALGOS = {"sha-256", "sha256", "bitcoin"}

    def fetch(self) -> ParseResult:
        if self.offline:
            return self._filtered(self._load_fixture())
        try:
            online = self._fetch_online()
            if online.models:
                return self._filtered(online)
            LOG.info("microbt online parse returned 0 models, falling back to fixture")
        except Exception as exc:
            LOG.warning("microbt online parse failed (%s) — using fixture", exc)
        return self._filtered(self._load_fixture())

    def _filtered(self, result: ParseResult) -> ParseResult:
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
            notes.append(f"microbt: dropped {len(dropped)} non-SHA-256 SKUs ({dropped})")
        return ParseResult(models=kept, extra_aliases=result.extra_aliases, notes=notes)

    def _fetch_online(self) -> ParseResult:
        try:
            import httpx  # noqa: F401
        except ImportError:
            raise RuntimeError("httpx not installed; cannot fetch online")
        return ParseResult(
            notes=["microbt online mode not yet implemented; deferring to fixture"]
        )
