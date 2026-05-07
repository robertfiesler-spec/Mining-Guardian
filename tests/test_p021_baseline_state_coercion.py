"""tests/test_p021_baseline_state_coercion.py

P-021-runtime-fix (2026-05-08) — regression guard for the scanner
TypeError that crashed every miner evaluation on the 2026-05-08
P-021-fix install:

    File "core/hashrate_evaluation.py", line 439, in record_sample
        start = datetime.fromisoformat(state["learning_start"])
    TypeError: fromisoformat: argument must be str

Root cause
----------
The schema disagrees with itself. `core/hashrate_evaluation.py:387`
declares `learning_start TEXT NOT NULL` (legacy SQLite shape) but is
`CREATE TABLE IF NOT EXISTS`, so on a real install the migration
`migrations/001_initial_schema.sql:151` wins — it declares
`TIMESTAMP WITH TIME ZONE NOT NULL`, and psycopg2 returns native
`datetime` objects for TIMESTAMPTZ columns. `state["learning_start"]`
was therefore a `datetime`, and the legacy `datetime.fromisoformat()`
crashed.

Fix
---
New `_coerce_to_datetime` helper in `core/hashrate_evaluation.py`
accepts datetime, ISO string (with or without trailing 'Z'), date,
or None/junk. Returns a UTC-aware datetime or `default` (None). Both
`record_sample` and `_lock_baseline` now route `learning_start`
through this helper. Invalid values log WARNING and skip the sample
rather than crash the scanner.

This test exercises the helper directly across every value type the
scanner has been observed to encounter (or could plausibly encounter
on a future psycopg2 driver upgrade).
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _import_helper():
    """Import `_coerce_to_datetime` without dragging in psycopg2 at
    module import time (the agent sandbox doesn't have it).
    """
    import importlib
    sys.modules.setdefault("psycopg2", mock.MagicMock())
    sys.modules.setdefault("psycopg2.extras", mock.MagicMock())
    mod = importlib.import_module("core.hashrate_evaluation")
    return mod._coerce_to_datetime


class TestCoerceToDatetime(unittest.TestCase):
    """Direct exercise of the coercion helper."""

    def setUp(self) -> None:
        self.coerce = _import_helper()

    # ---- datetime input ---------------------------------------------------

    def test_aware_datetime_passes_through(self) -> None:
        dt = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(self.coerce(dt), dt)

    def test_naive_datetime_gets_utc(self) -> None:
        dt = datetime(2026, 5, 8, 12, 0, 0)
        out = self.coerce(dt)
        self.assertIsNotNone(out)
        self.assertEqual(out.tzinfo, timezone.utc)
        # Same wall-clock time, just tagged UTC.
        self.assertEqual(out.replace(tzinfo=None), dt)

    def test_non_utc_aware_datetime_preserves_tz(self) -> None:
        # E.g. CDT (-05:00). Helper must NOT silently rewrite the offset.
        cdt = timezone(timedelta(hours=-5))
        dt = datetime(2026, 5, 8, 12, 0, 0, tzinfo=cdt)
        out = self.coerce(dt)
        self.assertEqual(out, dt)
        self.assertEqual(out.utcoffset(), timedelta(hours=-5))

    # ---- ISO-string input -------------------------------------------------

    def test_iso_string_with_tz(self) -> None:
        out = self.coerce("2026-05-08T12:00:00+00:00")
        self.assertEqual(out, datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc))

    def test_iso_string_with_z(self) -> None:
        # The 'Z' shorthand is what `datetime.now(timezone.utc).isoformat()`
        # NEVER produces, but is what `core.mining_guardian` does emit
        # via JSON helpers — accept it.
        out = self.coerce("2026-05-08T12:00:00Z")
        self.assertEqual(out, datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc))

    def test_iso_string_naive(self) -> None:
        # No tz — promote to UTC.
        out = self.coerce("2026-05-08T12:00:00")
        self.assertEqual(out, datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc))

    def test_iso_string_with_microseconds(self) -> None:
        out = self.coerce("2026-05-08T12:00:00.123456+00:00")
        self.assertEqual(
            out,
            datetime(2026, 5, 8, 12, 0, 0, 123456, tzinfo=timezone.utc),
        )

    # ---- date input -------------------------------------------------------

    def test_date_promoted_to_midnight_utc(self) -> None:
        out = self.coerce(date(2026, 5, 8))
        self.assertEqual(out, datetime(2026, 5, 8, 0, 0, 0, tzinfo=timezone.utc))

    # ---- junk / None ------------------------------------------------------

    def test_none_returns_default(self) -> None:
        self.assertIsNone(self.coerce(None))

    def test_none_returns_explicit_default(self) -> None:
        sentinel = datetime(2000, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(self.coerce(None, default=sentinel), sentinel)

    def test_empty_string_returns_default(self) -> None:
        self.assertIsNone(self.coerce(""))

    def test_whitespace_string_returns_default(self) -> None:
        self.assertIsNone(self.coerce("   "))

    def test_unparseable_string_returns_default_no_raise(self) -> None:
        # The helper must NEVER raise — the scanner can't afford to
        # crash on a single legacy-shaped row. Junk = None.
        self.assertIsNone(self.coerce("not-a-date"))
        self.assertIsNone(self.coerce("2026-13-99T99:99:99"))

    def test_int_returns_default_no_raise(self) -> None:
        # Some legacy code stored unix epochs as ints. We don't translate
        # them automatically (could be seconds or milliseconds) — return
        # None so the caller logs and skips.
        self.assertIsNone(self.coerce(1715184000))

    def test_dict_or_list_returns_default(self) -> None:
        self.assertIsNone(self.coerce({"learning_start": "2026-05-08"}))
        self.assertIsNone(self.coerce(["2026-05-08"]))


class TestRecordSampleHandlesDatetimeFromPostgres(unittest.TestCase):
    """End-to-end: BaselineManager.record_sample must NOT crash when
    `state["learning_start"]` is a `datetime` (the live psycopg2 case
    that broke the 2026-05-08 install).

    We patch `BaselineManager.get_state` to return a fake state with a
    datetime, plus stub `_connect()` so the UPDATE doesn't actually run.
    The original code blew up at `datetime.fromisoformat(<datetime>)`;
    the fixed code routes through `_coerce_to_datetime` and proceeds.
    """

    def setUp(self) -> None:
        # Need the module imported so we can patch its internals.
        import importlib
        sys.modules.setdefault("psycopg2", mock.MagicMock())
        sys.modules.setdefault("psycopg2.extras", mock.MagicMock())
        self.mod = importlib.import_module("core.hashrate_evaluation")

    def _make_manager(self):
        # Bypass __init__ — we don't need a real DSN or _ensure_table.
        mgr = self.mod.BaselineManager.__new__(self.mod.BaselineManager)
        mgr.db_path = "fake-dsn"
        mgr.learning_window_hrs = 72
        mgr.minimum_samples = 36
        mgr.tolerance_pct = 10.0
        mgr.notify_callback = None
        return mgr

    def _patch_connect(self, mgr):
        """Make `mgr._connect()` return a context manager whose
        `.execute()` is a no-op and `.commit()` is a no-op. The tests
        don't care about the SQL side-effect — only that record_sample
        doesn't TypeError on a datetime input.
        """
        cm = mock.MagicMock()
        cm.__enter__.return_value = cm
        cm.__exit__.return_value = False
        cm.execute = mock.MagicMock()
        cm.commit = mock.MagicMock()
        mgr._connect = mock.MagicMock(return_value=cm)
        return cm

    def test_datetime_state_does_not_crash(self) -> None:
        mgr = self._make_manager()
        self._patch_connect(mgr)
        learning_start_dt = datetime.now(timezone.utc) - timedelta(hours=1)
        fake_state = {
            "learning_start": learning_start_dt,
            "learning_complete": 0,
            "samples_collected": 5,
        }
        mgr.get_state = mock.MagicMock(return_value=fake_state)
        # Monkey-patch _lock_baseline so we don't need to mock the SELECT.
        mgr._lock_baseline = mock.MagicMock()
        try:
            result = mgr.record_sample("miner-1", hashrate_ths=100.0)
        except TypeError as exc:
            self.fail(f"record_sample raised TypeError on datetime state: {exc}")
        # 5+1=6 samples, ~1h elapsed — not enough to lock; returns False.
        self.assertFalse(result)

    def test_iso_string_state_still_works(self) -> None:
        # The legacy SQLite-shape (TEXT column → string) must still
        # work — backward compatibility.
        mgr = self._make_manager()
        self._patch_connect(mgr)
        iso = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        fake_state = {
            "learning_start": iso,
            "learning_complete": 0,
            "samples_collected": 5,
        }
        mgr.get_state = mock.MagicMock(return_value=fake_state)
        mgr._lock_baseline = mock.MagicMock()
        result = mgr.record_sample("miner-2", hashrate_ths=100.0)
        self.assertFalse(result)

    def test_invalid_state_skips_sample_no_crash(self) -> None:
        # Junk value → log + skip + return False. NEVER raise.
        mgr = self._make_manager()
        self._patch_connect(mgr)
        fake_state = {
            "learning_start": "not-a-real-date",
            "learning_complete": 0,
            "samples_collected": 5,
        }
        mgr.get_state = mock.MagicMock(return_value=fake_state)
        mgr._lock_baseline = mock.MagicMock()
        try:
            result = mgr.record_sample("miner-3", hashrate_ths=100.0)
        except Exception as exc:
            self.fail(f"record_sample raised on junk state: {exc}")
        self.assertFalse(result)

    def test_none_learning_start_skips_sample(self) -> None:
        mgr = self._make_manager()
        self._patch_connect(mgr)
        fake_state = {
            "learning_start": None,
            "learning_complete": 0,
            "samples_collected": 5,
        }
        mgr.get_state = mock.MagicMock(return_value=fake_state)
        mgr._lock_baseline = mock.MagicMock()
        result = mgr.record_sample("miner-4", hashrate_ths=100.0)
        self.assertFalse(result)


class TestLockBaselineDatetimeStateNoCrash(unittest.TestCase):
    """`_lock_baseline` reads `state["learning_start"]` and uses it as a
    SQL bound. Both datetime and ISO string are OK at the SQL layer
    (psycopg2 + the parameterised driver handle both). The reason we
    coerce here too is to keep the type predictable and the warning
    surface consistent with `record_sample`."""

    def setUp(self) -> None:
        import importlib
        sys.modules.setdefault("psycopg2", mock.MagicMock())
        sys.modules.setdefault("psycopg2.extras", mock.MagicMock())
        self.mod = importlib.import_module("core.hashrate_evaluation")

    def test_datetime_state_does_not_crash(self) -> None:
        mgr = self.mod.BaselineManager.__new__(self.mod.BaselineManager)
        mgr.db_path = "fake-dsn"
        mgr.learning_window_hrs = 72
        mgr.minimum_samples = 36

        learning_start_dt = datetime.now(timezone.utc) - timedelta(hours=80)
        fake_state = {
            "learning_start": learning_start_dt,
            "learning_complete": 0,
            "samples_collected": 100,
        }
        mgr.get_state = mock.MagicMock(return_value=fake_state)

        # Patch _connect: SELECT returns no rows → _lock_baseline logs
        # warning + early-return. We just need to confirm it doesn't
        # raise on the datetime input.
        cm = mock.MagicMock()
        cm.__enter__.return_value = cm
        cm.__exit__.return_value = False
        execute_result = mock.MagicMock()
        execute_result.fetchall = mock.MagicMock(return_value=[])
        cm.execute = mock.MagicMock(return_value=execute_result)
        cm.commit = mock.MagicMock()
        mgr._connect = mock.MagicMock(return_value=cm)

        try:
            mgr._lock_baseline("miner-X", datetime.now(timezone.utc))
        except TypeError as exc:
            self.fail(f"_lock_baseline raised TypeError on datetime state: {exc}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
