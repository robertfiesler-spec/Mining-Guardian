"""
file_lock.py — Shared file-locking utility for knowledge.json

Multiple modules (knowledge_manager, predictor, fingerprint_builder,
hvac_correlator, outcome_checker, insight_manager) read-modify-write
knowledge.json concurrently. Without locking, concurrent writes silently
lose data. This module provides:

1. File-level locking via fcntl.flock() (Unix advisory lock)
2. Atomic writes via temp file + os.replace()

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


@contextmanager
def locked_knowledge_update(knowledge_path: str):
    """Context manager: acquires file lock, loads JSON, yields dict, saves atomically.

    Usage:
        with locked_knowledge_update("/path/to/knowledge.json") as k:
            k["section"] = data
    """
    lock_path = knowledge_path + ".lock"
    lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        # Load current state under lock
        path = Path(knowledge_path)
        if path.exists():
            try:
                knowledge = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                knowledge = {}
        else:
            knowledge = {}

        yield knowledge

        # Atomic write: temp file in same directory then os.replace
        dir_name = os.path.dirname(knowledge_path) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(knowledge, f, indent=2)
            os.replace(tmp_path, knowledge_path)
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
    """
    dir_name = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
