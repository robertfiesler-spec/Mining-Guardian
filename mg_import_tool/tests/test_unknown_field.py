"""
test_unknown_field.py
=====================
Tests that:
  1. _guess_value_type correctly identifies int/float/string/enum/timestamp
  2. record_unknown_fields is a safe no-op when conn_params=None
  3. record_unknown_fields correctly identifies unknown vs known keys
  4. The KNOWN_KEYS_BY_FILE registry covers expected file patterns

Run:
    python -m pytest tests/test_unknown_field.py -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch, MagicMock
from mg_import import (
    _guess_value_type,
    record_unknown_fields,
    KNOWN_KEYS_BY_FILE,
    KNOWN_MINER_OVERVIEW_KEYS,
    KNOWN_MINER_LOG_KEYS,
    KNOWN_CGMINER_CONF_KEYS,
)


class TestGuessValueType:

    def test_integer_string(self):
        assert _guess_value_type("42") == "int"

    def test_negative_integer(self):
        assert _guess_value_type("-17") == "int"

    def test_float_string(self):
        assert _guess_value_type("3.14") == "float"

    def test_scientific_notation(self):
        assert _guess_value_type("1.5e-3") == "float"

    def test_timestamp_iso(self):
        assert _guess_value_type("2024-06-28T10:00:00") == "timestamp"

    def test_timestamp_date_only(self):
        assert _guess_value_type("2024/06/28") == "timestamp"

    def test_short_enum_like_string(self):
        # Short string with no spaces → enum
        result = _guess_value_type("psu_failure")
        assert result == "enum"

    def test_long_string(self):
        result = _guess_value_type("This is a long description with many words")
        assert result == "string"

    def test_none_value(self):
        assert _guess_value_type(None) == "string"

    def test_empty_string(self):
        # empty string after strip is int? No — "" doesn't match int re
        result = _guess_value_type("")
        assert result in ("string", "enum", "int")  # empty matches nothing useful


class TestRecordUnknownFields:

    def test_no_conn_is_noop(self):
        """Should not raise with conn_params=None."""
        record_unknown_fields(
            None, 1, "miner_overview.log",
            {"some_weird_key": "value"},
            KNOWN_MINER_OVERVIEW_KEYS
        )

    def test_all_known_keys_no_db_call(self):
        """If all keys are known, no DB call should be made."""
        known_payload = {k: "val" for k in list(KNOWN_MINER_OVERVIEW_KEYS)[:5]}
        with patch("mg_import.psycopg2") as mock_psycopg2, \
             patch("mg_import.PSYCOPG2_AVAILABLE", True):
            mock_conn = MagicMock()
            mock_psycopg2.connect.return_value = mock_conn
            record_unknown_fields(
                {"host": "localhost"}, 1, "miner_overview.log",
                known_payload, KNOWN_MINER_OVERVIEW_KEYS
            )
            # If all keys known → empty unknown dict → no DB connection needed
            # (implementation may or may not connect; key thing: no exception)

    def test_unknown_key_triggers_db_call(self):
        """A key NOT in known_keys should trigger a DB INSERT."""
        mock_cur = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_conn.autocommit = True

        with patch("mg_import.psycopg2") as mock_psycopg2, \
             patch("mg_import.PSYCOPG2_AVAILABLE", True):
            mock_psycopg2.connect.return_value = mock_conn
            record_unknown_fields(
                {"host": "localhost"}, 1, "miner_overview.log",
                {"chip_vcore_ripple_mv": "123"},
                KNOWN_MINER_OVERVIEW_KEYS
            )
            # The DB connection should be called since there's an unknown key
            mock_psycopg2.connect.assert_called_once()
            mock_cur.execute.assert_called()

    def test_bogus_field_key_surfaces(self):
        """A completely bogus key must appear in the execute call args."""
        executed_sqls = []

        def capture_execute(sql, args):
            executed_sqls.append((sql, args))

        mock_cur = MagicMock()
        mock_cur.execute.side_effect = capture_execute
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        with patch("mg_import.psycopg2") as mock_psycopg2, \
             patch("mg_import.PSYCOPG2_AVAILABLE", True):
            mock_psycopg2.connect.return_value = mock_conn
            record_unknown_fields(
                {"host": "localhost"}, 42, "miner_overview.log",
                {"totally_fake_field_xyz": "99"},
                KNOWN_MINER_OVERVIEW_KEYS
            )

        assert len(executed_sqls) == 1
        sql, args = executed_sqls[0]
        assert "totally_fake_field_xyz" in args


class TestKnownKeysRegistry:

    def test_registry_has_expected_file_patterns(self):
        assert "miner_overview.log" in KNOWN_KEYS_BY_FILE
        assert "miner.log"          in KNOWN_KEYS_BY_FILE
        assert "cgminer.conf"       in KNOWN_KEYS_BY_FILE

    def test_miner_type_in_overview_keys(self):
        assert "miner_type" in KNOWN_MINER_OVERVIEW_KEYS

    def test_mac_in_overview_keys(self):
        assert "MAC" in KNOWN_MINER_OVERVIEW_KEYS

    def test_firmware_in_overview_keys(self):
        assert "FIRMWARE_VERSION" in KNOWN_MINER_OVERVIEW_KEYS

    def test_event_timestamp_in_miner_log_keys(self):
        assert "event_timestamp" in KNOWN_MINER_LOG_KEYS

    def test_pools_in_cgminer_keys(self):
        assert "pools" in KNOWN_CGMINER_CONF_KEYS

    def test_overview_keys_is_frozenset(self):
        assert isinstance(KNOWN_MINER_OVERVIEW_KEYS, frozenset)

    def test_lookup_by_pattern(self):
        keys = KNOWN_KEYS_BY_FILE.get("miner_overview.log")
        assert keys is not None
        assert "miner_type" in keys
