"""
console/system_state.py — D-19 read-only system state panel

Best-effort collection of:
  - Postgres up/down
  - Ollama up/down
  - Tailscale up/down (and node name when available)
  - Grafana up/down
  - Last successful scan timestamp
  - Miner reachability summary (count online / total)

Every probe is wrapped in try/except and bounded by a short socket-level
timeout, because the console renders this panel synchronously and one slow
probe must not hang the page. A failed probe returns
`{"status": "unknown", "detail": <reason>}` rather than raising.
"""

from __future__ import annotations

import logging
import os
import socket
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

from core.db_targets import operational_target

logger = logging.getLogger("console.system_state")

# Bounded probe timeout. Tight enough that a single page render stays
# under ~1.5 s even if every probe fails, generous enough to ride past a
# transient blip on a healthy localhost service.
_PROBE_TIMEOUT_SEC = 0.6


def _tcp_probe(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=_PROBE_TIMEOUT_SEC):
            return True
    except (OSError, socket.timeout):
        return False


def _http_probe(url: str) -> Optional[int]:
    """Return HTTP status code or None on failure."""
    try:
        req = Request(url, headers={"User-Agent": "mg-console/1.0"})
        with urlopen(req, timeout=_PROBE_TIMEOUT_SEC) as resp:  # noqa: S310 (localhost)
            return resp.status
    except (URLError, socket.timeout, OSError):
        return None


# ── Individual probes ────────────────────────────────────────────────────────

def probe_postgres() -> Dict[str, Any]:
    # W14a (2026-05-12): was reading host/port directly via os.environ.get().
    # Delegate to core.db_targets.operational_target() so this probe targets
    # the same instance the rest of the operational code talks to. Probe
    # remains a TCP-only check — we deliberately do not open a real DB
    # connection here since the console renders this panel synchronously
    # and a slow Postgres response must not hang the page.
    target = operational_target()
    host = target.host
    port = target.port
    if _tcp_probe(host, port):
        return {"status": "up", "detail": f"{host}:{port}"}
    return {"status": "down", "detail": f"{host}:{port} unreachable"}


def probe_ollama() -> Dict[str, Any]:
    base = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    if not base.startswith("http"):
        base = f"http://{base}"
    code = _http_probe(f"{base}/api/tags")
    if code == 200:
        return {"status": "up", "detail": base}
    if code is None:
        return {"status": "down", "detail": f"{base} unreachable"}
    return {"status": "degraded", "detail": f"{base} HTTP {code}"}


def probe_grafana() -> Dict[str, Any]:
    base = os.environ.get("GRAFANA_URL", "http://localhost:3000")
    code = _http_probe(f"{base}/api/health")
    if code == 200:
        return {"status": "up", "detail": base}
    if code is None:
        return {"status": "down", "detail": f"{base} unreachable"}
    return {"status": "degraded", "detail": f"{base} HTTP {code}"}


def probe_tailscale() -> Dict[str, Any]:
    """Tailscale is operator-side only (D-19). Probe is best-effort: we look
    for the local tailscaled control socket and the published HTTP endpoint.
    """
    # Default Tailscale on macOS exposes its API on localhost via a Unix
    # socket (/var/run/tailscaled.socket) — we don't try to talk that
    # protocol from Python here. A simple TCP probe to the well-known
    # local web UI port is best-effort and may report 'down' even when
    # tailscaled is healthy. The detail string makes that explicit.
    detail = "best-effort probe; absence does not mean Tailscale is down"
    if _tcp_probe("localhost", 41112):
        return {"status": "up", "detail": "localhost:41112 reachable"}
    return {"status": "unknown", "detail": detail}


def probe_last_scan() -> Dict[str, Any]:
    """Last scan timestamp from the operational DB. Falls back gracefully."""
    try:
        import psycopg2  # type: ignore
        from api.system_settings import _pg_dsn
        conn = psycopg2.connect(_pg_dsn())
        try:
            cur = conn.cursor()
            cur.execute("SELECT MAX(scanned_at) FROM scans")
            row = cur.fetchone()
            if row and row[0]:
                return {"status": "up", "detail": row[0].isoformat()}
            return {"status": "unknown", "detail": "no scans yet"}
        finally:
            conn.close()
    except Exception as exc:
        logger.debug("probe_last_scan: %s", exc)
        return {"status": "unknown", "detail": str(exc)[:120]}


def probe_miner_reachability() -> Dict[str, Any]:
    """Online / total summary from the most recent scan."""
    try:
        import psycopg2  # type: ignore
        from api.system_settings import _pg_dsn
        conn = psycopg2.connect(_pg_dsn())
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    SUM(CASE WHEN status = 'ONLINE' THEN 1 ELSE 0 END) AS online,
                    COUNT(*) AS total
                FROM miner_readings
                WHERE id IN (
                    SELECT MAX(id) FROM miner_readings GROUP BY miner_id
                )
                """
            )
            row = cur.fetchone()
            online = int(row[0] or 0) if row else 0
            total = int(row[1] or 0) if row else 0
            if total == 0:
                return {"status": "unknown", "detail": "no miner_readings yet"}
            return {"status": "up", "detail": f"{online}/{total} online"}
        finally:
            conn.close()
    except Exception as exc:
        logger.debug("probe_miner_reachability: %s", exc)
        return {"status": "unknown", "detail": str(exc)[:120]}


def collect_system_state() -> Dict[str, Dict[str, Any]]:
    """Run every probe synchronously. Best-effort, never raises."""
    return {
        "postgres":         probe_postgres(),
        "ollama":           probe_ollama(),
        "grafana":          probe_grafana(),
        "tailscale":        probe_tailscale(),
        "last_scan":        probe_last_scan(),
        "miner_reach":      probe_miner_reachability(),
    }
