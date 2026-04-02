"""
deep_analysis_claude.py
Mining Guardian — One-Time Deep Analysis via Claude API

Pulls ALL historical data from guardian.db and feeds it to Claude
for comprehensive fleet analysis. Results saved to knowledge.json.

Usage: python3 deep_analysis_claude.py
"""

import os
import json
import sqlite3
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("deep_analysis")

CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DB_PATH = "guardian.db"


def query_claude(prompt: str) -> str:
    """Send prompt to Claude API."""
    logger.info("Sending to Claude (%d chars)...", len(prompt))
    resp = requests.post("https://api.anthropic.com/v1/messages", json={
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}]
    }, headers={
        "x-api-key": CLAUDE_API_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    }, timeout=120)
    data = resp.json()
    if "content" in data:
        text = data["content"][0]["text"]
        logger.info("Claude responded (%d chars)", len(text))
        return text
    else:
        logger.error("Claude error: %s", data.get("error", data))
        return ""


def gather_fleet_data():
    """Pull all historical data from the database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Miner history — aggregated per miner
    miners = conn.execute('''
        SELECT miner_id, model, ip, firmware_manufacturer,
               COUNT(*) as total_scans,
               AVG(hashrate_pct) as avg_hr,
               MIN(hashrate_pct) as min_hr,
               MAX(hashrate_pct) as max_hr,
               AVG(temp_chip) as avg_temp,
               MAX(temp_chip) as max_temp,
               SUM(CASE WHEN action IS NOT NULL AND action != 'MONITOR' THEN 1 ELSE 0 END) as times_flagged,
               GROUP_CONCAT(DISTINCT action) as actions_seen,
               GROUP_CONCAT(DISTINCT current_profile) as profiles_seen
        FROM miner_readings GROUP BY miner_id
        ORDER BY times_flagged DESC
    ''').fetchall()

    # AMS notifications summary
    notifs = conn.execute('''
        SELECT miner_ip, key, alert_level, COUNT(*) as cnt
        FROM ams_notifications
        GROUP BY miner_ip, key, alert_level
        ORDER BY cnt DESC LIMIT 50
    ''').fetchall()

    # Audit log — approved actions and outcomes
    audit = conn.execute('''
        SELECT miner_id, ip, model, action_taken, decision, problem
        FROM action_audit_log ORDER BY id DESC LIMIT 30
    ''').fetchall()

    # Miner logs collected
    logs = conn.execute('''
        SELECT miner_id, model, health_status, COUNT(*) as log_count
        FROM miner_logs GROUP BY miner_id, health_status
        ORDER BY log_count DESC LIMIT 30
    ''').fetchall()

    # Known dead boards
    dead = conn.execute(
        'SELECT * FROM known_dead_boards WHERE resolved_at IS NULL'
    ).fetchall()

    # Weather trends
    weather = conn.execute('''
        SELECT DATE(recorded_at) as day, AVG(temp_f) as avg_temp, AVG(humidity_pct) as avg_hum
        FROM weather_readings GROUP BY DATE(recorded_at) ORDER BY day DESC LIMIT 7
    ''').fetchall()

    conn.close()
    return {
        "miners": [dict(m) for m in miners],
        "notifications": [dict(n) for n in notifs],
        "audit": [dict(a) for a in audit],
        "logs": [dict(l) for l in logs],
        "dead_boards": [dict(d) for d in dead],
        "weather": [dict(w) for w in weather],
    }

def build_prompts(data):
    """Build prompts for Claude — split into batches to stay within context limits."""
    prompts = []

    # Prompt 1: Fleet-wide analysis
    p1 = ["You are Mining Guardian AI analyzing a Bitcoin mining fleet at BiXBiT USA in Fort Worth, TX.",
          "All cooling is liquid (hydro racks + immersion tank). No air cooling.",
          "Analyze this fleet data and provide insights.\n",
          f"FLEET: {len(data['miners'])} miners total\n"]

    for m in data["miners"]:
        profiles = m["profiles_seen"] or "none"
        p1.append(f"Miner {m['miner_id']} ({m['model']}) @ {m['ip']} | "
                  f"FW: {m['firmware_manufacturer'] or '?'} | "
                  f"Scans: {m['total_scans']} | Flagged: {m['times_flagged']}x | "
                  f"HR avg={m['avg_hr']:.0f}% min={m['min_hr']:.0f}% max={m['max_hr']:.0f}% | "
                  f"Temp avg={m['avg_temp']:.0f}°C max={m['max_temp']:.0f}°C | "
                  f"Actions: {m['actions_seen'] or 'none'} | Profiles: {profiles[:80]}")

    p1.append("\nAMS NOTIFICATIONS (top 50):")
    for n in data["notifications"]:
        p1.append(f"  {n['miner_ip']} | {n['key']} ({n['alert_level']}): {n['cnt']}x")

    p1.append("\nAUDIT LOG (last 30 approved/denied actions):")
    for a in data["audit"]:
        p1.append(f"  Miner {a['miner_id']} @ {a['ip']} | {a['action_taken']} | {a['decision']} | {a['problem'][:100]}")

    p1.append("\nWEATHER (last 7 days):")
    for w in data["weather"]:
        p1.append(f"  {w['day']}: avg {w['avg_temp']:.0f}°F, humidity {w['avg_hum']:.0f}%")

    p1.append("\nDEAD BOARDS:")
    for d in data["dead_boards"]:
        p1.append(f"  Miner {d['miner_id']} @ {d['ip']} — boards: {d['board_indices']}")

    p1.append("\nProvide:")
    p1.append("1. FLEET HEALTH SCORE (1-10) with justification")
    p1.append("2. TOP 5 PROBLEM MINERS — what's wrong and what to do")
    p1.append("3. PATTERNS — recurring issues, correlations between miners/models/temps/weather")
    p1.append("4. ROOT CAUSES — distinguish hardware failures from firmware glitches from environmental issues")
    p1.append("5. RECOMMENDATIONS — prioritized action list for the operator")
    p1.append("6. PREDICTIONS — which miners are likely to fail next based on trends")

    prompts.append("\n".join(p1))
    return prompts

def main():
    if not CLAUDE_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set in .env")
        return

    logger.info("=" * 60)
    logger.info("DEEP ANALYSIS — Feeding all data to Claude")
    logger.info("=" * 60)

    data = gather_fleet_data()
    logger.info("Data gathered: %d miners, %d notifications, %d audit entries, %d log records",
                len(data["miners"]), len(data["notifications"]),
                len(data["audit"]), len(data["logs"]))

    prompts = build_prompts(data)

    all_insights = []
    for i, prompt in enumerate(prompts):
        logger.info("Processing prompt %d/%d (%d chars)...", i+1, len(prompts), len(prompt))
        response = query_claude(prompt)
        if response:
            all_insights.append(response)
            print(f"\n{'='*60}")
            print(f"CLAUDE ANALYSIS {i+1}")
            print(f"{'='*60}")
            print(response)

    # Save to knowledge.json
    if all_insights:
        from knowledge_manager import KnowledgeManager
        km = KnowledgeManager()
        for insight in all_insights:
            km.add_llm_insight(insight, miner_id="claude_deep_analysis")
        km.save()
        logger.info("Insights saved to knowledge.json")

    logger.info("Deep analysis complete")


if __name__ == "__main__":
    main()
