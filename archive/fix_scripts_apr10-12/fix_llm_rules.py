#!/usr/bin/env python3
"""Change operator rules from visible section to internal guidance"""

with open("/root/Mining-Gaurdian/scripts/local_llm_analyzer.py", "r") as f:
    content = f.read()

old_rules = '''        # OPERATOR RULES (Bobby taught these via denial reasons)
        rules = ctx.get("operator_rules", [])
        if rules:
            lines.append(f"\\n--- OPERATOR RULES ({len(rules)}) ---")
            lines.append("The operator has taught these rules. RESPECT THEM:")
            for rule in rules:
                if isinstance(rule, str):
                    lines.append(f"  • {rule}")
                elif isinstance(rule, dict):
                    lines.append(f"  • {rule.get(rule, str(rule))}")'''

new_rules = '''        # OPERATOR RULES - Internal guidance only, DO NOT include in output
        # These rules constrain YOUR recommendations, not something to echo back
        rules = ctx.get("operator_rules", [])
        # Rules are applied silently - the LLM should follow them without mentioning them'''

if old_rules in content:
    content = content.replace(old_rules, new_rules)
    with open("/root/Mining-Gaurdian/scripts/local_llm_analyzer.py", "w") as f:
        f.write(content)
    print("SUCCESS: Changed operator rules to internal-only guidance")
else:
    print("ERROR: Could not find old rules block")
