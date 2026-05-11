"""
tests/test_p038_ams_cleanup_path_resolution.py

P-038 item #7 (2026-05-11) — `scripts/cleanup_ams_logs.py` resolved its
sys.path prefix and config path via the hardcoded legacy Linux VPS path
`/root/Mining-Guardian`. On the customer Mac Mini install
(`/Library/Application Support/MiningGuardian/...`) the import chain
silently no-op'd (sys.path.insert of a non-existent dir doesn't raise),
then the script crashed every scheduled run for 5+ consecutive days
(May 6 -> May 10, 2026) with:

    FileNotFoundError: [Errno 2] No such file or directory:
    '/root/Mining-Guardian/config.json'

The scheduled job stamped exit_code 1 in
`logs/scheduled/ams_cleanup.last-run.json` and the AMS log queue never
got cleaned, slowly bumping against the "too many log files" ceiling on
the AMS side.

This fix is the same fix-shape as P-034 -- replace hardcoded
`/root/Mining-Guardian/...` with `_ROOT = Path(__file__).resolve().parent.parent`
so the path resolves correctly under both the repo dev clone and the
Mac Mini install tree (`${MG_INSTALL_ROOT}` = the parent of `scripts/`
on the installed appliance).

This test module locks in:

  S1. Source-level: no `/root/Mining-Guardian` literal anywhere in
      `scripts/cleanup_ams_logs.py`. Negative regression guard.
  S2. Source-level: the canonical
      `_ROOT = Path(__file__).resolve().parent.parent` pattern is present.
  S3. Source-level: sys.path.insert never takes a hardcoded string
      literal -- it must derive from `_ROOT` (or similar) so the path
      resolves under both repo + Mac Mini install layouts.
  S4. Source-level: the config-path resolution chain honors
      `GUARDIAN_CONFIG` env var, matching the contract
      `core/mining_guardian.py::__main__` already uses.
  S5. Source-level: the default config path (when GUARDIAN_CONFIG is
      unset) is anchored on `_ROOT`.
  S6. Runtime: importing the module must not raise FileNotFoundError
      even with no config on disk -- the import itself must not touch
      the config file. Lazy resolution in `cleanup_all_logs()`, not
      at module import.
"""

import ast
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "cleanup_ams_logs.py"


def _src() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# S1. Negative regression -- no /root/Mining-Guardian anywhere in source.
# ---------------------------------------------------------------------------


def test_no_root_mining_guardian_literal_anywhere():
    """The legacy Linux VPS path must NOT appear anywhere in the source.

    Live evidence on the Mac Mini (May 6 -> May 10, 2026): every
    scheduled run crashed with FileNotFoundError pointing at
    `/root/Mining-Guardian/config.json`. Any reintroduction of that
    literal -- even in a comment that someone later uncomments -- would
    be a regression risk; the static check is cheap insurance.
    """
    src = _src()
    assert "/root/Mining-Guardian" not in src, (
        "scripts/cleanup_ams_logs.py must not reference the legacy Linux "
        "VPS path /root/Mining-Guardian -- use "
        "`_ROOT = Path(__file__).resolve().parent.parent` so the path "
        "resolves under both the dev clone and the Mac Mini install "
        "tree. P-038 item #7."
    )


# ---------------------------------------------------------------------------
# S2. Canonical _ROOT idiom is present.
# ---------------------------------------------------------------------------


def test_uses_canonical_root_idiom():
    """The script must compute _ROOT from its own file location.

    Matches the pattern in `core/mining_guardian.py` (line 43),
    `scripts/daily_log_failure_report.py`, and every other in-tree
    script that needs path-resolution under both repo and install
    layouts.
    """
    src = _src()
    assert "_ROOT = Path(__file__).resolve().parent.parent" in src, (
        "scripts/cleanup_ams_logs.py must define "
        "`_ROOT = Path(__file__).resolve().parent.parent` matching the "
        "canonical idiom used by core/mining_guardian.py and "
        "scripts/daily_log_failure_report.py. P-038 item #7."
    )


# ---------------------------------------------------------------------------
# S3. sys.path extension uses _ROOT, not a hardcoded string.
# ---------------------------------------------------------------------------


def test_syspath_extension_uses_root_not_hardcoded():
    """sys.path.insert must NOT take a hardcoded string literal.

    The pre-P-038 code did
        sys.path.insert(0, '/root/Mining-Guardian')
    which silently succeeded on macOS (insert of a non-existent path
    doesn't raise) but then failed at
        from core.mining_guardian import AMSClient, GuardianConfig
    because `/root/Mining-Guardian/core` isn't a real package on the
    Mac Mini.

    On the Mac Mini, the launcher already does
        cd "${INSTALL_ROOT}"
    and exports
        PYTHONPATH="${INSTALL_ROOT}:${PYTHONPATH:-}"
    (see scheduled_job_launcher.sh on the installed Mini), so an
    explicit `sys.path.insert(0, str(_ROOT))` is belt-and-suspenders
    for repo / direct-invocation scenarios where PYTHONPATH isn't set.
    """
    src = _src()
    tree = ast.parse(src)

    bad_inserts = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Match `sys.path.insert(...)` exactly.
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "insert"
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "path"
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == "sys"
        ):
            continue
        # Second positional arg is what's being inserted.
        path_arg = None
        if len(node.args) >= 2:
            path_arg = node.args[1]
        else:
            for kw in node.keywords:
                if kw.arg == "path":
                    path_arg = kw.value
                    break
        if path_arg is None:
            continue
        if isinstance(path_arg, ast.Constant) and isinstance(path_arg.value, str):
            bad_inserts.append(path_arg.value)

    assert not bad_inserts, (
        "scripts/cleanup_ams_logs.py must not call sys.path.insert with "
        "a hardcoded string literal. Found: "
        f"{bad_inserts}. Use `str(_ROOT)` (or similar derived value) "
        "instead. P-038 item #7."
    )


# ---------------------------------------------------------------------------
# S4. Config-path resolution honors GUARDIAN_CONFIG env.
# ---------------------------------------------------------------------------


def test_config_path_honors_guardian_config_env():
    """The config path resolution must honor GUARDIAN_CONFIG env var.

    This matches the contract `core/mining_guardian.py::__main__` uses
    at the bottom of that file (`os.environ.get("GUARDIAN_CONFIG",
    "config.json")`). Sharing the env var means an operator override
    works identically for both the scanner and this cleanup job.
    """
    src = _src()
    assert "GUARDIAN_CONFIG" in src, (
        "scripts/cleanup_ams_logs.py should honor the GUARDIAN_CONFIG "
        "env var (the same one core/mining_guardian.py::__main__ "
        "already uses) so an operator override works for both. "
        "P-038 item #7."
    )


# ---------------------------------------------------------------------------
# S5. Default config path is _ROOT-anchored.
# ---------------------------------------------------------------------------


def test_config_path_default_anchored_on_root():
    """Default (GUARDIAN_CONFIG unset) config path must be _ROOT-anchored.

    Concretely the default should resolve to `_ROOT / "config.json"`
    so it works under both the repo dev clone (`<repo>/config.json`)
    and the Mac Mini install tree (`${MG_INSTALL_ROOT}/config.json`).
    """
    src = _src()
    candidates = (
        '_ROOT / "config.json"',
        "_ROOT / 'config.json'",
        'str(_ROOT / "config.json")',
        "str(_ROOT / 'config.json')",
    )
    assert any(c in src for c in candidates), (
        "scripts/cleanup_ams_logs.py default config path must be "
        "_ROOT-anchored. Expected one of: "
        f"{candidates}. P-038 item #7."
    )


# ---------------------------------------------------------------------------
# S6. Runtime smoke -- module imports cleanly without touching FS.
# ---------------------------------------------------------------------------


def test_module_imports_without_touching_filesystem(monkeypatch):
    """Importing the module must not crash even if no config file exists.

    The pre-P-038 bug was at runtime inside `cleanup_all_logs()`, not
    at import time. This test locks the contract that no future refactor
    moves the config read to module scope (which would break unit-test
    collection and any "import to check it parses" smoke flow).

    We strip the env so any env-aware code in the module can't sneak
    in a real-config dependency. We accept ImportError as a soft skip
    because the module's `from core.mining_guardian import ...` line
    pulls in psycopg2 et al that aren't necessarily installed in the
    test sandbox -- the filesystem bug is already covered by the
    static checks above.
    """
    monkeypatch.delenv("GUARDIAN_CONFIG", raising=False)
    monkeypatch.delenv("MG_INSTALL_ROOT", raising=False)

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "cleanup_ams_logs_under_test",
        str(SCRIPT_PATH),
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)

    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except FileNotFoundError as e:
        pytest.fail(
            "Importing scripts/cleanup_ams_logs.py raised "
            f"FileNotFoundError: {e}. Module-scope code must not read "
            "config or any other file. P-038 item #7 regression."
        )
    except ImportError as e:
        pytest.skip(f"Optional import unavailable in test env: {e}")
