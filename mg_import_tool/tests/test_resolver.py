"""
tests/test_resolver.py
======================
Tests for the Layer 2 two-tier resolver module (resolver.py).

Covers:
  - normalize(): whitespace collapse, uppercase, +/++ preservation, no V-code strip
  - strip_vcode(): recognised/unrecognised V-codes, separator handling
  - Tier-1 exact hit
  - Tier-1 V-code-stripped hit with hardware_revision capture
  - Tier-2 hit with observed hashrate (nearest-bin selection)
  - Tier-2 tie: goes to lower-rated bin
  - Tier-2 hit with null / empty / non-numeric hashrate → unresolved
  - No-match → unresolved with reason='no_alias_match'
  - Empty/None raw_string → unresolved with reason='empty_raw_string'
  - resolve_identity_fields(): miner_type hit, control_board fallback, both miss
  - _pick_tier2_bin(): single candidate, multiple candidates, tie
  - _parse_hashrate_gh(): valid GH/s values, None, empty string, non-numeric
  - insert_unresolved(): no-op when conn=None
  - Streaming autotune: batch_size=500 produces correct SQL block count
  - Memory-bounded streaming over 15k-event synthetic archive

Run:
    python -m pytest tests/test_resolver.py -v
"""
import sys
import os
import io
import time
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock, patch, call

import resolver as _res
from resolver import (
    normalize,
    strip_vcode,
    resolve,
    resolve_identity_fields,
    insert_unresolved,
    ResolverResult,
    _pick_tier2_bin,
    _parse_hashrate_gh,
    _tier1_lookup,
    _tier2_lookup,
    _VCODES,
)

# Also import the batched SQL builder from mg_import so we can test batch_size=500
import importlib.util as _ilu
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = _ilu.spec_from_file_location('mg_import_for_resolver_test',
                                      os.path.join(_REPO, 'mg_import.py'))

# Mock heavy deps before loading
import unittest.mock as _umock
_psycopg2_mock = _umock.MagicMock()
sys.modules.setdefault('psycopg2', _psycopg2_mock)
sys.modules.setdefault('psycopg2.extras', _psycopg2_mock.extras)
sys.modules.setdefault('openpyxl', _umock.MagicMock())
_flask_mock = _umock.MagicMock()
_flask_inst = _umock.MagicMock()
_flask_inst.config = {}
_flask_mock.Flask.return_value = _flask_inst
sys.modules.setdefault('flask', _flask_mock)

_mg = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mg)

_build_autotune_sql_batched = _mg._build_antminer_autotune_sql_batched
_parse_antminer_miner_log = _mg._parse_antminer_miner_log


# ---------------------------------------------------------------------------
# Helpers for building mock DB connections
# ---------------------------------------------------------------------------

def _mock_conn_tier1(uuid_value):
    """Return a mock psycopg2 connection whose cursor returns uuid_value from Tier-1 query."""
    cur = MagicMock()
    cur.fetchone.return_value = (uuid_value,) if uuid_value else None
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


def _mock_conn_multi(responses: list):
    """
    Return a mock connection whose cursor.fetchone cycles through responses.
    Each entry in responses is either (value,) tuple or None.
    """
    call_index = [0]

    cur = MagicMock()

    def _fetchone():
        idx = call_index[0]
        call_index[0] += 1
        return responses[idx] if idx < len(responses) else None

    cur.fetchone.side_effect = _fetchone
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


# ===========================================================================
# 1. Normalizer tests
# ===========================================================================

class TestNormalize:

    def test_strips_leading_trailing_whitespace(self):
        assert normalize('  M31S+  ') == 'M31S+'

    def test_collapses_internal_whitespace(self):
        assert normalize('Antminer  S19') == 'ANTMINER S19'

    def test_uppercase(self):
        assert normalize('m50s') == 'M50S'

    def test_preserves_trailing_plus(self):
        assert normalize('M30S+') == 'M30S+'

    def test_preserves_trailing_double_plus(self):
        assert normalize('M30S++') == 'M30S++'

    def test_preserves_vcode_in_output(self):
        # Rule 4: do NOT strip V-codes at normalise stage
        assert normalize('M31S+_V100') == 'M31S+_V100'

    def test_empty_string_returns_empty(self):
        assert normalize('') == ''

    def test_none_returns_empty(self):
        assert normalize(None) == ''  # type: ignore

    def test_tabs_and_newlines_collapsed(self):
        assert normalize('M50\t S') == 'M50 S'

    def test_s19_plus_preserved(self):
        assert normalize('antminer s19+') == 'ANTMINER S19+'

    def test_m63s_plus_preserved(self):
        # M63, M63S, M63+, M63S+ are all different — never collapse
        assert normalize('m63s+') == 'M63S+'

    def test_m56s_double_plus_preserved(self):
        assert normalize('M56S++') == 'M56S++'


# ===========================================================================
# 2. strip_vcode tests
# ===========================================================================

class TestStripVcode:

    def test_v100_stripped(self):
        base, vcode = strip_vcode('M31S+_V100')
        assert base == 'M31S+'
        assert vcode == 'V100'

    def test_vk10_stripped(self):
        base, vcode = strip_vcode('M56S++_VK10')
        assert base == 'M56S++'
        assert vcode == 'VK10'

    def test_ve30_stripped(self):
        base, vcode = strip_vcode('M53S_VE30')
        assert base == 'M53S'
        assert vcode == 'VE30'

    def test_no_suffix_returns_none(self):
        base, vcode = strip_vcode('M21S')
        assert base == 'M21S'
        assert vcode is None

    def test_antminer_no_suffix(self):
        base, vcode = strip_vcode('ANTMINER S19')
        assert vcode is None

    def test_empty_string_passthrough(self):
        base, vcode = strip_vcode('')
        assert base == ''
        assert vcode is None

    def test_v_codes_are_recognised_set(self):
        # All 15 V-codes from the brief must be in _VCODES
        expected = {
            'V10', 'V20', 'V30', 'V40', 'V50', 'V60', 'V70', 'V80', 'V90', 'V100',
            'VE30', 'VE50', 'VE80', 'VK10', 'VK30',
        }
        assert expected.issubset(_VCODES)


# ===========================================================================
# 3. _parse_hashrate_gh tests
# ===========================================================================

class TestParseHashrateGh:

    def test_valid_gh_converts_to_ths(self):
        assert _parse_hashrate_gh('95000') == pytest.approx(95.0)

    def test_float_string(self):
        assert _parse_hashrate_gh('95500.5') == pytest.approx(95.5005)

    def test_none_returns_none(self):
        assert _parse_hashrate_gh(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_hashrate_gh('') is None

    def test_non_numeric_returns_none(self):
        assert _parse_hashrate_gh('N/A') is None

    def test_whitespace_stripped(self):
        assert _parse_hashrate_gh('  110000 ') == pytest.approx(110.0)

    def test_zero(self):
        assert _parse_hashrate_gh('0') == pytest.approx(0.0)


# ===========================================================================
# 4. _pick_tier2_bin tests
# ===========================================================================

class TestPickTier2Bin:

    def test_single_candidate_always_selected(self):
        result = _pick_tier2_bin(['uuid-a'], [100.0], 95.0)
        assert result == 'uuid-a'

    def test_nearest_bin_selected(self):
        # 95.0 TH/s is closer to 100 than 110
        result = _pick_tier2_bin(['uuid-a', 'uuid-b'], [100.0, 110.0], 95.0)
        assert result == 'uuid-a'

    def test_tie_goes_to_lower_rated_bin(self):
        # Equidistant from 100 and 110 at 105 → pick lower (uuid-a, rated 100)
        result = _pick_tier2_bin(['uuid-a', 'uuid-b'], [100.0, 110.0], 105.0)
        assert result == 'uuid-a'

    def test_nearest_upper_bin_selected(self):
        # 108 TH/s is closer to 110 than to 100
        result = _pick_tier2_bin(['uuid-a', 'uuid-b'], [100.0, 110.0], 108.0)
        assert result == 'uuid-b'

    def test_exact_match(self):
        result = _pick_tier2_bin(['uuid-c', 'uuid-d'], [80.0, 100.0], 100.0)
        assert result == 'uuid-d'

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError):
            _pick_tier2_bin(['uuid-a'], [100.0, 110.0], 95.0)

    def test_empty_candidates_raises(self):
        with pytest.raises((ValueError, IndexError)):
            _pick_tier2_bin([], [], 95.0)


# ===========================================================================
# 5. resolve() — offline (conn=None)
# ===========================================================================

class TestResolveOffline:

    def test_none_raw_string_returns_unresolved(self):
        r = resolve(None, None)
        assert r.tier == 'unresolved'
        assert r.model_id is None
        assert r.reason == 'empty_raw_string'

    def test_empty_raw_string_returns_unresolved(self):
        r = resolve(None, '')
        assert r.tier == 'unresolved'
        assert r.reason == 'empty_raw_string'

    def test_whitespace_only_returns_unresolved(self):
        r = resolve(None, '   ')
        assert r.tier == 'unresolved'
        assert r.reason == 'empty_raw_string'

    def test_valid_string_offline_returns_unresolved(self):
        # No conn → can't resolve → unresolved (no_alias_match)
        r = resolve(None, 'M50S')
        assert r.tier == 'unresolved'
        # reason may be no_alias_match or None (insert_unresolved is no-op)
        assert r.model_id is None


# ===========================================================================
# 6. resolve() — Tier-1 exact hit (mocked DB)
# ===========================================================================

class TestResolveTier1Exact:

    def test_tier1_hit_returns_model_id(self):
        UUID = 'aaaabbbb-cccc-dddd-eeee-ffffgggg0001'
        conn, cur = _mock_conn_tier1(UUID)
        r = resolve(conn, 'M50S')
        assert r.tier == 'tier1'
        assert r.model_id == UUID
        assert r.hardware_revision is None

    def test_tier1_hit_normalizes_before_lookup(self):
        UUID = 'aaaabbbb-cccc-dddd-eeee-ffffgggg0002'
        conn, cur = _mock_conn_tier1(UUID)
        # lowercase + spaces → should normalise to 'M50S' before query
        r = resolve(conn, '  m50s  ')
        assert r.tier == 'tier1'
        assert r.model_id == UUID

    def test_tier1_hit_with_plus_suffix(self):
        UUID = 'aaaabbbb-cccc-dddd-eeee-ffffgggg0003'
        conn, cur = _mock_conn_tier1(UUID)
        r = resolve(conn, 'M30S+')
        assert r.tier == 'tier1'
        assert r.model_id == UUID


# ===========================================================================
# 7. resolve() — Tier-1 V-code-stripped hit
# ===========================================================================

class TestResolveTier1VcodeStripped:

    def _conn_miss_then_hit(self, uuid_value):
        """First fetchone returns None (exact miss), second returns the UUID (stripped hit)."""
        conn, cur = _mock_conn_multi([None, (uuid_value,)])
        return conn

    def test_vcode_stripped_hit_returns_correct_tier(self):
        UUID = 'aaaabbbb-cccc-dddd-eeee-ffffgggg0010'
        conn = self._conn_miss_then_hit(UUID)
        r = resolve(conn, 'M31S+_V100')
        assert r.tier == 'tier1_vcode_stripped'
        assert r.model_id == UUID
        assert r.hardware_revision == 'V100'

    def test_vk10_vcode_stripped_captures_revision(self):
        UUID = 'aaaabbbb-cccc-dddd-eeee-ffffgggg0011'
        conn = self._conn_miss_then_hit(UUID)
        r = resolve(conn, 'M56S++_VK10')
        assert r.hardware_revision == 'VK10'
        assert r.tier == 'tier1_vcode_stripped'

    def test_ve30_stripped_captures_revision(self):
        UUID = 'aaaabbbb-cccc-dddd-eeee-ffffgggg0012'
        conn = self._conn_miss_then_hit(UUID)
        r = resolve(conn, 'M53S_VE30')
        assert r.hardware_revision == 'VE30'


# ===========================================================================
# 8. resolve() — Tier-2 hit
# ===========================================================================

class TestResolveTier2:

    def _conn_tier2(self, tier2_row):
        """
        Tier-1 queries return None; Tier-2 query returns tier2_row dict.
        """
        # We need to mock both _tier1_lookup (returns None) and _tier2_lookup
        pass  # We'll patch the internal functions directly

    def test_tier2_nearest_bin_selection(self):
        UUID_A = 'aaaabbbb-cccc-dddd-eeee-000000000001'
        UUID_B = 'aaaabbbb-cccc-dddd-eeee-000000000002'
        with patch.object(_res, '_tier1_lookup', return_value=None), \
             patch.object(_res, '_tier2_lookup', return_value={
                 'candidate_model_ids': [UUID_A, UUID_B],
                 'candidate_hashrates': [100.0, 110.0],
             }):
            # 95 TH/s → closer to 100 → UUID_A
            r = resolve(MagicMock(), 'M50-FAMILY', hashrate_gh='95000')
        assert r.tier == 'tier2'
        assert r.model_id == UUID_A

    def test_tier2_tie_goes_lower(self):
        UUID_A = 'aaaabbbb-cccc-dddd-eeee-000000000003'
        UUID_B = 'aaaabbbb-cccc-dddd-eeee-000000000004'
        with patch.object(_res, '_tier1_lookup', return_value=None), \
             patch.object(_res, '_tier2_lookup', return_value={
                 'candidate_model_ids': [UUID_A, UUID_B],
                 'candidate_hashrates': [100.0, 110.0],
             }):
            # 105 TH/s → equidistant → lower bin UUID_A
            r = resolve(MagicMock(), 'M50-FAMILY', hashrate_gh='105000')
        assert r.tier == 'tier2'
        assert r.model_id == UUID_A

    def test_tier2_upper_bin_wins_when_closer(self):
        UUID_A = 'aaaabbbb-cccc-dddd-eeee-000000000005'
        UUID_B = 'aaaabbbb-cccc-dddd-eeee-000000000006'
        with patch.object(_res, '_tier1_lookup', return_value=None), \
             patch.object(_res, '_tier2_lookup', return_value={
                 'candidate_model_ids': [UUID_A, UUID_B],
                 'candidate_hashrates': [100.0, 110.0],
             }):
            # 108 TH/s → closer to 110 → UUID_B
            r = resolve(MagicMock(), 'M50-FAMILY', hashrate_gh='108000')
        assert r.tier == 'tier2'
        assert r.model_id == UUID_B


# ===========================================================================
# 9. resolve() — Tier-2 hit, no hashrate → unresolved
# ===========================================================================

class TestResolveTier2NoHashrate:

    def test_null_hashrate_produces_unresolved(self):
        UUID_A = 'aaaabbbb-cccc-dddd-eeee-999999999001'
        with patch.object(_res, '_tier1_lookup', return_value=None), \
             patch.object(_res, '_tier2_lookup', return_value={
                 'candidate_model_ids': [UUID_A],
                 'candidate_hashrates': [100.0],
             }), \
             patch.object(_res, 'insert_unresolved') as mock_insert:
            r = resolve(MagicMock(), 'M50-FAMILY', hashrate_gh=None)
        assert r.tier == 'unresolved'
        assert r.reason == 'tier2_hit_no_hashrate'
        assert r.model_id is None
        mock_insert.assert_called_once()

    def test_empty_hashrate_produces_unresolved(self):
        UUID_A = 'aaaabbbb-cccc-dddd-eeee-999999999002'
        with patch.object(_res, '_tier1_lookup', return_value=None), \
             patch.object(_res, '_tier2_lookup', return_value={
                 'candidate_model_ids': [UUID_A],
                 'candidate_hashrates': [100.0],
             }):
            r = resolve(MagicMock(), 'M50-FAMILY', hashrate_gh='')
        assert r.tier == 'unresolved'
        assert r.reason == 'tier2_hit_no_hashrate'

    def test_nonnumeric_hashrate_produces_unresolved(self):
        UUID_A = 'aaaabbbb-cccc-dddd-eeee-999999999003'
        with patch.object(_res, '_tier1_lookup', return_value=None), \
             patch.object(_res, '_tier2_lookup', return_value={
                 'candidate_model_ids': [UUID_A],
                 'candidate_hashrates': [100.0],
             }):
            r = resolve(MagicMock(), 'M50-FAMILY', hashrate_gh='N/A')
        assert r.tier == 'unresolved'
        assert r.reason == 'tier2_hit_no_hashrate'


# ===========================================================================
# 10. resolve() — Fallback (no Tier-1 or Tier-2 hit)
# ===========================================================================

class TestResolveFallback:

    def test_no_match_returns_unresolved(self):
        with patch.object(_res, '_tier1_lookup', return_value=None), \
             patch.object(_res, '_tier2_lookup', return_value=None), \
             patch.object(_res, 'insert_unresolved') as mock_insert:
            r = resolve(MagicMock(), 'BOGUS_MINER_ZZZZZ')
        assert r.tier == 'unresolved'
        assert r.reason == 'no_alias_match'
        assert r.model_id is None
        mock_insert.assert_called_once()

    def test_no_match_with_archive_filename_passed_to_insert(self):
        with patch.object(_res, '_tier1_lookup', return_value=None), \
             patch.object(_res, '_tier2_lookup', return_value=None), \
             patch.object(_res, 'insert_unresolved') as mock_insert:
            resolve(MagicMock(), 'BOGUS_MINER_ZZZZZ',
                    archive_filename='test_archive.tar')
        args = mock_insert.call_args
        assert 'test_archive.tar' in args[0] or 'test_archive.tar' in str(args)


# ===========================================================================
# 11. resolve_identity_fields() — check BOTH miner_type AND control_board
# ===========================================================================

class TestResolveIdentityFields:

    def test_miner_type_hit_used_directly(self):
        UUID = 'aaaabbbb-cccc-dddd-eeee-111111111111'
        with patch.object(_res, '_tier1_lookup', return_value=UUID):
            r = resolve_identity_fields(
                MagicMock(), 'M50S', 'BM1762',
            )
        assert r.tier == 'tier1'
        assert r.model_id == UUID

    def test_control_board_used_when_miner_type_unresolved(self):
        """When miner_type misses, resolve_identity_fields falls back to control_board."""
        UUID = 'aaaabbbb-cccc-dddd-eeee-222222222222'
        # 'BOGUS_MINER_ZZZZZ' has no V-code: 1 Tier-1 call, 1 Tier-2 call
        # 'BM1762_REAL' has no V-code: 1 Tier-1 call
        # We want the control-board call to return the UUID
        call_count = [0]

        def tier1_side_effect(conn, normalised):
            call_count[0] += 1
            # Call 1: miner_type exact lookup -> miss
            # Call 2: control_board exact lookup -> hit
            if call_count[0] == 1:
                return None   # miner_type misses
            return UUID       # control_board hits

        with patch.object(_res, '_tier1_lookup', side_effect=tier1_side_effect), \
             patch.object(_res, '_tier2_lookup', return_value=None), \
             patch.object(_res, 'insert_unresolved'):
            r = resolve_identity_fields(
                MagicMock(), 'BOGUS_MINER_ZZZZZ', 'BM1762_REAL',
            )
        # Should have tried the control_board and got a tier1 result
        assert r.tier == 'tier1'
        assert r.model_id == UUID

    def test_both_miss_returns_miner_type_result(self):
        with patch.object(_res, '_tier1_lookup', return_value=None), \
             patch.object(_res, '_tier2_lookup', return_value=None), \
             patch.object(_res, 'insert_unresolved'):
            r = resolve_identity_fields(
                MagicMock(), 'BOGUS_A', 'BOGUS_B',
            )
        assert r.tier == 'unresolved'
        assert r.model_id is None


# ===========================================================================
# 12. insert_unresolved() — no-op safety
# ===========================================================================

class TestInsertUnresolved:

    def test_no_op_with_none_conn(self):
        # Must not raise
        insert_unresolved(None, 'BOGUS_MINER', 'no_alias_match', 'archive.tar')

    def test_no_op_with_empty_raw_string(self):
        insert_unresolved(MagicMock(), '', 'no_alias_match', 'archive.tar')

    def test_calls_execute_when_conn_present(self):
        cur = MagicMock()
        conn = MagicMock()
        conn.cursor.return_value = cur
        insert_unresolved(conn, 'M50X', 'no_alias_match', 'test.tar')
        cur.execute.assert_called_once()


# ===========================================================================
# 13. Streaming autotune — batch_size=500 default
# ===========================================================================

class TestAutotuneBatchSize500:

    def _make_rows(self, n: int) -> list:
        return [
            {
                'archive_filename': 'test.tar',
                'boot_session':     'session_test',
                'event_idx':        i,
                'event_timestamp':  '2024-06-28T10:00:00',
                'event_type':       'freq_set',
                'chain':            i % 3,
                'frequency_mhz':    450,
                'voltage_v':        None,
                'temp_max_c':       None,
                'raw_line':         f'[line {i}]',
            }
            for i in range(n)
        ]

    def test_default_batch_500_splits_1500_into_3_blocks(self):
        """1500 rows with default batch_size=500 → 3 SQL blocks."""
        rows = self._make_rows(1500)
        blocks = _build_autotune_sql_batched(rows)  # uses new default of 500
        assert len(blocks) == 3

    def test_500_rows_is_one_block(self):
        rows = self._make_rows(500)
        blocks = _build_autotune_sql_batched(rows)
        assert len(blocks) == 1

    def test_501_rows_is_two_blocks(self):
        rows = self._make_rows(501)
        blocks = _build_autotune_sql_batched(rows)
        assert len(blocks) == 2

    def test_each_block_under_5mb(self):
        """Memory guard: no single SQL block should exceed 5 MB."""
        rows = self._make_rows(500)
        blocks = _build_autotune_sql_batched(rows)
        for b in blocks:
            assert len(b.encode('utf-8')) < 5 * 1024 * 1024


# ===========================================================================
# 14. Memory-bounded streaming over 15k synthetic events
# ===========================================================================

class TestStreamingMemoryBound:

    def _make_synthetic_log(self, n_events: int, tmp_dir: str) -> str:
        path = os.path.join(tmp_dir, 'miner.log')
        with open(path, 'w') as f:
            f.write('[2024/06/28 10:00:00.000] MSG: Detect device complete: Antminer S19, AWP12\n')
            f.write('[2024/06/28 10:00:01.000] MSG: Firmware version: 54.0.1.3\n')
            for i in range(n_events):
                f.write(
                    f'[2024/06/28 10:01:{(i % 60):02d}.{(i % 1000):03d}] MSG: '
                    f'Set chain {i % 3} freq {400 + (i % 100)}\n'
                )
        return path

    def test_15k_events_complete_under_10s(self):
        """15,000 autotune events must stream and build SQL in under 10 seconds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._make_synthetic_log(15_000, tmpdir)
            t0 = time.monotonic()
            rows, events, model, fw = _parse_antminer_miner_log(
                path, 'test.tar', 'session_15k'
            )
            # Now build SQL in batches of 500
            blocks = _build_autotune_sql_batched(rows, batch_size=500)
            elapsed = time.monotonic() - t0
        assert elapsed < 10.0, (
            f'15k events + SQL build took {elapsed:.2f}s — streaming may not be active'
        )
        assert len(rows) >= 15_000
        # With 15k rows and batch_size=500 we expect exactly 30 blocks
        assert len(blocks) == 30

    def test_each_batch_block_has_on_conflict(self):
        """Every SQL block in the batch must contain ON CONFLICT."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._make_synthetic_log(1_000, tmpdir)
            rows, _, _, _ = _parse_antminer_miner_log(path, 'test.tar', 's')
            blocks = _build_autotune_sql_batched(rows, batch_size=500)
        for b in blocks:
            assert 'ON CONFLICT' in b


# ===========================================================================
# 15. Raw JSON capture — round-trip test (offline SQL generation)
# ===========================================================================

class TestRawJsonCapture:

    def test_insert_raw_json_no_op_without_conn(self):
        """insert_raw_json must not raise when conn_params=None."""
        from mg_import import insert_raw_json
        # Should be a no-op (no DB available). Signature updated 2026-04-29 to
        # canonical 7-arg form: (conn_params, archive_filename, source_file,
        # parser, payload, sha256, entity_label).
        insert_raw_json(None, 'test_archive.tar', 'miner_overview.log',
                        'antminer:miner_overview',
                        {'miner_model': 'M50S', 'firmware': '10.0.1'},
                        'a' * 64, 'miner_001')

    def test_insert_raw_json_no_op_without_psycopg2(self):
        """insert_raw_json must not raise when PSYCOPG2_AVAILABLE=False."""
        from mg_import import insert_raw_json
        with patch('mg_import.PSYCOPG2_AVAILABLE', False):
            insert_raw_json({'host': 'localhost'}, 'test_archive.tar',
                            'miner_overview.log',
                            'antminer:miner_overview',
                            {'miner_model': 'M50S'},
                            'b' * 64, 'miner_002')

    def test_insert_raw_json_calls_execute(self):
        """When conn_params provided and psycopg2 available, calls execute."""
        cur = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = cur

        import psycopg2 as _pg2_mock
        from mg_import import insert_raw_json
        with patch('mg_import.psycopg2') as mock_psycopg2, \
             patch('mg_import.PSYCOPG2_AVAILABLE', True):
            mock_psycopg2.connect.return_value = mock_conn
            insert_raw_json(
                {'host': 'localhost', 'database': 'mining_guardian'},
                'test_archive.tar',
                'miner_overview.log',
                'antminer:miner_overview',
                {'miner_model': 'M50S', 'firmware': '10.0.1'},
                'c' * 64,
                'miner_003',
            )
        cur.execute.assert_called_once()
        # Verify archive_filename and file_path_in_archive are in the query args
        call_args = cur.execute.call_args[0]
        assert 'test_archive.tar' in call_args[1]
        assert 'miner_overview.log' in call_args[1]
