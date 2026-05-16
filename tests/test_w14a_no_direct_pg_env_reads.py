"""
tests/test_w14a_no_direct_pg_env_reads.py

W14a cohort guard (2026-05-12) — every Postgres connector goes through
`core.db_targets.operational_target()` or `catalog_target()`, NOT through
direct `os.environ.get('GUARDIAN_PG_HOST'/'GUARDIAN_PG_PORT')` reads.

Why this guard exists
---------------------
Code in this repo connects to Postgres one of two ways:

  - **Pattern 1** — call `core.db_targets.operational_target()` or
    `catalog_target()`. The resolver returns the right host/port/dbname
    for the requested target. Topology-aware.
  - **Pattern 2** — read `GUARDIAN_PG_HOST` and `GUARDIAN_PG_PORT` from
    `os.environ` directly. Topology-blind.

In State A (one Postgres container, two databases inside it, both
reachable on port 5432) Pattern 2 happens to work because the catalog and
the operational DB share host/port and only `dbname` differs. In State B
(two separate Postgres instances, operational on 5432, catalog on 5433 —
the W14 target topology), Pattern 2 *silently misroutes* every catalog
read: the file keeps connecting to port 5432 looking for
`mining_guardian_catalog`, which no longer exists there.

The bug is silent because (a) the operational instance accepts the
connection and (b) `psycopg2` raises an error on the FIRST query against
a missing database, not at connect-time — but the connect itself can
succeed against a different database on the same instance if the caller
is sloppy about which dbname they pass. Either way: the failure mode is
"catalog reads start failing at runtime, with no compile-time signal".

This test fires the moment ANY file under the scanned roots reads
`GUARDIAN_PG_HOST` or `GUARDIAN_PG_PORT` outside the ALLOWED_BYPASSES
set. That's the convention's teeth.

The test lands RED (failing) the moment it's committed, because the
W14a refactor of 27 files is the WORK that turns it green. When the
last offender is migrated to `db_targets`, this test goes green and
W14a is done by definition.

Lifecycle
---------
1. **W14a commit 1 (this file)**: test added. It fails — 27 offenders.
   That's expected; the failure message lists them.
2. **W14a commits 2..N**: each batch refactors a subset of the 27 files.
   The offender count drops with each commit.
3. **W14a final commit**: the last offender is fixed. Test goes green.
   PR can merge.
4. **Forever after**: any new file that reintroduces Pattern 2 fails
   CI on the PR that adds it. Author sees the offender list and the
   pointer to `core.db_targets`, fixes it, re-pushes. Convention holds.

See:
  - docs/strategy/AMENDMENTS_2026-05-12.md §A01 (rationale, full file list)
  - docs/strategy/W14_PREP.md (refactor pattern, smoke tests, rollback)
  - core/db_targets.py (the resolver that Pattern 1 callers use)

Sibling cohort guards in this codebase that use the same shape:
  - tests/test_p038_timestamptz_vs_text_sql_casts.py (W16 cohort)
  - tests/test_no_retired_host_defaults.py
  - tests/test_p023_no_retired_hosts_in_shipped_payload.py
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


# `core/db_targets.py` is the ONE place that resolves these env vars.
# Anything else under the scanned roots must go through it. Test
# fixtures and helpers may also need to set these for isolation —
# `tests/` is excluded below at the directory level rather than per-file
# so this set stays tight.
ALLOWED_BYPASSES: frozenset[str] = frozenset({
    "core/db_targets.py",
})


# Pattern 2 — direct env reads of the *host* or *port* connect params.
# We intentionally do NOT match GUARDIAN_PG_USER / _PASSWORD /
# _DBNAME / _CATALOG_DBNAME here, because:
#   - User and password are the same for both targets even in State B
#     (per W14_PREP D2 default).
#   - _DBNAME and _CATALOG_DBNAME are the explicit distinguishers
#     between the two targets; resolving those via env IS the
#     `db_targets` job, so other files reading them is *also* wrong,
#     but a narrower guard (host/port only) is enough to catch the
#     concrete "silent misroute to port 5432" failure mode that
#     motivates W14a. Broadening the regex would surface false
#     positives (e.g. installer post-install bash that writes the
#     `.env` legitimately reads these names from its own arg parsing).
#
# Match both the bare token and the typical `os.environ.get("...")`
# wrapper. The regex is intentionally permissive — any mention is
# treated as suspicious, and ALLOWED_BYPASSES is the only escape hatch.
PATTERN_2_REGEX = re.compile(r"GUARDIAN_PG_(?:HOST|PORT)")


# Roots to scan. Anything outside these can read env vars freely
# (notably the installer's bash scripts under
# `installer/macos-pkg/scripts/`, which write the .env in the first
# place and legitimately reference these names).
SCAN_ROOTS: tuple[str, ...] = (
    "ai",
    "api",
    "core",
    "console",
    "monitoring",
    "scripts",
    "intelligence-catalog",
)


def _scan_for_pattern_2() -> list[str]:
    """Return sorted list of repo-relative paths that match PATTERN_2_REGEX.

    Excludes:
      - paths in ALLOWED_BYPASSES (e.g. core/db_targets.py itself)
      - anything under tests/ (test fixtures may set these env vars)
      - non-.py files
      - build artifacts (build/, dist/, .venv*/)
    """
    offenders: list[str] = []
    for root in SCAN_ROOTS:
        root_path = REPO_ROOT / root
        if not root_path.exists():
            continue
        for py in root_path.rglob("*.py"):
            rel = py.relative_to(REPO_ROOT).as_posix()
            if rel in ALLOWED_BYPASSES:
                continue
            # Skip build/staging artifacts that mirror source trees
            if "/build/" in rel or rel.startswith("build/"):
                continue
            if "/dist/" in rel or rel.startswith("dist/"):
                continue
            if "/.venv" in rel:
                continue
            # Exclude anything under tests/ — test fixtures and helpers
            # legitimately set GUARDIAN_PG_HOST/PORT to point a temporary
            # connection at a scratch instance. This matches the documented
            # contract above and makes the guard correct even if `tests`
            # is later added to SCAN_ROOTS (today it is not, so this is
            # belt-and-suspenders rather than currently load-bearing).
            if rel == "tests" or rel.startswith("tests/") or "/tests/" in rel:
                continue
            try:
                text = py.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if PATTERN_2_REGEX.search(text):
                offenders.append(rel)
    return sorted(offenders)


def test_no_pattern_2_outside_db_targets() -> None:
    """W14a cohort guard — every Postgres connector goes through
    `core.db_targets`.

    Failure mode this guards against: a file reads
    `GUARDIAN_PG_HOST`/`GUARDIAN_PG_PORT` directly via `os.environ`, then
    passes the values to `psycopg2.connect()`. Works fine in State A
    (one Postgres, two DBs on port 5432). Silently misroutes catalog
    reads to the operational instance in State B (catalog on port 5433).

    To fix a flagged file:

      Before (Pattern 2):
          host = os.environ.get("GUARDIAN_PG_HOST", "127.0.0.1")
          port = os.environ.get("GUARDIAN_PG_PORT", "5432")
          conn = psycopg2.connect(host=host, port=port, ...)

      After (Pattern 1):
          from core.db_targets import operational_target  # or catalog_target
          conn = psycopg2.connect(**operational_target().connect_kwargs())

    For catalog readers, substitute `catalog_target()`.

    See docs/strategy/AMENDMENTS_2026-05-12.md §A01 for the rationale
    and the authoritative 27-file list this guard was created to enforce.
    """
    offenders = _scan_for_pattern_2()
    assert not offenders, (
        "\n"
        f"W14a cohort guard: {len(offenders)} file(s) read "
        "GUARDIAN_PG_HOST/PORT directly, bypassing core.db_targets:\n"
        "  " + "\n  ".join(offenders) + "\n"
        "\n"
        "Use core.db_targets.operational_target() or catalog_target() "
        "instead. See docs/strategy/AMENDMENTS_2026-05-12.md §A01 for the "
        "rationale and the refactor pattern.\n"
        "\n"
        "If a file legitimately needs to read these env vars (e.g. a new "
        "helper inside core/), add it to ALLOWED_BYPASSES in this file "
        "with a comment explaining why.\n"
    )


def test_allowed_bypasses_actually_exist() -> None:
    """Sanity check: every entry in ALLOWED_BYPASSES points at a real file.

    Catches typos in the bypass list. If a bypass is removed from disk
    (e.g. file renamed) but kept in ALLOWED_BYPASSES, this fails — which
    is the right behaviour, since a stale bypass could shadow a real
    offender if someone re-creates the path later.
    """
    missing = [
        rel for rel in ALLOWED_BYPASSES
        if not (REPO_ROOT / rel).is_file()
    ]
    assert not missing, (
        f"\nALLOWED_BYPASSES contains paths that don't exist on disk:\n"
        "  " + "\n  ".join(missing) + "\n"
        "Remove them from ALLOWED_BYPASSES in "
        "tests/test_w14a_no_direct_pg_env_reads.py.\n"
    )


def test_db_targets_module_is_reachable() -> None:
    """Sanity check: the resolver the convention points at actually exists
    and exports the expected functions.

    Cheap canary against the failure mode where someone renames or
    deletes `core/db_targets.py` without updating ALLOWED_BYPASSES (this
    test) AND `CLAUDE.md` (W14b documentation). All three should move
    together.
    """
    db_targets_path = REPO_ROOT / "core" / "db_targets.py"
    assert db_targets_path.is_file(), (
        f"\nExpected resolver module at {db_targets_path} is missing.\n"
        "If `core/db_targets.py` was intentionally moved or renamed, "
        "update ALLOWED_BYPASSES in this file and the convention "
        "section in CLAUDE.md (W14b) so the three artifacts stay in sync.\n"
    )

    text = db_targets_path.read_text(encoding="utf-8")
    for symbol in ("def operational_target", "def catalog_target"):
        assert symbol in text, (
            f"\nExpected `{symbol}(...)` in {db_targets_path} but the "
            "symbol was not found. The W14a convention assumes both "
            "resolvers are exported from this module — "
            "see docs/strategy/AMENDMENTS_2026-05-12.md §A01.\n"
        )


def test_scan_for_pattern_2_excludes_tests_dir(tmp_path, monkeypatch) -> None:
    """Guard-of-the-guard: _scan_for_pattern_2() must skip tests/.

    The docstring of _scan_for_pattern_2() promises "anything under
    tests/" is excluded (test fixtures legitimately set
    GUARDIAN_PG_HOST/PORT to aim a throwaway connection at a scratch
    instance). For most of this guard's life that promise was only
    *implicitly* kept by `tests` not appearing in SCAN_ROOTS — the
    exclusion was documented but never coded, so adding `tests` to
    SCAN_ROOTS later would have silently false-flagged every fixture.

    This test pins the now-explicit behaviour: even when a tests/ path
    is forced into the walk, a Pattern-2 token inside it is NOT
    reported. If someone removes the explicit `tests/` skip, this fails
    and explains why — closing the W14a cohort-guard gap permanently.
    """
    import sys
    mod = sys.modules[__name__]

    # Create a fake tests/ file under a sandbox repo root that DOES
    # contain the forbidden pattern, then point the scanner's root +
    # scan roots at the sandbox with `tests` explicitly included.
    sandbox = tmp_path
    tdir = sandbox / "tests"
    tdir.mkdir()
    offending = tdir / "test_fixture_sets_pg_env.py"
    offending.write_text(
        'import os\n'
        'os.environ["GUARDIAN_PG_HOST"] = "127.0.0.1"\n'
        'os.environ["GUARDIAN_PG_PORT"] = "5499"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "REPO_ROOT", sandbox)
    monkeypatch.setattr(mod, "SCAN_ROOTS", ("tests",))

    offenders = mod._scan_for_pattern_2()
    assert offenders == [], (
        "_scan_for_pattern_2() reported a tests/ path as an offender:\n  "
        + "\n  ".join(offenders)
        + "\n\nThe W14a guard must exclude tests/ (fixtures legitimately "
        "set GUARDIAN_PG_HOST/PORT). The explicit `tests/` skip in "
        "_scan_for_pattern_2() was removed or broken — restore it. "
        "See the docstring's documented exclusion contract."
    )


def test_scan_for_pattern_2_still_flags_non_test_offenders(tmp_path, monkeypatch) -> None:
    """Counterpart: the tests/ skip must NOT neuter the guard for real code.

    A Pattern-2 token in a non-tests source file under a scanned root
    must still be reported. This proves the exclusion added to close the
    W14a gap is narrowly scoped to tests/ and did not accidentally make
    the whole guard permissive.
    """
    import sys
    mod = sys.modules[__name__]

    sandbox = tmp_path
    cdir = sandbox / "core"
    cdir.mkdir()
    bad = cdir / "rogue_connector.py"
    bad.write_text(
        'import os, psycopg2\n'
        'h = os.environ.get("GUARDIAN_PG_HOST", "127.0.0.1")\n'
        'conn = psycopg2.connect(host=h)\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "REPO_ROOT", sandbox)
    monkeypatch.setattr(mod, "SCAN_ROOTS", ("core",))
    monkeypatch.setattr(mod, "ALLOWED_BYPASSES", frozenset())

    offenders = mod._scan_for_pattern_2()
    assert offenders == ["core/rogue_connector.py"], (
        "Expected the rogue non-test connector to be flagged, got: "
        f"{offenders}. The tests/ exclusion must not make the guard "
        "permissive for real source files."
    )
