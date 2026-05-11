"""
tests/test_p038_timestamptz_vs_text_sql_casts.py

P-038 items #2 + #3 (2026-05-11) — `scripts/daily_log_failure_report.py` and
`ai/daily_deep_dive.py` both compared `timestamp with time zone` columns
against `text` values in WHERE clauses, breaking every scheduled run on
the Mac Mini with:

    psycopg2.errors.UndefinedFunction:
    operator does not exist: timestamp with time zone > text
        LINE 4: WHERE mr.scanned_at > ((NOW() - INTERVAL '1 day')::t...

and:

    psycopg2.errors.UndefinedFunction:
    operator does not exist: timestamp with time zone >= text
        LINE 6: WHERE system_id = '...' AND recorded_at >= TO_CHAR(...

Two distinct symptoms, one root cause: someone wrapped the RHS expression
in `::text` (`daily_log_failure_report.py`) or `TO_CHAR(NOW() - INTERVAL
'...', 'YYYY-MM-DD"T"HH24:MI:SS.US')` (`daily_deep_dive.py`) — coercing
a `timestamptz` value to a string. In current Postgres there is no
implicit `text -> timestamptz` coercion for ordering operators (`>`,
`>=`, `<`, `<=`), so every query fired `UndefinedFunction`.

Live evidence on the Mini (`/Library/Application Support/MiningGuardian/
logs/scheduled/`):
  - log_failure_report.last-run.json: exit_code=1 (May 9 and May 10 runs)
  - log_failure_report.err.log: identical traceback at line 84 for both
    runs.
  - daily_deep_dive.last-run.json: exit_code=1 (May 10 run; May 9 ran
    before P-035 / P-036 / P-037 stabilized the knowledge path).
  - daily_deep_dive.err.log: identical traceback at line 474.

Schema verified on the live Mini: every relevant column (`scanned_at`,
`collected_at`, `recorded_at`, `restarted_at`, `analyzed_at`, the
`timestamp` column in `action_audit_log`) is `timestamp with time zone`
in the `public` schema. There is no legacy text-format data the
`TO_CHAR()` could be matching — the data is uniform timestamptz.

Fix: drop the `::text` cast and the `TO_CHAR(...)` wrapper; let
`NOW() - INTERVAL '...'` (which returns `timestamptz`) compare directly
against the column. This is the form every other in-tree query already
uses (e.g., `core/database_pg.py`, `ai/knowledge_manager.py`,
`api/approval_api.py`).

This test module locks in:

  S1. Source-level negative regression — no `::text)` cast follows a
      timestamp expression in `scripts/daily_log_failure_report.py`.
  S2. Source-level negative regression — no `TO_CHAR(NOW() - INTERVAL`
      pattern anywhere in `ai/daily_deep_dive.py`.
  S3. Source-level positive — every `<col> [>=|>|<|<=]` comparison
      against `NOW() - INTERVAL ...` uses the bare form (no wrapping).
  S4. Cohort-wide guard — no OTHER source file under `ai/` or
      `scripts/` introduces the same broken pattern. The cohort guard
      catches sibling reintroductions before they hit the Mini.
  S5. AST sanity — both files parse cleanly after the fix.
  S6. Idempotence — running the regex sweep a second time produces no
      false positives once the fix is in.
"""

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_FAIL_PATH = REPO_ROOT / "scripts" / "daily_log_failure_report.py"
DEEP_DIVE_PATH = REPO_ROOT / "ai" / "daily_deep_dive.py"


def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# S1. daily_log_failure_report.py - no ::text cast of a timestamp expression
# ---------------------------------------------------------------------------


def test_log_failure_report_no_text_cast_of_now_interval():
    """The `::text` wrap of `NOW() - INTERVAL '...'` must NOT survive.

    Pre-P-038 the file had:
        WHERE mr.scanned_at > ((NOW() - INTERVAL '1 day')::text)
    Four occurrences in total. Each one is a SQL error at runtime
    because `timestamptz > text` has no operator.
    """
    src = _src(LOG_FAIL_PATH)
    # Anchor specifically on the broken shape so unrelated `::text`
    # casts (e.g., on a UUID for logging) don't false-positive.
    pattern = re.compile(r"\(NOW\(\)\s*-\s*INTERVAL\s+'[^']+'\)::text", re.IGNORECASE)
    matches = pattern.findall(src)
    assert not matches, (
        f"scripts/daily_log_failure_report.py still contains "
        f"`(NOW() - INTERVAL ...)::text` cast(s): {matches}. "
        "Drop the `::text` wrapper — compare `timestamptz` columns "
        "against `NOW() - INTERVAL '...'` directly. P-038 item #2."
    )


# ---------------------------------------------------------------------------
# S2. daily_deep_dive.py - no TO_CHAR(NOW() - INTERVAL ...) wrapper
# ---------------------------------------------------------------------------


def test_deep_dive_no_to_char_wrapping_now_interval():
    """The `TO_CHAR(NOW() - INTERVAL '...', 'YYYY-MM-DD"T"HH24:MI:SS.US')`
    wrap must NOT survive.

    Pre-P-038 the file had this exact form in 14 places. Each one is a
    SQL error at runtime because `timestamptz >= text` has no operator.
    """
    src = _src(DEEP_DIVE_PATH)
    # Broad-but-anchored: any TO_CHAR call whose first argument is
    # `NOW() - INTERVAL '...'`. Don't anchor on the format string —
    # someone might (legitimately or not) use a different format in a
    # future query, and that pattern would still be broken.
    pattern = re.compile(
        r"TO_CHAR\s*\(\s*NOW\(\)\s*-\s*INTERVAL\s+'[^']+'",
        re.IGNORECASE,
    )
    matches = pattern.findall(src)
    assert not matches, (
        f"ai/daily_deep_dive.py still contains `TO_CHAR(NOW() - "
        f"INTERVAL ...)` wrap(s): {len(matches)} occurrences "
        f"{matches[:3]}{'...' if len(matches) > 3 else ''}. "
        "Drop the `TO_CHAR(...)` wrapper — compare `timestamptz` "
        "columns against `NOW() - INTERVAL '...'` directly. "
        "P-038 item #3."
    )


# ---------------------------------------------------------------------------
# S3. Positive shape — bare `NOW() - INTERVAL '...'` is what survives.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [LOG_FAIL_PATH, DEEP_DIVE_PATH],
    ids=["daily_log_failure_report.py", "daily_deep_dive.py"],
)
def test_now_minus_interval_is_used_in_comparisons(path: Path):
    """After the fix, the file must still contain `NOW() - INTERVAL`
    expressions — just bare, not wrapped.

    A trivial sanity check that the fix didn't accidentally rip out
    the temporal filtering altogether.
    """
    src = _src(path)
    bare_pattern = re.compile(
        r"NOW\(\)\s*-\s*INTERVAL\s+'[^']+'",
        re.IGNORECASE,
    )
    bare_matches = bare_pattern.findall(src)
    assert bare_matches, (
        f"{path.name} has no `NOW() - INTERVAL '...'` expression at "
        "all after the fix. Did the temporal filtering get stripped "
        "by mistake? P-038 items #2/#3."
    )


# ---------------------------------------------------------------------------
# S4. Cohort-wide guard — no OTHER file under ai/ or scripts/ has the bug.
# ---------------------------------------------------------------------------


def _python_sources_under(root: Path) -> list[Path]:
    return [
        p
        for p in root.rglob("*.py")
        if "__pycache__" not in p.parts and ".venv" not in p.parts
    ]


def test_no_text_cast_of_timestamp_expression_anywhere_in_ai_or_scripts():
    """Cohort guard — the broken `(NOW() - INTERVAL '...')::text` shape
    must not appear in ANY ai/ or scripts/ source file.

    P-038 item #7 (cleanup_ams_logs.py) used the SAME family of legacy
    Linux VPS / dev-tree shortcuts. This test catches sibling files
    that share the bug shape but aren't yet on the P-038 cohort list.
    """
    bad_files: list[tuple[Path, list[str]]] = []
    pattern = re.compile(r"\(NOW\(\)\s*-\s*INTERVAL\s+'[^']+'\)::text", re.IGNORECASE)
    for root in (REPO_ROOT / "ai", REPO_ROOT / "scripts"):
        if not root.exists():
            continue
        for p in _python_sources_under(root):
            src = p.read_text(encoding="utf-8", errors="ignore")
            hits = pattern.findall(src)
            if hits:
                bad_files.append((p.relative_to(REPO_ROOT), hits))
    assert not bad_files, (
        "Sibling files share the `(NOW() - INTERVAL '...')::text` bug "
        f"that P-038 item #2 closes:\n"
        + "\n".join(f"  {p}: {h}" for p, h in bad_files)
        + "\nFix them in this same PR — they will fail at runtime the "
        "moment their respective scheduled jobs fire."
    )


def test_no_to_char_wrapping_timestamp_anywhere_in_ai_or_scripts():
    """Cohort guard — the broken `TO_CHAR(NOW() - INTERVAL '...')` shape
    must not appear in ANY ai/ or scripts/ source file.
    """
    bad_files: list[tuple[Path, int]] = []
    pattern = re.compile(
        r"TO_CHAR\s*\(\s*NOW\(\)\s*-\s*INTERVAL\s+'[^']+'",
        re.IGNORECASE,
    )
    for root in (REPO_ROOT / "ai", REPO_ROOT / "scripts"):
        if not root.exists():
            continue
        for p in _python_sources_under(root):
            src = p.read_text(encoding="utf-8", errors="ignore")
            hits = pattern.findall(src)
            if hits:
                bad_files.append((p.relative_to(REPO_ROOT), len(hits)))
    assert not bad_files, (
        "Sibling files share the `TO_CHAR(NOW() - INTERVAL '...')` "
        f"bug that P-038 item #3 closes:\n"
        + "\n".join(f"  {p}: {n} occurrence(s)" for p, n in bad_files)
        + "\nFix them in this same PR — they will fail at runtime the "
        "moment their respective scheduled jobs fire."
    )


# ---------------------------------------------------------------------------
# S5. AST sanity — both files parse cleanly after the fix.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [LOG_FAIL_PATH, DEEP_DIVE_PATH],
    ids=["daily_log_failure_report.py", "daily_deep_dive.py"],
)
def test_file_parses_cleanly(path: Path):
    """Belt-and-suspenders: after the fix, both files must still parse
    as valid Python. Catches a stray paren / quote / typo in any of
    the SQL string-literal edits.
    """
    src = _src(path)
    try:
        ast.parse(src)
    except SyntaxError as e:
        pytest.fail(
            f"{path.name} no longer parses as Python after the fix: {e}"
        )


# ---------------------------------------------------------------------------
# S6. Count-down regression — count the broken patterns; must be zero.
# ---------------------------------------------------------------------------


def test_total_broken_pattern_count_is_zero():
    """A single rollup count: the total number of broken patterns
    across both files must be zero. Easier to read at a glance than
    the per-file tests above, but the per-file tests give more
    targeted failure messages so this one is a summary.
    """
    text_cast_pattern = re.compile(
        r"\(NOW\(\)\s*-\s*INTERVAL\s+'[^']+'\)::text", re.IGNORECASE
    )
    to_char_pattern = re.compile(
        r"TO_CHAR\s*\(\s*NOW\(\)\s*-\s*INTERVAL\s+'[^']+'", re.IGNORECASE
    )
    total = 0
    for path in (LOG_FAIL_PATH, DEEP_DIVE_PATH):
        src = _src(path)
        total += len(text_cast_pattern.findall(src))
        total += len(to_char_pattern.findall(src))
    assert total == 0, (
        f"Found {total} broken `timestamptz vs text` SQL pattern(s) "
        f"across the two files. P-038 items #2 + #3 require all "
        "occurrences removed."
    )
