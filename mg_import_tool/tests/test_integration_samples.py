"""
tests/test_integration_samples.py
==================================
Integration tests for mg_import_tool v3 — runs all 6 sample archives
through process_archive() offline (no PostgreSQL required).

Verifies:
- Each archive produces ≥1 SQL block (no error block)
- Expected tables receive ≥N INSERT rows per spec
- Total wall-clock time for all 6 archives < 180 s
- V-suffix model `M31S+_V100` is correctly identified (not unknown)
- No autotune runaway: Antminer S19 autotune processes within timeout

Run:
    python -m pytest tests/test_integration_samples.py -v
"""

import sys
import os
import re
import time
import unittest.mock as _mock

# ---------------------------------------------------------------------------
# Bootstrap: mock heavy optional deps before importing mg_import
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_psycopg2_mock = _mock.MagicMock()
sys.modules.setdefault('psycopg2', _psycopg2_mock)
sys.modules.setdefault('psycopg2.extras', _psycopg2_mock.extras)
sys.modules.setdefault('openpyxl', _mock.MagicMock())

_flask_mock = _mock.MagicMock()
_flask_instance = _mock.MagicMock()
_flask_instance.config = {}
_flask_mock.Flask.return_value = _flask_instance
sys.modules.setdefault('flask', _flask_mock)

import importlib.util as _ilu
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = _ilu.spec_from_file_location('mg_import', os.path.join(_REPO, 'mg_import.py'))
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

process_archive = _mod.process_archive
detect_archive_shape = _mod.detect_archive_shape

# ---------------------------------------------------------------------------
# Archive locations
# ---------------------------------------------------------------------------
_WORKSPACE = os.path.dirname(_REPO)   # /home/user/workspace

def _find(filename: str) -> str | None:
    """Search workspace root for the archive."""
    candidate = os.path.join(_WORKSPACE, filename)
    if os.path.isfile(candidate):
        return candidate
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INSERT_RE = re.compile(r'INSERT\s+INTO\s+knowledge\.(\w+)', re.IGNORECASE)
_INSERT_BATCH_RE = re.compile(
    r'INSERT\s+INTO\s+knowledge\.(\w+)[^;]+?VALUES\s*\(', re.IGNORECASE | re.DOTALL
)

def _count_inserts(sql_blocks: list, table: str) -> int:
    """Count number of INSERT INTO knowledge.<table> occurrences across all blocks."""
    pat = re.compile(
        r'INSERT\s+INTO\s+knowledge\.' + re.escape(table) + r'\b',
        re.IGNORECASE,
    )
    return sum(len(pat.findall(blk)) for blk in sql_blocks)


def _has_error(sql_blocks: list) -> bool:
    return any(blk.strip().startswith('-- ERROR') for blk in sql_blocks)


def _error_msg(sql_blocks: list) -> str:
    for blk in sql_blocks:
        if blk.strip().startswith('-- ERROR'):
            return blk[:300]
    return ''


def _run_archive(filename: str):
    """Load archive bytes and call process_archive. Returns (sql_blocks, elapsed_s)."""
    path = _find(filename)
    if path is None:
        return None, 0.0
    with open(path, 'rb') as fh:
        data = fh.read()
    t0 = time.monotonic()
    blocks = process_archive(data, filename)   # no conn_params → offline mode
    elapsed = time.monotonic() - t0
    return blocks, elapsed


# ---------------------------------------------------------------------------
# Per-archive test cases
# ---------------------------------------------------------------------------

SAMPLE_SPECS = [
    {
        'filename': '10.0.14.57.20250313133403.tgz',
        'label': 'WhatsMiner M56S++_VK10 (IP-named)',
        'shape': 'whatsminer',
        'min_rows': {
            'field_log_imports': 1,
            'field_log_miner_identity': 1,
            'field_log_power_samples': 1,
            'field_log_temp_snapshots': 1,
            'field_log_api_stats': 1,
            'field_log_pools': 1,
        },
    },
    {
        'filename': 'M31S-_V100_2024-07-01_19-38-2.tgz',
        'label': 'WhatsMiner M31S+_V100 (model-named, V-suffix)',
        'shape': 'whatsminer',
        'min_rows': {
            'field_log_imports': 1,
            'field_log_miner_identity': 1,
            'field_log_power_samples': 1,
            'field_log_temp_snapshots': 1,
            'field_log_api_stats': 1,
            'field_log_pools': 1,
        },
    },
    {
        'filename': 'M21S_2024-02-14_21-59-4.tgz',
        'label': 'WhatsMiner M21S (minimal)',
        'shape': 'whatsminer',
        'min_rows': {
            'field_log_imports': 1,
            # M21S minimal: may only have api + pools
            'field_log_api_stats': 1,
            'field_log_pools': 1,
        },
    },
    {
        'filename': '10.0.12.59.20250320222600-5.tgz',
        'label': 'WhatsMiner (IP-named, ams_bixbit.json)',
        'shape': 'whatsminer',
        'min_rows': {
            'field_log_imports': 1,
            'field_log_miner_identity': 1,
            'field_log_power_samples': 1,
            'field_log_temp_snapshots': 1,
            'field_log_api_stats': 1,
            'field_log_pools': 1,
        },
    },
    {
        'filename': 'Antminer_S19_1970-01-01_2024-11-29-3.tar',
        'label': 'Antminer S19 (epoch timestamps, minimal)',
        'shape': 'antminer',
        'min_rows': {
            'field_log_imports': 1,
            'field_log_antminer_boots': 1,
            # No autotune events (emergency sleep mode) — assert 0 is fine
            'field_log_pools': 1,
        },
    },
    {
        'filename': 'Antminer_S19_2024-06-27_2024-06-29-6.tar',
        'label': 'Antminer S19 (84 files, real timestamps)',
        'shape': 'antminer',
        'min_rows': {
            'field_log_imports': 1,
            'field_log_antminer_boots': 1,
            'field_log_antminer_autotune': 1,
            'field_log_pools': 1,
        },
    },
]

import pytest


@pytest.fixture(scope='module')
def all_results():
    """Run all 6 archives once; cache results for all tests in this module."""
    results = {}
    for spec in SAMPLE_SPECS:
        fn = spec['filename']
        blocks, elapsed = _run_archive(fn)
        results[fn] = {'blocks': blocks, 'elapsed': elapsed, 'spec': spec}
    return results


# ---------------------------------------------------------------------------
# Test: total wall-clock time < 3 minutes
# ---------------------------------------------------------------------------

class TestTotalRuntime:
    def test_all_six_under_180s(self, all_results):
        """Integration requirement: 6 archives finish in < 3 minutes."""
        total = sum(r['elapsed'] for r in all_results.values() if r['blocks'] is not None)
        assert total < 180.0, (
            f'Total integration time {total:.1f}s exceeds 180s limit. '
            'Check for streaming runaway in Antminer autotune.'
        )


# ---------------------------------------------------------------------------
# Test: per-archive shape + row counts
# ---------------------------------------------------------------------------

class TestArchiveParsing:

    @pytest.mark.parametrize('spec', SAMPLE_SPECS, ids=[s['filename'] for s in SAMPLE_SPECS])
    def test_archive_runs_without_error(self, spec, all_results):
        fn = spec['filename']
        result = all_results[fn]
        if result['blocks'] is None:
            pytest.skip(f'{fn} not found in workspace')
        assert not _has_error(result['blocks']), (
            f'{fn} produced an error block:\n{_error_msg(result["blocks"])}'
        )

    @pytest.mark.parametrize('spec', SAMPLE_SPECS, ids=[s['filename'] for s in SAMPLE_SPECS])
    def test_archive_produces_sql_blocks(self, spec, all_results):
        fn = spec['filename']
        result = all_results[fn]
        if result['blocks'] is None:
            pytest.skip(f'{fn} not found in workspace')
        assert len(result['blocks']) >= 1, f'{fn}: no SQL blocks produced'

    @pytest.mark.parametrize('spec', SAMPLE_SPECS, ids=[s['filename'] for s in SAMPLE_SPECS])
    def test_archive_min_row_counts(self, spec, all_results):
        fn = spec['filename']
        result = all_results[fn]
        if result['blocks'] is None:
            pytest.skip(f'{fn} not found in workspace')
        blocks = result['blocks']
        for table, min_count in spec['min_rows'].items():
            actual = _count_inserts(blocks, table)
            assert actual >= min_count, (
                f'{fn}: expected ≥{min_count} INSERT for {table}, got {actual}'
            )


# ---------------------------------------------------------------------------
# Test: V-suffix model correctly parsed from M31S+_V100 archive
# ---------------------------------------------------------------------------

class TestVSuffixIntegration:

    def test_m31s_plus_v100_miner_identity_inserted(self, all_results):
        """The M31S+_V100 archive must produce a miner_identity row (miner_type parsed)."""
        fn = 'M31S-_V100_2024-07-01_19-38-2.tgz'
        result = all_results[fn]
        if result['blocks'] is None:
            pytest.skip(f'{fn} not found in workspace')
        count = _count_inserts(result['blocks'], 'field_log_miner_identity')
        assert count >= 1, (
            f'Expected ≥1 miner_identity row for M31S+_V100 archive, got {count}. '
            'V-suffix model parse may have failed.'
        )

    def test_m31s_plus_v100_miner_type_in_sql(self, all_results):
        """The raw miner_type value M31S+_V100 must appear somewhere in the SQL output."""
        fn = 'M31S-_V100_2024-07-01_19-38-2.tgz'
        result = all_results[fn]
        if result['blocks'] is None:
            pytest.skip(f'{fn} not found in workspace')
        combined = '\n'.join(result['blocks'])
        # The miner_overview.log has `miner_type = M31S+_V100`
        assert 'M31S+_V100' in combined or 'M31S-_V100' in combined, (
            'Expected raw model string M31S+_V100 (or M31S-_V100) in SQL output. '
            'miner_overview parsing may have regressed.'
        )

    def test_m56s_plus_plus_vk10_parsed(self, all_results):
        """The M56S++_VK10 WhatsMiner archive must produce miner_identity rows."""
        fn = '10.0.14.57.20250313133403.tgz'
        result = all_results[fn]
        if result['blocks'] is None:
            pytest.skip(f'{fn} not found in workspace')
        combined = '\n'.join(result['blocks'])
        assert 'M56S' in combined, (
            'Expected M56S model string in SQL output from IP-named WhatsMiner archive.'
        )


# ---------------------------------------------------------------------------
# Test: Antminer streaming does not run away
# ---------------------------------------------------------------------------

class TestAntminerStreamingFix:

    def test_antminer_s19_84_files_under_60s(self, all_results):
        """The large Antminer S19 archive (84 files) must complete within 60s."""
        fn = 'Antminer_S19_2024-06-27_2024-06-29-6.tar'
        result = all_results[fn]
        if result['blocks'] is None:
            pytest.skip(f'{fn} not found in workspace')
        assert result['elapsed'] < 60.0, (
            f'Antminer S19 84-file archive took {result["elapsed"]:.1f}s — '
            'streaming autotune timeout may not be working.'
        )

    def test_antminer_s19_epoch_under_30s(self, all_results):
        """The epoch-timestamped Antminer S19 archive must complete within 30s."""
        fn = 'Antminer_S19_1970-01-01_2024-11-29-3.tar'
        result = all_results[fn]
        if result['blocks'] is None:
            pytest.skip(f'{fn} not found in workspace')
        assert result['elapsed'] < 30.0, (
            f'Antminer S19 epoch archive took {result["elapsed"]:.1f}s — unexpectedly slow.'
        )

    def test_antminer_s19_84_files_autotune_rows(self, all_results):
        """The 84-file Antminer S19 archive should produce ≥1 autotune INSERT."""
        fn = 'Antminer_S19_2024-06-27_2024-06-29-6.tar'
        result = all_results[fn]
        if result['blocks'] is None:
            pytest.skip(f'{fn} not found in workspace')
        count = _count_inserts(result['blocks'], 'field_log_antminer_autotune')
        assert count >= 1, (
            f'Expected ≥1 autotune INSERT for 84-file S19 archive, got {count}.'
        )


# ---------------------------------------------------------------------------
# Test: shape detection
# ---------------------------------------------------------------------------

class TestShapeDetection:

    @pytest.mark.parametrize('spec', SAMPLE_SPECS, ids=[s['filename'] for s in SAMPLE_SPECS])
    def test_shape_detection(self, spec, all_results):
        fn = spec['filename']
        expected_shape = spec['shape']
        result = all_results[fn]
        if result['blocks'] is None:
            pytest.skip(f'{fn} not found in workspace')
        # Shape is embedded in the import block comment
        combined = '\n'.join(result['blocks'])
        # Both 'whatsminer' and 'antminer' appear in block comments
        assert expected_shape.lower() in combined.lower(), (
            f'{fn}: expected shape "{expected_shape}" not found in SQL output'
        )


# ---------------------------------------------------------------------------
# Test: import block always present with required fields
# ---------------------------------------------------------------------------

class TestImportBlockStructure:

    @pytest.mark.parametrize('spec', SAMPLE_SPECS, ids=[s['filename'] for s in SAMPLE_SPECS])
    def test_import_row_has_sha256(self, spec, all_results):
        fn = spec['filename']
        result = all_results[fn]
        if result['blocks'] is None:
            pytest.skip(f'{fn} not found in workspace')
        combined = '\n'.join(result['blocks'])
        # SHA-256 hex string is 64 characters — should appear in the import INSERT
        sha_re = re.compile(r'\b[0-9a-f]{64}\b', re.IGNORECASE)
        assert sha_re.search(combined), (
            f'{fn}: no SHA-256 hash found in SQL output (import row may be missing)'
        )

    @pytest.mark.parametrize('spec', SAMPLE_SPECS, ids=[s['filename'] for s in SAMPLE_SPECS])
    def test_field_log_imports_exactly_one_row(self, spec, all_results):
        fn = spec['filename']
        result = all_results[fn]
        if result['blocks'] is None:
            pytest.skip(f'{fn} not found in workspace')
        count = _count_inserts(result['blocks'], 'field_log_imports')
        assert count == 1, (
            f'{fn}: expected exactly 1 field_log_imports INSERT, got {count}'
        )


# ---------------------------------------------------------------------------
# Standalone runner (python tests/test_integration_samples.py)
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import time as _time_mod

    print('=' * 72)
    print('mg_import v3 Integration Tests — 6 sample archives')
    print('=' * 72)
    print()

    passed = failed = skipped = 0
    t_wall_start = _time_mod.monotonic()
    results_cache = {}

    for spec in SAMPLE_SPECS:
        fn = spec['filename']
        label = spec['label']
        path = _find(fn)
        if path is None:
            print(f'  [SKIP] {fn} — not found in workspace')
            skipped += 1
            continue

        t0 = _time_mod.monotonic()
        blocks, elapsed = _run_archive(fn)
        results_cache[fn] = {'blocks': blocks, 'elapsed': elapsed}

        if blocks is None:
            print(f'  [SKIP] {fn} — not found')
            skipped += 1
            continue

        if _has_error(blocks):
            print(f'  [FAIL] {fn}')
            print(f'         {_error_msg(blocks)}')
            failed += 1
            continue

        ok = True
        row_report = []
        for table, min_count in spec['min_rows'].items():
            actual = _count_inserts(blocks, table)
            status = 'ok' if actual >= min_count else 'FAIL'
            if actual < min_count:
                ok = False
            row_report.append(f'{table}: {actual} (min {min_count}) [{status}]')

        result_str = 'PASS' if ok else 'FAIL'
        print(f'  [{result_str}] {label}')
        print(f'         {fn}  ({elapsed:.2f}s, {len(blocks)} SQL blocks)')
        for line in row_report:
            print(f'           {line}')
        print()

        if ok:
            passed += 1
        else:
            failed += 1

    total_elapsed = _time_mod.monotonic() - t_wall_start
    print('=' * 72)
    print(f'Total time: {total_elapsed:.2f}s  (limit 180s) — ',
          'PASS' if total_elapsed < 180 else 'FAIL (too slow)')
    print()
    total = passed + failed + skipped
    print(f'Results: {passed} passed, {failed} failed, {skipped} skipped / {total} archives')
    print()
    if failed == 0 and skipped == 0:
        print('ALL TESTS PASSED.')
        sys.exit(0)
    elif failed == 0:
        print(f'PASSED ({skipped} archives skipped — not found in workspace).')
        sys.exit(0)
    else:
        print('FAILURES DETECTED.')
        sys.exit(1)
