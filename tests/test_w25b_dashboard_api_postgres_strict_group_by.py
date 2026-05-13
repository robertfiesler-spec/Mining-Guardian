"""
tests/test_w25b_dashboard_api_postgres_strict_group_by.py

W25b (2026-05-13) — Postgres-strict GROUP BY hardening for
fleet_board_stats.

Live evidence that motivated the fix (Mini, dashboard_api.err.log
right after the W25 bind fix unblocked the iframes):

    psycopg2.errors.GroupingError: column "miner_readings.model"
    must appear in the GROUP BY clause or be used in an aggregate
    function
    LINE 9: SELECT ip, model FROM miner_readings WHERE s...
                       ^
      File ".../api/dashboard_api.py", line 774, in fleet_board_stats
        rej_rows = conn.execute(\"\"\"
                   ^^^^^^^^^^^^^^^^

Root cause: two SQLite-isms in `fleet_board_stats`. Each query had
a subquery shaped `SELECT ip, model FROM miner_readings WHERE
scan_id=%s GROUP BY ip` (selects non-aggregated `model` while
grouping only by `ip`). SQLite is lenient — it picks an arbitrary
`model` per ip silently. Postgres is strict — every non-aggregated
column in SELECT must appear in GROUP BY (or be wrapped in an
aggregate). The same bug class also appeared in the outer queries:
`SELECT m.model ... GROUP BY p.ip` (and same for `c.ip`).

The Board Health dashboard iframe rendered HTTP 500 across all five
panels that depended on /fleet/board_stats — the last broken iframe
left over from W25. The /api/report and /ai/dashboard iframes were
fine because they didn't aggregate at all.

Fix design: use Postgres's `DISTINCT ON (ip)` shorthand in the
subqueries — semantically "exactly one row per ip" — and add
`m.model` to the outer GROUP BY clauses. Two-character-class delta,
preserves the original defensive intent, runs on Postgres without
the SQLite-ism.

Verified against the live DB before commit:
    WITH latest_scan AS (SELECT MAX(id) AS id FROM scans)
    SELECT p.ip, COALESCE(m.model, 'Unknown') as model, ...
    FROM pool_readings p
    LEFT JOIN (SELECT DISTINCT ON (ip) ip, model FROM miner_readings
               WHERE scan_id=(SELECT id FROM latest_scan) ORDER BY ip
              ) m ON p.ip = m.ip
    WHERE p.scan_id=(SELECT id FROM latest_scan)
    GROUP BY p.ip, m.model
    ORDER BY rej_rate DESC LIMIT 5;
returned 5 rows; top offender 192.168.188.86 with 4.8% rejection.

Asserted by this test module:

  S1. The bad subquery pattern `SELECT ip, model FROM
      miner_readings WHERE scan_id=%s GROUP BY ip` is gone from
      api/dashboard_api.py. (Regression guard.)
  S2. The `fleet_board_stats` function's rej_rows query uses
      `DISTINCT ON (ip)` in its subquery.
  S3. The `fleet_board_stats` function's hw_rows query uses
      `DISTINCT ON (ip)` in its subquery.
  S4. The outer GROUP BY clauses in `fleet_board_stats` include
      `m.model` so the selected COALESCE(m.model, ...) column is
      grouped.
  S5. Sibling-sweep guard (Failure Mode 9): no other SQL literal
      anywhere under api/ scripts/ ai/ core/ has the same bug class
      — a SELECT-then-GROUP-BY pattern that selects a non-aggregated
      column from `miner_readings` while grouping only by `ip`.

These tests run against the repo on the laptop, not the live
service. The live smoke (curl /fleet/board_stats and confirm HTTP
200 + rendered HTML) is captured in the PR description.
"""
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_API = REPO_ROOT / "api" / "dashboard_api.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# S1. The bad subquery pattern is gone from dashboard_api.py.
# ---------------------------------------------------------------------------

def test_S1_old_sqlite_subquery_pattern_is_gone():
    """The pre-W25b shape `SELECT ip, model FROM miner_readings
    WHERE scan_id=... GROUP BY ip` must not appear anywhere in
    dashboard_api.py. This is the direct regression guard for the
    bug class that produced the GroupingError."""
    src = _read(DASHBOARD_API)
    # Whitespace-tolerant match — catches reformat-only reintroductions.
    normalized = re.sub(r"\s+", " ", src)
    forbidden = re.compile(
        r"SELECT\s+ip\s*,\s*model\s+FROM\s+miner_readings\s+"
        r"WHERE\s+scan_id\s*=\s*%s\s+GROUP\s+BY\s+ip\b",
        re.IGNORECASE,
    )
    matches = forbidden.findall(normalized)
    assert not matches, (
        "api/dashboard_api.py still contains the SQLite-ism subquery "
        "`SELECT ip, model FROM miner_readings WHERE scan_id=%s GROUP "
        "BY ip` — Postgres rejects this with GroupingError because "
        "`model` is selected but not in GROUP BY. See module docstring "
        "of this test file for the live-Mini stack trace that "
        "motivated W25b."
    )


# ---------------------------------------------------------------------------
# S2 + S3. Both fleet_board_stats subqueries now use DISTINCT ON (ip).
# ---------------------------------------------------------------------------

def _extract_fleet_board_stats_source(src: str) -> str:
    """Return just the source of the fleet_board_stats function so
    sibling functions can't shadow assertions about this one."""
    # The function definition through the next `@app.get(` or `def `
    # at column 0 marks its end.
    pattern = re.compile(
        r"def\s+fleet_board_stats\s*\(.*?(?=^\@app\.get|\ndef\s)",
        re.DOTALL | re.MULTILINE,
    )
    m = pattern.search(src)
    assert m is not None, (
        "Could not locate `def fleet_board_stats(...)` in "
        "api/dashboard_api.py — has it been renamed or removed? "
        "W25b's whole point of existence is this function."
    )
    return m.group(0)


def test_S2_rej_rows_subquery_uses_distinct_on_ip():
    """The rej_rows query (joins pool_readings to miner_readings
    for model lookup) must use DISTINCT ON (ip) in its subquery."""
    src = _extract_fleet_board_stats_source(_read(DASHBOARD_API))
    # The rej_rows query is the first conn.execute in the function.
    # Look for the LEFT JOIN subquery shape we care about.
    pattern = re.compile(
        r"""(?xs)
        rej_rows\s*=\s*conn\.execute\s*\(\s*\"\"\"
        .*?LEFT\s+JOIN\s*\(\s*
        SELECT\s+DISTINCT\s+ON\s*\(\s*ip\s*\)\s+ip\s*,\s*model
        \s+FROM\s+miner_readings
        .*?\"\"\"
        """
    )
    assert pattern.search(src) is not None, (
        "rej_rows query in fleet_board_stats must use `SELECT "
        "DISTINCT ON (ip) ip, model FROM miner_readings` in its "
        "LEFT JOIN subquery — that's the Postgres-correct shape "
        "that preserves 'exactly one row per ip'."
    )


def test_S3_hw_rows_subquery_uses_distinct_on_ip():
    """The hw_rows query (joins chain_readings to miner_readings
    for model lookup) must use the same DISTINCT ON (ip) shape."""
    src = _extract_fleet_board_stats_source(_read(DASHBOARD_API))
    pattern = re.compile(
        r"""(?xs)
        hw_rows\s*=\s*conn\.execute\s*\(\s*\"\"\"
        .*?LEFT\s+JOIN\s*\(\s*
        SELECT\s+DISTINCT\s+ON\s*\(\s*ip\s*\)\s+ip\s*,\s*model
        \s+FROM\s+miner_readings
        .*?\"\"\"
        """
    )
    assert pattern.search(src) is not None, (
        "hw_rows query in fleet_board_stats must use `SELECT "
        "DISTINCT ON (ip) ip, model FROM miner_readings` in its "
        "LEFT JOIN subquery — same fix shape as rej_rows."
    )


# ---------------------------------------------------------------------------
# S4. Outer GROUP BY clauses include m.model.
# ---------------------------------------------------------------------------

def test_S4_outer_group_by_clauses_include_m_model():
    """The outer GROUP BY clauses must include `m.model` (not just
    `p.ip` / `c.ip`) because `COALESCE(m.model, 'Unknown')` appears
    in the SELECT list. Postgres rejects the otherwise-equivalent
    SQLite shape."""
    src = _extract_fleet_board_stats_source(_read(DASHBOARD_API))
    # Both outer queries: one groups by `p.ip, m.model`, the other
    # by `c.ip, m.model`. Require both to be present.
    p_group_pattern = re.compile(
        r"GROUP\s+BY\s+p\.ip\s*,\s*m\.model\b", re.IGNORECASE
    )
    c_group_pattern = re.compile(
        r"GROUP\s+BY\s+c\.ip\s*,\s*m\.model\b", re.IGNORECASE
    )
    assert p_group_pattern.search(src) is not None, (
        "rej_rows outer query must `GROUP BY p.ip, m.model` — "
        "`m.model` is in the SELECT list, so Postgres requires it "
        "in GROUP BY too."
    )
    assert c_group_pattern.search(src) is not None, (
        "hw_rows outer query must `GROUP BY c.ip, m.model` — "
        "same reason as the rej_rows case."
    )


# ---------------------------------------------------------------------------
# S5. Sibling-sweep guard (Failure Mode 9).
# ---------------------------------------------------------------------------

def test_S5_no_sibling_sqlite_ism_group_by_miner_readings_model():
    """Failure Mode 9 sweep: no SQL literal anywhere under api/ scripts/
    ai/ core/ should select non-aggregated `model` from
    miner_readings while grouping only by `ip`. If a sibling exists
    with the same bug pattern, this work item should expand to cover
    it rather than leaving a latent duplicate Postgres GroupingError.

    The pattern we sweep for is intentionally narrow — only
    `SELECT ip, model FROM miner_readings ... GROUP BY ip` (in
    that order, no aggregate around model). Wider SELECT lists
    (e.g. SELECT ip, model, COUNT(*)) are fine because the COUNT(*)
    is the aggregate Postgres needs."""
    candidate_dirs = [
        REPO_ROOT / "api",
        REPO_ROOT / "scripts",
        REPO_ROOT / "ai",
        REPO_ROOT / "core",
    ]
    forbidden = re.compile(
        # SELECT ip, model FROM miner_readings WHERE ... GROUP BY ip
        # — the specific shape that triggered the GroupingError.
        r"SELECT\s+ip\s*,\s*model\s+FROM\s+miner_readings"
        r"[^;]*?GROUP\s+BY\s+ip\b",
        re.IGNORECASE | re.DOTALL,
    )
    offenders = []
    for d in candidate_dirs:
        if not d.exists():
            continue
        for p in d.rglob("*.py"):
            sp = str(p)
            if any(skip in sp for skip in ("/build/", "/.venv", "/venv/", "/__pycache__/")):
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if forbidden.search(text):
                offenders.append(str(p.relative_to(REPO_ROOT)))
    assert not offenders, (
        "Sibling-sweep failure: the following file(s) still contain "
        "`SELECT ip, model FROM miner_readings ... GROUP BY ip` — "
        "the exact SQLite-ism that W25b fixes in fleet_board_stats. "
        "Either fold them into this PR (same bug class — fits Failure "
        "Mode 9 same-class-cohort rule) or open a sibling ticket and "
        "explicitly carve them out of this guard.\n  "
        + "\n  ".join(offenders)
    )
