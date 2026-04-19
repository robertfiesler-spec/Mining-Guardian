#!/usr/bin/env python3
"""
Claude-Powered Daily Deep Dive
Uses Claude API for per-miner analysis (temporary while Qwen GPU is down).
"""

import json
import sqlite3
import time
import logging
import sys
import os
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

# Config
DB_PATH = Path("/root/Mining-Gaurdian/guardian.db")
KNOWLEDGE_PATH = Path("/root/Mining-Gaurdian/knowledge.json")
LOG_DIR = Path("/root/Mining-Gaurdian/daily_miner_logs")
WIP_BASE = Path("/root/Mining-Gaurdian/daily_deep_dive_wip")

CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("claude_deep_dive")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_online_miners(conn) -> List[Dict]:
    latest = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    if not latest:
        return []
    rows = conn.execute("""
        SELECT miner_id, ip, model, status, hashrate_pct, current_profile, uptime
        FROM scan_miners WHERE scan_id = ?
    """, (latest["id"],)).fetchall()
    return [dict(r) for r in rows]


def get_miner_log(miner_id: str, date: str) -> Optional[str]:
    log_file = LOG_DIR / date / f"{miner_id}.log"
    if log_file.exists():
        return log_file.read_text()[:15000]
    return None


def get_24h_trends(conn, miner_id: str) -> Dict:
    trends = {}
    restarts = conn.execute("""
        SELECT restarted_at, restart_type, outcome, hashrate_before, hashrate_after
        FROM miner_restarts 
        WHERE miner_id = ? AND restarted_at >= datetime('now', '-24 hours')
        ORDER BY restarted_at DESC
    """, (miner_id,)).fetchall()
    trends["restarts"] = [dict(r) for r in restarts]
    
    chains = conn.execute("""
        SELECT chain_id, AVG(chip_temp) as avg_temp, MIN(chip_temp) as min_temp, MAX(chip_temp) as max_temp
        FROM chain_readings
        WHERE miner_id = ? AND recorded_at >= datetime('now', '-24 hours')
        GROUP BY chain_id
    """, (miner_id,)).fetchall()
    trends["chains"] = [dict(r) for r in chains]
    return trends


def build_prompt(miner: Dict, log: Optional[str], trends: Dict) -> str:
    prompt = f"""Analyze this Bitcoin miner briefly:

MINER: {miner.get('miner_id')} | IP: {miner.get('ip')} | MODEL: {miner.get('model')}
STATUS: {miner.get('status')} | HASHRATE: {miner.get('hashrate_pct', '?')}% | UPTIME: {miner.get('uptime', '?')}

24H: Restarts={len(trends.get('restarts', []))} Chains={trends.get('chains', [])}

"""
    if log:
        lines = log.split('\n')
        errors = [l for l in lines if 'error' in l.lower() or 'fail' in l.lower()][:5]
        if errors:
            prompt += "ERRORS:\n" + "\n".join(errors) + "\n\n"
        else:
            prompt += "LOG: Clean (no errors)\n\n"
    else:
        prompt += "LOG: Not available\n\n"
    
    prompt += """RULES: Temps <84C normal. Zero hashrate+no temps=OFF. All boards dead+control on=PSU failure.

Give: STATUS (healthy/degraded/failing/offline), ISSUES, ACTION (none/monitor/restart/power_cycle/ticket), REASON (1 sentence)"""
    return prompt


def query_claude(prompt: str) -> Optional[str]:
    if not CLAUDE_API_KEY:
        logger.error("No ANTHROPIC_API_KEY set")
        return None
    try:
        start = time.time()
        resp = requests.post("https://api.anthropic.com/v1/messages", json={
            "model": CLAUDE_MODEL,
            "max_tokens": 500,
            "messages": [{"role": "user", "content": prompt}]
        }, headers={
            "x-api-key": CLAUDE_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }, timeout=60)
        elapsed = time.time() - start
        resp.raise_for_status()
        data = resp.json()
        for block in data.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                text = block["text"]
                logger.info("Claude OK: %.1fs, %d chars", elapsed, len(text))
                return text
        return None
    except Exception as e:
        logger.error("Claude error: %s", e)
        return None


def run():
    today = datetime.now().strftime("%Y-%m-%d")
    logger.info("=" * 60)
    logger.info(f"CLAUDE DEEP DIVE — {today}")
    logger.info("=" * 60)
    
    knowledge = {}
    if KNOWLEDGE_PATH.exists():
        knowledge = json.loads(KNOWLEDGE_PATH.read_text())
    
    wip_dir = WIP_BASE / today
    wip_dir.mkdir(parents=True, exist_ok=True)
    
    conn = get_db()
    miners = get_online_miners(conn)
    logger.info(f"Online miners: {len(miners)}")
    
    results = {}
    start_time = time.time()
    
    for i, miner in enumerate(miners, 1):
        mid = miner["miner_id"]
        cache = wip_dir / f"claude_{mid}.json"
        
        if cache.exists():
            logger.info(f"[{i}/{len(miners)}] {mid}: cached")
            cached = json.loads(cache.read_text())
            results[mid] = cached.get("analysis", "")
            continue
        
        logger.info(f"[{i}/{len(miners)}] {mid} ({miner.get('ip')}) {miner.get('model')}")
        
        log = get_miner_log(mid, today)
        trends = get_24h_trends(conn, mid)
        prompt = build_prompt(miner, log, trends)
        
        analysis = query_claude(prompt)
        if analysis:
            results[mid] = analysis
            cache.write_text(json.dumps({
                "miner_id": mid,
                "timestamp": datetime.now().isoformat(),
                "analysis": analysis
            }, indent=2))
    
    conn.close()
    elapsed = time.time() - start_time
    
    # Save to knowledge
    if "daily_deep_analyses" not in knowledge:
        knowledge["daily_deep_analyses"] = []
    knowledge["daily_deep_analyses"] = [
        e for e in knowledge["daily_deep_analyses"] if e.get("date") != today
    ]
    
    entry = {
        "date": today,
        "timestamp": datetime.now().isoformat(),
        "wall_time_seconds": int(elapsed),
        "miners_online": len(miners),
        "miners_analyzed": len(results),
        "per_miner": results,
        "fleet_synthesis": f"Claude deep dive: {len(results)}/{len(miners)} miners in {elapsed/60:.1f} min",
        "source": "claude_deep_dive",
    }
    knowledge["daily_deep_analyses"] = [entry] + knowledge["daily_deep_analyses"][:29]
    knowledge["last_updated"] = datetime.now().isoformat()
    KNOWLEDGE_PATH.write_text(json.dumps(knowledge, indent=2))
    
    logger.info("=" * 60)
    logger.info(f"COMPLETE: {len(results)}/{len(miners)} miners in {elapsed/60:.1f} min")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(run())
