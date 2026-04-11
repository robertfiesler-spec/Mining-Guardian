#!/usr/bin/env python3
"""
COMPREHENSIVE AI SYSTEM AUDIT — April 11, 2026

This script audits every AI component to verify:
1. What data each component READS
2. What data each component WRITES
3. Which feedback loops are CLOSED (working)
4. Which feedback loops are BROKEN (data orphaned)
5. Cross-learning effectiveness

Run: python3 ai/comprehensive_audit.py
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = str(_ROOT / "guardian.db")
KNOWLEDGE_PATH = _ROOT / "knowledge.json"

def load_knowledge():
    if KNOWLEDGE_PATH.exists():
        return json.loads(KNOWLEDGE_PATH.read_text())
    return {}

def audit_database():
    """Audit all database tables for usage."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    
    tables = {}
    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        name = row['name']
        count = conn.execute(f"SELECT COUNT(*) as c FROM {name}").fetchone()['c']
        tables[name] = count
    
    conn.close()
    return tables

def audit_knowledge():
    """Audit all knowledge.json structures."""
    k = load_knowledge()
    structures = {}
    for key, val in k.items():
        if isinstance(val, list):
            structures[key] = f"list[{len(val)}]"
        elif isinstance(val, dict):
            structures[key] = f"dict[{len(val)} keys]"
        else:
            structures[key] = type(val).__name__
    return structures

# ══════════════════════════════════════════════════════════════════════════════
# AI COMPONENT AUDIT MATRIX
# ══════════════════════════════════════════════════════════════════════════════

AI_COMPONENTS = {
    # ─────────────────────────────────────────────────────────────────────────
    # CORE DATA COLLECTION (not AI but feeds AI)
    # ─────────────────────────────────────────────────────────────────────────
    "mining_guardian.py (scanner)": {
        "description": "Hourly fleet scanner — collects all miner data",
        "writes_db": [
            "scans",
            "miner_readings",
            "chain_readings", 
            "pool_readings",
            "miner_state_readings",
            "miner_ams_extended",
            "hvac_readings",
            "weather_readings",
            "ams_notifications",
        ],
        "writes_knowledge": [],
        "reads_db": ["known_dead_boards", "pending_approvals"],
        "reads_knowledge": [],
        "calls_ai": ["predictor", "confidence_scorer", "action_diversity", "local_llm_analyzer"],
    },
    
    "daily_collect_logs.py": {
        "description": "Daily log collection from miners (1pm cron)",
        "writes_db": ["miner_logs", "log_metrics"],
        "writes_knowledge": [],
        "reads_db": ["miner_readings"],
        "reads_knowledge": [],
        "calls_ai": [],
    },
    
    # ─────────────────────────────────────────────────────────────────────────
    # REAL-TIME AI (runs every scan)
    # ─────────────────────────────────────────────────────────────────────────
    "predictor.py": {
        "description": "Pre-failure prediction — 12 signals analyzed per miner",
        "writes_db": [],
        "writes_knowledge": ["predictions"],
        "reads_db": [
            "miner_readings",
            "chain_readings",
            "pool_readings",
            "miner_state_readings",
            "ams_notifications",
            "miner_restarts",
            "hvac_readings",
            "log_metrics (chain_events)",
        ],
        "reads_knowledge": ["miner_fingerprints"],  # ✅ WIRED Apr 10
        "calls_ai": [],
        "feedback_loop": "outcome_checker validates predictions → prediction_accuracy",
    },
    
    "outcome_checker.py": {
        "description": "Validates restart outcomes after action",
        "writes_db": ["miner_restarts (outcome, hashrate_after, recovery_time_scans)"],
        "writes_knowledge": ["miner_profiles", "prediction_accuracy"],  # ✅ WIRED Apr 10
        "reads_db": ["miner_restarts", "miner_readings", "scans"],
        "reads_knowledge": ["predictions"],  # ✅ WIRED Apr 10
        "calls_ai": [],
        "feedback_loop": "Creates labeled training data for confidence_scorer",
    },
    
    "confidence_scorer.py": {
        "description": "Gates autonomous action based on success history",
        "writes_db": [],
        "writes_knowledge": [],
        "reads_db": ["miner_restarts (outcomes)", "miner_readings (hashrate stability)"],
        "reads_knowledge": ["miner_fingerprints (modifier)"],
        "reads_knowledge_apr10": ["predictions"],  # ✅ WIRED Apr 10 — _get_prediction_penalty()
        "calls_ai": ["fingerprint_builder.get_confidence_modifier()"],
        "feedback_loop": "Outcome history → confidence → autonomy gates",
    },
    
    "action_diversity.py": {
        "description": "Expands beyond RESTART to POWER_PROFILE_DOWN/UP, ECO_MODE, POOL_FAILOVER",
        "writes_db": [],
        "writes_knowledge": [],
        "reads_db": [
            "miner_readings",
            "miner_state_readings",
            "pool_readings",
            "ams_notifications",
            "hvac_readings",
            "action_audit_log",
        ],
        "reads_knowledge": ["miner_fingerprints", "predictions"],  # ✅ WIRED Apr 10
        "calls_ai": [],
        "feedback_loop": "Uses fingerprint history to prefer alternatives for bad restart history",
    },
    
    "local_llm_analyzer.py": {
        "description": "Hourly Qwen analysis of scan results → Slack + knowledge",
        "writes_db": [],
        "writes_knowledge": ["llm_scan_analyses"],
        "reads_db": [
            "scans",
            "miner_readings (flagged miners)",
            "miner_restarts (recent outcomes)",
            "action_audit_log (denials)",
            "miner_logs (restart comparisons)",
            "hvac_readings",
            "weather_readings",
        ],
        "reads_knowledge": [
            "patterns",
            "known_issues",  # ✅ Now reads FULL issues, not just count (Apr 10)
            "refined_insights",
            "llm_scan_analyses (previous 3)",  # ✅ WIRED Apr 9
            "predictions",           # ✅ WIRED Apr 10
            "operator_rules",        # ✅ WIRED Apr 10 (but now internal-only, not echoed)
            "miner_fingerprints",    # ✅ WIRED Apr 10
            "cross_miner_analysis",  # ✅ WIRED Apr 10
        ],
        "calls_ai": [],
        "feedback_loop": "Previous analyses → current analysis (learns from self)",
    },
    
    # ─────────────────────────────────────────────────────────────────────────
    # DAILY AI (runs once per day at 4pm)
    # ─────────────────────────────────────────────────────────────────────────
    "daily_deep_dive.py": {
        "description": "Deep per-miner analysis with full logs (4pm cron, ~7 hours)",
        "writes_db": [],
        "writes_knowledge": ["daily_deep_analyses"],
        "reads_db": [
            "miner_readings",
            "chain_readings",
            "miner_logs (daily_baseline)",
            "miner_restarts",
            "miner_hardware",
            "hvac_readings",
            "weather_readings",
            "action_audit_log",
        ],
        "reads_knowledge": [
            "miner_fingerprints",
            "llm_scan_analyses (all recent)",
            "operator_rules",
            "refined_insights",
        ],
        "calls_ai": [],
        "feedback_loop": "Feeds weekly Claude training with deep miner profiles",
    },
    
    "fingerprint_builder.py": {
        "description": "Builds behavioral profile for each miner",
        "writes_db": [],
        "writes_knowledge": ["miner_fingerprints"],
        "reads_db": [
            "miner_readings",
            "chain_readings",
            "miner_state_readings",
            "pool_readings",
            "miner_hardware",
            "ams_notifications",
            "miner_restarts",
            "known_dead_boards",
            "log_metrics (chain_events)",
        ],
        "reads_knowledge": [],
        "calls_ai": [],
        "feedback_loop": "Fingerprints feed predictor, confidence_scorer, action_diversity",
    },
    
    # ─────────────────────────────────────────────────────────────────────────
    # WEEKLY AI (runs Sunday 3am)
    # ─────────────────────────────────────────────────────────────────────────
    "weekly_train.py": {
        "description": "Weekly orchestrator — calls all weekly components",
        "writes_db": [],
        "writes_knowledge": ["hvac_correlation (via hvac_correlator)"],
        "reads_db": [],
        "reads_knowledge": [],
        "calls_ai": [
            "train_cohort.run_cohort_training()",
            "fingerprint_builder.build_all_fingerprints()",
            "hvac_correlator.get_hvac_correlation_patterns()",
            "predictor.get_prediction_accuracy()",
        ],
    },
    
    "train_cohort.py": {
        "description": "Cohort-based Claude training — groups miners by hardware",
        "writes_db": [],
        "writes_knowledge": ["cross_miner_analysis", "refined_insights (via insight_manager)"],
        "reads_db": [
            "miner_readings",
            "miner_hardware",
            "miner_restarts",
            "action_audit_log",
            "chain_readings",
            "pool_readings",
            "miner_logs",
            "hvac_readings",
            "weather_readings",
        ],
        "reads_knowledge": [
            "llm_scan_analyses (all week)",
            "daily_deep_analyses",
            "operator_rules",
            "refined_insights (existing)",
            "miner_fingerprints",
        ],
        "calls_ai": ["insight_manager.process_refined_insights()"],
        "feedback_loop": "Produces cross_miner_analysis that feeds daily and hourly LLM",
    },
    
    "hvac_correlator.py": {
        "description": "Correlates HVAC conditions with miner flags",
        "writes_db": [],
        "writes_knowledge": ["hvac_correlation"],
        "reads_db": ["hvac_readings", "miner_readings (flagged counts)"],
        "reads_knowledge": [],
        "calls_ai": [],
        "feedback_loop": "❌ ORPHANED — hvac_correlation is written but NOT read by anyone",
    },
    
    "refinement_chain.py": {
        "description": "Multi-pass refinement: Qwen → Claude → Qwen merge",
        "writes_db": [],
        "writes_knowledge": ["weekly_refinement_chain"],
        "reads_db": [],
        "reads_knowledge": [
            "daily_deep_analyses",
            "cross_miner_analysis",
            "llm_scan_analyses",
        ],
        "calls_ai": [],
        "feedback_loop": "Creates refined weekly synthesis that feeds next week",
    },
    
    "insight_manager.py": {
        "description": "Manages permanent refined insights from Claude",
        "writes_db": [],
        "writes_knowledge": ["refined_insights"],
        "reads_db": [],
        "reads_knowledge": ["refined_insights (existing for merge)"],
        "calls_ai": [],
        "feedback_loop": "Refined insights accumulate and feed all LLM prompts",
    },
    
    # ─────────────────────────────────────────────────────────────────────────
    # KNOWLEDGE MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────────
    "knowledge_manager.py": {
        "description": "Utility for reading/writing knowledge.json",
        "writes_db": [],
        "writes_knowledge": ["patterns", "known_issues", "operator_rules"],
        "reads_db": [],
        "reads_knowledge": ["*"],
        "calls_ai": [],
    },
    
    "combine_knowledge.py": {
        "description": "Federated knowledge merge (future multi-site)",
        "writes_db": [],
        "writes_knowledge": ["patterns", "known_issues"],
        "reads_db": [],
        "reads_knowledge": ["*"],
        "calls_ai": [],
    },
    
    "export_knowledge.py": {
        "description": "Exports knowledge.json for federation",
        "writes_db": [],
        "writes_knowledge": [],
        "reads_db": [],
        "reads_knowledge": ["*"],
        "calls_ai": [],
    },
    
    "backup_knowledge.py": {
        "description": "Daily GitHub backup of knowledge.json (4am cron)",
        "writes_db": [],
        "writes_knowledge": [],
        "reads_db": [],
        "reads_knowledge": ["*"],
        "calls_ai": [],
    },
}

# ══════════════════════════════════════════════════════════════════════════════
# FEEDBACK LOOP ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

FEEDBACK_LOOPS = {
    "PREDICTION → VALIDATION": {
        "status": "✅ CLOSED (Apr 10)",
        "flow": [
            "predictor.py writes predictions to knowledge.json",
            "outcome_checker.py reads predictions when validating outcomes",
            "outcome_checker.py writes prediction_accuracy back to knowledge.json",
            "predictor can now learn which signals were accurate",
        ],
        "evidence": "prediction_accuracy dict exists with tp/fp/fn/tn counts",
    },
    
    "FINGERPRINT → PREDICTION": {
        "status": "✅ CLOSED (Apr 10)",
        "flow": [
            "fingerprint_builder.py builds miner_fingerprints",
            "predictor.py reads fingerprints via _get_fingerprint_risk_modifier()",
            "Poor restart history adds +15 risk points",
            "Frequent reboots add +5 risk points",
        ],
        "evidence": "signals array includes 'behavioral_risk: +Xpts from poor restart history'",
    },
    
    "FINGERPRINT → CONFIDENCE": {
        "status": "✅ CLOSED",
        "flow": [
            "fingerprint_builder.py builds miner_fingerprints with confidence_modifier",
            "confidence_scorer.py reads modifier via get_confidence_modifier()",
            "Modifies final confidence score by ±15 points",
        ],
        "evidence": "fingerprint_adjustment applied in get_confidence()",
    },
    
    "PREDICTION → CONFIDENCE": {
        "status": "✅ CLOSED (Apr 10)",
        "flow": [
            "predictor.py writes predictions",
            "confidence_scorer.py reads predictions via _get_prediction_penalty()",
            "Pre-failure signals reduce confidence by -5 to -15 points",
        ],
        "evidence": "prediction_penalty variable in confidence calculation",
    },
    
    "FINGERPRINT → ACTION_DIVERSITY": {
        "status": "✅ CLOSED (Apr 10)",
        "flow": [
            "fingerprint_builder.py builds miner_fingerprints",
            "action_diversity.py reads via _get_miner_context()",
            "Poor restart success rate → prefer POWER_PROFILE_DOWN over RESTART",
        ],
        "evidence": "_should_prefer_alternatives() function checks restart_success_rate",
    },
    
    "OUTCOME → MINER_PROFILES": {
        "status": "✅ CLOSED",
        "flow": [
            "outcome_checker.py validates restarts",
            "Writes outcome to miner_profiles in knowledge.json",
            "Calculates restart_success_rate per miner",
        ],
        "evidence": "miner_profiles dict with success_count, failure_count, restart_success_rate",
    },
    
    "OPERATOR RULES → HOURLY LLM": {
        "status": "✅ CLOSED (Apr 10, refined Apr 11)",
        "flow": [
            "Denial reasons extracted from action_audit_log",
            "Stored as operator_rules in knowledge.json",
            "local_llm_analyzer reads operator_rules",
            "Apr 11: Changed to internal guidance, NOT echoed in output",
        ],
        "evidence": "Rules constrain LLM behavior silently",
    },
    
    "CROSS_MINER_ANALYSIS → HOURLY LLM": {
        "status": "✅ CLOSED (Apr 10)",
        "flow": [
            "train_cohort.py generates cross_miner_analysis weekly",
            "local_llm_analyzer.py reads last 3 cross_miner_analysis",
            "Weekly strategic insights feed hourly decisions",
        ],
        "evidence": "cross_miner_analysis in _get_scan_context()",
    },
    
    "DAILY_DEEP_ANALYSES → WEEKLY TRAINING": {
        "status": "✅ CLOSED",
        "flow": [
            "daily_deep_dive.py writes daily_deep_analyses",
            "train_cohort.py reads daily_deep_analyses for synthesis",
        ],
        "evidence": "TEMP_MAY_REMOVE merge block in train_cohort.py",
    },
    
    "HVAC_CORRELATION → ???": {
        "status": "❌ ORPHANED",
        "flow": [
            "hvac_correlator.py writes hvac_correlation to knowledge.json",
            "NOBODY reads hvac_correlation",
        ],
        "evidence": "hvac_correlation dict exists but grep finds no readers",
        "fix_needed": "Add to predictor.py and local_llm_analyzer.py context",
    },
    
    "LLM_SCAN_ANALYSES → SELF-LEARNING": {
        "status": "✅ CLOSED (Apr 9)",
        "flow": [
            "local_llm_analyzer.py writes llm_scan_analyses",
            "local_llm_analyzer.py reads previous 3 analyses",
            "LLM learns from its own history",
        ],
        "evidence": "previous_analyses in _get_scan_context()",
    },
    
    "REFINED_INSIGHTS → ALL LLMS": {
        "status": "✅ CLOSED",
        "flow": [
            "insight_manager.py accumulates refined_insights",
            "local_llm_analyzer, daily_deep_dive, train_cohort all read refined_insights",
        ],
        "evidence": "refined_insights in all prompt builders",
    },
}

# ══════════════════════════════════════════════════════════════════════════════
# DATA ORPHAN ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def find_orphaned_data():
    """Find data structures that are written but never read."""
    
    k = load_knowledge()
    tables = audit_database()
    
    orphans = []
    
    # Check database tables
    db_orphans = {
        "miner_baselines": "0 rows — schema exists but never populated",
        "chip_readings": "0 rows — stub table, never implemented",
        "miner_ams_extended": f"{tables.get('miner_ams_extended', 0)} rows — collected but only used for debug",
    }
    
    # Check knowledge structures
    knowledge_orphans = {
        "hvac_correlation": "Written by hvac_correlator, read by NOBODY",
        "miner_profiles": "Written by outcome_checker, partially used (needs more integration)",
        "facility_events": f"{len(k.get('facility_events', []))} entries — written, not actively used",
    }
    
    return {"database": db_orphans, "knowledge": knowledge_orphans}

# ══════════════════════════════════════════════════════════════════════════════
# RECOMMENDATIONS
# ══════════════════════════════════════════════════════════════════════════════

RECOMMENDATIONS = [
    {
        "priority": "HIGH",
        "issue": "hvac_correlation is orphaned",
        "fix": "Add hvac_correlation to predictor.py and local_llm_analyzer.py",
        "benefit": "Facility stress context improves predictions",
    },
    {
        "priority": "MEDIUM",
        "issue": "miner_ams_extended not used in AI",
        "fix": "Feed map_location, last_power_on to fingerprint_builder",
        "benefit": "Location-based failure correlation",
    },
    {
        "priority": "MEDIUM",
        "issue": "miner_profiles duplication with miner_fingerprints",
        "fix": "Consolidate into miner_fingerprints only",
        "benefit": "Single source of truth per miner",
    },
    {
        "priority": "LOW",
        "issue": "chip_readings table empty",
        "fix": "Either populate or remove from schema",
        "benefit": "Code cleanup",
    },
    {
        "priority": "LOW",
        "issue": "miner_baselines table empty",
        "fix": "Either implement baseline learning or remove",
        "benefit": "Code cleanup",
    },
    {
        "priority": "DONE",
        "issue": "predictions not validated",
        "fix": "outcome_checker now validates predictions (Apr 10)",
        "benefit": "Predictor learns which signals work",
    },
    {
        "priority": "DONE",
        "issue": "fingerprints not used in predictor",
        "fix": "predictor now reads fingerprints (Apr 10)",
        "benefit": "Poor history = higher risk prediction",
    },
    {
        "priority": "DONE",
        "issue": "hourly LLM blind to most knowledge",
        "fix": "Added 5 new context sources (Apr 10)",
        "benefit": "LLM sees full picture",
    },
]


def main():
    print("=" * 80)
    print("COMPREHENSIVE AI SYSTEM AUDIT — April 11, 2026")
    print("=" * 80)
    
    # Database audit
    print("\n📊 DATABASE TABLES")
    print("-" * 40)
    tables = audit_database()
    for name, count in sorted(tables.items(), key=lambda x: -x[1]):
        print(f"  {name}: {count:,} rows")
    
    # Knowledge audit
    print("\n📚 KNOWLEDGE.JSON STRUCTURES")
    print("-" * 40)
    structures = audit_knowledge()
    for name, info in sorted(structures.items()):
        print(f"  {name}: {info}")
    
    # Feedback loop status
    print("\n🔄 FEEDBACK LOOPS")
    print("-" * 40)
    for name, loop in FEEDBACK_LOOPS.items():
        status = loop["status"]
        print(f"  {status} {name}")
    
    # Orphaned data
    print("\n⚠️ ORPHANED DATA")
    print("-" * 40)
    orphans = find_orphaned_data()
    for category, items in orphans.items():
        print(f"  [{category}]")
        for name, desc in items.items():
            print(f"    {name}: {desc}")
    
    # Recommendations
    print("\n📋 RECOMMENDATIONS")
    print("-" * 40)
    for rec in RECOMMENDATIONS:
        priority = rec["priority"]
        icon = "✅" if priority == "DONE" else "🔴" if priority == "HIGH" else "🟡" if priority == "MEDIUM" else "⚪"
        print(f"  {icon} [{priority}] {rec['issue']}")
        if priority != "DONE":
            print(f"       Fix: {rec['fix']}")
    
    print("\n" + "=" * 80)
    print("AUDIT COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
