#!/usr/bin/env python3
"""Patch local_llm_analyzer.py to include refined_insights in Qwen prompts."""

ANALYZER_PATH = '/root/Mining-Gaurdian/scripts/local_llm_analyzer.py'

with open(ANALYZER_PATH, 'r') as f:
    content = f.read()

# Find where to insert - after the patterns section, before Instructions
old_block = '''        # Instructions
        lines.append("""
=== YOUR TASK ==='''

new_block = '''        # Refined Fleet Insights — data-driven procurement and cohort intelligence
        insights = ctx.get("refined_insights", {})
        if insights:
            lines.append(f"\\n--- FLEET INTELLIGENCE ({len(insights)} insights) ---")
            lines.append("Use these data-driven insights to inform your analysis:")
            for key, ins in list(insights.items())[:10]:
                action = ins.get("action", "?")
                topic = ins.get("topic", key)
                insight_text = ins.get("insight", "")[:150]
                confidence = ins.get("confidence", "?")
                # Color-code by action type
                if action in ("REJECT", "REPLACE"):
                    prefix = "[DONT BUY]"
                elif action == "KEEP":
                    prefix = "[GOOD]"
                elif action in ("WATCH", "INVESTIGATE"):
                    prefix = "[MONITOR]"
                elif action == "TUNE":
                    prefix = "[RULE]"
                else:
                    prefix = f"[{action}]"
                lines.append(f"  {prefix} {topic} ({confidence}): {insight_text}")

        # Instructions
        lines.append("""
=== YOUR TASK ==='''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open(ANALYZER_PATH, 'w') as f:
        f.write(content)
    print("SUCCESS: Patched local_llm_analyzer.py with refined_insights section")
else:
    print("ERROR: Could not find insertion point")
