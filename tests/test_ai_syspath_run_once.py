"""
P-030 (2026-05-08) regression test — `ai/` directory MUST be on sys.path
before `run_once()` imports `knowledge_manager`.

Production scanner is invoked as `mining_guardian.py --once` which calls
`run_once()` directly (see L2695). `run_once()` does
`from knowledge_manager import KnowledgeManager` (an `ai/` module) at
multiple call sites. Prior to P-030, only `loop()` injected `ai/` into
sys.path — so every `--once` scan silently logged
`Knowledge update skipped: No module named 'knowledge_manager'`,
disabling the persistent knowledge feed that the weekly Claude training
and daily deep dive both depend on.

Fix: include `str(_ROOT / "ai")` in the early sys.path list at module
import time (top of `core/mining_guardian.py`), so it is on path BEFORE
any `run_once()` invocation, regardless of whether the caller goes
through `loop()`.

These tests parse the source rather than importing `core.mining_guardian`
because that module pulls heavy production deps (websocket, requests,
database_pg, etc.) that the unit-test environment intentionally does not
install.
"""

import ast
import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GUARDIAN_SRC = REPO_ROOT / "core" / "mining_guardian.py"


def _read_guardian_source() -> str:
    return GUARDIAN_SRC.read_text(encoding="utf-8")


def test_guardian_source_exists():
    assert GUARDIAN_SRC.exists(), f"missing {GUARDIAN_SRC}"


def test_early_syspath_block_includes_ai_dir():
    """
    The early sys.path setup at the top of `core/mining_guardian.py`
    MUST list `_ROOT / "ai"` so `from knowledge_manager import ...`
    in `run_once()` resolves regardless of whether `loop()` ran first.
    """
    src = _read_guardian_source()

    # Locate the early loop that pushes paths into sys.path. It should
    # be the first such loop in the file (above any function definition).
    tree = ast.parse(src)
    early_loop = None
    for node in tree.body:
        if isinstance(node, ast.For):
            early_loop = node
            break

    assert early_loop is not None, (
        "No top-level `for` loop found in core/mining_guardian.py; the "
        "early sys.path setup is missing or has been moved."
    )

    # The iterator should be a list literal of `str(_ROOT / <name>)`.
    assert isinstance(early_loop.iter, ast.List), (
        "Early sys.path loop's iterator is not a list literal — "
        "structure changed; revisit P-030 fix."
    )

    paths = []
    for elt in early_loop.iter.elts:
        # Each element is `str(_ROOT / "<name>")` — pull the literal name.
        if (
            isinstance(elt, ast.Call)
            and isinstance(elt.func, ast.Name)
            and elt.func.id == "str"
            and elt.args
        ):
            arg = elt.args[0]
            if isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Div):
                # _ROOT / "name"
                if isinstance(arg.right, ast.Constant) and isinstance(
                    arg.right.value, str
                ):
                    paths.append(arg.right.value)
            elif isinstance(arg, ast.Name) and arg.id == "_ROOT":
                paths.append("")  # the bare _ROOT entry

    assert "ai" in paths, (
        "P-030 regression: early sys.path block in core/mining_guardian.py "
        "does not include `_ROOT / 'ai'`. run_once()'s "
        "`from knowledge_manager import KnowledgeManager` will fail with "
        "`No module named 'knowledge_manager'` whenever the scanner is "
        f"invoked as `--once`. Found paths: {paths!r}"
    )


def test_ai_path_inserted_before_run_once_call_site():
    """
    Defensive structural check: the early sys.path block (which now
    includes `ai/`) must appear in source BEFORE the first
    `from knowledge_manager import` line. If a future refactor moves
    the bare import above the path setup, this test catches it.
    """
    src = _read_guardian_source()
    lines = src.splitlines()

    syspath_line = None
    for i, line in enumerate(lines):
        if 'sys.path.insert' in line and syspath_line is None:
            syspath_line = i
            break

    knowledge_import_line = None
    for i, line in enumerate(lines):
        if re.match(r'\s*from knowledge_manager import', line):
            knowledge_import_line = i
            break

    assert syspath_line is not None, "no sys.path.insert call found"
    assert knowledge_import_line is not None, (
        "no `from knowledge_manager import` found — file structure changed"
    )
    assert syspath_line < knowledge_import_line, (
        f"sys.path setup at line {syspath_line + 1} comes AFTER "
        f"`from knowledge_manager import` at line {knowledge_import_line + 1}; "
        "run_once() will import-fail."
    )


def test_knowledge_manager_module_exists_at_expected_path():
    """
    The fix only works if `ai/knowledge_manager.py` actually exists on
    disk. If the file is moved or renamed, the sys.path entry no longer
    helps — fail loudly.
    """
    km = REPO_ROOT / "ai" / "knowledge_manager.py"
    assert km.exists(), (
        f"expected ai/knowledge_manager.py at {km}; if the module has "
        "been relocated, update the sys.path entry in "
        "core/mining_guardian.py to match."
    )


def test_bare_knowledge_manager_module_resolves_with_ai_on_syspath(tmp_path):
    """
    Functional smoke: with `<repo>/ai` on sys.path (as the early
    sys.path block now ensures), Python's import machinery FINDS
    `knowledge_manager` — i.e. the failure mode we are fixing
    (`No module named 'knowledge_manager'`) does not occur.

    Production runtime deps such as `psycopg2` may or may not be
    installed in the unit-test environment; this test cares about
    module discovery, not whether `KnowledgeManager` can fully import
    its transitive deps. We use `importlib.util.find_spec` so the
    assertion passes even when (e.g.) `psycopg2` is unavailable.

    Counter-test: WITHOUT `ai/` on sys.path the spec must be `None`,
    proving the early sys.path entry is the load-bearing piece.

    Run in isolated subprocesses so we do not pollute the main test
    process's sys.path or import cache.
    """
    import subprocess
    import sys

    ai_dir = REPO_ROOT / "ai"
    assert ai_dir.is_dir()

    # POSITIVE: with ai/ on sys.path the spec must resolve.
    pos_script = (
        "import sys, importlib.util\n"
        f"sys.path.insert(0, {str(ai_dir)!r})\n"
        "spec = importlib.util.find_spec('knowledge_manager')\n"
        "print('FOUND' if spec is not None else 'MISSING')\n"
    )
    pos = subprocess.run(
        [sys.executable, "-c", pos_script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert pos.returncode == 0, (
        f"positive subprocess crashed:\nstdout={pos.stdout!r}\n"
        f"stderr={pos.stderr!r}"
    )
    assert "FOUND" in pos.stdout, (
        "P-030 regression: even with ai/ on sys.path, Python cannot "
        "find `knowledge_manager`. Has the file moved?\n"
        f"stdout={pos.stdout!r}\nstderr={pos.stderr!r}"
    )

    # NEGATIVE / counter-test: without ai/ on sys.path the spec must
    # be None — proving the entry added by P-030 is what makes the
    # positive case work.
    neg_script = (
        "import sys, importlib.util\n"
        # Strip every entry that points into the repo's ai/ dir; this
        # mimics a fresh interpreter where loop() has not run.
        f"_AI = {str(ai_dir)!r}\n"
        "sys.path[:] = [p for p in sys.path if p != _AI]\n"
        "spec = importlib.util.find_spec('knowledge_manager')\n"
        "print('FOUND' if spec is not None else 'MISSING')\n"
    )
    neg = subprocess.run(
        [sys.executable, "-c", neg_script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert neg.returncode == 0
    assert "MISSING" in neg.stdout, (
        "Counter-test failed: `knowledge_manager` resolves WITHOUT "
        "ai/ on sys.path — meaning some other path entry is masking "
        "the failure mode and this regression test is not actually "
        "guarding against P-030."
    )
