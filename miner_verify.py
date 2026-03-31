"""
miner_verify.py — Direct miner verification for AMS false-offline detection
============================================================================
When AMS reports a miner as offline, this module attempts a direct connection
to the miner's IP to verify whether it's actually unreachable.

Two verification methods (tried in order):
  1. CGMiner TCP API on port 4028 — send 'summary' command, no auth needed.
     Works for BiXBiT firmware and standard Antminer/WhatsMiner.
  2. HTTP check on port 80 — GET /dashboard, check for 200 response.
     Fallback for miners where port 4028 isn't available.

If either succeeds, the miner is actually online — AMS is reporting a false
offline (typically caused by WebSocket sync lag after a restart or brief
network hiccup).
"""

import json
import socket
import logging
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger("mining_guardian")

# How long to wait for direct connection attempts
TCP_TIMEOUT  = 5   # seconds
HTTP_TIMEOUT = 5   # seconds

# Port 4028 CGMiner TCP API — no auth, read-only
CGMINER_PORT = 4028
# BiXBiT firmware web dashboard
HTTP_PORT    = 80


def verify_miner_online(ip: str) -> dict:
    """
    Attempt direct connection to a miner to verify it's actually offline.

    Returns:
      {
        "actually_online": bool,
        "method": "tcp_4028" | "http_80" | None,
        "hashrate_ths": float | None,   # if available from TCP
        "status_detail": str,           # human-readable result
      }
    """
    # ── Method 1: CGMiner TCP port 4028 ──────────────────────────────────
    result = _try_tcp_4028(ip)
    if result["actually_online"]:
        return result

    # ── Method 2: HTTP port 80 ────────────────────────────────────────────
    result = _try_http_80(ip)
    return result


def _try_tcp_4028(ip: str) -> dict:
    """Send CGMiner 'summary' command via TCP and check for a valid response."""
    cmd = json.dumps({"command": "summary"}).encode() + b"\n"
    try:
        with socket.create_connection((ip, CGMINER_PORT), timeout=TCP_TIMEOUT) as sock:
            sock.sendall(cmd)
            data = b""
            sock.settimeout(TCP_TIMEOUT)
            while True:
                try:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if len(data) > 100:  # got a real response, stop reading
                        break
                except socket.timeout:
                    break

        if not data:
            return _not_online("tcp_4028", "Connected but no data returned")

        # Try to parse the response
        try:
            parsed   = json.loads(data.decode("utf-8", errors="replace"))
            summary  = parsed.get("SUMMARY", [{}])[0]
            mhs_av   = summary.get("MHS av", 0) or 0
            # CGMiner returns hashrate in MH/s — convert to TH/s
            # (MH/s ÷ 1,000,000 = TH/s)
            ths      = round(mhs_av / 1_000_000, 2)
            status   = parsed.get("STATUS", [{}])[0].get("STATUS", "?")
            return {
                "actually_online": True,
                "method":          "tcp_4028",
                "hashrate_ths":    ths if ths > 0 else None,
                "status_detail":   (
                    f"TCP:4028 responded — CGMiner status={status}, "
                    f"hashrate={ths:.1f} TH/s"
                ),
            }
        except Exception:
            # Got data but couldn't parse — still means port is open and alive
            return {
                "actually_online": True,
                "method":          "tcp_4028",
                "hashrate_ths":    None,
                "status_detail":   "TCP:4028 responded (non-JSON response — miner alive)",
            }

    except (socket.timeout, ConnectionRefusedError, OSError):
        return _not_online("tcp_4028", f"TCP:4028 unreachable on {ip}")


def _try_http_80(ip: str) -> dict:
    """HTTP GET to the miner's web interface."""
    url = f"http://{ip}/"
    try:
        resp = requests.get(url, timeout=HTTP_TIMEOUT, allow_redirects=True)
        if resp.status_code < 500:
            return {
                "actually_online": True,
                "method":          "http_80",
                "hashrate_ths":    None,
                "status_detail":   (
                    f"HTTP:80 responded with {resp.status_code} — miner web UI alive"
                ),
            }
        return _not_online("http_80", f"HTTP:80 returned {resp.status_code}")
    except Exception as e:
        return _not_online("http_80", f"HTTP:80 unreachable: {e}")


def _not_online(method: str, reason: str) -> dict:
    return {
        "actually_online": False,
        "method":          method,
        "hashrate_ths":    None,
        "status_detail":   reason,
    }
