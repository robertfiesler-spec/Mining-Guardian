"""
W17 cohort guard — naked datetime.now() sweep to UTC-aware.

W17 converted 111 "Class A" call sites (datetime.now() -> datetime.now(timezone.utc))
across live ai/ core/ api/ scripts/ code. This guard locks that in and protects
the DELIBERATE exclusions so a future session does not "helpfully" regress them.

Classes (see PR #<W17>):
  A  convert   — timestamps written to/compared against UTC-stored data
  B  exclude   — matched elapsed-time pairs (timezone-invariant subtraction)
  C  exclude   — deliberate human-facing LOCAL time (log filenames, CDT-labelled
                 operator output). Converting these is a VISIBLE regression.
  D  exclude   — core/database.py: dead SQLite layer, 0 live importers; belongs
                 to the archive-deletion item, not W17 (Failure Mode 9).

This test runs without live Postgres (pure source scan) so it never skips.
"""
import re
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
SWEPT_DIRS = ["ai", "core", "api", "scripts"]

# Class B/C/D — every site W17 deliberately did NOT convert. (path, lineno-ish anchor substring)
EXPECTED_EXCLUSIONS = {
    # Class D — dead SQLite layer (whole file)
    "core/database.py": "ALL",  # entire file excluded; archive item owns it
    # Class B — elapsed-time / duration pairs
    "core/llm_analyzer.py": ["start = datetime.now()",
                             "elapsed = int((datetime.now() - start)"],
    "scripts/migrate_split_databases.py": ["start_time = datetime.now()",
                                           "duration = datetime.now() - start_time"],
    "scripts/migrate_to_postgres.py": ["start_time = datetime.now()",
                                        "duration = datetime.now() - start_time"],
    # Class C — deliberate LOCAL display / filenames / CDT-labelled
    "ai/backup_knowledge.py": ['datetime.now().strftime("%Y-%m-%d %H:%M")'],
    "ai/daily_deep_dive.py": ["f\"Date: {datetime.now().strftime('%Y-%m-%d')}\""],
    "core/mining_guardian.py": ["guardian_{datetime.now().strftime('%Y-%m-%d')}.log",
                                'datetime.now().strftime("%Y-%m-%d %H:%M")'],
    "api/intelligence_report_api.py": ['datetime.now().strftime("%I:%M %p CDT")',
                                       'datetime.now().strftime("%B %d, %Y %I:%M %p CDT")'],
    "api/ai_dashboard_api.py": ["datetime.now().strftime('%Y-%m-%d %H:%M')"],
    "scripts/daily_log_failure_report.py": ["datetime.now().strftime('%Y-%m-%d %I:%M %p')"],
    "scripts/run_after_deep_dive.py": ["datetime.now():%H:%M:%S"],
    "scripts/morning_briefing.py": ['datetime.now().strftime("%A, %B %d'],
}

NAKED = re.compile(r"datetime\.now\(\)")


def _iter_py():
    for d in SWEPT_DIRS:
        for p in (REPO / d).rglob("*.py"):
            if "/.venv" in str(p) or "/build/" in str(p):
                continue
            yield p


def test_no_naked_now_in_swept_live_paths():
    """Every datetime.now() in live swept code must be an expected exclusion."""
    offenders = []
    for p in _iter_py():
        rel = str(p.relative_to(REPO))
        if rel == "core/database.py":
            continue  # Class D: whole file owned by archive item
        if rel.startswith("tests/"):
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if not NAKED.search(line):
                continue
            allowed = EXPECTED_EXCLUSIONS.get(rel)
            if allowed and allowed != "ALL" and any(a in line for a in allowed):
                continue
            offenders.append(f"{rel}:{i}: {line.strip()}")
    assert not offenders, (
        "Naked datetime.now() found in swept live code (W17). Either convert to "
        "datetime.now(timezone.utc) or, if intentionally LOCAL, add it to "
        "EXPECTED_EXCLUSIONS with a documented reason:\n  " + "\n  ".join(offenders)
    )


def test_class_c_local_sites_remain_local():
    """Class C deliberate-local sites must NOT have been converted to UTC.

    Protects operator-facing local timestamps + log filenames from a future
    well-meaning sweep. Failure here means someone UTC-ified human display.
    """
    regressions = []
    for rel, anchors in EXPECTED_EXCLUSIONS.items():
        if anchors == "ALL":
            continue
        p = REPO / rel
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for a in anchors:
            # The Class C/B anchors are written with the NAKED form on purpose.
            if "datetime.now()" in a and a not in text:
                regressions.append(f"{rel}: expected deliberate-local site missing "
                                    f"(was it converted to UTC?): {a}")
    assert not regressions, (
        "A deliberate Class B/C site changed — likely UTC-converted by mistake:\n  "
        + "\n  ".join(regressions)
    )


def test_database_py_untouched_by_w17():
    """core/database.py is dead SQLite (Class D) — W17 must not have edited it."""
    p = REPO / "core/database.py"
    text = p.read_text(encoding="utf-8", errors="ignore")
    assert "datetime.now(timezone.utc)" not in text, (
        "core/database.py was modified by the W17 sweep. It is dead SQLite-layer "
        "code with zero live importers and belongs to the archive-deletion item, "
        "not W17 (Failure Mode 9: do not bundle distinct bug classes)."
    )
