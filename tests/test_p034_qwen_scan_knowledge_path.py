"""
tests/test_p034_qwen_scan_knowledge_path.py

P-034 (2026-05-08) — regression tests for the Qwen post-scan
`llm_scan_analyses` persistence path fix.

Pre-P-034, the post-scan Qwen analysis block in
`core/mining_guardian.py` hard-coded the legacy Linux dev path
`/root/Mining-Guardian/knowledge.json` for both the read and the
atomic write. On the Mac Mini install tree the canonical knowledge
path is `${MG_INSTALL_ROOT}/knowledge/knowledge.json` (with a
compat symlink at `${MG_INSTALL_ROOT}/knowledge.json`), so the
hard-coded path didn't exist and every scan logged:

    Qwen scan analysis failed:
      [Errno 2] No such file or directory:
        '/root/Mining-Guardian/knowledge.json.tmp'

even though the Qwen call itself succeeded.

These tests lock in:

  1. The hard-coded `/root/Mining-Guardian/knowledge.json` path no
     longer appears in the Qwen scan persistence block.
  2. That block resolves the knowledge path via `_ROOT` (i.e. the
     repo / install root the scanner already computes) so it works
     both in the dev clone and in the installed tree.
  3. That block uses the canonical `core.file_lock.locked_knowledge_update`
     helper, which guarantees both file locking and atomic write —
     the same contract every other knowledge writer follows.
  4. No other active Python file in the scanner hot path
     (`core/`, `ai/`) writes to `/root/Mining-Guardian/knowledge.json`
     either, so this regression cannot creep back in via a sibling
     module.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


# The canonical Qwen post-scan persistence block lives in
# `core/mining_guardian.py`. We extract it once and assert against the
# slice rather than the whole file so the assertions stay surgical.

_SCANNER_PATH = REPO_ROOT / "core" / "mining_guardian.py"


def _scanner_src() -> str:
    return _SCANNER_PATH.read_text()


def _qwen_block(src: str) -> str:
    """Return the slice of mining_guardian.py covering the Qwen post-scan
    analysis + persistence block.

    The block starts at the `analysis_text = resp.get("response"...` line
    that follows the Ollama HTTP call and ends at the next top-level
    `elif` / `except` boundary. We pin it by searching for two stable
    sentinels: the analysis_text assignment, and the `Qwen scan analysis
    failed` warning that closes the surrounding try/except.
    """
    start_token = 'analysis_text = resp.get("response"'
    end_token = "Qwen scan analysis failed"
    i = src.index(start_token)
    j = src.index(end_token, i)
    return src[i:j]


# ─────────────────────────────────────────────────────────────────────────
# §1. The hard-coded /root/... path is gone from the Qwen block
# ─────────────────────────────────────────────────────────────────────────


def test_qwen_block_no_root_mining_guardian_path():
    block = _qwen_block(_scanner_src())
    for quote in (
        '"/root/Mining-Guardian/knowledge.json"',
        "'/root/Mining-Guardian/knowledge.json'",
    ):
        assert quote not in block, (
            "core/mining_guardian.py Qwen post-scan block still contains "
            f"the hard-coded literal {quote} — that path does not exist "
            "in the Mac Mini install tree (canonical location is "
            "${MG_INSTALL_ROOT}/knowledge/knowledge.json with a compat "
            "symlink at ${MG_INSTALL_ROOT}/knowledge.json). Use "
            "`_ROOT / 'knowledge.json'` and `core.file_lock."
            "locked_knowledge_update` instead. P-034."
        )


# ─────────────────────────────────────────────────────────────────────────
# §2. The Qwen block resolves the knowledge path via _ROOT
# ─────────────────────────────────────────────────────────────────────────


def test_qwen_block_uses_root_relative_knowledge_path():
    block = _qwen_block(_scanner_src())
    assert '_ROOT / "knowledge.json"' in block, (
        "core/mining_guardian.py Qwen post-scan block must resolve the "
        "knowledge path via the module-level `_ROOT` (i.e. "
        "`_ROOT / 'knowledge.json'`) so it works under both the dev "
        "clone and the Mac Mini install tree. P-034."
    )


# ─────────────────────────────────────────────────────────────────────────
# §3. The Qwen block uses locked_knowledge_update for the write
# ─────────────────────────────────────────────────────────────────────────


def test_qwen_block_uses_locked_knowledge_update():
    block = _qwen_block(_scanner_src())
    assert "locked_knowledge_update" in block, (
        "core/mining_guardian.py Qwen post-scan block must persist "
        "`llm_scan_analyses` via `core.file_lock.locked_knowledge_update`. "
        "Pre-P-034 the block did its own read-modify-temp-replace, which "
        "(a) raced with every other knowledge writer and (b) hard-coded "
        "the wrong path. P-034."
    )


def test_qwen_block_imports_file_lock_helper():
    """The block (or the module) must actually import the helper it uses."""
    src = _scanner_src()
    assert "from core.file_lock import locked_knowledge_update" in src, (
        "core/mining_guardian.py must import locked_knowledge_update "
        "from core.file_lock for the Qwen post-scan persistence. P-034."
    )


# ─────────────────────────────────────────────────────────────────────────
# §4. No other active scanner-hot-path Python file writes to the bad path
# ─────────────────────────────────────────────────────────────────────────

# We sweep `core/` and `ai/` (the modules pulled in by the scanner loop
# and the AI features that ride alongside it). `archive/`, `installer/`,
# `migrations/`, `intelligence-catalog/`, and the `tests/` tree are
# explicitly excluded — the archive directory in particular preserves
# pre-P-034 backup copies on purpose, and we do not want this regression
# test to fail because of a historical snapshot.

_HOT_PATH_DIRS = ("core", "ai")
_BAD_LITERALS = (
    '"/root/Mining-Guardian/knowledge.json"',
    "'/root/Mining-Guardian/knowledge.json'",
)


def _iter_hot_path_python_files():
    for d in _HOT_PATH_DIRS:
        root = REPO_ROOT / d
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            yield p


def test_no_hot_path_module_hardcodes_root_knowledge_json():
    offenders = []
    for p in _iter_hot_path_python_files():
        text = p.read_text()
        for quote in _BAD_LITERALS:
            if quote in text:
                offenders.append((str(p.relative_to(REPO_ROOT)), quote))
    assert not offenders, (
        "Active scanner-hot-path Python files still hard-code the bad "
        "knowledge path:\n"
        + "\n".join(f"  - {f}: {q}" for f, q in offenders)
        + "\nResolve via `_ROOT / 'knowledge.json'` and "
          "`core.file_lock.locked_knowledge_update`. P-034."
    )
