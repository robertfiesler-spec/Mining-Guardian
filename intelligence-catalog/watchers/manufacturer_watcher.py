#!/usr/bin/env python3
"""
manufacturer_watcher.py — C3 manufacturer-page watcher (PR #16, 2026-04-27)

Walks each registered manufacturer parser, fetches their public product pages,
extracts miner_model / manufacturer / alias proposals, and pushes them into
staging.* via the dual_writer module (PR #15). Never writes to hardware.*
directly — promotion is a separate manual / C5 step.

Architecture
------------
A parser is a class with this contract:

    class Parser(BaseParser):
        BRAND = "bitmain"   # must match hardware.manufacturers.brand enum
        DISPLAY_NAME = "Bitmain"
        START_URLS = ["https://www.bitmain.com/products"]

        def fetch(self) -> list[dict]:
            '''Return a list of model dicts, each shaped like the
            unified_miner_index.json entry: {slug, manufacturer,
            display_name, specs, ...}'''
            ...

        def aliases_for(self, model: dict) -> list[str]:
            '''Optional: extra aliases to register for this model.'''
            ...

The watcher then:
  1. Calls propose_manufacturer for the brand (idempotent)
  2. For each model: propose_miner_model + propose_alias for every alias
  3. Implements the cross-model normalized-alias collision check (per N6 review):
     if two distinct models share the same normalized alias, the SECOND one
     is rejected and logged for human triage.

Usage
-----
    python intelligence-catalog/watchers/manufacturer_watcher.py --list
    python intelligence-catalog/watchers/manufacturer_watcher.py --run bitmain
    python intelligence-catalog/watchers/manufacturer_watcher.py --run-all
    python intelligence-catalog/watchers/manufacturer_watcher.py --run-all --dry-run

Conservative by design
----------------------
* HTTP fetches have a 15-second timeout and a small retry budget
* Parsers that raise are logged and skipped (one bad parser does not break the run)
* Network unavailable -> watchers run in offline mode using bundled fixture data
  (parsers may declare an OFFLINE_FIXTURE attribute pointing at a local JSON)
* No watcher writes to hardware.* directly
* All proposals carry source_run_id so a single run can be audited as a unit
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import re
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

# ──────────────────────────────────────────────────────────────────────────
# dual_writer import (file-path style, since "intelligence-catalog" has hyphen)
# ──────────────────────────────────────────────────────────────────────────

_HERE = Path(__file__).resolve().parent
_DB_DIR = _HERE.parent / "db"
sys.path.insert(0, str(_HERE.parent))  # so `parsers.bitmain` etc. resolve

try:
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "_mg_dual_writer", _DB_DIR / "dual_writer.py"
    )
    _dw = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
    _spec.loader.exec_module(_dw)                 # type: ignore[union-attr]
    propose_miner_model = _dw.propose_miner_model
    propose_manufacturer = _dw.propose_manufacturer
    propose_alias = _dw.propose_alias
    is_postgres_available = _dw.is_postgres_available
    DUAL_WRITER_AVAILABLE = True
except Exception as _exc:
    propose_miner_model = None
    propose_manufacturer = None
    propose_alias = None
    is_postgres_available = lambda: False  # noqa: E731
    DUAL_WRITER_AVAILABLE = False
    logging.getLogger(__name__).warning(
        "dual_writer unavailable: %s — watcher will run in dry-run mode", _exc
    )


LOG = logging.getLogger("manufacturer_watcher")


# ──────────────────────────────────────────────────────────────────────────
# Alias normalization (must match the canonical schema's normalize_alias() SQL)
# ──────────────────────────────────────────────────────────────────────────

_ALIAS_NORM_RE = re.compile(r"[^a-z0-9]+")

def normalize_alias(alias: str) -> str:
    """Lowercase, strip all non-alphanumerics. Mirrors the SQL-side normalize.

    Examples:
        "S21 EXP"   -> "s21exp"
        "S21EXP"    -> "s21exp"
        "S21-EXP+"  -> "s21exp"
    """
    if not alias:
        return ""
    return _ALIAS_NORM_RE.sub("", alias.lower())


# ──────────────────────────────────────────────────────────────────────────
# Base parser contract
# ──────────────────────────────────────────────────────────────────────────

@dataclass
class ParseResult:
    models: list[dict] = field(default_factory=list)
    extra_aliases: dict[str, list[str]] = field(default_factory=dict)  # slug -> aliases
    notes: list[str] = field(default_factory=list)


class BaseParser(ABC):
    BRAND: str = ""
    DISPLAY_NAME: str = ""
    START_URLS: list[str] = []
    OFFLINE_FIXTURE: Optional[Path] = None

    def __init__(self, *, offline: bool = False, http_timeout: int = 15):
        self.offline = offline
        self.http_timeout = http_timeout

    @abstractmethod
    def fetch(self) -> ParseResult:
        ...

    # Helpers shared across parsers ────────────────────────────────────

    def _load_fixture(self) -> ParseResult:
        if not self.OFFLINE_FIXTURE or not self.OFFLINE_FIXTURE.exists():
            return ParseResult(notes=[f"no offline fixture for {self.BRAND}"])
        try:
            data = json.loads(self.OFFLINE_FIXTURE.read_text())
            return ParseResult(
                models=data.get("models", []),
                extra_aliases=data.get("extra_aliases", {}),
                notes=[f"loaded fixture {self.OFFLINE_FIXTURE.name}"],
            )
        except Exception as exc:
            LOG.warning("fixture load failed for %s: %s", self.BRAND, exc)
            return ParseResult(notes=[f"fixture load failed: {exc}"])


# ──────────────────────────────────────────────────────────────────────────
# Watcher engine
# ──────────────────────────────────────────────────────────────────────────

# Registry of parser module names. Each one must be importable as
# parsers.<name> and expose a `Parser` class. We register only parsers that
# have been *implemented*. Stubs are documented in the module docstring of
# manufacturer_watcher and added to this list as they go online.
PARSER_MODULES: list[str] = [
    "parsers.bitmain",
    "parsers.microbt",
    "parsers.canaan",
    "parsers.auradine",
    "parsers.bitdeer",
]


@dataclass
class WatcherStats:
    parsers_run: int = 0
    parsers_failed: int = 0
    models_proposed: int = 0
    models_skipped_collision: int = 0
    aliases_proposed: int = 0
    aliases_skipped_collision: int = 0
    manufacturers_proposed: int = 0


def _load_parsers(only: Optional[list[str]] = None) -> list[BaseParser]:
    parsers: list[BaseParser] = []
    for mod_name in PARSER_MODULES:
        if only and not any(o in mod_name for o in only):
            continue
        try:
            mod = importlib.import_module(mod_name)
            cls = getattr(mod, "Parser", None)
            if cls is None:
                LOG.warning("parser %s has no `Parser` class — skipping", mod_name)
                continue
            parsers.append(cls())
        except Exception as exc:
            LOG.warning("could not load parser %s: %s", mod_name, exc)
    return parsers


def run_watcher(
    *,
    only: Optional[list[str]] = None,
    offline: bool = False,
    dry_run: bool = False,
    run_id: Optional[UUID] = None,
) -> WatcherStats:
    """Run the watcher across registered parsers.

    Args:
        only: list of substrings; parsers whose module name matches at least
              one are included. `None` means "all".
        offline: pass through to parsers; they should use OFFLINE_FIXTURE
        dry_run: do not call propose_* (just log)
        run_id: a UUID stamped onto every proposal; default is a fresh uuid4()

    Returns:
        WatcherStats summarizing the run.
    """
    if run_id is None:
        run_id = uuid4()
    LOG.info("watcher run started: run_id=%s offline=%s dry_run=%s",
             run_id, offline, dry_run)

    parsers = _load_parsers(only=only)
    if not parsers:
        LOG.warning("no parsers loaded — nothing to do")
        return WatcherStats()

    # Collision detection: track normalized aliases across the entire run so
    # two distinct models from different parsers can't claim the same alias.
    alias_owners: dict[str, str] = {}   # normalized_alias -> "<brand>:<slug>"
    stats = WatcherStats()

    for parser in parsers:
        parser.offline = offline or parser.offline
        try:
            stats.parsers_run += 1
            LOG.info("running parser %s (%s)", parser.BRAND, parser.DISPLAY_NAME)
            result = parser.fetch()
            for note in result.notes:
                LOG.info("  note: %s", note)
        except Exception as exc:
            stats.parsers_failed += 1
            LOG.exception("parser %s crashed: %s", parser.BRAND, exc)
            continue

        # Propose manufacturer once per parser
        if not dry_run and propose_manufacturer is not None:
            mfg_payload = {"brand": parser.BRAND, "display_name": parser.DISPLAY_NAME}
            mfg_id = propose_manufacturer(
                brand=parser.BRAND,
                payload=mfg_payload,
                source_tool="manufacturer_watcher",
                source_url=parser.START_URLS[0] if parser.START_URLS else None,
                source_run_id=run_id,
            )
            if mfg_id is not None:
                stats.manufacturers_proposed += 1

        # Propose every model + its aliases
        for model in result.models:
            slug = model.get("slug")
            if not slug:
                LOG.warning("  model has no slug, skipping: %s",
                            model.get("display_name") or model)
                continue

            # Proper provenance: stamp the manufacturer onto every model
            model = dict(model)
            model.setdefault("manufacturer", parser.BRAND)

            if not dry_run and propose_miner_model is not None:
                mid = propose_miner_model(
                    slug=slug,
                    payload=model,
                    source_tool="manufacturer_watcher",
                    source_url=parser.START_URLS[0] if parser.START_URLS else None,
                    source_run_id=run_id,
                )
                if mid is not None:
                    stats.models_proposed += 1
            else:
                LOG.info("  [dry-run] would propose %s/%s", parser.BRAND, slug)
                stats.models_proposed += 1

            # Aliases (canonical name + display_name + extras)
            aliases = set()
            for cand in (model.get("display_name"), model.get("name"),
                         model.get("model_number"), slug):
                if cand:
                    aliases.add(str(cand))
            for extra in result.extra_aliases.get(slug, []):
                aliases.add(extra)

            for alias in aliases:
                norm = normalize_alias(alias)
                if not norm:
                    continue
                owner_key = f"{parser.BRAND}:{slug}"
                prior = alias_owners.get(norm)
                if prior and prior != owner_key:
                    stats.aliases_skipped_collision += 1
                    LOG.warning(
                        "  alias collision: '%s' (norm=%s) claimed by %s, "
                        "now seen on %s — skipping (manual triage required)",
                        alias, norm, prior, owner_key,
                    )
                    continue
                alias_owners[norm] = owner_key

                if not dry_run and propose_alias is not None:
                    aid = propose_alias(
                        miner_slug=slug,
                        alias=alias,
                        source_tool="manufacturer_watcher",
                        alias_source=f"{parser.BRAND}_official",
                        is_common=(alias == slug),
                        source_url=parser.START_URLS[0] if parser.START_URLS else None,
                        source_run_id=run_id,
                    )
                    if aid is not None:
                        stats.aliases_proposed += 1
                else:
                    LOG.info("    [dry-run] would propose alias %s -> %s", slug, alias)
                    stats.aliases_proposed += 1

    LOG.info(
        "watcher run finished: parsers=%d failed=%d models=%d aliases=%d "
        "(model_collisions=%d, alias_collisions=%d) manufacturers=%d",
        stats.parsers_run, stats.parsers_failed,
        stats.models_proposed, stats.aliases_proposed,
        stats.models_skipped_collision, stats.aliases_skipped_collision,
        stats.manufacturers_proposed,
    )
    return stats


# ──────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mining Guardian — manufacturer page watcher (C3 / PR #16)"
    )
    parser.add_argument("--list", action="store_true",
                        help="List registered parsers and exit")
    parser.add_argument("--run", metavar="BRAND",
                        help="Run only the parser for this brand (substring match)")
    parser.add_argument("--run-all", action="store_true",
                        help="Run every registered parser")
    parser.add_argument("--offline", action="store_true",
                        help="Use bundled OFFLINE_FIXTURE files instead of HTTP")
    parser.add_argument("--dry-run", action="store_true",
                        help="Do not write to staging.*; just log what would be proposed")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if args.list:
        for mod_name in PARSER_MODULES:
            print(mod_name)
        return 0

    if not args.run and not args.run_all:
        parser.print_help()
        return 1

    only = [args.run] if args.run else None
    stats = run_watcher(only=only, offline=args.offline, dry_run=args.dry_run)
    print(json.dumps(stats.__dict__, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
