#!/usr/bin/env python3
"""
catalog_updater.py
Mining Guardian — Catalog Auto-Updater Tool

Standalone script to add or update miner models in the unified catalog.
Can be called by cron jobs, other scripts, or manually from CLI.

Usage:
  python catalog_updater.py --add-model '{"slug": "antminer-s25", "manufacturer": "bitmain", ...}'
  python catalog_updater.py --update-model antminer-s21 '{"specs": {"current_street_price_usd": 3500}}'
  python catalog_updater.py --add-from-csv /path/to/enrichment_results.csv
  python catalog_updater.py --regenerate-known-models

Importable as a module:
  from catalog_updater import add_model, update_model, add_from_csv, deep_merge
"""

import argparse
import csv
import json
import sys
from copy import deepcopy
from pathlib import Path


# ── Paths ────────────────────────────────────────────────────────
TOOLS_DIR = Path(__file__).resolve().parent
CATALOG_DIR = TOOLS_DIR.parent
DATA_DIR = CATALOG_DIR / "data"
REPO_DIR = CATALOG_DIR.parent
INDEX_JSON = DATA_DIR / "unified_miner_index.json"
KNOWN_MODELS_TXT = REPO_DIR / "catalog_known_models.txt"


# ── Core helpers ─────────────────────────────────────────────────

def load_index() -> dict:
    """Load the unified miner index from disk."""
    if INDEX_JSON.exists():
        with open(INDEX_JSON) as f:
            return json.load(f)
    return {}


def save_index(index: dict) -> None:
    """Write the unified miner index back to disk."""
    with open(INDEX_JSON, "w") as f:
        json.dump(index, f, indent=2)
        f.write("\n")


def deep_merge(base: dict, update: dict) -> dict:
    """Deep-merge *update* into *base*.

    Rules:
      - None / empty-string / "N/A" values in *update* are skipped (never overwrite real data).
      - Nested dicts are merged recursively.
      - Non-null scalars in *update* overwrite the corresponding key in *base*.

    Returns a new dict (does not mutate inputs).
    """
    result = deepcopy(base)
    for key, new_val in update.items():
        # Skip null / empty / placeholder values — never overwrite real data
        if new_val is None or new_val == "" or new_val == "N/A":
            continue

        existing = result.get(key)
        if isinstance(existing, dict) and isinstance(new_val, dict):
            result[key] = deep_merge(existing, new_val)
        else:
            result[key] = deepcopy(new_val)
    return result


def regenerate_known_models(index: dict) -> int:
    """Regenerate catalog_known_models.txt from current index.

    Returns the number of model slugs written.
    """
    slugs = sorted(index.keys())
    KNOWN_MODELS_TXT.write_text("\n".join(slugs) + "\n")
    return len(slugs)


# ── Public API (importable) ──────────────────────────────────────

def add_model(model_data: dict, index: dict | None = None) -> tuple[dict, str]:
    """Add a new model to the catalog.

    Args:
        model_data: dict with at least "slug" and "manufacturer".
        index: optional pre-loaded index (loads from disk if None).

    Returns:
        (updated_index, summary_message)
    """
    if index is None:
        index = load_index()

    slug = model_data.get("slug")
    if not slug:
        raise ValueError("Model data must include a 'slug' field")

    if slug in index:
        # Model exists — merge new data into it
        index[slug] = deep_merge(index[slug], {
            k: v for k, v in model_data.items() if k != "slug"
        })
        return index, f"Updated existing model: {slug}"

    # New model — build entry
    entry = {
        "manufacturer": model_data.get("manufacturer", "unknown"),
        "display_name": model_data.get("name") or model_data.get("display_name") or slug,
        "entity": "",
        "specs": model_data.get("specs", {}),
        "enrichment": model_data.get("enrichment", {}),
    }
    # Build entity string if not provided
    mfg = entry["manufacturer"]
    name = entry["display_name"]
    entry["entity"] = model_data.get("entity") or f"{mfg} {name}"

    # Merge any extra top-level keys
    for k, v in model_data.items():
        if k not in ("slug", "manufacturer", "name", "display_name", "entity", "specs", "enrichment"):
            entry[k] = v

    index[slug] = entry
    return index, f"Added new model: {slug}"


def update_model(slug: str, updates: dict, index: dict | None = None) -> tuple[dict, str]:
    """Update an existing model with new data (deep merge).

    Args:
        slug: the model slug to update.
        updates: dict of fields to merge in.
        index: optional pre-loaded index.

    Returns:
        (updated_index, summary_message)
    """
    if index is None:
        index = load_index()

    if slug not in index:
        raise ValueError(f"Model '{slug}' not found in catalog ({len(index)} models available)")

    index[slug] = deep_merge(index[slug], updates)
    return index, f"Updated model: {slug}"


def add_from_csv(csv_path: str, index: dict | None = None) -> tuple[dict, str]:
    """Bulk-add or update models from a CSV file.

    Expected CSV columns:
      - slug (required)
      - manufacturer, name/display_name, entity (optional top-level)
      - Any column starting with "specs." goes into specs dict
      - Any column starting with "enrichment." goes into enrichment dict
      - All other columns go into enrichment dict

    Returns:
        (updated_index, summary_message)
    """
    if index is None:
        index = load_index()

    csv_file = Path(csv_path)
    if not csv_file.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    added = 0
    updated = 0

    with open(csv_file) as f:
        for row in csv.DictReader(f):
            slug = row.get("slug", "").strip()
            if not slug:
                continue

            model_data = {"slug": slug}

            # Top-level fields
            for field in ("manufacturer", "name", "display_name", "entity"):
                val = row.get(field, "").strip()
                if val:
                    model_data[field] = val

            # Parse specs.* and enrichment.* prefixed columns
            specs = {}
            enrichment = {}
            for col, val in row.items():
                val = val.strip() if val else ""
                if not val or col in ("slug", "manufacturer", "name", "display_name", "entity"):
                    continue
                if col.startswith("specs."):
                    key = col[6:]
                    specs[key] = _coerce_value(val)
                elif col.startswith("enrichment."):
                    key = col[11:]
                    enrichment[key] = val
                else:
                    # Default: put into enrichment
                    enrichment[col] = val

            if specs:
                model_data["specs"] = specs
            if enrichment:
                model_data["enrichment"] = enrichment

            was_new = slug not in index
            index, _ = add_model(model_data, index)
            if was_new:
                added += 1
            else:
                updated += 1

    return index, f"CSV import: {added} added, {updated} updated from {csv_file.name}"


def _coerce_value(val: str):
    """Try to convert a string to int/float if it looks numeric."""
    if val.isdigit():
        return int(val)
    try:
        return float(val)
    except ValueError:
        return val


# ── CLI ──────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mining Guardian Catalog Updater — add/update miner models",
    )
    parser.add_argument(
        "--add-model",
        metavar="JSON",
        help='Add a model from JSON string: \'{"slug": "...", "manufacturer": "...", ...}\'',
    )
    parser.add_argument(
        "--update-model",
        nargs=2,
        metavar=("SLUG", "JSON"),
        help='Update a model: --update-model antminer-s21 \'{"specs": {...}}\'',
    )
    parser.add_argument(
        "--add-from-csv",
        metavar="PATH",
        help="Bulk-add/update models from a CSV file",
    )
    parser.add_argument(
        "--regenerate-known-models",
        action="store_true",
        help="Regenerate catalog_known_models.txt from current index",
    )

    args = parser.parse_args()

    if not any([args.add_model, args.update_model, args.add_from_csv, args.regenerate_known_models]):
        parser.print_help()
        return 1

    index = load_index()
    messages = []

    try:
        if args.add_model:
            model_data = json.loads(args.add_model)
            index, msg = add_model(model_data, index)
            messages.append(msg)

        if args.update_model:
            slug, json_str = args.update_model
            updates = json.loads(json_str)
            index, msg = update_model(slug, updates, index)
            messages.append(msg)

        if args.add_from_csv:
            index, msg = add_from_csv(args.add_from_csv, index)
            messages.append(msg)

        # Save updated index
        save_index(index)

        # Always regenerate known models after changes
        count = regenerate_known_models(index)
        messages.append(f"Wrote {count} slugs to {KNOWN_MODELS_TXT.name}")

        if args.regenerate_known_models and not any([args.add_model, args.update_model, args.add_from_csv]):
            count = regenerate_known_models(index)
            messages.append(f"Regenerated {KNOWN_MODELS_TXT.name} with {count} models")

    except (json.JSONDecodeError, ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # Print summary
    print(f"Catalog: {len(index)} models total")
    for msg in messages:
        print(f"  {msg}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
