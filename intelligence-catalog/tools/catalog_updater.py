#!/usr/bin/env python3
"""
catalog_updater.py
Mining Guardian — Catalog Auto-Updater Tool

Standalone script to add or update miner models in the unified catalog.
Can be called by cron jobs, other scripts, or manually from CLI.

*** D-12 (locked 2026-04-27): Postgres-as-truth ***
This tool now writes EVERY change to Postgres FIRST (via the dual_writer
module) and then to unified_miner_index.json as a debug / git-tracked export.
The JSON file is no longer the source of truth — hardware.miner_models in
Postgres is. The Postgres write is best-effort; if it fails (Postgres down,
library missing, etc.) the JSON path proceeds and a warning is logged. This
lets us run the tool from environments without Postgres during the May 5
transition. After mid-May, this fail-soft policy will tighten.

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
import logging
import os
import sys
from copy import deepcopy
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

# C1 dual-write: every JSON change also lands in staging.miner_model_proposals.
# Import is wrapped so this module still runs in environments without
# psycopg2 or without the catalog repo on PYTHONPATH.
try:
    # Adjust path so "intelligence-catalog/db/dual_writer.py" is importable
    # whether this file is run as a script or imported as a module.
    _DB_DIR = Path(__file__).resolve().parent.parent / "db"
    if str(_DB_DIR.parent) not in sys.path:
        sys.path.insert(0, str(_DB_DIR.parent))
    # We import the module by file path because "intelligence-catalog" is not
    # a valid Python package name (the hyphen breaks `import` syntax).
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("_mg_dual_writer", _DB_DIR / "dual_writer.py")
    _dw_module = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
    _spec.loader.exec_module(_dw_module)        # type: ignore[union-attr]
    propose_miner_model = _dw_module.propose_miner_model  # type: ignore[attr-defined]
    _DUAL_WRITE_AVAILABLE = True
except Exception as _exc:
    propose_miner_model = None  # type: ignore[assignment]
    _DUAL_WRITE_AVAILABLE = False
    logging.getLogger("catalog_updater").debug(
        "dual_writer not loaded (%s); JSON-only mode", _exc
    )


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


def _dual_write_proposal(slug: str, payload: dict, *, op: str) -> None:
    """Best-effort dual-write into staging.miner_model_proposals (D-12).

    Never raises — a Postgres outage must NOT break the JSON path during the
    May 5 transition. The dual_writer module already swallows exceptions and
    logs warnings; we just check the feature flag and call.
    """
    if not _DUAL_WRITE_AVAILABLE or propose_miner_model is None:
        return
    try:
        propose_miner_model(
            slug=slug,
            payload=payload,
            source_tool="catalog_updater",
        )
    except Exception as exc:
        # Defense in depth — dual_writer already swallows but if a future
        # change leaks an exception we still don't want to break JSON writes.
        logging.getLogger("catalog_updater").warning(
            "dual-write %s for %s failed: %s", op, slug, exc
        )


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
        _dual_write_proposal(slug, index[slug], op="update")
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
    _dual_write_proposal(slug, entry, op="add")
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
    _dual_write_proposal(slug, index[slug], op="update")
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
    parser.add_argument(
        "--notify-api",
        metavar="URL",
        help="Hit the API hot-reload endpoint after changes (e.g. http://localhost:8590)",
    )
    parser.add_argument(
        "--sync-grafana",
        metavar="URL",
        help="Sync Grafana dropdown variable with current models (e.g. http://grafana.fieslerfamily.com)",
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

    # Notify API to hot-reload the catalog
    if args.notify_api:
        api_url = args.notify_api
        try:
            req = Request(f"{api_url}/api/catalog/reload", method="POST")
            resp = urlopen(req, timeout=10)
            result = json.loads(resp.read())
            messages.append(f"API reloaded: {result.get('old_count', '?')} → {result.get('new_count', '?')} models")
        except Exception as exc:
            messages.append(f"API reload failed: {exc}")

    # Sync Grafana variable with current model list
    if args.sync_grafana:
        msg = sync_grafana_variable(index, args.sync_grafana)
        messages.append(msg)

    # Print summary
    print(f"Catalog: {len(index)} models total")
    for msg in messages:
        print(f"  {msg}")

    return 0


def sync_grafana_variable(index: dict, grafana_url: str) -> str:
    """Update the Grafana Intelligence Report dashboard variable with current model list.
    
    Builds the Custom variable options from the catalog and pushes via Grafana API.
    """
    grafana_user = os.environ.get("GRAFANA_USER", "admin")
    grafana_pass = os.environ.get("GRAFANA_PASS", "temppass123")
    
    # Build sorted label:value pairs for Grafana Custom variable
    labels = []
    for slug, info in sorted(index.items()):
        if info is None:
            continue
        mfr = (info.get('manufacturer') or 'unknown').title()
        name = info.get('name') or slug.replace('-', ' ').title()
        specs = info.get('specs') or {}
        hr = specs.get('hashrate_ths')
        label = f"{mfr} {name}"
        if hr:
            label += f" ({hr} TH/s)"
        labels.append(f"{label} : {slug}")
    
    custom_options = ','.join(labels)
    
    # Find the Intelligence Report dashboard UID
    try:
        import base64
        auth = base64.b64encode(f"{grafana_user}:{grafana_pass}".encode()).decode()
        headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
        
        # Search for the dashboard
        req = Request(f"{grafana_url}/api/search?query=Intelligence%20Report", headers=headers)
        resp = urlopen(req, timeout=10)
        dashboards = json.loads(resp.read())
        
        intel_dash = None
        for d in dashboards:
            if 'Intelligence' in d.get('title', '') and 'Report' in d.get('title', ''):
                intel_dash = d
                break
        
        if not intel_dash:
            return "Grafana sync: Intelligence Report dashboard not found"
        
        uid = intel_dash['uid']
        
        # Get the full dashboard JSON
        req = Request(f"{grafana_url}/api/dashboards/uid/{uid}", headers=headers)
        resp = urlopen(req, timeout=10)
        dash_data = json.loads(resp.read())
        
        dashboard = dash_data['dashboard']
        
        # Find and update the miner_model variable
        templating = dashboard.get('templating', {}).get('list', [])
        updated = False
        for var in templating:
            if var.get('name') == 'miner_model':
                var['query'] = custom_options
                var['type'] = 'custom'
                # Rebuild options list
                var['options'] = []
                for pair in labels:
                    text, value = pair.rsplit(' : ', 1)
                    var['options'].append({'text': text.strip(), 'value': value.strip(), 'selected': False})
                if var['options']:
                    var['options'][0]['selected'] = True
                    var['current'] = {'text': var['options'][0]['text'], 'value': var['options'][0]['value']}
                updated = True
                break
        
        if not updated:
            return "Grafana sync: miner_model variable not found in dashboard"
        
        # Save the updated dashboard
        payload = json.dumps({
            'dashboard': dashboard,
            'folderId': dash_data.get('meta', {}).get('folderId', 0),
            'overwrite': True
        }).encode()
        
        req = Request(f"{grafana_url}/api/dashboards/db", data=payload, headers=headers, method="POST")
        resp = urlopen(req, timeout=10)
        result = json.loads(resp.read())
        
        return f"Grafana synced: {len(labels)} models in dropdown (version {result.get('version', '?')})"
        
    except Exception as exc:
        return f"Grafana sync failed: {exc}"


if __name__ == "__main__":
    sys.exit(main())
