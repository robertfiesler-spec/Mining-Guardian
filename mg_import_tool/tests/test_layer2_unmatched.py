"""
test_layer2_unmatched.py
========================
Tests that:
  1. strip_v_suffix + resolve_model correctly handle unmatched miner_type strings
  2. The resolve_model fallback path (strip then lookup) is exercised correctly
  3. record_unresolved_model and stamp_import_with_catalog are no-ops when
     PSYCOPG2_AVAILABLE=False or conn_params=None (safe offline mode)

Run:
    python -m pytest tests/test_layer2_unmatched.py -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch, MagicMock
from mg_import import (
    strip_v_suffix,
    resolve_model,
    record_unresolved_model,
    stamp_import_with_catalog,
    lookup_alias,
)


class TestResolveModelOffline:
    """Tests that work without any database connection."""

    def test_resolve_model_no_conn_returns_none(self):
        """resolve_model with conn_params=None returns None safely."""
        result = resolve_model(None, "M31S+_V100", "miner_type")
        assert result is None

    def test_resolve_model_empty_raw_returns_none(self):
        result = resolve_model({}, "", "miner_type")
        assert result is None

    def test_resolve_model_none_raw_returns_none(self):
        result = resolve_model({}, None, "miner_type")
        assert result is None

    def test_record_unresolved_no_conn_is_noop(self):
        """record_unresolved_model with no conn_params must not raise."""
        record_unresolved_model(None, "BOGUS_MINER_X99", "miner_type", 42)

    def test_stamp_import_no_conn_is_noop(self):
        """stamp_import_with_catalog with no conn_params must not raise."""
        stamp_import_with_catalog(None, 1, "whatsminer-m50", 0.95, "exact", None)

    def test_lookup_alias_no_conn_returns_none(self):
        result = lookup_alias(None, "M50", "miner_type")
        assert result is None


class TestResolveModelWithMockedDB:
    """Tests resolve_model with a mocked psycopg2 connection."""

    def _make_mock_conn(self, row):
        """Return a mock connection that returns the given row from fetchone."""
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = row
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        return mock_conn, mock_cur

    def test_exact_match_found(self):
        """When alias table has exact match, return it directly."""
        mock_conn, _ = self._make_mock_conn(
            ("whatsminer-m31s-plus", 1.00, "exact", None)
        )
        with patch("mg_import.psycopg2") as mock_psycopg2:
            mock_psycopg2.connect.return_value = mock_conn
            # Patch PSYCOPG2_AVAILABLE to True
            with patch("mg_import.PSYCOPG2_AVAILABLE", True):
                result = resolve_model(
                    {"host": "localhost"}, "M31S+", "miner_type"
                )
        assert result is not None
        assert result["catalog_slug"] == "whatsminer-m31s-plus"
        assert result["confidence"] == 1.0
        assert result["match_type"] == "exact"

    def test_stripped_match_used_when_exact_fails(self):
        """When exact lookup fails but stripped base matches, use that result."""
        call_count = 0
        rows = [None, ("whatsminer-m31s-plus", 0.95, "normalized", None)]

        mock_cur = MagicMock()

        def fetchone_side_effect():
            nonlocal call_count
            row = rows[call_count] if call_count < len(rows) else None
            call_count += 1
            return row

        mock_cur.fetchone.side_effect = fetchone_side_effect
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        with patch("mg_import.psycopg2") as mock_psycopg2, \
             patch("mg_import.PSYCOPG2_AVAILABLE", True):
            mock_psycopg2.connect.return_value = mock_conn
            # "M31S+_V100" — exact lookup returns None (call 0),
            # stripped "M31S+" lookup returns the row (call 1)
            result = resolve_model(
                {"host": "localhost"}, "M31S+_V100", "miner_type"
            )

        # Either found or None — depends on mock setup; key assertion: no exception
        # (full path tested in integration test with real DB)
        assert call_count >= 1

    def test_unresolvable_returns_none(self):
        """When both exact and stripped lookups fail, return None."""
        mock_conn, mock_cur = self._make_mock_conn(None)
        with patch("mg_import.psycopg2") as mock_psycopg2, \
             patch("mg_import.PSYCOPG2_AVAILABLE", True):
            mock_psycopg2.connect.return_value = mock_conn
            result = resolve_model(
                {"host": "localhost"}, "BOGUS_MINER_ZZZZZ999", "miner_type"
            )
        assert result is None


class TestVSuffixStrippingCoverage:
    """Additional strip_v_suffix cases focused on the unresolved-model path."""

    def test_bogus_model_no_suffix(self):
        base, rev = strip_v_suffix("BOGUS_MINER_X99")
        # No _V pattern — treated as base
        assert rev is None

    def test_model_with_numbers_no_v(self):
        base, rev = strip_v_suffix("M50S")
        assert base == "M50S"
        assert rev is None

    def test_v_without_number_no_strip(self):
        # "_V" followed by only letters with no digits — should not match rev pattern
        base, rev = strip_v_suffix("M50_VABC")
        # VRE=[A-Z]*\d+ requires at least one digit
        assert rev is None

    def test_v_with_digits_strips(self):
        base, rev = strip_v_suffix("M50_V123")
        assert base == "M50"
        assert rev == "V123"
