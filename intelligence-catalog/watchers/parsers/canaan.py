#!/usr/bin/env python3
"""parsers/canaan.py — Canaan Avalon parser (PR #19, 2026-04-27).

Bitcoin SHA-256 SKUs only. Focuses on current-gen A14XX, A15, A16, and the
home-miner Avalon Q. Same offline-fixture / online-stub pattern as PR #16
Bitmain and PR #18 MicroBT.
"""
from __future__ import annotations

import logging
from pathlib import Path

from manufacturer_watcher import BaseParser, ParseResult  # type: ignore[import-not-found]

LOG = logging.getLogger(__name__)
_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "canaan_offline.json"


class Parser(BaseParser):
    BRAND = "canaan"
    DISPLAY_NAME = "Canaan"
    START_URLS = ["https://canaan.io/product"]
    OFFLINE_FIXTURE = _FIXTURE

    _ALLOWED_ALGOS = {"sha-256", "sha256", "bitcoin"}

    def fetch(self) -> ParseResult:
        if self.offline:
            return self._filtered(self._load_fixture())
        try:
            online = self._fetch_online()
            if online.models:
                return self._filtered(online)
            LOG.info("canaan online parse returned 0 models, falling back to fixture")
        except Exception as exc:
            LOG.warning("canaan online parse failed (%s) — using fixture", exc)
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
            notes.append(f"canaan: dropped {len(dropped)} non-SHA-256 SKUs ({dropped})")
        return ParseResult(models=kept, extra_aliases=result.extra_aliases, notes=notes)

    def _fetch_online(self) -> ParseResult:
        try:
            import httpx  # noqa: F401
        except ImportError:
            raise RuntimeError("httpx not installed; cannot fetch online")
        return ParseResult(
            notes=["canaan online mode not yet implemented; deferring to fixture"]
        )
