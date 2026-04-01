"""
train_llm_pass2.py
Mining Guardian — Second LLM Training Pass

Feeds miner scan readings, AMS notifications, and fleet-wide patterns
to Ollama for deeper analysis across ALL 58 miners.

Pass 1 covered 9 miners with CGMiner logs.
Pass 2 covers ALL miners using scan telemetry + AMS alerts.
"""

import sqlite3
import json
import logging
import time
from llm_analyzer import LLMAnalyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("train_llm_pass2")

DB_PATH = "guardian.db"


def get_miner_history():
    """Get scan history for every miner."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    miners = conn.execute('''
        SELECT miner_id, model, ip, COUNT(*) as scan_count,
               AVG(hashrate_pct) as avg_hr_pct,
               MIN(hashrate_pct) as min_hr_pct,
               MAX(hashrate_pct) as max_hr_pct,
               AVG(temp_chip) as avg_temp,
               MAX(temp_chip) as max_temp,
               SUM(CASE WHEN action IS NOT NULL AND action != 'MONITOR' THEN 1 ELSE 0 END) as times_flagged,
               GROUP_CONCAT(DISTINCT action) as action_types
        FROM miner_readings
        GROUP BY miner_id
        ORDER BY times_flagged DESC
    ''').fetchall()

    # Get AMS notifications per miner IP
    notifs = conn.execute('''
        SELECT miner_ip, key, alert_level, COUNT(*) as cnt
        FROM ams_notifications
        GROUP BY miner_ip, key, alert_level
        ORDER BY miner_ip, cnt DESC
    ''').fetchall()

    notif_map = {}
    for n in notifs:
        ip = n["miner_ip"]
        if ip not in notif_map:
            notif_map[ip] = []
        notif_map[ip].append(f'{n["key"]}({n["alert_level"]}): {n["cnt"]}x')

    conn.close()
    return [dict(m) for m in miners], notif_map


def train_pass2():
    analyzer = LLMAnalyzer()
    miners, notif_map = get_miner_history()
    logger.info("Pass 2: %d miners with scan history", len(miners))

    # Batch miners into groups of 5 for fleet-level analysis (smaller = faster on CPU)
    batch_size = 5
    results = []

    for i in range(0, len(miners), batch_size):
        batch = miners[i:i + batch_size]
        prompt_parts = [f"Fleet Analysis Batch {i // batch_size + 1} — {len(batch)} miners:\n"]

        for m in batch:
            ip = m["ip"]
            ams_alerts = ", ".join(notif_map.get(ip, ["none"]))
            prompt_parts.append(
                f"- Miner {m['miner_id']} ({m['model']}) @ {ip}: "
                f"{m['scan_count']} scans, flagged {m['times_flagged']}x, "
                f"HR avg={m['avg_hr_pct']:.0f}% min={m['min_hr_pct']:.0f}% max={m['max_hr_pct']:.0f}%, "
                f"Temp avg={m['avg_temp']:.0f}°C max={m['max_temp']:.0f}°C, "
                f"Actions: {m['action_types'] or 'none'}, "
                f"AMS alerts: {ams_alerts}"
            )

        prompt_parts.append(
            "\nFor each miner, classify as: HEALTHY, DEGRADED, or CRITICAL."
            "\nIdentify which miners share the same root cause."
            "\nList the top 3 miners that need immediate attention and why."
            "\nNote any fleet-wide patterns (common model issues, environmental, firmware)."
        )

        prompt = "\n".join(prompt_parts)
        logger.info("Analyzing batch %d/%d (%d miners)...",
                     i // batch_size + 1,
                     (len(miners) + batch_size - 1) // batch_size,
                     len(batch))

        response = analyzer.analyze_issues(
            scan_id=0, issues=[
                {"id": m["miner_id"], "model": m["model"], "ip": m["ip"],
                 "action": m["action_types"] or "NONE",
                 "issues": [f"Flagged {m['times_flagged']}x, HR avg {m['avg_hr_pct']:.0f}%"]}
                for m in batch
            ]
        )

        results.append({
            "batch": i // batch_size + 1,
            "miners": [m["miner_id"] for m in batch],
            "analysis": response[:500] if response else "no response"
        })
        logger.info("  → %s", (response or "")[:200])
        time.sleep(3)

    # Final fleet-wide summary
    logger.info("Generating fleet-wide summary...")
    summary_prompt = (
        f"You have analyzed {len(miners)} Bitcoin miners across {len(results)} batches.\n"
        f"Total scan readings: {sum(m['scan_count'] for m in miners)}\n"
        f"Fleet breakdown:\n"
        f"- Miners flagged 20+ times: {sum(1 for m in miners if m['times_flagged'] >= 20)}\n"
        f"- Miners flagged 10-19 times: {sum(1 for m in miners if 10 <= m['times_flagged'] < 20)}\n"
        f"- Miners flagged 1-9 times: {sum(1 for m in miners if 1 <= m['times_flagged'] < 10)}\n"
        f"- Miners never flagged: {sum(1 for m in miners if m['times_flagged'] == 0)}\n"
        f"- Average fleet hashrate: {sum(m['avg_hr_pct'] for m in miners) / len(miners):.1f}%\n"
        f"- Models: {', '.join(set(m['model'] for m in miners))}\n\n"
        f"Write a 1-paragraph executive summary of fleet health.\n"
        f"Then list the top 5 miners that need immediate maintenance and why."
    )

    summary = analyzer.analyze_issues(scan_id=0, issues=[
        {"id": "fleet", "model": "all", "ip": "summary",
         "action": "FLEET_SUMMARY",
         "issues": [summary_prompt]}
    ])

    print("\n" + "=" * 60)
    print("PASS 2 COMPLETE — Fleet-Wide Analysis")
    print("=" * 60)
    print(f"\nMiners analyzed: {len(miners)}")
    print(f"Batches processed: {len(results)}")
    print(f"\nFLEET SUMMARY:")
    print(summary)

    for r in results:
        print(f"\n--- Batch {r['batch']} (miners {r['miners']}) ---")
        print(r["analysis"])


if __name__ == "__main__":
    train_pass2()
