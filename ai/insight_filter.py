#!/usr/bin/env python3
"""
insight_filter.py — Filter insights against existing operator/pattern rules

Before proposing insights to the operator, check if they are already covered
by locked rules. Mark duplicates/covered insights as "already_covered" so
they do not clutter the review queue.

Also consolidates contradictory insights (e.g., "0110 is worse" vs "0130 is worse")
into a single "needs_more_data" insight.
"""

import json
import re
from pathlib import Path
from datetime import datetime

KNOWLEDGE_PATH = Path("/root/Mining-Gaurdian/knowledge.json")


def load_knowledge():
    with open(KNOWLEDGE_PATH) as f:
        return json.load(f)


def save_knowledge(k):
    tmp = str(KNOWLEDGE_PATH) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(k, f, indent=2)
    import os
    os.replace(tmp, str(KNOWLEDGE_PATH))


def get_existing_rules(k):
    """Extract all locked rules/patterns for comparison."""
    rules = []
    
    # Operator rules (list of dicts or strings)
    for rule in k.get("operator_rules", []):
        if isinstance(rule, dict):
            rules.append(rule.get("rule", "").lower())
            rules.append(rule.get("description", "").lower())
        else:
            rules.append(str(rule).lower())
    
    # Pattern rules (list of dicts)
    for pattern in k.get("pattern_rules", []):
        if isinstance(pattern, dict):
            rules.append(pattern.get("name", "").lower())
            rules.append(pattern.get("rule", "").lower())
    
    # Process rules (list)
    for rule in k.get("process_rules", []):
        if isinstance(rule, dict):
            rules.append(rule.get("rule", "").lower())
        else:
            rules.append(str(rule).lower())
    
    return [r for r in rules if r]


def insight_matches_rule(insight_text, rules):
    """Check if an insight is already covered by existing rules."""
    insight_lower = insight_text.lower()
    
    # Key phrases that indicate coverage
    coverage_patterns = [
        # Restart rules
        (r"restart.*fail", "restart"),
        (r"21%.*restart", "restart"),
        (r"restart.*success.*rate", "restart"),
        (r"restart.*approval", "restart"),
        
        # Hardware failure patterns  
        (r"zero.*telemetry.*72", "hardware_failure"),
        (r"no.*pdu.*access", "hardware_failure"),
        (r"100%.*hardware.*failure", "hardware_failure"),
        (r"complete.*failure", "hardware_failure"),
        
        # AH3880/firmware rules
        (r"ah3880.*firmware", "firmware"),
        (r"auradine.*firmware", "firmware"),
        (r"firmware.*breakdown.*thermal", "firmware"),
        (r"firmware.*rollback", "firmware"),
        
        # Temperature rules
        (r"84.*threshold", "temperature"),
        (r"chip.*temp.*84", "temperature"),
        
        # PSU patterns
        (r"psu.*voltage.*14\.[34]", "psu"),
        (r"voltage.*fluctuation.*14", "psu"),
        (r"psu.*partial.*circuit", "psu"),
    ]
    
    for pattern, rule_keyword in coverage_patterns:
        if re.search(pattern, insight_lower):
            # Check if we have a rule covering this
            for rule in rules:
                if rule_keyword in rule:
                    return True, rule_keyword
    
    return False, None


def find_contradictions(insights):
    """Find insights that contradict each other."""
    contradictions = {}
    
    # Group by topic patterns
    pcb_insights = []
    for key, ins in insights.items():
        if isinstance(ins, dict):
            insight_text = ins.get("insight", "")
            # Look for PCB revision comparisons
            if "pcb=" in insight_text.lower() or ("0110" in insight_text and "0130" in insight_text):
                pcb_insights.append((key, ins))
    
    # Check for contradictions in PCB insights (more than 3 = conflicting data)
    if len(pcb_insights) > 3:
        contradictions["pcb_revision_analysis"] = [k for k, _ in pcb_insights]
    
    return contradictions


def filter_insights():
    """Main filter function."""
    k = load_knowledge()
    insights = k.get("refined_insights", {})
    rules = get_existing_rules(k)
    
    print(f"Loaded {len(rules)} existing rules to check against")
    
    stats = {
        "total": len(insights),
        "already_covered": 0,
        "contradictory": 0,
        "needs_review": 0,
        "details": []
    }
    
    # Find contradictions first
    contradictions = find_contradictions(insights)
    
    for key, ins in insights.items():
        if not isinstance(ins, dict):
            continue
        
        insight_text = ins.get("insight", "")
        current_status = ins.get("status", "pending")
        
        # Skip already processed
        if current_status in ["approved", "rejected", "already_covered", "contradictory"]:
            continue
        
        # Check if covered by existing rules
        is_covered, matching_rule = insight_matches_rule(insight_text, rules)
        if is_covered:
            ins["status"] = "already_covered"
            ins["covered_by"] = matching_rule
            ins["filtered_at"] = datetime.now().isoformat()
            stats["already_covered"] += 1
            stats["details"].append(f"COVERED: {key} -> {matching_rule}")
            continue
        
        # Check if part of contradiction group
        for group_name, group_keys in contradictions.items():
            if key in group_keys:
                ins["status"] = "contradictory"
                ins["contradiction_group"] = group_name
                ins["filtered_at"] = datetime.now().isoformat()
                stats["contradictory"] += 1
                stats["details"].append(f"CONTRADICTORY: {key} -> {group_name}")
                break
        else:
            # Not covered, not contradictory = needs review
            if current_status == "pending":
                stats["needs_review"] += 1
    
    # Save updated knowledge
    k["refined_insights"] = insights
    save_knowledge(k)
    
    return stats


if __name__ == "__main__":
    print("=== INSIGHT FILTER ===")
    print()
    stats = filter_insights()
    print()
    print(f"Total insights: {stats[\"total\"]}")
    print(f"Already covered by rules: {stats[\"already_covered\"]}")
    print(f"Contradictory (need more data): {stats[\"contradictory\"]}")
    print(f"Need operator review: {stats[\"needs_review\"]}")
    print()
    if stats["details"]:
        print("Details:")
        for detail in stats["details"]:
            print(f"  {detail}")
