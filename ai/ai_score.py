#!/usr/bin/env python3
"""
ai_score.py
Mining Guardian — AI Intelligence Score Calculator

Cumulative, ever-growing score that reflects the lifetime learning
of the Mining Guardian AI system. No caps — the score grows with
every scan, every action, every training session.

Score components:
  - Data Ingested:    Total raw data points collected across all tables
  - Knowledge Depth:  Insights, patterns, cross-miner analysis, LLM analyses
  - Actions Taken:    Every decision — approved, denied, auto, tickets, predictions
  - Outcomes Learned: Labeled restart outcomes + denial reasons captured
  - Autonomy Growth:  Cumulative auto-actions + confidence-based decisions

The total score is the SUM of all components — it only goes up.
Every 5-minute scan adds to Data Ingested.
Every training session adds to Knowledge Depth.
Every operator interaction adds to Actions Taken.
"""

import os
import json
from pathlib import Path
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import DictCursor

_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_PATH = str(_ROOT / "knowledge.json")


def _pg_dsn() -> str:
    """Build a Postgres DSN from GUARDIAN_PG_* env vars."""
    return (
        f"host={os.environ.get('GUARDIAN_PG_HOST', 'localhost')} "
        f"port={os.environ.get('GUARDIAN_PG_PORT', '5432')} "
        f"user={os.environ.get('GUARDIAN_PG_USER', 'guardian_app')} "
        f"password={os.environ['GUARDIAN_PG_PASSWORD']} "
        f"dbname={os.environ.get('GUARDIAN_PG_DBNAME', 'mining_guardian')}"
    )


class _PgConnWrapper:
    """Adapter that mimics sqlite3.Connection's shortcuts while delegating
    to a real psycopg2 connection using DictCursor."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        cur = self._conn.cursor(cursor_factory=DictCursor)
        cur.execute(sql, params or ())
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)


def calculate_score(conn=None, knowledge=None) -> dict:
    """Calculate the full cumulative AI score.
    
    Returns dict with total_score (uncapped, always growing) and breakdown.
    """
    close_conn = False
    if conn is None:
        conn = _PgConnWrapper(psycopg2.connect(_pg_dsn()))
        close_conn = True

    if knowledge is None:
        try:
            with open(KNOWLEDGE_PATH) as f:
                knowledge = json.load(f)
        except Exception:
            knowledge = {}

    # ═══════════════════════════════════════════════════════════
    # DATA INGESTED — every row in every table counts
    # Grows every 5-minute scan automatically
    # ═══════════════════════════════════════════════════════════
    data_counts = {}
    data_tables = {
        "scans": 10,                # each scan = 10 pts
        "miner_readings": 1,        # each reading = 1 pt
        "chain_readings": 1,        # per-board data
        "pool_readings": 1,         # pool share data
        "miner_state_readings": 1,  # device state
        "miner_ams_extended": 1,    # AMS extended fields
        "miner_hardware": 50,       # hardware identity = high value
        "miner_logs": 25,           # each log file = 25 pts
        "log_metrics": 0.01,        # 9.7M rows × 0.01 = ~97k pts
        "ams_notifications": 0.5,   # AMS alerts
        "hvac_readings": 5,         # facility data = valuable
        "weather_readings": 2,      # environmental context
    }
    
    data_score = 0
    for table, weight in data_tables.items():
        try:
            cnt = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0
            data_counts[table] = cnt
            data_score += int(cnt * weight)
        except Exception:
            data_counts[table] = 0

    # ═══════════════════════════════════════════════════════════
    # KNOWLEDGE DEPTH — what the AI has synthesized
    # Grows with training sessions and pattern detection
    # ═══════════════════════════════════════════════════════════
    issues = len(knowledge.get("known_issues", []))
    patterns = len(knowledge.get("patterns", []))
    profiles = len(knowledge.get("miner_profiles", {}))
    has_cross_miner = 1 if knowledge.get("cross_miner_analysis") else 0
    rich_profiles = sum(1 for p in knowledge.get("miner_profiles", {}).values()
                        if p.get("issue_history"))

    # Local LLM scan analyses (from Qwen 32B every scan)
    llm_scan_analyses = len(knowledge.get("llm_scan_analyses", []))
    # Operator rules extracted from denial reasons
    operator_rules = len(knowledge.get("operator_rules", []))

    total_analyses = 0
    try:
        total_analyses = conn.execute("SELECT COUNT(*) FROM llm_analysis").fetchone()[0] or 0
    except Exception:
        pass

    knowledge_score = (
        issues * 100 +              # each insight = 100 pts
        patterns * 500 +            # each pattern = 500 pts
        profiles * 50 +             # each profile = 50 pts
        rich_profiles * 100 +       # profiles with history = bonus 100
        has_cross_miner * 2000 +    # cross-miner analysis = 2000 pts
        total_analyses * 25 +       # each Claude LLM analysis = 25 pts
        llm_scan_analyses * 50 +    # each local LLM scan analysis = 50 pts
        operator_rules * 1000       # each operator rule = 1000 pts (very valuable)
    )

    knowledge_detail = {
        "insights": issues,
        "patterns": patterns,
        "profiles": profiles,
        "rich_profiles": rich_profiles,
        "cross_miner_analysis": bool(has_cross_miner),
        "llm_analyses": total_analyses,
        "llm_scan_analyses": llm_scan_analyses,
        "operator_rules": operator_rules,
    }

    # ═══════════════════════════════════════════════════════════
    # ACTIONS TAKEN — every decision the system made
    # Grows with every approval, denial, auto-action
    # ═══════════════════════════════════════════════════════════
    action_counts = {}
    action_queries = {
        "approved": ("SELECT COUNT(*) FROM action_audit_log WHERE decision='APPROVED'", 50),
        "denied": ("SELECT COUNT(*) FROM action_audit_log WHERE decision='DENIED'", 25),
        "auto_overnight": ("SELECT COUNT(*) FROM action_audit_log WHERE decision='AUTO_OVERNIGHT'", 100),
        "escalated": ("SELECT COUNT(*) FROM action_audit_log WHERE decision='ESCALATED'", 200),
        "restarts": ("SELECT COUNT(*) FROM miner_restarts", 75),
        "tickets_created": ("SELECT COUNT(*) FROM known_dead_boards WHERE ticket_created IS NOT NULL", 500),
        "predictions_fired": ("SELECT COUNT(*) FROM action_audit_log WHERE action_taken LIKE '%%PREEMPTIVE%%' OR action_taken LIKE '%%POWER_PROFILE%%'", 150),
    }
    
    actions_score = 0
    for key, (query, weight) in action_queries.items():
        try:
            cnt = conn.execute(query).fetchone()[0] or 0
            action_counts[key] = cnt
            actions_score += cnt * weight
        except Exception:
            action_counts[key] = 0

    # ═══════════════════════════════════════════════════════════
    # OUTCOMES LEARNED — labeled results that improve accuracy
    # Each labeled outcome teaches the AI what works
    # ═══════════════════════════════════════════════════════════
    outcome_detail = {"success": 0, "failure": 0, "partial": 0, "pending": 0,
                      "denial_reasons": 0, "success_rate_pct": 0}
    outcomes_score = 0
    try:
        outcomes = conn.execute("""
            SELECT outcome, COUNT(*) as cnt FROM miner_restarts
            WHERE outcome IS NOT NULL GROUP BY outcome
        """).fetchall()
        for r in outcomes:
            outcome_detail[r["outcome"].lower()] = r["cnt"]
        
        total_labeled = outcome_detail["success"] + outcome_detail["failure"] + outcome_detail["partial"]
        if total_labeled > 0:
            outcome_detail["success_rate_pct"] = round(
                outcome_detail["success"] / total_labeled * 100, 1)
        
        # Each labeled outcome = 200 pts (they're rare and valuable)
        outcomes_score += total_labeled * 200
        # Each pending = 50 pts (data collected, waiting for label)
        outcomes_score += outcome_detail["pending"] * 50
        
        # Denial reasons — extremely valuable training signal
        dr = conn.execute(
            "SELECT COUNT(*) FROM action_audit_log WHERE notes LIKE '%%DENIAL_REASON%%'"
        ).fetchone()[0] or 0
        outcome_detail["denial_reasons"] = dr
        outcomes_score += dr * 300  # each explained denial = 300 pts
    except Exception:
        pass

    # ═══════════════════════════════════════════════════════════
    # AUTONOMY GROWTH — cumulative autonomous operation
    # Every auto-action without human = the system earning trust
    # ═══════════════════════════════════════════════════════════
    autonomy_detail = {"auto_actions": 0, "manual_actions": 0, "auto_rate_pct": 0,
                       "fingerprints_built": 0, "signals_detected": 0}
    autonomy_score = 0
    try:
        auto = action_counts.get("auto_overnight", 0)
        manual = action_counts.get("approved", 0)
        autonomy_detail["auto_actions"] = auto
        autonomy_detail["manual_actions"] = manual
        if auto + manual > 0:
            autonomy_detail["auto_rate_pct"] = round(auto / (auto + manual) * 100, 1)
        
        # Each autonomous action = 150 pts
        autonomy_score += auto * 150
        
        # Fingerprints built
        autonomy_detail["fingerprints_built"] = profiles
        autonomy_score += profiles * 75
        
        # Pre-failure signals detected (from predictor)
        try:
            signals = conn.execute("""
                SELECT COUNT(*) FROM action_audit_log 
                WHERE action_taken LIKE '%%PREEMPTIVE%%'
            """).fetchone()[0] or 0
            autonomy_detail["signals_detected"] = signals
            autonomy_score += signals * 200
        except Exception:
            pass
    except Exception:
        pass

    # ═══════════════════════════════════════════════════════════
    # TOTAL — sum of everything, never capped
    # ═══════════════════════════════════════════════════════════
    total = (data_score + knowledge_score + actions_score + outcomes_score + autonomy_score) // 10

    result = {
        "total_score": total,
        "components": {
            "data_ingested": {"score": data_score, "detail": data_counts},
            "knowledge_depth": {"score": knowledge_score, "detail": knowledge_detail},
            "actions_taken": {"score": actions_score, "detail": action_counts},
            "outcomes_learned": {"score": outcomes_score, "detail": outcome_detail},
            "autonomy_growth": {"score": autonomy_score, "detail": autonomy_detail},
        },
        "total_data_points": sum(data_counts.values()),
        "calculated_at": datetime.now().isoformat(),
    }

    if close_conn:
        conn.close()

    return result


def format_number(n):
    """Format large numbers with commas and K/M suffixes for display."""
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n/1_000:.1f}K"
    return f"{n:,}"


if __name__ == "__main__":
    result = calculate_score()
    print(f"\n{'='*60}")
    print(f"  MINING GUARDIAN AI SCORE: {format_number(result['total_score'])}")
    print(f"  Total Data Points: {format_number(result['total_data_points'])}")
    print(f"{'='*60}")
    for name, comp in result["components"].items():
        print(f"\n  {name.upper().replace('_',' ')}: {format_number(comp['score'])} pts")
        for k, v in comp["detail"].items():
            if isinstance(v, (int, float)):
                print(f"    {k}: {format_number(v) if isinstance(v, int) and v > 999 else v}")
            else:
                print(f"    {k}: {v}")
    print(f"\n{'='*60}\n")
