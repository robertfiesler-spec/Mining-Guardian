"""
core/dt_format.py — Datetime formatting helper for display strings.
====================================================================

Provides `fmt_dt(value, length=16)` — formats a heterogeneous datetime-
or-string-or-None value into a fixed-length display string.

Why this exists (P-038 item #5, 2026-05-11):
    Legacy SQLite-era code (`ai/train_comprehensive.py`,
    `ai/local_llm_analyzer.py`, `ai/train_llm.py`, `ai/daily_deep_dive.py`,
    `scripts/verify_training_data.py`) did `row['col'][:16]` everywhere
    to truncate a timestamp string for display, expecting `row['col']`
    to be a `str`. The CR-5 / B-7 migrations (late April 2026) moved
    those columns to `timestamp with time zone`. psycopg2 returns
    `timestamptz` as a native `datetime.datetime` object, not a string,
    and `datetime[:16]` crashes:
        TypeError: 'datetime.datetime' object is not subscriptable

    Observed live on the Mini 2026-05-11:
        File ".../train_comprehensive.py", line 290, in build_miner_prompt
            f"Scans: {s.get('scan_count')} | Last seen: {s.get('last_seen', '')[:16]}",
        TypeError: 'datetime.datetime' object is not subscriptable
    Crashed `run_weekly` from `ai/weekly_train.py:38`, exit_code=1.

    This helper is the INVERSE of `core.hashrate_evaluation.
    _coerce_to_datetime` (B-32 P-021, 2026-05-08): instead of coercing
    a heterogeneous shape INTO a datetime, it formats a heterogeneous
    shape OUT to a fixed-length display string. Stays in `core/` for
    the same reason — it has no DB dependency (no psycopg2 import,
    no SQLAlchemy import) so any module can use it without dragging
    DB libraries into its import graph.

Acceptable input types and behaviour:
    - `datetime` (aware) → `value.isoformat(sep=" ")[:length]`.
       Default `length=16` → `"YYYY-MM-DD HH:MM"`.
    - `datetime` (naive) → same as aware. The tzinfo is dropped by
       the slice anyway at length=16; full ISO output stays consistent.
    - `str` → `value[:length]`. Existing-text-column rows (e.g.
       `log_metrics.log_timestamp` which IS `text` on the Mini)
       pass through unchanged.
    - `None` / empty string → `""`. Caller decides whether to render
       "Last seen: " with an empty value or skip the line entirely.
    - junk (int, list, dict, object()) → `""`. The scheduled job
       can't afford to crash on a single legacy-shaped row, so the
       helper never raises.

Never raises. Always returns a `str`.
"""

from datetime import datetime

__all__ = ["fmt_dt"]


def fmt_dt(value, length: int = 16) -> str:
    """Format `value` as a fixed-length display string.

    See module docstring for the full contract.

    Args:
        value: A `datetime`, a string, `None`, or anything else.
        length: The maximum length of the returned string. Defaults
            to 16 (the legacy `[:16]` convention for "YYYY-MM-DD HH:MM").

    Returns:
        A string of at most `length` characters. Never raises.
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        try:
            return value.isoformat(sep=" ")[:length]
        except Exception:
            return ""
    if isinstance(value, str):
        return value[:length]
    # Anything else — defensive fallback. Never crash a scheduled job
    # on a row shape we didn't anticipate.
    try:
        return str(value)[:length]
    except Exception:
        return ""
