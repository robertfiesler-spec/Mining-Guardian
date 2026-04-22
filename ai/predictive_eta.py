"""
Predictive ETA Module for Mining Guardian
April 22, 2026

Estimates time-to-failure for miners based on:
1. Current predictor score (0-100)
2. Rate of score increase over time
3. Historical time-to-failure patterns
4. Restart frequency trends
"""

import os
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)


def get_db():
    """Get database connection."""
    db_path = os.getenv("GUARDIAN_DB", "/root/Mining-Gaurdian/guardian.db")
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def calculate_miner_eta(miner_id: str, current_score: float) -> Dict[str, Any]:
    """
    Calculate estimated time to failure for a single miner.
    
    Uses:
    - Current predictor score
    - Score trend over last 7 days
    - Restart frequency acceleration
    - Historical patterns from similar miners
    
    Returns:
        eta_hours: Estimated hours until failure (None if healthy)
        eta_label: Human-readable ETA ("~2 days", "< 24 hours", etc.)
        confidence: Low/Medium/High based on data quality
        risk_level: Critical/High/Medium/Low/Healthy
        factors: List of contributing factors
    """
    conn = get_db()
    try:
        # Get restart history for trend analysis
        restarts = conn.execute("""
            SELECT restarted_at, outcome
            FROM miner_restarts
            WHERE miner_id = ?
            ORDER BY restarted_at DESC
            LIMIT 30
        """, (miner_id,)).fetchall()
        
        # Get recent predictor analyses if available
        analyses = conn.execute("""
            SELECT analyzed_at, response
            FROM llm_analysis
            WHERE miner_id = ?
            ORDER BY analyzed_at DESC
            LIMIT 10
        """, (miner_id,)).fetchall()
        
    finally:
        conn.close()
    
    # Calculate restart acceleration
    now = datetime.now()
    restarts_24h = 0
    restarts_7d = 0
    restarts_30d = len(restarts)
    failures_30d = 0
    
    for r in restarts:
        try:
            ts = datetime.fromisoformat(r["restarted_at"].replace("Z", "").split("+")[0])
            age = now - ts
            if age <= timedelta(hours=24):
                restarts_24h += 1
            if age <= timedelta(days=7):
                restarts_7d += 1
            if r["outcome"] and r["outcome"].upper() in ("FAILURE", "FAILED", "NO_RECOVERY"):
                failures_30d += 1
        except:
            continue
    
    # Calculate factors and ETA
    factors = []
    eta_hours = None
    confidence = "Low"
    
    # Factor 1: Current predictor score
    if current_score >= 80:
        factors.append(f"Critical predictor score ({current_score:.0f})")
        eta_hours = 12  # Base estimate
        confidence = "High"
    elif current_score >= 60:
        factors.append(f"High predictor score ({current_score:.0f})")
        eta_hours = 48
        confidence = "Medium"
    elif current_score >= 40:
        factors.append(f"Elevated predictor score ({current_score:.0f})")
        eta_hours = 168  # ~1 week
        confidence = "Low"
    
    # Factor 2: Restart acceleration
    if restarts_24h >= 3:
        factors.append(f"{restarts_24h} restarts in 24h (acute instability)")
        eta_hours = min(eta_hours or 999, 6)
        confidence = "High"
    elif restarts_24h >= 2:
        factors.append(f"{restarts_24h} restarts in 24h")
        eta_hours = min(eta_hours or 999, 24)
    
    if restarts_7d >= 5:
        factors.append(f"{restarts_7d} restarts in 7 days (chronic)")
        eta_hours = min(eta_hours or 999, 48)
        confidence = "Medium" if confidence == "Low" else confidence
    
    # Factor 3: Failure rate
    if failures_30d >= 2:
        factors.append(f"{failures_30d} failures in 30 days")
        eta_hours = min(eta_hours or 999, 24)
        confidence = "High"
    
    # Factor 4: Accelerating restart rate
    # Compare last 3 days vs previous 4 days
    restarts_3d = sum(1 for r in restarts if _age_hours(r["restarted_at"]) <= 72)
    restarts_prev_4d = restarts_7d - restarts_3d
    if restarts_3d > restarts_prev_4d * 1.5 and restarts_3d >= 2:
        factors.append(f"Accelerating restart rate ({restarts_3d} in 3d vs {restarts_prev_4d} prev 4d)")
        eta_hours = min(eta_hours or 999, eta_hours * 0.5 if eta_hours else 36)
    
    # Determine risk level
    if eta_hours is None:
        risk_level = "Healthy"
        eta_label = "No issues detected"
    elif eta_hours <= 12:
        risk_level = "Critical"
        eta_label = "< 12 hours"
    elif eta_hours <= 24:
        risk_level = "Critical"
        eta_label = "< 24 hours"
    elif eta_hours <= 48:
        risk_level = "High"
        eta_label = "1-2 days"
    elif eta_hours <= 168:
        risk_level = "Medium"
        eta_label = "~1 week"
    else:
        risk_level = "Low"
        eta_label = "> 1 week"
    
    return {
        "miner_id": miner_id,
        "current_score": round(current_score, 1),
        "eta_hours": round(eta_hours, 1) if eta_hours else None,
        "eta_label": eta_label,
        "confidence": confidence,
        "risk_level": risk_level,
        "factors": factors,
        "restarts_24h": restarts_24h,
        "restarts_7d": restarts_7d,
        "failures_30d": failures_30d
    }


def _age_hours(timestamp_str: str) -> float:
    """Calculate age in hours from timestamp string."""
    try:
        ts = datetime.fromisoformat(timestamp_str.replace("Z", "").split("+")[0])
        return (datetime.now() - ts).total_seconds() / 3600
    except:
        return 9999


def get_fleet_eta_ranking() -> List[Dict[str, Any]]:
    """
    Get all miners ranked by predicted time-to-failure.
    
    Returns list of miners with ETA, sorted by urgency (critical first).
    """
    conn = get_db()
    try:
        # Get latest predictor scores for all miners
        # We'll use restart count as a proxy for score since we may not have stored scores
        rows = conn.execute("""
            WITH restart_counts AS (
                SELECT 
                    miner_id,
                    COUNT(*) as total_restarts,
                    SUM(CASE WHEN restarted_at > datetime('now', '-1 day') THEN 1 ELSE 0 END) as restarts_24h,
                    SUM(CASE WHEN restarted_at > datetime('now', '-7 days') THEN 1 ELSE 0 END) as restarts_7d,
                    SUM(CASE WHEN outcome IN ('FAILURE', 'FAILED', 'NO_RECOVERY') THEN 1 ELSE 0 END) as failures
                FROM miner_restarts
                GROUP BY miner_id
            ),
            latest_readings AS (
                SELECT DISTINCT miner_id, ip
                FROM miner_readings
                WHERE scanned_at = (SELECT MAX(scanned_at) FROM miner_readings)
            )
            SELECT 
                lr.miner_id,
                lr.ip,
                COALESCE(rc.total_restarts, 0) as total_restarts,
                COALESCE(rc.restarts_24h, 0) as restarts_24h,
                COALESCE(rc.restarts_7d, 0) as restarts_7d,
                COALESCE(rc.failures, 0) as failures
            FROM latest_readings lr
            LEFT JOIN restart_counts rc ON lr.miner_id = rc.miner_id
            ORDER BY rc.restarts_24h DESC, rc.restarts_7d DESC, rc.failures DESC
        """).fetchall()
    finally:
        conn.close()
    
    results = []
    for r in rows:
        # Calculate a pseudo-score based on restart patterns
        score = 0
        score += r["restarts_24h"] * 25  # High weight for recent restarts
        score += r["restarts_7d"] * 5    # Medium weight for weekly
        score += r["failures"] * 15      # High weight for failures
        score = min(score, 100)
        
        eta_info = calculate_miner_eta(r["miner_id"], score)
        eta_info["ip"] = r["ip"]
        
        # Only include miners with issues
        if eta_info["risk_level"] != "Healthy":
            results.append(eta_info)
    
    # Sort by urgency (lowest ETA first)
    results.sort(key=lambda x: x["eta_hours"] or 9999)
    
    return results


def format_eta_report() -> str:
    """Format ETA ranking as a Slack message."""
    rankings = get_fleet_eta_ranking()
    
    if not rankings:
        return "✅ *Predictive ETA*: No miners showing signs of imminent failure."
    
    lines = ["⏰ *Predictive Failure ETA*\n"]
    
    # Group by risk level
    critical = [r for r in rankings if r["risk_level"] == "Critical"]
    high = [r for r in rankings if r["risk_level"] == "High"]
    medium = [r for r in rankings if r["risk_level"] == "Medium"]
    
    if critical:
        lines.append("🔴 *CRITICAL* (< 24 hours)")
        for m in critical[:5]:
            factors_str = "; ".join(m["factors"][:2]) if m["factors"] else "Multiple signals"
            lines.append(f"  `{m['ip']}` — ETA: {m['eta_label']} ({m['confidence']} confidence)")
            lines.append(f"    ↳ {factors_str}")
    
    if high:
        lines.append("\n🟠 *HIGH RISK* (1-2 days)")
        for m in high[:5]:
            factors_str = "; ".join(m["factors"][:2]) if m["factors"] else "Multiple signals"
            lines.append(f"  `{m['ip']}` — ETA: {m['eta_label']}")
            lines.append(f"    ↳ {factors_str}")
    
    if medium:
        lines.append(f"\n🟡 *MEDIUM RISK*: {len(medium)} miners (~1 week)")
    
    return "\n".join(lines)


def get_eta_for_miner(ip_or_id: str) -> Dict[str, Any]:
    """Get ETA for a specific miner by IP or ID."""
    conn = get_db()
    try:
        # Find miner
        row = conn.execute("""
            SELECT miner_id, ip FROM miner_readings
            WHERE ip = ? OR miner_id = ?
            ORDER BY id DESC LIMIT 1
        """, (ip_or_id, ip_or_id)).fetchone()
        
        if not row:
            return {"error": f"Miner {ip_or_id} not found"}
        
        miner_id = row["miner_id"]
        ip = row["ip"]
        
        # Get restart stats to calculate score
        restarts = conn.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN restarted_at > datetime('now', '-1 day') THEN 1 ELSE 0 END) as h24,
                SUM(CASE WHEN restarted_at > datetime('now', '-7 days') THEN 1 ELSE 0 END) as d7,
                SUM(CASE WHEN outcome IN ('FAILURE', 'FAILED') THEN 1 ELSE 0 END) as fails
            FROM miner_restarts WHERE miner_id = ?
        """, (miner_id,)).fetchone()
    finally:
        conn.close()
    
    # Calculate score
    score = 0
    if restarts:
        score += (restarts["h24"] or 0) * 25
        score += (restarts["d7"] or 0) * 5
        score += (restarts["fails"] or 0) * 15
    score = min(score, 100)
    
    eta_info = calculate_miner_eta(miner_id, score)
    eta_info["ip"] = ip
    
    return eta_info
