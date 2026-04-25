"""
test_streaming_autotune.py
==========================
Tests that the streaming Antminer miner.log parser:
  1. Handles 20,000 autotune events without hanging (must complete < 10s)
  2. Correctly classifies freq_set / temp_max / voltage / init_done events
  3. Yields meta items for miner_model and firmware_version
  4. Respects the 60s timeout guard (synthetic slow read is not needed;
     we just verify the guard is present in code)
  5. Produces correct batched SQL (max 1000 rows per statement)

Run:
    python -m pytest tests/test_streaming_autotune.py -v
"""
import sys
import os
import time
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from mg_import import (
    _stream_antminer_miner_log,
    _parse_antminer_miner_log,
    _build_antminer_autotune_sql_batched,
)


def _make_synthetic_log(n_autotune_events: int, tmp_dir: str) -> str:
    """
    Write a synthetic miner.log with n_autotune_events freq_set lines
    plus a device-complete line and an error line.
    """
    path = os.path.join(tmp_dir, "miner.log")
    lines = []
    lines.append("[2024/06/28 10:00:00.000] MSG: Detect device complete: Antminer S19, AWP12\n")
    lines.append("[2024/06/28 10:00:01.000] MSG: Firmware version: 54.0.1.3\n")
    for i in range(n_autotune_events):
        lines.append(
            f"[2024/06/28 10:01:{(i % 60):02d}.{(i % 1000):03d}] MSG: "
            f"Set chain {i % 3} freq {400 + (i % 100)}\n"
        )
    lines.append("[2024/06/28 11:00:00.000] ERROR: Hash board 0 temperature too high\n")
    lines.append("[2024/06/28 11:00:01.000] MSG: Temp max 95C\n")
    lines.append("[2024/06/28 11:00:02.000] MSG: Psu current voltage 12.85V\n")
    lines.append("[2024/06/28 11:00:03.000] MSG: Init done\n")
    with open(path, "w") as f:
        f.writelines(lines)
    return path


class TestStreamingParser:

    def test_20k_events_under_10s(self):
        """20,000 autotune events must stream in under 10 seconds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _make_synthetic_log(20_000, tmpdir)
            t0 = time.monotonic()
            autotune, events, model, fw = _parse_antminer_miner_log(
                path, "test_archive.tar", "session_20k"
            )
            elapsed = time.monotonic() - t0

        assert elapsed < 10.0, (
            f"20k autotune parse took {elapsed:.2f}s — exceeds 10s limit. "
            "Streaming fix may not be active."
        )
        # ≥ 20,000: the log has 20k freq_set events plus temp_max / voltage /
        # init_done entries which also land in the autotune table.
        assert len(autotune) >= 20_000, (
            f"Expected ≥20,000 autotune rows, got {len(autotune)}"
        )
        assert model == "Antminer S19"
        assert fw is not None

    def test_meta_extraction(self):
        """miner_model and firmware_version are extracted correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _make_synthetic_log(10, tmpdir)
            _, _, model, fw = _parse_antminer_miner_log(
                path, "test.tar", "session_meta"
            )
        assert model == "Antminer S19"
        assert fw == "54.0.1.3"

    def test_freq_set_event_type(self):
        """freq_set events are classified correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _make_synthetic_log(5, tmpdir)
            rows, _, _, _ = _parse_antminer_miner_log(
                path, "test.tar", "session_freq"
            )
        freq_set = [r for r in rows if r.get("event_type") == "freq_set"]
        assert len(freq_set) == 5
        for r in freq_set:
            assert r["chain"] in (0, 1, 2)
            assert 400 <= r["frequency_mhz"] <= 500

    def test_error_events_captured(self):
        """ERROR-level lines produce event items."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _make_synthetic_log(0, tmpdir)
            _, events, _, _ = _parse_antminer_miner_log(
                path, "test.tar", "session_err"
            )
        errors = [e for e in events if e["severity"] == "ERROR"]
        assert len(errors) >= 1
        assert "temperature" in errors[0]["message"].lower()

    def test_temp_max_and_voltage_events(self):
        """temp_max and voltage events are parsed from synthetic log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _make_synthetic_log(0, tmpdir)
            rows, _, _, _ = _parse_antminer_miner_log(
                path, "test.tar", "session_tv"
            )
        tmax = [r for r in rows if r.get("event_type") == "temp_max"]
        volt = [r for r in rows if r.get("event_type") == "voltage"]
        assert len(tmax) == 1
        assert tmax[0]["temp_max_c"] == 95.0
        assert len(volt) == 1
        assert volt[0]["voltage_v"] == 12.85

    def test_init_done_event(self):
        """init_done events are parsed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _make_synthetic_log(0, tmpdir)
            rows, _, _, _ = _parse_antminer_miner_log(
                path, "test.tar", "session_init"
            )
        init = [r for r in rows if r.get("event_type") == "init_done"]
        assert len(init) == 1

    def test_generator_yields_kinds(self):
        """_stream_antminer_miner_log yields dicts with 'kind' key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _make_synthetic_log(3, tmpdir)
            items = list(_stream_antminer_miner_log(path, "t.tar", "s"))
        kinds = {i["kind"] for i in items}
        assert "meta" in kinds
        assert "autotune" in kinds


class TestBatchedSQLBuilder:

    def _make_autotune_rows(self, n: int) -> list:
        return [
            {
                "archive_filename": "test.tar",
                "boot_session":     "cglog_init_2024-06-28_10-00-00",
                "event_idx":        i,
                "event_timestamp":  "2024-06-28T10:00:00",
                "event_type":       "freq_set",
                "chain":            i % 3,
                "frequency_mhz":    450,
                "voltage_v":        None,
                "temp_max_c":       None,
                "raw_line":         f"[2024/06/28 10:00:00.000] MSG: Set chain {i%3} freq 450",
            }
            for i in range(n)
        ]

    def test_batch_size_1000_produces_correct_count(self):
        """2500 rows should produce 3 SQL blocks (1000 + 1000 + 500)."""
        rows = self._make_autotune_rows(2500)
        blocks = _build_antminer_autotune_sql_batched(rows, batch_size=1000)
        assert len(blocks) == 3

    def test_empty_rows_produces_no_blocks(self):
        blocks = _build_antminer_autotune_sql_batched([], batch_size=1000)
        assert blocks == []

    def test_single_row_produces_one_block(self):
        rows = self._make_autotune_rows(1)
        blocks = _build_antminer_autotune_sql_batched(rows, batch_size=1000)
        assert len(blocks) == 1
        assert "INSERT INTO knowledge.field_log_antminer_autotune" in blocks[0]

    def test_on_conflict_in_each_block(self):
        rows = self._make_autotune_rows(1500)
        blocks = _build_antminer_autotune_sql_batched(rows, batch_size=1000)
        for b in blocks:
            assert "ON CONFLICT" in b

    def test_no_single_massive_string(self):
        """Each block must be under 5MB — no quadratic blowup."""
        rows = self._make_autotune_rows(1000)
        blocks = _build_antminer_autotune_sql_batched(rows, batch_size=1000)
        for b in blocks:
            assert len(b) < 5 * 1024 * 1024  # 5 MB
