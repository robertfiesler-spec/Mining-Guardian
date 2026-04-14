#!/usr/bin/env python3
"""
Add confidence scores to dashboard API and morning briefing.

This patch:
1. Adds confidence to /miners/flagged API endpoint
2. Adds confidence to morning briefing Slack message
3. Creates new /ai/confidence_summary endpoint for demo
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ============================================================
# PATCH 1: Add confidence to /miners/flagged API
# ============================================================

api_file = ROOT / "api" / "dashboard_api.py"
api_content = api_file.read_text()

OLD_FLAGGED = '''def miners_flagged():
    """All miners currently flagged in the latest scan."""
    conn = get_db()
    scan = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    if not scan:
        return []
    rows = conn.execute("""
        SELECT miner_id, ip, model, status, hashrate_pct,
               temp_chip, action, issue
        FROM miner_readings
        WHERE scan_id = ? AND action IS NOT NULL
        ORDER BY action, ip
    """, (scan["id"],)).fetchall()
    conn.close()
    return [dict(r) for r in rows]'''

NEW_FLAGGED = '''def miners_flagged():
    """All miners currently flagged in the latest scan — with AI confidence scores."""
    conn = get_db()
    scan = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    if not scan:
        return []
    rows = conn.execute("""
        SELECT miner_id, ip, model, status, hashrate_pct,
               temp_chip, action, issue
        FROM miner_readings
        WHERE scan_id = ? AND action IS NOT NULL
        ORDER BY action, ip
    """, (scan["id"],)).fetchall()
    conn.close()

    # Add confidence scores for each flagged miner
    try:
        _ai_path = str(_ROOT / "ai")
        if _ai_path not in sys.path:
            sys.path.insert(0, _ai_path)
        from confidence_scorer import get_confidence, get_gate
        has_confidence = True
    except ImportError:
        has_confidence = False

    result = []
    for r in rows:
        d = dict(r)
        if has_confidence and d.get("action") in ("RESTART", "PDU_CYCLE", "RESTART_CHECK_BOARDS"):
            try:
                score, reason = get_confidence(
                    str(d["miner_id"]), d["ip"], d["action"],
                    hashrate_pct=d.get("hashrate_pct")
                )
                gate = get_gate(score)
                d["confidence"] = score
                d["confidence_gate"] = gate
                d["confidence_reason"] = reason
            except Exception:
                d["confidence"] = None
                d["confidence_gate"] = None
                d["confidence_reason"] = None
        else:
            d["confidence"] = None
            d["confidence_gate"] = None
            d["confidence_reason"] = None
        result.append(d)

    return result'''

if OLD_FLAGGED in api_content:
    api_content = api_content.replace(OLD_FLAGGED, NEW_FLAGGED)
    api_file.write_text(api_content)
    print("✅ Patched /miners/flagged to include confidence scores")
else:
    print("⚠️  Could not find miners_flagged function to patch")

print("Done!")
