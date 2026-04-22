"""
morning_briefing.py
Mining Guardian — Daily Morning Briefing

Posts a 7am daily summary to #mining-guardian covering:
  - Overnight events (restarts, approvals, new dead boards)
  - Current fleet status
  - Environmental trends (temp, HVAC delta)
  - Bitcoin price + estimated daily revenue
  - LLM-generated analysis of anything notable overnight
  - Top miners to watch today based on recent history

Run via cron: 0 7 * * * cd /root/Mining-Gaurdian && venv/bin/python morning_briefing.py
"""

import os
import json
import sqlite3
import logging
import requests
from datetime import datetime, timedelta
from slack_sdk import WebClient
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("morning_briefing")

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
CHANNEL_ID      = "C0AQ8SE1448"
DB_PATH         = "guardian.db"
OLLAMA_URL      = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY", "")


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def get_btc_price() -> tuple:
    """Returns (price_usd, change_24h_pct) or (None, None)."""
    try:
        resp = requests.get(
            "https://api.coinbase.com/v2/prices/BTC-USD/spot",
            timeout=8
        )
        price = float(resp.json()["data"]["amount"])
        return price, None
    except Exception:
        return None, None


def get_overnight_summary() -> dict:
    """Pull everything that happened since midnight."""
    conn   = get_db()
    # Use UTC consistently — rest of codebase stores timestamps in UTC
    from datetime import timezone
    now_utc   = datetime.now(timezone.utc)
    since     = now_utc.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    yesterday = (now_utc - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0).isoformat()

    # Audit log — approved/denied actions overnight
    actions = conn.execute("""
        SELECT miner_id, ip, model, action_taken, decision, approved_by, timestamp
        FROM action_audit_log
        WHERE timestamp >= ?
        ORDER BY timestamp
    """, (yesterday,)).fetchall()

    # Latest scan
    latest = conn.execute("""
        SELECT * FROM scans ORDER BY id DESC LIMIT 1
    """).fetchone()

    # New dead boards discovered
    dead = conn.execute("""
        SELECT miner_id, ip, model, board_indices, first_seen
        FROM known_dead_boards
        WHERE first_seen >= ? AND resolved_at IS NULL
    """, (yesterday,)).fetchall()

    # Resolved dead boards overnight
    resolved = conn.execute("""
        SELECT miner_id, ip, model, board_indices, resolved_at
        FROM known_dead_boards
        WHERE resolved_at >= ?
    """, (yesterday,)).fetchall()

    # Top flagged miners in last 24h
    top_flagged = conn.execute("""
        SELECT miner_id, ip, model, COUNT(*) as flags,
               AVG(temp_chip) as avg_temp, AVG(hashrate_pct) as avg_hr
        FROM miner_readings
        WHERE scanned_at >= ? AND action IS NOT NULL AND action != 'MONITOR'
        GROUP BY miner_id
        ORDER BY flags DESC
        LIMIT 5
    """, (yesterday,)).fetchall()

    # HVAC overnight average
    hvac = conn.execute("""
        SELECT AVG(supply_temp_f) as avg_supply, AVG(return_temp_f) as avg_return,
               AVG(delta_t_f) as avg_dt, MAX(return_temp_f) as max_return
        FROM hvac_readings
        WHERE recorded_at >= ?
    """, (yesterday,)).fetchone()

    # Weather overnight
    wx = conn.execute("""
        SELECT AVG(temp_f) as avg_temp, MAX(temp_f) as max_temp,
               AVG(humidity_pct) as avg_hum
        FROM weather_readings
        WHERE recorded_at >= ?
    """, (yesterday,)).fetchone()

    conn.close()
    return {
        "actions":     [dict(a) for a in actions],
        "latest_scan": dict(latest) if latest else {},
        "dead_boards": [dict(d) for d in dead],
        "resolved":    [dict(r) for r in resolved],
        "top_flagged": [dict(f) for f in top_flagged],
        "hvac":        dict(hvac) if hvac else {},
        "weather":     dict(wx) if wx else {},
    }


def query_llm(prompt: str) -> str:
    """Query LLM — Claude API if available, else Ollama."""
    if ANTHROPIC_KEY:
        try:
            resp = requests.post("https://api.anthropic.com/v1/messages", json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 600,
                "messages": [{"role": "user", "content": prompt}]
            }, headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            for block in data.get("content", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    return block["text"]
            logger.warning("Claude returned no text block in morning briefing")
            return None
        except Exception as e:
            logger.warning("Claude API failed, falling back to Ollama: %s", e)

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL, "prompt": prompt, "stream": False
        }, timeout=120)
        return resp.json().get("response", "")
    except Exception as e:
        logger.warning("Ollama also failed: %s", e)
        return ""


def build_briefing(data: dict, btc_price: float) -> str:
    """Build the morning briefing Slack message."""
    now   = datetime.now().strftime("%A, %B %d — %I:%M %p")
    scan  = data["latest_scan"]
    lines = [f"*🌅 Good morning — Mining Guardian Daily Briefing*",
             f"_{now}_", ""]

    # Fleet status
    if scan:
        online  = scan.get("online", 0)
        offline = scan.get("offline", 0)
        issues  = scan.get("issues", 0)
        status  = "✅ Fleet healthy" if issues == 0 else f"⚠️ {issues} issue(s) active"
        lines.append(f"*Fleet:* {online} online / {offline} offline — {status}")

    # BTC price + revenue estimate using real fleet hashrate
    if btc_price:
        try:
            conn_hr = get_db()
            # Bug fix: column is 'hashrate' (GH/s), not 'hashrate_ths'
            row = conn_hr.execute("""
                SELECT SUM(mr.hashrate) / 1000.0 as fleet_ths FROM (
                    SELECT miner_id, MAX(id) as max_id
                    FROM miner_readings WHERE status='online'
                    GROUP BY miner_id
                ) latest
                JOIN miner_readings mr ON mr.id = latest.max_id
            """).fetchone()
            conn_hr.close()
            fleet_ths = float(row["fleet_ths"] or 0) if row else 0
        except Exception:
            fleet_ths = 0
        if fleet_ths <= 0:
            fleet_ths = 5000  # fallback if DB unavailable
        est_daily_btc = fleet_ths * 86400 / (1e12 * 900)
        est_daily_usd = est_daily_btc * btc_price
        lines.append(f"*₿ BTC:* ${btc_price:,.0f} | Est. daily revenue: ~${est_daily_usd:,.0f} ({fleet_ths:,.0f} TH/s)")

    # Cost & Profitability (Apr 22 2026)
    try:
        from monitoring.cost_tracker import CostTracker
        from core.database import GuardianDB
        db = GuardianDB(os.path.join(os.path.dirname(__file__), "..", "guardian.db"))
        tracker = CostTracker(db)
        profit_data = tracker.get_profitability_analysis()
        if "error" not in profit_data:
            daily_cost = profit_data["daily_electricity_cost"]
            daily_profit = profit_data["daily_profit"]
            margin = profit_data["profit_margin_pct"]
            rate = profit_data["electricity_rate"]
            emoji = "📈" if daily_profit > 0 else "📉"
            lines.append(f"*⚡ Electricity:* ${daily_cost:,.0f}/day @ ${rate}/kWh | {emoji} Profit: ${daily_profit:,.0f}/day ({margin:.0f}% margin)")
    except Exception as e:
        logger.warning(f"Cost tracking unavailable for briefing: {e}")


    # Overnight actions
    actions = data["actions"]
    if actions:
        approved = [a for a in actions if a["decision"] == "APPROVED"]
        denied   = [a for a in actions if a["decision"] == "DENIED"]
        lines.append(f"\n*🔧 Overnight Actions ({len(actions)} total)*")
        if approved:
            lines.append(f"  ✅ {len(approved)} approved — " +
                         ", ".join(f"`{a['ip']}`" for a in approved[:5]))
        if denied:
            lines.append(f"  ❌ {len(denied)} denied")
    else:
        lines.append("\n*🔧 Overnight Actions:* None")

    # Dead boards
    if data["dead_boards"]:
        lines.append(f"\n*🔴 New Dead Boards ({len(data['dead_boards'])})*")
        for d in data["dead_boards"]:
            lines.append(f"  • `{d['ip']}` {d['model']} — boards {d['board_indices']}")

    if data["resolved"]:
        lines.append(f"*✅ Boards Recovered:* {len(data['resolved'])}")

    # Top flagged miners overnight
    if data["top_flagged"]:
        lines.append(f"\n*⚠️ Most Active Problem Miners (last 24h)*")
        for f in data["top_flagged"]:
            lines.append(f"  • `{f['ip']}` {f['model']} — flagged {f['flags']}x "
                         f"| avg HR: {f['avg_hr'] or 0:.0f}% | avg temp: {f['avg_temp'] or 0:.0f}°C")

    # HVAC overnight
    hvac = data["hvac"]
    if hvac.get("avg_supply"):
        lines.append(f"\n*🌡️ Overnight HVAC*")
        lines.append(f"  Supply avg: {hvac['avg_supply']:.1f}°F | "
                     f"Return avg: {hvac['avg_return']:.1f}°F | "
                     f"ΔT avg: {hvac['avg_dt']:.1f}°F | "
                     f"Return peak: {hvac['max_return']:.1f}°F")

    return "\n".join(lines)


def main():
    logger.info("Running morning briefing...")
    client   = WebClient(token=SLACK_BOT_TOKEN)
    data     = get_overnight_summary()
    btc, _   = get_btc_price()

    # Build the base briefing message
    briefing = build_briefing(data, btc)

    # Ask LLM for any notable insights
    notable = []
    if data["dead_boards"]:
        notable.append(f"{len(data['dead_boards'])} new dead board(s) detected overnight")
    if data["top_flagged"]:
        notable.append(f"Top problem miner: {data['top_flagged'][0]['ip']} "
                       f"flagged {data['top_flagged'][0]['flags']}x in 24h")
    if data["hvac"].get("max_return") and data["hvac"]["max_return"] > 90:
        notable.append(f"Return water peaked at {data['hvac']['max_return']:.1f}°F overnight")

    if notable:
        llm_prompt = (
            "You are Mining Guardian AI for BiXBiT USA in Fort Worth, TX. "
            "All cooling is liquid. Write a 2-3 sentence operator note about "
            "these overnight events. Be direct and actionable:\n"
            + "\n".join(f"- {n}" for n in notable)
        )
        llm_note = query_llm(llm_prompt)
        if llm_note and "error" not in llm_note.lower():
            briefing += f"\n\n*🤖 AI Note:* {llm_note.strip()}"

    # Post to Slack
    try:
        client.chat_postMessage(channel=CHANNEL_ID, text=briefing)
        logger.info("Morning briefing posted to #mining-guardian")
    except Exception as e:
        logger.error("Failed to post briefing: %s", e)


if __name__ == "__main__":
    main()
