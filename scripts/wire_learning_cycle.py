#!/usr/bin/env python3
"""
Wire the continuous learning cycle:
1. Local LLM analyses feed into Claude's weekly training
2. Claude's refined knowledge feeds back to local LLM prompts
"""
import os

REPO = "/Users/BigBobby/Documents/GitHub/Mining Gaurdian"

# ═══════════════════════════════════════════════════════════
# FIX 1: Claude weekly training reads local LLM's scan analyses
# Add to the fleet-level prompt in train_comprehensive.py
# ═══════════════════════════════════════════════════════════
train_path = os.path.join(REPO, "ai/train_comprehensive.py")
with open(train_path) as f:
    c = f.read()

# Insert before CROSS-MINER ANALYSIS
target = '    lines.append(\n        "\\n=== CROSS-MINER ANALYSIS REQUESTED ===\\n"'

local_llm_section = '''    # ── Local LLM weekly analyses — what the on-site AI learned this week ──
    # The local LLM (Qwen 32B) runs after every scan and produces analyses.
    # Claude should read these to understand what the local AI observed,
    # validate its conclusions, and build on them with deeper insight.
    try:
        import json as _json
        from pathlib import Path as _Path
        _kp = _Path(__file__).resolve().parent.parent / "knowledge.json"
        if _kp.exists():
            _k = _json.loads(_kp.read_text())
            local_analyses = _k.get("llm_scan_analyses", [])
            if local_analyses:
                lines.append("\\n--- LOCAL LLM ANALYSES THIS WEEK ---")
                lines.append(f"The on-site AI (Qwen 32B) analyzed {len(local_analyses)} scans this week.")
                lines.append("Review its analyses below. Validate correct conclusions, correct mistakes,")
                lines.append("and identify patterns the local AI missed that you can see fleet-wide.")
                # Show most recent 10 analyses
                for a in local_analyses[:10]:
                    ts = a.get("timestamp", "?")[:16]
                    scan = a.get("scan_id", "?")
                    text = a.get("analysis", "")[:300]
                    lines.append(f"\\n  [Scan #{scan} @ {ts}]:")
                    lines.append(f"    {text}")

            # Also include any rules the local LLM extracted from denial reasons
            local_rules = _k.get("operator_rules", [])
            if local_rules:
                lines.append("\\n--- OPERATOR RULES (extracted by local LLM) ---")
                lines.append("The local AI extracted these rules from operator denial reasons.")
                lines.append("Validate and refine them:")
                for rule in local_rules[:10]:
                    lines.append(f"  - {rule}")
    except Exception:
        pass

'''

if target in c:
    c = c.replace(target, local_llm_section + target)
    print("FIX 1: Claude training now reads local LLM analyses")
else:
    print("FIX 1: Could not find insertion point")

# Also add question 8 to the cross-miner analysis
old_q = '"7. Which restarts actually improved hashrate vs which were wasted effort? Should any miners stop getting restarted?\\n"'
new_q = old_q + '\n        "8. Review the local AI analyses above — are its conclusions correct? What did it miss?\\n"'

if old_q in c:
    c = c.replace(old_q, new_q)
    print("FIX 1b: Added Q8 — Claude validates local LLM conclusions")

with open(train_path, "w") as f:
    f.write(c)

# ═══════════════════════════════════════════════════════════
# FIX 2: Local LLM prompts include Claude's refined knowledge
# The local_llm_analyzer already reads knowledge.json patterns,
# but let's make it also read Claude's cross-miner analysis
# and any validated rules from the weekly training
# ═══════════════════════════════════════════════════════════
llm_path = os.path.join(REPO, "ai/local_llm_analyzer.py")
with open(llm_path) as f:
    lc = f.read()

# Add Claude's validated rules to the scan prompt
old_patterns = '''        # Known patterns
        if ctx["patterns"]:
            lines.append(f"\\n--- KNOWN PATTERNS ({len(ctx[\\'patterns\\'])}) ---")'''

# Use a simpler approach — add to the _get_scan_context method
old_knowledge = '''        # Knowledge patterns
        knowledge = {}
        if KNOWLEDGE_PATH.exists():
            try:
                knowledge = json.loads(KNOWLEDGE_PATH.read_text())
            except Exception:
                pass

        conn.close()

        return {'''

new_knowledge = '''        # Knowledge — includes both Claude's weekly analysis and local LLM history
        knowledge = {}
        if KNOWLEDGE_PATH.exists():
            try:
                knowledge = json.loads(KNOWLEDGE_PATH.read_text())
            except Exception:
                pass

        # Claude's cross-miner analysis (from weekly training)
        cross_miner = knowledge.get("cross_miner_analysis", {})

        # Operator rules extracted by local LLM or Claude
        operator_rules = knowledge.get("operator_rules", [])

        conn.close()

        return {'''

if old_knowledge in lc:
    lc = lc.replace(old_knowledge, new_knowledge)
    print("FIX 2a: Local LLM context includes Claude's analysis and operator rules")

    # Also add these to the return dict
    old_return_end = '''            "known_issues_count": len(knowledge.get("known_issues", [])),
        }'''
    new_return_end = '''            "known_issues_count": len(knowledge.get("known_issues", [])),
            "cross_miner_analysis": cross_miner,
            "operator_rules": operator_rules,
        }'''
    lc = lc.replace(old_return_end, new_return_end)
    print("FIX 2b: Added cross_miner_analysis and operator_rules to context")

    # Add these to the prompt builder
    old_instructions = '        # Instructions'
    new_instructions = '''        # Claude's cross-miner analysis (from weekly training)
        xm = ctx.get("cross_miner_analysis", {})
        if xm:
            lines.append("\\n--- CLAUDE WEEKLY ANALYSIS (use as reference) ---")
            for key, val in list(xm.items())[:5]:
                lines.append(f"  {key}: {str(val)[:150]}")

        # Operator rules (accumulated from denials)
        rules = ctx.get("operator_rules", [])
        if rules:
            lines.append("\\n--- OPERATOR RULES (follow these) ---")
            for rule in rules:
                lines.append(f"  - {rule}")

        # Instructions'''
    lc = lc.replace(old_instructions, new_instructions)
    print("FIX 2c: Local LLM prompt includes Claude's analysis and operator rules")

    with open(llm_path, "w") as f:
        f.write(lc)
else:
    print("FIX 2: Could not find knowledge block in local_llm_analyzer")

# ═══════════════════════════════════════════════════════════
# FIX 3: Store operator rules extracted by LLM in knowledge.json
# Update the denial processing to save rules persistently
# ═══════════════════════════════════════════════════════════
# Already storing analyses in llm_scan_analyses — need to also
# store extracted rules in operator_rules[]
old_store = '''    def _store_analysis(self, scan_id: int, analysis: str) -> None:
        """Store LLM analysis in knowledge.json."""'''

new_store = '''    def store_operator_rule(self, rule: str) -> None:
        """Store an operator rule extracted from denial reasons."""
        try:
            knowledge = {}
            if KNOWLEDGE_PATH.exists():
                knowledge = json.loads(KNOWLEDGE_PATH.read_text())

            rules = knowledge.get("operator_rules", [])
            # Deduplicate — don't add if similar rule exists
            if not any(rule[:30].lower() in r.lower() for r in rules):
                rules.append(rule)
                knowledge["operator_rules"] = rules[-20:]  # keep last 20

                tmp = str(KNOWLEDGE_PATH) + ".tmp"
                with open(tmp, "w") as f:
                    json.dump(knowledge, f, indent=2)
                import os
                os.replace(tmp, str(KNOWLEDGE_PATH))
                logger.info("Operator rule stored: %s", rule[:80])
        except Exception as e:
            logger.warning("Failed to store operator rule: %s", e)

    def _store_analysis(self, scan_id: int, analysis: str) -> None:
        """Store LLM analysis in knowledge.json."""'''

with open(llm_path) as f:
    lc = f.read()

if old_store in lc:
    lc = lc.replace(old_store, new_store)
    with open(llm_path, "w") as f:
        f.write(lc)
    print("FIX 3: Added store_operator_rule method")
else:
    print("FIX 3: Could not find store method")

# Also update process_denial to store the rule
old_denial = '        if analysis:\n            logger.info("LLM denial rule for %s: %s", ip, analysis[:150])\n        return analysis'
new_denial = '''        if analysis:
            logger.info("LLM denial rule for %s: %s", ip, analysis[:150])
            # Store the rule persistently
            self.store_operator_rule(analysis)
        return analysis'''

with open(llm_path) as f:
    lc = f.read()
if old_denial in lc:
    lc = lc.replace(old_denial, new_denial)
    with open(llm_path, "w") as f:
        f.write(lc)
    print("FIX 3b: Denial rules now persist in knowledge.json")

print("\nDone — compile check next")
