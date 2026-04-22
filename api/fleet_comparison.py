"""
Fleet Comparison Module for Mining Guardian
April 22, 2026

Compares miner models by performance metrics:
- Hashrate efficiency (TH/s per kW)
- Uptime/reliability
- Temperature characteristics
- Cost efficiency ($/TH/day)
"""

import os
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


def get_db():
    """Get database connection."""
    db_path = os.getenv("GUARDIAN_DB", "/root/Mining-Gaurdian/guardian.db")
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def get_model_comparison(electricity_rate: float = 0.042) -> List[Dict[str, Any]]:
    """
    Compare all miner models by key performance metrics.
    
    Returns list of models with:
    - Model name
    - Miner count
    - Average hashrate (TH/s)
    - Average power (W)
    - Efficiency (J/TH)
    - Average temperature
    - Uptime percentage
    - Daily cost per TH
    - Restart rate (per miner per week)
    """
    conn = get_db()
    try:
        # Get model stats from latest readings
        rows = conn.execute("""
            WITH latest_scan AS (
                SELECT MAX(scanned_at) as latest FROM miner_readings
            ),
            model_stats AS (
                SELECT 
                    mr.model,
                    COUNT(DISTINCT mr.miner_id) as miner_count,
                    AVG(mr.hashrate) / 1000.0 as avg_hashrate_ths,
                    AVG(mr.consumption) as avg_consumption,
                    AVG(mr.temp_chip) as avg_temp,
                    SUM(CASE WHEN mr.status = 'online' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as uptime_pct
                FROM miner_readings mr, latest_scan ls
                WHERE mr.scanned_at = ls.latest
                AND mr.model IS NOT NULL AND mr.model != ''
                GROUP BY mr.model
            ),
            restart_stats AS (
                SELECT 
                    mr.model,
                    COUNT(rst.id) * 1.0 / COUNT(DISTINCT rst.miner_id) / 
                        (julianday('now') - julianday(MIN(rst.restarted_at))) * 7 as restarts_per_miner_week
                FROM miner_readings mr
                LEFT JOIN miner_restarts rst ON mr.miner_id = rst.miner_id
                WHERE mr.model IS NOT NULL AND mr.model != ''
                GROUP BY mr.model
            )
            SELECT 
                ms.*,
                COALESCE(rs.restarts_per_miner_week, 0) as restarts_per_week
            FROM model_stats ms
            LEFT JOIN restart_stats rs ON ms.model = rs.model
            ORDER BY ms.avg_hashrate_ths DESC
        """).fetchall()
        
        results = []
        for r in rows:
            hashrate = r["avg_hashrate_ths"] or 0
            power = r["avg_consumption"] or 0
            
            # Efficiency in J/TH (lower is better)
            efficiency = (power / hashrate) if hashrate > 0 else 0
            
            # Daily cost per TH
            daily_kwh = power * 24 / 1000
            daily_cost = daily_kwh * electricity_rate
            cost_per_th = (daily_cost / hashrate) if hashrate > 0 else 0
            
            results.append({
                "model": r["model"],
                "miner_count": r["miner_count"],
                "avg_hashrate_ths": round(hashrate, 1),
                "avg_consumption": round(power, 0),
                "efficiency_jth": round(efficiency, 1),
                "avg_temp_c": round(r["avg_temp"] or 0, 1),
                "uptime_pct": round(r["uptime_pct"] or 0, 1),
                "cost_per_th_day": round(cost_per_th, 4),
                "restarts_per_week": round(r["restarts_per_week"] or 0, 2)
            })
        
        return results
    finally:
        conn.close()


def get_model_detail(model_name: str) -> Dict[str, Any]:
    """
    Get detailed stats for a specific model including all miners.
    """
    conn = get_db()
    try:
        # Get all miners of this model with latest readings
        rows = conn.execute("""
            WITH latest_scan AS (
                SELECT MAX(scanned_at) as latest FROM miner_readings
            )
            SELECT 
                mr.miner_id,
                mr.ip,
                mr.hashrate / 1000.0 as hashrate_ths,
                mr.consumption,
                mr.temp_chip,
                mr.status
            FROM miner_readings mr, latest_scan ls
            WHERE mr.scanned_at = ls.latest
            AND mr.model = ?
            ORDER BY mr.hashrate DESC
        """, (model_name,)).fetchall()
        
        if not rows:
            return {"error": f"Model {model_name} not found"}
        
        miners = []
        total_hashrate = 0
        total_power = 0
        online_count = 0
        
        for r in rows:
            hashrate = r["hashrate_ths"] or 0
            power = r["consumption"] or 0
            total_hashrate += hashrate
            total_power += power
            if r["status"] == "online":
                online_count += 1
            
            efficiency = (power / hashrate) if hashrate > 0 else 0
            
            miners.append({
                "miner_id": r["miner_id"],
                "ip": r["ip"],
                "hashrate_ths": round(hashrate, 1),
                "consumption": round(power, 0),
                "efficiency_jth": round(efficiency, 1),
                "temp_c": round(r["temp_chip"] or 0, 1),
                "status": r["status"]
            })
        
        return {
            "model": model_name,
            "miner_count": len(miners),
            "online_count": online_count,
            "total_hashrate_ths": round(total_hashrate, 1),
            "total_power_kw": round(total_power / 1000, 2),
            "avg_hashrate_ths": round(total_hashrate / len(miners), 1) if miners else 0,
            "avg_consumption": round(total_power / len(miners), 0) if miners else 0,
            "miners": miners
        }
    finally:
        conn.close()


def get_efficiency_ranking() -> List[Dict[str, Any]]:
    """
    Rank all individual miners by efficiency (J/TH).
    Lower is better.
    """
    conn = get_db()
    try:
        rows = conn.execute("""
            WITH latest_scan AS (
                SELECT MAX(scanned_at) as latest FROM miner_readings
            )
            SELECT 
                mr.miner_id,
                mr.ip,
                mr.model,
                mr.hashrate / 1000.0 as hashrate_ths,
                mr.consumption,
                mr.temp_chip
            FROM miner_readings mr, latest_scan ls
            WHERE mr.scanned_at = ls.latest
            AND mr.hashrate > 0 AND mr.consumption > 0
            ORDER BY (mr.consumption / (mr.hashrate / 1000.0)) ASC
            LIMIT 50
        """).fetchall()
        
        return [
            {
                "rank": i + 1,
                "miner_id": r["miner_id"],
                "ip": r["ip"],
                "model": r["model"],
                "hashrate_ths": round(r["hashrate_ths"], 1),
                "consumption": round(r["consumption"], 0),
                "efficiency_jth": round(r["consumption"] / r["hashrate_ths"], 1),
                "temp_c": round(r["temp_chip"] or 0, 1)
            }
            for i, r in enumerate(rows)
        ]
    finally:
        conn.close()


def format_comparison_report(electricity_rate: float = 0.042) -> str:
    """Format model comparison as Slack message."""
    models = get_model_comparison(electricity_rate)
    
    if not models:
        return "⚠️ No model comparison data available"
    
    lines = ["📊 *Fleet Model Comparison*\n"]
    
    # Header
    lines.append("```")
    lines.append(f"{'Model':<20} {'#':>3} {'TH/s':>7} {'W':>6} {'J/TH':>5} {'$/TH':>6} {'Up%':>5}")
    lines.append("-" * 60)
    
    for m in models:
        lines.append(
            f"{m['model'][:20]:<20} {m['miner_count']:>3} "
            f"{m['avg_hashrate_ths']:>7.1f} {m['avg_consumption']:>6.0f} "
            f"{m['efficiency_jth']:>5.1f} {m['cost_per_th_day']:>6.4f} "
            f"{m['uptime_pct']:>5.1f}"
        )
    
    lines.append("```")
    
    # Best performers
    if len(models) > 1:
        best_efficiency = min(models, key=lambda x: x["efficiency_jth"] if x["efficiency_jth"] > 0 else 999)
        best_uptime = max(models, key=lambda x: x["uptime_pct"])
        
        lines.append(f"\n🏆 *Best Efficiency:* {best_efficiency['model']} ({best_efficiency['efficiency_jth']:.1f} J/TH)")
        lines.append(f"🏆 *Best Uptime:* {best_uptime['model']} ({best_uptime['uptime_pct']:.1f}%)")
    
    return "\n".join(lines)


def format_efficiency_ranking(top_n: int = 10) -> str:
    """Format efficiency ranking as Slack message."""
    ranking = get_efficiency_ranking()[:top_n]
    
    if not ranking:
        return "⚠️ No efficiency ranking data available"
    
    lines = [f"⚡ *Top {top_n} Most Efficient Miners*\n"]
    lines.append("```")
    lines.append(f"{'#':>2} {'IP':<16} {'Model':<15} {'TH/s':>6} {'W':>5} {'J/TH':>5}")
    lines.append("-" * 55)
    
    for m in ranking:
        lines.append(
            f"{m['rank']:>2} {m['ip']:<16} {m['model'][:15]:<15} "
            f"{m['hashrate_ths']:>6.1f} {m['consumption']:>5.0f} {m['efficiency_jth']:>5.1f}"
        )
    
    lines.append("```")
    
    return "\n".join(lines)
