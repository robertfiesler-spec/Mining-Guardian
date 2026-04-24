"""
Cost Tracker Module for Mining Guardian
April 22, 2026

Provides electricity cost tracking and profitability analysis:
- Option A: Simple fleet total (kW × $/kWh × hours)
- Option B: Per-miner breakdown (actual consumption from chain_readings)
- Option C: Full profitability (BTC revenue - electricity cost = profit)

Configuration via .env:
- ELECTRICITY_RATE_KWH: Default $0.042/kWh (BiXBiT USA rate)
"""

import os
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# Default electricity rate (can be overridden via .env)
DEFAULT_ELECTRICITY_RATE = 0.042  # $/kWh



class _PgConnWrapper:
    """Thin wrapper over psycopg2 Connection providing a SQLite-style
    conn.execute(sql, params).fetchone/fetchall() shortcut.

    psycopg2 Connection has no .execute() method — SQL must go through a
    cursor. This wrapper creates a cursor per call so the existing
    `conn.execute("SELECT ...").fetchall()` idiom keeps working without
    rewriting every call site.
    """

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        cur = self._conn.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()
        return False


class CostTracker:
    """Electricity cost and profitability tracker for mining operations."""

    def __init__(self, db_or_path, electricity_rate: Optional[float] = None):
        # Accept either a GuardianDB object or a database path string
        if isinstance(db_or_path, str):
            self.db_path = db_or_path
            self.db = None
        else:
            self.db = db_or_path
            self.db_path = None
        self.electricity_rate = electricity_rate or float(
            os.getenv("ELECTRICITY_RATE_KWH", DEFAULT_ELECTRICITY_RATE)
        )

    def _get_connection(self):
        """Get a database connection.

        Accepts either a DSN string (db_path) or a pre-existing GuardianPGDB
        instance (self.db). Returns a _PgConnWrapper in both cases so callers
        can use the SQLite-style `conn.execute(sql).fetchone()` idiom.
        """
        import psycopg2
        from psycopg2.extras import DictCursor
        if self.db_path:
            return _PgConnWrapper(psycopg2.connect(self.db_path, cursor_factory=DictCursor))
        elif self.db is not None:
            # GuardianPGDB was passed — open a fresh connection using its DSN
            return _PgConnWrapper(psycopg2.connect(self.db._dsn, cursor_factory=DictCursor))
        else:
            raise RuntimeError("CostTracker has neither db_path nor db instance")

    def get_electricity_rate(self) -> float:
        """Get current electricity rate in $/kWh."""
        return self.electricity_rate

    def set_electricity_rate(self, rate: float) -> None:
        """Update electricity rate (runtime only, doesn't persist to .env)."""
        self.electricity_rate = rate
        logger.info(f"Electricity rate updated to ${rate}/kWh")

    # ══════════════════════════════════════════════════════════════════════════
    # OPTION A: Simple Fleet Total
    # ══════════════════════════════════════════════════════════════════════════

    def get_fleet_power_summary(self) -> Dict[str, Any]:
        """
        Option A: Simple fleet-wide power and cost summary.
        
        Returns:
            total_watts: Current fleet power draw in watts
            total_kw: Current fleet power draw in kW
            hourly_cost: Cost per hour at current rate
            daily_cost: Estimated daily cost (24h)
            monthly_cost: Estimated monthly cost (30 days)
            online_miners: Number of miners online
            rate_per_kwh: Current electricity rate
        """
        conn = self._get_connection()
        try:
            # Get latest power readings per miner (sum all boards)
            rows = conn.execute("""
                SELECT miner_id, SUM(consumption_w) as total_watts
                FROM chain_readings
                WHERE scanned_at = (
                    SELECT MAX(scanned_at) FROM chain_readings
                )
                AND consumption_w IS NOT NULL AND consumption_w > 0
                GROUP BY miner_id
            """).fetchall()

            if not rows:
                return {
                    "total_watts": 0,
                    "total_kw": 0,
                    "hourly_cost": 0,
                    "daily_cost": 0,
                    "monthly_cost": 0,
                    "online_miners": 0,
                    "rate_per_kwh": self.electricity_rate,
                    "error": "No power data available"
                }

            total_watts = sum(r["total_watts"] for r in rows)
            total_kw = total_watts / 1000
            hourly_cost = total_kw * self.electricity_rate
            daily_cost = hourly_cost * 24
            monthly_cost = daily_cost * 30

            return {
                "total_watts": round(total_watts, 0),
                "total_kw": round(total_kw, 2),
                "hourly_cost": round(hourly_cost, 2),
                "daily_cost": round(daily_cost, 2),
                "monthly_cost": round(monthly_cost, 2),
                "online_miners": len(rows),
                "rate_per_kwh": self.electricity_rate
            }
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════════════════════════
    # OPTION B: Per-Miner Breakdown
    # ══════════════════════════════════════════════════════════════════════════

    def get_per_miner_costs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Option B: Per-miner electricity cost breakdown.
        
        Returns list of miners sorted by cost (highest first):
            miner_id, ip, model, watts, kw, hourly_cost, daily_cost, hashrate_ths
        """
        conn = self._get_connection()
        try:
            # Get latest readings with hashrate
            rows = conn.execute("""
                SELECT 
                    cr.miner_id,
                    cr.ip,
                    SUM(cr.consumption_w) as total_watts,
                    SUM(cr.rate_mhs) / 1000 as hashrate_ths
                FROM chain_readings cr
                WHERE cr.scanned_at = (
                    SELECT MAX(scanned_at) FROM chain_readings
                )
                AND cr.consumption_w IS NOT NULL AND cr.consumption_w > 0
                GROUP BY cr.miner_id, cr.ip
                ORDER BY total_watts DESC
                LIMIT %s
            """, (limit,)).fetchall()

            results = []
            for r in rows:
                watts = r["total_watts"]
                kw = watts / 1000
                hourly = kw * self.electricity_rate
                daily = hourly * 24
                hashrate = r["hashrate_ths"] or 0

                # Efficiency: J/TH (watts per TH/s)
                efficiency = (watts / hashrate) if hashrate > 0 else 0

                results.append({
                    "miner_id": r["miner_id"],
                    "ip": r["ip"],
                    "watts": round(watts, 0),
                    "kw": round(kw, 2),
                    "hourly_cost": round(hourly, 3),
                    "daily_cost": round(daily, 2),
                    "hashrate_ths": round(hashrate, 1),
                    "efficiency_jth": round(efficiency, 1)
                })

            return results
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════════════════════════
    # OPTION C: Full Profitability Analysis
    # ══════════════════════════════════════════════════════════════════════════

    def get_btc_price(self) -> Optional[float]:
        """Fetch current BTC price from Coinbase API."""
        try:
            resp = requests.get(
                "https://api.coinbase.com/v2/prices/BTC-USD/spot",
                timeout=10
            )
            return float(resp.json()["data"]["amount"])
        except Exception as e:
            logger.warning(f"Failed to fetch BTC price: {e}")
            return None

    def get_network_difficulty(self) -> Optional[float]:
        """Fetch current Bitcoin network difficulty."""
        try:
            resp = requests.get(
                "https://blockchain.info/q/getdifficulty",
                timeout=10
            )
            return float(resp.text)
        except Exception as e:
            logger.warning(f"Failed to fetch network difficulty: {e}")
            return None

    def estimate_daily_btc_revenue(self, hashrate_ths: float, difficulty: Optional[float] = None) -> float:
        """
        Estimate daily BTC revenue based on hashrate and network difficulty.
        
        Formula: (hashrate * 86400 * block_reward) / (difficulty * 2^32)
        """
        if difficulty is None:
            difficulty = self.get_network_difficulty()
        if difficulty is None or difficulty <= 0:
            # Fallback: rough estimate using 750 EH/s network hashrate
            # daily_btc ≈ (hashrate_ths / 750_000_000) * 3.125 * 144
            return (hashrate_ths / 750_000_000) * 3.125 * 144

        block_reward = 3.125  # Post-halving 2024
        blocks_per_day = 144
        
        # More accurate calculation
        # hashrate in H/s = hashrate_ths * 1e12
        hashrate_hs = hashrate_ths * 1e12
        network_hashrate = (difficulty * 2**32) / 600  # H/s
        
        if network_hashrate <= 0:
            return 0
            
        share = hashrate_hs / network_hashrate
        daily_btc = share * block_reward * blocks_per_day
        
        return daily_btc

    def get_profitability_analysis(self) -> Dict[str, Any]:
        """
        Option C: Full profitability analysis.
        
        Returns:
            btc_price: Current BTC/USD price
            fleet_hashrate_ths: Total fleet hashrate in TH/s
            daily_btc: Estimated daily BTC revenue
            daily_revenue_usd: Daily revenue in USD
            daily_electricity_cost: Daily electricity cost in USD
            daily_profit: Daily profit (revenue - cost)
            monthly_profit: Monthly profit estimate
            profit_margin: Profit as percentage of revenue
            breakeven_btc_price: BTC price at which profit = 0
            cost_per_btc_mined: Electricity cost per BTC mined
        """
        # Get fleet power and hashrate
        conn = self._get_connection()
        try:
            rows = conn.execute("""
                SELECT 
                    SUM(consumption_w) as total_watts,
                    SUM(rate_mhs) / 1000 as total_hashrate_ths
                FROM chain_readings
                WHERE scanned_at = (
                    SELECT MAX(scanned_at) FROM chain_readings
                )
                AND consumption_w IS NOT NULL AND consumption_w > 0
            """).fetchone()
        finally:
            conn.close()

        if not rows or not rows["total_watts"]:
            return {"error": "No power/hashrate data available"}

        total_watts = rows["total_watts"]
        total_kw = total_watts / 1000
        hashrate_ths = rows["total_hashrate_ths"] or 0

        # Get BTC price
        btc_price = self.get_btc_price()
        if btc_price is None:
            return {"error": "Could not fetch BTC price"}

        # Calculate costs
        daily_electricity_cost = total_kw * self.electricity_rate * 24

        # Calculate revenue
        daily_btc = self.estimate_daily_btc_revenue(hashrate_ths)
        daily_revenue_usd = daily_btc * btc_price

        # Calculate profit
        daily_profit = daily_revenue_usd - daily_electricity_cost
        monthly_profit = daily_profit * 30

        # Calculate metrics
        profit_margin = (daily_profit / daily_revenue_usd * 100) if daily_revenue_usd > 0 else 0
        
        # Breakeven BTC price: price where revenue = cost
        breakeven_btc_price = (daily_electricity_cost / daily_btc) if daily_btc > 0 else 0
        
        # Cost per BTC mined
        cost_per_btc = (daily_electricity_cost / daily_btc) if daily_btc > 0 else 0

        return {
            "btc_price": round(btc_price, 2),
            "fleet_hashrate_ths": round(hashrate_ths, 1),
            "fleet_power_kw": round(total_kw, 2),
            "daily_btc": round(daily_btc, 6),
            "daily_revenue_usd": round(daily_revenue_usd, 2),
            "daily_electricity_cost": round(daily_electricity_cost, 2),
            "daily_profit": round(daily_profit, 2),
            "monthly_profit": round(monthly_profit, 2),
            "profit_margin_pct": round(profit_margin, 1),
            "breakeven_btc_price": round(breakeven_btc_price, 2),
            "cost_per_btc_mined": round(cost_per_btc, 2),
            "electricity_rate": self.electricity_rate
        }

    # ══════════════════════════════════════════════════════════════════════════
    # Formatted Output for Slack/Display
    # ══════════════════════════════════════════════════════════════════════════

    def format_fleet_summary(self) -> str:
        """Format Option A as a Slack message."""
        data = self.get_fleet_power_summary()
        if "error" in data:
            return f"⚠️ {data['error']}"
        
        return (
            f"⚡ *Fleet Power Summary*\n"
            f"  Power: {data['total_kw']:,.1f} kW ({data['online_miners']} miners)\n"
            f"  Rate: ${data['rate_per_kwh']}/kWh\n"
            f"  Hourly: ${data['hourly_cost']:,.2f}\n"
            f"  Daily: ${data['daily_cost']:,.2f}\n"
            f"  Monthly: ${data['monthly_cost']:,.2f}"
        )

    def format_per_miner_costs(self, top_n: int = 10) -> str:
        """Format Option B as a Slack message (top N by cost)."""
        miners = self.get_per_miner_costs(limit=top_n)
        if not miners:
            return "⚠️ No per-miner cost data available"
        
        lines = [f"⚡ *Per-Miner Electricity Cost* (top {len(miners)} by usage)"]
        for m in miners:
            lines.append(
                f"  `{m['ip']}` — {m['watts']:,.0f}W | "
                f"${m['daily_cost']:.2f}/day | "
                f"{m['hashrate_ths']:.1f} TH/s | "
                f"{m['efficiency_jth']:.0f} J/TH"
            )
        return "\n".join(lines)

    def format_profitability(self) -> str:
        """Format Option C as a Slack message."""
        data = self.get_profitability_analysis()
        if "error" in data:
            return f"⚠️ {data['error']}"
        
        # Determine profit emoji
        if data["daily_profit"] > 0:
            profit_emoji = "📈"
            profit_status = "PROFITABLE"
        else:
            profit_emoji = "📉"
            profit_status = "UNPROFITABLE"

        return (
            f"💰 *Mining Profitability Analysis*\n"
            f"\n"
            f"*Revenue*\n"
            f"  ₿ Price: ${data['btc_price']:,.0f}\n"
            f"  Fleet: {data['fleet_hashrate_ths']:,.0f} TH/s @ {data['fleet_power_kw']:,.1f} kW\n"
            f"  Daily: ~{data['daily_btc']:.5f} BTC (${data['daily_revenue_usd']:,.2f})\n"
            f"\n"
            f"*Costs*\n"
            f"  Rate: ${data['electricity_rate']}/kWh\n"
            f"  Daily electricity: ${data['daily_electricity_cost']:,.2f}\n"
            f"  Cost per BTC: ${data['cost_per_btc_mined']:,.0f}\n"
            f"\n"
            f"*{profit_emoji} {profit_status}*\n"
            f"  Daily profit: ${data['daily_profit']:,.2f}\n"
            f"  Monthly profit: ${data['monthly_profit']:,.2f}\n"
            f"  Margin: {data['profit_margin_pct']:.1f}%\n"
            f"  Breakeven BTC: ${data['breakeven_btc_price']:,.0f}"
        )

    def format_full_report(self) -> str:
        """Format all three options as a comprehensive report."""
        lines = []
        
        # Option A: Fleet Summary
        lines.append(self.format_fleet_summary())
        lines.append("")
        
        # Option B: Top 5 miners by cost
        lines.append(self.format_per_miner_costs(top_n=5))
        lines.append("")
        
        # Option C: Profitability
        lines.append(self.format_profitability())
        
        return "\n".join(lines)
