"""
train_llm.py
Mining Guardian — Feed historical logs to LLM for pattern learning

Reads miner logs from guardian.db and sends them to Ollama in batches
to build up the LLM's understanding of normal vs problematic miner behavior.
Saves analysis results to the llm_analysis table.
"""

import sqlite3
import json
import sys
import logging
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "core") not in sys.path:
    sys.path.insert(0, str(_ROOT / "core"))

from llm_analyzer import LLMAnalyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("train_llm")

DB_PATH = "guardian.db"


def get_logs_with_content():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    logs = conn.execute("""
        SELECT miner_id, model, health_status, collected_at, log_file, content
        FROM miner_logs
        WHERE LENGTH(content) > 100
        ORDER BY collected_at ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in logs]


def train_on_logs():
    analyzer = LLMAnalyzer()
    logs = get_logs_with_content()
    logger.info("Found %d logs with content to analyze", len(logs))

    # Group logs by miner
    by_miner = {}
    for log in logs:
        mid = log["miner_id"]
        if mid not in by_miner:
            by_miner[mid] = []
        by_miner[mid].append(log)

    logger.info("Grouped into %d unique miners", len(by_miner))

    results = []
    for miner_id, miner_logs in by_miner.items():
        model = miner_logs[0]["model"]
        statuses = [l["health_status"] for l in miner_logs]
        flagged_count = statuses.count("flagged")
        healthy_count = statuses.count("healthy")

        # Build a summary of this miner's log history
        log_excerpts = []
        for l in miner_logs[:5]:  # max 5 logs per miner
            content = l["content"] or "(empty)"
            # Full log — no truncation. We section it so the LLM gets structured data:
            # Boot header (EEPROM, hardware identity, PSU, chip counts) — first 8000 chars
            # Steady-state operations (chip hashrate, PSU voltage, system health) — middle sample
            # Recent tail — last 4000 chars (most recent events)
            if len(content) > 16000:
                boot_section = content[:8000]
                mid_start = len(content) // 2
                mid_section = content[mid_start:mid_start + 4000]
                tail_section = content[-4000:]
                full_excerpt = (
                    f"[BOOT/INIT]\n{boot_section}\n"
                    f"[MID-OPERATION SAMPLE]\n{mid_section}\n"
                    f"[RECENT TAIL]\n{tail_section}"
                )
            else:
                full_excerpt = content
            log_excerpts.append(
                f"[{l['collected_at'][:16]}] {l['log_file']} ({l['health_status']}):\n{full_excerpt}"
            )

        prompt = (
            f"Analyze the log history for miner {miner_id} ({model}).\n"
            f"This miner has been flagged {flagged_count} times and was healthy {healthy_count} times.\n\n"
            f"Log excerpts:\n" + "\n---\n".join(log_excerpts) + "\n\n"
            f"Based on these logs:\n"
            f"1. What patterns do you see?\n"
            f"2. Is this a hardware issue, firmware issue, or environmental?\n"
            f"3. What is the likely root cause?\n"
            f"4. Should this miner be prioritized for maintenance?"
        )

        logger.info("Analyzing miner %s (%s) — %d logs, %d flagged",
                     miner_id, model, len(miner_logs), flagged_count)

        response = analyzer.analyze_single_miner(
            scan_id=0, miner_id=miner_id, ip="historical",
            model=model, problem=f"Historical analysis: {flagged_count} flags",
            logs={"log_excerpts": log_excerpts[:3]}
        )

        results.append({
            "miner_id": miner_id,
            "model": model,
            "flagged": flagged_count,
            "analysis": response[:500]
        })

        logger.info("  → %s", response[:200])
        time.sleep(2)  # don't overwhelm Ollama

    # Print summary
    print("\n" + "=" * 60)
    print("TRAINING COMPLETE — LLM Analysis Summary")
    print("=" * 60)
    for r in results:
        print(f"\nMiner {r['miner_id']} ({r['model']}) — flagged {r['flagged']}x:")
        print(f"  {r['analysis']}")

    print(f"\nTotal miners analyzed: {len(results)}")
    print(f"Results saved to llm_analysis table in guardian.db")


if __name__ == "__main__":
    train_on_logs()
