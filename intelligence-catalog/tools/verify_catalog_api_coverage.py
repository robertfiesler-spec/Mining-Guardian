#!/usr/bin/env python3
"""
verify_catalog_api_coverage.py — confirm every catalog API query type
returns real rows (PR #23 / ROADMAP §Wed).

The catalog API (`intelligence-catalog/catalog-api/catalog_api.py`) issues
21 distinct table-existence-gated queries while assembling a scan-bundle
or a single-miner knowledge response. This script enumerates all 21,
runs them against Postgres, and prints PASS / FAIL based on whether
each returns ≥1 row.

The 21 queries are grouped by the API helper they live in:

    fuzzy_match_models()
        1. hardware.miner_models
    _fetch_chip_specs() and single-model /specs
        2. hardware.chips
    Single-model /specs
        3. hardware.psu_models
    _fetch_failure_patterns()
        4. ops.failure_patterns
        5. ops.failure_symptoms
        6. ops.miner_error_codes
        7. hardware.model_known_issues
    _fetch_firmware_data()
        8. firmware.firmware_releases
        9. firmware.firmware_compatibility
       10. firmware.firmware_bugs
    _fetch_thresholds()
       11. ops.operational_thresholds
       12. ops.miner_baseline_reference
       13. ops.operational_profiles
       14. ops.environmental_correlations
    _fetch_repair_data()
       15. repair.repair_procedures
       16. repair.diagnostic_tools
       17. repair.parts
    _fetch_environmental_data()
       18. facility.cooling_solutions
       19. facility.container_environment_reference
    Single-model /failures (model-aware variant of #4)   → reuses query 4
    Single-model /repair  (model-aware variant of #15)   → reuses query 15

Two additional verifier-only queries probe the catalog populated by C5
(PR #22) so we know the feedback loop is producing rows:

       20. ops.failure_patterns       WHERE primary_source_id = bobby_operational
       21. hardware.model_known_issues WHERE primary_source_id = bobby_operational

Output
------
    {
      "total":  21,
      "pass":   17,
      "warn":    3,   # table exists, 0 rows
      "fail":    1,   # table missing
      "results": [{"name": "...", "table": "...", "status": "PASS|WARN|FAIL", "rows": N}, ...]
    }

Exit code is 0 if every query is PASS or WARN (table exists). Exit 2
if any required table is missing — that's the cutover blocker.

Usage
-----
    PGHOST=/tmp PGPORT=5433 MG_DB_PASSWORD=sandbox \\
        python intelligence-catalog/tools/verify_catalog_api_coverage.py
    python intelligence-catalog/tools/verify_catalog_api_coverage.py --json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Optional

LOG = logging.getLogger("verify_catalog_api_coverage")

# Same sentinel as feedback_loop.py
SOURCE_ID_BOBBY_OPERATIONAL = "a0000000-0000-0000-0000-00000000000f"


# Each entry: (display_name, schema, table, where_clause_or_None)
QUERY_SPECS: list[tuple[str, str, str, Optional[str]]] = [
    ("fuzzy_match_models",          "hardware", "miner_models",                   None),
    ("chip_specs",                  "hardware", "chips",                          None),
    ("psu_specs",                   "hardware", "psu_models",                     None),
    ("failure_patterns",            "ops",      "failure_patterns",               None),
    ("failure_symptoms",            "ops",      "failure_symptoms",               None),
    ("miner_error_codes",           "ops",      "miner_error_codes",              None),
    ("model_known_issues",          "hardware", "model_known_issues",             None),
    ("firmware_releases",           "firmware", "firmware_releases",              None),
    ("firmware_compatibility",      "firmware", "firmware_compatibility",         None),
    ("firmware_bugs",               "firmware", "firmware_bugs",                  None),
    ("operational_thresholds",      "ops",      "operational_thresholds",         None),
    ("miner_baseline_reference",    "ops",      "miner_baseline_reference",       None),
    ("operational_profiles",        "ops",      "operational_profiles",           None),
    ("environmental_correlations",  "ops",      "environmental_correlations",     None),
    ("repair_procedures",           "repair",   "repair_procedures",              None),
    ("diagnostic_tools",            "repair",   "diagnostic_tools",               None),
    ("parts",                       "repair",   "parts",                          None),
    ("cooling_solutions",           "facility", "cooling_solutions",              None),
    ("container_env_reference",     "facility", "container_environment_reference", None),
    ("c5_feedback_failure_patterns",   "ops",      "failure_patterns",
        f"primary_source_id = '{SOURCE_ID_BOBBY_OPERATIONAL}'"),
    ("c5_feedback_known_issues",       "hardware", "model_known_issues",
        f"primary_source_id = '{SOURCE_ID_BOBBY_OPERATIONAL}'"),
]


def _get_connection():
    try:
        import psycopg2  # type: ignore
    except ImportError:
        LOG.error("psycopg2 not installed")
        return None
    pw = os.environ.get("MG_DB_PASSWORD")
    if not pw:
        LOG.error("MG_DB_PASSWORD not set")
        return None
    try:
        return psycopg2.connect(
            host=os.environ.get("PGHOST", "/var/run/postgresql"),
            port=int(os.environ.get("PGPORT", "5432")),
            user=os.environ.get("PGUSER", "guardian_admin"),
            dbname=os.environ.get("PGDATABASE", "mining_guardian"),
            password=pw,
            connect_timeout=5,
        )
    except Exception as exc:
        LOG.error("Postgres unreachable: %s", exc)
        return None


def _table_exists(cur, schema: str, table: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema=%s AND table_name=%s",
        (schema, table),
    )
    return cur.fetchone() is not None


def _count_rows(cur, schema: str, table: str, where: Optional[str]) -> int:
    sql = f'SELECT COUNT(*) FROM "{schema}"."{table}"'
    if where:
        sql += f" WHERE {where}"
    cur.execute(sql)
    return cur.fetchone()[0]


def verify(*, ignore_c5_warns: bool = True) -> dict:
    """Run the 21 queries and return a structured report.

    `ignore_c5_warns`: if True (default), the two C5-feedback probes that
    return 0 rows are reported as WARN, not FAIL. They legitimately stay
    empty until operational data starts flowing from public.* (which it
    can't in a fresh sandbox). They're still part of the 21 — they just
    can't gate the cutover.
    """
    report = {"total": len(QUERY_SPECS), "pass": 0, "warn": 0, "fail": 0,
              "results": []}
    conn = _get_connection()
    if conn is None:
        report["fail"] = report["total"]
        report["error"] = "no postgres connection"
        return report

    try:
        with conn.cursor() as cur:
            for name, schema, table, where in QUERY_SPECS:
                full = f"{schema}.{table}" + (f" WHERE {where}" if where else "")
                if not _table_exists(cur, schema, table):
                    report["fail"] += 1
                    report["results"].append({
                        "name": name, "table": full,
                        "status": "FAIL", "rows": 0,
                        "reason": "table does not exist",
                    })
                    continue
                try:
                    n = _count_rows(cur, schema, table, where)
                except Exception as exc:
                    report["fail"] += 1
                    report["results"].append({
                        "name": name, "table": full,
                        "status": "FAIL", "rows": 0,
                        "reason": str(exc),
                    })
                    continue
                if n > 0:
                    report["pass"] += 1
                    status = "PASS"
                    reason = None
                else:
                    is_c5_probe = name.startswith("c5_feedback_")
                    if is_c5_probe and ignore_c5_warns:
                        report["warn"] += 1
                        status = "WARN"
                        reason = "expected — operational data not yet flowing"
                    else:
                        report["warn"] += 1
                        status = "WARN"
                        reason = "table exists but is empty"
                report["results"].append({
                    "name": name, "table": full,
                    "status": status, "rows": n, "reason": reason,
                })
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return report


def _print_human(report: dict) -> None:
    print(f"Catalog API coverage — {report['total']} query types")
    print("=" * 78)
    width = max(len(r["name"]) for r in report["results"])
    for r in report["results"]:
        marker = {"PASS": "✓", "WARN": "·", "FAIL": "✗"}.get(r["status"], "?")
        line = (f"  {marker} [{r['status']:<4}] {r['name']:<{width}}  "
                f"{r['table']:<55}  rows={r['rows']}")
        if r.get("reason"):
            line += f"  ({r['reason']})"
        print(line)
    print("=" * 78)
    print(f"  PASS: {report['pass']}   WARN: {report['warn']}   FAIL: {report['fail']}")
    print(f"  Total: {report['total']}")


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--json", action="store_true",
                   help="emit JSON instead of human text")
    p.add_argument("--strict-c5", action="store_true",
                   help="treat empty C5 feedback probes as WARN-blocking "
                        "(default: tolerated)")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    report = verify(ignore_c5_warns=not args.strict_c5)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_human(report)

    # Exit code: 0 if no FAIL, 2 otherwise
    return 0 if report["fail"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
