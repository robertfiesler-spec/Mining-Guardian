#!/usr/bin/env python3
"""
rebuild_unified_index.py
========================

Rebuilds intelligence-catalog/data/unified_miner_index.json from:
  • The current unified_miner_index.json (preserves rich enrichment + corrections)
  • The full seed CSV (intelligence-catalog/seed-data/all_bitcoin_sha256_miners.csv)
    so any miner present in the seed but missing from the index gets a
    skeleton entry created from seed-CSV columns.

Why
---
The seed catalog has 313 SHA-256 miner variants (250 model families).
The unified_miner_index.json on disk has only 247 family-level entries.
That means up to 66 cataloged variants — and 37 cataloged families —
are invisible to the Intelligence Report API and its "pick a miner"
dropdown.

This script does NOT delete any existing entry, does NOT modify any
existing entry's enrichment, and does NOT change slug formats for
entries that are already in the index. It only ADDS new skeleton
entries for variants that have no corresponding index slot.

Slug format
-----------
For new entries, the slug is generated from manufacturer + canonical_name
using the rule:
  lower-case → replace spaces and underscores with "-" → strip non-
  alphanumeric except "-" → collapse "--" → strip leading/trailing "-".

To avoid duplicating existing keys, each candidate slug is checked
against the existing index. If the family root (e.g., "antminer-t21")
already has a rich entry, we do NOT add per-variant slugs that would
collapse onto it. The rich entry already represents the family.

Output
------
Writes the rebuilt index to:
    intelligence-catalog/data/unified_miner_index.json

Prints a summary:
  • before count
  • after count
  • added count + sample new slugs
  • skipped count + sample skipped (because family already represented)

Run
---
    python3 intelligence-catalog/seed-data/rebuild_unified_index.py

Idempotent — running it twice produces the same output.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INDEX_PATH = REPO / "intelligence-catalog" / "data" / "unified_miner_index.json"
SEED_CSV = REPO / "intelligence-catalog" / "seed-data" / "all_bitcoin_sha256_miners.csv"


def slugify(text: str) -> str:
    """Slug rule used for NEW entries only — never re-keys existing ones."""
    s = text.lower().strip()
    s = s.replace("—", "-").replace("–", "-")
    s = re.sub(r"[^\w\s\-+.]", "", s)
    s = s.replace(".", "").replace("+", "plus")
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def family_slug(manufacturer: str, canonical_name: str) -> str:
    """Slug for the model family (strip trailing variant qualifier in parens)."""
    base = re.sub(r"\s*\([^)]*\)\s*$", "", canonical_name).strip()
    # Most existing keys drop the manufacturer word for Bitmain/MicroBT
    # because canonical names already start with "Antminer"/"Whatsminer".
    return slugify(base)


def variant_slug(manufacturer: str, canonical_name: str) -> str:
    """Slug for a specific variant including hashrate qualifier."""
    return slugify(canonical_name)


def parse_int(v: str) -> int | None:
    if not v or v.strip() == "":
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def parse_float(v: str) -> float | None:
    if not v or v.strip() == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def parse_bool(v: str) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes", "y")


def build_skeleton_entry(seed_row: dict) -> dict:
    """Build a minimal-style index entry from a seed CSV row.

    Mirrors the existing minimal entries (e.g., antminer-s23e-u2h)
    that have only manufacturer / name / specs. No fabricated enrichment.
    """
    specs: dict = {}

    hashrate = parse_float(seed_row.get("stock_hashrate_th", ""))
    if hashrate is not None:
        specs["hashrate_ths"] = hashrate

    power = parse_int(seed_row.get("stock_power_w", ""))
    if power is not None:
        specs["power_watts"] = power

    eff = parse_float(seed_row.get("stock_efficiency_j_th", ""))
    if eff is not None:
        specs["efficiency_jth"] = eff

    cooling = seed_row.get("cooling_type", "").strip()
    if cooling:
        specs["cooling"] = cooling

    # All seed rows are SHA-256 by repo policy
    specs["algorithm"] = "SHA-256"

    asic_chip = seed_row.get("asic_chip", "").strip()
    if asic_chip and asic_chip.upper() not in ("UNKNOWN", "N/A", ""):
        specs["asic_chip"] = asic_chip

    process_node = seed_row.get("process_node", "").strip()
    if process_node:
        specs["process_node"] = process_node

    release_date = seed_row.get("release_date", "").strip()
    if release_date:
        specs["release_date"] = release_date

    hashboards = parse_int(seed_row.get("hashboard_count", ""))
    if hashboards is not None:
        specs["hashboard_count"] = hashboards

    is_current = parse_bool(seed_row.get("is_current_product", ""))
    specs["is_current_product"] = is_current

    entry = {
        "manufacturer": seed_row.get("manufacturer", "").strip().lower(),
        "name": seed_row.get("canonical_name", "").strip(),
        "specs": specs,
    }
    notes = seed_row.get("notes", "").strip()
    if notes:
        entry["notes"] = notes

    sources = seed_row.get("source_urls", "").strip()
    if sources:
        entry["source_urls"] = sources

    return entry


def main() -> int:
    if not INDEX_PATH.exists():
        print(f"FATAL: {INDEX_PATH} does not exist")
        return 1
    if not SEED_CSV.exists():
        print(f"FATAL: {SEED_CSV} does not exist")
        return 1

    with INDEX_PATH.open() as f:
        index = json.load(f)
    before_count = len(index)

    with SEED_CSV.open() as f:
        seed_rows = list(csv.DictReader(f))

    # Build candidate slug -> seed row mapping.
    # For each seed row, decide: does this row already have an index entry?
    # We check both the variant-level slug AND the family-level slug.
    added: list[tuple[str, str]] = []  # (slug, display)
    skipped_existing_family: list[tuple[str, str]] = []  # (variant_slug, why)
    skipped_existing_variant: list[str] = []

    existing_keys = set(index.keys())

    for row in seed_rows:
        if not row.get("manufacturer") or not row.get("canonical_name"):
            continue

        v_slug = variant_slug(row["manufacturer"], row["canonical_name"])
        f_slug = family_slug(row["manufacturer"], row["canonical_name"])

        # Already present at variant-level slug
        if v_slug in existing_keys:
            skipped_existing_variant.append(v_slug)
            continue

        # Family root already represented — don't proliferate variants
        # under a family that has a rich enrichment entry. The rich
        # family entry stays the canonical "pick this miner" choice in
        # the dropdown.
        if f_slug != v_slug and f_slug in existing_keys:
            skipped_existing_family.append((v_slug, f_slug))
            continue

        # Add new entry
        entry = build_skeleton_entry(row)
        index[v_slug] = entry
        existing_keys.add(v_slug)
        added.append((v_slug, row["canonical_name"]))

    # Write atomically
    with INDEX_PATH.open("w") as f:
        json.dump(index, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")

    after_count = len(index)

    # Summary
    print(f"Seed CSV rows:                   {len(seed_rows)}")
    print(f"Index entries (before):          {before_count}")
    print(f"Index entries (after):           {after_count}")
    print(f"New skeleton entries added:      {len(added)}")
    print(f"Skipped (variant already in idx):  {len(skipped_existing_variant)}")
    print(f"Skipped (family already in idx):   {len(skipped_existing_family)}")
    print()
    if added:
        print("First 10 newly-added slugs:")
        for slug, name in added[:10]:
            print(f"  + {slug}  ({name})")
    if skipped_existing_family:
        print()
        print("First 10 family-collision skips (variant -> family):")
        for v, fam in skipped_existing_family[:10]:
            print(f"  - {v}  ->  family {fam} already in index")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
