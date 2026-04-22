#!/usr/bin/env python3
"""
tools/test_archive_parsers.py
------------------------------
Offline test for mg_import archive parsers.

Runs all 6 sample archives through process_archive(), counts SQL INSERT rows
per target table, asserts non-empty results, and prints a summary.

No PostgreSQL connection is needed — parsers generate SQL strings; this
script inspects those strings directly.

Usage:
    python tools/test_archive_parsers.py

Expected sample archives (workspace root or LOG_ARCHIVES_DIR):
    10.0.14.57.20250313133403.tgz        WhatsMiner M56S++_VK10, IP-named
    M31S-_V100_2024-07-01_19-38-2.tgz   WhatsMiner M31S+_V100, model-named
    M21S_2024-02-14_21-59-4.tgz         WhatsMiner (minimal, 6 files)
    10.0.12.59.20250320222600-5.tgz      WhatsMiner (IP-named, ams_bixbit.json)
    Antminer_S19_1970-01-01_2024-11-29-3.tar   Antminer S19, nvdata tree
    Antminer_S19_2024-06-27_2024-06-29-6.tar   Antminer S19, nvdata tree 84 files
"""

import sys
import os
import re

# Allow running from within the tools/ subdir or from the repo root
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _REPO_ROOT)

# Import the archive processing functions directly (no Flask server needed)
# We do a targeted import of the archive-specific functions
import importlib.util

spec = importlib.util.spec_from_file_location(
    'mg_import',
    os.path.join(_REPO_ROOT, 'mg_import.py')
)
_mod = importlib.util.module_from_spec(spec)
# Stub out psycopg2 and flask to allow import without running the server
import unittest.mock as _mock
sys.modules.setdefault('psycopg2', _mock.MagicMock())
sys.modules.setdefault('psycopg2.extras', _mock.MagicMock())
sys.modules.setdefault('openpyxl', _mock.MagicMock())

# Flask mock that captures route registrations but doesn't do anything
_flask_mock = _mock.MagicMock()
_flask_instance = _mock.MagicMock()
_flask_instance.config = {}
_flask_mock.Flask.return_value = _flask_instance
sys.modules.setdefault('flask', _flask_mock)

spec.loader.exec_module(_mod)

process_archive = _mod.process_archive
detect_archive_shape = _mod.detect_archive_shape

# ---------------------------------------------------------------------------
# Sample archive locations
# ---------------------------------------------------------------------------
WORKSPACE = os.path.dirname(_REPO_ROOT)  # /home/user/workspace
LOG_ARCHIVES_DIR = os.path.join(WORKSPACE, '')  # archives live in workspace root

SAMPLE_ARCHIVES = [
    {
        'filename': '10.0.14.57.20250313133403.tgz',
        'expected_shape': 'whatsminer',
        'expected_tables': {
            'field_log_imports': 1,
            'field_log_miner_identity': 1,   # at least 1 slot
            'field_log_power_samples': 1,
            'field_log_temp_snapshots': 1,
            'field_log_api_stats': 1,
            'field_log_pools': 1,
        },
    },
    {
        'filename': 'M31S-_V100_2024-07-01_19-38-2.tgz',
        'expected_shape': 'whatsminer',
        'expected_tables': {
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
        'expected_shape': 'whatsminer',
        'expected_tables': {
            'field_log_imports': 1,
            # M21S has miner.log (not miner_overview.log), api.log, pools.log
            'field_log_api_stats': 1,
            'field_log_pools': 1,
        },
    },
    {
        'filename': '10.0.12.59.20250320222600-5.tgz',
        'expected_shape': 'whatsminer',
        'expected_tables': {
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
        'expected_shape': 'antminer',
        'expected_tables': {
            'field_log_imports': 1,
            'field_log_antminer_boots': 1,
            # This archive entered emergency sleep mode — no freq_set events fire.
            # Autotune rows = 0 is legitimate. Do not assert > 0.
            'field_log_pools': 1,
        },
    },
    {
        'filename': 'Antminer_S19_2024-06-27_2024-06-29-6.tar',
        'expected_shape': 'antminer',
        'expected_tables': {
            'field_log_imports': 1,
            'field_log_antminer_boots': 1,
            'field_log_antminer_autotune': 1,
            'field_log_pools': 1,
        },
    },
]

# All 8 archive-specific tables
ALL_TABLES = [
    'field_log_imports',
    'field_log_miner_identity',
    'field_log_power_samples',
    'field_log_temp_snapshots',
    'field_log_pools',
    'field_log_api_stats',
    'field_log_antminer_boots',
    'field_log_antminer_autotune',
    'field_log_events',
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def count_inserts_for_table(sql_blocks: list, table_name: str) -> int:
    """Count INSERT INTO knowledge.<table_name> statements across all SQL blocks."""
    pattern = re.compile(
        r'INSERT INTO knowledge\.' + re.escape(table_name) + r'\b',
        re.IGNORECASE
    )
    total = 0
    for block in sql_blocks:
        total += len(pattern.findall(block))
    return total


def find_archive(filename: str) -> str:
    """Locate a sample archive file — try workspace root and log_archives dir."""
    candidates = [
        os.path.join(WORKSPACE, filename),
        os.path.join(WORKSPACE, 'log_archives', filename),
        os.path.join(LOG_ARCHIVES_DIR, filename),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def has_error_block(sql_blocks: list) -> bool:
    """Return True if any block starts with '-- ERROR'."""
    return any(b.strip().startswith('-- ERROR') for b in sql_blocks)


# ---------------------------------------------------------------------------
# Truncated archive test
# ---------------------------------------------------------------------------

def test_truncated_archive():
    """Verify that a 29-byte truncated archive fails cleanly with a clear error."""
    print('\n--- Test: truncated archive (29 bytes) ---')
    fake_bytes = b'PK' + b'\x00' * 27  # 29 bytes, not a valid tar/tgz
    result = process_archive(fake_bytes, 'M30S_V31_2024-07-11_10-06.tgz')
    assert result, 'Expected at least one result block'
    first = result[0]
    assert first.startswith('-- ERROR'), (
        f'Expected error block for truncated archive, got: {first[:200]!r}'
    )
    print(f'  PASS — truncated archive fails cleanly: {first[:120]!r}')
    return True


# ---------------------------------------------------------------------------
# Shape detection test
# ---------------------------------------------------------------------------

def test_shape_detection():
    """Verify detect_archive_shape correctly identifies the two shapes."""
    print('\n--- Test: shape detection ---')
    wm_names = ['10.0.14.57.logs/', '10.0.14.57.logs/miner_overview.log',
                '10.0.14.57.logs/power.log']
    am_names = ['nvdata/2024-06/29/', 'nvdata/2024-06/29/cglog_init_2024-06-29_00-00-00/',
                'nvdata/2024-06/29/cglog_init_2024-06-29_00-00-00/miner.log']
    unk_names = ['random_file.txt', 'data/output.csv']

    assert detect_archive_shape(wm_names) == 'whatsminer', 'Failed WhatsMiner detection'
    assert detect_archive_shape(am_names) == 'antminer', 'Failed Antminer detection'
    assert detect_archive_shape(unk_names) == 'unknown', 'Failed unknown detection'
    print('  PASS — shape detection correct for all 3 cases')
    return True


# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------

def run_tests():
    passed = 0
    failed = 0
    results_summary = []

    print('=' * 72)
    print('mg_import Archive Parser Tests — offline (no PostgreSQL)')
    print('=' * 72)

    # Shape detection
    try:
        test_shape_detection()
        passed += 1
    except Exception as e:
        print(f'  FAIL — shape detection: {e}')
        failed += 1

    # Truncated archive
    try:
        test_truncated_archive()
        passed += 1
    except Exception as e:
        print(f'  FAIL — truncated archive: {e}')
        failed += 1

    print()

    # Per-archive tests
    for spec in SAMPLE_ARCHIVES:
        filename = spec['filename']
        expected_shape = spec['expected_shape']
        expected_tables = spec['expected_tables']

        path = find_archive(filename)
        if path is None:
            print(f'[SKIP] {filename} — not found in workspace')
            results_summary.append({'filename': filename, 'status': 'SKIP', 'counts': {}})
            continue

        print(f'\n--- {filename} ({os.path.getsize(path):,} bytes) ---')

        try:
            with open(path, 'rb') as f:
                file_bytes = f.read()

            sql_blocks = process_archive(file_bytes, filename)
            assert sql_blocks, 'process_archive returned empty list'

            if has_error_block(sql_blocks):
                error_block = next(b for b in sql_blocks if b.strip().startswith('-- ERROR'))
                print(f'  ERROR block: {error_block[:200]}')
                failed += 1
                results_summary.append({'filename': filename, 'status': 'FAIL', 'counts': {}})
                continue

            # Count rows per table
            counts = {table: count_inserts_for_table(sql_blocks, table) for table in ALL_TABLES}

            print(f'  Shape: {expected_shape}')
            print(f'  SQL blocks generated: {len(sql_blocks)}')
            print()
            col_w = max(len(t) for t in ALL_TABLES) + 2
            print(f'  {"Table":<{col_w}} {"Rows":>6}  {"Expected":>9}  Status')
            print(f'  {"-"*col_w}  {"-"*6}  {"-"*9}  ------')

            archive_passed = True
            for table in ALL_TABLES:
                count = counts[table]
                min_expected = expected_tables.get(table, 0)
                ok = count >= min_expected
                status = 'PASS' if ok else 'FAIL'
                if not ok:
                    archive_passed = False
                marker = '' if ok else ' <-- FAIL'
                print(f'  {table:<{col_w}} {count:>6}  {min_expected:>9}  {status}{marker}')

            if archive_passed:
                passed += 1
                results_summary.append({'filename': filename, 'status': 'PASS', 'counts': counts})
                print(f'\n  Result: PASS')
            else:
                failed += 1
                results_summary.append({'filename': filename, 'status': 'FAIL', 'counts': counts})
                print(f'\n  Result: FAIL')

        except Exception as e:
            import traceback
            print(f'  EXCEPTION: {e}')
            traceback.print_exc()
            failed += 1
            results_summary.append({'filename': filename, 'status': 'FAIL', 'counts': {}})

    # Final summary
    print()
    print('=' * 72)
    print('SUMMARY')
    print('=' * 72)
    col_w = max(len(r['filename']) for r in results_summary) + 2 if results_summary else 40
    for r in results_summary:
        fn = r['filename']
        status = r['status']
        if status == 'PASS':
            print(f'  PASS  {fn}')
        elif status == 'SKIP':
            print(f'  SKIP  {fn}')
        else:
            print(f'  FAIL  {fn}')
    print()
    total = passed + failed
    print(f'Tests passed: {passed}/{total}')
    if failed:
        print(f'Tests failed: {failed}/{total}')
        print()
        print('FAIL — one or more tests did not pass.')
        sys.exit(1)
    else:
        print()
        print('ALL TESTS PASSED.')
        sys.exit(0)


if __name__ == '__main__':
    run_tests()
