"""
Trends API Endpoints for Mining Guardian Dashboard
April 22, 2026

Provides time-series data for trend visualization:
- Fleet-wide hashrate, power, efficiency trends
- Per-miner degradation tracking
- Temperature trends with HVAC correlation
- Profitability trends over time
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional


def get_fleet_trends(conn, hours: int = 24) -> Dict[str, Any]:
    """
    Fleet-wide trends over the specified time window.
    
    Returns time-series data for:
    - Total hashrate (TH/s)
    - Total power (kW)
    - Efficiency (J/TH)
    - Online/offline miner counts
    - Temperature averages
    """
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    
    # Get aggregated chain readings per scan timestamp
    rows = conn.execute("""
        SELECT 
            scanned_at,
            COUNT(DISTINCT miner_id) as miner_count,
            SUM(rate_mhs) / 1000.0 as total_hashrate_ths,
            SUM(consumption_w) / 1000.0 as total_power_kw,
            AVG(temp_chip) as avg_chip_temp,
            MAX(temp_chip) as max_chip_temp
        FROM chain_readings
        WHERE scanned_at > ?
        AND consumption_w > 0
        GROUP BY scanned_at
        ORDER BY scanned_at ASC
    """, (cutoff,)).fetchall()
    
    data_points = []
    for r in rows:
        hashrate = r["total_hashrate_ths"] or 0
        power = r["total_power_kw"] or 0
        efficiency = (power * 1000 / hashrate) if hashrate > 0 else 0
        
        data_points.append({
            "timestamp": r["scanned_at"],
            "miners": r["miner_count"],
            "hashrate_ths": round(hashrate, 1),
            "power_kw": round(power, 2),
            "efficiency_jth": round(efficiency, 1),
            "avg_temp": round(r["avg_chip_temp"] or 0, 1),
            "max_temp": round(r["max_chip_temp"] or 0, 1)
        })
    
    return {
        "hours": hours,
        "data_points": len(data_points),
        "series": data_points
    }


def get_miner_trend(conn, miner_id: str, hours: int = 24) -> Dict[str, Any]:
    """
    Single miner trend data for degradation tracking.
    
    Returns time-series of:
    - Hashrate per board
    - Power consumption
    - Temperatures
    - Board health indicators
    """
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    
    rows = conn.execute("""
        SELECT 
            scanned_at,
            board_index,
            rate_mhs / 1000.0 as hashrate_ths,
            consumption_w,
            temp_chip,
            temp_chip,
            voltage
        FROM chain_readings
        WHERE miner_id = ?
        AND scanned_at > ?
        ORDER BY scanned_at ASC, board_index ASC
    """, (miner_id, cutoff)).fetchall()
    
    # Group by timestamp
    by_timestamp = {}
    for r in rows:
        ts = r["scanned_at"]
        if ts not in by_timestamp:
            by_timestamp[ts] = {
                "timestamp": ts,
                "boards": [],
                "total_hashrate": 0,
                "total_power": 0,
                "max_temp": 0
            }
        by_timestamp[ts]["boards"].append({
            "index": r["board_index"],
            "hashrate_ths": round(r["hashrate_ths"] or 0, 2),
            "watts": round(r["consumption_w"] or 0, 0),
            "temp": round(r["temp_chip"] or 0, 1),
            "voltage": round(r["voltage"] or 0, 2)
        })
        by_timestamp[ts]["total_hashrate"] += r["hashrate_ths"] or 0
        by_timestamp[ts]["total_power"] += r["consumption_w"] or 0
        by_timestamp[ts]["max_temp"] = max(by_timestamp[ts]["max_temp"], r["temp_chip"] or 0)
    
    series = list(by_timestamp.values())
    for point in series:
        point["total_hashrate"] = round(point["total_hashrate"], 1)
        point["total_power"] = round(point["total_power"], 0)
        point["max_temp"] = round(point["max_temp"], 1)
    
    return {
        "miner_id": miner_id,
        "hours": hours,
        "data_points": len(series),
        "series": series
    }


def get_degradation_ranking(conn, days: int = 7) -> List[Dict[str, Any]]:
    """
    Rank miners by degradation over the time window.
    
    Compares recent performance vs baseline to identify
    miners showing decline in hashrate or efficiency.
    """
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    recent_cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    
    # Get baseline (first half of period) vs recent (last 24h)
    rows = conn.execute("""
        WITH baseline AS (
            SELECT 
                miner_id,
                AVG(rate_mhs) / 1000.0 as avg_hashrate,
                AVG(consumption_w) as avg_power
            FROM chain_readings
            WHERE scanned_at > ? AND scanned_at < ?
            AND consumption_w > 0
            GROUP BY miner_id
        ),
        recent AS (
            SELECT 
                miner_id,
                AVG(rate_mhs) / 1000.0 as avg_hashrate,
                AVG(consumption_w) as avg_power
            FROM chain_readings
            WHERE scanned_at > ?
            AND consumption_w > 0
            GROUP BY miner_id
        )
        SELECT 
            b.miner_id,
            b.avg_hashrate as baseline_hashrate,
            r.avg_hashrate as recent_hashrate,
            b.avg_power as baseline_power,
            r.avg_power as recent_power,
            ((r.avg_hashrate - b.avg_hashrate) / NULLIF(b.avg_hashrate, 0)) * 100 as hashrate_change_pct,
            ((r.avg_power - b.avg_power) / NULLIF(b.avg_power, 0)) * 100 as power_change_pct
        FROM baseline b
        JOIN recent r ON b.miner_id = r.miner_id
        WHERE b.avg_hashrate > 0
        ORDER BY hashrate_change_pct ASC
        LIMIT 20
    """, (cutoff, recent_cutoff, recent_cutoff)).fetchall()
    
    return [
        {
            "miner_id": r["miner_id"],
            "baseline_hashrate_ths": round(r["baseline_hashrate"] or 0, 1),
            "recent_hashrate_ths": round(r["recent_hashrate"] or 0, 1),
            "hashrate_change_pct": round(r["hashrate_change_pct"] or 0, 1),
            "baseline_power_w": round(r["baseline_power"] or 0, 0),
            "recent_power_w": round(r["recent_power"] or 0, 0),
            "power_change_pct": round(r["power_change_pct"] or 0, 1)
        }
        for r in rows
    ]


def get_profitability_trend(conn, electricity_rate: float, hours: int = 168) -> List[Dict[str, Any]]:
    """
    Profitability trend over time (default: 7 days).
    
    Estimates profit at each scan point based on:
    - Fleet hashrate at that time
    - Power consumption at that time
    - Current BTC price (simplified - uses latest)
    """
    import requests
    
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    
    # Get BTC price
    try:
        resp = requests.get("https://api.coinbase.com/v2/prices/BTC-USD/spot", timeout=10)
        btc_price = float(resp.json()["data"]["amount"])
    except Exception:
        btc_price = 78000  # Fallback
    
    rows = conn.execute("""
        SELECT 
            scanned_at,
            SUM(rate_mhs) / 1000.0 as total_hashrate_ths,
            SUM(consumption_w) / 1000.0 as total_power_kw
        FROM chain_readings
        WHERE scanned_at > ?
        AND consumption_w > 0
        GROUP BY scanned_at
        ORDER BY scanned_at ASC
    """, (cutoff,)).fetchall()
    
    series = []
    for r in rows:
        hashrate = r["total_hashrate_ths"] or 0
        power_kw = r["total_power_kw"] or 0
        
        # Estimate hourly revenue/cost
        # BTC per hour ≈ hashrate * 3600 / (difficulty * 2^32) * block_reward
        # Simplified: hashrate_ths / 750,000,000 * 3.125 * 6 (blocks/hour)
        hourly_btc = (hashrate / 750_000_000) * 3.125 * 6
        hourly_revenue = hourly_btc * btc_price
        hourly_cost = power_kw * electricity_rate
        hourly_profit = hourly_revenue - hourly_cost
        
        series.append({
            "timestamp": r["scanned_at"],
            "hashrate_ths": round(hashrate, 1),
            "power_kw": round(power_kw, 2),
            "hourly_revenue": round(hourly_revenue, 4),
            "hourly_cost": round(hourly_cost, 4),
            "hourly_profit": round(hourly_profit, 4)
        })
    
    return {
        "hours": hours,
        "btc_price": btc_price,
        "electricity_rate": electricity_rate,
        "data_points": len(series),
        "series": series
    }


def get_temperature_trends(conn, hours: int = 24) -> Dict[str, Any]:
    """
    Temperature trends with HVAC correlation.
    
    Returns:
    - Chip temperatures over time
    - HVAC supply/return temps
    - Correlation indicators
    """
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    
    # Chip temps from chain_readings
    chip_rows = conn.execute("""
        SELECT 
            scanned_at,
            AVG(temp_chip) as avg_temp,
            MAX(temp_chip) as max_temp,
            MIN(temp_chip) as min_temp
        FROM chain_readings
        WHERE scanned_at > ?
        AND temp_chip IS NOT NULL
        GROUP BY scanned_at
        ORDER BY scanned_at ASC
    """, (cutoff,)).fetchall()
    
    # HVAC temps
    hvac_rows = conn.execute("""
        SELECT 
            recorded_at,
            supply_temp_f,
            return_temp_f,
            return_temp_f - supply_temp_f as delta_t
        FROM hvac_readings
        WHERE recorded_at > ?
        ORDER BY recorded_at ASC
    """, (cutoff,)).fetchall()
    
    chip_series = [
        {
            "timestamp": r["scanned_at"],
            "avg": round(r["avg_temp"] or 0, 1),
            "max": round(r["max_temp"] or 0, 1),
            "min": round(r["min_temp"] or 0, 1)
        }
        for r in chip_rows
    ]
    
    hvac_series = [
        {
            "timestamp": r["recorded_at"],
            "supply": round(r["supply_temp_f"] or 0, 1),
            "return": round(r["return_temp_f"] or 0, 1),
            "delta_t": round(r["delta_t"] or 0, 1)
        }
        for r in hvac_rows
    ]
    
    return {
        "hours": hours,
        "chip_temps": {
            "data_points": len(chip_series),
            "series": chip_series
        },
        "hvac_temps": {
            "data_points": len(hvac_series),
            "series": hvac_series
        }
    }
