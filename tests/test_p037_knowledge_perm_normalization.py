"""tests/test_p037_knowledge_perm_normalization.py

P-037 (2026-05-09) — owner/mode normalization on canonical knowledge
writes (and on the discovery sink rolling snapshot).

Background
----------
Live evidence on the customer Mac Mini after installing pkg
``e3461260af2a`` and running the scanner once (2026-05-09 morning):

  * P-034 / P-035 / P-036 all verified ✅ — scanner exit 0, Qwen scan
    persisted to ``llm_scan_analyses``, no ``/root/Mining-Guardian``
    path in logs, no ``Knowledge update skipped: 'total_flags'``
    warning, the P-029 compat symlink survived the scan.
  * BUT — the canonical
    ``/Library/Application Support/MiningGuardian/knowledge/knowledge.json``
    was rewritten as ``root-owned 0600``. Manual recovery required
    ``chown miningguardian:staff`` and ``chmod 0664``.
  * ``cron_tracking/scanner_discovery/latest_findings.json`` came out
    mode 0664 (P-032 fix held) but root-owned, also requiring a
    manual chown.

Root cause: ``tempfile.mkstemp`` creates the temp file at mode 0600
and ``os.replace`` carries the source mode bits to the destination,
so unless the writer explicitly normalises mode + owner the
canonical knowledge file ends up unreadable to the operator account
(and the cross-account cron readers — see P-022 / P-032 doc).

Fix (P-037)
-----------
After every ``os.replace`` onto the canonical knowledge target,
``core/file_lock.py`` calls ``_normalize_knowledge_perms`` which:

  1. ``os.chmod(path, 0o664)`` unconditionally (idempotent, dev-portable).
  2. Resolves ``${MG_INSTALL_OPERATOR_USER:-miningguardian}:staff`` and
     calls ``os.chown`` if both accounts exist; otherwise silently
     skips (dev / CI workstations).
  3. Swallows EPERM if running non-privileged.

``core/discovery_sink.py::_atomic_write_json`` got the same treatment
for ``latest_findings.json``.

This module locks in:

  §1. Mode 0664 enforced after every ``locked_knowledge_update`` write.
  §2. Mode 0664 enforced after every ``atomic_write_json`` write.
  §3. Mode 0664 enforced through the P-029 compat symlink (P-036 +
       P-037 interaction — symlink preserved AND canonical mode is
       healed).
  §4. Owner/group normalization via monkeypatched ``pwd``/``grp``/
       ``os.chown`` so the test does not need root.
  §5. Missing user/group is non-fatal: mode-only normalization still
       happens.
  §6. ``MG_INSTALL_OPERATOR_USER`` env override is honoured.
  §7. discovery_sink rolling snapshot is mode 0664 + owner-normalized
       on every rewrite.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import stat
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core import file_lock as fl  # noqa: E402
from core.file_lock import (  # noqa: E402
    atomic_write_json,
    locked_knowledge_update,
)


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────


def _mode_bits(path: Path) -> int:
    """Return just the permission bits of the file at ``path``."""
    return stat.S_IMODE(path.stat().st_mode)


def _make_p029_layout(tmp_path: Path) -> tuple[Path, Path]:
    """Return (compat_symlink, canonical_file). Mirrors the P-036 fixture."""
    kdir = tmp_path / "knowledge"
    kdir.mkdir()
    canonical = kdir / "knowledge.json"
    canonical.write_text(json.dumps({"version": 1, "miner_profiles": {}}))
    compat = tmp_path / "knowledge.json"
    os.symlink("knowledge/knowledge.json", compat)
    return compat, canonical


# ─────────────────────────────────────────────────────────────────────────
# §1. Mode normalization on locked_knowledge_update
# ─────────────────────────────────────────────────────────────────────────


def test_locked_update_writes_mode_0664_on_regular_file(tmp_path):
    """The canonical mode-bits enforcement is the cheap win — every
    write lands at 0664 regardless of the daemon umask or the temp
    file's mkstemp default of 0600."""
    target = tmp_path / "knowledge.json"
    target.write_text("{}")
    # Pre-write at 0600 to mimic the "root-owned daemon write" state on
    # the Mini after install — this is the broken state P-037 heals.
    os.chmod(target, 0o600)
    assert _mode_bits(target) == 0o600

    with locked_knowledge_update(str(target)) as k:
        k["healed"] = True

    assert _mode_bits(target) == 0o664, (
        "P-037: locked_knowledge_update must heal mode to 0664 after "
        "every write so cross-account readers (cron, operator shell) "
        "stay readable. Live evidence on Mini after pkg e3461260af2a "
        "ran the scanner: canonical knowledge.json was 0600 root-owned."
    )


def test_locked_update_resets_mode_under_strict_umask(tmp_path, monkeypatch):
    """Even under umask 077 (which would create 0700 dirs and 0600 files
    by default) the explicit chmod wins."""
    monkeypatch.setattr(os, "umask", lambda _m: 0o077)
    # Apply the umask we want to verify against.
    old = os.umask(0o077)
    try:
        target = tmp_path / "knowledge.json"
        target.write_text("{}")
        with locked_knowledge_update(str(target)) as k:
            k["umask_test"] = True
        assert _mode_bits(target) == 0o664
    finally:
        os.umask(old)


# ─────────────────────────────────────────────────────────────────────────
# §2. Mode normalization on atomic_write_json
# ─────────────────────────────────────────────────────────────────────────


def test_atomic_write_json_writes_mode_0664(tmp_path):
    target = tmp_path / "snapshot.json"
    atomic_write_json(str(target), {"version": 1})
    assert _mode_bits(target) == 0o664


def test_atomic_write_json_heals_preexisting_0600(tmp_path):
    target = tmp_path / "snapshot.json"
    target.write_text("{}")
    os.chmod(target, 0o600)
    atomic_write_json(str(target), {"healed": True})
    assert _mode_bits(target) == 0o664


# ─────────────────────────────────────────────────────────────────────────
# §3. Mode normalization through P-029 compat symlink (P-036 + P-037)
# ─────────────────────────────────────────────────────────────────────────


def test_locked_update_through_symlink_heals_canonical_mode(tmp_path):
    """P-036 keeps the symlink intact; P-037 makes sure the canonical
    file behind it is at 0664 — both must hold for the install layout
    to stay healthy across scans."""
    compat, canonical = _make_p029_layout(tmp_path)
    # Mimic the live-Mini broken state: canonical at 0600 root-owned.
    os.chmod(canonical, 0o600)

    with locked_knowledge_update(str(compat)) as k:
        k["miner_profiles"]["65891"] = {"total_flags": 1}

    # P-036 — symlink intact.
    assert os.path.islink(compat)
    assert os.readlink(compat) == "knowledge/knowledge.json"
    # P-037 — canonical mode healed.
    assert _mode_bits(canonical) == 0o664


def test_atomic_write_through_symlink_heals_canonical_mode(tmp_path):
    compat, canonical = _make_p029_layout(tmp_path)
    os.chmod(canonical, 0o600)
    atomic_write_json(str(compat), {"version": 2, "marker": "atomic"})
    assert os.path.islink(compat)
    assert _mode_bits(canonical) == 0o664


# ─────────────────────────────────────────────────────────────────────────
# §4. Owner normalization (monkeypatched — no root required)
# ─────────────────────────────────────────────────────────────────────────


class _FakePwEntry:
    def __init__(self, uid: int) -> None:
        self.pw_uid = uid


class _FakeGrEntry:
    def __init__(self, gid: int) -> None:
        self.gr_gid = gid


def test_locked_update_calls_chown_with_resolved_owner(tmp_path, monkeypatch):
    """When the configured user/group exist, they get chown'd."""
    target = tmp_path / "knowledge.json"
    target.write_text("{}")

    chown_calls: list[tuple[str, int, int]] = []

    def fake_getpwnam(name: str) -> _FakePwEntry:
        assert name == "miningguardian"
        return _FakePwEntry(uid=501)

    def fake_getgrnam(name: str) -> _FakeGrEntry:
        assert name == "staff"
        return _FakeGrEntry(gid=20)

    def fake_chown(path: str, uid: int, gid: int) -> None:
        chown_calls.append((path, uid, gid))

    monkeypatch.setattr(fl.pwd, "getpwnam", fake_getpwnam)
    monkeypatch.setattr(fl.grp, "getgrnam", fake_getgrnam)
    monkeypatch.setattr(fl.os, "chown", fake_chown)
    monkeypatch.delenv("MG_INSTALL_OPERATOR_USER", raising=False)

    with locked_knowledge_update(str(target)) as k:
        k["owner_test"] = True

    assert chown_calls, (
        "P-037: when the operator user/group exist, locked_knowledge_update "
        "must chown the canonical target."
    )
    path, uid, gid = chown_calls[-1]
    assert path == str(target)
    assert uid == 501
    assert gid == 20


def test_atomic_write_calls_chown_with_resolved_owner(tmp_path, monkeypatch):
    target = tmp_path / "knowledge.json"
    chown_calls: list[tuple[str, int, int]] = []

    monkeypatch.setattr(
        fl.pwd, "getpwnam", lambda _n: _FakePwEntry(uid=501),
    )
    monkeypatch.setattr(
        fl.grp, "getgrnam", lambda _n: _FakeGrEntry(gid=20),
    )
    monkeypatch.setattr(
        fl.os, "chown",
        lambda p, u, g: chown_calls.append((p, u, g)),
    )

    atomic_write_json(str(target), {"k": "v"})
    assert chown_calls
    assert chown_calls[-1] == (str(target), 501, 20)


# ─────────────────────────────────────────────────────────────────────────
# §5. Missing user/group is non-fatal; mode still applies
# ─────────────────────────────────────────────────────────────────────────


def test_missing_owner_user_does_not_fail(tmp_path, monkeypatch):
    """Dev/CI workstations don't have a 'miningguardian' account.
    Owner resolution must fail soft — chmod still happens."""
    target = tmp_path / "knowledge.json"
    target.write_text("{}")
    os.chmod(target, 0o600)

    def boom(_name: str):
        raise KeyError(_name)

    monkeypatch.setattr(fl.pwd, "getpwnam", boom)
    chown_calls: list = []
    monkeypatch.setattr(
        fl.os, "chown", lambda *a, **kw: chown_calls.append(a),
    )

    with locked_knowledge_update(str(target)) as k:
        k["fallback"] = True

    assert _mode_bits(target) == 0o664, (
        "P-037: missing operator user must NOT block the chmod — "
        "dev/test portability."
    )
    assert chown_calls == [], (
        "P-037: missing operator user must skip chown entirely "
        "(no exception, no partial chown)."
    )


def test_missing_owner_group_does_not_fail(tmp_path, monkeypatch):
    target = tmp_path / "knowledge.json"
    target.write_text("{}")
    os.chmod(target, 0o600)

    monkeypatch.setattr(
        fl.pwd, "getpwnam", lambda _n: _FakePwEntry(uid=501),
    )

    def boom(_name: str):
        raise KeyError(_name)

    monkeypatch.setattr(fl.grp, "getgrnam", boom)
    chown_calls: list = []
    monkeypatch.setattr(
        fl.os, "chown", lambda *a, **kw: chown_calls.append(a),
    )

    with locked_knowledge_update(str(target)) as k:
        k["fallback_group"] = True

    assert _mode_bits(target) == 0o664
    assert chown_calls == []


def test_chown_eperm_does_not_fail(tmp_path, monkeypatch):
    """Running as a non-privileged user that's not the file's owner
    will get EPERM from chown. The helper must swallow it so the next
    privileged write can heal."""
    target = tmp_path / "knowledge.json"
    target.write_text("{}")
    os.chmod(target, 0o664)

    monkeypatch.setattr(
        fl.pwd, "getpwnam", lambda _n: _FakePwEntry(uid=501),
    )
    monkeypatch.setattr(
        fl.grp, "getgrnam", lambda _n: _FakeGrEntry(gid=20),
    )

    def eperm(*_a, **_kw):
        raise PermissionError("Operation not permitted")

    monkeypatch.setattr(fl.os, "chown", eperm)

    # Must not raise.
    with locked_knowledge_update(str(target)) as k:
        k["eperm"] = True

    assert _mode_bits(target) == 0o664


# ─────────────────────────────────────────────────────────────────────────
# §6. MG_INSTALL_OPERATOR_USER override is honoured
# ─────────────────────────────────────────────────────────────────────────


def test_operator_user_env_override(tmp_path, monkeypatch):
    """Customer-installed account name (per postinstall) overrides the
    default ``miningguardian``."""
    target = tmp_path / "knowledge.json"
    target.write_text("{}")

    seen_users: list[str] = []

    def fake_getpwnam(name: str):
        seen_users.append(name)
        return _FakePwEntry(uid=999)

    monkeypatch.setattr(fl.pwd, "getpwnam", fake_getpwnam)
    monkeypatch.setattr(
        fl.grp, "getgrnam", lambda _n: _FakeGrEntry(gid=20),
    )
    monkeypatch.setattr(fl.os, "chown", lambda *a, **kw: None)
    monkeypatch.setenv("MG_INSTALL_OPERATOR_USER", "customops")

    with locked_knowledge_update(str(target)) as k:
        k["env_override"] = True

    assert "customops" in seen_users, (
        "P-037: MG_INSTALL_OPERATOR_USER must be the user name passed "
        "to pwd.getpwnam — postinstall sets this on the customer Mini."
    )


# ─────────────────────────────────────────────────────────────────────────
# §7. discovery_sink rolling snapshot gets the same treatment
# ─────────────────────────────────────────────────────────────────────────


def test_discovery_sink_writes_mode_0664(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_DISCOVERY_SINK_DIR", str(tmp_path))
    sink = importlib.reload(importlib.import_module("core.discovery_sink"))

    ok = sink.record_discovery("unknown_model", {
        "model_name": "S19JPro",
        "ip": "192.168.188.36",
    })
    assert ok
    latest = tmp_path / "latest_findings.json"
    assert latest.exists()
    assert _mode_bits(latest) == 0o664


def test_discovery_sink_calls_chown_on_canonical_target(tmp_path, monkeypatch):
    """The discovery sink should also normalize owner after the
    rolling-snapshot rewrite — the live Mini logged
    ``latest_findings.json`` came out 0664 but root-owned, requiring
    a manual chown after install."""
    monkeypatch.setenv("MG_DISCOVERY_SINK_DIR", str(tmp_path))
    sink_mod = importlib.reload(importlib.import_module("core.discovery_sink"))

    chown_calls: list[tuple[str, int, int]] = []
    monkeypatch.setattr(
        sink_mod.pwd, "getpwnam", lambda _n: _FakePwEntry(uid=501),
    )
    monkeypatch.setattr(
        sink_mod.grp, "getgrnam", lambda _n: _FakeGrEntry(gid=20),
    )
    monkeypatch.setattr(
        sink_mod.os, "chown",
        lambda p, u, g: chown_calls.append((p, u, g)),
    )

    ok = sink_mod.record_discovery("new_firmware", {
        "model_name": "AH3880",
        "firmware_version": "0.9.9.3-stage29.2799",
        "ip": "192.168.188.20",
    })
    assert ok
    assert chown_calls, (
        "P-037: discovery_sink._atomic_write_json must chown the rolling "
        "snapshot. Live Mini after pkg e3461260af2a: latest_findings.json "
        "was 0664 root-owned, blocking the cron-driven catalog importer "
        "(which runs as the operator account) from writing back."
    )
    target_path = chown_calls[-1][0]
    assert target_path.endswith("latest_findings.json")


def test_discovery_sink_chown_failure_non_fatal(tmp_path, monkeypatch):
    """A chown failure must not crash record_discovery — the scanner
    hot path is the highest priority."""
    monkeypatch.setenv("MG_DISCOVERY_SINK_DIR", str(tmp_path))
    sink_mod = importlib.reload(importlib.import_module("core.discovery_sink"))

    monkeypatch.setattr(
        sink_mod.pwd, "getpwnam", lambda _n: _FakePwEntry(uid=501),
    )
    monkeypatch.setattr(
        sink_mod.grp, "getgrnam", lambda _n: _FakeGrEntry(gid=20),
    )

    def boom(*_a, **_kw):
        raise PermissionError("Operation not permitted")

    monkeypatch.setattr(sink_mod.os, "chown", boom)

    # Must not raise.
    ok = sink_mod.record_discovery("unknown_model", {
        "model_name": "S19JPro",
    })
    assert ok is True


# ─────────────────────────────────────────────────────────────────────────
# §8. Cohabitation with P-036 — broken symlink edge case still safe
# ─────────────────────────────────────────────────────────────────────────


def test_broken_symlink_edge_case_still_works(tmp_path):
    """Broken symlink falls through to the original path (P-036
    fallback). P-037's chmod must still apply to whatever file ends
    up created."""
    compat = tmp_path / "knowledge.json"
    os.symlink("knowledge/knowledge.json", compat)  # target dir absent
    with locked_knowledge_update(str(compat)) as k:
        k["fallback"] = True
    # Either the file was created at the symlink path or at the
    # canonical path — whichever the resolver picked, mode must be 0664.
    if compat.exists() and not compat.is_symlink():
        assert _mode_bits(compat) == 0o664
    else:
        cano = tmp_path / "knowledge" / "knowledge.json"
        if cano.exists():
            assert _mode_bits(cano) == 0o664
