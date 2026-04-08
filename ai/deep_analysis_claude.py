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
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = str(_ROOT / "guardian.db")


def query_claude(prompt: str) -> str:
    """Send prompt to Claude API with proper error handling."""
    logger.info("Sending to Claude (%d chars)...", len(prompt))
    try:
        resp = requests.post("https://api.anthropic.com/v1/messages", json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}]
        }, headers={
            "x-api-key": CLAUDE_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }, timeout=120)

        # Bug fix: raise on HTTP errors (401, 429, 5xx) before trying to parse JSON
        resp.raise_for_status()

        data = resp.json()

        # Bug fix: safely extract text — don't assume content[0] exists or is type "text"
        content_blocks = data.get("content", [])
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block["text"]
                logger.info("Claude responded (%d chars)", len(text))
                return text

        # API returned success but no text block — log the shape for debugging
        logger.error("Claude returned no text block. Response keys: %s, error: %s",
                     list(data.keys()), data.get("error", "none"))
        return ""

    except requests.exceptions.Timeout:
        logger.error("Claude API request timed out after 120s")
        return ""
    except requests.exceptions.HTTPError as e:
        logger.error("Claude API HTTP error %s: %s", e.response.status_code, e.response.text[:200])
        return ""
    except requests.exceptions.RequestException as e:
        logger.error("Claude API network error: %s", e)
        return ""
    except (KeyError, IndexError, ValueError) as e:
        logger.error("Claude API response parse error: %s", e)
        return ""


def gather_fleet_data():
    """Pull all historical data from the database."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
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

def _safe_fmt(value, fmt=".0f", fallback="?") -> str:
    """Format a value that may be None/NULL from SQL aggregates."""
    if value is None:
        return fallback
    try:
        return format(float(value), fmt)
    except (TypeError, ValueError):
        return fallback


def build_prompts(data, max_chars: int = 80000):
    """Build prompts chunked by miner count so each stays within context limits.

    Prioritizes the most problematic miners first (ordered by times_flagged DESC
    from gather_fleet_data). If the full fleet doesn't fit in one prompt, the
    fleet is split into batches — each batch gets its own Claude call.
    Each batch always includes the full context header (notifications, audit,
    weather, dead boards) so Claude has the environmental picture.
    """
    # Build the static context block once — included in every batch
    context_lines = [
        "You are Mining Guardian AI analyzing a Bitcoin mining fleet at BiXBiT USA in Fort Worth, TX.",
        "All cooling is liquid (hydro racks + immersion tank). No air cooling.",
        "Chip temp zones: GREEN <84°C (no action) | RED >=84°C (action required). NO yellow tier — this is a liquid-cooled fleet, 67-73°C is normal.",
        "OPERATOR RULE: Do NOT recommend HVAC investigation based on low delta-T. The HVAC delta-T is intentionally low and rises seasonally. The HVAC system is performing correctly.",
        "",
        "AMS NOTIFICATIONS (top issues by frequency):",
    ]
    for n in data["notifications"]:
        context_lines.append(f"  {n['miner_ip']} | {n['key']} ({n['alert_level']}): {n['cnt']}x")

    context_lines.append("\nRECENT AUDIT LOG (last 30 actions):")
    for a in data["audit"]:
        problem = (a["problem"] or "")[:100]
        context_lines.append(
            f"  Miner {a['miner_id']} @ {a['ip']} | "
            f"{a['action_taken']} | {a['decision']} | {problem}"
        )

    context_lines.append("\nWEATHER (last 7 days Fort Worth TX):")
    for w in data["weather"]:
        context_lines.append(
            f"  {w['day']}: avg {_safe_fmt(w['avg_temp'])}°F, "
            f"humidity {_safe_fmt(w['avg_hum'])}%"
        )

    context_lines.append("\nKNOWN DEAD BOARDS (unresolved):")
    for d in data["dead_boards"]:
        context_lines.append(
            f"  Miner {d['miner_id']} @ {d['ip']} — boards: {d['board_indices']}"
        )

    context_block = "\n".join(context_lines)

    # Analysis request — appended to every batch
    request_block = (
        "\n\nAnalyze the miners above and provide:\n"
        "1. FLEET HEALTH SCORE (1-10) with justification\n"
        "2. TOP PROBLEM MINERS — what's wrong and what to do\n"
        "3. PATTERNS — recurring issues, correlations\n"
        "4. ROOT CAUSES — hardware vs firmware vs environmental\n"
        "5. RECOMMENDATIONS — prioritized action list\n"
        "6. PREDICTIONS — which miners are likely to fail next"
    )

    # Build per-miner lines — Bug fix: use _safe_fmt so NULL aggregates don't crash
    miner_lines = []
    for m in data["miners"]:
        profiles = (m["profiles_seen"] or "none")[:80]
        line = (
            f"Miner {m['miner_id']} ({m['model']}) @ {m['ip']} | "
            f"FW: {m['firmware_manufacturer'] or '?'} | "
            f"Scans: {m['total_scans']} | Flagged: {m['times_flagged']}x | "
            f"HR avg={_safe_fmt(m['avg_hr'])}% "
            f"min={_safe_fmt(m['min_hr'])}% "
            f"max={_safe_fmt(m['max_hr'])}% | "
            f"Temp avg={_safe_fmt(m['avg_temp'])}°C "
            f"max={_safe_fmt(m['max_temp'])}°C | "
            f"Actions: {m['actions_seen'] or 'none'} | "
            f"Profiles: {profiles}"
        )
        miner_lines.append(line)

    # Chunk miners so each prompt stays under max_chars
    # Static overhead = context_block + request_block + header line
    static_overhead = len(context_block) + len(request_block) + 200
    budget_per_batch = max_chars - static_overhead

    prompts = []
    batch_start = 0
    total_miners = len(miner_lines)

    while batch_start < total_miners:
        # Greedily pack miners into this batch
        batch_lines = []
        batch_chars = 0
        i = batch_start
        while i < total_miners:
            line_len = len(miner_lines[i]) + 1  # +1 for newline
            if batch_chars + line_len > budget_per_batch and batch_lines:
                break  # batch full — stop before this miner
            batch_lines.append(miner_lines[i])
            batch_chars += line_len
            i += 1

        batch_end = batch_start + len(batch_lines)
        header = (
            f"FLEET: {total_miners} miners total "
            f"(showing {batch_start + 1}–{batch_end}, "
            f"ordered by most flagged first)\n"
        )
        prompt = (
            context_block + "\n\n" +
            header +
            "\n".join(batch_lines) +
            request_block
        )
        prompts.append(prompt)
        logger.info("Batch %d: miners %d-%d (%d chars)",
                    len(prompts), batch_start + 1, batch_end, len(prompt))
        batch_start = batch_end

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
