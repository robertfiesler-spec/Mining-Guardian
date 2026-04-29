"""Shared Grafana authentication helper for all maintenance scripts.

Replaces the previously hard-coded `admin:002300rf` literal that was embedded
in `scripts/check_grafana_board.py`, `scripts/check_grafana_board2.py`,
`scripts/update_grafana_ai.py`, and `scripts/update_grafana_pool.py`. The
literal was rotated on the live VPS on 2026-04-29; baking it back into source
would (a) leak the new password into the repo and (b) break again the next
time it rotates.

All credentials must come from the environment:

    GRAFANA_URL        default: http://localhost:3000
    GRAFANA_USER       default: admin
    GRAFANA_PASSWORD   no default - the script aborts if it is unset

The helper exposes both forms callers need:

    grafana_url()                 -> str  (e.g. "http://localhost:3000")
    grafana_basic_auth_header()   -> str  (e.g. "Basic YWRtaW46czNjcmV0")
    grafana_basic_auth_tuple()    -> (str, str)  for `requests.get(..., auth=...)`

Each call validates that GRAFANA_PASSWORD is set; the abort message tells the
operator which env var to set instead of failing with an opaque 401.
"""
from __future__ import annotations

import base64
import os
import sys


def _require_password() -> str:
    pw = os.environ.get("GRAFANA_PASSWORD")
    if not pw:
        sys.stderr.write(
            "GRAFANA_PASSWORD environment variable is not set.\n"
            "Export it before running this script, e.g.:\n"
            "  export GRAFANA_PASSWORD='<the current Grafana admin password>'\n"
            "(GRAFANA_USER and GRAFANA_URL also honour env overrides; defaults are\n"
            "'admin' and 'http://localhost:3000'.)\n"
        )
        sys.exit(2)
    return pw


def grafana_url() -> str:
    return os.environ.get("GRAFANA_URL", "http://localhost:3000").rstrip("/")


def grafana_user() -> str:
    return os.environ.get("GRAFANA_USER", "admin")


def grafana_basic_auth_header() -> str:
    creds = f"{grafana_user()}:{_require_password()}".encode("utf-8")
    return "Basic " + base64.b64encode(creds).decode("ascii")


def grafana_basic_auth_tuple() -> tuple[str, str]:
    return (grafana_user(), _require_password())
