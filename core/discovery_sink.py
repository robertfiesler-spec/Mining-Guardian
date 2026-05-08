"""core/discovery_sink.py — P-022 (2026-05-08) scanner-discovery JSON sink.

Persists scanner-side intelligence findings (unknown miner models, new
firmware versions) to a durable file under
``${INSTALL_ROOT}/cron_tracking/scanner_discovery/`` on every scan.

Why this exists
---------------
Audit (2026-05-08) of the daily catalog-import path found that the
``com.miningguardian.scheduled.catalog-import`` job has nothing to
consume on customer Macs: ``cron_tracking/`` is empty, no Perplexity
watcher writes there, and the scanner's discovery findings (unknown
``S19JPro`` / ``S21EXPHyd`` / ``AH3880`` / ``S21Imm`` model rows + the
``0.9.9.3-stage29.2799`` firmware string) are persisted to the
``discovery_log`` table but **never surfaced to the file-based intake
surface every other catalog-bound source uses**. The 5 Perplexity
watchers all write JSON to ``cron_tracking/<watcher>/`` — for them to
participate in the same intake pipeline, the scanner needs to write
the same way.

This module is the smallest possible slice that closes the gap:

* A single function ``record_discovery(event_type, payload)`` appends
  to the date-stamped JSONL stream and updates a rolling
  ``latest_findings.json`` for the daily import job to read.
* Atomic write semantics: temp-file + ``os.replace`` so a crash mid-
  write never leaves a corrupted JSON.
* Dedup-with-counters: the rolling file groups events by
  ``(event_type, model_name, firmware_version)`` and tracks
  ``first_seen``, ``last_seen``, ``count``, ``ips`` (set of last-N
  IPs). The scanner runs hourly; without dedup the file would grow
  unboundedly.
* Side-effect-free: a missing install root, a permission error, or
  any I/O failure is swallowed with a single WARNING log. The scanner
  never raises out of the discovery hot path.

The on-disk shape is documented in ``docs/SCANNER_DISCOVERY_SINK.md``.

Layout
~~~~~~
::

    ${INSTALL_ROOT}/cron_tracking/scanner_discovery/
        latest_findings.json      <- rolling dedup'd snapshot (the file
                                     the catalog-import job reads)
        events-YYYY-MM-DD.jsonl   <- append-only audit trail (one JSON
                                     object per line, never rewritten)

The catalog-import wrapper inspects ``latest_findings.json``'s presence
and event count and reports them — so even if the import path doesn't
yet promote scanner_discovery findings into ``staging.miner_model_proposals``
(that's a follow-up PR), the data is no longer wasted.

Public API
~~~~~~~~~~
* ``record_discovery(event_type, payload)`` — append + update rolling
  snapshot. Best-effort; never raises.
* ``read_latest()`` — return the current rolling snapshot dict (used
  by tests and by future readers). Returns ``{}`` on absent/corrupt
  file.
* ``resolve_sink_dir()`` — return the absolute Path to the sink
  directory. Mirrors ``_resolve_log_dir`` in ``core/mining_guardian.py``.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("mining_guardian.discovery_sink")

_ROOT = Path(__file__).resolve().parent.parent

# Cap the per-key IP list so a noisy fleet doesn't unbounded-grow the
# rolling file. 16 unique IPs is enough to characterise the spread of a
# new model across the fleet without retaining every observation.
_MAX_IPS_PER_KEY = 16


def resolve_sink_dir() -> Path:
    """Return the directory the sink writes into.

    Resolution order mirrors ``core/mining_guardian.py::_resolve_log_dir``:

    1. ``MG_DISCOVERY_SINK_DIR`` env var (explicit override).
    2. ``MG_INSTALL_ROOT`` env var → ``<root>/cron_tracking/scanner_discovery``.
    3. Inferred install root from this file's location → repo root /
       ``cron_tracking/scanner_discovery`` (dev-tree invocation).
    """
    explicit = os.environ.get("MG_DISCOVERY_SINK_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    install_root = os.environ.get("MG_INSTALL_ROOT")
    if install_root:
        return (
            Path(install_root).expanduser().resolve()
            / "cron_tracking"
            / "scanner_discovery"
        )
    return _ROOT / "cron_tracking" / "scanner_discovery"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _atomic_write_json(path: Path, payload: Any) -> None:
    """Write JSON to ``path`` via a temp-file + ``os.replace``.

    Same dir as the target so the rename is atomic (POSIX guarantees
    same-fs rename atomicity).

    P-032 (2026-05-08) — explicitly chmod the temp file to 0664 before
    the atomic replace. ``tempfile.mkstemp`` creates the temp file with
    mode 0600 by design, and ``os.replace`` preserves the source file's
    mode bits when it overwrites the destination. The net effect was
    that every scan rewrote ``latest_findings.json`` (and any future
    JSON the sink writes) as 0600, even after the P-027 postinstall step
    healed the on-disk file to 0664. The cron-driven import job runs
    under a different account on customer Macs, so a 0600 snapshot is
    unreadable to it. Setting mode 0664 here keeps the sink aligned with
    P-027's expectation (group-readable+writable, world-readable) and
    survives subsequent rewrites without operator intervention.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True, default=str)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        # P-032: align with P-027 postinstall (0664) so cron-driven
        # readers running under a different account can still consume the
        # rolling snapshot after each scan.
        os.chmod(tmp_name, 0o664)
        os.replace(tmp_name, path)
    except Exception:
        # Best-effort cleanup of the temp file; never raise.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _key_for(event_type: str, payload: Dict[str, Any]) -> str:
    """Stable dedup key per event family.

    * unknown_model: keyed by raw model name (the AMS-emitted form, NOT
      the normalised slug — we want one row per AMS-observed string so
      the catalog-import job sees the actual scanner observation).
    * new_firmware: keyed by (model_name, firmware_version).

    Unknown event types fall through to a defensive "type|model|fw" key
    so any future event family is at least distinguishable.
    """
    model = (payload.get("model_name") or "").strip()
    firmware = (payload.get("firmware_version") or "").strip()
    if event_type == "unknown_model":
        return f"unknown_model|{model}"
    if event_type == "new_firmware":
        return f"new_firmware|{model}|{firmware}"
    return f"{event_type}|{model}|{firmware}"


def _load_snapshot(latest_path: Path) -> Dict[str, Any]:
    if not latest_path.exists():
        return {"version": 1, "events": {}}
    try:
        with latest_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "events" not in data:
            return {"version": 1, "events": {}}
        return data
    except (OSError, json.JSONDecodeError):
        # A torn write from before atomic-replace was added, or a manual
        # edit that broke the file. Reset rather than crash; the
        # append-only events-*.jsonl is the real audit trail.
        logger.warning(
            "discovery_sink: latest_findings.json unreadable, "
            "resetting in place: %s", latest_path,
        )
        return {"version": 1, "events": {}}


def _merge_event(snapshot: Dict[str, Any], event_type: str,
                 payload: Dict[str, Any], now: str) -> None:
    key = _key_for(event_type, payload)
    events: Dict[str, Any] = snapshot.setdefault("events", {})
    existing = events.get(key)
    ip = (payload.get("ip") or "").strip()
    if existing is None:
        events[key] = {
            "event_type": event_type,
            "model_name": payload.get("model_name", "") or "",
            "firmware_version": payload.get("firmware_version", "") or "",
            "first_seen": now,
            "last_seen": now,
            "count": 1,
            "ips": [ip] if ip else [],
            "miner_id_examples": (
                [str(payload["miner_id"])]
                if payload.get("miner_id") is not None
                else []
            ),
            "source": payload.get("source", "scanner_discovery"),
        }
        return
    existing["last_seen"] = now
    existing["count"] = int(existing.get("count", 0)) + 1
    if ip and ip not in existing.get("ips", []):
        ips = existing.setdefault("ips", [])
        ips.append(ip)
        # Trim trailing entries — keep the OLDEST plus most-recent
        # (drop the middle) so the file always shows first-seen-IP and
        # latest-seen-IP without unbounded growth. Simpler: trim to the
        # first _MAX_IPS_PER_KEY.
        del ips[_MAX_IPS_PER_KEY:]
    if payload.get("miner_id") is not None:
        miner_id = str(payload["miner_id"])
        examples = existing.setdefault("miner_id_examples", [])
        if miner_id not in examples:
            examples.append(miner_id)
            del examples[_MAX_IPS_PER_KEY:]


def _append_event_log(events_path: Path, event_type: str,
                      payload: Dict[str, Any], now: str) -> None:
    """Append-only JSONL audit trail. One JSON object per line.

    Never deduped. The rolling latest_findings.json is the dedup'd
    view; this file is the receipt that every observation was captured.
    """
    events_path.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "ts": now,
        "event_type": event_type,
        "model_name": payload.get("model_name", "") or "",
        "firmware_version": payload.get("firmware_version", "") or "",
        "ip": payload.get("ip", "") or "",
        "miner_id": payload.get("miner_id"),
        "source": payload.get("source", "scanner_discovery"),
    }
    with events_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, sort_keys=True, default=str))
        f.write("\n")


def record_discovery(event_type: str, payload: Optional[Dict[str, Any]] = None) -> bool:
    """Persist one discovery event.

    Best-effort: any I/O failure is swallowed with a WARNING log so the
    scanner's hot path is never disrupted by a broken sink.

    Args:
        event_type: 'unknown_model' | 'new_firmware' | (future).
        payload: dict with keys model_name (str), firmware_version (str,
                 optional), ip (str, optional), miner_id (str/int,
                 optional), source (str, default 'scanner_discovery').

    Returns:
        True if the rolling snapshot was updated, False on any I/O
        failure. Tests use this; production callers ignore the return.
    """
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        logger.warning(
            "discovery_sink: payload must be a dict (got %r); skipping",
            type(payload).__name__,
        )
        return False
    if event_type not in ("unknown_model", "new_firmware"):
        # Tolerate unknown types (forward-compat) but log once at INFO so
        # the operator sees a future caller emitting something new.
        logger.info(
            "discovery_sink: recording unfamiliar event_type=%r (will be "
            "stored under that name in latest_findings.json)",
            event_type,
        )

    sink_dir = resolve_sink_dir()
    latest_path = sink_dir / "latest_findings.json"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    events_path = sink_dir / f"events-{today}.jsonl"

    now = _utc_now_iso()
    try:
        sink_dir.mkdir(parents=True, exist_ok=True)
        snapshot = _load_snapshot(latest_path)
        snapshot["updated_at"] = now
        _merge_event(snapshot, event_type, payload, now)
        _atomic_write_json(latest_path, snapshot)
        _append_event_log(events_path, event_type, payload, now)
        return True
    except OSError as exc:
        logger.warning(
            "discovery_sink: failed to persist %s discovery to %s: %s",
            event_type, sink_dir, exc,
        )
        return False


def read_latest() -> Dict[str, Any]:
    """Return the current rolling snapshot dict (used by readers + tests)."""
    latest_path = resolve_sink_dir() / "latest_findings.json"
    return _load_snapshot(latest_path)
