#!/usr/bin/env python3
"""
ai_score.py
Mining Guardian — AI Intelligence Score Calculator

Calculates a multi-dimensional score that reflects the ACTUAL depth
of the AI's learning — not just entry counts.

Score components (out of 1000):
  - Data Depth (0-200):  total scans, readings, chain data, log metrics collected
  - Knowledge (0-200):   issues, patterns, profiles, cross-miner analysis
  - Experience (0-200):  total actions taken, outcomes labeled, denial reasons captured
  - Accuracy (0-200):    restart success rate, prediction hit rate, false positive rate
  - Autonomy (0-200):    % of actions auto-executed vs manual, confidence score avg

Each component grows naturally as the system operates:
  - Every scan adds to Data Depth
  - Every training session adds to Knowledge  
  - Every approved/denied action adds to Experience
  - Every labeled outcome adds to Accuracy
  - Every auto-action vs manual adds to Autonomy
"""

import sqlite3
import json
import math
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = str(_ROOT / "guardian.db")
KNOWLEDGE_PATH = str(_ROOT / "knowledge.json")


def calculate_score(conn=None, knowledge=None) -> dict:
    """Calculate the full AI score breakdown.
    
    Returns dict with total_score (0-1000) and component breakdown.
    """
    close_conn = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        close_conn = True

    if knowledge is None:
        try:
            with open(KNOWLEDGE_PATH) as f:
                knowledge = json.load(f)
        except Exception:
            knowledge = {}

    # ── DATA DEPTH (0-200) ──────────────────────────────────────
    # How much raw data has the system collected?
    # Grows every 5-minute scan automatically
    total_scans = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0] or 0
    total_readings = conn.execute("SELECT COUNT(*) FROM miner_readings").fetchone()[0] or 0
    total_chain = conn.execute("SELECT COUNT(*) FROM chain_readings").fetchone()[0] or 0
    total_pool = conn.execute("SELECT COUNT(*) FROM pool_readings").fetchone()[0] or 0
    total_logs = conn.execute("SELECT COUNT(*) FROM miner_logs").fetchone()[0] or 0
    total_hardware = conn.execute("SELECT COUNT(DISTINCT miner_id) FROM miner_hardware").fetchone()[0] or 0
    total_log_metrics = conn.execute("SELECT COUNT(*) FROM log_metrics").fetchone()[0] or 0

    # Logarithmic scale so early data collection shows big jumps
    # 1000 scans = ~150 points, 5000 scans = ~185, 10000 = ~200
    data_raw = (
        total_scans * 1.0 +
        total_readings * 0.01 +
        total_chain * 0.01 +
        total_pool * 0.01 +
        total_logs * 0.5 +
        total_hardware * 5.0 +
        total_log_metrics * 0.0001
    )
    data_depth = min(200, int(200 * (math.log10(max(data_raw, 1)) / math.log10(100000))))

    # ── KNOWLEDGE (0-200) ───────────────────────────────────────
    # What has the AI learned and synthesized?
    # Grows with training sessions, pattern detection, cross-miner analysis
    issues = len(knowledge.get("known_issues", []))
    patterns = len(knowledge.get("patterns", []))
    profiles = len(knowledge.get("miner_profiles", {}))
    has_cross_miner = 1 if knowledge.get("cross_miner_analysis") else 0
    has_fleet_summary = 1 if knowledge.get("fleet_summary", {}).get("total_miners") else 0
    
    # Count profiles with actual LLM insights (not just empty stubs)
    rich_profiles = sum(
        1 for p in knowledge.get("miner_profiles", {}).values()
        if p.get("issue_history") or p.get("llm_insights") or p.get("restart_outcomes")
    )
    
    # Total LLM analyses ever performed (from DB)
    total_analyses = conn.execute(
        "SELECT COUNT(*) FROM llm_analysis"
    ).fetchone()[0] or 0

    knowledge_raw = (
        issues * 2.0 +
        patterns * 15.0 +
        profiles * 1.0 +
        rich_profiles * 3.0 +
        has_cross_miner * 30.0 +
        has_fleet_summary * 10.0 +
        total_analyses * 0.5
    )
    knowledge_score = min(200, int(200 * (math.log10(max(knowledge_raw, 1)) / math.log10(5000))))

    # ── EXPERIENCE (0-200) ──────────────────────────────────────
    # How many decisions has the system made and learned from?
    # Grows with every approval, denial, and overnight action
    total_approved = conn.execute(
        "SELECT COUNT(*) FROM action_audit_log WHERE decision='APPROVED'"
    ).fetchone()[0] or 0
    total_denied = conn.execute(
        "SELECT COUNT(*) FROM action_audit_log WHERE decision='DENIED'"
    ).fetchone()[0] or 0
    total_auto = conn.execute(
        "SELECT COUNT(*) FROM action_audit_log WHERE decision='AUTO_OVERNIGHT'"
    ).fetchone()[0] or 0
    total_expired = conn.execute(
        "SELECT COUNT(*) FROM action_audit_log WHERE approved_by LIKE '%Auto-Expired%'"
    ).fetchone()[0] or 0
    denial_reasons = conn.execute(
        "SELECT COUNT(*) FROM action_audit_log WHERE notes LIKE '%DENIAL_REASON%'"
    ).fetchone()[0] or 0
    total_restarts = conn.execute(
        "SELECT COUNT(*) FROM miner_restarts"
    ).fetchone()[0] or 0
    total_tickets = conn.execute(
        "SELECT COUNT(*) FROM known_dead_boards WHERE ticket_created IS NOT NULL"
    ).fetchone()[0] or 0

    experience_raw = (
        total_approved * 2.0 +
        total_denied * 1.0 +
        total_auto * 3.0 +       # auto actions worth more — system acted alone
        denial_reasons * 5.0 +     # explained denials are high-value training data
        total_restarts * 2.0 +
        total_tickets * 10.0
    )
    experience_score = min(200, int(200 * (math.log10(max(experience_raw, 1)) / math.log10(10000))))

    # ── ACCURACY (0-200) ────────────────────────────────────────
    # How good are the AI's decisions?
    # Grows as outcomes are labeled and success rate improves
    outcomes = conn.execute("""
        SELECT outcome, COUNT(*) as cnt
        FROM miner_restarts
        WHERE outcome IS NOT NULL AND outcome != 'PENDING'
        GROUP BY outcome
    """).fetchall()
    
    outcome_map = {r["outcome"]: r["cnt"] for r in outcomes}
    successes = outcome_map.get("SUCCESS", 0)
    failures = outcome_map.get("FAILURE", 0)
    partials = outcome_map.get("PARTIAL", 0)
    total_outcomes = successes + failures + partials

    if total_outcomes > 0:
        success_rate = (successes + partials * 0.5) / total_outcomes
        # Base accuracy from success rate (0-150)
        accuracy_base = int(success_rate * 150)
        # Bonus for volume of labeled outcomes (0-50)
        accuracy_volume = min(50, int(50 * (math.log10(max(total_outcomes, 1)) / math.log10(500))))
        accuracy_score = min(200, accuracy_base + accuracy_volume)
    else:
        accuracy_score = 0

    # ── AUTONOMY (0-200) ────────────────────────────────────────
    # How independently is the system operating?
    # Grows as auto-actions increase relative to manual
    total_actions = total_approved + total_auto
    if total_actions > 0:
        auto_rate = total_auto / total_actions
        # Base autonomy from auto rate (0-150)
        autonomy_base = int(auto_rate * 150)
        # Bonus for total volume of autonomous actions (0-50)
        autonomy_volume = min(50, int(50 * (math.log10(max(total_auto, 1)) / math.log10(1000))))
        autonomy_score = min(200, autonomy_base + autonomy_volume)
    else:
        autonomy_score = 0

    # ── TOTAL SCORE ─────────────────────────────────────────────
    total = data_depth + knowledge_score + experience_score + accuracy_score + autonomy_score

    result = {
        "total_score": total,
        "max_score": 1000,
        "components": {
            "data_depth": {
                "score": data_depth, "max": 200,
                "detail": {
                    "scans": total_scans,
                    "readings": total_readings,
                    "chain_readings": total_chain,
                    "pool_readings": total_pool,
                    "logs_collected": total_logs,
                    "hardware_identified": total_hardware,
                    "log_metrics": total_log_metrics,
                }
            },
            "knowledge": {
                "score": knowledge_score, "max": 200,
                "detail": {
                    "insights": issues,
                    "patterns": patterns,
                    "profiles": profiles,
                    "rich_profiles": rich_profiles,
                    "has_cross_miner": bool(has_cross_miner),
                    "has_fleet_summary": bool(has_fleet_summary),
                    "total_llm_analyses": total_analyses,
                }
            },
            "experience": {
                "score": experience_score, "max": 200,
                "detail": {
                    "approved": total_approved,
                    "denied": total_denied,
                    "auto_overnight": total_auto,
                    "expired": total_expired,
                    "denial_reasons": denial_reasons,
                    "restarts": total_restarts,
                    "tickets_created": total_tickets,
                }
            },
            "accuracy": {
                "score": accuracy_score, "max": 200,
                "detail": {
                    "success": successes,
                    "failure": failures,
                    "partial": partials,
                    "success_rate": round(success_rate * 100, 1) if total_outcomes > 0 else 0,
                }
            },
            "autonomy": {
                "score": autonomy_score, "max": 200,
                "detail": {
                    "auto_actions": total_auto,
                    "manual_actions": total_approved,
                    "auto_rate": round(auto_rate * 100, 1) if total_actions > 0 else 0,
                }
            },
        }
    }

    if close_conn:
        conn.close()

    return result


if __name__ == "__main__":
    result = calculate_score()
    print(f"\n{'='*60}")
    print(f"  MINING GUARDIAN AI SCORE: {result['total_score']} / {result['max_score']}")
    print(f"{'='*60}")
    for name, comp in result["components"].items():
        bar = "█" * (comp["score"] // 10) + "░" * ((200 - comp["score"]) // 10)
        print(f"  {name:15s} {bar} {comp['score']:3d}/200")
        for k, v in comp["detail"].items():
            print(f"    {k}: {v}")
    print(f"{'='*60}\n")
