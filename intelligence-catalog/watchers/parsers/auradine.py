#!/usr/bin/env python3
"""parsers/auradine.py — Auradine Teraflux parser (PR #20, 2026-04-27).

Bitcoin SHA-256 SKUs only. The Auradine catalog also ships AI-prefixed
Kaspa miners (e.g. AI3680, kHeavyHash); those are dropped at parse time
by the algorithm filter \u2014 the fixture intentionally includes one to
exercise that path.
"""
from __future__ import annotations

import logging
from pathlib import Path

from manufacturer_watcher import BaseParser, ParseResult  # type: ignore[import-not-found]

LOG = logging.getLogger(__name__)
_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "auradine_offline.json"


class Parser(BaseParser):
    BRAND = "auradine"
    DISPLAY_NAME = "Auradine"
    START_URLS = ["https://www.auradine.com/products"]
    OFFLINE_FIXTURE = _FIXTURE

    _ALLOWED_ALGOS = {"sha-256", "sha256", "bitcoin"}

    def fetch(self) -> ParseResult:
        if self.offline:
            return self._filtered(self._load_fixture())
        try:
            online = self._fetch_online()
            if online.models:
                return self._filtered(online)
            LOG.info("auradine online parse returned 0 models, falling back to fixture")
        except Exception as exc:
            LOG.warning("auradine online parse failed (%s) — using fixture", exc)
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
            notes.append(f"auradine: dropped {len(dropped)} non-SHA-256 SKUs ({dropped})")
        return ParseResult(models=kept, extra_aliases=result.extra_aliases, notes=notes)

    def _fetch_online(self) -> ParseResult:
        try:
            import httpx  # noqa: F401
        except ImportError:
            raise RuntimeError("httpx not installed; cannot fetch online")
        return ParseResult(
            notes=["auradine online mode not yet implemented; deferring to fixture"]
        )
