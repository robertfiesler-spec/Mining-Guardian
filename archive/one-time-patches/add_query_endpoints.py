#!/usr/bin/env python3
"""
Surgical inserter: adds the /query/* endpoint block to api/dashboard_api.py.

Inserts a new block IMMEDIATELY BEFORE the `if __name__ == "__main__":` line.
Idempotent: if the marker '# ── QUERY ENDPOINTS (Bobby/OpenClaw skill-facing) ──' is
already present, does nothing and exits 0.

Follows the CLAUDE.md rules:
  - Uses existing db_conn() context manager pattern
  - Read-only SQL, parameterized
  - Compact JSON shapes for LLM consumption
  - # TEMP comments where VPS-specific assumptions matter
  - Scope discipline: does NOT touch existing endpoints
"""
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "api" / "dashboard_api.py"
MARKER = "# ── QUERY ENDPOINTS (Bobby/OpenClaw skill-facing) ──"
INSERT_BEFORE = 'if __name__ == "__main__":'

NEW_BLOCK = '''
# ── QUERY ENDPOINTS (Bobby/OpenClaw skill-facing) ──
#
# These endpoints are consumed by the guardian-db OpenClaw skill at
# /data/.openclaw/skills/guardian-db/ inside the OpenClaw container.
# The skill makes HTTP calls to these endpoints to answer fleet questions
# in Slack DMs.
#
# TEMP: In the current VPS dev environment, the OpenClaw container reaches
#       these endpoints via the Docker bridge IP of the VPS host
#       (typically 172.18.0.1:8585). On May 1 2026 when Mining Guardian and
#       OpenClaw are both containers in the same docker-compose stack on a
#       Mac mini, this becomes http://mining-guardian:8585/query/... via
#       service-name DNS — a one-line config change in the skill.
#
# Design rules for this block:
#   - Read-only only. No writes under any circumstances.
#   - Compact JSON shapes. Fields named in plain English. No nested wrappers.
#   - Small-integer defaults for `hours` and `limit` so the LLM doesn't
#     accidentally pull the whole database.
#   - Errors return {"error": "..."} with appropriate HTTP status codes.
#   - Every endpoint uses db_conn() context manager — guaranteed close.

def _latest_scan_id(conn):
    """Return the id of the most recent scan, or None if no scans exist."""
    row = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    return row["id"] if row else None


@app.get("/query/fleet_summary")
def query_fleet_summary():
    """
    High-level fleet state from the latest scan.

    Returns counts of online/offline/flagged miners, fleet total hashrate,
    and the scan timestamp so the LLM can say things like
    "as of 10 minutes ago, 55 miners are online and 3 are flagged".
    """
    with db_conn() as conn:
        scan = conn.execute(
            "SELECT id, scanned_at, total_miners, online, offline, issues "
            "FROM scans ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not scan:
            return {"error": "no scans in database yet"}

        agg = conn.execute(
            "SELECT "
            "  COALESCE(SUM(hashrate), 0) AS total_hashrate, "
            "  COALESCE(SUM(max_hashrate), 0) AS total_max_hashrate, "
            "  COALESCE(AVG(hashrate_pct), 0) AS avg_pct, "
            "  COUNT(*) AS miner_count "
            "FROM miner_readings WHERE scan_id = ?",
            (scan["id"],),
        ).fetchone()

        flagged = conn.execute(
            "SELECT COUNT(*) AS n FROM miner_readings "
            "WHERE scan_id = ? AND issue IS NOT NULL AND issue != ''",
            (scan["id"],),
        ).fetchone()["n"]

        return {
            "scan_id": scan["id"],
            "scan_time": scan["scanned_at"],
            "total_miners": scan["total_miners"],
            "online": scan["online"],
            "offline": scan["offline"],
            "flagged": flagged,
            "total_hashrate_ths": round(agg["total_hashrate"], 1) if agg["total_hashrate"] else 0,
            "total_max_hashrate_ths": round(agg["total_max_hashrate"], 1) if agg["total_max_hashrate"] else 0,
            "avg_hashrate_pct": round(agg["avg_pct"], 1) if agg["avg_pct"] else 0,
        }


@app.get("/query/flagged_miners")
def query_flagged_miners():
    """
    Every miner currently flagged (issue != null) in the most recent scan.
    Returns one row per miner with the full context the LLM needs to
    explain what's wrong to the operator.
    """
    with db_conn() as conn:
        scan_id = _latest_scan_id(conn)
        if scan_id is None:
            return {"error": "no scans in database yet", "miners": []}

        rows = conn.execute(
            "SELECT ip, model, status, hashrate, max_hashrate, hashrate_pct, "
            "       temp_chip, temp_board, issue, action, current_profile, "
            "       firmware_version, map_location, uptime "
            "FROM miner_readings "
            "WHERE scan_id = ? AND issue IS NOT NULL AND issue != '' "
            "ORDER BY "
            "  CASE WHEN status = 'OFFLINE' THEN 0 "
            "       WHEN temp_chip >= 84 THEN 1 "
            "       WHEN hashrate_pct < 80 THEN 2 "
            "       ELSE 3 END, "
            "  ip",
            (scan_id,),
        ).fetchall()

        return {
            "scan_id": scan_id,
            "count": len(rows),
            "miners": [dict(r) for r in rows],
        }


@app.get("/query/miner_history/{ip}")
def query_miner_history(ip: str, hours: int = 24):
    """
    Time-series of readings for one miner over the last N hours.
    Used to answer "what has miner .36 been doing today?"

    hours default 24, max 168 (1 week) to protect the DB from huge queries.
    """
    if hours < 1 or hours > 168:
        return {"error": "hours must be between 1 and 168"}

    with db_conn() as conn:
        rows = conn.execute(
            "SELECT scan_id, scanned_at, status, hashrate, hashrate_pct, "
            "       temp_chip, temp_board, issue, action, current_profile "
            "FROM miner_readings "
            "WHERE ip = ? "
            "  AND scanned_at >= datetime('now', ? || ' hours') "
            "ORDER BY scanned_at DESC "
            "LIMIT 500",
            (ip, f"-{hours}"),
        ).fetchall()

        if not rows:
            return {
                "ip": ip,
                "hours": hours,
                "count": 0,
                "readings": [],
                "note": f"no readings for {ip} in the last {hours} hours",
            }

        latest = rows[0]
        oldest = rows[-1]
        return {
            "ip": ip,
            "model": None,  # joined below if possible
            "hours": hours,
            "count": len(rows),
            "latest": dict(latest),
            "oldest_in_window": dict(oldest),
            "readings": [dict(r) for r in rows],
        }


@app.get("/query/recent_actions")
def query_recent_actions(hours: int = 4, limit: int = 50):
    """
    Recent entries from action_audit_log — every approve/deny/auto-execute
    decision the bot has made, with who approved it and any notes.

    Default window 4 hours, max 168 (1 week). Default limit 50, max 500.
    """
    if hours < 1 or hours > 168:
        return {"error": "hours must be between 1 and 168"}
    if limit < 1 or limit > 500:
        return {"error": "limit must be between 1 and 500"}

    with db_conn() as conn:
        rows = conn.execute(
            "SELECT timestamp, miner_id, ip, model, problem, action_taken, "
            "       decision, approved_by, notes "
            "FROM action_audit_log "
            "WHERE timestamp >= datetime('now', ? || ' hours') "
            "ORDER BY timestamp DESC "
            "LIMIT ?",
            (f"-{hours}", limit),
        ).fetchall()

        return {
            "hours": hours,
            "count": len(rows),
            "actions": [dict(r) for r in rows],
        }


@app.get("/query/miner_outcomes/{ip}")
def query_miner_outcomes(ip: str, limit: int = 20):
    """
    Recent restart outcomes for a single miner from miner_restarts table.
    Shows hashrate_before, hashrate_after, and whether the outcome was
    SUCCESS or FAILURE. Used to answer "is the bot's fixing actually
    working on this miner, or is it stuck in a failure loop?"
    """
    if limit < 1 or limit > 200:
        return {"error": "limit must be between 1 and 200"}

    with db_conn() as conn:
        rows = conn.execute(
            "SELECT restarted_at, restart_type, outcome, "
            "       hashrate_before, hashrate_after, recovery_time_scans "
            "FROM miner_restarts "
            "WHERE ip = ? "
            "ORDER BY restarted_at DESC "
            "LIMIT ?",
            (ip, limit),
        ).fetchall()

        if not rows:
            return {"ip": ip, "count": 0, "outcomes": [],
                    "note": f"no restart history for {ip}"}

        success = sum(1 for r in rows if r["outcome"] == "SUCCESS")
        failure = sum(1 for r in rows if r["outcome"] == "FAILURE")

        return {
            "ip": ip,
            "count": len(rows),
            "success_count": success,
            "failure_count": failure,
            "outcomes": [dict(r) for r in rows],
        }


@app.get("/query/board_health/{ip}")
def query_board_health(ip: str):
    """
    Per-board health for a miner from the most recent chain_readings entry.
    Shows hashrate, voltage, frequency, hw_errors, and temperature per board.
    Used to answer "which boards are dying on miner X?"
    """
    with db_conn() as conn:
        scan_id = _latest_scan_id(conn)
        if scan_id is None:
            return {"error": "no scans in database yet"}

        rows = conn.execute(
            "SELECT board_index, rate_mhs, voltage, freq_mhz, consumption_w, "
            "       hw_errors, temp_board, temp_chip "
            "FROM chain_readings "
            "WHERE ip = ? AND scan_id = ? "
            "ORDER BY board_index",
            (ip, scan_id),
        ).fetchall()

        if not rows:
            return {"ip": ip, "count": 0, "boards": [],
                    "note": f"no board readings for {ip} in latest scan"}

        return {
            "ip": ip,
            "scan_id": scan_id,
            "count": len(rows),
            "boards": [dict(r) for r in rows],
        }


@app.get("/query/worst_performers")
def query_worst_performers(limit: int = 5):
    """
    Bottom N miners by hashrate_pct in the most recent scan.
    Excludes OFFLINE miners (they're 0% by definition and not interesting
    for a "who's underperforming" question).
    """
    if limit < 1 or limit > 50:
        return {"error": "limit must be between 1 and 50"}

    with db_conn() as conn:
        scan_id = _latest_scan_id(conn)
        if scan_id is None:
            return {"error": "no scans in database yet", "miners": []}

        rows = conn.execute(
            "SELECT ip, model, status, hashrate, max_hashrate, hashrate_pct, "
            "       temp_chip, issue, map_location "
            "FROM miner_readings "
            "WHERE scan_id = ? AND status != 'OFFLINE' "
            "ORDER BY hashrate_pct ASC "
            "LIMIT ?",
            (scan_id, limit),
        ).fetchall()

        return {
            "scan_id": scan_id,
            "count": len(rows),
            "miners": [dict(r) for r in rows],
        }


@app.get("/query/known_dead_boards")
def query_known_dead_boards():
    """
    Miners in the known_dead_boards table — the ones the bot has given up on
    and ticketed. These are suppressed from flag reports, so the LLM needs
    a dedicated query to surface them when asked.
    """
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT miner_id, ip, model, board_indices, first_seen, "
            "       restart_attempted, restart_result, ticket_created, notes "
            "FROM known_dead_boards "
            "WHERE resolved_at IS NULL "
            "ORDER BY first_seen DESC"
        ).fetchall()

        return {
            "count": len(rows),
            "miners": [dict(r) for r in rows],
        }


@app.get("/query/hvac_latest")
def query_hvac_latest():
    """
    Most recent HVAC reading from the BAS.
    OPERATOR NOTE (per CLAUDE.md memory rules): Low delta-T is intentional
    and expected. Do NOT flag low delta-T as a problem in LLM responses.
    """
    with db_conn() as conn:
        row = conn.execute(
            "SELECT recorded_at, supply_temp_f, return_temp_f, delta_t_f, "
            "       diff_pressure, spray_pump_on, cwp1_vfd_pct, cwp2_vfd_pct, "
            "       ct1_vfd_pct, ct2_vfd_pct, leak_alarm, ct1_fault, ct2_fault, "
            "       pump_fault "
            "FROM hvac_readings "
            "ORDER BY recorded_at DESC LIMIT 1"
        ).fetchone()

        if not row:
            return {"error": "no hvac readings yet"}

        d = dict(row)
        d["operator_note"] = (
            "Low delta-T is intentional and expected for this facility. "
            "Do not flag low delta-T as a problem."
        )
        return d


# ── END QUERY ENDPOINTS ──


'''


def main():
    text = TARGET.read_text()

    if MARKER in text:
        print(f"Marker already present in {TARGET}; nothing to do.")
        return 0

    if INSERT_BEFORE not in text:
        print(f"ERROR: insertion anchor '{INSERT_BEFORE}' not found in {TARGET}")
        return 1

    # Insert immediately before the anchor line
    new_text = text.replace(INSERT_BEFORE, NEW_BLOCK.lstrip("\n") + "\n\n" + INSERT_BEFORE, 1)

    # Write atomically: write to tmp, then rename
    tmp = TARGET.with_suffix(TARGET.suffix + ".tmp")
    tmp.write_text(new_text)
    tmp.replace(TARGET)

    original_lines = text.count("\n")
    new_lines = new_text.count("\n")
    print(f"Inserted {new_lines - original_lines} lines into {TARGET}")
    print(f"Original: {original_lines} lines. New: {new_lines} lines.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
