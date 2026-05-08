"""
file_lock.py — Shared file-locking utility for knowledge.json

Multiple modules (knowledge_manager, predictor, fingerprint_builder,
hvac_correlator, outcome_checker, insight_manager) read-modify-write
knowledge.json concurrently. Without locking, concurrent writes silently
lose data. This module provides:

1. File-level locking via fcntl.flock() (Unix advisory lock)
2. Atomic writes via temp file + os.replace()
3. Symlink-preserving replace (P-036) — when the path is a symlink, the
   atomic rename lands on the symlink's target file, not on the symlink.

Usage:
    from core.file_lock import locked_knowledge_update

    def my_writer():
        with locked_knowledge_update(KNOWLEDGE_PATH) as knowledge:
            knowledge["my_section"] = new_data
            # knowledge is automatically saved atomically on exit
"""

import fcntl
import json
import logging
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger("file_lock")


def _resolve_write_target(knowledge_path: str) -> str:
    """Return the canonical path the atomic rename should land on.

    P-036 (2026-05-08). The P-029 layout puts the active runtime knowledge
    file at ``${MG_INSTALL_ROOT}/knowledge/knowledge.json`` and a
    compatibility symlink at ``${MG_INSTALL_ROOT}/knowledge.json`` pointing
    at it. Most existing writers compute their path as
    ``_ROOT / "knowledge.json"`` — i.e. the symlink. ``os.replace`` from a
    temp file in the same parent directory replaces the *symlink* with a
    regular file rather than updating the symlink's target. The Mini
    install logged exactly that on 2026-05-08: a 948-byte regular file
    appeared at ``…/MiningGuardian/knowledge.json`` while the canonical
    3.7 MB knowledge file under ``knowledge/`` stayed intact but unused
    by readers that follow the symlink.

    The fix: when the supplied path is a symlink, follow it once and use
    the link target as the rename destination. The temp file is created
    in the *target's* directory so the os.replace is on the same
    filesystem and the symlink itself is left untouched.

    Non-symlink paths are returned unchanged. Broken symlinks (target
    doesn't exist) also return the original path so the writer creates a
    new file at the symlink location and the existing behavior is
    preserved (rare, but covered by tests).
    """
    try:
        if os.path.islink(knowledge_path):
            # readlink returns the target literally; resolve relative to
            # the symlink's parent so a relative target like
            # "knowledge/knowledge.json" works.
            link_target = os.readlink(knowledge_path)
            if not os.path.isabs(link_target):
                link_target = os.path.normpath(
                    os.path.join(os.path.dirname(knowledge_path), link_target)
                )
            # Only redirect when the target's parent dir exists; otherwise
            # the writer would fail on tempfile.mkstemp and we'd lose the
            # graceful "create file at symlink" fallback.
            if os.path.isdir(os.path.dirname(link_target) or "."):
                return link_target
    except OSError:
        # readlink can raise on race / permission edge cases. Fall through
        # and use the original path; the caller will surface any error.
        pass
    return knowledge_path


@contextmanager
def locked_knowledge_update(knowledge_path: str):
    """Context manager: acquires file lock, loads JSON, yields dict, saves atomically.

    Usage:
        with locked_knowledge_update("/path/to/knowledge.json") as k:
            k["section"] = data

    Symlink-safe (P-036): if ``knowledge_path`` is a symlink, the atomic
    rename targets the symlink's underlying file, leaving the symlink
    intact.
    """
    write_target = _resolve_write_target(knowledge_path)
    # Lock on the symlink target as well so two writers — one given the
    # symlink, one given the canonical path — serialize against the same
    # lock file.
    lock_path = write_target + ".lock"
    lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        # Load current state under lock from the symlink (which transparently
        # resolves to the canonical file, keeping reader semantics consistent
        # with non-symlink layouts).
        path = Path(knowledge_path)
        if path.exists():
            try:
                knowledge = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                knowledge = {}
        else:
            knowledge = {}

        yield knowledge

        # Atomic write: temp file in the target's directory then os.replace
        # onto the canonical file (symlink left intact when applicable).
        dir_name = os.path.dirname(write_target) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(knowledge, f, indent=2)
            os.replace(tmp_path, write_target)
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()


def atomic_write_json(path: str, data: dict):
    """Write JSON atomically (temp file + os.replace) without locking.

    Use this only when the caller already holds the lock or when
    locking is not needed (single-writer scenarios).

    Symlink-safe (P-036): if ``path`` is a symlink, the rename targets
    the symlink's underlying file rather than replacing the symlink.
    """
    write_target = _resolve_write_target(path)
    dir_name = os.path.dirname(write_target) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, write_target)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
