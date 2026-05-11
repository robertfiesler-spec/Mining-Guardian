"""
tests/test_p038_datetime_slicing.py

P-038 item #5 part A (2026-05-11) — `weekly_training` (and 3 sibling files)
crash with `TypeError: 'datetime.datetime' object is not subscriptable`
because legacy SQLite-era code did `row['col'][:16]` to truncate a
timestamp string for display, expecting `row['col']` to be a `str`.

Live evidence on the Mini before writing the fix (`/Library/Application
Support/MiningGuardian/logs/scheduled/weekly_training.err.log`):

    File ".../train_comprehensive.py", line 290, in build_miner_prompt
        f"Scans: {s.get('scan_count')} | Last seen: {s.get('last_seen', '')[:16]}",
                                                     ~~~~~~~~~~~~~~~~~~~~~~^^^^^
    TypeError: 'datetime.datetime' object is not subscriptable

The `last_seen` column is `MAX(scanned_at)` aliased — `scanned_at` is
`timestamp with time zone` since the CR-5 / B-7 migrations (late
April 2026). psycopg2 returns `timestamptz` as a native
`datetime.datetime` object, not a string. The legacy `[:16]` slice
then crashes.

Schema verified live on the Mini's Postgres: every column the buggy
slicing operates on (`scanned_at` → `last_seen` alias, `recorded_at` →
ams_notifications, `timestamp` → action_audit_log, `collected_at` →
miner_logs, `restarted_at` → miner_restarts) is `timestamp with time
zone`. The `log_metrics.log_timestamp` column is `text` and so
`e['first'][:16]` against that column is NOT buggy — the cohort guard
test below confirms it stays in.

The fix introduces a tiny shared helper, `core.dt_format.fmt_dt(value,
length=16)`, that:
  - returns "" for None / empty / unusable input
  - returns `value.isoformat(sep=" ")[:length]` for datetime input
  - returns `str(value)[:length]` for str input (str passthrough)

This is the INVERSE of `core.hashrate_evaluation._coerce_to_datetime`
(B-32 P-021): instead of coercing a heterogeneous shape INTO a
datetime, it formats a heterogeneous shape OUT to a fixed-length
string for display.

All 4 affected files (`ai/train_comprehensive.py`,
`ai/local_llm_analyzer.py`, `ai/train_llm.py`,
`scripts/verify_training_data.py`) import `fmt_dt` and replace every
`row['<timestamptz_col>'][:N]` with `fmt_dt(row['<col>'], N)`.

Asserted by this test module:

  S1.  Helper exists and behaves correctly for: None, "", datetime
       (with tz), datetime (naive), iso string, partial iso string,
       arbitrary length parameter, non-datetime non-string input.
  S2.  Negative regression — no `[<column>][:N]` slice of a
       known-timestamptz column survives in any of the 4 fixed files.
  S3.  Positive — every 4 fixed file imports `fmt_dt` from
       `core.dt_format`.
  S4.  Cohort-wide guard — no other `.py` under `ai/` or `scripts/`
       has reintroduced the same broken pattern.
  S5.  AST sanity — all 4 fixed files parse cleanly.
  S6.  The `text`-typed `log_metrics.log_timestamp` slice on
       `train_comprehensive.py` line 367 (`e['first'][:16]`) IS still
       present after the fix — text columns slice fine and don't need
       the helper. (Sanity check that I didn't over-correct.)
"""

import ast
import importlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

FIXED_FILES = [
    REPO_ROOT / "ai" / "train_comprehensive.py",
    REPO_ROOT / "ai" / "local_llm_analyzer.py",
    REPO_ROOT / "ai" / "train_llm.py",
    REPO_ROOT / "ai" / "daily_deep_dive.py",
    REPO_ROOT / "scripts" / "verify_training_data.py",
]

TIMESTAMPTZ_COLUMN_NAMES = [
    "last_seen",
    "scanned_at",
    "collected_at",
    "recorded_at",
    "restarted_at",
    "analyzed_at",
    "restart_time",
    # action_audit_log.timestamp is timestamptz too — match by exact
    # column name in the slicing context.
    "timestamp",
]


def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# S1. core.dt_format.fmt_dt behaviour.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fmt_dt():
    """Import the helper without dragging in psycopg2 — the helper has
    no DB dependency and must stay that way."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    mod = importlib.import_module("core.dt_format")
    return mod.fmt_dt


def test_fmt_dt_returns_empty_for_none(fmt_dt):
    assert fmt_dt(None) == ""


def test_fmt_dt_returns_empty_for_empty_string(fmt_dt):
    assert fmt_dt("") == ""


def test_fmt_dt_formats_aware_datetime(fmt_dt):
    """The live bug shape: psycopg2 hands back a tz-aware datetime."""
    dt = datetime(2026, 5, 11, 17, 33, 54, tzinfo=timezone.utc)
    assert fmt_dt(dt) == "2026-05-11 17:33"  # length 16 default


def test_fmt_dt_formats_naive_datetime(fmt_dt):
    """For completeness — some legacy SQLite-era rows are naive."""
    dt = datetime(2026, 5, 11, 17, 33, 54)
    assert fmt_dt(dt) == "2026-05-11 17:33"


def test_fmt_dt_passes_through_str(fmt_dt):
    """Existing str rows (e.g. log_metrics.log_timestamp = text)
    must still slice correctly without the helper raising."""
    assert fmt_dt("2026-05-11T17:33:54.000Z") == "2026-05-11T17:33"


def test_fmt_dt_honors_length(fmt_dt):
    """Some sites slice to 10 (date only); the helper must accept
    arbitrary lengths."""
    dt = datetime(2026, 5, 11, 17, 33, 54, tzinfo=timezone.utc)
    assert fmt_dt(dt, length=10) == "2026-05-11"


def test_fmt_dt_never_raises_on_unusable_input(fmt_dt):
    """Never crash on a row Claude can't afford to fail on — the
    scheduled job will continue with an empty timestamp display
    rather than tank the whole run."""
    for junk in (123, 4.5, [], {}, set(), object()):
        # `fmt_dt` must return a string (possibly empty), not raise.
        result = fmt_dt(junk)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# S2 / S3. negative regression + positive import check on every fixed file.
# ---------------------------------------------------------------------------


_BAD_SLICE_PATTERN = re.compile(
    r"\[\s*['\"](?:"
    + "|".join(re.escape(c) for c in TIMESTAMPTZ_COLUMN_NAMES)
    + r")['\"]\s*\]\s*\[\s*:\s*\d+\s*\]"
)


@pytest.mark.parametrize("path", FIXED_FILES, ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_no_timestamptz_column_slice_survives(path: Path):
    """Pre-P-038-#5 the file had `row['<timestamptz_col>'][:N]` slices
    that crashed at runtime once the column was migrated to
    timestamptz. After the fix, no such slice should remain."""
    src = _src(path)
    hits = _BAD_SLICE_PATTERN.findall(src)
    assert not hits, (
        f"{path.relative_to(REPO_ROOT)} still contains "
        f"`row['<timestamptz_col>'][:N]` slices: {hits}. "
        "Replace with `fmt_dt(row['<col>'], N)` from core.dt_format. "
        "P-038 item #5."
    )


@pytest.mark.parametrize("path", FIXED_FILES, ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_imports_fmt_dt(path: Path):
    """Every fixed file must import `fmt_dt`.

    Two valid forms are accepted:
      - `from core.dt_format import fmt_dt` (when the file's import
        graph has `_ROOT` on sys.path — the canonical full-path form).
      - `from dt_format import fmt_dt` (when the file's import graph
        has `_ROOT / "core"` on sys.path — matches the existing
        `from llm_analyzer import LLMAnalyzer` convention in
        `train_comprehensive.py` and `train_llm.py`).
    """
    src = _src(path)
    full_form = re.search(
        r"from\s+core\.dt_format\s+import\s+(?:fmt_dt|.*\bfmt_dt\b)",
        src,
    )
    short_form = re.search(
        r"from\s+dt_format\s+import\s+(?:fmt_dt|.*\bfmt_dt\b)",
        src,
    )
    assert full_form or short_form, (
        f"{path.relative_to(REPO_ROOT)} does not import `fmt_dt`. "
        "P-038 item #5 fix requires either "
        "`from core.dt_format import fmt_dt` or "
        "`from dt_format import fmt_dt` (matching the file's existing "
        "sys.path convention)."
    )


# ---------------------------------------------------------------------------
# S4. cohort-wide guard — no other ai/ or scripts/ file has the pattern.
# ---------------------------------------------------------------------------


def _python_sources_under(root: Path) -> list[Path]:
    return [
        p
        for p in root.rglob("*.py")
        if "__pycache__" not in p.parts and ".venv" not in p.parts
    ]


def test_no_timestamptz_slice_anywhere_in_ai_or_scripts():
    """Cohort guard — the broken `row['<timestamptz_col>'][:N]` shape
    must not appear in any `.py` under `ai/` or `scripts/`."""
    bad_files: list[tuple[Path, list[str]]] = []
    for root in (REPO_ROOT / "ai", REPO_ROOT / "scripts"):
        if not root.exists():
            continue
        for p in _python_sources_under(root):
            src = p.read_text(encoding="utf-8", errors="ignore")
            hits = _BAD_SLICE_PATTERN.findall(src)
            if hits:
                bad_files.append((p.relative_to(REPO_ROOT), hits))
    assert not bad_files, (
        "Sibling files share the `row['<timestamptz_col>'][:N]` bug:\n"
        + "\n".join(f"  {p}: {h}" for p, h in bad_files)
        + "\nReplace with `fmt_dt(...)` in the same PR — they will "
        "crash at runtime the moment their respective scheduled jobs "
        "fire."
    )


# ---------------------------------------------------------------------------
# S5. AST sanity — all 4 fixed files parse cleanly.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", FIXED_FILES, ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_file_parses_cleanly(path: Path):
    src = _src(path)
    try:
        ast.parse(src)
    except SyntaxError as e:
        pytest.fail(f"{path.relative_to(REPO_ROOT)} no longer parses as Python: {e}")


# ---------------------------------------------------------------------------
# S6. text-typed column slices stay — log_metrics.log_timestamp is text.
# ---------------------------------------------------------------------------


def test_text_typed_log_timestamp_slice_still_present():
    """`ai/train_comprehensive.py` builds chain-event display lines
    from `log_metrics.log_timestamp` which IS `text` in the DB (not
    timestamptz). Those slices should NOT be replaced — psycopg2
    returns them as strings already, and the helper would be
    unnecessary overhead. This test guards against over-correction.

    Verified live on the Mini's Postgres on 2026-05-11:
        log_metrics.log_timestamp | text
    """
    src = _src(REPO_ROOT / "ai" / "train_comprehensive.py")
    # The `e['first'][:16]` line was line 367 pre-fix. After the fix
    # it stays — log_timestamp is a text column so the slice works.
    assert re.search(
        r"e\[['\"]first['\"]\]\s*\[\s*:\s*16\s*\]",
        src,
    ), (
        "ai/train_comprehensive.py no longer slices "
        "`e['first'][:16]`. That column comes from "
        "`log_metrics.log_timestamp` which is `text` on the Mini — "
        "the slice is correct and should not have been replaced. "
        "Over-correction sanity check failed."
    )
