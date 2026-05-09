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
4. Owner/mode normalization on the canonical target (P-037) — after
   atomic replace, enforce mode 0664 and (on installed macOS) ownership
   ``${MG_INSTALL_OPERATOR_USER:-miningguardian}:staff``. Best-effort: if
   the user/group does not exist (dev/test workstations) or the process
   is not privileged enough to chown, the chown is skipped silently and
   the chmod still applies. ``tempfile.mkstemp`` creates files at 0600
   and ``os.replace`` carries the source mode bits to the destination,
   so without explicit normalization every scan rewrote the canonical
   knowledge file as 0600 root-owned (live evidence on the customer Mini
   2026-05-09 after installing pkg e3461260 — see B-46 / P-037).

Usage:
    from core.file_lock import locked_knowledge_update

    def my_writer():
        with locked_knowledge_update(KNOWLEDGE_PATH) as knowledge:
            knowledge["my_section"] = new_data
            # knowledge is automatically saved atomically on exit
"""

import fcntl
import grp
import json
import logging
import os
import pwd
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

logger = logging.getLogger("file_lock")

# P-037 (2026-05-09). Canonical mode + owner/group for knowledge writes
# on the installed Mac Mini. ``MG_INSTALL_OPERATOR_USER`` is set by the
# installer postinstall (D-13 / P-029) to the customer's chosen account
# (default ``miningguardian``). The group is always ``staff`` on macOS
# per the postinstall layout. On dev/test workstations the user/group
# typically does not exist — the helper skips chown and only enforces
# the mode, which keeps the test suite portable without root.
_KNOWLEDGE_FILE_MODE = 0o664
_KNOWLEDGE_FILE_GROUP = "staff"
_KNOWLEDGE_FILE_OWNER_DEFAULT = "miningguardian"


def _resolve_owner_user() -> str:
    """Return the configured operator user.

    Honours ``MG_INSTALL_OPERATOR_USER`` (set by postinstall) so a
    customer who installed under a different account name still gets
    correct ownership normalization. Falls back to ``miningguardian``
    which matches the default installer-created account.
    """
    return (
        os.environ.get("MG_INSTALL_OPERATOR_USER")
        or _KNOWLEDGE_FILE_OWNER_DEFAULT
    )


def _normalize_knowledge_perms(
    path: str,
    *,
    mode: int = _KNOWLEDGE_FILE_MODE,
    owner_user: Optional[str] = None,
    owner_group: str = _KNOWLEDGE_FILE_GROUP,
) -> None:
    """Enforce mode + (best-effort) owner on the canonical knowledge file.

    P-037 (2026-05-09). After ``os.replace`` lands the temp file on the
    canonical target, the destination inherits the temp file's mode
    (0600 from ``tempfile.mkstemp``) and is owned by whoever ran the
    writer (``root`` under launchd on macOS). Without this normalization,
    the canonical knowledge file ends up unreadable to the operator
    account and unwritable by the next scan unless it manages to clobber
    via root again — and the operator-side cron path (e.g. catalog
    importer) cannot read 0600 root-owned files at all.

    Behaviour:
      * mode is set unconditionally (cheap, idempotent, dev-portable).
      * owner is resolved via ``pwd.getpwnam`` / ``grp.getgrnam``; if
        either is missing (dev/test machines without the
        installer-created accounts) the chown is skipped silently.
      * a chown failure (EPERM — running as a non-privileged user) is
        also swallowed; the next privileged write still corrects it.

    The path is NOT followed through symlinks for the chmod (we already
    write to the canonical target via ``_resolve_write_target``); a
    chmod on the symlink itself would be a no-op on Linux anyway. The
    caller passes the canonical target path directly.
    """
    try:
        os.chmod(path, mode)
    except OSError as exc:
        # Best-effort. If we can't chmod (no permission), the next
        # privileged write will heal it. Log at debug to keep the
        # scanner hot path quiet.
        logger.debug(
            "file_lock: chmod %o on %s failed: %s", mode, path, exc,
        )
        return

    user_name = owner_user or _resolve_owner_user()
    try:
        uid = pwd.getpwnam(user_name).pw_uid
        gid = grp.getgrnam(owner_group).gr_gid
    except KeyError:
        # User/group absent (dev workstation, CI). Mode-only is good
        # enough — the installed Mini has the accounts created by
        # postinstall.
        return
    try:
        os.chown(path, uid, gid)
    except OSError as exc:
        # EPERM — running as non-root and not the file's current owner.
        # The next privileged write will heal it; log at debug so the
        # hot path stays quiet on dev workstations.
        logger.debug(
            "file_lock: chown %s:%s on %s failed: %s",
            user_name, owner_group, path, exc,
        )


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

    Owner/mode-safe (P-037): after the atomic replace, the canonical
    target is normalized to mode 0664 and (best-effort) owner
    ``${MG_INSTALL_OPERATOR_USER:-miningguardian}:staff``. Dev/test
    workstations without those accounts get mode-only normalization.
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
            # P-037 — heal mode + owner on the canonical target so a
            # root-owned 0600 file from launchd does not lock the
            # operator account out of subsequent reads/writes.
            _normalize_knowledge_perms(write_target)
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

    Owner/mode-safe (P-037): the canonical target is normalized to mode
    0664 and (best-effort) owner ``${MG_INSTALL_OPERATOR_USER:-miningguardian}:staff``
    after the replace. See ``_normalize_knowledge_perms``.
    """
    write_target = _resolve_write_target(path)
    dir_name = os.path.dirname(write_target) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, write_target)
        _normalize_knowledge_perms(write_target)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
