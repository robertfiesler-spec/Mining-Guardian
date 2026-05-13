"""
tests/test_p038_no_slice_on_timestamp_fields.py

P-038 cohort guard test (2026-05-13).

The W16 timestamptz migration (PR #178) replaced TO_CHAR(NOW(...)) SQL
casts with native timestamptz returns. After W16, psycopg2 returns
`datetime.datetime` objects for timestamp columns instead of strings.
Any legacy `row["col"][:16]` or `row.get("col", "")[:16]` slice pattern
crashes with:

    TypeError: 'datetime.datetime' object is not subscriptable

Bug history:
- P-038 item #5 (2026-05-11): caught `train_comprehensive.py:290` —
  `s.get('last_seen', '')[:16]` crashed weekly training.
- 2026-05-12 daily_deep_dive natural fire: caught
  `daily_deep_dive.py:652` — `r.get('restarted_at', '%s')[:16]` crashed
  16:25 CDT on miner 19/69, leaving the deep dive partially complete
  for 16 days running.
- 2026-05-13 cohort sweep PR #206: this test landed alongside fixes
  for 8 sites across 3 files (daily_deep_dive.py, train_comprehensive.py,
  slack_command_handler.py).

Canonical fix pattern: `from core.dt_format import fmt_dt; fmt_dt(value)`.
`fmt_dt` accepts datetime, str, None, or anything else; always returns
a string; never raises.

Scope of the guard.
The grep matches any string-slice operator applied to a dict access whose
KEY contains common timestamp suffixes/prefixes (`_at`, `_time`,
`timestamp`, `_dt`, `last_seen`, `first_seen`, `recorded_at`,
`collected_at`, `scanned_at`, `restarted_at`, `analyzed_at`, `ingested_at`,
`updated_at`, `created_at`). False positives that look like timestamp
columns but are not (e.g. `timeout`, `last_*` non-temporal) are
explicitly listed in `KNOWN_FALSE_POSITIVES` below.

Allowed places this pattern can still legitimately appear:
- `core/dt_format.py` — the canonical helper, references the pattern
  in its own docstring as an example of the legacy bug.
- `scripts/inspect_training.py` — reads from `knowledge.json` only;
  values are JSON-encoded ISO 8601 strings (datetime.isoformat()).
- This test file itself.

When the guard fires, the fix is almost always:
1. `from core.dt_format import fmt_dt` (the import may already exist).
2. Replace `row["col"][:N]` with `fmt_dt(row["col"], length=N)`.
3. Replace `row.get("col", "")[:N]` with `fmt_dt(row.get("col"), length=N)`.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Timestamp-like dict-key fragments. The regex below matches `["key"]` or
# `.get("key", ...)` where the key contains any of these substrings.
TIMESTAMP_KEY_FRAGMENTS = (
    "_at",
    "_time",
    "timestamp",
    "_dt",
    "last_seen",
    "first_seen",
    "recorded_at",
    "collected_at",
    "scanned_at",
    "restarted_at",
    "analyzed_at",
    "ingested_at",
    "updated_at",
    "created_at",
    "log_timestamp",
)

# Files where the pattern is legitimate (canonical helper or JSON-only).
ALLOWED_FILES = {
    "core/dt_format.py",  # canonical helper — docstring example
    "scripts/inspect_training.py",  # knowledge.json reader — JSON strings
    "tests/test_p038_no_slice_on_timestamp_fields.py",  # this file
    "tests/test_p038_datetime_slicing.py",  # PR #178 test — docstring includes pre-fix pattern as history
}

# Directories whose contents are dead code (one-time patches, archived
# experiments, fix scripts that were merged long ago). They still live in
# the repo for historical reference but are NEVER imported by the running
# system. The cohort guard skips them; the PR #208 follow-up will either
# delete them outright or sweep them too.
ALLOWED_DIR_PREFIXES = (
    "archive/",
    "fixes/",
)

# PR #207 (2026-05-13) closed out the DEFERRED_TO_PR_207 set —
# api/dashboard_api.py (12 sites) + api/ai_dashboard_api.py (2 sites)
# all converted to fmt_dt(). Set kept empty for traceability; if a future
# PR needs to defer files again, the mechanism is right here.
DEFERRED_TO_PR_207 = set()

# Specific lines that look like a timestamp slice but aren't (false
# positives in the regex). Format: "<relpath>:<exact match text>".
# Keep this list short — every entry is a paper trail that demands
# explanation. If you find yourself adding more than a handful, the
# regex needs refinement, not more exceptions.
KNOWN_FALSE_POSITIVES = {
    # api/ai_dashboard_api.py L173: `sorted(preds, key=lambda x: x.get(
    # "predicted_at", ""), reverse=True)[:15]` — `[:15]` here slices the
    # LIST to its first 15 elements, not a string. The regex falsely
    # matches because `predicted_at` is timestamp-like and `[:15]` is a
    # slice within the lookback window. Format: "<relpath>:<exact code substring>".
    'api/ai_dashboard_api.py:preds = sorted(preds, key=lambda x: x.get("predicted_at", ""), reverse=True)[:15]',
}


def _git_tracked_python_files() -> list[Path]:
    """Files git would actually ship in a build. Avoids site-packages,
    .venv, generated files."""
    out = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [REPO_ROOT / line for line in out.splitlines() if line]


# Pattern matches the SLICE first, then we look BACKWARD up to ~60 chars
# for the closest dict-access whose key looks timestamp-like. This avoids
# false positives where two dict-accesses appear on one line and the wrong
# one is the timestamp (e.g. `e['board_index'] ... e['first'][:16]`).
_SLICE_AT_END_RE = re.compile(
    r"""
    (?P<lookback> [^\n]{0,60}? )                              # up to ~60 chars before
    (?:
        \[ \s* : \s* \d+ \s* \]                              # [:N]
        |
        \[ \s* \d+ \s* : \s* \d+ \s* \]                      # [N:M]
    )
    """,
    re.VERBOSE,
)

# Within the lookback window, find the *last* dict access (closest to the slice).
_DICT_ACCESS_RE = re.compile(
    r"""
    (?:
        \[ \s* ["'] (?P<key1> [a-zA-Z_][a-zA-Z0-9_]* ) ["'] \s* \]   # dict["key"]
        |
        \.get\( \s* ["'] (?P<key2> [a-zA-Z_][a-zA-Z0-9_]* ) ["'] [^)]* \)  # dict.get("key"...)
    )
    """,
    re.VERBOSE,
)

# Calls whose RESULT is safe to slice. These return `str`, so slicing the
# output is fine. Match the function-call shape immediately before the slice.
_SAFE_RESULT_PATTERNS = (
    re.compile(r"fmt_dt\([^)]*\)\s*$"),   # fmt_dt(x) returns str — slice is safe
    re.compile(r"\.isoformat\(\)\s*$"),    # x.isoformat() returns str
    re.compile(r"\.strftime\([^)]*\)\s*$"), # x.strftime(...) returns str
    re.compile(r"str\([^)]*\)\s*$"),       # str(x) returns str
)


def _key_is_timestamp_like(key: str) -> bool:
    """Return True if the dict key name looks like a timestamp column."""
    key_lower = key.lower()
    return any(frag in key_lower for frag in TIMESTAMP_KEY_FRAGMENTS)


def test_no_slice_on_timestamp_dict_keys() -> None:
    """No string-slice on dict accesses to timestamp-like columns.

    Replaces every legacy `row["col"][:N]` with `fmt_dt(row["col"], length=N)`
    from `core.dt_format`. See module docstring for the full history.
    """
    violations: list[str] = []

    for py_file in _git_tracked_python_files():
        rel = py_file.relative_to(REPO_ROOT).as_posix()
        if rel in ALLOWED_FILES:
            continue
        if rel in DEFERRED_TO_PR_207:
            continue
        if any(rel.startswith(prefix) for prefix in ALLOWED_DIR_PREFIXES):
            continue

        try:
            text = py_file.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        for slice_match in _SLICE_AT_END_RE.finditer(text):
            lookback = slice_match.group("lookback")

            # Skip if this slice is inside a comment line. Comments are
            # documentation about the bug pattern, not executable code.
            line_no_check = text.count("\n", 0, slice_match.start()) + 1
            line_check = text.splitlines()[line_no_check - 1]
            if line_check.lstrip().startswith("#"):
                continue

            # If the slice is anchored directly on a function call whose
            # result is `str` (fmt_dt, isoformat, strftime, str), it's safe.
            if any(p.search(lookback) for p in _SAFE_RESULT_PATTERNS):
                continue

            # Find the LAST dict-access in the lookback window (closest to the slice).
            last_key_match = None
            for m in _DICT_ACCESS_RE.finditer(lookback):
                last_key_match = m
            if not last_key_match:
                continue

            key = last_key_match.group("key1") or last_key_match.group("key2") or ""
            if not _key_is_timestamp_like(key):
                continue

            # Compute line number for actionable diagnostics
            line_no = text.count("\n", 0, slice_match.start()) + 1
            line = text.splitlines()[line_no - 1].strip()

            key_str = f"{rel}:{line}"
            if key_str in KNOWN_FALSE_POSITIVES:
                continue

            violations.append(
                f"\n  {rel}:{line_no}\n    {line}\n    "
                f"(key={key!r} is timestamp-like — replace [:N] with "
                f"fmt_dt(..., length=N) from core.dt_format)"
            )

    assert not violations, (
        "P-038 cohort guard failed.\n"
        "These lines slice a string-shaped operator on a dict access whose key\n"
        "looks like a timestamp column. After the W16 timestamptz migration,\n"
        "psycopg2 returns datetime objects for such columns, and slicing a\n"
        "datetime crashes with TypeError. Use fmt_dt() from core.dt_format\n"
        "instead.\n\n"
        f"Found {len(violations)} violation(s):" + "".join(violations)
    )


def test_regex_actually_matches_bug_pattern() -> None:
    """Sanity check: the regex catches the exact pre-fix lines from PR #206.

    If a future change to the regex accidentally loosens it so the original
    bug wouldn't be caught, this test fails loudly. Verified-by-negation
    using the exact strings that were live in production yesterday.
    """
    # (line, expected_key) pairs — each is a real pre-fix line.
    pre_fix_samples = [
        # daily_deep_dive.py:652 — the crash that triggered this cohort
        ("""f"  [{r.get('restarted_at', '%s')[:16]}] {r.get('restart_type') or '%s'}\"""",
         "restarted_at"),
        # daily_deep_dive.py:665 — latent sibling
        ("""f"  [{a.get('timestamp', '%s')[:16]}] {a.get('action_taken') or '%s'}\"""",
         "timestamp"),
        # slack_command_handler.py:179
        ("""f"*🤖 Fleet Status — {scan['scanned_at'][:16]}*\"""",
         "scanned_at"),
        # train_comprehensive.py — the dual-access line that previously
        # tripped the greedy regex; expected_key should be 'first', not 'board_index'
        ("""f"Board {e['board_index']}: {e['event']} (first: {e['first'][:16]})\"""",
         "first"),
    ]

    for sample, expected_key in pre_fix_samples:
        # Walk slices in the sample; find the FIRST one whose nearest
        # preceding dict-access matches expected_key.
        found = False
        for slice_match in _SLICE_AT_END_RE.finditer(sample):
            lookback = slice_match.group("lookback")
            last_key_match = None
            for m in _DICT_ACCESS_RE.finditer(lookback):
                last_key_match = m
            if not last_key_match:
                continue
            key = last_key_match.group("key1") or last_key_match.group("key2") or ""
            if key == expected_key:
                found = True
                break
        assert found, (
            f"Regex failed to identify expected key {expected_key!r} for line:\n"
            f"  {sample}\n"
            "The lookback-anchored regex may be missing a case."
        )


def test_safe_result_patterns_recognized() -> None:
    """fmt_dt(...)[N:M] and similar safe-result patterns must NOT be flagged.

    Otherwise the cohort guard would require us to wrap every fmt_dt call
    output to avoid the post-fmt_dt slice that we use for compact display
    forms (e.g., HH:MM-only output from `fmt_dt(...)[11:16]`).
    """
    safe_samples = [
        # slack_command_handler.py overnight_report — fmt_dt result sliced for HH:MM
        '''f"@ {fmt_dt(a['timestamp'])[11:16]}"''',
        # slack_command_handler.py cmd_audit — fmt_dt result sliced for MM-DD HH:MM
        '''f"by auto @ {fmt_dt(r['timestamp'])[5:]}"''',
        # Generic .isoformat() slice
        '''ts = some_dt.isoformat()[:16]''',
        # str(x) slice
        '''label = str(some_value)[:50]''',
    ]
    for sample in safe_samples:
        # Walk through, ensure the safe-result detection trips on each slice.
        any_flagged = False
        for slice_match in _SLICE_AT_END_RE.finditer(sample):
            lookback = slice_match.group("lookback")
            if any(p.search(lookback) for p in _SAFE_RESULT_PATTERNS):
                continue  # correctly recognized as safe
            # Now check if it would have been flagged as a violation
            last_key_match = None
            for m in _DICT_ACCESS_RE.finditer(lookback):
                last_key_match = m
            if last_key_match:
                key = last_key_match.group("key1") or last_key_match.group("key2") or ""
                if _key_is_timestamp_like(key):
                    any_flagged = True
                    break
        assert not any_flagged, (
            f"Safe-result pattern incorrectly flagged as a bug:\n  {sample}\n"
            "Check _SAFE_RESULT_PATTERNS; fmt_dt-output slicing must be allowed."
        )


def test_canonical_helper_is_available() -> None:
    """The fmt_dt helper must be importable — it's the prescribed fix."""
    from core.dt_format import fmt_dt
    from datetime import datetime, timezone

    # Sanity check the contract every line in this PR relies on:
    assert fmt_dt(datetime(2026, 5, 13, 10, 30, 45, tzinfo=timezone.utc)) == "2026-05-13 10:30"
    assert fmt_dt("2026-05-13 10:30:00") == "2026-05-13 10:30"
    assert fmt_dt(None) == ""
    assert fmt_dt(12345) == "12345"  # graceful fallback


if __name__ == "__main__":
    test_canonical_helper_is_available()
    test_regex_actually_matches_bug_pattern()
    test_safe_result_patterns_recognized()
    test_no_slice_on_timestamp_dict_keys()
    print("All P-038 cohort guard checks passed.")
