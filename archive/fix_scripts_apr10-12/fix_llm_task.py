#!/usr/bin/env python3
"""Fix the hourly LLM task instructions to stop repeating operator rules and HVAC"""

with open("/root/Mining-Gaurdian/scripts/local_llm_analyzer.py", "r") as f:
    content = f.read()

old_task = '''=== YOUR TASK ===
Based on this scan data:

1. SUMMARY (2-3 sentences): What's CHANGED since the last scan? Any NEW trends?
   If nothing changed, say "Fleet stable, no changes from last scan" and move on.
2. CONCERNS (bullet list): Which miners need attention and why?
3. LOG ANALYSIS (if restart logs present): What changed between pre and post restart?
   Did the restart fix the actual problem or just mask it?
4. OPERATOR LEARNING: ONLY include this section if there are NEW denials with NEW reasons.
   The 20-minute post-restart cooldown rule is ALREADY KNOWN — do not repeat it.
   Skip this section entirely if there are no new lessons to learn.
5. PATTERN MATCH: If any flagged miners match known reliability patterns, note the correlation.
6. RECOMMENDATION (1-2 sentences): What should the operator do next?
   CRITICAL: Do NOT recommend HVAC inspection — the cooling system is working correctly.

Keep it concise, factual, and actionable. No fluff. You are an expert mining fleet analyst.

CRITICAL: Do NOT repeat the same analysis as previous scans. If you've already flagged
a miner multiple times and nothing has changed, just note "still pending" and move on.
Your job is to find NEW patterns and changes, not repeat yourself.'''

new_task = '''=== YOUR TASK ===
Based on this scan data, provide:

1. SUMMARY (2-3 sentences): What CHANGED since the last scan?
2. CONCERNS (bullet list): Which miners need immediate attention and why?
3. LOG ANALYSIS (only if restart logs present): What changed pre vs post restart?
4. RECOMMENDATION (1-2 sentences): Specific next action for the operator.

=== ABSOLUTE RULES - VIOLATIONS WILL BE FLAGGED ===
- NEVER mention HVAC, cooling systems, or environmental controls. The cooling is FINE.
- NEVER echo back operator rules. They are for YOUR reference, not to repeat.
- NEVER include "OPERATOR LEARNING" section - those rules are already known.
- NEVER pad the report - only report miners with real issues requiring action.
- If a miner was flagged before with no change, just say "still pending" - do not re-analyze.'''

if old_task in content:
    content = content.replace(old_task, new_task)
    with open("/root/Mining-Gaurdian/scripts/local_llm_analyzer.py", "w") as f:
        f.write(content)
    print("SUCCESS: Updated task instructions")
else:
    print("ERROR: Could not find old task block")
    # Show what we're looking for
    if "YOUR TASK" in content:
        idx = content.find("YOUR TASK")
        print("Found YOUR TASK at index", idx)
        print("Context:", content[idx:idx+500])
