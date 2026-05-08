"""
tests/test_p036_knowledge_symlink_preserve.py

P-036 (2026-05-08) — symlink-preserving knowledge writes.

Live evidence captured on the customer Mac Mini after installing package
2b41764: the canonical
``/Library/Application Support/MiningGuardian/knowledge/knowledge.json``
remained intact (3,739,968 bytes, 96 profiles, 133 fingerprints, 176
``llm_scan_analyses``) but the top-level compat symlink at
``/Library/Application Support/MiningGuardian/knowledge.json`` was replaced
by a root-owned regular file of 948 bytes at 15:43.

Root cause: P-029 installed
``${MG_INSTALL_ROOT}/knowledge.json -> knowledge/knowledge.json`` as a
symlink. P-034/P-035 writers compute the path as ``_ROOT / "knowledge.json"``
(the symlink). The P-035 ``locked_knowledge_update`` helper (and
``atomic_write_json``) creates a temp file in the same directory and calls
``os.replace(tmp_path, knowledge_path)``. ``os.replace`` of a temp file
onto a symlink path replaces the *symlink* with a regular file rather than
updating the symlink's target.

Fix (P-036): ``core.file_lock`` now resolves the symlink one level before
choosing the temp directory and the rename destination, so the canonical
target file is updated atomically while the symlink at the original
location is left intact. Old non-symlink layouts (including the dev
checkout where ``knowledge.json`` lives directly at the repo root) are
unaffected.
"""

import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.file_lock import (  # noqa: E402  - sys.path mutated above on purpose
    atomic_write_json,
    locked_knowledge_update,
)


def _make_p029_layout(tmp_path: Path) -> tuple[Path, Path]:
    """Build a minimal P-029-style layout under ``tmp_path``.

    Returns (compat_symlink, canonical_file).
    """
    kdir = tmp_path / "knowledge"
    kdir.mkdir()
    canonical = kdir / "knowledge.json"
    canonical.write_text(json.dumps({
        "version": 1,
        "miner_profiles": {},
        "known_issues": [],
        "patterns": [],
    }))
    compat = tmp_path / "knowledge.json"
    # Use a relative target so the resolver's relative-path branch is
    # exercised by at least one test.
    os.symlink("knowledge/knowledge.json", compat)
    return compat, canonical


# ─────────────────────────────────────────────────────────────────────────
# §1. locked_knowledge_update preserves the symlink at the compat path
# ─────────────────────────────────────────────────────────────────────────


def test_locked_update_through_symlink_preserves_link(tmp_path):
    """The compat symlink stays a symlink after a locked write."""
    compat, canonical = _make_p029_layout(tmp_path)
    assert os.path.islink(compat)

    with locked_knowledge_update(str(compat)) as knowledge:
        knowledge["miner_profiles"]["65891"] = {"total_flags": 1}

    # Symlink survives the write.
    assert os.path.islink(compat), (
        "P-036: compat symlink at MG_INSTALL_ROOT/knowledge.json must "
        "survive a locked write that targets the symlink path."
    )
    # Symlink still points at the canonical file.
    assert os.readlink(compat) == "knowledge/knowledge.json"


def test_locked_update_through_symlink_writes_canonical_file(tmp_path):
    """The canonical file (symlink target) is the file actually updated."""
    compat, canonical = _make_p029_layout(tmp_path)
    canonical_inode_before = canonical.stat().st_ino

    with locked_knowledge_update(str(compat)) as knowledge:
        knowledge["miner_profiles"]["65891"] = {"total_flags": 7}

    # The canonical file's content reflects the write.
    on_disk = json.loads(canonical.read_text())
    assert on_disk["miner_profiles"]["65891"]["total_flags"] == 7, (
        "P-036: writes through the compat symlink must update the "
        "canonical knowledge/knowledge.json file."
    )
    # Canonical file's inode changed (atomic replace produced a new file)
    # but the symlink and its target path are still intact.
    assert canonical.stat().st_ino != canonical_inode_before
    # Reading via the symlink also returns the new content.
    via_symlink = json.loads(Path(compat).read_text())
    assert via_symlink["miner_profiles"]["65891"]["total_flags"] == 7


def test_locked_update_does_not_create_regular_file_at_symlink(tmp_path):
    """No regression to the live B-36 shape: the compat path must not
    become a regular file after the write."""
    compat, _ = _make_p029_layout(tmp_path)
    with locked_knowledge_update(str(compat)) as knowledge:
        knowledge["llm_scan_analyses"] = [{"id": "scan-1"}]
    # If the bug is back, this assertion catches it.
    assert not (
        os.path.isfile(compat) and not os.path.islink(compat)
    ), (
        "P-036 regression: locked_knowledge_update replaced the compat "
        "symlink with a regular file. This is the exact failure mode "
        "captured on the Mac Mini at 2026-05-08T15:43."
    )


# ─────────────────────────────────────────────────────────────────────────
# §2. atomic_write_json preserves the symlink as well
# ─────────────────────────────────────────────────────────────────────────


def test_atomic_write_through_symlink_preserves_link(tmp_path):
    compat, canonical = _make_p029_layout(tmp_path)
    atomic_write_json(str(compat), {"version": 2, "marker": "atomic"})
    assert os.path.islink(compat)
    assert json.loads(canonical.read_text())["marker"] == "atomic"


def test_atomic_write_through_symlink_to_absolute_target(tmp_path):
    """Resolver also handles absolute symlink targets."""
    kdir = tmp_path / "knowledge"
    kdir.mkdir()
    canonical = kdir / "knowledge.json"
    canonical.write_text("{}")
    compat = tmp_path / "knowledge.json"
    os.symlink(str(canonical), compat)  # absolute target

    atomic_write_json(str(compat), {"version": 3})
    assert os.path.islink(compat)
    assert json.loads(canonical.read_text())["version"] == 3


# ─────────────────────────────────────────────────────────────────────────
# §3. Non-symlink layouts are unaffected (dev checkout)
# ─────────────────────────────────────────────────────────────────────────


def test_locked_update_on_regular_file_unchanged(tmp_path):
    """Plain regular file (no symlink) — behavior must match pre-P-036."""
    target = tmp_path / "knowledge.json"
    target.write_text("{}")
    with locked_knowledge_update(str(target)) as knowledge:
        knowledge["plain"] = True
    assert json.loads(target.read_text())["plain"] is True
    assert not os.path.islink(target)


def test_locked_update_on_missing_path_creates_file(tmp_path):
    """Path doesn't exist yet — writer creates a regular file (no symlink
    semantics to preserve)."""
    target = tmp_path / "knowledge.json"
    assert not target.exists()
    with locked_knowledge_update(str(target)) as knowledge:
        knowledge["fresh"] = True
    assert target.is_file()
    assert not os.path.islink(target)
    assert json.loads(target.read_text())["fresh"] is True


def test_locked_update_on_broken_symlink_falls_back_to_original_path(tmp_path):
    """Broken symlink — writer creates a file at the symlink path itself.

    This is a defensive edge case: if the canonical target's parent
    directory does not exist, redirecting the rename there would fail.
    The resolver falls back to the original path so the writer can still
    make progress (and operations can investigate the broken symlink).
    """
    compat = tmp_path / "knowledge.json"
    # Target dir does not exist — broken symlink.
    os.symlink("knowledge/knowledge.json", compat)
    assert os.path.islink(compat)
    # Resolver should fall back to the original path. The first write
    # will replace the broken symlink with a regular file because there
    # is no canonical target to redirect to. That's acceptable for this
    # edge case; the production layout the bug describes always has the
    # target dir present.
    with locked_knowledge_update(str(compat)) as knowledge:
        knowledge["fallback"] = True
    # Either it created the file at the symlink path, or it left the
    # broken symlink intact — both are acceptable, but the data must be
    # readable somewhere.
    assert compat.exists() or (tmp_path / "knowledge" / "knowledge.json").exists()


# ─────────────────────────────────────────────────────────────────────────
# §4. End-to-end: KnowledgeManager.save() through the compat symlink
# ─────────────────────────────────────────────────────────────────────────


_HAS_PSYCOPG2 = True
try:  # pragma: no cover - environment-dependent
    import psycopg2  # noqa: F401
except ImportError:
    _HAS_PSYCOPG2 = False


@pytest.mark.skipif(not _HAS_PSYCOPG2, reason="psycopg2 not installed in test env")
def test_knowledge_manager_save_preserves_compat_symlink(tmp_path):
    """End-to-end: KnowledgeManager.save() through the symlink path keeps
    the symlink intact and writes to the canonical file."""
    compat, canonical = _make_p029_layout(tmp_path)

    from ai.knowledge_manager import KnowledgeManager

    km = KnowledgeManager(db_path="unused", knowledge_path=str(compat))
    km.knowledge["marker"] = "from-knowledge-manager"
    km.save()

    assert os.path.islink(compat), (
        "P-036: KnowledgeManager.save() through the compat symlink must "
        "preserve the symlink."
    )
    assert json.loads(canonical.read_text())["marker"] == "from-knowledge-manager"
