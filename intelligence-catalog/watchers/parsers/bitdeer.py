#!/usr/bin/env python3
"""parsers/bitdeer.py — Bitdeer SealMiner parser (PR #21, 2026-04-27).

Bitcoin SHA-256 SKUs only. Bitdeer's catalog is uniformly SHA-256 today
(no Kaspa/LTC SKUs shipped under the SealMiner line as of 2026-04-27),
so the algorithm filter is a defensive guard rather than a real-data
test path. The 12 fixture entries match the 12 SealMiner rows already
seeded in hardware.miner_models so PR #5 promotion can validate slug
and hashrate equality.
"""
from __future__ import annotations

import logging
from pathlib import Path

from manufacturer_watcher import BaseParser, ParseResult  # type: ignore[import-not-found]

LOG = logging.getLogger(__name__)
_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "bitdeer_offline.json"


class Parser(BaseParser):
    BRAND = "bitdeer"
    DISPLAY_NAME = "Bitdeer"
    START_URLS = ["https://www.bitdeer.com/products"]
    OFFLINE_FIXTURE = _FIXTURE

    _ALLOWED_ALGOS = {"sha-256", "sha256", "bitcoin"}

    def fetch(self) -> ParseResult:
        if self.offline:
            return self._filtered(self._load_fixture())
        try:
            online = self._fetch_online()
            if online.models:
                return self._filtered(online)
            LOG.info("bitdeer online parse returned 0 models, falling back to fixture")
        except Exception as exc:
            LOG.warning("bitdeer online parse failed (%s) — using fixture", exc)
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
            notes.append(f"bitdeer: dropped {len(dropped)} non-SHA-256 SKUs ({dropped})")
        return ParseResult(models=kept, extra_aliases=result.extra_aliases, notes=notes)

    def _fetch_online(self) -> ParseResult:
        try:
            import httpx  # noqa: F401
        except ImportError:
            raise RuntimeError("httpx not installed; cannot fetch online")
        return ParseResult(
            notes=["bitdeer online mode not yet implemented; deferring to fixture"]
        )
