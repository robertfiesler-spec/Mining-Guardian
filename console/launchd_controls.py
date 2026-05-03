"""
console/launchd_controls.py — D-19 task pause/resume + status

Wraps `launchctl print system/<label>` and `launchctl bootout / bootstrap`
to give the console a way to pause and resume scheduled tasks. The console
runs as root (it is the 10th LaunchDaemon), so launchctl is in scope.

What pause means: `launchctl bootout system/<label>`. The plist stays on
disk; the daemon stops. Resume calls `launchctl bootstrap system <plist>`
again. This is the same mechanism postinstall.sh uses for its idempotent
re-install path.

Status is parsed from `launchctl print system/<label>`. We do NOT shell
out for every page render — the /tasks endpoint runs N probes in parallel
with a short timeout, but that is bounded.

Test-mode override: setting MG_CONSOLE_LAUNCHCTL=mock causes every probe
to return a static "loaded" / "running" result. Used by unit tests that
must not hit the host launchd.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Any, Dict, Optional

logger = logging.getLogger("console.launchd_controls")

_LAUNCHCTL = shutil.which("launchctl") or "/bin/launchctl"
_PROBE_TIMEOUT_SEC = 1.5


def _mock_mode() -> bool:
    return os.environ.get("MG_CONSOLE_LAUNCHCTL", "").lower() == "mock"


def status(plist_label: Optional[str]) -> Dict[str, Any]:
    """Return a small dict: {"loaded": bool, "running": bool, "pid": int|None,
    "last_exit_code": int|None, "raw": str}.

    On any error or when plist_label is None (in-process pollers), returns
    {"loaded": None, "running": None, ...}.
    """
    if plist_label is None:
        return {"loaded": None, "running": None, "pid": None,
                "last_exit_code": None, "raw": "(in-process)"}

    if _mock_mode():
        return {"loaded": True, "running": True, "pid": 1234,
                "last_exit_code": 0, "raw": "mock"}

    try:
        proc = subprocess.run(
            [_LAUNCHCTL, "print", f"system/{plist_label}"],
            capture_output=True, text=True, timeout=_PROBE_TIMEOUT_SEC,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.debug("status(%s) failed: %s", plist_label, exc)
        return {"loaded": None, "running": None, "pid": None,
                "last_exit_code": None, "raw": f"err: {exc}"}

    if proc.returncode != 0:
        # not loaded
        return {"loaded": False, "running": False, "pid": None,
                "last_exit_code": None, "raw": (proc.stderr or "").strip()[:200]}

    raw = proc.stdout
    pid = None
    last_exit = None
    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("pid = "):
            try:
                pid = int(s.split("=", 1)[1].strip())
            except ValueError:
                pid = None
        elif s.startswith("last exit code = "):
            try:
                last_exit = int(s.split("=", 1)[1].strip())
            except ValueError:
                last_exit = None
    return {"loaded": True, "running": pid is not None,
            "pid": pid, "last_exit_code": last_exit,
            "raw": raw[:500]}


def pause(plist_label: str) -> bool:
    """Run `launchctl bootout system/<label>`. Returns True on success."""
    if _mock_mode():
        logger.info("MOCK pause %s", plist_label)
        return True
    try:
        proc = subprocess.run(
            [_LAUNCHCTL, "bootout", f"system/{plist_label}"],
            capture_output=True, text=True, timeout=_PROBE_TIMEOUT_SEC * 2,
        )
        return proc.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.warning("pause(%s) failed: %s", plist_label, exc)
        return False


def resume(plist_label: str, plist_path: str) -> bool:
    """Run `launchctl bootstrap system <plist_path>`. Returns True on success.

    Caller must supply the absolute path to the plist on disk (typically
    /Library/LaunchDaemons/<label>.plist on the customer Mini)."""
    if _mock_mode():
        logger.info("MOCK resume %s from %s", plist_label, plist_path)
        return True
    if not os.path.isabs(plist_path):
        return False
    try:
        proc = subprocess.run(
            [_LAUNCHCTL, "bootstrap", "system", plist_path],
            capture_output=True, text=True, timeout=_PROBE_TIMEOUT_SEC * 2,
        )
        return proc.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.warning("resume(%s) failed: %s", plist_label, exc)
        return False
