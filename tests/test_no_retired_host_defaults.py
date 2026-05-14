"""
P-018E regression guard — no retired-host defaults in active code.

The ROBS-PC tailscale endpoint `100.110.87.1` was the catalog API host
(port 8420) and the Ollama host (port 11434) before the Mac mini cutover.
After the cutover, every operational reference to that IP must point at
the Mini's local services (`127.0.0.1:11434` for Ollama, the local
catalog DB for catalog reads).

P-018C removed the catalog HTTP default; P-018E removes every remaining
Ollama / Postgres / catalog-API default that pointed at the retired
host. This test asserts that the substring `100.110.87.1` never appears
inside an active Python `os.getenv(..., DEFAULT)` or hardcoded URL
constant going forward.

Documentation, comments, and intentional REFUSAL guards (the retired-
host blacklist in `ai/catalog_context.py::_http_fallback_url`) are
allowed because they protect future readers from re-introducing the
wrong default. The test ignores `archive/`, `docs/`, `tests/`,
`installer/macos-pkg/scripts/postinstall.sh` (the .pkg's own builder
already drops `OLLAMA_HOST=http://127.0.0.1:11434`), and any line that
appears inside a comment or docstring.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent

# Directories whose retired-host references are explicitly allowed:
# - archive/        : decommissioned scratch
# - docs/           : historical handoff & runbook references
# - tests/          : the test files themselves cite the retired host
# - .git/           : never crawl
ALLOWED_DIR_PREFIXES = ("archive/", "docs/", "tests/", ".git/")

# Non-source directories that must never be crawled — build artifacts
# and virtualenvs are not part of the repo's source tree:
# - build/          : the .pkg staging dir (gitignored, .gitignore:15).
#                     build_pkg.sh step 3 rm -rf's it and re-stages a
#                     *copy* of the payload, so e.g.
#                     build/stage/payload/ai/catalog_context.py duplicates
#                     the real ai/catalog_context.py. The real file is
#                     correctly exempt via ALLOWED_FILES; the staged copy
#                     is a different path string and would false-flag the
#                     walk.
# - venv/ / .venv*/ : virtualenvs (e.g. .venv-p018-tests/) carry thousands
#                     of third-party site-package .py files that are not
#                     repo source.
# - __pycache__/    : compiled bytecode dirs.
# Matches the exclusion convention already used by test_p023 /
# test_w25 / test_w25b / test_w14a.
_EXCLUDED_DIR_SEGMENTS = ("build", "venv", ".venv", "__pycache__")

# Files whose retired-host references are intentional refusal guards:
# - ai/catalog_context.py: the opt-in HTTP fallback safety check
#                          (`_http_fallback_url` REFUSES the retired host).
# - .env.example: documents that the retired host must NOT be set.
# - intelligence-catalog/catalog-api/.env.example: same.
ALLOWED_FILES = {
    "ai/catalog_context.py",
    ".env.example",
    "intelligence-catalog/catalog-api/.env.example",
}

RETIRED_IP = "100.110.87.1"


def _iter_python_files():
    """Yield repo-relative POSIX paths for every active *.py file."""
    for path in REPO_ROOT.rglob("*.py"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if any(rel.startswith(p) for p in ALLOWED_DIR_PREFIXES):
            continue
        if any(seg in _EXCLUDED_DIR_SEGMENTS for seg in rel.split("/")):
            continue
        yield rel, path


def _strip_comments_and_docstrings(text: str) -> str:
    """Cheap conservative scrubber.

    Removes:
      * lines whose first non-whitespace char is '#' (full-line comments)
      * triple-quoted blocks (both ''' and "")

    The scrubber is intentionally conservative — it errs on the side of
    deleting too much (missing some live code references) rather than
    too little (false-flagging a docstring). For the retired-host
    check, that bias is correct: an active runtime reference would
    appear OUTSIDE both forms.
    """
    # Strip triple-quoted blocks first, both kinds.
    text = re.sub(r"'''.*?'''", "", text, flags=re.DOTALL)
    text = re.sub(r'""".*?"""', "", text, flags=re.DOTALL)
    out_lines = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        # Strip trailing inline comment (best-effort — won't catch
        # comments inside string literals, which is fine because the
        # retired host doesn't appear in any literal we care about).
        out_lines.append(line.split("#", 1)[0])
    return "\n".join(out_lines)


def test_no_retired_host_in_active_python_code():
    """No active Python file may contain `100.110.87.1` outside a
    comment / docstring. This is the wedge that finally retires the
    ROBS-PC endpoint repo-wide."""
    offenders: list[tuple[str, list[int]]] = []
    for rel, path in _iter_python_files():
        if rel in ALLOWED_FILES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if RETIRED_IP not in text:
            continue
        scrubbed = _strip_comments_and_docstrings(text)
        if RETIRED_IP not in scrubbed:
            continue
        # Find offending line numbers in the original text for a useful
        # failure message.
        bad_lines = [
            i + 1
            for i, line in enumerate(text.splitlines())
            if RETIRED_IP in line and not line.lstrip().startswith("#")
        ]
        offenders.append((rel, bad_lines))

    if offenders:
        msg = "\n".join(f"  {rel}:{lines}" for rel, lines in offenders)
        pytest.fail(
            f"\nActive Python code contains the retired ROBS-PC host "
            f"{RETIRED_IP!r}:\n{msg}\n"
            "Defaults must point at the Mini's local services "
            "(127.0.0.1:11434 for Ollama, core.db_targets.catalog_target() "
            "for the catalog DB). Comments / docstrings / refusal guards "
            "in the ALLOWED_* lists are exempt."
        )


def test_no_retired_host_in_env_examples_as_default():
    """`.env.example` files may MENTION the retired host (so operators
    learn not to set it), but they must NOT show it as a key=value
    line that would copy it into a real .env."""
    bad: list[tuple[str, int, str]] = []
    pattern = re.compile(r"^[A-Z_][A-Z0-9_]*\s*=\s*[^#\n]*100\.110\.87\.1")
    for path in REPO_ROOT.rglob("*.example"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if any(rel.startswith(p) for p in ALLOWED_DIR_PREFIXES):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), start=1):
            if pattern.match(line):
                bad.append((rel, i, line))

    if bad:
        msg = "\n".join(f"  {rel}:{i}: {line}" for rel, i, line in bad)
        pytest.fail(
            f"\n.env.example file(s) still set the retired host as a "
            f"key=value default:\n{msg}\n"
            "Either leave the value empty or use 127.0.0.1."
        )


def test_catalog_api_resolves_via_core_db_targets():
    """The catalog API server must source DB params from
    `core.db_targets.catalog_target()` (P-018E), not from a
    standalone `os.getenv("DB_NAME", "mining_guardian")` shortcut."""
    path = REPO_ROOT / "intelligence-catalog" / "catalog-api" / "catalog_api.py"
    text = path.read_text(encoding="utf-8")
    # Must reference the helper.
    assert "catalog_target" in text, (
        "intelligence-catalog/catalog-api/catalog_api.py must import "
        "core.db_targets.catalog_target() per P-018E"
    )
    # Must NOT keep the pre-P-018E default that silently routed the
    # catalog API at the operational DB.
    bad = 'DB_NAME = os.getenv("DB_NAME", "mining_guardian")'
    assert bad not in text, (
        "catalog_api.py still contains the pre-P-018E default that "
        "pointed at the operational DB. The default must come from "
        "catalog_target().dbname (mining_guardian_catalog)."
    )


def test_ollama_url_defaults_are_local():
    """Spot-check the six files where `OLLAMA_URL` had a retired-host
    default. Each must now default to 127.0.0.1 (or have no default
    other than what the env / config chain provides)."""
    targets = (
        "core/llm_analyzer.py",
        "core/mining_guardian.py",
        "ai/combine_knowledge.py",
        "ai/daily_deep_dive.py",
        "ai/local_llm_analyzer.py",
        "ai/refinement_chain.py",
    )
    for rel in targets:
        path = REPO_ROOT / rel
        text = path.read_text(encoding="utf-8")
        # No retired-host default may remain (comments are stripped first).
        scrubbed = _strip_comments_and_docstrings(text)
        assert "100.110.87.1" not in scrubbed, (
            f"{rel} still has 100.110.87.1 in active code"
        )
        # Every os.getenv("OLLAMA_URL", DEFAULT) in this file must use
        # 127.0.0.1 in DEFAULT (regex captures the full default arg).
        for match in re.finditer(
            r'os\.getenv\(\s*["\']OLLAMA_URL["\']\s*,\s*["\']([^"\']+)["\']\s*\)',
            scrubbed,
        ):
            default = match.group(1)
            assert "127.0.0.1" in default, (
                f"{rel}: OLLAMA_URL default {default!r} is not Mini-local"
            )


def test_migrate_sqlite_catalog_db_host_default_is_local():
    """The historical 2026-04-23 cutover script's CATALOG_DB_HOST
    default must point at localhost — re-running it on the Mini must
    not silently target a remote tailscale host."""
    path = REPO_ROOT / "migrations" / "migrate_sqlite_to_postgres.py"
    text = path.read_text(encoding="utf-8")
    scrubbed = _strip_comments_and_docstrings(text)
    assert "100.110.87.1" not in scrubbed, (
        "migrate_sqlite_to_postgres.py still defaults CATALOG_DB_HOST "
        "to the retired tailscale IP"
    )
    assert 'CATALOG_DB_HOST", "127.0.0.1"' in text, (
        "migrate_sqlite_to_postgres.py must default CATALOG_DB_HOST "
        "to 127.0.0.1"
    )
