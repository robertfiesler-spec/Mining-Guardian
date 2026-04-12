#!/usr/bin/env python3
"""Add confidence scores to approval cards in mining_guardian.py"""
import re

with open('/root/Mining-Gaurdian/core/mining_guardian.py', 'r') as f:
    content = f.read()

# The old code block (lines ~3271-3282)
old_text = '''            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{idx}.* ☐  {icon} `{ip}` — *{label}*\\n"
                        f"      {model}  |  📍 {loc}  |  ⚡ HR: *{hr}%*  |  {temp_icon} Temp: *{temp}°C*"
                    )
                }
            })

        # ── Divider + approval instructions'''

new_text = '''            # Get confidence score for this action
            conf_str = ""
            try:
                from ai.confidence_scorer import get_confidence, get_gate
                score, _ = get_confidence(str(issue.get("id", "")), ip, issue["action"],
                                          hashrate_pct=hr if hr != "?" else None)
                gate = get_gate(score)
                gate_emoji = "🟢" if gate == "AUTO" else "🟡" if gate == "ASK" else "🔴"
                conf_str = f"  |  {gate_emoji} Conf: *{score}%*"
            except Exception:
                pass

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{idx}.* ☐  {icon} `{ip}` — *{label}*\\n"
                        f"      {model}  |  📍 {loc}  |  ⚡ HR: *{hr}%*  |  {temp_icon} Temp: *{temp}°C*{conf_str}"
                    )
                }
            })

        # ── Divider + approval instructions'''

if old_text in content:
    content = content.replace(old_text, new_text)
    with open('/root/Mining-Gaurdian/core/mining_guardian.py', 'w') as f:
        f.write(content)
    print("SUCCESS: Added confidence to approval cards")
else:
    print("ERROR: Target block not found")
