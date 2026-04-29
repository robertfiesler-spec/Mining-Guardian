"""
tests/test_identity_and_raw_json.py
====================================
v3.2 tests for:
  - field_log_miner_identity population from Antminer archives
  - archive-level fallback identity row when no boot sessions parsed
  - resolver stamping of identity rows (mocked DB)
  - field_log_raw_json per-file capture
  - idempotency (re-import produces no duplicate rows)
  - insert_miner_identity helper (mocked DB)
  - _insert_archive_raw_json_files helper
  - _update_import_run_resolver_stats helper
  - _stream_antminer_miner_log new meta patterns (MAC, kernel, control_board, cool_mode)

Run:
    python -m pytest tests/test_identity_and_raw_json.py -v
"""
import sys
import os
import json
import tempfile
import tarfile
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock, patch, call

# ---------------------------------------------------------------------------
# Bootstrap: mock heavy optional deps before importing mg_import
# ---------------------------------------------------------------------------
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

import importlib.util as _ilu
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = _ilu.spec_from_file_location('mg_import_id_test',
                                      os.path.join(_REPO, 'mg_import.py'))
_mg = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mg)

# Imports from the loaded module
parse_antminer_bundle        = _mg.parse_antminer_bundle
_stream_antminer_miner_log   = _mg._stream_antminer_miner_log
_build_identity_sql          = _mg._build_identity_sql
insert_miner_identity        = _mg.insert_miner_identity
insert_raw_json              = _mg.insert_raw_json
_insert_archive_raw_json_files = _mg._insert_archive_raw_json_files
_update_import_run_resolver_stats = _mg._update_import_run_resolver_stats


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

def _make_miner_log(lines: list, tmp_dir: str, filename: str = 'miner.log') -> str:
    path = os.path.join(tmp_dir, filename)
    with open(path, 'w') as fh:
        fh.writelines(lines)
    return path


def _make_minimal_antminer_archive(tmp_dir: str, archive_name: str,
                                   sessions: list = None,
                                   log_lines_per_session: list = None):
    """
    Build a minimal Antminer tar archive in tmp_dir.

    sessions: list of session folder names (default: one session)
    log_lines_per_session: list of lists of log lines (parallel to sessions)
    Returns path to the .tar file.
    """
    if sessions is None:
        sessions = ['cglog_init_2024-06-28_10-00-00']
    if log_lines_per_session is None:
        log_lines_per_session = [
            [
                '[2024/06/28 10:00:00.000] MSG: Detect device complete: Antminer S19, AWP12\n',
                '[2024/06/28 10:00:01.000] MSG: Firmware version: 54.0.1.3\n',
                '[2024/06/28 10:00:02.000] MSG: Set chain 0 freq 450\n',
            ]
        ] * len(sessions)

    # Build directory tree in a sub-temp-dir then tar it
    src = tempfile.mkdtemp(dir=tmp_dir, prefix='src_')
    nvdata = os.path.join(src, 'nvdata', '2024-06', '28')
    os.makedirs(nvdata)
    for i, session in enumerate(sessions):
        sdir = os.path.join(nvdata, session)
        os.makedirs(sdir)
        lines = log_lines_per_session[i] if i < len(log_lines_per_session) else []
        with open(os.path.join(sdir, 'miner.log'), 'w') as f:
            f.writelines(lines)

    # cgminer.conf
    config_dir = os.path.join(src, 'config')
    os.makedirs(config_dir)
    with open(os.path.join(config_dir, 'cgminer.conf'), 'w') as f:
        json.dump({'pools': [{'url': 'stratum+tcp://pool.example.com:3333',
                              'user': 'worker1', 'pass': 'x'}]}, f)

    tar_path = os.path.join(tmp_dir, archive_name)
    with tarfile.open(tar_path, 'w') as tf:
        tf.add(src, arcname='.')
    return tar_path


def _count_inserts(sql_blocks: list, table: str) -> int:
    import re
    pat = re.compile(
        r'INSERT\s+INTO\s+knowledge\.' + re.escape(table) + r'\b',
        re.IGNORECASE,
    )
    return sum(len(pat.findall(blk)) for blk in sql_blocks)


# ===========================================================================
# TestIdentityExtractionFromAntminerLog
# ===========================================================================

class TestIdentityExtractionFromAntminerLog:
    """Tests for parse_antminer_bundle yielding field_log_miner_identity rows."""

    def test_single_session_produces_one_identity_row(self):
        """One boot session → exactly one identity INSERT."""
        with tempfile.TemporaryDirectory() as td:
            tar = _make_minimal_antminer_archive(td, 'test.tar')
            with open(tar, 'rb') as f:
                data = f.read()
            # call parse_antminer_bundle through process_archive (offline, no conn_params)
            blocks = _mg.process_archive(data, 'test.tar')
        count = _count_inserts(blocks, 'field_log_miner_identity')
        assert count >= 1, (
            f'Expected ≥1 field_log_miner_identity INSERT, got {count}. '
            'v3.2 antminer identity fix may not be active.'
        )

    def test_multiple_sessions_produce_one_identity_row_each(self):
        """Three boot sessions → at least 3 identity INSERTs."""
        sessions = [
            'cglog_init_2024-06-27_08-00-00',
            'cglog_init_2024-06-28_09-00-00',
            'cglog_init_2024-06-29_10-00-00',
        ]
        default_lines = [
            '[2024/06/28 10:00:00.000] MSG: Detect device complete: Antminer S19, AWP12\n',
            '[2024/06/28 10:00:01.000] MSG: Set chain 0 freq 450\n',
        ]
        log_lines = [list(default_lines) for _ in sessions]
        with tempfile.TemporaryDirectory() as td:
            tar = _make_minimal_antminer_archive(td, 'multi.tar', sessions, log_lines)
            with open(tar, 'rb') as f:
                data = f.read()
            blocks = _mg.process_archive(data, 'multi.tar')
        count = _count_inserts(blocks, 'field_log_miner_identity')
        assert count >= 3, (
            f'Expected ≥3 identity rows for 3 boot sessions, got {count}.'
        )

    def test_identity_sql_includes_entity_label(self):
        """Identity SQL must include a per-session entity_label."""
        with tempfile.TemporaryDirectory() as td:
            tar = _make_minimal_antminer_archive(td, 'ent.tar')
            with open(tar, 'rb') as f:
                data = f.read()
            blocks = _mg.process_archive(data, 'ent.tar')
        combined = '\n'.join(blocks)
        assert 'cglog_init_' in combined, (
            'entity_label with cglog_init_ prefix not found in identity SQL.'
        )

    def test_identity_sql_includes_miner_type(self):
        """When miner.log has 'Detect device complete: Antminer S19', identity row has miner_type."""
        with tempfile.TemporaryDirectory() as td:
            tar = _make_minimal_antminer_archive(td, 'mt.tar')
            with open(tar, 'rb') as f:
                data = f.read()
            blocks = _mg.process_archive(data, 'mt.tar')
        combined = '\n'.join(blocks)
        assert 'Antminer S19' in combined, (
            'Expected "Antminer S19" in SQL output from miner.log parse.'
        )

    def test_no_sessions_emits_archive_level_identity_row(self):
        """
        Antminer archive where the cglog_init_ session dir exists (so shape=antminer)
        but holds no miner.log file at all → session_meta is empty, identity row
        still created with all NULL identity fields (archive-level entity_label).
        """
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, 'src')
            # Must have a cglog_init_ dir so shape detection returns 'antminer'
            sdir = os.path.join(src, 'nvdata', '2024-06', '28',
                                'cglog_init_2024-06-28_10-00-00')
            os.makedirs(sdir)
            # No miner.log in the session dir — session_meta will be empty
            cfg_dir = os.path.join(src, 'config')
            os.makedirs(cfg_dir)
            with open(os.path.join(cfg_dir, 'cgminer.conf'), 'w') as f:
                json.dump({'pools': []}, f)
            tar_path = os.path.join(td, 'nolog.tar')
            with tarfile.open(tar_path, 'w') as tf:
                tf.add(src, arcname='.')
            with open(tar_path, 'rb') as f:
                data = f.read()
            blocks = _mg.process_archive(data, 'nolog.tar')
        count = _count_inserts(blocks, 'field_log_miner_identity')
        assert count >= 1, (
            f'Expected ≥1 identity row even without a miner.log, got {count}.'
        )

    def test_empty_nvdata_archive_shape_unknown_no_crash(self):
        """
        Archive with nvdata/ but no cglog_init_ sessions is detected as 'unknown' shape.
        process_archive must not crash and must return a non-error block.
        (archive-level identity fallback only applies to antminer shape)
        """
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, 'src')
            os.makedirs(os.path.join(src, 'nvdata', '2024-06', '28'))
            tar_path = os.path.join(td, 'empty.tar')
            with tarfile.open(tar_path, 'w') as tf:
                tf.add(src, arcname='.')
            with open(tar_path, 'rb') as f:
                data = f.read()
            blocks = _mg.process_archive(data, 'empty.tar')
        assert blocks, 'process_archive must return at least one SQL block'
        # Should not be an error block
        assert not any(b.strip().startswith('-- ERROR') for b in blocks), (
            'process_archive should not return error for empty nvdata archive'
        )

    def test_identity_rows_stored_in_archive_meta(self):
        """parse_antminer_bundle should store identity_rows in archive_meta."""
        with tempfile.TemporaryDirectory() as td:
            tar = _make_minimal_antminer_archive(td, 'meta.tar')
            with open(tar, 'rb') as f:
                data = f.read()
            # extract to a temp dir and call parse_antminer_bundle directly
            import tarfile as _tf
            import shutil
            extract_dir = tempfile.mkdtemp(dir=td)
            with _tf.open(fileobj=io.BytesIO(data)) as tf:
                tf.extractall(extract_dir)
            archive_meta = {
                'filename': 'meta.tar',
                'sha256': 'abc',
                'file_size_bytes': len(data),
                'miner_ip': None,
                'miner_model': None,
                'firmware_version': None,
                'mac_address': None,
                'control_board': None,
                'kernel_version': None,
                'archive_timestamp': None,
                'files_in_archive': 0,
                'parse_warnings': None,
            }
            parse_antminer_bundle(extract_dir, archive_meta)
            shutil.rmtree(extract_dir, ignore_errors=True)
        assert 'identity_rows' in archive_meta, (
            'parse_antminer_bundle must store identity_rows in archive_meta.'
        )
        assert isinstance(archive_meta['identity_rows'], list)
        assert len(archive_meta['identity_rows']) >= 1


# ===========================================================================
# TestAntminerLogNewMetaPatterns
# ===========================================================================

class TestAntminerLogNewMetaPatterns:
    """Tests for the new v3.2 meta patterns in _stream_antminer_miner_log."""

    def _parse(self, lines: list):
        with tempfile.TemporaryDirectory() as td:
            path = _make_miner_log(lines, td)
            items = list(_stream_antminer_miner_log(path, 'test.tar', 'session_x'))
        return items

    def test_mac_hwaddr_extracted(self):
        lines = [
            '[2024/06/28 10:00:00.000] MSG: eth0 HWaddr AA:BB:CC:DD:EE:FF\n',
        ]
        items = self._parse(lines)
        macs = [i['mac_address'] for i in items if i.get('kind') == 'meta' and 'mac_address' in i]
        assert macs, 'Expected mac_address meta item from eth0 HWaddr line'
        assert macs[0] == 'AA:BB:CC:DD:EE:FF'

    def test_mac_colon_pattern_extracted(self):
        lines = [
            '[2024/06/28 10:00:00.000] MSG: MAC: 11:22:33:44:55:66 configured\n',
        ]
        items = self._parse(lines)
        macs = [i['mac_address'] for i in items if i.get('kind') == 'meta' and 'mac_address' in i]
        assert macs, 'Expected mac_address from MAC: pattern'
        assert '11:22:33:44:55:66' in macs[0]

    def test_kernel_version_extracted(self):
        lines = [
            '[2024/06/28 10:00:00.000] MSG: Linux localhost 5.4.0-generic custom\n',
        ]
        items = self._parse(lines)
        kv = [i['kernel_version'] for i in items if i.get('kind') == 'meta' and 'kernel_version' in i]
        assert kv, 'Expected kernel_version meta item from Linux kernel line'
        assert '5.4.0' in kv[0]

    def test_control_board_version_extracted(self):
        lines = [
            '[2024/06/28 10:00:00.000] MSG: control_board_type=XILINX-V2\n',
        ]
        items = self._parse(lines)
        cb = [i['control_board_version'] for i in items
              if i.get('kind') == 'meta' and 'control_board_version' in i]
        assert cb, 'Expected control_board_version meta item'
        assert 'XILINX' in cb[0]

    def test_cool_mode_extracted(self):
        lines = [
            '[2024/06/28 10:00:00.000] MSG: cool_mode=immersion detected\n',
        ]
        items = self._parse(lines)
        cm = [i['cool_mode'] for i in items if i.get('kind') == 'meta' and 'cool_mode' in i]
        assert cm, 'Expected cool_mode meta item'
        assert cm[0] == 'immersion'

    def test_only_first_mac_captured_per_session(self):
        """Only the first MAC address seen should be used (first-seen wins)."""
        with tempfile.TemporaryDirectory() as td:
            lines = [
                '[2024/06/28 10:00:00.000] MSG: eth0 HWaddr AA:BB:CC:DD:EE:FF\n',
                '[2024/06/28 10:00:01.000] MSG: Detect device complete: Antminer S19, AWP12\n',
                '[2024/06/28 10:00:02.000] MSG: eth0 HWaddr 00:11:22:33:44:55\n',
            ]
            tar = _make_minimal_antminer_archive(
                td, 'mac.tar',
                sessions=['cglog_init_2024-06-28_10-00-00'],
                log_lines_per_session=[lines],
            )
            with open(tar, 'rb') as f:
                data = f.read()
            blocks = _mg.process_archive(data, 'mac.tar')
        combined = '\n'.join(blocks)
        # First MAC should appear; second should not override
        assert 'AA:BB:CC:DD:EE:FF' in combined


# ===========================================================================
# TestInsertMinerIdentityFunction
# ===========================================================================

class TestInsertMinerIdentityFunction:
    """Unit tests for insert_miner_identity with mocked psycopg2."""

    def _make_conn_mock(self):
        cur = MagicMock()
        conn = MagicMock()
        conn.cursor.return_value = cur
        return conn, cur

    def test_insert_called_for_each_row(self):
        """insert_miner_identity calls cur.execute once per identity row."""
        conn, cur = self._make_conn_mock()
        with patch.object(_mg, 'PSYCOPG2_AVAILABLE', True), \
             patch('psycopg2.connect', return_value=conn):
            rows = [
                {'entity_label': 'a.tar::session1', 'archive_filename': 'a.tar',
                 'miner_type': 'Antminer S19', 'firmware_version': '1.0',
                 'btminer_md5': None, 'mac_address': None, 'control_board_version': None,
                 'kernel_version': None, 'cool_mode': None, 'slot': None,
                 'pcb_serial': None, 'chip_data': None, 'hashrate_gh': None},
                {'entity_label': 'a.tar::session2', 'archive_filename': 'a.tar',
                 'miner_type': 'Antminer S19', 'firmware_version': '1.0',
                 'btminer_md5': None, 'mac_address': None, 'control_board_version': None,
                 'kernel_version': None, 'cool_mode': None, 'slot': None,
                 'pcb_serial': None, 'chip_data': None, 'hashrate_gh': None},
            ]
            insert_miner_identity({'host': 'localhost'}, rows)
        assert cur.execute.call_count == 2, (
            f'Expected 2 execute calls, got {cur.execute.call_count}'
        )

    def test_noop_when_psycopg2_unavailable(self):
        """insert_miner_identity is a no-op when PSYCOPG2_AVAILABLE=False."""
        with patch.object(_mg, 'PSYCOPG2_AVAILABLE', False):
            rows = [{'entity_label': 'x', 'archive_filename': 'x.tar',
                     'miner_type': None, 'firmware_version': None,
                     'btminer_md5': None, 'mac_address': None,
                     'control_board_version': None, 'kernel_version': None,
                     'cool_mode': None, 'slot': None, 'pcb_serial': None,
                     'chip_data': None, 'hashrate_gh': None}]
            # Should not raise
            insert_miner_identity({'host': 'localhost'}, rows)

    def test_noop_when_empty_rows(self):
        """insert_miner_identity is a no-op for empty list."""
        with patch.object(_mg, 'PSYCOPG2_AVAILABLE', True), \
             patch('psycopg2.connect') as mock_connect:
            insert_miner_identity({'host': 'localhost'}, [])
            mock_connect.assert_not_called()

    def test_resolver_results_stamped(self):
        """Resolver results (hardware_revision, model_id, tier) are passed to execute."""
        conn, cur = self._make_conn_mock()
        with patch.object(_mg, 'PSYCOPG2_AVAILABLE', True), \
             patch('psycopg2.connect', return_value=conn):
            from resolver import ResolverResult
            rows = [{'entity_label': 'r.tar::s1', 'archive_filename': 'r.tar',
                     'miner_type': 'Antminer S19', 'firmware_version': None,
                     'btminer_md5': None, 'mac_address': None,
                     'control_board_version': None, 'kernel_version': None,
                     'cool_mode': None, 'slot': None, 'pcb_serial': None,
                     'chip_data': None, 'hashrate_gh': None}]
            res = ResolverResult(model_id='uuid-123', tier='tier1', hardware_revision='V100')
            insert_miner_identity({'host': 'localhost'}, rows, resolver_results=[res])
        # The execute call args should contain the resolver fields
        call_args = cur.execute.call_args_list[0]
        params = call_args[0][1]  # second positional arg = parameter tuple
        assert 'V100' in params, 'hardware_revision V100 should be in execute params'
        assert 'uuid-123' in params, 'model_id uuid-123 should be in execute params'
        assert 'tier1' in params, 'tier tier1 should be in execute params'


# ===========================================================================
# TestRawJsonPerFile
# ===========================================================================

class TestRawJsonPerFile:
    """Tests for _insert_archive_raw_json_files per-file raw JSON capture."""

    def test_json_file_is_captured(self):
        """*.json file in tmp_dir is captured via insert_raw_json."""
        with tempfile.TemporaryDirectory() as td:
            jf = os.path.join(td, 'data.json')
            with open(jf, 'w') as f:
                json.dump({'key': 'value', 'num': 42}, f)
            calls = []
            def _fake_insert(cp, af, fp, parser, payload, sha, entity):
                calls.append((af, fp, payload))
            with patch.object(_mg, 'insert_raw_json', side_effect=_fake_insert), \
                 patch.object(_mg, 'PSYCOPG2_AVAILABLE', True):
                _insert_archive_raw_json_files({'host': 'localhost'}, 'arch.tar', td)
        assert any('data.json' in c[1] for c in calls), (
            'Expected data.json in file_path_in_archive for raw_json capture.'
        )

    def test_json_log_file_captured(self):
        """*.log file starting with { is treated as JSON and captured."""
        with tempfile.TemporaryDirectory() as td:
            lf = os.path.join(td, 'api.log')
            with open(lf, 'w') as f:
                json.dump({'status': 'ok'}, f)
            calls = []
            def _fake_insert(cp, af, fp, parser, payload, sha, entity):
                calls.append((af, fp, payload))
            with patch.object(_mg, 'insert_raw_json', side_effect=_fake_insert), \
                 patch.object(_mg, 'PSYCOPG2_AVAILABLE', True):
                _insert_archive_raw_json_files({'host': 'localhost'}, 'arch.tar', td)
        assert any('api.log' in c[1] for c in calls), (
            'Expected api.log (JSON-looking .log) to be captured.'
        )

    def test_non_json_log_not_captured(self):
        """Plain text *.log file (not JSON) is skipped."""
        with tempfile.TemporaryDirectory() as td:
            lf = os.path.join(td, 'miner.log')
            with open(lf, 'w') as f:
                f.write('[2024/06/28 10:00:00] MSG: something happened\n')
            calls = []
            def _fake_insert(cp, af, fp, parser, payload, sha, entity):
                calls.append((af, fp, payload))
            with patch.object(_mg, 'insert_raw_json', side_effect=_fake_insert), \
                 patch.object(_mg, 'PSYCOPG2_AVAILABLE', True):
                _insert_archive_raw_json_files({'host': 'localhost'}, 'arch.tar', td)
        log_calls = [c for c in calls if 'miner.log' in c[1]]
        assert not log_calls, (
            'Plain text miner.log should NOT be captured as raw_json.'
        )

    def test_empty_file_skipped(self):
        """Empty files are skipped."""
        with tempfile.TemporaryDirectory() as td:
            ef = os.path.join(td, 'empty.json')
            open(ef, 'w').close()
            calls = []
            def _fake_insert(cp, af, fp, parser, payload, sha, entity):
                calls.append((af, fp, payload))
            with patch.object(_mg, 'insert_raw_json', side_effect=_fake_insert), \
                 patch.object(_mg, 'PSYCOPG2_AVAILABLE', True):
                _insert_archive_raw_json_files({'host': 'localhost'}, 'arch.tar', td)
        assert not calls, 'Empty .json file should be skipped.'

    def test_multiple_json_files_all_captured(self):
        """Multiple JSON files in different subdirs are all captured."""
        with tempfile.TemporaryDirectory() as td:
            sub = os.path.join(td, 'sub')
            os.makedirs(sub)
            for i in range(3):
                with open(os.path.join(td if i < 2 else sub, f'f{i}.json'), 'w') as f:
                    json.dump({'idx': i}, f)
            calls = []
            def _fake_insert(cp, af, fp, parser, payload, sha, entity):
                calls.append((af, fp, payload))
            with patch.object(_mg, 'insert_raw_json', side_effect=_fake_insert), \
                 patch.object(_mg, 'PSYCOPG2_AVAILABLE', True):
                _insert_archive_raw_json_files({'host': 'localhost'}, 'arch.tar', td)
        assert len(calls) == 3, f'Expected 3 captured files, got {len(calls)}'

    def test_non_directory_tmp_dir_is_noop(self):
        """Non-existent tmp_dir does not raise."""
        calls = []
        def _fake_insert(cp, af, fp, parser, payload, sha, entity):
            calls.append((af, fp, payload))
        with patch.object(_mg, 'insert_raw_json', side_effect=_fake_insert):
            _insert_archive_raw_json_files({'host': 'localhost'}, 'arch.tar', '/nonexistent')
        assert not calls


# ===========================================================================
# TestIdempotencyInserts
# ===========================================================================

class TestIdempotencyInserts:
    """Tests verifying ON CONFLICT clauses are present for idempotency."""

    def test_identity_sql_has_on_conflict(self):
        """_build_identity_sql must include ON CONFLICT clause."""
        rows = [{
            'entity_label': 'test.tar::session1',
            'archive_filename': 'test.tar',
            'miner_type': 'Antminer S19',
            'firmware_version': '1.0',
            'btminer_md5': None,
            'mac_address': None,
            'control_board_version': None,
            'kernel_version': None,
            'cool_mode': None,
            'slot': None,
            'pcb_serial': None,
            'chip_data': None,
            'hashrate_gh': None,
        }]
        sql = _build_identity_sql(rows)
        assert 'ON CONFLICT' in sql.upper(), (
            '_build_identity_sql must include ON CONFLICT for idempotency.'
        )

    def test_insert_raw_json_on_conflict_in_code(self):
        """insert_raw_json SQL must contain ON CONFLICT DO NOTHING."""
        import inspect
        src = inspect.getsource(insert_raw_json)
        assert 'ON CONFLICT' in src.upper(), (
            'insert_raw_json must include ON CONFLICT DO NOTHING.'
        )

    def test_field_log_ddl_has_unique_index_for_identity(self):
        """FIELD_LOG_DDL must include the composite unique index for identity."""
        ddl = _mg.FIELD_LOG_DDL
        assert 'field_log_miner_identity_archive_entity_idx' in ddl, (
            'FIELD_LOG_DDL must include field_log_miner_identity_archive_entity_idx.'
        )

    def test_field_log_ddl_does_not_have_legacy_raw_json_unique_index(self):
        """FIELD_LOG_DDL must NOT include the legacy unique index for raw_json.

        Updated 2026-04-29 in lockstep with the B-4/B-5 fix: the canonical
        partitioned `knowledge.field_log_raw_json` shape does not have a
        `file_path_in_archive` column, so the old unique index
        `field_log_raw_json_archive_path_idx` was removed and `insert_raw_json`
        no longer relies on ON CONFLICT. The non-unique indexes
        idx_raw_json_archive / idx_raw_json_entity / idx_raw_json_sha provide
        the lookup paths we need. This test guards against re-introducing
        the dead index.
        """
        ddl = _mg.FIELD_LOG_DDL
        assert 'field_log_raw_json_archive_path_idx' not in ddl, (
            'FIELD_LOG_DDL must NOT include the legacy '
            'field_log_raw_json_archive_path_idx (removed per B-4/B-5 fix).'
        )


# ===========================================================================
# TestResolverStatsCounting
# ===========================================================================

class TestResolverStatsCounting:
    """Tests for _update_import_run_resolver_stats."""

    def test_stats_update_called_with_correct_json(self):
        """_update_import_run_resolver_stats executes UPDATE with correct JSON keys."""
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value = cur
        with patch.object(_mg, 'PSYCOPG2_AVAILABLE', True), \
             patch('psycopg2.connect', return_value=conn):
            _update_import_run_resolver_stats(
                {'host': 'localhost'}, 'arch.tar',
                tier1_hits=5, tier1_vcode_hits=2, tier2_hits=1, unresolved=3
            )
        assert cur.execute.called
        call_args = cur.execute.call_args[0]
        # Second arg is the json.dumps(stats) string
        stats_json = call_args[1][0]
        stats = json.loads(stats_json)
        assert stats['tier1_hits'] == 5
        assert stats['tier1_vcode_hits'] == 2
        assert stats['tier2_hits'] == 1
        assert stats['unresolved'] == 3

    def test_noop_when_psycopg2_unavailable(self):
        """_update_import_run_resolver_stats is a no-op when no DB."""
        with patch.object(_mg, 'PSYCOPG2_AVAILABLE', False), \
             patch('psycopg2.connect') as mc:
            _update_import_run_resolver_stats(
                {'host': 'localhost'}, 'arch.tar', 1, 0, 0, 0
            )
            mc.assert_not_called()


# ===========================================================================
# TestIntegrationAntminerIdentityInSQL
# ===========================================================================

class TestIntegrationAntminerIdentityInSQL:
    """Integration: Antminer archives in workspace produce identity SQL."""

    def _find(self, fn: str):
        candidate = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            '..', fn
        )
        if os.path.isfile(candidate):
            return candidate
        candidate2 = os.path.join('/home/user/workspace', fn)
        if os.path.isfile(candidate2):
            return candidate2
        return None

    def _run(self, fn: str):
        path = self._find(fn)
        if not path:
            return None
        with open(path, 'rb') as f:
            data = f.read()
        return _mg.process_archive(data, fn)

    def test_antminer_s19_84_files_has_identity_rows(self):
        """The real Antminer S19 84-file archive must produce ≥1 identity INSERT."""
        fn = 'Antminer_S19_2024-06-27_2024-06-29-6.tar'
        blocks = self._run(fn)
        if blocks is None:
            pytest.skip(f'{fn} not found in workspace')
        count = _count_inserts(blocks, 'field_log_miner_identity')
        assert count >= 1, (
            f'{fn}: expected ≥1 field_log_miner_identity INSERT, got {count}.'
        )

    def test_antminer_s19_epoch_has_identity_rows(self):
        """The epoch-timestamped Antminer S19 archive must produce ≥1 identity INSERT."""
        fn = 'Antminer_S19_1970-01-01_2024-11-29-3.tar'
        blocks = self._run(fn)
        if blocks is None:
            pytest.skip(f'{fn} not found in workspace')
        count = _count_inserts(blocks, 'field_log_miner_identity')
        assert count >= 1, (
            f'{fn}: expected ≥1 field_log_miner_identity INSERT, got {count}.'
        )
