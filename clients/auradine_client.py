"""
auradine_client.py — Teraflux AH3880 Direct Device API Client
==============================================================
⚠️  SECONDARY PATH ONLY — AMS IS PRIMARY ⚠️

Architecture rule for Mining Guardian:
  ALL miner commands (reboot, standby, profile changes, PDU control, etc.)
  go through AMS first. AMS provides the audit log, handles auth, and the
  Mac Mini only needs LAN access to AMS — not direct access to each miner.

This client is kept for:
  1. Reference — documents what the AH3880 can do natively
  2. Future fallback — if AMS doesn't expose a specific AH3880 capability
  3. On-site direct access if needed (requires Mac Mini on miner LAN)

Do NOT use this client in normal fleet scan / remediation flows.
Always go through AMSClient first.

------------------------------------------------------------------
Auradine Teraflux miners expose two API surfaces:

  1. HTTP(S)/REST  -> port 8080 (HTTP) or port 8443 (HTTPS)
     - Requires JWT token auth (POST /token with admin/admin)
     - Full read + write access

  2. JSON/TCP (CGMiner-compatible) -> port 4028
     - No authentication required
     - Read-only (summary, pools, devs, stats, etc.)

Default credentials: admin / admin
Default ports:       HTTP=8080, HTTPS=8443, TCP=4028

IMPORTANT OPERATIONAL NOTE:
  Always call standby() before cutting PDU power to an AH3880.
  Disconnecting power or coolant without a graceful standby can
  damage the cooling plate and void warranty.
  (AMS handles this correctly when commands go through it.)
"""

import json
import socket
import logging
import time
from typing import Any, Dict, Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("mining_guardian")
