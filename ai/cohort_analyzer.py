#!/usr/bin/env python3
"""
cohort_analyzer.py — Fast Cohort-Based Daily Analysis

REPLACES: daily_deep_dive.py (which was too slow at 135 min per miner)

NEW APPROACH:
- Analyze cohorts (groups of similar miners) not individual miners
- ~5 min per cohort instead of ~135 min per miner
- Only analyze outliers individually
- Total time: 2-3 hours instead of 30+ hours

CREATED: 2026-04-19
BRANCH: feature/fast-cohort-analysis
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / ai))
sys.path.insert(0, str(_ROOT / core))

# Reuse existing cohort building logic
from train_cohort import (
    build_cohorts,
    summarize_cohort,
    _normalize_model,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("cohort_analyzer")

DB_PATH = str(_ROOT / "guardian.db")
KNOWLEDGE_PATH = _ROOT / "knowledge.json"
WIP_BASE = _ROOT / "cohort_analysis_wip"

# Qwen config
OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://100.110.87.1:11434")
QWEN_MODEL = "qwen2.5:32b-instruct-q4_K_M"
QWEN_TIMEOUT = 600  # 10 min max per cohort (vs 135 min per miner before!)

# Limits
MAX_PROMPT_CHARS = 15000  # Target smaller prompts for speed
MAX_OUTLIER_DEEP_DIVES = 10  # Cap individual analyses


def query_qwen(prompt: str, label: str = "") -> Optional[str]:
    """Send prompt to Qwen and return response."""
    import requests
    
    url = f"{OLLAMA_URL}/api/generate"
    payload = {
        "model": QWEN_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_ctx": 16384,  # Smaller context = faster
            "num_predict": 2000,  # Shorter responses
        }
    }
    
    start = time.time()
    try:
        logger.info("Qwen call [%s]: prompt=%d chars, timeout=%ds", 
                   label, len(prompt), QWEN_TIMEOUT)
        resp = requests.post(url, json=payload, timeout=QWEN_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        response_text = data.get("response", "")
        elapsed = time.time() - start
        logger.info("Qwen OK [%s]: %.1fs, output=%d chars", 
                   label, elapsed, len(response_text))
        return response_text
    except Exception as e:
        logger.error("Qwen error [%s]: %s", label, e)
        return None


def build_cohort_prompt(cohort_key: Tuple, summary: Dict, operator_rules: List[str]) -> str:
    """Build a compact prompt for cohort analysis.
    
    Target: <15K chars (vs 35K for per-miner deep dive)
    """
    model, firmware, chip_bin, pcb, cooling = cohort_key
    agg = summary.get("aggregates", {})
    outliers = summary.get("outliers", [])
    problems = summary.get("top_problems", [])
    outcomes = summary.get("restart_outcomes", [])
    
    # Build compact operator rules summary (first line of each)
    rules_summary = "\n".join(f"- {r.split(chr(10))[0][:80]}" for r in operator_rules[:5])
    
    # Build outlier list
    outlier_text = ""
    if outliers:
        outlier_text = "\n\nOUTLIERS (performing differently from cohort):\n"
        for o in outliers[:5]:
            outlier_text += f"- Miner {o['miner_id']} ({o['ip']}): {chr(44).join(o['reasons'])}\n"
    
    # Build problems list
    problems_text = ""
    if problems:
        problems_text = "\nRECENT ISSUES:\n"
        for p in problems[:3]:
            problems_text += f"- {p[problem]}: {p[cnt]} occurrences\n"
    
    prompt = f"""You are a Bitcoin mining fleet analyst. Analyze this cohort of miners.

COHORT: {model} / {firmware} / Chip Bin {chip_bin} / PCB {pcb} / Cooling {cooling}
MINERS IN COHORT: {summary.get(member_count, 0)}

PERFORMANCE (last 7 days):
- Average hashrate: {agg.get(avg_hr, N/A)}% of rated
- Hashrate range: {agg.get(min_hr, N/A)}% - {agg.get(max_hr, N/A)}%
- Average chip temp: {agg.get(avg_temp, N/A)}°C (max: {agg.get(max_temp, N/A)}°C)
- Offline readings: {agg.get(offline_count, 0)} / {agg.get(total_readings, 0)}
- Flagged readings: {agg.get(flag_count, 0)}
{problems_text}
RESTART OUTCOMES: {json.dumps([dict(o) for o in outcomes], indent=2) if outcomes else None recorded}
{outlier_text}
OPERATOR RULES (abbreviated):
{rules_summary}

Provide a brief analysis (max 500 words):
1. COHORT HEALTH: GREEN (healthy) / YELLOW (monitor) / RED (action needed)
2. KEY OBSERVATIONS: What patterns do you see?
3. OUTLIERS: Which specific miners need individual attention and why?
4. RECOMMENDATIONS: What actions should be taken (if any)?

Be concise. Focus on actionable insights.
"""
    return prompt


def build_fleet_synthesis_prompt(cohort_analyses: Dict[str, str]) -> str:
    """Build prompt for fleet-wide synthesis from cohort analyses."""
    
    # Summarize each cohort analysis
    summaries = []
    for cohort_key, analysis in cohort_analyses.items():
        # Extract just the health status and key points
        summary = analysis[:500] if analysis else "No analysis"
        summaries.append(f"## {cohort_key}\n{summary}\n")
    
    prompt = f"""You are a Bitcoin mining fleet analyst. Synthesize the following cohort analyses into a fleet-wide report.

{chr(10).join(summaries)}

Provide a fleet synthesis (max 300 words):
1. OVERALL FLEET HEALTH: Summary across all cohorts
2. COMMON PATTERNS: Issues appearing in multiple cohorts
3. PRIORITY ACTIONS: Top 3 things operator should do today
4. TRENDS: Any concerning trends to watch

Be concise and actionable.
"""
    return prompt


def run_cohort_analysis(dry_run: bool = False) -> int:
    """Main cohort analysis loop."""
    
    start_time = time.time()
    today = datetime.now().strftime("%Y-%m-%d")
    
    logger.info("=" * 70)
    logger.info("COHORT ANALYSIS starting — date=%s dry_run=%s", today, dry_run)
    logger.info("=" * 70)
    
    # Create WIP directory
    wip_dir = WIP_BASE / today
    wip_dir.mkdir(parents=True, exist_ok=True)
    
    # Load operator rules
    operator_rules = []
    if KNOWLEDGE_PATH.exists():
        try:
            knowledge = json.loads(KNOWLEDGE_PATH.read_text())
            operator_rules = knowledge.get("operator_rules", [])
        except Exception:
            pass
    logger.info("Loaded %d operator rules", len(operator_rules))
    
    # Connect to database and build cohorts
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    cohorts = build_cohorts(conn)
    logger.info("Built %d cohorts", len(cohorts))
    
    if dry_run:
        logger.info("DRY RUN — would analyze %d cohorts", len(cohorts))
        conn.close()
        return 0
    
    # Analyze each cohort
    cohort_analyses = {}
    all_outliers = []
    
    for i, (cohort_key, members) in enumerate(sorted(cohorts.items(), key=lambda x: -len(x[1])), 1):
        cohort_name = "/".join(str(k) for k in cohort_key)
        logger.info("[%d/%d] Cohort %s (%d miners)", i, len(cohorts), cohort_name, len(members))
        
        # Check for cached analysis
        cache_file = wip_dir / f"cohort_{cohort_name.replace(/, _)}.json"
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text())
                if not cached.get("skipped"):
                    logger.info("  Using cached analysis")
                    cohort_analyses[cohort_name] = cached.get("analysis", "")
                    all_outliers.extend(cached.get("outliers", []))
                    continue
            except Exception:
                pass
        
        # Build summary and prompt
        summary = summarize_cohort(conn, cohort_key, members)
        prompt = build_cohort_prompt(cohort_key, summary, operator_rules)
        
        logger.info("  Prompt size: %d chars", len(prompt))
        
        # Query Qwen
        analysis = query_qwen(prompt, label=f"cohort {cohort_name}")
        
        if analysis:
            cohort_analyses[cohort_name] = analysis
            all_outliers.extend(summary.get("outliers", []))
            
            # Cache result
            cache_file.write_text(json.dumps({
                "cohort_key": cohort_name,
                "member_count": len(members),
                "timestamp": datetime.now().isoformat(),
                "prompt_chars": len(prompt),
                "analysis": analysis,
                "outliers": summary.get("outliers", []),
            }, indent=2))
            logger.info("  ✓ Analysis complete (%d chars)", len(analysis))
        else:
            logger.warning("  ✗ Analysis failed")
    
    # Fleet synthesis
    logger.info("=" * 50)
    logger.info("FLEET SYNTHESIS")
    synth_prompt = build_fleet_synthesis_prompt(cohort_analyses)
    logger.info("Synthesis prompt: %d chars", len(synth_prompt))
    
    fleet_synthesis = query_qwen(synth_prompt, label="fleet synthesis")
    
    # Save to knowledge.json
    _save_to_knowledge(today, cohort_analyses, fleet_synthesis, all_outliers, start_time)
    
    elapsed = time.time() - start_time
    logger.info("=" * 70)
    logger.info("COHORT ANALYSIS complete — %.1f minutes", elapsed / 60)
    logger.info("  Cohorts analyzed: %d", len(cohort_analyses))
    logger.info("  Outliers flagged: %d", len(all_outliers))
    logger.info("=" * 70)
    
    conn.close()
    return 0


def _save_to_knowledge(date: str, cohort_analyses: Dict, fleet_synthesis: str,
                        outliers: List, start_time: float):
    """Save cohort analysis to knowledge.json."""
    
    knowledge = {}
    if KNOWLEDGE_PATH.exists():
        try:
            knowledge = json.loads(KNOWLEDGE_PATH.read_text())
        except Exception:
            pass
    
    if not isinstance(knowledge.get("cohort_analyses"), list):
        knowledge["cohort_analyses"] = []
    
    # Remove existing entry for same date
    knowledge["cohort_analyses"] = [
        e for e in knowledge["cohort_analyses"]
        if e.get("date") != date
    ]
    
    entry = {
        "date": date,
        "timestamp": datetime.now().isoformat(),
        "wall_time_seconds": int(time.time() - start_time),
        "cohorts_analyzed": len(cohort_analyses),
        "outliers_flagged": len(outliers),
        "cohort_summaries": {k: v[:500] for k, v in cohort_analyses.items()},  # Truncate for storage
        "fleet_synthesis": fleet_synthesis,
        "outliers": outliers[:20],  # Keep top 20
        "source": "qwen_cohort_analysis",
    }
    
    # Keep last 30 days
    knowledge["cohort_analyses"] = [entry] + knowledge["cohort_analyses"][:29]
    knowledge["last_updated"] = datetime.now().isoformat()
    
    KNOWLEDGE_PATH.write_text(json.dumps(knowledge, indent=2))
    logger.info("Saved cohort analysis to knowledge.json")


def main():
    parser = argparse.ArgumentParser(description="Fast Cohort-Based Analysis")
    parser.add_argument("--dry-run", action="store_true", help="List cohorts without analyzing")
    args = parser.parse_args()
    
    try:
        code = run_cohort_analysis(dry_run=args.dry_run)
        sys.exit(code)
    except KeyboardInterrupt:
        logger.error("Interrupted")
        sys.exit(130)
    except Exception as e:
        logger.error("Fatal: %s", e)
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
