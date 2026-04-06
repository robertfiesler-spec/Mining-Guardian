#!/usr/bin/env python3
"""Inspect what the weekly training actually wrote to knowledge.json"""
import json

d = json.load(open("knowledge.json"))

print("=" * 60)
print("WHAT THE WEEKLY TRAINING ACTUALLY DID")
print("=" * 60)

# 1. Cross-miner analysis
cma = d.get("cross_miner_analysis", [])
print(f"\n--- CROSS-MINER ANALYSIS (new section): {'YES' if cma else 'NO'} ---")
if cma:
    for item in cma:
        print(f"  Analyzed: {item.get('analyzed_at','?')}")
        print(f"  Summary: {item.get('summary','')[:500]}")

# 2. Fleet summary
fs = d.get("fleet_summary", {})
print(f"\n--- FLEET SUMMARY ---")
for k, v in fs.items():
    print(f"  {k}: {str(v)[:150]}")

# 3. Miner profiles — what's IN them
profiles = d.get("miner_profiles", {})
print(f"\n--- MINER PROFILES ({len(profiles)} total) ---")
if profiles:
    # Show structure of one profile
    sample_key = list(profiles.keys())[0]
    sample = profiles[sample_key]
    print(f"  Sample profile ({sample_key}):")
    print(f"  Keys: {list(sample.keys())}")
    for k, v in sample.items():
        val_str = str(v)[:150]
        print(f"    {k}: {val_str}")
    
    # Count profiles with LLM insights vs empty
    has_insights = sum(1 for p in profiles.values() if p.get("llm_insights") or p.get("restart_outcomes"))
    print(f"\n  Profiles with LLM insights: {has_insights}/{len(profiles)}")

# 4. Known issues — show recent ones
issues = d.get("known_issues", [])
print(f"\n--- KNOWN ISSUES ({len(issues)} total) — last 5: ---")
for i in issues[-5:]:
    if isinstance(i, dict):
        print(f"  [{i.get('timestamp','?')[:16]}] miner={i.get('miner_id','?')} {str(i.get('insight',''))[:200]}")
    else:
        print(f"  {str(i)[:200]}")

# 5. Patterns
patterns = d.get("patterns", [])
print(f"\n--- PATTERNS ({len(patterns)} total) ---")
for p in patterns:
    print(f"  {str(p)[:200]}")

# 6. LLM insights added by training
print(f"\n--- TRAINING INSIGHTS (what Claude Sonnet wrote) ---")
insight_count = 0
for issue in issues:
    if isinstance(issue, dict) and "2026-04-06" in str(issue.get("timestamp", "")):
        insight_count += 1
        if insight_count <= 5:
            print(f"  [{issue.get('miner_id','?')}] {str(issue.get('insight',''))[:250]}")
print(f"\n  Total new insights from today's training: {insight_count}")

print(f"\n{'=' * 60}")
print(f"SCORE BREAKDOWN: {len(issues)} issues + {len(patterns)}×10 patterns + {len(profiles)} profiles = {len(issues) + len(patterns)*10 + len(profiles)}")
print(f"{'=' * 60}")
