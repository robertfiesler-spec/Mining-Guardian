#!/usr/bin/env python3
"""
Fix the miner-dropdown auto-expand bug on the Intelligence Report dashboard.

Bug: the template variable on dashboard `intelligence_report_001` is wired
as a hard-coded literal list ("custom" type) so new miners discovered by the
daily search runs never appear, and not all miners currently in the database
are visible.

Fix: rewrite that variable to a query-driven variable that re-runs on every
dashboard load. Auto-detects datasource type (postgres / prometheus / mysql)
from the existing dashboard config, so it does the right thing for whichever
backend the dashboard is wired against.

Behaviour:
  * Step 1 — INSPECT.  Connects to local Grafana, fetches the dashboard,
    prints every templating variable, datasource, and the panel datasources.
    Writes a backup of the dashboard JSON to /tmp/intelligence_report_001-BACKUP-<ts>.json.
    Makes NO changes.

  * Step 2 — DRY-RUN.  Re-runs detection, builds the corrected variable,
    prints a unified diff against the live JSON, exits.  Makes NO changes.

  * Step 3 — APPLY.   Same as DRY-RUN, then POSTs the new dashboard with
    overwrite=true and bumps the version.  Prints final state.

Each step is gated by a CLI flag.  Default with no flags is INSPECT.

Usage on the VPS (where Grafana runs at localhost:3000):

    cd ~/Documents/GitHub/Mining-Guardian   # or wherever the repo is checked out
    git pull --ff-only
    python3 scripts/fix_intelligence_dropdown.py            # INSPECT
    python3 scripts/fix_intelligence_dropdown.py --dry-run  # show the diff
    python3 scripts/fix_intelligence_dropdown.py --apply    # apply the fix

After --apply, hard-refresh the Grafana dashboard in your browser
(Cmd+Shift+R) to bust the in-memory cache.

This script is idempotent: re-running --apply on an already-fixed dashboard
is a no-op (it detects the variable is already query-driven and exits).
"""

from __future__ import annotations

import argparse
import base64
import copy
import datetime as dt
import difflib
import json
import os
import sys
import urllib.request
import urllib.error

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
GRAFANA = os.environ.get("GRAFANA_URL", "http://localhost:3000")
DASHBOARD_UID = "intelligence_report_001"
VARIABLE_NAME_CANDIDATES = ("miner", "serial", "miner_serial", "serial_number", "miner_id", "host", "hostname")
TIMEOUT = 15

# Auth precedence:
#   1. GRAFANA_API_KEY env var (preferred — service-account token)
#   2. GRAFANA_USER + GRAFANA_PASS env vars
#   3. Fallback to admin:002300rf (matches existing scripts/check_grafana_board2.py)
API_KEY = os.environ.get("GRAFANA_API_KEY", "").strip()
USER = os.environ.get("GRAFANA_USER", "admin").strip()
PASS = os.environ.get("GRAFANA_PASS", "002300rf").strip()


# -----------------------------------------------------------------------------
# HTTP helpers
# -----------------------------------------------------------------------------
def _auth_header() -> dict[str, str]:
    if API_KEY:
        return {"Authorization": f"Bearer {API_KEY}"}
    creds = base64.b64encode(f"{USER}:{PASS}".encode()).decode()
    return {"Authorization": f"Basic {creds}"}


def _get(path: str) -> dict:
    req = urllib.request.Request(f"{GRAFANA}{path}", headers=_auth_header())
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read())


def _post(path: str, payload: dict) -> dict:
    body = json.dumps(payload).encode()
    headers = _auth_header() | {"Content-Type": "application/json"}
    req = urllib.request.Request(
        f"{GRAFANA}{path}", data=body, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"POST failed [{e.code}]: {body}")


# -----------------------------------------------------------------------------
# Detection
# -----------------------------------------------------------------------------
def find_miner_var(templating_list: list[dict]) -> tuple[int, dict] | tuple[None, None]:
    """Return (index, variable) for the miner dropdown, or (None, None)."""
    # First pass — name match
    for i, v in enumerate(templating_list):
        name = (v.get("name") or "").lower()
        label = (v.get("label") or "").lower()
        if name in VARIABLE_NAME_CANDIDATES or any(c in label for c in VARIABLE_NAME_CANDIDATES):
            return i, v
    # Second pass — type=custom with miner-shaped values
    for i, v in enumerate(templating_list):
        if v.get("type") == "custom":
            opts = v.get("options", []) or []
            if opts:
                sample = (opts[0].get("value") or "").upper()
                if any(ch.isdigit() for ch in sample) and len(sample) >= 4:
                    return i, v
    return None, None


def detect_panel_datasource(dash: dict) -> dict | None:
    """Best-guess datasource the variable should query against."""
    # Prefer the most common panel datasource
    counts: dict[str, dict] = {}
    for p in dash.get("panels", []) or []:
        ds = p.get("datasource")
        if isinstance(ds, dict):
            key = f"{ds.get('type')}:{ds.get('uid')}"
            counts.setdefault(key, {"count": 0, "ds": ds})
            counts[key]["count"] += 1
    if not counts:
        return None
    best = max(counts.values(), key=lambda x: x["count"])
    return best["ds"]


def build_query_for(ds_type: str) -> tuple[str, str | dict]:
    """Return (label, query) appropriate for the datasource type."""
    if ds_type == "postgres":
        # Canonical miner readings table — use most-recent scan to filter
        # for currently-tracked miners.  miner_readings has columns
        # (miner_id, ip, model, scanned_at) per ai/predictive_eta.py:281.
        return (
            "Miner",
            (
                "SELECT DISTINCT miner_id AS \"__value\", "
                "COALESCE(NULLIF(ip, ''), miner_id) AS \"__text\" "
                "FROM miner_readings "
                "WHERE scanned_at > NOW() - INTERVAL '7 days' "
                "ORDER BY 2"
            ),
        )
    if ds_type in ("prometheus", "loki"):
        # Use label_values against the canonical fleet metric.  Fleet metrics
        # in this codebase carry a `miner` or `instance` label per
        # scripts/update_grafana_pool.py.
        return ("Miner", "label_values(mining_guardian_fleet_online, miner)")
    if ds_type == "mysql":
        return (
            "Miner",
            "SELECT DISTINCT miner_id AS __value, COALESCE(ip, miner_id) AS __text "
            "FROM miner_readings WHERE scanned_at > NOW() - INTERVAL 7 DAY ORDER BY __text",
        )
    raise SystemExit(f"Unsupported datasource type: {ds_type}")


def build_fixed_variable(old: dict, ds: dict) -> dict:
    """Build a fully-populated 'query' template variable.

    Preserves the variable's name and label.  Forces refresh=2 ('On Time
    Range Change'), multi=true, includeAll=true.
    """
    label, query = build_query_for(ds.get("type", ""))
    return {
        "name": old.get("name") or "miner",
        "label": old.get("label") or label,
        "type": "query",
        "datasource": ds,
        "query": query,
        "refresh": 2,
        "multi": True,
        "includeAll": True,
        "allValue": None,
        "sort": 1,  # alphabetical ascending
        "hide": old.get("hide", 0),
        "skipUrlSync": old.get("skipUrlSync", False),
        "definition": query if isinstance(query, str) else json.dumps(query),
        "options": [],
        "current": {"selected": False, "text": ["All"], "value": ["$__all"]},
    }


# -----------------------------------------------------------------------------
# Pretty printing
# -----------------------------------------------------------------------------
def print_inspect(dash: dict, var_idx: int | None, var: dict | None, ds: dict | None) -> None:
    print(f"Title:    {dash.get('title')}")
    print(f"UID:      {dash.get('uid')}")
    print(f"Schema:   v{dash.get('schemaVersion')}")
    print(f"Version:  {dash.get('version')}")
    print(f"Panels:   {len(dash.get('panels', []) or [])}")
    print()
    tlist = dash.get("templating", {}).get("list", []) or []
    print(f"Template variables ({len(tlist)}):")
    for i, t in enumerate(tlist):
        marker = " <-- TARGET" if i == var_idx else ""
        print(f"  [{i}] name={t.get('name')!r}  label={t.get('label')!r}  type={t.get('type')!r}{marker}")
        if t.get("type") == "custom":
            opts = t.get("options", []) or []
            print(f"        options ({len(opts)}): {[o.get('value') for o in opts[:8]]}{' ...' if len(opts) > 8 else ''}")
        if t.get("type") == "query":
            print(f"        query: {str(t.get('query'))[:200]}")
            print(f"        datasource: {t.get('datasource')}")
    print()
    print(f"Most-common panel datasource: {ds}")


def print_diff(before: dict, after: dict) -> None:
    a = json.dumps(before, indent=2, sort_keys=True).splitlines(keepends=True)
    b = json.dumps(after, indent=2, sort_keys=True).splitlines(keepends=True)
    sys.stdout.writelines(
        difflib.unified_diff(a, b, fromfile="variable.before", tofile="variable.after", n=3)
    )


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="show the diff but make no changes")
    ap.add_argument("--apply", action="store_true", help="apply the fix to Grafana")
    args = ap.parse_args()

    # Fetch the dashboard
    try:
        d = _get(f"/api/dashboards/uid/{DASHBOARD_UID}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"FAILED to fetch dashboard: HTTP {e.code}\n{body}", file=sys.stderr)
        return 2

    dash = d["dashboard"]

    # Backup
    ts = dt.datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = f"/tmp/{DASHBOARD_UID}-BACKUP-{ts}.json"
    with open(backup_path, "w") as f:
        json.dump(d, f, indent=2)
    print(f"Backup written: {backup_path}\n")

    # Find the miner variable
    tlist = dash.get("templating", {}).get("list", []) or []
    var_idx, var = find_miner_var(tlist)

    # Detect downstream datasource
    ds = detect_panel_datasource(dash)

    if not args.dry_run and not args.apply:
        # INSPECT mode
        print_inspect(dash, var_idx, var, ds)
        if var is None:
            print("\nWARNING: no miner-shaped template variable found.  Either "
                  "the dashboard has no dropdown, or the variable uses an "
                  "unexpected name.  Edit VARIABLE_NAME_CANDIDATES at the top "
                  "of this script and re-run.")
            return 1
        if var.get("type") == "query":
            print(f"\nVariable {var.get('name')!r} is ALREADY query-driven.  "
                  "Nothing to fix.")
            return 0
        print(f"\nVariable {var.get('name')!r} is type={var.get('type')!r}.  "
              "Re-run with --dry-run to preview the fix, or --apply to apply.")
        return 0

    # DRY-RUN / APPLY require we found something to fix
    if var is None or var_idx is None:
        print("ERROR: no miner-shaped template variable found.  See INSPECT output.", file=sys.stderr)
        return 2
    if var.get("type") == "query":
        print(f"Variable {var.get('name')!r} is already query-driven — no-op.")
        return 0
    if ds is None:
        print("ERROR: cannot detect panel datasource.  Aborting.", file=sys.stderr)
        return 2

    # Build the fixed variable
    new_var = build_fixed_variable(var, ds)

    print("DIFF (variable only):")
    print_diff(var, new_var)
    print()

    if not args.apply:
        print("(--dry-run mode — not applied.)")
        return 0

    # Apply
    new_dash = copy.deepcopy(dash)
    new_dash["templating"]["list"][var_idx] = new_var
    new_dash["version"] = dash.get("version", 1) + 1

    payload = {
        "dashboard": new_dash,
        "message": (
            "fix(grafana): make Intelligence Report miner dropdown query-driven "
            "(auto-expand on new miners, refresh=2, multi+all)"
        ),
        "overwrite": True,
        "folderUid": d.get("meta", {}).get("folderUid", ""),
    }
    resp = _post("/api/dashboards/db", payload)
    print(f"Applied.  Grafana response: {json.dumps(resp, indent=2)}")
    print(f"\nNew dashboard version: {new_dash['version']}")
    print("Hard-refresh the dashboard in your browser (Cmd+Shift+R) to see the change.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
